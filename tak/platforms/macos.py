"""TAK macOS backends — mlx-whisper, Core Audio, AppleScript."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import time
import wave
from typing import Optional

import numpy as np
import sounddevice as sd

from tak.app import (
    BaseAudioRecorder, BaseTranscriber,
    WHISPER_RATE, CHANNELS, DTYPE, BLOCK_SIZE, KEY_MAP,
    status, announce, warn, error, _resample, C,
)


# ─── MLX Hub model mapping ──────────────────────────────────────────────
MLX_MODELS = {
    "tiny":     "mlx-community/whisper-tiny-mlx",
    "base":     "mlx-community/whisper-base-mlx",
    "small":    "mlx-community/whisper-small-mlx",
    "medium":   "mlx-community/whisper-medium-mlx-fp32",
    "large-v3": "mlx-community/whisper-large-v3-mlx",
    "turbo":    "mlx-community/whisper-large-v3-turbo",
}


# ─── accessibility permission check ─────────────────────────────────────
def check_accessibility_permission() -> bool:
    """Verify that Accessibility permission is granted for pynput."""
    try:
        result = subprocess.run(
            ["osascript", "-e",
             'tell application "System Events" to get name of first process'],
            capture_output=True, timeout=5,
        )
        if result.returncode != 0:
            error("Accessibility permission not granted.")
            error("Go to: System Settings → Privacy & Security → Accessibility")
            error("Add your terminal app (Terminal.app / iTerm2) to the list.")
            return False
        return True
    except Exception:
        warn("Could not verify Accessibility permission — proceeding anyway")
        return True


# ─── key map adjustments ────────────────────────────────────────────────
def adjust_key_map():
    """Remove keys that don't exist on Mac keyboards."""
    for k in ["scroll_lock", "pause", "insert"]:
        KEY_MAP.pop(k, None)


# ─── WAV writer helper ──────────────────────────────────────────────────
def _write_wav(path: str, audio: np.ndarray, rate: int):
    """Write float32 audio to a 16-bit WAV using only the standard library."""
    int16_audio = (audio * 32767).clip(-32768, 32767).astype(np.int16)
    with wave.open(path, "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        wf.writeframes(int16_audio.tobytes())


# ─── text injection via AppleScript ──────────────────────────────────────
def type_text(text: str) -> bool:
    """Type text into the currently focused window using AppleScript."""
    if not text.strip():
        return False
    try:
        escaped = text.replace("\\", "\\\\").replace('"', '\\"')
        script = (
            'tell application "System Events"\n'
            f'    keystroke "{escaped}"\n'
            'end tell'
        )
        subprocess.run(
            ["osascript", "-e", script],
            check=True, timeout=30, capture_output=True,
        )
        return True
    except FileNotFoundError:
        error("osascript not found (should never happen on macOS)")
        return False
    except subprocess.TimeoutExpired:
        error("AppleScript timed out typing text")
        return False
    except subprocess.CalledProcessError as e:
        error(f"AppleScript error: {e}")
        return False


# ─── clipboard paste via pbcopy + Cmd+V ─────────────────────────────────
def type_text_clipboard(text: str) -> bool:
    """Paste text via clipboard as a fallback."""
    if not text.strip():
        return False
    try:
        # Save current clipboard
        old_clip = subprocess.run(
            ["pbpaste"],
            capture_output=True, text=True, timeout=2,
        ).stdout

        # Set new clipboard content
        proc = subprocess.Popen(["pbcopy"], stdin=subprocess.PIPE)
        proc.communicate(text.encode("utf-8"))

        # Paste with Cmd+V
        subprocess.run(
            ["osascript", "-e",
             'tell application "System Events" to keystroke "v" using command down'],
            check=True, timeout=5, capture_output=True,
        )

        time.sleep(0.1)

        # Restore original clipboard
        proc = subprocess.Popen(["pbcopy"], stdin=subprocess.PIPE)
        proc.communicate(old_clip.encode("utf-8"))

        return True
    except Exception as e:
        error(f"Clipboard paste failed: {e}")
        return False


# ─── transcriber ─────────────────────────────────────────────────────────
class MacTranscriber(BaseTranscriber):
    """Transcribes audio using mlx-whisper (Metal-accelerated on Apple Silicon)."""

    def __init__(self, model_size: str = "turbo"):
        import mlx_whisper  # local import — not available on Linux
        self._mlx_whisper = mlx_whisper

        # Resolve model path
        if "/" in model_size:
            self._model_path = model_size
        else:
            self._model_path = MLX_MODELS.get(model_size)
            if self._model_path is None:
                available = ", ".join(MLX_MODELS.keys())
                error(f"Unknown model '{model_size}'. Available: {available}")
                error("Or pass a full HuggingFace repo path (e.g., mlx-community/whisper-tiny-mlx)")
                sys.exit(1)

        status(f"Loading Whisper model '{model_size}' ({self._model_path})…", C.CYAN)

        # Warm up: transcribe a silent clip to trigger model download + compilation
        warmup_audio = np.zeros(WHISPER_RATE, dtype=np.float32)  # 1 second of silence
        warmup_path = os.path.join(tempfile.gettempdir(), "tak_warmup.wav")
        _write_wav(warmup_path, warmup_audio, WHISPER_RATE)
        try:
            self._mlx_whisper.transcribe(
                warmup_path,
                path_or_hf_repo=self._model_path,
                language="en",
            )
        finally:
            try:
                os.unlink(warmup_path)
            except FileNotFoundError:
                pass

        announce(f"Model '{model_size}' loaded and ready")

    def transcribe(self, audio: np.ndarray) -> str:
        """Transcribe audio numpy array to text. Auto-detects English/Spanish."""
        status("Transcribing…", C.YELLOW)
        t0 = time.time()

        # Write temp WAV — mlx-whisper needs a file path
        tmp_path = os.path.join(tempfile.gettempdir(), "tak_audio.wav")
        _write_wav(tmp_path, audio, WHISPER_RATE)

        try:
            result = self._mlx_whisper.transcribe(
                tmp_path,
                path_or_hf_repo=self._model_path,
                language=None,  # auto-detect (en/es)
            )
        finally:
            try:
                os.unlink(tmp_path)
            except FileNotFoundError:
                pass

        text = result.get("text", "").strip()
        elapsed = time.time() - t0

        lang = result.get("language", "??")
        status(f"Language: {lang}  ·  Took {elapsed:.1f}s", C.DIM)

        return text


# ─── audio recorder ─────────────────────────────────────────────────────
class MacAudioRecorder(BaseAudioRecorder):
    """Records audio via Core Audio (through PortAudio/sounddevice)."""

    def __init__(self, device: Optional[int] = None):
        self._device = device
        self._recording = False
        self._stream: Optional[sd.InputStream] = None
        self._chunks: list[np.ndarray] = []

        dev_idx = device if device is not None else sd.default.device[0]
        dev_info = sd.query_devices(dev_idx, "input")
        self._hw_rate = int(dev_info["default_samplerate"])

        for candidate in [48000, 44100]:
            try:
                sd.check_input_settings(
                    device=dev_idx, samplerate=candidate,
                    channels=CHANNELS, dtype=DTYPE,
                )
                self._hw_rate = candidate
                break
            except Exception:
                continue

        status(f"Audio: Core Audio device {dev_idx} @ {self._hw_rate} Hz", C.DIM)

    def start(self):
        """Start recording audio."""
        self._recording = True
        self._chunks = []

        self._stream = sd.InputStream(
            samplerate=self._hw_rate,
            channels=CHANNELS,
            dtype=DTYPE,
            blocksize=BLOCK_SIZE,
            device=self._device,
            callback=self._callback,
        )
        self._stream.start()
        status("🎤 Recording…", C.RED)

    def _callback(self, indata: np.ndarray, frames: int, time_info, status_flags):
        if status_flags:
            warn(f"Audio status: {status_flags}")
        if self._recording:
            self._chunks.append(indata.copy())

    def stop(self) -> Optional[np.ndarray]:
        """Stop recording and return audio as float32 numpy array at WHISPER_RATE."""
        self._recording = False

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
    """Run macOS-specific initialization."""
    adjust_key_map()
    if not check_accessibility_permission():
        sys.exit(1)


def get_default_model():
    """Default Whisper model for macOS."""
    return "turbo"


def get_platform_label():
    """Platform label for the banner."""
    return "macOS / Metal"
