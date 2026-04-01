# TAK Platform Architecture

![Platform](https://img.shields.io/badge/Platform-Linux%20%7C%20macOS-blue?logo=linux&logoColor=white)
![CUDA](https://img.shields.io/badge/GPU-CUDA%2012-76B900?logo=nvidia&logoColor=white)
![MLX](https://img.shields.io/badge/GPU-MLX%20%2F%20Metal-000000?logo=apple&logoColor=white)
![faster-whisper](https://img.shields.io/badge/ASR-faster--whisper-FF6F00)
![mlx-whisper](https://img.shields.io/badge/ASR-mlx--whisper-000000?logo=apple&logoColor=white)
![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white)

Cross-platform architecture comparison for TAK, covering the full stack from hardware to application layer.

---

## Platform Detection & Dispatch

The entire application branches at a single detection point in `tak/__main__.py`. All platform-specific behavior is isolated in backend modules — the core (`tak/app.py`) has zero platform imports.

```mermaid
flowchart TD
    START([python -m tak]) --> DETECT["platform.system()"]

    DETECT -->|"Linux"| LINUX_IMPORT["from tak.platforms import linux as backend"]
    DETECT -->|"Darwin"| MAC_IMPORT["from tak.platforms import macos as backend"]

    LINUX_IMPORT --> LINUX_SETUP["backend.platform_setup()<br/>ensure_cuda_libs()"]
    MAC_IMPORT --> MAC_SETUP["backend.platform_setup()<br/>adjust_key_map()<br/>check_accessibility_permission()"]

    LINUX_SETUP --> ARGS[Parse CLI args]
    MAC_SETUP --> ARGS

    ARGS --> BUILD_LINUX{Linux}
    ARGS --> BUILD_MAC{macOS}

    BUILD_LINUX --> LINUX_REC["LinuxAudioRecorder<br/>PipeWire / ALSA"]
    BUILD_LINUX --> LINUX_TR["LinuxTranscriber<br/>faster-whisper + CUDA"]
    BUILD_MAC --> MAC_REC["MacAudioRecorder<br/>Core Audio"]
    BUILD_MAC --> MAC_TR["MacTranscriber<br/>mlx-whisper + Metal"]

    LINUX_REC --> APP[TakApp — constructor injection]
    LINUX_TR --> APP
    MAC_REC --> APP
    MAC_TR --> APP

    style LINUX_SETUP fill:#76B900,color:#fff
    style MAC_SETUP fill:#007AFF,color:#fff
    style LINUX_REC fill:#629FF4,color:#fff
    style LINUX_TR fill:#76B900,color:#fff
    style MAC_REC fill:#007AFF,color:#fff
    style MAC_TR fill:#007AFF,color:#fff
```

---

## Full Stack Comparison

Side-by-side view of every layer, from hardware through application output.

```mermaid
graph TB
    subgraph LINUX["Linux Stack"]
        direction TB
        L_HW["NVIDIA GPU<br/>CUDA Cores / Tensor Cores"]
        L_DRV["CUDA 12 Driver<br/>cuBLAS 12 + cuDNN 9"]
        L_PRE["ctypes.CDLL Pre-load<br/>RTLD_GLOBAL into process space"]
        L_INF["CTranslate2<br/>float16 GPU inference"]
        L_ASR["faster-whisper<br/>Whisper model"]
        L_AUDIO["PipeWire pw-record<br/>16kHz mono direct"]
        L_AUDIO_FB["sounddevice / ALSA<br/>fallback"]
        L_OUTPUT["xdotool type<br/>--clearmodifiers --delay 12"]
        L_OUTPUT_FB["xclip + Ctrl+V<br/>clipboard fallback"]

        L_HW --> L_DRV --> L_PRE --> L_INF --> L_ASR
        L_AUDIO --> L_ASR
        L_AUDIO_FB -.->|fallback| L_ASR
        L_ASR --> L_OUTPUT
        L_ASR -.-> L_OUTPUT_FB
    end

    subgraph MACOS["macOS Stack"]
        direction TB
        M_HW["Apple Silicon SoC<br/>CPU + GPU + Neural Engine"]
        M_METAL["Metal GPU<br/>via MLX framework"]
        M_INF["MLX<br/>GPU-accelerated inference"]
        M_ASR["mlx-whisper<br/>Whisper model"]
        M_AUDIO["sounddevice<br/>CoreAudio backend"]
        M_OUTPUT["osascript / AppleScript<br/>keystroke simulation"]
        M_OUTPUT_FB["pbcopy + Cmd+V<br/>clipboard fallback"]

        M_HW --> M_METAL --> M_INF --> M_ASR
        M_AUDIO --> M_ASR
        M_ASR --> M_OUTPUT
        M_ASR -.-> M_OUTPUT_FB
    end

    style LINUX fill:#1a1a2e,color:#fff
    style MACOS fill:#1a1a2e,color:#fff
    style L_HW fill:#76B900,color:#fff
    style L_DRV fill:#76B900,color:#fff
    style L_PRE fill:#76B900,color:#fff
    style L_INF fill:#76B900,color:#fff
    style M_HW fill:#007AFF,color:#fff
    style M_METAL fill:#007AFF,color:#fff
    style M_INF fill:#007AFF,color:#fff
    style L_AUDIO fill:#629FF4,color:#fff
    style L_AUDIO_FB fill:#4a6fa5,color:#fff
    style M_AUDIO fill:#007AFF,color:#fff
    style L_OUTPUT fill:#E34F26,color:#fff
    style L_OUTPUT_FB fill:#a33,color:#fff
    style M_OUTPUT fill:#555,color:#fff
    style M_OUTPUT_FB fill:#333,color:#fff
```

---

## ML Inference Layer Detail

![CUDA float16](https://img.shields.io/badge/Linux-float16%20GPU-76B900?logo=nvidia&logoColor=white)
![MLX Metal](https://img.shields.io/badge/macOS-MLX%20Metal%20GPU-007AFF?logo=apple&logoColor=white)

How the ML inference path differs between platforms.

```mermaid
flowchart LR
    AUDIO["16kHz float32<br/>mono audio"] --> PLATFORM{Platform?}

    PLATFORM -->|Linux| LINUX_PATH
    PLATFORM -->|macOS| MAC_PATH

    subgraph LINUX_PATH["Linux: faster-whisper + CUDA"]
        direction TB
        L_VAD["VAD Filter<br/>threshold: 0.3"]
        L_WHISPER["Whisper Encoder<br/>+ Decoder"]
        CT2_GPU["CTranslate2<br/>GPU Engine"]
        CUBLAS["cuBLAS 12<br/>Matrix Multiply"]
        CUDNN["cuDNN 9<br/>Convolution Ops"]
        VRAM["GPU VRAM<br/>1-6 GB depending on model"]

        L_VAD --> L_WHISPER --> CT2_GPU
        CT2_GPU --> CUBLAS
        CT2_GPU --> CUDNN
        CUBLAS --> VRAM
        CUDNN --> VRAM
    end

    subgraph MAC_PATH["macOS: mlx-whisper + Metal"]
        direction TB
        M_WAV["Write temp WAV<br/>(mlx-whisper needs file path)"]
        M_WHISPER["Whisper Encoder<br/>+ Decoder"]
        MLX_ENGINE["MLX Framework<br/>GPU Engine"]
        METAL["Metal<br/>GPU Compute Shaders"]
        URAM["Unified RAM<br/>~1-6 GB depending on model"]

        M_WAV --> M_WHISPER --> MLX_ENGINE
        MLX_ENGINE --> METAL
        METAL --> URAM
    end

    LINUX_PATH --> TEXT["Transcribed Text"]
    MAC_PATH --> TEXT

    style LINUX_PATH fill:#1b2d1b,color:#fff
    style MAC_PATH fill:#1b2333,color:#fff
    style CT2_GPU fill:#76B900,color:#fff
    style CUBLAS fill:#76B900,color:#fff
    style CUDNN fill:#76B900,color:#fff
    style VRAM fill:#444,color:#fff
    style MLX_ENGINE fill:#007AFF,color:#fff
    style METAL fill:#007AFF,color:#fff
    style URAM fill:#444,color:#fff
```

### Key Differences

| Aspect | Linux (faster-whisper) | macOS (mlx-whisper) |
|--------|----------------------|---------------------|
| **Inference engine** | CTranslate2 | MLX |
| **GPU API** | CUDA | Metal |
| **Compute precision** | float16 (GPU) / int8 (CPU) | MLX default (model-dependent) |
| **Input format** | numpy array (in-memory) | File path (temp WAV on disk) |
| **Built-in VAD** | Yes (Silero VAD, configurable) | No (push-to-talk boundaries suffice) |
| **Model format** | CTranslate2 converted | MLX converted (from HuggingFace) |
| **Default model** | `medium` | `turbo` (whisper-large-v3-turbo) |

---

## CUDA Library Pre-load Sequence (Linux Only)

On Linux, CUDA libraries must be loaded into the process address space *before* CTranslate2 initializes. Setting `LD_LIBRARY_PATH` from Python is too late because the dynamic linker has already cached its search paths.

```mermaid
sequenceDiagram
    participant EP as tak/__main__.py
    participant LINUX as platforms/linux.py
    participant CTYPES as ctypes
    participant FS as Filesystem
    participant CUDA as CUDA Libraries
    participant CT2 as CTranslate2
    participant WHISPER as faster-whisper

    Note over EP: PLATFORM == "Linux"

    EP->>LINUX: platform_setup()
    LINUX->>LINUX: ensure_cuda_libs()
    LINUX->>FS: Find site-packages path

    rect rgb(118, 185, 0, 0.1)
        Note over LINUX,CUDA: Load order matters: cublasLt -> cublas -> cudnn
        LINUX->>CTYPES: CDLL(libcublasLt.so.12, RTLD_GLOBAL)
        CTYPES->>CUDA: Map library globally
        LINUX->>CTYPES: CDLL(libcublas.so.12, RTLD_GLOBAL)
        CTYPES->>CUDA: Map library globally
        LINUX->>CTYPES: CDLL(libcudnn.so.9, RTLD_GLOBAL)
        CTYPES->>CUDA: Map library globally
    end

    Note over CUDA: CUDA libs now in memory

    EP->>LINUX: LinuxTranscriber(model_size, device, compute_type)
    LINUX->>WHISPER: WhisperModel(device="cuda")
    WHISPER->>CT2: Initialize engine
    CT2->>CUDA: dlopen cublas/cudnn — already loaded
    CT2-->>WHISPER: GPU engine ready
```

---

## MLX Model Loading Sequence (macOS Only)

On macOS, mlx-whisper loads MLX-optimized Whisper models from HuggingFace Hub. A warm-up transcription runs at startup to trigger the model download and MLX compilation.

```mermaid
sequenceDiagram
    participant EP as tak/__main__.py
    participant MACOS as platforms/macos.py
    participant MLX as mlx_whisper
    participant HF as HuggingFace Hub
    participant METAL as Metal GPU

    Note over EP: PLATFORM == "Darwin"

    EP->>MACOS: platform_setup()
    MACOS->>MACOS: adjust_key_map()
    MACOS->>MACOS: check_accessibility_permission()

    EP->>MACOS: MacTranscriber("turbo")
    MACOS->>MLX: import mlx_whisper (local)
    MACOS->>MACOS: Map "turbo" → "mlx-community/whisper-large-v3-turbo"

    Note over MACOS,HF: Warm-up: transcribe 1s of silence
    MACOS->>MACOS: _write_wav(silence)
    MACOS->>MLX: transcribe(warmup.wav, path_or_hf_repo=...)
    MLX->>HF: Download model (first run only, ~1.6 GB)
    HF-->>MLX: Model weights cached
    MLX->>METAL: Compile Metal shaders
    METAL-->>MLX: GPU kernels ready
    MLX-->>MACOS: Warm-up complete

    Note over MACOS: Model loaded, Metal GPU ready
```

---

## Audio Recording Layer

```mermaid
flowchart TD
    MIC([Microphone]) --> PLATFORM_CHECK{Platform?}

    PLATFORM_CHECK -->|Linux| PW_CHECK{pw-record<br/>available?}
    PLATFORM_CHECK -->|macOS| COREAUDIO

    PW_CHECK -->|Yes| PIPEWIRE["pw-record subprocess<br/>16kHz mono s16<br/>WAV file on disk"]
    PW_CHECK -->|No| ALSA["sounddevice<br/>ALSA backend<br/>native rate, in-memory"]

    COREAUDIO["sounddevice<br/>CoreAudio backend<br/>native rate, in-memory"]

    PIPEWIRE --> PROCESS
    ALSA --> PROCESS
    COREAUDIO --> PROCESS

    subgraph PROCESS["Audio Processing Pipeline (shared)"]
        direction LR
        READ["Read WAV /<br/>concat chunks"] --> FLOAT["int16 → float32<br/>÷ 32768"]
        FLOAT --> RESAMPLE{"Rate =<br/>16kHz?"}
        RESAMPLE -->|No| INTERP["Linear interpolation<br/>resample to 16kHz"]
        RESAMPLE -->|Yes| NORM
        INTERP --> NORM["Auto-normalize<br/>boost up to 200×"]
    end

    PROCESS --> OUT["16kHz float32 mono<br/>Whisper-ready"]

    style PIPEWIRE fill:#629FF4,color:#fff
    style ALSA fill:#4a6fa5,color:#fff
    style COREAUDIO fill:#007AFF,color:#fff
    style OUT fill:#FF6F00,color:#fff
```

---

## Text Injection Layer

```mermaid
flowchart TD
    TEXT["Transcribed Text"] --> EMPTY{Empty?}
    EMPTY -->|Yes| SKIP([No output])
    EMPTY -->|No| PLAT{Platform?}

    PLAT -->|Linux| CLIP_L{--clipboard?}
    PLAT -->|macOS| CLIP_M{--clipboard?}

    CLIP_L -->|No| XDOTOOL["xdotool type<br/>--clearmodifiers<br/>--delay 12ms"]
    CLIP_L -->|Yes| XCLIP

    CLIP_M -->|No| APPLESCRIPT["osascript<br/>AppleScript keystroke"]
    CLIP_M -->|Yes| PBCOPY

    subgraph XCLIP["Linux Clipboard Paste"]
        direction TB
        XC1["xclip -o (save clipboard)"]
        XC2["xclip (set text)"]
        XC3["xdotool key ctrl+v"]
        XC4["sleep 100ms"]
        XC5["xclip (restore clipboard)"]
        XC1 --> XC2 --> XC3 --> XC4 --> XC5
    end

    subgraph PBCOPY["macOS Clipboard Paste"]
        direction TB
        PB1["pbpaste (save clipboard)"]
        PB2["pbcopy (set text)"]
        PB3["osascript Cmd+V"]
        PB4["sleep 100ms"]
        PB5["pbcopy (restore clipboard)"]
        PB1 --> PB2 --> PB3 --> PB4 --> PB5
    end

    XDOTOOL --> WINDOW([Focused Window])
    XCLIP --> WINDOW
    APPLESCRIPT --> WINDOW
    PBCOPY --> WINDOW

    style XDOTOOL fill:#E34F26,color:#fff
    style APPLESCRIPT fill:#555,color:#fff
    style XCLIP fill:#a33,color:#fff
    style PBCOPY fill:#333,color:#fff
```

---

## Platform Comparison Matrix

| Layer | Linux | macOS |
|-------|-------|-------|
| ![GPU](https://img.shields.io/badge/GPU-76B900?logo=nvidia&logoColor=white) **Accelerator** | NVIDIA CUDA (float16) | Apple Metal via MLX |
| ![Inference](https://img.shields.io/badge/Inference-FF6F00) **Engine** | CTranslate2 + cuBLAS/cuDNN | MLX + Metal GPU |
| ![ASR](https://img.shields.io/badge/ASR-blue) **Whisper Library** | faster-whisper | mlx-whisper |
| ![Model](https://img.shields.io/badge/Model-purple) **Default Model** | `medium` | `turbo` (whisper-large-v3-turbo) |
| ![Audio](https://img.shields.io/badge/Audio-629FF4) **Recording** | PipeWire `pw-record` / ALSA fallback | Core Audio via `sounddevice` |
| ![Output](https://img.shields.io/badge/Output-E34F26) **Text Injection** | `xdotool` / `xclip` | AppleScript / `pbcopy` |
| ![Key](https://img.shields.io/badge/Trigger-blue) **Default Key** | Right Ctrl (`ctrl_r`) | Right Ctrl (`ctrl_r`) |
| ![Perms](https://img.shields.io/badge/Permissions-yellow) **Access** | `input` group for `/dev/input` | Accessibility + Microphone in System Settings |
| ![Speed](https://img.shields.io/badge/Speed-green) **Inference Speed** | Fast (CUDA GPU) | Fast (Metal GPU on Apple Silicon) |

---

## Optional Future Enhancements

These are not currently implemented but could improve performance further:

1. **`lightning-whisper-mlx`** — Claims 4× faster than standard mlx-whisper. Could be offered as `--backend lightning`.
2. **Silero VAD preprocessing** — mlx-whisper has no built-in VAD. Could add as optional preprocessing for noisy environments.
3. **Intel Mac detection** — Detect `platform.machine() != "arm64"` and warn about slower CPU-only performance.
4. **CGEventPost text injection** — Better Unicode support than AppleScript. Requires `pyobjc-framework-Quartz`.
