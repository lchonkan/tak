"""TAK Linux backends — faster-whisper, PipeWire/ALSA, xdotool/xclip."""

from __future__ import annotations

import ctypes
import os
import site
import subprocess
import time
import wave
from typing import Optional

import numpy as np
import sounddevice as sd

from tak.app import (
    BaseAudioRecorder, BaseTranscriber,
    WHISPER_RATE, CHANNELS, DTYPE, BLOCK_SIZE,
    status, announce, warn, error, _resample, C,
)


# ─── CUDA initialization ────────────────────────────────────────────────
def ensure_cuda_libs():
    """Pre-load pip-installed NVIDIA libs so ctranslate2 can find them at runtime.

    Setting LD_LIBRARY_PATH from within the process is too late — the dynamic
    linker has already cached the search paths.  Instead we use ctypes.CDLL
    with RTLD_GLOBAL so that when ctranslate2 later asks for libcublas.so.12
    it is already in the process address space.
    """
    try:
        sp = site.getsitepackages()[0]
    except Exception:
        return

    # Order matters: cublas depends on cublasLt, cudnn depends on cublas
    libs_to_load = [
        os.path.join(sp, "nvidia", "cublas", "lib", "libcublasLt.so.12"),
        os.path.join(sp, "nvidia", "cublas", "lib", "libcublas.so.12"),
        os.path.join(sp, "nvidia", "cudnn", "lib", "libcudnn.so.9"),
    ]
    for lib_path in libs_to_load:
        if os.path.isfile(lib_path):
            try:
                ctypes.CDLL(lib_path, mode=ctypes.RTLD_GLOBAL)
            except OSError:
                pass  # best effort


# ─── text injection via xdotool ─────────────────────────────────────────
def type_text(text: str) -> bool:
    """Type text into the currently focused window using xdotool."""
    if not text.strip():
        return False
    try:
        # xdotool type handles unicode and special chars
        subprocess.run(
            ["xdotool", "type", "--clearmodifiers", "--delay", "12", "--", text],
            check=True,
            timeout=30,
        )
        return True
    except FileNotFoundError:
        error("xdotool not found. Install it: sudo apt install xdotool")
        return False
    except subprocess.TimeoutExpired:
        error("xdotool timed out typing text")
        return False
    except subprocess.CalledProcessError as e:
        error(f"xdotool error: {e}")
        return False


# ─── clipboard fallback (for apps that don't work with xdotool type) ───
def type_text_clipboard(text: str) -> bool:
    """Paste text via clipboard as a fallback."""
    if not text.strip():
        return False
    try:
        # Save current clipboard
        old_clip = subprocess.run(
            ["xclip", "-selection", "clipboard", "-o"],
            capture_output=True, text=True, timeout=2,
        ).stdout

        # Set new clipboard content
        proc = subprocess.Popen(
            ["xclip", "-selection", "clipboard"],
            stdin=subprocess.PIPE,
        )
        proc.communicate(text.encode("utf-8"))

        # Paste with Ctrl+V
        subprocess.run(
            ["xdotool", "key", "--clearmodifiers", "ctrl+v"],
            check=True, timeout=5,
        )

        time.sleep(0.1)

        # Restore old clipboard
        proc = subprocess.Popen(
            ["xclip", "-selection", "clipboard"],
            stdin=subprocess.PIPE,
        )
        proc.communicate(old_clip.encode("utf-8"))

        return True
    except Exception as e:
        error(f"Clipboard fallback failed: {e}")
        return False


# ─── transcriber ─────────────────────────────────────────────────────────
class LinuxTranscriber(BaseTranscriber):
    """Transcribes audio using faster-whisper (CUDA-accelerated)."""

    def __init__(self, model_size: str = "medium", device: str = "cuda", compute_type: str = "float16"):
        from faster_whisper import WhisperModel  # local import

        status(f"Loading Whisper model '{model_size}' on {device} ({compute_type})…", C.CYAN)
        self.model = WhisperModel(
            model_size,
            device=device,
            compute_type=compute_type,
        )
        announce(f"Model '{model_size}' loaded and ready")

    def transcribe(self, audio: np.ndarray) -> str:
        """Transcribe audio numpy array to text. Auto-detects English/Spanish."""
        status("Transcribing…", C.YELLOW)
        t0 = time.time()

        segments, info = self.model.transcribe(
            audio,
            beam_size=5,
            language=None,  # auto-detect (en/es)
            vad_filter=True,
            vad_parameters=dict(
                threshold=0.3,  # lower = more sensitive (default 0.5)
                min_silence_duration_ms=300,
                speech_pad_ms=300,
                min_speech_duration_ms=100,
            ),
        )

        text_parts = []
        for segment in segments:
            text_parts.append(segment.text.strip())

        text = " ".join(text_parts).strip()
        elapsed = time.time() - t0

        lang = info.language if info.language else "??"
        prob = info.language_probability if info.language_probability else 0
        status(f"Language: {lang} ({prob:.0%})  ·  Took {elapsed:.1f}s", C.DIM)

        return text


# ─── audio recorder ─────────────────────────────────────────────────────
class LinuxAudioRecorder(BaseAudioRecorder):
    """Records audio via PipeWire (pw-record) or ALSA fallback (sounddevice)."""

    def __init__(self, device: Optional[int] = None):
        self._device = device
        self._recording = False
        self._pw_proc: Optional[subprocess.Popen] = None
        self._tmp_path = os.path.join(
            os.environ.get("XDG_RUNTIME_DIR", "/tmp"),
            "tak_recording.wav",
        )
        # Ensure XDG_RUNTIME_DIR is set for PipeWire access
        if "XDG_RUNTIME_DIR" not in os.environ:
            os.environ["XDG_RUNTIME_DIR"] = f"/run/user/{os.getuid()}"

        # Check if pw-record is available
        self._use_pw = self._check_pw_record()
        if self._use_pw:
            status("Audio: using PipeWire (pw-record) → default source", C.DIM)
        else:
            # Fallback: direct ALSA via sounddevice
            self._init_sounddevice(device)

    @staticmethod
    def _check_pw_record() -> bool:
        try:
            subprocess.run(
                ["pw-record", "--help"],
                capture_output=True, timeout=2,
            )
            return True
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False

    def _init_sounddevice(self, device: Optional[int]):
        """Fallback init for direct ALSA recording."""
        self._stream: Optional[sd.InputStream] = None
        self._chunks: list[np.ndarray] = []

        dev_idx = device if device is not None else sd.default.device[0]
        dev_info = sd.query_devices(dev_idx, "input")
        self._hw_rate = int(dev_info["default_samplerate"])

        for candidate in [48000, 44100]:
            try:
                sd.check_input_settings(device=dev_idx, samplerate=candidate,
                                        channels=CHANNELS, dtype=DTYPE)
                self._hw_rate = candidate
                break
            except Exception:
                continue

        status(f"Audio: ALSA device {dev_idx} @ {self._hw_rate} Hz (fallback)", C.YELLOW)

    def start(self):
        """Start recording audio."""
        self._recording = True

        if self._use_pw:
            # Remove old file
            try:
                os.unlink(self._tmp_path)
            except FileNotFoundError:
                pass

            cmd = [
                "pw-record",
                "--rate", "16000",       # record directly at Whisper's rate
                "--channels", "1",
                "--format", "s16",       # 16-bit signed int
                self._tmp_path,
            ]
            self._pw_proc = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        else:
            self._chunks = []
            if self._stream is None:
                self._stream = sd.InputStream(
                    samplerate=self._hw_rate,
                    channels=CHANNELS,
                    dtype=DTYPE,
                    blocksize=BLOCK_SIZE,
                    device=self._device,
                    callback=self._sd_callback,
                )
                self._stream.start()

        status("🎤 Recording…", C.RED)

    def _sd_callback(self, indata: np.ndarray, frames: int, time_info, status_flags):
        if status_flags:
            warn(f"Audio status: {status_flags}")
        if self._recording:
            self._chunks.append(indata.copy())

    def stop(self) -> Optional[np.ndarray]:
        """Stop recording and return audio as float32 numpy array at WHISPER_RATE."""
        self._recording = False

        if self._use_pw:
            return self._stop_pw()
        else:
            return self._stop_sd()

    def _stop_pw(self) -> Optional[np.ndarray]:
        """Stop pw-record and read the wav file."""
        if self._pw_proc is not None:
            self._pw_proc.terminate()
            try:
                self._pw_proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self._pw_proc.kill()
                self._pw_proc.wait()
            self._pw_proc = None

        if not os.path.isfile(self._tmp_path):
            return None

        try:
            with wave.open(self._tmp_path, "r") as wf:
                n_frames = wf.getnframes()
                if n_frames == 0:
                    return None
                raw = wf.readframes(n_frames)
                rate = wf.getframerate()
                n_channels = wf.getnchannels()

            audio = np.frombuffer(raw, dtype=np.int16)
            # If stereo, take first channel
            if n_channels > 1:
                audio = audio[::n_channels]

            audio_f32 = audio.astype(np.float32) / 32768.0

            # Resample if pw-record didn't honor --rate
            if rate != WHISPER_RATE:
                audio_f32 = _resample(audio_f32, rate, WHISPER_RATE)

        except Exception as e:
            error(f"Failed to read recording: {e}")
            return None
        finally:
            try:
                os.unlink(self._tmp_path)
            except FileNotFoundError:
                pass

        audio_f32 = self.normalize(audio_f32)
        duration = len(audio_f32) / WHISPER_RATE
        status(f"Recorded {duration:.1f}s of audio", C.DIM)
        return audio_f32

    def _stop_sd(self) -> Optional[np.ndarray]:
        """Stop sounddevice stream and return audio."""
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None

        if not self._chunks:
            return None

        audio = np.concatenate(self._chunks, axis=0).flatten()
        audio_f32 = audio.astype(np.float32) / 32768.0
        audio_f32 = _resample(audio_f32, self._hw_rate, WHISPER_RATE)
        audio_f32 = self.normalize(audio_f32)
        duration = len(audio_f32) / WHISPER_RATE
        status(f"Recorded {duration:.1f}s of audio", C.DIM)
        return audio_f32


# ─── platform interface ──────────────────────────────────────────────────
def platform_setup():
    """Run Linux-specific initialization."""
    ensure_cuda_libs()

def get_default_model():
    """Default Whisper model for Linux."""
    return "medium"

def get_platform_label():
    """Platform label for the banner."""
    return "Linux / X11"
