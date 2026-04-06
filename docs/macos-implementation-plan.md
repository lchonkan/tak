# macOS Implementation Plan

> **✅ Status: COMPLETED.** All deliverables have been implemented. This document is retained as a reference for the design decisions made during implementation.

Development guide for adding macOS support to TAK. This work happened entirely in new files — no changes to `tak/app.py` or `tak/platforms/linux.py` were needed.

## Current State

macOS support is fully implemented, including a native `.app` bundle with menu bar, preferences UI, and model download progress. The codebase is modular:

```
tak/__main__.py              → CLI entry point, platform detection, backend wiring
tak/gui_main.py              → GUI entry point for macOS .app bundle
tak/app.py                   → shared: TakApp, base classes, CLI, colors, constants
tak/config.py                → TakConfig dataclass (platform-agnostic settings)
tak/platforms/linux.py       → Linux: faster-whisper, PipeWire/ALSA, xdotool/xclip
tak/platforms/macos.py       → macOS: mlx-whisper, Core Audio, AppleScript
tak/ui/design.py             → shared design system (colors, fonts, card views)
tak/ui/overlay_macos.py      → floating recording/transcribing pill overlay
tak/ui/menubar_macos.py      → macOS menu bar status item and dropdown
tak/ui/settings_macos.py     → preferences window (NSUserDefaults persistence)
tak/ui/splash_macos.py       → model download splash screen
```

## Deliverables

### Core (Phase 1)

| File | Status | Description |
|------|--------|-------------|
| `tak/platforms/macos.py` | **✅ Done** | macOS backends (mlx-whisper, Core Audio, AppleScript) |
| `requirements-macos.txt` | **✅ Done** | macOS Python dependencies |
| `README.md` | **✅ Done** | macOS installation section, updated model table |
| `docs/architecture.md` | **✅ Done** | macOS backend added to all diagrams |

### Native UI & .app Bundle (Phase 2)

| File | Status | Description |
|------|--------|-------------|
| `tak/config.py` | **✅ Done** | `TakConfig` dataclass for platform-agnostic settings |
| `tak/gui_main.py` | **✅ Done** | GUI entry point for `.app` bundle (NSUserDefaults config, download splash) |
| `tak/ui/design.py` | **✅ Done** | Shared design system — colors, fonts, `CardView`, `BarView` |
| `tak/ui/overlay_macos.py` | **✅ Done** | Floating recording/transcribing pill overlay on all screens |
| `tak/ui/menubar_macos.py` | **✅ Done** | `NSStatusItem` with mic icon, status display, Preferences/Uninstall/Quit menu |
| `tak/ui/settings_macos.py` | **✅ Done** | Preferences window with trigger key, model, audio device, clipboard toggle. Inline model download progress. NSUserDefaults persistence. Restart-required modal. |
| `tak/ui/splash_macos.py` | **✅ Done** | Model download splash screen with progress bar, speed, and ETA |
| `TAK.spec` | **✅ Done** | PyInstaller spec for building macOS `.app` bundle |
| `setup_app.py` | **✅ Done** | Post-build script for `.app` bundle setup |
| `resources/tak.icns` | **✅ Done** | macOS app icon |

No changes were made to: `tak/app.py`, `tak/platforms/linux.py`.

---

## Prerequisites (macOS dev machine)

Before starting implementation, set up the development environment:

```bash
# 1. Homebrew (if not installed)
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# 2. System dependencies
brew install portaudio

# 3. Conda environment
conda create -n tak python=3.11 -y
conda activate tak

# 4. Python dependencies
pip install mlx-whisper pynput sounddevice numpy

# 5. Accessibility permission (required for pynput key detection)
# System Settings → Privacy & Security → Accessibility → add your terminal app

# 6. Microphone permission
# macOS will prompt on first audio recording attempt
```

### Hardware notes

- **Apple Silicon (M1/M2/M3/M4) recommended.** MLX uses Metal for GPU acceleration on Apple Silicon.
- **Intel Macs** will work but run CPU-only inference. Consider detecting `platform.machine() != "arm64"` and warning about slower performance.
- **macOS 13+ (Ventura)** required for MLX.

---

## Step 1: Create `tak/platforms/macos.py`

This is the main implementation file. It must export the same interface as `tak/platforms/linux.py` so `tak/__main__.py` can use them interchangeably.

### Required exports

The entry point (`tak/__main__.py:50-54`) expects these names:

```python
# Classes
MacAudioRecorder(device: int | None)     # extends BaseAudioRecorder
MacTranscriber(model_size: str)          # extends BaseTranscriber

# Functions
type_text(text: str) -> bool
type_text_clipboard(text: str) -> bool
platform_setup() -> None
get_default_model() -> str
get_platform_label() -> str
```

### 1.1 Imports

```python
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
```

**Do NOT import `mlx_whisper` at module level.** Use a local import inside `MacTranscriber.__init__()`. This keeps the module importable in environments where mlx-whisper is not installed (e.g., during linting on Linux).

### 1.2 Accessibility permission check

macOS requires Accessibility permission for `pynput` to detect global key events. Check this at startup and fail with a clear error message if not granted.

```python
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
```

### 1.3 Key map adjustments

Mac keyboards don't have `scroll_lock`, `pause`, or `insert`. Remove them so `parse_args()` help text doesn't show unsupported keys.

```python
def adjust_key_map():
    """Remove keys that don't exist on Mac keyboards."""
    for k in ["scroll_lock", "pause", "insert"]:
        KEY_MAP.pop(k, None)
```

### 1.4 WAV writer helper

`mlx-whisper` takes a file path (not a numpy array). Write a WAV file using only the standard library `wave` module — no extra dependency needed.

```python
def _write_wav(path: str, audio: np.ndarray, rate: int):
    """Write float32 audio to a 16-bit WAV using only the standard library."""
    int16_audio = (audio * 32767).clip(-32768, 32767).astype(np.int16)
    with wave.open(path, "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        wf.writeframes(int16_audio.tobytes())
```

### 1.5 MacTranscriber

Uses `mlx-whisper` for Metal-accelerated transcription on Apple Silicon.

**Model selection:**

| CLI arg     | MLX Hub repo |
|-------------|-------------|
| `tiny`      | `mlx-community/whisper-tiny-mlx` |
| `base`      | `mlx-community/whisper-base-mlx` |
| `small`     | `mlx-community/whisper-small-mlx` |
| `medium`    | `mlx-community/whisper-medium-mlx-fp32` |
| `large-v3`  | `mlx-community/whisper-large-v3-mlx` |
| `turbo`     | `mlx-community/whisper-large-v3-turbo` (default) |

Key decisions:
- **Default model is `turbo`** — 809M params, 4 decoder layers, fast, multilingual (English + Spanish), ~1.6 GB.
- **Do NOT use `distil-whisper-large-v3`** — it's English-only and breaks Spanish support.
- **No built-in VAD.** Unlike `faster-whisper`, mlx-whisper has no `vad_filter` parameter. For push-to-talk this is acceptable — the user controls recording boundaries via key press/release.
- **Temp WAV file approach.** `mlx-whisper.transcribe()` takes a file path, not a numpy array. Write to a temp file, transcribe, then delete.
- **Warm-up on init.** Transcribe a silent audio clip to trigger model download during startup, not during first real transcription.
- If the user passes a string with `/` in it (e.g., `--model mlx-community/some-model`), use it as a raw HF repo path.
- Models are cached in `~/.cache/huggingface/hub/` (same location as Linux).

The class must:
1. Inherit from `BaseTranscriber`
2. Import `mlx_whisper` locally in `__init__`
3. Map `model_size` string to MLX Hub repo
4. Warm up with a silent clip to trigger download
5. Implement `transcribe(audio: np.ndarray) -> str` that writes a temp WAV, calls `mlx_whisper.transcribe()`, and returns the text

### 1.6 MacAudioRecorder

Uses `sounddevice` with Core Audio (through PortAudio). No PipeWire equivalent needed on macOS.

The class must:
1. Inherit from `BaseAudioRecorder`
2. Detect the hardware sample rate (prefer 48000, then 44100)
3. Record via `sd.InputStream` with a callback that accumulates chunks
4. On `stop()`: concatenate chunks, convert to float32, resample to 16 kHz, normalize (via `self.normalize()` from base class)
5. Use `TMPDIR` environment variable (not `XDG_RUNTIME_DIR`) for any temp files

### 1.7 Text injection — `type_text()`

Uses AppleScript via `osascript` to simulate keystrokes:

```python
escaped = text.replace("\\", "\\\\").replace('"', '\\"')
script = (
    'tell application "System Events"\n'
    f'    keystroke "{escaped}"\n'
    'end tell'
)
subprocess.run(["osascript", "-e", script], check=True, timeout=30, capture_output=True)
```

Must handle:
- Backslash and double-quote escaping for AppleScript strings
- `FileNotFoundError` (should never happen on macOS but be safe)
- `TimeoutExpired` and `CalledProcessError`
- Empty/whitespace-only input (return `False`)

### 1.8 Text injection — `type_text_clipboard()`

Clipboard paste using `pbcopy`/`pbpaste` and Cmd+V:

1. Save current clipboard via `pbpaste`
2. Set clipboard via `pbcopy` (pipe text to stdin)
3. Simulate Cmd+V: `osascript -e 'tell application "System Events" to keystroke "v" using command down'`
4. Sleep 100ms
5. Restore original clipboard via `pbcopy`

### 1.9 Platform interface functions

```python
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

---

## Step 2: Create `requirements-macos.txt`

```
mlx-whisper>=0.4.0
mlx>=0.21.0
pynput>=1.7.6
sounddevice>=0.4.6
numpy>=1.24.0
```

---

## Step 3: Update README.md

Add a macOS section after the existing Linux installation instructions. Keep the Linux section unchanged.

### Changes needed:

1. **Add macOS requirements** under a new `### macOS` heading in the Requirements section:
   - macOS 13+ (Ventura or later)
   - Apple Silicon (M1/M2/M3/M4) recommended
   - Homebrew

2. **Add macOS installation** section:
   - `brew install portaudio`
   - Conda env setup (same as Linux)
   - `pip install -r requirements-macos.txt`
   - Accessibility permission instructions
   - Note about `--key caps_lock` for MacBook keyboards (no Right Ctrl)

3. **Update model sizes table** to include `turbo`:

   | Model      | VRAM/RAM | Speed   | Accuracy | Notes |
   |------------|----------|---------|----------|-------|
   | `tiny`     | ~1 GB   | Fastest | Basic    |       |
   | `base`     | ~1 GB   | Fast    | Good     |       |
   | `small`    | ~2 GB   | Moderate| Better   |       |
   | `medium`   | ~5 GB   | Slower  | Great    | Linux default |
   | `large-v3` | ~6 GB   | Slowest | Best     |       |
   | `turbo`    | ~2 GB   | Fast    | Great    | macOS default |

4. **Add macOS troubleshooting** entries:
   - Accessibility permission not granted
   - Microphone permission not granted
   - No Right Ctrl on MacBook keyboards

---

## Step 4: Update `docs/architecture.md`

Add the macOS backend to the existing diagrams. Changes are additive — do not modify the Linux sections.

1. **Module Structure diagram** — add `tak/platforms/macos.py` as a sibling to `tak/platforms/linux.py`
2. **Component Diagram** — add macOS subgraph with Core Audio, mlx-whisper, AppleScript
3. **Class Diagram** — add `MacAudioRecorder` and `MacTranscriber` extending the base classes

---

## Testing

### macOS test commands

```bash
./run.sh                        # default (turbo model, ctrl_r key)
./run.sh --key caps_lock        # MacBook-friendly key
./run.sh --model small          # smaller model
./run.sh --clipboard            # clipboard mode (Cmd+V)
```

### Verification checklist

**Startup and permissions:**

- [ ] Banner shows "macOS / Metal"
- [ ] Clear error if Accessibility permission not granted
- [ ] Microphone permission dialog appears on first run
- [ ] `scroll_lock`, `pause`, `insert` absent from key list

**Recording:**

- [ ] Hold trigger key → "Recording..." appears
- [ ] Release → audio captured, duration printed
- [ ] Tap-and-release (<0.3s) → "Too short" warning

**Transcription:**

- [ ] English speech → correct text
- [ ] Spanish speech → correct text with accents (a, e, n, etc.)
- [ ] Language auto-detected and printed
- [ ] Model downloads on first run, cached on subsequent runs

**Text injection:**

- [ ] Default mode: text appears in TextEdit via AppleScript keystroke
- [ ] `--clipboard` mode: text pasted via Cmd+V
- [ ] Spanish characters typed correctly
- [ ] Works in: TextEdit, VS Code, browser text fields, Terminal

**Cross-platform regression (run on Linux after adding tak/platforms/macos.py):**

- [ ] Linux still works (no import errors from macos.py)
- [ ] `from tak.platforms import macos` only happens when `platform.system() == "Darwin"`

**Performance:**

- [ ] 3-5 second clip transcribes in < 3 seconds on M1+
- [ ] Metal GPU visible in Activity Monitor during transcription

---

## Common Mistakes to Avoid

1. **Don't import `mlx_whisper` at module level.** Local import inside `MacTranscriber.__init__()` only. This prevents `ImportError` on Linux.

2. **Don't use `distil-whisper-large-v3`.** It is English-only and breaks Spanish support.

3. **Don't add `soundfile` as a dependency.** The `_write_wav()` helper uses only the standard library `wave` module.

4. **Don't modify `tak/app.py`.** The core module is platform-agnostic. All macOS-specific logic goes in `tak/platforms/macos.py`.

5. **Don't modify `tak/platforms/linux.py`.** macOS support is purely additive — new files only.

6. **Don't put platform-detection logic in `tak/platforms/macos.py`.** That lives in `tak/__main__.py` (the entry point). The macOS module assumes it's running on macOS.

7. **Don't modify `KEY_MAP` in `tak/app.py`.** The full map lives in core. macOS removes unsupported keys via `adjust_key_map()` in `platform_setup()`.

8. **Don't forget to call `self.normalize()` (not `self._normalize()`).** The normalize method lives on `BaseAudioRecorder` as a public static method.

---

## Optional Enhancements (Post-MVP)

Not required for the initial implementation, but useful improvements for later:

1. **CGEventPost text injection** — Better Unicode support than AppleScript. Requires `pyobjc-framework-Quartz`. Consider if Spanish characters cause issues with `osascript`.

2. **`lightning-whisper-mlx` backend** — Claims 4x faster than standard mlx-whisper. Could be offered as `--backend lightning`.

3. **Silero VAD preprocessing** — mlx-whisper has no built-in VAD. Could add as optional preprocessing for noisy environments.

4. **Intel Mac detection** — Detect `platform.machine() != "arm64"` and warn about slower CPU-only performance.
