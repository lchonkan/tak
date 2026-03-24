# TAK — Talk to Keyboard

Push-to-talk speech-to-text that types anywhere on Linux.

Hold a key → speak → release → your words appear wherever you're typing.
Works in any application — terminals, browsers, editors, chat apps, anything with a text cursor.

## Features

- **Push-to-talk** — microphone is only open while you hold the key (no always-on listening)
- **System-wide** — types into whatever window/field currently has focus
- **Bilingual** — auto-detects English and Spanish
- **Local & private** — runs entirely on your machine via [faster-whisper](https://github.com/SYSTRAN/faster-whisper) (no cloud APIs)
- **GPU-accelerated** — uses CUDA on your NVIDIA GPU for fast transcription
- **Auto-normalization** — automatically boosts quiet microphone levels
- **Voice activity detection** — filters out silence and background noise
- **Configurable** — choose your trigger key, model size, and input method

## Requirements

- Linux with X11 (Wayland support planned)
- NVIDIA GPU with CUDA (or use `--cpu` for CPU-only)
- [Conda](https://docs.anaconda.com/miniconda/) (Miniconda or Anaconda)
- System packages: `xdotool`, `xclip`, `libportaudio2`

## Installation

### 1. Install system dependencies

```bash
sudo apt install xdotool xclip libportaudio2
```

### 2. Create the Conda environment

```bash
conda create -n tak python=3.11 -y
conda activate tak
```

### 3. Install Python dependencies

```bash
pip install faster-whisper pynput sounddevice numpy
```

For GPU acceleration (recommended), also install the CUDA libraries:

```bash
pip install nvidia-cublas-cu12 nvidia-cudnn-cu12
```

### 4. Input permissions

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
2. **Audio recording** — Captures audio via PipeWire (`pw-record`) for proper device routing, or falls back to ALSA via `sounddevice`. Audio is recorded at 16 kHz mono (Whisper's native format). Quiet audio is auto-normalized so Whisper can hear it.
3. **Transcription & typing** — `faster-whisper` transcribes the audio locally using your GPU (or CPU). The detected text is then typed into the focused window using `xdotool`, or pasted via clipboard as a fallback.

Transcription runs in a background thread so the key listener stays responsive. If you start a new recording while the previous one is still being transcribed, it waits until the current transcription finishes.

## Architecture

```mermaid
graph LR
    User((User)) -->|holds trigger key| TAK

    subgraph TAK["TAK Application"]
        KL[Key Listener] --> AR[Audio Recorder]
        AR --> TR[Transcriber]
        TR --> TI[Text Injector]
    end

    AR -.->|pw-record / ALSA| Mic[Microphone]
    TR -.->|faster-whisper| GPU[GPU / CPU]
    TI -.->|xdotool / xclip| FW[Focused Window]
```

For detailed architecture diagrams (class diagrams, sequence diagrams, state machines, threading model, audio pipeline, and more), see **[docs/architecture.md](docs/architecture.md)**.

### Project structure

```
tak/
├── tak.py             # Main application (all logic in one file)
├── run.sh             # Launcher script (activates conda env + CUDA paths)
├── README.md          # This file
├── docs/
│   └── architecture.md  # Detailed architecture diagrams
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
