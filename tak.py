#!/usr/bin/env python3
"""
TAK — Talk to Keyboard
Push-to-talk speech-to-text that types anywhere.

Hold a key to record, release to transcribe and type the result
into whatever window/field has focus. Works system-wide on X11.

Usage:
    python tak.py                  # default: hold Right-Ctrl to talk
    python tak.py --key scroll_lock
    python tak.py --key pause
    python tak.py --model large-v3  # use a bigger Whisper model
"""

from __future__ import annotations

import argparse
import os
import site
import subprocess
import sys
import threading
import time
import wave
from pathlib import Path
from typing import Optional


def _ensure_cuda_libs():
    """Pre-load pip-installed NVIDIA libs so ctranslate2 can find them at runtime.

    Setting LD_LIBRARY_PATH from within the process is too late — the dynamic
    linker has already cached the search paths.  Instead we use ctypes.CDLL
    with RTLD_GLOBAL so that when ctranslate2 later asks for libcublas.so.12
    it is already in the process address space.
    """
    import ctypes
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

_ensure_cuda_libs()


import numpy as np
import sounddevice as sd
from faster_whisper import WhisperModel
from pynput import keyboard

# ─── constants ──────────────────────────────────────────────────────────
WHISPER_RATE = 16000  # Whisper expects 16 kHz
CHANNELS = 1
DTYPE = "int16"
BLOCK_SIZE = 1024  # frames per audio callback

# ─── color helpers ──────────────────────────────────────────────────────
class C:
    RESET  = "\033[0m"
    BOLD   = "\033[1m"
    DIM    = "\033[2m"
    RED    = "\033[91m"
    GREEN  = "\033[92m"
    YELLOW = "\033[93m"
    CYAN   = "\033[96m"
    BLUE   = "\033[94m"
    MAG    = "\033[95m"

def banner():
    print(f"""
{C.CYAN}{C.BOLD}╔══════════════════════════════════════════╗
║            TAK · Talk to Keyboard        ║
╚══════════════════════════════════════════╝{C.RESET}
""")

def status(msg: str, color: str = C.DIM):
    print(f"  {color}▸ {msg}{C.RESET}")

def announce(msg: str):
    print(f"\n  {C.GREEN}{C.BOLD}✔ {msg}{C.RESET}")

def warn(msg: str):
    print(f"  {C.YELLOW}⚠ {msg}{C.RESET}")

def error(msg: str):
    print(f"  {C.RED}✖ {msg}{C.RESET}")


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


# ─── resampling ──────────────────────────────────────────────────────────
def _resample(audio: np.ndarray, orig_sr: int, target_sr: int) -> np.ndarray:
    """Resample audio from orig_sr to target_sr using linear interpolation.

    Good enough for speech — avoids pulling in scipy/librosa.
    """
    if orig_sr == target_sr:
        return audio
    duration = len(audio) / orig_sr
    target_len = int(duration * target_sr)
    indices = np.linspace(0, len(audio) - 1, target_len)
    return np.interp(indices, np.arange(len(audio)), audio).astype(np.float32)


# ─── audio recorder ─────────────────────────────────────────────────────
class AudioRecorder:
    """Records audio via PipeWire (pw-record) for proper device routing.

    Conda's PortAudio only sees raw ALSA devices, missing PipeWire's
    virtual routing.  Using pw-record directly captures from whatever
    PipeWire source is configured as default (headset, USB mic, etc.).
    Falls back to sounddevice if pw-record is unavailable.
    """

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
            r = subprocess.run(
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
            import wave
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

        audio_f32 = self._normalize(audio_f32)
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
        audio_f32 = self._normalize(audio_f32)
        duration = len(audio_f32) / WHISPER_RATE
        status(f"Recorded {duration:.1f}s of audio", C.DIM)
        return audio_f32

    @staticmethod
    def _normalize(audio: np.ndarray) -> np.ndarray:
        """Auto-normalize quiet audio so Whisper can hear it."""
        peak = np.max(np.abs(audio))
        if peak > 1e-6:
            gain = min(0.9 / peak, 200.0)
            if gain > 1.5:
                status(f"Mic level low (peak {peak:.4f}), boosting {gain:.0f}×", C.YELLOW)
            audio = audio * gain
        return audio


# ─── transcriber ─────────────────────────────────────────────────────────
class Transcriber:
    """Transcribes audio using faster-whisper (local, GPU-accelerated)."""

    def __init__(self, model_size: str = "medium", device: str = "cuda", compute_type: str = "float16"):
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


# ─── key name mapping ───────────────────────────────────────────────────
KEY_MAP = {
    "ctrl_r":      keyboard.Key.ctrl_r,
    "ctrl_l":      keyboard.Key.ctrl_l,
    "alt_r":       keyboard.Key.alt_r,
    "alt_l":       keyboard.Key.alt_l,
    "shift_r":     keyboard.Key.shift_r,
    "shift_l":     keyboard.Key.shift_l,
    "scroll_lock": keyboard.Key.scroll_lock,
    "pause":       keyboard.Key.pause,
    "insert":      keyboard.Key.insert,
    "f1":          keyboard.Key.f1,
    "f2":          keyboard.Key.f2,
    "f3":          keyboard.Key.f3,
    "f4":          keyboard.Key.f4,
    "f5":          keyboard.Key.f5,
    "f6":          keyboard.Key.f6,
    "f7":          keyboard.Key.f7,
    "f8":          keyboard.Key.f8,
    "f9":          keyboard.Key.f9,
    "f10":         keyboard.Key.f10,
    "f11":         keyboard.Key.f11,
    "f12":         keyboard.Key.f12,
    "caps_lock":   keyboard.Key.caps_lock,
}


# ─── main application ──────────────────────────────────────────────────
class TakApp:
    """Main push-to-talk application."""

    def __init__(self, args: argparse.Namespace):
        self.trigger_key = KEY_MAP.get(args.key)
        if self.trigger_key is None:
            error(f"Unknown key '{args.key}'. Available: {', '.join(KEY_MAP.keys())}")
            sys.exit(1)

        self.use_clipboard = args.clipboard
        self.recorder = AudioRecorder(device=args.device)
        self.transcriber = Transcriber(
            model_size=args.model,
            device="cuda" if not args.cpu else "cpu",
            compute_type="float16" if not args.cpu else "int8",
        )
        self._pressed = False
        self._lock = threading.Lock()
        self._processing = False

    def _on_press(self, key):
        """Handle key press — start recording."""
        if key == self.trigger_key and not self._pressed:
            with self._lock:
                if self._processing:
                    return  # still transcribing previous clip
                self._pressed = True
            self.recorder.start()

    def _on_release(self, key):
        """Handle key release — stop recording, transcribe, type."""
        if key == self.trigger_key and self._pressed:
            self._pressed = False
            audio = self.recorder.stop()

            if audio is None or len(audio) < WHISPER_RATE * 0.3:
                warn("Too short — skipped (hold key longer)")
                return

            # Run transcription in a thread to avoid blocking the key listener
            threading.Thread(target=self._process, args=(audio,), daemon=True).start()

    def _process(self, audio: np.ndarray):
        """Transcribe and type the result."""
        with self._lock:
            self._processing = True

        try:
            text = self.transcriber.transcribe(audio)

            if not text:
                warn("No speech detected")
                return

            announce(f"「{text}」")

            if self.use_clipboard:
                ok = type_text_clipboard(text)
            else:
                ok = type_text(text)

            if ok:
                status("Typed into focused window ✓", C.GREEN)
            else:
                warn("Could not type text — make sure a text field is focused")
        except Exception as e:
            error(f"Transcription error: {e}")
        finally:
            with self._lock:
                self._processing = False

    def run(self):
        """Start the application."""
        banner()
        print(f"  {C.BOLD}Push-to-talk key:{C.RESET}  {C.CYAN}{self.trigger_key.name}{C.RESET}")
        print(f"  {C.BOLD}Input method:{C.RESET}      {'clipboard (Ctrl+V)' if self.use_clipboard else 'xdotool type'}")
        print(f"  {C.BOLD}Languages:{C.RESET}         English · Español (auto-detect)")
        print()
        print(f"  {C.DIM}Hold the key to speak, release to transcribe & type.{C.RESET}")
        print(f"  {C.DIM}Press Ctrl+C to quit.{C.RESET}")
        print()

        with keyboard.Listener(
            on_press=self._on_press,
            on_release=self._on_release,
        ) as listener:
            try:
                listener.join()
            except KeyboardInterrupt:
                print(f"\n  {C.DIM}Bye! 👋{C.RESET}\n")


# ─── CLI ────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        prog="tak",
        description="TAK — Talk to Keyboard. Push-to-talk speech-to-text that types anywhere.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python tak.py                          # Hold Right-Ctrl to talk
  python tak.py --key scroll_lock        # Use Scroll Lock instead
  python tak.py --model large-v3         # More accurate (slower)
  python tak.py --model small            # Faster, less accurate
  python tak.py --clipboard              # Use clipboard paste instead of xdotool type
  python tak.py --cpu                    # Run on CPU (no GPU needed)

Available keys:
  ctrl_r, ctrl_l, alt_r, alt_l, shift_r, shift_l,
  scroll_lock, pause, insert, f1-f12, caps_lock
        """,
    )
    parser.add_argument(
        "--key", "-k",
        default="ctrl_r",
        help="Key to hold for push-to-talk (default: ctrl_r)",
    )
    parser.add_argument(
        "--model", "-m",
        default="medium",
        help="Whisper model size: tiny, base, small, medium, large-v3 (default: medium)",
    )
    parser.add_argument(
        "--clipboard", "-c",
        action="store_true",
        help="Use clipboard paste (Ctrl+V) instead of xdotool type",
    )
    parser.add_argument(
        "--cpu",
        action="store_true",
        help="Force CPU inference (default: uses CUDA if available)",
    )
    parser.add_argument(
        "--device", "-d",
        type=int,
        default=None,
        help="Audio input device index (see: python -m sounddevice)",
    )
    args = parser.parse_args()
    app = TakApp(args)
    app.run()


if __name__ == "__main__":
    main()
