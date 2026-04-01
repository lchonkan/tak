# TAK — Talk to Keyboard

![Python](https://img.shields.io/badge/Python-3.11+-3776AB?logo=python&logoColor=white)
![Platform](https://img.shields.io/badge/Platform-Linux%20%2F%20X11%20·%20macOS-FCC624?logo=linux&logoColor=black)
![CUDA](https://img.shields.io/badge/CUDA-GPU%20Accelerated-76B900?logo=nvidia&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-green)
![Speech](https://img.shields.io/badge/Speech--to--Text-Whisper-FF6F00?logo=openai&logoColor=white)
![Privacy](https://img.shields.io/badge/Privacy-100%25%20Offline-blueviolet)
![GitHub repo size](https://img.shields.io/github/repo-size/lchonkan/tak)
![GitHub last commit](https://img.shields.io/github/last-commit/lchonkan/tak)

Push-to-talk speech-to-text that types anywhere.

Hold a key → speak → release → your words appear wherever you're typing.
Works in any application — terminals, browsers, editors, chat apps, anything with a text cursor.

## Features

- **Push-to-talk** — microphone is only open while you hold the key (no always-on listening)
- **System-wide** — types into whatever window/field currently has focus
- **Cross-platform** — Linux (X11) and macOS (planned)
- **Bilingual** — auto-detects English and Spanish
- **Local & private** — runs entirely on your machine via [faster-whisper](https://github.com/SYSTRAN/faster-whisper) (no cloud APIs)
- **GPU-accelerated** — uses CUDA on your NVIDIA GPU for fast transcription (Linux)
- **Auto-normalization** — automatically boosts quiet microphone levels
- **Voice activity detection** — filters out silence and background noise
- **Modular architecture** — platform-agnostic core with pluggable backends
- **Configurable** — choose your trigger key, model size, and input method

## Requirements

### Linux

- Linux with X11 (Wayland support planned)
- NVIDIA GPU with CUDA (or use `--cpu` for CPU-only)
- [Conda](https://docs.anaconda.com/miniconda/) (Miniconda or Anaconda)
- System packages: `xdotool`, `xclip`, `libportaudio2`

## Installation

### Linux

#### 1. Install system dependencies

```bash
sudo apt install xdotool xclip libportaudio2
```

#### 2. Create the Conda environment

```bash
conda create -n tak python=3.11 -y
conda activate tak
```

#### 3. Install Python dependencies

```bash
pip install -r requirements-linux.txt
```

Or install manually:

```bash
pip install faster-whisper pynput sounddevice numpy
```

For GPU acceleration (recommended), also install the CUDA libraries:

```bash
pip install nvidia-cublas-cu12 nvidia-cudnn-cu12
```

#### 4. Input permissions

`pynput` needs access to `/dev/input` to detect key presses. Add your user to the `input` group:

```bash
sudo usermod -aG input $USER
# Log out and back in for the change to take effect
```

## Quick Start

```bash
./run.sh
```

First run downloads the Whisper model (~1.5 GB for the default `medium` model). Subsequent runs start much faster.

```
Hold Right-Ctrl → Speak → Release → Text appears at cursor
Press Ctrl+C in terminal to quit
```

## Usage

### Options

```
./run.sh --key scroll_lock     # Use a different trigger key
./run.sh --model large-v3      # More accurate (uses more VRAM)
./run.sh --model small          # Faster, less accurate
./run.sh --model tiny           # Fastest, least accurate
./run.sh --clipboard            # Use Ctrl+V paste instead of simulated typing
./run.sh --cpu                  # Run on CPU (no GPU required)
./run.sh --device 2             # Use a specific audio input device
```

You can also run directly with Python (after activating the conda env):

```bash
conda activate tak
python tak.py --key ctrl_r --model medium
```

### Available trigger keys

```
ctrl_r (default), ctrl_l, alt_r, alt_l, shift_r, shift_l,
scroll_lock, pause, insert, f1–f12, caps_lock
```

### Model sizes

| Model      | VRAM   | Speed   | Accuracy |
|------------|--------|---------|----------|
| `tiny`     | ~1 GB  | Fastest | Basic    |
| `base`     | ~1 GB  | Fast    | Good     |
| `small`    | ~2 GB  | Moderate| Better   |
| `medium`   | ~5 GB  | Slower  | Great    |
| `large-v3` | ~6 GB  | Slowest | Best     |

Models are downloaded on first use and cached in `~/.cache/huggingface/hub/`.

## How It Works

TAK has three main stages that run in a loop:

1. **Key listener** — `pynput` monitors for the trigger key. On press, recording starts; on release, recording stops.
2. **Audio recording** — On Linux, captures audio via PipeWire (`pw-record`) for proper device routing, or falls back to ALSA via `sounddevice`. Audio is recorded at 16 kHz mono (Whisper's native format). Quiet audio is auto-normalized so Whisper can hear it.
3. **Transcription & typing** — `faster-whisper` transcribes the audio locally using your GPU (or CPU). The detected text is then typed into the focused window using platform-specific text injection (xdotool on Linux).

Transcription runs in a background thread so the key listener stays responsive. If you start a new recording while the previous one is still being transcribed, it waits until the current transcription finishes.

## Architecture

TAK uses a modular architecture with dependency injection. The core application logic is platform-agnostic, while platform-specific backends (audio recording, transcription, text injection) are plugged in at startup.

```mermaid
graph TD
    subgraph "tak.py (Entry Point)"
        EP[Platform Detection] --> |Linux| LINUX[tak_linux]
        EP --> |macOS| MACOS[tak_macos]
    end

    subgraph "tak_core.py (Shared)"
        APP[TakApp]
        BASE_REC[BaseAudioRecorder]
        BASE_TR[BaseTranscriber]
        PARSE[parse_args]
    end

    subgraph "tak_linux.py (Linux Backend)"
        LREC[LinuxAudioRecorder<br/>PipeWire / ALSA]
        LTR[LinuxTranscriber<br/>faster-whisper + CUDA]
        LTI[type_text<br/>xdotool / xclip]
    end

    LINUX --> |injects backends| APP
    LREC --> |extends| BASE_REC
    LTR --> |extends| BASE_TR
    APP --> |uses| LREC
    APP --> |uses| LTR
    APP --> |uses| LTI
```

For detailed architecture diagrams (class diagrams, sequence diagrams, state machines, threading model, audio pipeline, and more), see **[docs/architecture.md](docs/architecture.md)**.

### Project structure

```
tak/
├── tak.py                  # Entry point — detects platform, wires backends, runs app
├── tak_core.py             # Shared: TakApp, CLI parser, colors, constants, base classes
├── tak_linux.py            # Linux: LinuxTranscriber, LinuxAudioRecorder, xdotool/xclip
├── run.sh                  # Cross-platform launcher (activates conda env + CUDA paths)
├── requirements-linux.txt  # Linux Python dependencies
├── README.md               # This file
├── LICENSE
├── docs/
│   └── architecture.md     # Detailed architecture diagrams
└── .gitignore
```

## Troubleshooting

### Text doesn't appear in some apps

Some applications don't accept simulated keystrokes from `xdotool`. Use clipboard mode instead:

```bash
./run.sh --clipboard
```

### Permission denied / key not detected

`pynput` needs access to `/dev/input`. Make sure your user is in the `input` group:

```bash
sudo usermod -aG input $USER
# Log out and back in
```

### No audio input

List available audio devices:

```bash
conda activate tak && python -m sounddevice
```

Then specify the device index:

```bash
./run.sh --device <index>
```

### PipeWire not available

If `pw-record` is not installed, TAK automatically falls back to direct ALSA recording via `sounddevice`. This works but may not see PipeWire virtual devices (e.g., Bluetooth headsets routed through PipeWire). To install PipeWire tools:

```bash
sudo apt install pipewire-pulse pipewire-audio-client-libraries
```

### CUDA errors on startup

Make sure you have the NVIDIA CUDA pip packages installed:

```bash
pip install nvidia-cublas-cu12 nvidia-cudnn-cu12
```

Or bypass GPU entirely:

```bash
./run.sh --cpu
```

### Model download is slow

Whisper models are downloaded from Hugging Face on first use. If downloads are slow, you can set a mirror:

```bash
export HF_ENDPOINT=https://hf-mirror.com
./run.sh
```

## License

MIT
