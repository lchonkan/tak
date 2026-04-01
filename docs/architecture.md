# TAK Architecture

![faster-whisper](https://img.shields.io/badge/ASR-faster--whisper-FF6F00?logo=openai&logoColor=white)
![pynput](https://img.shields.io/badge/Input-pynput-4285F4)
![PipeWire](https://img.shields.io/badge/Audio-PipeWire%20%2F%20ALSA-629FF4)
![xdotool](https://img.shields.io/badge/Output-xdotool%20%2F%20xclip-E34F26)
![CTranslate2](https://img.shields.io/badge/Inference-CTranslate2-76B900?logo=nvidia&logoColor=white)
![NumPy](https://img.shields.io/badge/NumPy-Audio%20Processing-013243?logo=numpy&logoColor=white)

Detailed software architecture documentation for TAK (Talk to Keyboard).

## Table of Contents

- [System Overview](#system-overview)
- [Module Structure](#module-structure)
- [Component Diagram](#component-diagram)
- [Class Diagram](#class-diagram)
- [Push-to-Talk Sequence](#push-to-talk-sequence)
- [Application State Machine](#application-state-machine)
- [Audio Pipeline](#audio-pipeline)
- [Text Injection Flow](#text-injection-flow)
- [Threading Model](#threading-model)
- [CUDA Initialization](#cuda-initialization)

---

## System Overview

TAK is a single-process, multi-threaded application that captures speech via push-to-talk and types the transcribed text into any focused window. It uses a modular architecture with platform-agnostic core logic and pluggable platform backends. All processing happens locally — no network calls are made after the initial model download.

```mermaid
graph LR
    User((User)) -->|holds trigger key| TAK
    Mic[Microphone] -->|audio stream| TAK

    subgraph TAK["TAK Application"]
        KL[Key Listener]
        AR[Audio Recorder]
        TR[Transcriber]
        TI[Text Injector]
    end

    TAK -->|simulated keystrokes| FW[Focused Window]

    subgraph "Linux Dependencies"
        PW[PipeWire / ALSA]
        FW_MODEL[faster-whisper]
        XDO[xdotool / xclip]
    end

    AR -.->|records via| PW
    TR -.->|uses| FW_MODEL
    TI -.->|types via| XDO
```

---

## Module Structure

TAK is split into three modules with a clear dependency flow. Platform branching happens only in the entry point — the core module has no platform-specific imports.

```mermaid
graph TD
    subgraph "tak/__main__.py — Entry Point"
        EP[Platform detection<br/>Backend wiring<br/>Dependency injection]
    end

    subgraph "tak/app.py — Shared Core"
        TAKAPP[TakApp]
        BASE[BaseAudioRecorder<br/>BaseTranscriber]
        UTIL[parse_args · colors · constants<br/>KEY_MAP · _resample · normalize]
    end

    subgraph "tak/platforms/linux.py — Linux Backend"
        CUDA_INIT[ensure_cuda_libs]
        LINUX_TR[LinuxTranscriber]
        LINUX_REC[LinuxAudioRecorder]
        LINUX_TI[type_text · type_text_clipboard]
        LINUX_IF[platform_setup · get_default_model<br/>get_platform_label]
    end

    EP -->|imports| TAKAPP
    EP -->|imports on Linux| LINUX_IF
    LINUX_TR -->|extends| BASE
    LINUX_REC -->|extends| BASE
    TAKAPP -->|uses injected| LINUX_TR
    TAKAPP -->|uses injected| LINUX_REC
    TAKAPP -->|uses injected| LINUX_TI
```

### Design Principles

- **No `if IS_MACOS` inside core.** Platform branching happens only in `tak/__main__.py` (entry point).
- **Constructor injection.** `TakApp` receives backends as arguments — it never imports a platform module.
- **Each platform file is self-contained.** Deleting `tak/platforms/linux.py` on a Mac causes no errors.
- **Shared utilities in core.** Resampling, normalization, colors, constants, CLI parsing — all platform-agnostic.

---

## Component Diagram

A detailed view of all components, their responsibilities, and how they interconnect. Components are organized by module.

```mermaid
graph TD
    subgraph "tak/app.py — Platform-Agnostic"
        PYNPUT[pynput<br/>Keyboard Listener]
        TAKAPP[TakApp<br/>Main Controller]
        BASE_REC[BaseAudioRecorder<br/>ABC]
        BASE_TR[BaseTranscriber<br/>ABC]
    end

    subgraph "tak/platforms/linux.py — Linux Backend"
        subgraph Input Layer
            PWREC[pw-record<br/>PipeWire Audio]
            SDEV[sounddevice<br/>ALSA Fallback]
        end

        AREC[LinuxAudioRecorder]
        TRANS[LinuxTranscriber]

        subgraph Output Layer
            XDOTOOL[xdotool<br/>Keystroke Simulation]
            XCLIP[xclip<br/>Clipboard Paste]
        end

        subgraph ML Engine
            WHISPER[faster-whisper<br/>Whisper Model]
            CT2[CTranslate2<br/>Inference Runtime]
            CUDA[CUDA / cuBLAS / cuDNN<br/>GPU Acceleration]
        end
    end

    PYNPUT -->|key events| TAKAPP
    TAKAPP -->|start/stop| AREC
    TAKAPP -->|audio data| TRANS
    TAKAPP -->|text| XDOTOOL
    TAKAPP -->|text| XCLIP

    AREC -->|implements| BASE_REC
    TRANS -->|implements| BASE_TR

    AREC -->|primary| PWREC
    AREC -->|fallback| SDEV

    TRANS --> WHISPER
    WHISPER --> CT2
    CT2 --> CUDA
```

---

## Class Diagram

The class hierarchy uses abstract base classes in `tak_core.py` with concrete implementations in platform modules. `TakApp` receives its dependencies via constructor injection.

```mermaid
classDiagram
    class TakApp {
        -trigger_key: Key
        -recorder: BaseAudioRecorder
        -transcriber: BaseTranscriber
        -_type_fn: Callable
        -_clipboard_fn: Callable
        -use_clipboard: bool
        -_platform_label: str
        -_pressed: bool
        -_lock: threading.Lock
        -_processing: bool
        +run()
        -_on_press(key)
        -_on_release(key)
        -_process(audio: ndarray)
    }

    class BaseAudioRecorder {
        <<abstract>>
        +start()* void
        +stop()* ndarray | None
        +normalize(audio: ndarray)$ ndarray
    }

    class BaseTranscriber {
        <<abstract>>
        +transcribe(audio: ndarray)* str
    }

    class LinuxAudioRecorder {
        -_device: int | None
        -_recording: bool
        -_pw_proc: Popen | None
        -_tmp_path: str
        -_use_pw: bool
        -_stream: InputStream | None
        -_chunks: list~ndarray~
        -_hw_rate: int
        +start()
        +stop() ndarray | None
        -_check_pw_record() bool
        -_init_sounddevice(device)
        -_stop_pw() ndarray | None
        -_stop_sd() ndarray | None
        -_sd_callback(indata, frames, time_info, status)
    }

    class LinuxTranscriber {
        -model: WhisperModel
        +__init__(model_size, device, compute_type)
        +transcribe(audio: ndarray) str
    }

    BaseAudioRecorder <|-- LinuxAudioRecorder : extends
    BaseTranscriber <|-- LinuxTranscriber : extends
    TakApp --> BaseAudioRecorder : recorder (injected)
    TakApp --> BaseTranscriber : transcriber (injected)
    TakApp ..> type_fn : calls (injected)
    TakApp ..> clipboard_fn : calls (injected)
```

### Module ownership

| Class / Function | Module |
|---|---|
| `TakApp`, `BaseAudioRecorder`, `BaseTranscriber`, `parse_args()` | `tak/app.py` |
| `LinuxAudioRecorder`, `LinuxTranscriber`, `type_text()`, `type_text_clipboard()` | `tak/platforms/linux.py` |
| Platform detection, backend wiring | `tak/__main__.py` |

---

## Push-to-Talk Sequence

The complete lifecycle of a single push-to-talk interaction.

```mermaid
sequenceDiagram
    actor User
    participant KL as Key Listener<br/>(pynput)
    participant App as TakApp<br/>(tak/app)
    participant Rec as LinuxAudioRecorder<br/>(tak/platforms/linux)
    participant PW as pw-record / ALSA
    participant Mic as Microphone
    participant Trans as LinuxTranscriber<br/>(tak/platforms/linux)
    participant Whisper as faster-whisper
    participant XDO as xdotool

    User->>KL: Press trigger key
    KL->>App: _on_press(key)
    App->>App: Check not already processing
    App->>Rec: start()
    Rec->>PW: Launch pw-record subprocess
    PW->>Mic: Open audio stream

    Note over Mic,PW: Audio recording in progress...

    User->>KL: Release trigger key
    KL->>App: _on_release(key)
    App->>Rec: stop()
    Rec->>PW: Terminate subprocess
    PW-->>Rec: WAV file on disk
    Rec->>Rec: Read WAV, normalize, resample
    Rec-->>App: float32 audio array

    App->>App: Check audio length >= 0.3s

    App->>App: Spawn transcription thread
    activate App
    App->>Trans: transcribe(audio)
    Trans->>Whisper: model.transcribe()
    Note over Whisper: VAD filtering<br/>Language detection<br/>Beam search decoding
    Whisper-->>Trans: segments + language info
    Trans-->>App: transcribed text

    App->>XDO: type_text(text)
    XDO->>User: Text appears in focused window
    deactivate App
```

---

## Application State Machine

The states TAK transitions through during operation.

```mermaid
stateDiagram-v2
    [*] --> Initializing

    Initializing --> Ready : Model loaded

    Ready --> Recording : Trigger key pressed
    Recording --> Ready : Released too quickly<br/>(&lt; 0.3s)
    Recording --> Transcribing : Trigger key released<br/>(audio &gt;= 0.3s)

    Transcribing --> Typing : Text recognized
    Transcribing --> Ready : No speech detected
    Transcribing --> Ready : Transcription error

    Typing --> Ready : Text typed successfully
    Typing --> Ready : Typing failed

    note right of Recording
        New key presses are
        ignored while in
        Transcribing or Typing
    end note

    note right of Initializing
        Downloads model on
        first run (~1.5 GB)
    end note
```

---

## Audio Pipeline

How audio flows from microphone to Whisper-ready format.

```mermaid
graph TD
    subgraph Recording
        MIC[Microphone Input] --> ROUTE{PipeWire<br/>available?}
        ROUTE -->|Yes| PW[pw-record<br/>16kHz mono s16]
        ROUTE -->|No| SD[sounddevice<br/>native rate]
        PW --> WAV[WAV file on disk]
        SD --> CHUNKS[In-memory chunks]
    end

    subgraph Processing
        WAV --> READ[Read WAV file]
        CHUNKS --> CONCAT[Concatenate chunks]

        READ --> INT16[int16 raw audio]
        CONCAT --> INT16

        INT16 --> F32[Convert to float32<br/>divide by 32768]

        F32 --> RESAMPLE{Sample rate<br/>= 16kHz?}
        RESAMPLE -->|No| LI[Linear interpolation<br/>resample to 16kHz]
        RESAMPLE -->|Yes| NORM
        LI --> NORM

        NORM[Auto-normalize]
        NORM --> PEAK{Peak level<br/>check}
        PEAK -->|Low peak| BOOST[Boost gain<br/>up to 200x]
        PEAK -->|Normal| OUT
        BOOST --> OUT
    end

    OUT[16kHz float32 mono<br/>normalized audio] --> WHISPER[faster-whisper]

    subgraph Transcription
        WHISPER --> VAD[Voice Activity Detection<br/>threshold: 0.3]
        VAD --> LANG[Language Detection<br/>English / Spanish]
        LANG --> BEAM[Beam Search<br/>beam_size: 5]
        BEAM --> TEXT[Transcribed Text]
    end
```

---

## Text Injection Flow

How transcribed text gets typed into the target application (Linux shown — uses xdotool/xclip from `tak_linux.py`).

```mermaid
graph TD
    TEXT[Transcribed Text] --> EMPTY{Text is<br/>empty?}
    EMPTY -->|Yes| SKIP[Skip - no speech detected]
    EMPTY -->|No| MODE{Clipboard<br/>mode?}

    MODE -->|No| XDOTOOL[xdotool type<br/>--clearmodifiers<br/>--delay 12ms]
    MODE -->|Yes| CLIP_FLOW

    subgraph CLIP_FLOW [Clipboard Paste Flow]
        SAVE[Save current clipboard<br/>via xclip -o]
        SET[Set clipboard to text<br/>via xclip]
        PASTE[Simulate Ctrl+V<br/>via xdotool key]
        WAIT[Wait 100ms]
        RESTORE[Restore original clipboard]
        SAVE --> SET --> PASTE --> WAIT --> RESTORE
    end

    XDOTOOL --> RESULT{Success?}
    CLIP_FLOW --> RESULT

    RESULT -->|Yes| DONE[Text appears in<br/>focused window]
    RESULT -->|No| ERR[Error message<br/>in terminal]
```

---

## Threading Model

How TAK manages concurrency to keep the UI responsive.

```mermaid
graph TD
    subgraph Main Thread
        MAIN[main] --> INIT[Initialize TakApp]
        INIT --> LISTENER[keyboard.Listener<br/>blocks on join]
    end

    subgraph Listener Thread["Listener Thread (pynput)"]
        PRESS[on_press callback]
        RELEASE[on_release callback]
        PRESS -->|start recording| REC[recorder.start]
        RELEASE -->|stop recording| STOP[recorder.stop]
    end

    subgraph Worker Thread["Worker Thread (per transcription)"]
        STOP -->|spawn daemon thread| PROCESS[_process]
        PROCESS --> LOCK1[Acquire lock<br/>set _processing = True]
        LOCK1 --> TRANSCRIBE[transcriber.transcribe]
        TRANSCRIBE --> TYPE[_type_fn / _clipboard_fn]
        TYPE --> LOCK2[Release lock<br/>set _processing = False]
    end

    LISTENER -.->|events| PRESS
    LISTENER -.->|events| RELEASE

    LOCK1 -.->|blocks new recordings| PRESS

    style Main_Thread fill:#e1f5fe
    style Worker_Thread fill:#fff3e0
```

The threading lock (`_lock`) ensures that:
- Only one transcription runs at a time
- New key presses are ignored while a transcription is in progress
- State transitions are atomic

---

## CUDA Initialization

How TAK pre-loads NVIDIA libraries before the Whisper model is initialized. This runs on Linux only, triggered by `tak.platforms.linux.platform_setup()` during startup.

```mermaid
sequenceDiagram
    participant EP as tak/__main__.py
    participant LINUX as platforms/linux.py
    participant CTYPES as ctypes
    participant FS as Filesystem
    participant CUDA as CUDA Libraries
    participant CT2 as CTranslate2
    participant WHISPER as faster-whisper

    EP->>LINUX: platform_setup()
    LINUX->>LINUX: ensure_cuda_libs()
    LINUX->>FS: Find site-packages path

    LINUX->>FS: Check libcublasLt.so.12
    FS-->>LINUX: exists
    LINUX->>CTYPES: CDLL(libcublasLt.so.12, RTLD_GLOBAL)
    CTYPES->>CUDA: Load into process address space

    LINUX->>FS: Check libcublas.so.12
    FS-->>LINUX: exists
    LINUX->>CTYPES: CDLL(libcublas.so.12, RTLD_GLOBAL)
    CTYPES->>CUDA: Load into process address space

    LINUX->>FS: Check libcudnn.so.9
    FS-->>LINUX: exists
    LINUX->>CTYPES: CDLL(libcudnn.so.9, RTLD_GLOBAL)
    CTYPES->>CUDA: Load into process address space

    Note over LINUX,CUDA: Libraries now in process memory<br/>LD_LIBRARY_PATH is too late at this point

    EP->>LINUX: LinuxTranscriber(model_size, device, compute_type)
    LINUX->>WHISPER: WhisperModel(device="cuda")
    WHISPER->>CT2: Initialize engine
    CT2->>CUDA: Find cublas/cudnn (already loaded)
    CT2-->>WHISPER: Model ready
