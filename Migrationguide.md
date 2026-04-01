# TAK Cross-Platform Migration Guide

## Complete Implementation Plan for Claude Code

**Repository:** `github.com/lchonkan/tak`
**Current state:** Single-file Linux app (`tak.py`, ~400 lines)
**Target state:** Multi-file cross-platform app (Linux + macOS)

---

## Execution Order

This guide is organized into two phases, executed sequentially. Each phase ends with a testing gate. Do not start Phase 2 until Phase 1 passes all tests.

| Phase | Goal | Deliverables | Test on |
|-------|------|-------------|---------|
| **1** | Refactor Linux into modular architecture | `tak_core.py`, `tak_linux.py`, new `tak.py`, updated `run.sh` | Linux |
| **2** | Add macOS support | `tak_macos.py`, `requirements-macos.txt`, README update | macOS |

**Commit after Phase 1** to create a clean rollback point before adding macOS.

---

## Target File Structure

```
tak/
├── tak.py                  # Entry point — detects platform, wires backends, runs app
├── tak_core.py             # Shared: TakApp, CLI parser, colors, constants, resampling
├── tak_linux.py            # Linux: LinuxTranscriber, LinuxAudioRecorder, xdotool/xclip
├── tak_macos.py            # macOS: MacTranscriber, MacAudioRecorder, osascript/pbcopy
├── run.sh                  # Cross-platform launcher
├── requirements-linux.txt  # Linux Python dependencies
├── requirements-macos.txt  # macOS Python dependencies
├── README.md               # Updated with macOS instructions
├── LICENSE
└── docs/
    └── architecture.md
```

### Design Principles

- **No `if IS_MACOS` inside core.** Platform branching happens only in `tak.py` (entry point).
- **Constructor injection.** `TakApp` receives backends as arguments — it never imports a platform module.
- **Each platform file is self-contained.** Deleting `tak_linux.py` on a Mac or `tak_macos.py` on Linux causes no errors.
- **Shared utilities in core.** Resampling, normalization, colors, constants, CLI parsing — all platform-agnostic.

### Dependency Flow

```
tak.py  (entry point)
  ├── imports tak_core     (always)
  ├── imports tak_linux    (if Linux)
  └── imports tak_macos    (if macOS)

tak_core.py  (zero platform-specific imports)
  ├── TakApp               (receives backends via constructor)
  ├── BaseAudioRecorder    (ABC)
  ├── BaseTranscriber      (ABC)
  ├── parse_args()
  ├── Color helpers
  ├── Constants
  ├── _resample()
  └── KEY_MAP

tak_linux.py               tak_macos.py
  ├── ensure_cuda_libs()     ├── check_accessibility_permission()
  ├── LinuxTranscriber       ├── MacTranscriber
  ├── LinuxAudioRecorder     ├── MacAudioRecorder
  ├── type_text (xdotool)    ├── type_text (osascript)
  ├── type_text_clipboard    ├── type_text_clipboard
  ├── platform_setup()       ├── platform_setup()
  ├── get_default_model()    ├── get_default_model()
  └── get_platform_label()   └── get_platform_label()
```

---

# PHASE 1 — Linux Refactoring

**Goal:** Split the current monolithic `tak.py` into `tak_core.py` + `tak_linux.py` + new `tak.py` entry point, with zero behavior changes on Linux.

---

## Phase 1, Step 1: Create `tak_core.py`

Create this file from scratch. It will contain everything that is platform-independent, extracted from the current `tak.py`.

### 1.1 Imports

```python
from __future__ import annotations

import argparse
import threading
import time
from abc import ABC, abstractmethod
from typing import Optional, Callable

import numpy as np
from pynput import keyboard
```

### 1.2 Constants

Copy from current `tak.py`:

```python
WHISPER_RATE = 16000
CHANNELS = 1
DTYPE = "int16"
BLOCK_SIZE = 1024
```

### 1.3 Color helpers

Copy the entire `C` class and all five helper functions from current `tak.py`: `status()`, `announce()`, `warn()`, `error()`.

**Modify `banner()`** to accept a platform label:

```python
def banner(platform_label: str = ""):
    print(f"""
{C.CYAN}{C.BOLD}╔══════════════════════════════════════════╗
║            TAK · Talk to Keyboard        ║
║  {platform_label:^40s}║
╚══════════════════════════════════════════╝{C.RESET}
""")
```

### 1.4 Resampling

Copy `_resample()` from current `tak.py` unchanged.

### 1.5 Key map

Copy `KEY_MAP` dictionary from current `tak.py` unchanged. Platform files may modify it at runtime (macOS removes keys that don't exist on Mac keyboards).

### 1.6 Base classes (new)

These don't exist in the current code. Create them:

```python
class BaseAudioRecorder(ABC):
    """Interface for platform-specific audio recorders."""

    @abstractmethod
    def start(self) -> None:
        ...

    @abstractmethod
    def stop(self) -> Optional[np.ndarray]:
        ...

    @staticmethod
    def normalize(audio: np.ndarray) -> np.ndarray:
        """Auto-normalize quiet audio so Whisper can hear it."""
        peak = np.max(np.abs(audio))
        if peak > 1e-6:
            gain = min(0.9 / peak, 200.0)
            if gain > 1.5:
                status(f"Mic level low (peak {peak:.4f}), boosting {gain:.0f}×", C.YELLOW)
            audio = audio * gain
        return audio


class BaseTranscriber(ABC):
    """Interface for platform-specific transcribers."""

    @abstractmethod
    def transcribe(self, audio: np.ndarray) -> str:
        ...
```

The `normalize()` static method is extracted from the current `AudioRecorder._normalize()`. It moves to the base class because both Linux and macOS recorders need it.

### 1.7 TakApp class (modified)

Copy `TakApp` from current `tak.py`, then make these changes:

**Replace the constructor.** The current constructor creates backends internally:

```python
# CURRENT — creates backends itself
def __init__(self, args: argparse.Namespace):
    self.trigger_key = KEY_MAP.get(args.key)
    self.use_clipboard = args.clipboard
    self.recorder = AudioRecorder(device=args.device)
    self.transcriber = Transcriber(model_size=args.model, ...)
```

New constructor receives pre-built backends:

```python
# NEW — receives backends via dependency injection
def __init__(
    self,
    trigger_key,
    recorder: BaseAudioRecorder,
    transcriber: BaseTranscriber,
    type_fn: Callable[[str], bool],
    clipboard_fn: Callable[[str], bool],
    use_clipboard: bool = False,
    platform_label: str = "",
):
    self.trigger_key = trigger_key
    self.recorder = recorder
    self.transcriber = transcriber
    self._type_fn = type_fn
    self._clipboard_fn = clipboard_fn
    self.use_clipboard = use_clipboard
    self._platform_label = platform_label
    self._pressed = False
    self._lock = threading.Lock()
    self._processing = False
```

**Update `_process()`** — replace direct function calls with injected callables:

```python
# CURRENT
if self.use_clipboard:
    ok = type_text_clipboard(text)
else:
    ok = type_text(text)

# NEW
if self.use_clipboard:
    ok = self._clipboard_fn(text)
else:
    ok = self._type_fn(text)
```

**Update `run()`** — use platform label in banner, remove hardcoded platform references:

```python
# CURRENT
banner()
print(f"  {C.BOLD}Input method:{C.RESET}      {'clipboard (Ctrl+V)' if self.use_clipboard else 'xdotool type'}")

# NEW
banner(self._platform_label)
print(f"  {C.BOLD}Input method:{C.RESET}      {'clipboard paste' if self.use_clipboard else 'simulated keystrokes'}")
```

The `_on_press()`, `_on_release()` methods and the rest of `run()` (keyboard listener, Ctrl+C) stay unchanged.

### 1.8 CLI parser (extracted from current `main()`)

```python
def parse_args():
    parser = argparse.ArgumentParser(
        prog="tak",
        description="TAK — Talk to Keyboard. Push-to-talk speech-to-text.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python tak.py                          # Hold Right-Ctrl to talk
  python tak.py --key scroll_lock        # Use Scroll Lock instead
  python tak.py --key caps_lock          # Use Caps Lock (good for MacBooks)
  python tak.py --model large-v3         # More accurate (slower)
  python tak.py --model turbo            # Fast + accurate (macOS default)
  python tak.py --clipboard              # Use clipboard paste
  python tak.py --cpu                    # Run on CPU (no GPU needed)

Available keys:
  ctrl_r (default), ctrl_l, alt_r, alt_l, shift_r, shift_l,
  scroll_lock, pause, insert, f1-f12, caps_lock
        """,
    )
    parser.add_argument("--key", "-k", default="ctrl_r",
                        help="Key to hold for push-to-talk (default: ctrl_r)")
    parser.add_argument("--model", "-m", default=None,
                        help="Whisper model size (default: turbo on macOS, medium on Linux)")
    parser.add_argument("--clipboard", "-c", action="store_true",
                        help="Use clipboard paste instead of simulated typing")
    parser.add_argument("--cpu", action="store_true",
                        help="Force CPU inference (default: uses CUDA if available)")
    parser.add_argument("--device", "-d", type=int, default=None,
                        help="Audio input device index (see: python -m sounddevice)")
    return parser.parse_args()
```

---

## Phase 1, Step 2: Create `tak_linux.py`

Create this file by moving all Linux-specific code from the current `tak.py`.

### 2.1 Imports

```python
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

from tak_core import (
    BaseAudioRecorder, BaseTranscriber,
    WHISPER_RATE, CHANNELS, DTYPE, BLOCK_SIZE,
    status, announce, warn, error, _resample, C,
)
```

**Important:** Do NOT import `faster_whisper` at module level. Use a local import inside `LinuxTranscriber.__init__()`. This keeps the module importable on systems where faster-whisper is not installed.

### 2.2 CUDA initialization

Move the body of `_ensure_cuda_libs()` here and rename it. **Do NOT auto-call it** — in the current `tak.py` this function runs as a side effect of importing the module. In the new structure, it only runs when `platform_setup()` is explicitly called.

```python
def ensure_cuda_libs():
    """Pre-load pip-installed NVIDIA libs so ctranslate2 can find them at runtime."""
    # ... existing _ensure_cuda_libs() body unchanged ...
```

### 2.3 `LinuxTranscriber`

Rename from current `Transcriber`. Inherit from `BaseTranscriber`. Move `faster_whisper` import to local:

```python
class LinuxTranscriber(BaseTranscriber):
    """Transcribes audio using faster-whisper (CUDA-accelerated)."""

    def __init__(self, model_size: str = "medium", device: str = "cuda", compute_type: str = "float16"):
        from faster_whisper import WhisperModel  # local import
        status(f"Loading Whisper model '{model_size}' on {device} ({compute_type})…", C.CYAN)
        self.model = WhisperModel(model_size, device=device, compute_type=compute_type)
        announce(f"Model '{model_size}' loaded and ready")

    def transcribe(self, audio: np.ndarray) -> str:
        # ... existing transcribe() body unchanged ...
```

### 2.4 `LinuxAudioRecorder`

Rename from current `AudioRecorder`. Inherit from `BaseAudioRecorder`.

**One change:** replace `self._normalize()` with `self.normalize()` in both `_stop_pw()` and `_stop_sd()`, since the method now lives on the base class.

```python
class LinuxAudioRecorder(BaseAudioRecorder):
    """Records audio via PipeWire (pw-record) or ALSA fallback (sounddevice)."""

    def __init__(self, device: Optional[int] = None):
        # ... existing __init__ body unchanged ...

    def start(self):
        # ... existing body unchanged ...

    def stop(self) -> Optional[np.ndarray]:
        # ... existing body unchanged ...

    # All private methods move unchanged:
    # _check_pw_record, _init_sounddevice, _sd_callback, _stop_pw, _stop_sd

    # REMOVE the _normalize static method — it now lives in BaseAudioRecorder.normalize()
```

In `_stop_pw()` and `_stop_sd()`, update the call:

```python
# CURRENT
audio_f32 = self._normalize(audio_f32)

# NEW
audio_f32 = self.normalize(audio_f32)
```

### 2.5 Text injection functions

Move `type_text()` and `type_text_clipboard()` from current `tak.py` — no changes to function bodies.

### 2.6 Platform interface functions (new)

Add these at the bottom of the file:

```python
def platform_setup():
    """Run Linux-specific initialization."""
    ensure_cuda_libs()

def get_default_model():
    """Default Whisper model for Linux."""
    return "medium"

def get_platform_label():
    """Platform label for the banner."""
    return "Linux / X11"
```

---

## Phase 1, Step 3: Rewrite `tak.py` as Entry Point

Replace the entire current `tak.py` with:

```python
#!/usr/bin/env python3
"""
TAK — Talk to Keyboard
Push-to-talk speech-to-text that types anywhere.

Cross-platform: Linux (X11) and macOS.

Usage:
    python tak.py                  # default: hold Right-Ctrl to talk
    python tak.py --key scroll_lock
    python tak.py --model large-v3
"""

from __future__ import annotations

import platform
import sys


def main():
    from tak_core import parse_args, KEY_MAP, error, warn

    args = parse_args()

    IS_MACOS = platform.system() == "Darwin"
    IS_LINUX = platform.system() == "Linux"

    # ── Import platform backend ──────────────────────────────────
    if IS_MACOS:
        import tak_macos as backend
    elif IS_LINUX:
        import tak_linux as backend
    else:
        error(f"Unsupported platform: {platform.system()}")
        sys.exit(1)

    # ── Platform-specific initialization ─────────────────────────
    backend.platform_setup()

    # ── Resolve trigger key ──────────────────────────────────────
    trigger_key = KEY_MAP.get(args.key)
    if trigger_key is None:
        error(f"Unknown key '{args.key}'. Available: {', '.join(KEY_MAP.keys())}")
        sys.exit(1)

    # ── Resolve model ────────────────────────────────────────────
    model_size = args.model if args.model else backend.get_default_model()

    # ── Build backends ───────────────────────────────────────────
    if IS_MACOS:
        if args.cpu:
            warn("--cpu flag ignored on macOS (MLX auto-selects best device)")
        recorder = backend.MacAudioRecorder(device=args.device)
        transcriber = backend.MacTranscriber(model_size)
    else:
        recorder = backend.LinuxAudioRecorder(device=args.device)
        device = "cpu" if args.cpu else "cuda"
        compute_type = "int8" if args.cpu else "float16"
        transcriber = backend.LinuxTranscriber(model_size, device=device, compute_type=compute_type)

    # ── Build and run app ────────────────────────────────────────
    from tak_core import TakApp

    app = TakApp(
        trigger_key=trigger_key,
        recorder=recorder,
        transcriber=transcriber,
        type_fn=backend.type_text,
        clipboard_fn=backend.type_text_clipboard,
        use_clipboard=args.clipboard,
        platform_label=backend.get_platform_label(),
    )
    app.run()


if __name__ == "__main__":
    main()
```

---

## Phase 1, Step 4: Update `run.sh`

Replace the current Linux-only `run.sh` with a cross-platform version:

```bash
#!/usr/bin/env bash
# TAK launcher — cross-platform (Linux + macOS)
# Usage: ./run.sh [args...]

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

eval "$(conda shell.bash hook)"
conda activate tak

# Set CUDA library paths only on Linux
if [[ "$(uname)" == "Linux" ]]; then
    SITE_PKGS="$(python3 -c 'import site; print(site.getsitepackages()[0])')"
    CUBLAS_LIB="$SITE_PKGS/nvidia/cublas/lib"
    CUDNN_LIB="$SITE_PKGS/nvidia/cudnn/lib"
    for d in "$CUBLAS_LIB" "$CUDNN_LIB"; do
        if [ -d "$d" ]; then
            export LD_LIBRARY_PATH="${d}:${LD_LIBRARY_PATH:-}"
        fi
    done
fi

exec python3 "$SCRIPT_DIR/tak.py" "$@"
```

---

## Phase 1, Step 5: Create `requirements-linux.txt`

```
faster-whisper>=1.0.0
pynput>=1.7.6
sounddevice>=0.4.6
numpy>=1.24.0
nvidia-cublas-cu12
nvidia-cudnn-cu12
```

---

## Phase 1, Step 6: Test on Linux

Run every combination:

```bash
./run.sh                      # default config
./run.sh --key ctrl_r         # explicit key
./run.sh --model small        # different model
./run.sh --clipboard          # clipboard mode
./run.sh --cpu                # CPU mode
```

### Phase 1 verification checklist

- [ ] Banner shows "Linux / X11"
- [ ] CUDA libs load correctly (GPU model loading message appears)
- [ ] PipeWire recording works (or sounddevice fallback)
- [ ] English transcription works
- [ ] Spanish transcription works
- [ ] `xdotool` text injection works
- [ ] `--clipboard` mode works (xclip)
- [ ] `--cpu` flag switches to CPU inference
- [ ] `--device` flag selects audio input device
- [ ] Short recording (<0.3s) shows "Too short" warning
- [ ] New recording blocked while transcription is in progress
- [ ] Ctrl+C exits cleanly
- [ ] All error messages match pre-refactoring behavior

### ⛔ GATE: Do not proceed to Phase 2 until all boxes are checked.

### Commit

```bash
git add tak.py tak_core.py tak_linux.py run.sh requirements-linux.txt
git commit -m "refactor: split monolithic tak.py into modular architecture

- tak_core.py: shared platform-agnostic code (TakApp, CLI, colors, base classes)
- tak_linux.py: Linux backends (faster-whisper, PipeWire/ALSA, xdotool/xclip)
- tak.py: thin entry point with platform detection
- run.sh: updated for cross-platform support
- No behavior changes on Linux"
```

---

# PHASE 2 — macOS Implementation

**Goal:** Add macOS support by creating `tak_macos.py` with Metal-accelerated backends. No changes to `tak_core.py` or `tak_linux.py`.

---

## Phase 2, Step 7: Create `tak_macos.py`

### 7.1 Full implementation

```python
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

from tak_core import (
    BaseAudioRecorder, BaseTranscriber,
    WHISPER_RATE, CHANNELS, DTYPE, BLOCK_SIZE, KEY_MAP,
    status, announce, warn, error, _resample, C,
)


# ── Accessibility check ──────────────────────────────────────────────

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


# ── Key map adjustments ──────────────────────────────────────────────

def adjust_key_map():
    """Remove keys that don't exist on Mac keyboards."""
    for k in ["scroll_lock", "pause", "insert"]:
        KEY_MAP.pop(k, None)


# ── WAV writer (stdlib only — no soundfile dependency) ───────────────

def _write_wav(path: str, audio: np.ndarray, rate: int):
    """Write float32 audio to a 16-bit WAV using only the standard library."""
    int16_audio = (audio * 32767).clip(-32768, 32767).astype(np.int16)
    with wave.open(path, "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        wf.writeframes(int16_audio.tobytes())


# ── Transcriber ──────────────────────────────────────────────────────

MLX_MODEL_MAP = {
    "tiny":     "mlx-community/whisper-tiny-mlx",
    "base":     "mlx-community/whisper-base-mlx",
    "small":    "mlx-community/whisper-small-mlx",
    "medium":   "mlx-community/whisper-medium-mlx-fp32",
    "large-v3": "mlx-community/whisper-large-v3-mlx",
    "turbo":    "mlx-community/whisper-large-v3-turbo",
}


class MacTranscriber(BaseTranscriber):
    """Transcribes audio using mlx-whisper (Metal-accelerated on Apple Silicon)."""

    def __init__(self, model_size: str = "turbo"):
        import mlx_whisper  # local import
        self._mlx_whisper = mlx_whisper

        self._model_repo = MLX_MODEL_MAP.get(model_size)
        if self._model_repo is None:
            if "/" in model_size:
                self._model_repo = model_size
            else:
                warn(f"Unknown model '{model_size}', falling back to turbo")
                self._model_repo = MLX_MODEL_MAP["turbo"]

        status(f"Loading MLX Whisper model '{model_size}' → {self._model_repo}…", C.CYAN)

        # Warm up: trigger model download if not cached
        try:
            silent = np.zeros(WHISPER_RATE, dtype=np.float32)
            fd, tmp_path = tempfile.mkstemp(suffix=".wav")
            os.close(fd)
            _write_wav(tmp_path, silent, WHISPER_RATE)
            try:
                self._mlx_whisper.transcribe(tmp_path, path_or_hf_repo=self._model_repo)
            finally:
                os.unlink(tmp_path)
        except Exception:
            status("Model will download on first use", C.DIM)

        announce(f"Model '{model_size}' ready (MLX / Metal)")

    def transcribe(self, audio: np.ndarray) -> str:
        """Transcribe audio. Auto-detects English/Spanish."""
        status("Transcribing (MLX)…", C.YELLOW)
        t0 = time.time()

        tmp_path = None
        try:
            fd, tmp_path = tempfile.mkstemp(suffix=".wav")
            os.close(fd)
            _write_wav(tmp_path, audio, WHISPER_RATE)

            result = self._mlx_whisper.transcribe(
                tmp_path,
                path_or_hf_repo=self._model_repo,
                language=None,  # auto-detect
            )
        finally:
            if tmp_path and os.path.exists(tmp_path):
                os.unlink(tmp_path)

        text = result.get("text", "").strip()
        lang = result.get("language", "??")
        elapsed = time.time() - t0
        status(f"Language: {lang}  ·  Took {elapsed:.1f}s", C.DIM)
        return text


# ── Audio Recorder ───────────────────────────────────────────────────

class MacAudioRecorder(BaseAudioRecorder):
    """Records audio via sounddevice (Core Audio through PortAudio)."""

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

    def start(self) -> None:
        self._recording = True
        self._chunks = []
        if self._stream is None:
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


# ── Text injection ───────────────────────────────────────────────────

def type_text(text: str) -> bool:
    """Type text into the focused window using AppleScript keystroke."""
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
        error("osascript not found (should be built into macOS)")
        return False
    except subprocess.TimeoutExpired:
        error("osascript timed out typing text")
        return False
    except subprocess.CalledProcessError as e:
        error(f"osascript error: {e.stderr.decode()}")
        return False


def type_text_clipboard(text: str) -> bool:
    """Paste text via clipboard on macOS (Cmd+V)."""
    if not text.strip():
        return False
    try:
        old_clip = subprocess.run(
            ["pbpaste"], capture_output=True, text=True, timeout=2,
        ).stdout

        proc = subprocess.Popen(["pbcopy"], stdin=subprocess.PIPE)
        proc.communicate(text.encode("utf-8"))

        subprocess.run(
            ["osascript", "-e",
             'tell application "System Events" to keystroke "v" using command down'],
            check=True, timeout=5,
        )

        time.sleep(0.1)

        proc = subprocess.Popen(["pbcopy"], stdin=subprocess.PIPE)
        proc.communicate(old_clip.encode("utf-8"))

        return True
    except Exception as e:
        error(f"Clipboard fallback failed: {e}")
        return False


# ── Platform interface ───────────────────────────────────────────────

def platform_setup():
    """Run macOS-specific initialization."""
    adjust_key_map()
    if not check_accessibility_permission():
        sys.exit(1)

def get_default_model():
    return "turbo"

def get_platform_label():
    return "macOS / Metal"
```

### 7.2 Notes on mlx-whisper

- **Recommended model:** `mlx-community/whisper-large-v3-turbo` — 809M params, 4 decoder layers, multilingual (English + Spanish), ~1.6 GB. Source: https://huggingface.co/mlx-community/whisper-large-v3-turbo
- **No built-in VAD.** Unlike `faster-whisper`, mlx-whisper has no `vad_filter` parameter. For push-to-talk this is fine — the user controls recording boundaries.
- **Temp WAV file approach.** Uses Python's built-in `wave` module — no extra dependency needed.
- **Do NOT use `distil-whisper-large-v3`.** It is English-only and does not support Spanish.
- Models are cached in `~/.cache/huggingface/hub/` (same location as Linux).

---

## Phase 2, Step 8: Create `requirements-macos.txt`

```
mlx-whisper>=0.4.0
mlx>=0.21.0
pynput>=1.7.6
sounddevice>=0.4.6
numpy>=1.24.0
```

---

## Phase 2, Step 9: Update README.md

Add a macOS section after the existing Linux installation instructions:

```markdown
## macOS Installation

### Requirements

- macOS 13+ (Ventura or later)
- Apple Silicon (M1/M2/M3/M4) recommended
- [Homebrew](https://brew.sh)

### 1. Install system dependencies

\```bash
brew install portaudio
\```

### 2. Create the Conda environment

\```bash
conda create -n tak python=3.11 -y
conda activate tak
\```

### 3. Install Python dependencies

\```bash
pip install mlx-whisper pynput sounddevice numpy
\```

### 4. Grant Accessibility permission

TAK needs Accessibility access to detect key presses system-wide:

**System Settings → Privacy & Security → Accessibility** → Add your terminal app

### 5. Run

\```bash
./run.sh
\```

The default trigger key is Right Control (`ctrl_r`).
On MacBook built-in keyboards (no Right Ctrl), use:

\```bash
./run.sh --key caps_lock
\```
```

Also update the model size table to include `turbo`:

```markdown
| Model      | VRAM/RAM | Speed   | Accuracy | Notes |
|------------|----------|---------|----------|-------|
| `tiny`     | ~1 GB   | Fastest | Basic    |       |
| `base`     | ~1 GB   | Fast    | Good     |       |
| `small`    | ~2 GB   | Moderate| Better   |       |
| `medium`   | ~5 GB   | Slower  | Great    | Linux default |
| `large-v3` | ~6 GB   | Slowest | Best     |       |
| `turbo`    | ~2 GB   | Fast    | Great    | macOS default, recommended |
```

---

## Phase 2, Step 10: Test on macOS

### macOS prerequisites

```bash
# Install Homebrew if needed
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# System deps
brew install portaudio

# Python environment
conda create -n tak python=3.11 -y
conda activate tak
pip install mlx-whisper pynput sounddevice numpy

# Grant Accessibility permission
# System Settings → Privacy & Security → Accessibility → add Terminal.app
```

### macOS test commands

```bash
./run.sh                      # default (turbo model, ctrl_r key)
./run.sh --key caps_lock      # MacBook-friendly key
./run.sh --model small        # smaller model
./run.sh --clipboard          # clipboard mode
```

### Phase 2 verification checklist

**Startup and permissions:**

- [ ] Banner shows "macOS / Metal"
- [ ] Clear error if Accessibility permission not granted
- [ ] Microphone permission dialog appears on first run
- [ ] `scroll_lock`, `pause`, `insert` absent from key list

**Recording:**

- [ ] Hold trigger key → "Recording…" appears
- [ ] Release → audio captured, duration printed
- [ ] Tap-and-release (<0.3s) → "Too short" warning

**Transcription:**

- [ ] English speech → correct text
- [ ] Spanish speech → correct text with accents (á, é, ñ, etc.)
- [ ] Language auto-detected and printed
- [ ] Model downloads on first run, cached on subsequent runs

**Text injection:**

- [ ] Default mode: text appears in TextEdit via AppleScript
- [ ] `--clipboard` mode: text pasted via Cmd+V
- [ ] Spanish characters (ñ, á, é, í, ó, ú, ü, ¿, ¡) typed correctly
- [ ] Works in: TextEdit, VS Code, browser text fields, Terminal

**Cross-platform regression:**

- [ ] Linux still works after adding `tak_macos.py` (no import errors)
- [ ] `--cpu` flag accepted on macOS with warning

**Performance:**

- [ ] 3–5 second clip transcribes in < 3 seconds on M1+
- [ ] Metal GPU visible in Activity Monitor during transcription

### Commit

```bash
git add tak_macos.py requirements-macos.txt README.md
git commit -m "feat: add macOS support (Apple Silicon / Metal)

- tak_macos.py: mlx-whisper transcription, Core Audio recording, AppleScript text injection
- Default model: whisper-large-v3-turbo (fast + multilingual)
- Accessibility permission check on startup
- Mac keyboard adjustments (remove scroll_lock, pause, insert)
- README updated with macOS installation instructions"
```

---

## Common Mistakes to Avoid

1. **Don't leave `_ensure_cuda_libs()` auto-calling at module level.** The current code runs it as a side effect of importing `tak.py`. In the new structure it must only run inside `platform_setup()`.

2. **Don't import `faster_whisper` at the top of `tak_linux.py`.** Local import inside `LinuxTranscriber.__init__()` only. Same for `mlx_whisper` in `tak_macos.py`.

3. **Don't forget `self._normalize()` → `self.normalize()`.** The method moved from a private static method on `AudioRecorder` to a public static method on `BaseAudioRecorder`. Update call sites in `_stop_pw()` and `_stop_sd()`.

4. **Don't put platform-detection logic in `tak_core.py`.** Zero `import platform` calls in core. All branching happens in `tak.py`.

5. **Don't modify `KEY_MAP` in `tak_core.py` based on platform.** The full map lives in core. macOS removes unsupported keys in `platform_setup()`. Linux doesn't modify it.

6. **Don't use `soundfile` in `tak_macos.py`.** The `_write_wav()` helper uses only the standard library `wave` module, avoiding an extra dependency.

7. **Don't use `distil-whisper-large-v3` on macOS.** It's English-only and breaks Spanish support.

---

## Optional Enhancements (Post-MVP)

Not required for either phase, but nice improvements for later:

1. **CGEventPost text injection (macOS)** — Better Unicode than AppleScript. Requires `pyobjc-framework-Quartz`. Recommended if Spanish characters cause issues with `osascript`.

2. **`lightning-whisper-mlx` backend** — Claims 4x faster than standard mlx-whisper. Could be offered as `--backend lightning`. Source: https://github.com/mustafaaljadery/lightning-whisper-mlx

3. **Silero VAD preprocessing (macOS)** — mlx-whisper has no built-in VAD. Add as optional preprocessing for noisy environments.

4. **Intel Mac detection** — Detect `platform.machine() != "arm64"` and warn about slower CPU-only performance.

5. **Wayland support (Linux)** — `xdotool` doesn't work on Wayland. Would need `wtype` or `ydotool`. Out of scope for this migration." user notes: # TAK Cross-Platform Migration Guide

## Complete Implementation Plan for Claude Code

**Repository:** `github.com/lchonkan/tak`
**Current state:** Single-file Linux app (`tak.py`, ~400 lines)
**Target state:** Multi-file cross-platform app (Linux + macOS)

---

## Execution Order

This guide is organized into two phases, executed sequentially. Each phase ends with a testing gate. Do not start Phase 2 until Phase 1 passes all tests.

| Phase | Goal | Deliverables | Test on |
|-------|------|-------------|---------|
| **1** | Refactor Linux into modular architecture | `tak_core.py`, `tak_linux.py`, new `tak.py`, updated `run.sh` | Linux |
| **2** | Add macOS support | `tak_macos.py`, `requirements-macos.txt`, README update | macOS |

**Commit after Phase 1** to create a clean rollback point before adding macOS.

---

## Target File Structure

```
tak/
├── tak.py                  # Entry point — detects platform, wires backends, runs app
├── tak_core.py             # Shared: TakApp, CLI parser, colors, constants, resampling
├── tak_linux.py            # Linux: LinuxTranscriber, LinuxAudioRecorder, xdotool/xclip
├── tak_macos.py            # macOS: MacTranscriber, MacAudioRecorder, osascript/pbcopy
├── run.sh                  # Cross-platform launcher
├── requirements-linux.txt  # Linux Python dependencies
├── requirements-macos.txt  # macOS Python dependencies
├── README.md               # Updated with macOS instructions
├── LICENSE
└── docs/
    └── architecture.md
```

### Design Principles

- **No `if IS_MACOS` inside core.** Platform branching happens only in `tak.py` (entry point).
- **Constructor injection.** `TakApp` receives backends as arguments — it never imports a platform module.
- **Each platform file is self-contained.** Deleting `tak_linux.py` on a Mac or `tak_macos.py` on Linux causes no errors.
- **Shared utilities in core.** Resampling, normalization, colors, constants, CLI parsing — all platform-agnostic.

### Dependency Flow

```
tak.py  (entry point)
  ├── imports tak_core     (always)
  ├── imports tak_linux    (if Linux)
  └── imports tak_macos    (if macOS)

tak_core.py  (zero platform-specific imports)
  ├── TakApp               (receives backends via constructor)
  ├── BaseAudioRecorder    (ABC)
  ├── BaseTranscriber      (ABC)
  ├── parse_args()
  ├── Color helpers
  ├── Constants
  ├── _resample()
  └── KEY_MAP

tak_linux.py               tak_macos.py
  ├── ensure_cuda_libs()     ├── check_accessibility_permission()
  ├── LinuxTranscriber       ├── MacTranscriber
  ├── LinuxAudioRecorder     ├── MacAudioRecorder
  ├── type_text (xdotool)    ├── type_text (osascript)
  ├── type_text_clipboard    ├── type_text_clipboard
  ├── platform_setup()       ├── platform_setup()
  ├── get_default_model()    ├── get_default_model()
  └── get_platform_label()   └── get_platform_label()
```

---

# PHASE 1 — Linux Refactoring

**Goal:** Split the current monolithic `tak.py` into `tak_core.py` + `tak_linux.py` + new `tak.py` entry point, with zero behavior changes on Linux.

---

## Phase 1, Step 1: Create `tak_core.py`

Create this file from scratch. It will contain everything that is platform-independent, extracted from the current `tak.py`.

### 1.1 Imports

```python
from __future__ import annotations

import argparse
import threading
import time
from abc import ABC, abstractmethod
from typing import Optional, Callable

import numpy as np
from pynput import keyboard
```

### 1.2 Constants

Copy from current `tak.py`:

```python
WHISPER_RATE = 16000
CHANNELS = 1
DTYPE = "int16"
BLOCK_SIZE = 1024
```

### 1.3 Color helpers

Copy the entire `C` class and all five helper functions from current `tak.py`: `status()`, `announce()`, `warn()`, `error()`.

**Modify `banner()`** to accept a platform label:

```python
def banner(platform_label: str = ""):
    print(f"""
{C.CYAN}{C.BOLD}╔══════════════════════════════════════════╗
║            TAK · Talk to Keyboard        ║
║  {platform_label:^40s}║
╚══════════════════════════════════════════╝{C.RESET}
""")
```

### 1.4 Resampling

Copy `_resample()` from current `tak.py` unchanged.

### 1.5 Key map

Copy `KEY_MAP` dictionary from current `tak.py` unchanged. Platform files may modify it at runtime (macOS removes keys that don't exist on Mac keyboards).

### 1.6 Base classes (new)

These don't exist in the current code. Create them:

```python
class BaseAudioRecorder(ABC):
    """Interface for platform-specific audio recorders."""

    @abstractmethod
    def start(self) -> None:
        ...

    @abstractmethod
    def stop(self) -> Optional[np.ndarray]:
        ...

    @staticmethod
    def normalize(audio: np.ndarray) -> np.ndarray:
        """Auto-normalize quiet audio so Whisper can hear it."""
        peak = np.max(np.abs(audio))
        if peak > 1e-6:
            gain = min(0.9 / peak, 200.0)
            if gain > 1.5:
                status(f"Mic level low (peak {peak:.4f}), boosting {gain:.0f}×", C.YELLOW)
            audio = audio * gain
        return audio


class BaseTranscriber(ABC):
    """Interface for platform-specific transcribers."""

    @abstractmethod
    def transcribe(self, audio: np.ndarray) -> str:
        ...
```

The `normalize()` static method is extracted from the current `AudioRecorder._normalize()`. It moves to the base class because both Linux and macOS recorders need it.

### 1.7 TakApp class (modified)

Copy `TakApp` from current `tak.py`, then make these changes:

**Replace the constructor.** The current constructor creates backends internally:

```python
# CURRENT — creates backends itself
def __init__(self, args: argparse.Namespace):
    self.trigger_key = KEY_MAP.get(args.key)
    self.use_clipboard = args.clipboard
    self.recorder = AudioRecorder(device=args.device)
    self.transcriber = Transcriber(model_size=args.model, ...)
```

New constructor receives pre-built backends:

```python
# NEW — receives backends via dependency injection
def __init__(
    self,
    trigger_key,
    recorder: BaseAudioRecorder,
    transcriber: BaseTranscriber,
    type_fn: Callable[[str], bool],
    clipboard_fn: Callable[[str], bool],
    use_clipboard: bool = False,
    platform_label: str = "",
):
    self.trigger_key = trigger_key
    self.recorder = recorder
    self.transcriber = transcriber
    self._type_fn = type_fn
    self._clipboard_fn = clipboard_fn
    self.use_clipboard = use_clipboard
    self._platform_label = platform_label
    self._pressed = False
    self._lock = threading.Lock()
    self._processing = False
```

**Update `_process()`** — replace direct function calls with injected callables:

```python
# CURRENT
if self.use_clipboard:
    ok = type_text_clipboard(text)
else:
    ok = type_text(text)

# NEW
if self.use_clipboard:
    ok = self._clipboard_fn(text)
else:
    ok = self._type_fn(text)
```

**Update `run()`** — use platform label in banner, remove hardcoded platform references:

```python
# CURRENT
banner()
print(f"  {C.BOLD}Input method:{C.RESET}      {'clipboard (Ctrl+V)' if self.use_clipboard else 'xdotool type'}")

# NEW
banner(self._platform_label)
print(f"  {C.BOLD}Input method:{C.RESET}      {'clipboard paste' if self.use_clipboard else 'simulated keystrokes'}")
```

The `_on_press()`, `_on_release()` methods and the rest of `run()` (keyboard listener, Ctrl+C) stay unchanged.

### 1.8 CLI parser (extracted from current `main()`)

```python
def parse_args():
    parser = argparse.ArgumentParser(
        prog="tak",
        description="TAK — Talk to Keyboard. Push-to-talk speech-to-text.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python tak.py                          # Hold Right-Ctrl to talk
  python tak.py --key scroll_lock        # Use Scroll Lock instead
  python tak.py --key caps_lock          # Use Caps Lock (good for MacBooks)
  python tak.py --model large-v3         # More accurate (slower)
  python tak.py --model turbo            # Fast + accurate (macOS default)
  python tak.py --clipboard              # Use clipboard paste
  python tak.py --cpu                    # Run on CPU (no GPU needed)

Available keys:
  ctrl_r (default), ctrl_l, alt_r, alt_l, shift_r, shift_l,
  scroll_lock, pause, insert, f1-f12, caps_lock
        """,
    )
    parser.add_argument("--key", "-k", default="ctrl_r",
                        help="Key to hold for push-to-talk (default: ctrl_r)")
    parser.add_argument("--model", "-m", default=None,
                        help="Whisper model size (default: turbo on macOS, medium on Linux)")
    parser.add_argument("--clipboard", "-c", action="store_true",
                        help="Use clipboard paste instead of simulated typing")
    parser.add_argument("--cpu", action="store_true",
                        help="Force CPU inference (default: uses CUDA if available)")
    parser.add_argument("--device", "-d", type=int, default=None,
                        help="Audio input device index (see: python -m sounddevice)")
    return parser.parse_args()
```

---

## Phase 1, Step 2: Create `tak_linux.py`

Create this file by moving all Linux-specific code from the current `tak.py`.

### 2.1 Imports

```python
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

from tak_core import (
    BaseAudioRecorder, BaseTranscriber,
    WHISPER_RATE, CHANNELS, DTYPE, BLOCK_SIZE,
    status, announce, warn, error, _resample, C,
)
```

**Important:** Do NOT import `faster_whisper` at module level. Use a local import inside `LinuxTranscriber.__init__()`. This keeps the module importable on systems where faster-whisper is not installed.

### 2.2 CUDA initialization

Move the body of `_ensure_cuda_libs()` here and rename it. **Do NOT auto-call it** — in the current `tak.py` this function runs as a side effect of importing the module. In the new structure, it only runs when `platform_setup()` is explicitly called.

```python
def ensure_cuda_libs():
    """Pre-load pip-installed NVIDIA libs so ctranslate2 can find them at runtime."""
    # ... existing _ensure_cuda_libs() body unchanged ...
```

### 2.3 `LinuxTranscriber`

Rename from current `Transcriber`. Inherit from `BaseTranscriber`. Move `faster_whisper` import to local:

```python
class LinuxTranscriber(BaseTranscriber):
    """Transcribes audio using faster-whisper (CUDA-accelerated)."""

    def __init__(self, model_size: str = "medium", device: str = "cuda", compute_type: str = "float16"):
        from faster_whisper import WhisperModel  # local import
        status(f"Loading Whisper model '{model_size}' on {device} ({compute_type})…", C.CYAN)
        self.model = WhisperModel(model_size, device=device, compute_type=compute_type)
        announce(f"Model '{model_size}' loaded and ready")

    def transcribe(self, audio: np.ndarray) -> str:
        # ... existing transcribe() body unchanged ...
```

### 2.4 `LinuxAudioRecorder`

Rename from current `AudioRecorder`. Inherit from `BaseAudioRecorder`.

**One change:** replace `self._normalize()` with `self.normalize()` in both `_stop_pw()` and `_stop_sd()`, since the method now lives on the base class.

```python
class LinuxAudioRecorder(BaseAudioRecorder):
    """Records audio via PipeWire (pw-record) or ALSA fallback (sounddevice)."""

    def __init__(self, device: Optional[int] = None):
        # ... existing __init__ body unchanged ...

    def start(self):
        # ... existing body unchanged ...

    def stop(self) -> Optional[np.ndarray]:
        # ... existing body unchanged ...

    # All private methods move unchanged:
    # _check_pw_record, _init_sounddevice, _sd_callback, _stop_pw, _stop_sd

    # REMOVE the _normalize static method — it now lives in BaseAudioRecorder.normalize()
```

In `_stop_pw()` and `_stop_sd()`, update the call:

```python
# CURRENT
audio_f32 = self._normalize(audio_f32)

# NEW
audio_f32 = self.normalize(audio_f32)
```

### 2.5 Text injection functions

Move `type_text()` and `type_text_clipboard()` from current `tak.py` — no changes to function bodies.

### 2.6 Platform interface functions (new)

Add these at the bottom of the file:

```python
def platform_setup():
    """Run Linux-specific initialization."""
    ensure_cuda_libs()

def get_default_model():
    """Default Whisper model for Linux."""
    return "medium"

def get_platform_label():
    """Platform label for the banner."""
    return "Linux / X11"
```

---

## Phase 1, Step 3: Rewrite `tak.py` as Entry Point

Replace the entire current `tak.py` with:

```python
#!/usr/bin/env python3
"""
TAK — Talk to Keyboard
Push-to-talk speech-to-text that types anywhere.

Cross-platform: Linux (X11) and macOS.

Usage:
    python tak.py                  # default: hold Right-Ctrl to talk
    python tak.py --key scroll_lock
    python tak.py --model large-v3
"""

from __future__ import annotations

import platform
import sys


def main():
    from tak_core import parse_args, KEY_MAP, error, warn

    args = parse_args()

    IS_MACOS = platform.system() == "Darwin"
    IS_LINUX = platform.system() == "Linux"

    # ── Import platform backend ──────────────────────────────────
    if IS_MACOS:
        import tak_macos as backend
    elif IS_LINUX:
        import tak_linux as backend
    else:
        error(f"Unsupported platform: {platform.system()}")
        sys.exit(1)

    # ── Platform-specific initialization ─────────────────────────
    backend.platform_setup()

    # ── Resolve trigger key ──────────────────────────────────────
    trigger_key = KEY_MAP.get(args.key)
    if trigger_key is None:
        error(f"Unknown key '{args.key}'. Available: {', '.join(KEY_MAP.keys())}")
        sys.exit(1)

    # ── Resolve model ────────────────────────────────────────────
    model_size = args.model if args.model else backend.get_default_model()

    # ── Build backends ───────────────────────────────────────────
    if IS_MACOS:
        if args.cpu:
            warn("--cpu flag ignored on macOS (MLX auto-selects best device)")
        recorder = backend.MacAudioRecorder(device=args.device)
        transcriber = backend.MacTranscriber(model_size)
    else:
        recorder = backend.LinuxAudioRecorder(device=args.device)
        device = "cpu" if args.cpu else "cuda"
        compute_type = "int8" if args.cpu else "float16"
        transcriber = backend.LinuxTranscriber(model_size, device=device, compute_type=compute_type)

    # ── Build and run app ────────────────────────────────────────
    from tak_core import TakApp

    app = TakApp(
        trigger_key=trigger_key,
        recorder=recorder,
        transcriber=transcriber,
        type_fn=backend.type_text,
        clipboard_fn=backend.type_text_clipboard,
        use_clipboard=args.clipboard,
        platform_label=backend.get_platform_label(),
    )
    app.run()


if __name__ == "__main__":
    main()
```

---

## Phase 1, Step 4: Update `run.sh`

Replace the current Linux-only `run.sh` with a cross-platform version:

```bash
#!/usr/bin/env bash
# TAK launcher — cross-platform (Linux + macOS)
# Usage: ./run.sh [args...]

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

eval "$(conda shell.bash hook)"
conda activate tak

# Set CUDA library paths only on Linux
if [[ "$(uname)" == "Linux" ]]; then
    SITE_PKGS="$(python3 -c 'import site; print(site.getsitepackages()[0])')"
    CUBLAS_LIB="$SITE_PKGS/nvidia/cublas/lib"
    CUDNN_LIB="$SITE_PKGS/nvidia/cudnn/lib"
    for d in "$CUBLAS_LIB" "$CUDNN_LIB"; do
        if [ -d "$d" ]; then
            export LD_LIBRARY_PATH="${d}:${LD_LIBRARY_PATH:-}"
        fi
    done
fi

exec python3 "$SCRIPT_DIR/tak.py" "$@"
```

---

## Phase 1, Step 5: Create `requirements-linux.txt`

```
faster-whisper>=1.0.0
pynput>=1.7.6
sounddevice>=0.4.6
numpy>=1.24.0
nvidia-cublas-cu12
nvidia-cudnn-cu12
```

---

## Phase 1, Step 6: Test on Linux

Run every combination:

```bash
./run.sh                      # default config
./run.sh --key ctrl_r         # explicit key
./run.sh --model small        # different model
./run.sh --clipboard          # clipboard mode
./run.sh --cpu                # CPU mode
```

### Phase 1 verification checklist

- [ ] Banner shows "Linux / X11"
- [ ] CUDA libs load correctly (GPU model loading message appears)
- [ ] PipeWire recording works (or sounddevice fallback)
- [ ] English transcription works
- [ ] Spanish transcription works
- [ ] `xdotool` text injection works
- [ ] `--clipboard` mode works (xclip)
- [ ] `--cpu` flag switches to CPU inference
- [ ] `--device` flag selects audio input device
- [ ] Short recording (<0.3s) shows "Too short" warning
- [ ] New recording blocked while transcription is in progress
- [ ] Ctrl+C exits cleanly
- [ ] All error messages match pre-refactoring behavior

### ⛔ GATE: Do not proceed to Phase 2 until all boxes are checked.

### Commit

```bash
git add tak.py tak_core.py tak_linux.py run.sh requirements-linux.txt
git commit -m "refactor: split monolithic tak.py into modular architecture

- tak_core.py: shared platform-agnostic code (TakApp, CLI, colors, base classes)
- tak_linux.py: Linux backends (faster-whisper, PipeWire/ALSA, xdotool/xclip)
- tak.py: thin entry point with platform detection
- run.sh: updated for cross-platform support
- No behavior changes on Linux"
```

---

# PHASE 2 — macOS Implementation

**Goal:** Add macOS support by creating `tak_macos.py` with Metal-accelerated backends. No changes to `tak_core.py` or `tak_linux.py`.

---

## Phase 2, Step 7: Create `tak_macos.py`

### 7.1 Full implementation

```python
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

from tak_core import (
    BaseAudioRecorder, BaseTranscriber,
    WHISPER_RATE, CHANNELS, DTYPE, BLOCK_SIZE, KEY_MAP,
    status, announce, warn, error, _resample, C,
)


# ── Accessibility check ──────────────────────────────────────────────

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


# ── Key map adjustments ──────────────────────────────────────────────

def adjust_key_map():
    """Remove keys that don't exist on Mac keyboards."""
    for k in ["scroll_lock", "pause", "insert"]:
        KEY_MAP.pop(k, None)


# ── WAV writer (stdlib only — no soundfile dependency) ───────────────

def _write_wav(path: str, audio: np.ndarray, rate: int):
    """Write float32 audio to a 16-bit WAV using only the standard library."""
    int16_audio = (audio * 32767).clip(-32768, 32767).astype(np.int16)
    with wave.open(path, "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        wf.writeframes(int16_audio.tobytes())


# ── Transcriber ──────────────────────────────────────────────────────

MLX_MODEL_MAP = {
    "tiny":     "mlx-community/whisper-tiny-mlx",
    "base":     "mlx-community/whisper-base-mlx",
    "small":    "mlx-community/whisper-small-mlx",
    "medium":   "mlx-community/whisper-medium-mlx-fp32",
    "large-v3": "mlx-community/whisper-large-v3-mlx",
    "turbo":    "mlx-community/whisper-large-v3-turbo",
}


class MacTranscriber(BaseTranscriber):
    """Transcribes audio using mlx-whisper (Metal-accelerated on Apple Silicon)."""

    def __init__(self, model_size: str = "turbo"):
        import mlx_whisper  # local import
        self._mlx_whisper = mlx_whisper

        self._model_repo = MLX_MODEL_MAP.get(model_size)
        if self._model_repo is None:
            if "/" in model_size:
                self._model_repo = model_size
            else:
                warn(f"Unknown model '{model_size}', falling back to turbo")
                self._model_repo = MLX_MODEL_MAP["turbo"]

        status(f"Loading MLX Whisper model '{model_size}' → {self._model_repo}…", C.CYAN)

        # Warm up: trigger model download if not cached
        try:
            silent = np.zeros(WHISPER_RATE, dtype=np.float32)
            fd, tmp_path = tempfile.mkstemp(suffix=".wav")
            os.close(fd)
            _write_wav(tmp_path, silent, WHISPER_RATE)
            try:
                self._mlx_whisper.transcribe(tmp_path, path_or_hf_repo=self._model_repo)
            finally:
                os.unlink(tmp_path)
        except Exception:
            status("Model will download on first use", C.DIM)

        announce(f"Model '{model_size}' ready (MLX / Metal)")

    def transcribe(self, audio: np.ndarray) -> str:
        """Transcribe audio. Auto-detects English/Spanish."""
        status("Transcribing (MLX)…", C.YELLOW)
        t0 = time.time()

        tmp_path = None
        try:
            fd, tmp_path = tempfile.mkstemp(suffix=".wav")
            os.close(fd)
            _write_wav(tmp_path, audio, WHISPER_RATE)

            result = self._mlx_whisper.transcribe(
                tmp_path,
                path_or_hf_repo=self._model_repo,
                language=None,  # auto-detect
            )
        finally:
            if tmp_path and os.path.exists(tmp_path):
                os.unlink(tmp_path)

        text = result.get("text", "").strip()
        lang = result.get("language", "??")
        elapsed = time.time() - t0
        status(f"Language: {lang}  ·  Took {elapsed:.1f}s", C.DIM)
        return text


# ── Audio Recorder ───────────────────────────────────────────────────

class MacAudioRecorder(BaseAudioRecorder):
    """Records audio via sounddevice (Core Audio through PortAudio)."""

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

    def start(self) -> None:
        self._recording = True
        self._chunks = []
        if self._stream is None:
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


# ── Text injection ───────────────────────────────────────────────────

def type_text(text: str) -> bool:
    """Type text into the focused window using AppleScript keystroke."""
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
        error("osascript not found (should be built into macOS)")
        return False
    except subprocess.TimeoutExpired:
        error("osascript timed out typing text")
        return False
    except subprocess.CalledProcessError as e:
        error(f"osascript error: {e.stderr.decode()}")
        return False


def type_text_clipboard(text: str) -> bool:
    """Paste text via clipboard on macOS (Cmd+V)."""
    if not text.strip():
        return False
    try:
        old_clip = subprocess.run(
            ["pbpaste"], capture_output=True, text=True, timeout=2,
        ).stdout

        proc = subprocess.Popen(["pbcopy"], stdin=subprocess.PIPE)
        proc.communicate(text.encode("utf-8"))

        subprocess.run(
            ["osascript", "-e",
             'tell application "System Events" to keystroke "v" using command down'],
            check=True, timeout=5,
        )

        time.sleep(0.1)

        proc = subprocess.Popen(["pbcopy"], stdin=subprocess.PIPE)
        proc.communicate(old_clip.encode("utf-8"))

        return True
    except Exception as e:
        error(f"Clipboard fallback failed: {e}")
        return False


# ── Platform interface ───────────────────────────────────────────────

def platform_setup():
    """Run macOS-specific initialization."""
    adjust_key_map()
    if not check_accessibility_permission():
        sys.exit(1)

def get_default_model():
    return "turbo"

def get_platform_label():
    return "macOS / Metal"
```

### 7.2 Notes on mlx-whisper

- **Recommended model:** `mlx-community/whisper-large-v3-turbo` — 809M params, 4 decoder layers, multilingual (English + Spanish), ~1.6 GB. Source: https://huggingface.co/mlx-community/whisper-large-v3-turbo
- **No built-in VAD.** Unlike `faster-whisper`, mlx-whisper has no `vad_filter` parameter. For push-to-talk this is fine — the user controls recording boundaries.
- **Temp WAV file approach.** Uses Python's built-in `wave` module — no extra dependency needed.
- **Do NOT use `distil-whisper-large-v3`.** It is English-only and does not support Spanish.
- Models are cached in `~/.cache/huggingface/hub/` (same location as Linux).

---

## Phase 2, Step 8: Create `requirements-macos.txt`

```
mlx-whisper>=0.4.0
mlx>=0.21.0
pynput>=1.7.6
sounddevice>=0.4.6
numpy>=1.24.0
```

---

## Phase 2, Step 9: Update README.md

Add a macOS section after the existing Linux installation instructions:

```markdown
## macOS Installation

### Requirements

- macOS 13+ (Ventura or later)
- Apple Silicon (M1/M2/M3/M4) recommended
- [Homebrew](https://brew.sh)

### 1. Install system dependencies

\```bash
brew install portaudio
\```

### 2. Create the Conda environment

\```bash
conda create -n tak python=3.11 -y
conda activate tak
\```

### 3. Install Python dependencies

\```bash
pip install mlx-whisper pynput sounddevice numpy
\```

### 4. Grant Accessibility permission

TAK needs Accessibility access to detect key presses system-wide:

**System Settings → Privacy & Security → Accessibility** → Add your terminal app

### 5. Run

\```bash
./run.sh
\```

The default trigger key is Right Control (`ctrl_r`).
On MacBook built-in keyboards (no Right Ctrl), use:

\```bash
./run.sh --key caps_lock
\```
```

Also update the model size table to include `turbo`:

```markdown
| Model      | VRAM/RAM | Speed   | Accuracy | Notes |
|------------|----------|---------|----------|-------|
| `tiny`     | ~1 GB   | Fastest | Basic    |       |
| `base`     | ~1 GB   | Fast    | Good     |       |
| `small`    | ~2 GB   | Moderate| Better   |       |
| `medium`   | ~5 GB   | Slower  | Great    | Linux default |
| `large-v3` | ~6 GB   | Slowest | Best     |       |
| `turbo`    | ~2 GB   | Fast    | Great    | macOS default, recommended |
```

---

## Phase 2, Step 10: Test on macOS

### macOS prerequisites

```bash
# Install Homebrew if needed
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# System deps
brew install portaudio

# Python environment
conda create -n tak python=3.11 -y
conda activate tak
pip install mlx-whisper pynput sounddevice numpy

# Grant Accessibility permission
# System Settings → Privacy & Security → Accessibility → add Terminal.app
```

### macOS test commands

```bash
./run.sh                      # default (turbo model, ctrl_r key)
./run.sh --key caps_lock      # MacBook-friendly key
./run.sh --model small        # smaller model
./run.sh --clipboard          # clipboard mode
```

### Phase 2 verification checklist

**Startup and permissions:**

- [ ] Banner shows "macOS / Metal"
- [ ] Clear error if Accessibility permission not granted
- [ ] Microphone permission dialog appears on first run
- [ ] `scroll_lock`, `pause`, `insert` absent from key list

**Recording:**

- [ ] Hold trigger key → "Recording…" appears
- [ ] Release → audio captured, duration printed
- [ ] Tap-and-release (<0.3s) → "Too short" warning

**Transcription:**

- [ ] English speech → correct text
- [ ] Spanish speech → correct text with accents (á, é, ñ, etc.)
- [ ] Language auto-detected and printed
- [ ] Model downloads on first run, cached on subsequent runs

**Text injection:**

- [ ] Default mode: text appears in TextEdit via AppleScript
- [ ] `--clipboard` mode: text pasted via Cmd+V
- [ ] Spanish characters (ñ, á, é, í, ó, ú, ü, ¿, ¡) typed correctly
- [ ] Works in: TextEdit, VS Code, browser text fields, Terminal

**Cross-platform regression:**

- [ ] Linux still works after adding `tak_macos.py` (no import errors)
- [ ] `--cpu` flag accepted on macOS with warning

**Performance:**

- [ ] 3–5 second clip transcribes in < 3 seconds on M1+
- [ ] Metal GPU visible in Activity Monitor during transcription

### Commit

```bash
git add tak_macos.py requirements-macos.txt README.md
git commit -m "feat: add macOS support (Apple Silicon / Metal)

- tak_macos.py: mlx-whisper transcription, Core Audio recording, AppleScript text injection
- Default model: whisper-large-v3-turbo (fast + multilingual)
- Accessibility permission check on startup
- Mac keyboard adjustments (remove scroll_lock, pause, insert)
- README updated with macOS installation instructions"
```

---

## Common Mistakes to Avoid

1. **Don't leave `_ensure_cuda_libs()` auto-calling at module level.** The current code runs it as a side effect of importing `tak.py`. In the new structure it must only run inside `platform_setup()`.

2. **Don't import `faster_whisper` at the top of `tak_linux.py`.** Local import inside `LinuxTranscriber.__init__()` only. Same for `mlx_whisper` in `tak_macos.py`.

3. **Don't forget `self._normalize()` → `self.normalize()`.** The method moved from a private static method on `AudioRecorder` to a public static method on `BaseAudioRecorder`. Update call sites in `_stop_pw()` and `_stop_sd()`.

4. **Don't put platform-detection logic in `tak_core.py`.** Zero `import platform` calls in core. All branching happens in `tak.py`.

5. **Don't modify `KEY_MAP` in `tak_core.py` based on platform.** The full map lives in core. macOS removes unsupported keys in `platform_setup()`. Linux doesn't modify it.

6. **Don't use `soundfile` in `tak_macos.py`.** The `_write_wav()` helper uses only the standard library `wave` module, avoiding an extra dependency.

7. **Don't use `distil-whisper-large-v3` on macOS.** It's English-only and breaks Spanish support.

---

## Optional Enhancements (Post-MVP)

Not required for either phase, but nice improvements for later:

1. **CGEventPost text injection (macOS)** — Better Unicode than AppleScript. Requires `pyobjc-framework-Quartz`. Recommended if Spanish characters cause issues with `osascript`.

2. **`lightning-whisper-mlx` backend** — Claims 4x faster than standard mlx-whisper. Could be offered as `--backend lightning`. Source: https://github.com/mustafaaljadery/lightning-whisper-mlx

3. **Silero VAD preprocessing (macOS)** — mlx-whisper has no built-in VAD. Add as optional preprocessing for noisy environments.

4. **Intel Mac detection** — Detect `platform.machine() != "arm64"` and warn about slower CPU-only performance.

5. **Wayland support (Linux)** — `xdotool` doesn't work on Wayland. Would need `wtype` or `ydotool`. Out of scope for this migration.. You can now continue with the user's answers in mind.