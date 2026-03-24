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
- **Configurable** — choose your trigger key, model size, and input method

## Requirements

- Linux with X11 (Wayland support planned)
- NVIDIA GPU with CUDA (or use `--cpu` for CPU-only)
- Conda (Miniconda/Anaconda)
- System packages: `xdotool`, `xclip`, `libportaudio2`

## Quick Start

```bash
# 1. Install system dependencies (one-time)
sudo apt install xdotool xclip libportaudio2

# 2. Run
./run.sh
```

First run will download the Whisper model (~1.5 GB for `medium`).

## Usage

```
Hold Right-Ctrl → Speak → Release → Text appears at cursor
Press Ctrl+C in terminal to quit
```

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

### Available Trigger Keys

```
ctrl_r (default), ctrl_l, alt_r, alt_l, shift_r, shift_l,
scroll_lock, pause, insert, f1–f12, caps_lock
```

### Model Sizes

| Model     | VRAM   | Speed     | Accuracy  |
|-----------|--------|-----------|-----------|
| `tiny`    | ~1 GB  | Fastest   | Basic     |
| `base`    | ~1 GB  | Fast      | Good      |
| `small`   | ~2 GB  | Moderate  | Better    |
| `medium`  | ~5 GB  | Slower    | Great     |
| `large-v3`| ~6 GB  | Slowest   | Best      |

## Troubleshooting

### Text doesn't appear in some apps
Use clipboard mode: `./run.sh --clipboard`

### Permission denied / key not detected
`pynput` needs access to `/dev/input`. Run with your user (not root), or add yourself to the `input` group:
```bash
sudo usermod -aG input $USER
# Log out and back in
```

### No audio input
List devices: `conda activate tak && python -m sounddevice`
Then specify: `./run.sh --device <index>`

## Architecture

```
┌──────────────────────────────────────────────────────┐
│                    TAK Application                   │
│                                                      │
│  ┌─────────┐    ┌──────────┐    ┌──────────────────┐ │
│  │ pynput  │───▶│  Audio   │───▶│  faster-whisper  │ │
│  │ key     │    │ Recorder │    │  (GPU/CUDA)      │ │
│  │ listener│    │ sounddev │    │  auto-detect     │ │
│  └─────────┘    └──────────┘    │  en/es           │ │
│       │                         └────────┬─────────┘ │
│       │                                  │           │
│       │              text                │           │
│       │         ┌────────────────────────┘           │
│       │         ▼                                    │
│       │    ┌──────────┐                              │
│       │    │ xdotool  │──▶ any focused text field    │
│       │    │ type     │                              │
│       │    └──────────┘                              │
│       │                                              │
│  hold key = record │ release = transcribe + type     │
└──────────────────────────────────────────────────────┘
```
