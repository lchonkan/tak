# CLAUDE.md — Instructions for Claude Code

This file tells Claude Code how to work in this repository. Follow these rules for all tasks.

## Git Workflow

This project uses Git Flow. Read `CONTRIBUTING.md` for the full spec. Key rules:

### Branching

- **Never commit directly to `main`.** It is the stable release branch.
- **Never commit directly to `develop`** unless the change is trivial (typo fix, one-line doc edit).
- All work happens on **feature branches created from `develop`**:
  ```
  git checkout develop && git pull origin develop
  git checkout -b <prefix>/<short-description>
  ```
- Branch prefixes: `feature/`, `fix/`, `docs/`, `refactor/`, `test/`, `chore/`
- Lowercase, hyphens, short names: `feature/macos-audio`, not `Feature/MacOS_Audio_Recording`

### Hotfixes

- Only for urgent production bugs. Branch from `main`, PR targets `main`.
- After merge, back-merge `main` into `develop`.

### Commits

- Use Conventional Commits: `<type>: <summary>` (e.g., `feat: add macOS clipboard paste`)
- Types: `feat`, `fix`, `docs`, `refactor`, `test`, `chore`, `perf`
- Summary under 72 characters, imperative mood ("add", not "added")
- Body explains **why**, not what

### Pull Requests

- PRs target **`develop`**, not `main` (unless hotfix)
- Use squash merge
- Keep PRs focused — one logical change per PR
- PR title follows commit message format
- Include a test plan in the description

## Project Architecture

TAK is a modular push-to-talk speech-to-text app. The architecture uses dependency injection to keep platform code separated.

### Package structure

```
tak/                            # Python package
├── __init__.py                 # Package marker + __version__
├── __main__.py                 # Entry point (platform detection, backend wiring)
├── app.py                      # Shared core (TakApp, base classes, CLI, constants)
├── platforms/
│   ├── __init__.py
│   ├── linux.py                # Linux backend
│   └── macos.py                # macOS backend (mlx-whisper, Core Audio, AppleScript)
└── ui/                         # UI layer (planned)
    └── __init__.py
```

### File responsibilities

| File | Role | Rules |
|------|------|-------|
| `tak/__main__.py` | Entry point | Only file that does platform detection. Imports the correct backend and wires it into `TakApp`. |
| `tak/app.py` | Shared core | **Zero platform-specific imports.** No `import platform`, no `if IS_MACOS`. Contains `TakApp`, base classes (`BaseAudioRecorder`, `BaseTranscriber`), `parse_args()`, constants, color helpers, `_resample()`, `KEY_MAP`. |
| `tak/platforms/linux.py` | Linux backend | `LinuxAudioRecorder`, `LinuxTranscriber`, `type_text()`, `type_text_clipboard()`, `ensure_cuda_libs()`, `platform_setup()`, `get_default_model()`, `get_platform_label()`. Imports from `tak.app` only. |
| `tak/platforms/macos.py` | macOS backend | `MacAudioRecorder`, `MacTranscriber`, `type_text()`, `type_text_clipboard()`, `check_accessibility_permission()`, `adjust_key_map()`, `_write_wav()`, `platform_setup()`, `get_default_model()`, `get_platform_label()`. Uses mlx-whisper (Metal), Core Audio (sounddevice), AppleScript (osascript). Imports from `tak.app` only. |
| `run.sh` | Launcher | Activates conda env, sets CUDA paths on Linux only, runs `python -m tak`. |

### Design rules

- **No platform branching in core.** All `if IS_MACOS` / `if IS_LINUX` logic lives in `tak/__main__.py` only.
- **Constructor injection.** `TakApp` receives backends as arguments — it never imports a platform module.
- **Platform modules are self-contained.** Deleting `linux.py` on a Mac or `macos.py` on Linux must not cause errors.
- **Local imports for heavy deps.** `faster_whisper` and `mlx_whisper` are imported inside `__init__()`, not at module level.
- **Shared utilities stay in core.** Resampling, normalization, colors, constants, CLI parsing.
- **All imports are absolute.** Use `from tak.app import ...` and `from tak.platforms import linux`, not relative imports.

### Adding a new platform

1. Create `tak/platforms/<platform>.py` implementing the same interface (see `tak/platforms/linux.py` as reference)
2. Add the platform branch in `tak/__main__.py`
3. Create `requirements-<platform>.txt`
4. Do not modify `tak/app.py` or existing platform files

## Code Style

- Python 3.11+
- Use type hints for function signatures
- Match existing code style — no reformatting of untouched code
- Prefer standard library over new dependencies
- Don't add docstrings, comments, or type annotations to code you didn't change

## Key Documentation

- `CONTRIBUTING.md` — Git Flow, commit conventions, PR guidelines
- `docs/architecture.md` — System diagrams, class hierarchy, threading model
- `docs/platform-architecture.md` — Cross-platform stack comparison diagrams
- `docs/macos-implementation-plan.md` — macOS implementation spec (completed)

## Running and Testing

```bash
./run.sh                    # default config
./run.sh --cpu              # CPU-only (no GPU)
./run.sh --clipboard        # clipboard paste mode
./run.sh --key caps_lock    # different trigger key
./run.sh --model small      # smaller/faster model
python -m tak --help        # direct invocation (after conda activate tak)
```

There are no automated tests yet. Verify changes manually using the commands above and the verification checklists in `docs/macos-implementation-plan.md`.
