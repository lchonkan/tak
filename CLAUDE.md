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
├── __main__.py                 # CLI entry point (platform detection, backend wiring)
├── gui_main.py                 # GUI entry point for macOS .app bundle
├── app.py                      # Shared core (TakApp, base classes, CLI, constants)
├── config.py                   # TakConfig dataclass (platform-agnostic settings)
├── platforms/
│   ├── __init__.py
│   ├── linux.py                # Linux backend
│   └── macos.py                # macOS backend (mlx-whisper, Core Audio, AppleScript)
└── ui/
    ├── __init__.py
    ├── design.py               # Shared design system (colors, fonts, card views)
    ├── overlay_macos.py        # Floating recording/transcribing pill overlay
    ├── menubar_macos.py        # macOS menu bar status item and dropdown
    ├── settings_macos.py       # Preferences window (NSUserDefaults persistence)
    └── splash_macos.py         # Model download splash screen
```

### File responsibilities

| File | Role | Rules |
|------|------|-------|
| `tak/__main__.py` | CLI entry point | Platform detection, CLI argument parsing, backend wiring into `TakApp`. Used by `run.sh` and `python -m tak`. |
| `tak/gui_main.py` | GUI entry point | macOS `.app` bundle launcher. Loads config from NSUserDefaults (not CLI args), shows download splash, builds menu bar and overlay. Used by PyInstaller (`TAK.spec`). |
| `tak/app.py` | Shared core | **Zero platform-specific imports.** No `import platform`, no `if IS_MACOS`. Contains `TakApp`, base classes (`BaseAudioRecorder`, `BaseTranscriber`), `parse_args()`, constants, color helpers, `_resample()`, `KEY_MAP`. |
| `tak/config.py` | Settings container | `TakConfig` dataclass with `trigger_key`, `model`, `use_clipboard`, `audio_device`. Platform-agnostic — no UI or persistence logic. |
| `tak/platforms/linux.py` | Linux backend | `LinuxAudioRecorder`, `LinuxTranscriber`, `type_text()`, `type_text_clipboard()`, `ensure_cuda_libs()`, `platform_setup()`, `get_default_model()`, `get_platform_label()`. Imports from `tak.app` only. |
| `tak/platforms/macos.py` | macOS backend | `MacAudioRecorder`, `MacTranscriber`, `type_text()`, `type_text_clipboard()`, `check_accessibility_permission()`, `adjust_key_map()`, `_write_wav()`, `platform_setup()`, `get_default_model()`, `get_platform_label()`. Uses mlx-whisper (Metal), Core Audio (sounddevice), AppleScript (osascript). Imports from `tak.app` only. |
| `tak/ui/design.py` | Design system | Shared colors, fonts, and reusable views (`CardView`, `BarView`). All UI files import from here. |
| `tak/ui/overlay_macos.py` | Recording overlay | Floating pill on all screens — red while recording, yellow while transcribing. |
| `tak/ui/menubar_macos.py` | Menu bar | `NSStatusItem` with mic icon, status display, Preferences / Uninstall / Quit menu items. |
| `tak/ui/settings_macos.py` | Preferences window | Borderless panel for trigger key, model, audio device, clipboard toggle. Persists to `NSUserDefaults`. Shows inline model download progress. Shows restart-required modal after changes. |
| `tak/ui/splash_macos.py` | Download splash | Full-screen overlay shown during initial model download with progress bar, speed, and ETA. |
| `run.sh` | Launcher | Activates conda env, sets CUDA paths on Linux only, runs `python -m tak`. |
| `TAK.spec` | PyInstaller spec | Builds macOS `.app` bundle via `pyinstaller TAK.spec`. Contains BUNDLE step that creates `TAK.app`. All build config (datas, binaries, hidden imports, excludes) lives here — `setup_app.py` just invokes it. |
| `setup_app.py` | App bundle build | Runs `pyinstaller TAK.spec`, then patches Info.plist and ad-hoc code signs the bundle. This is the single command to build: `python setup_app.py`. |
| `ship_dmg.py` | Distribution | Signs the app with Developer ID, creates a DMG with Applications symlink, and notarizes with Apple. Run after `setup_app.py`. |

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

## App Bundle Build

The macOS `.app` bundle is built with PyInstaller. The single build command is:

```bash
conda activate tak
python setup_app.py
```

This runs `pyinstaller TAK.spec`, patches Info.plist, and ad-hoc code signs the bundle. Output: `dist/TAK.app`.

### Build rules

- **All build config lives in `TAK.spec`** — datas, binaries, hidden imports, excludes, and the BUNDLE step. `setup_app.py` only invokes the spec and runs post-build steps (Info.plist patching, code signing).
- **Never bypass `TAK.spec`** by passing CLI flags to PyInstaller directly. The spec file contains the BUNDLE step that creates the `.app` wrapper. Without it, PyInstaller only produces a bare `dist/TAK/` directory.
- **Paths in `TAK.spec` must be dynamic** — resolved from the active Python environment at build time, never hardcoded to a specific conda path.
- **After building, always verify** that `dist/TAK.app/Contents/` exists (not just `dist/TAK/`).
- **After any change to `gui_main.py` or build files**, rebuild and launch the `.app` to verify it works. Check `~/Library/Logs/TAK/tak.log` for errors.

### macOS permissions model

- The `.app` bundle requires Accessibility and Microphone permissions.
- **Never quit the app when accessibility is not granted.** Instead, trigger the system prompt (`AXIsProcessTrustedWithOptions` with `kAXTrustedCheckOptionPrompt`) and continue launching. Use an `NSTimer` to poll `AXIsProcessTrusted()` and restart the pynput listener when permission arrives. This avoids a quit/relaunch loop where macOS keeps revoking permissions on each new code signature.
- pynput silently ignores key events when accessibility is missing — it does not crash. The listener just needs to be restarted after permission is granted mid-session.

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
- `docs/donations.md` — Donation methods and wallet addresses

## Running and Testing

### Terminal (CLI)

```bash
./run.sh                    # default config
./run.sh --cpu              # CPU-only (no GPU)
./run.sh --clipboard        # clipboard paste mode
./run.sh --key caps_lock    # different trigger key
./run.sh --model small      # smaller/faster model
python -m tak --help        # direct invocation (after conda activate tak)
```

### App bundle (macOS)

```bash
python setup_app.py         # build dist/TAK.app + dist/TAK.dmg
open dist/TAK.app           # launch locally
tail -f ~/Library/Logs/TAK/tak.log  # watch logs
```

The `.app` bundle logs to `~/Library/Logs/TAK/tak.log` (stdout/stderr are redirected there). Always check this log when debugging app bundle issues.

### Shipping (signed DMG)

```bash
python setup_app.py         # 1. build dist/TAK.app (ad-hoc signed, for local dev)
python ship_dmg.py          # 2. sign with Developer ID, create DMG, notarize
```

`ship_dmg.py` requires a "Developer ID Application" certificate and accepts `--identity` or `CODESIGN_IDENTITY` env var. Use `--skip-notarize` to sign without submitting to Apple. See `python ship_dmg.py --help` for details.

There are no automated tests yet. Verify changes manually using the commands above and the verification checklists in `docs/macos-implementation-plan.md`.
