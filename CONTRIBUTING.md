# Contributing to TAK

Thanks for your interest in contributing to TAK! This guide covers the branching model, workflow, and conventions we follow.

## Git Flow

TAK uses a simplified Git Flow model with two long-lived branches and short-lived feature branches.

### Branches

| Branch | Purpose | Deploys to |
|--------|---------|------------|
| `main` | Stable, release-ready code | Production / tagged releases |
| `develop` | Integration branch for in-progress work | — |

All development happens on **feature branches** created from `develop`. When `develop` is stable and ready for release, it gets merged into `main` with a version tag.

### Branch naming

Use a prefix that describes the type of change:

```
feature/<short-description>     # New functionality
fix/<short-description>         # Bug fixes
docs/<short-description>        # Documentation only
refactor/<short-description>    # Code restructuring, no behavior change
test/<short-description>        # Adding or updating tests
chore/<short-description>       # Build, CI, dependency updates
```

Examples:
```
feature/macos-support
fix/pipewire-timeout
docs/readme-installation
refactor/extract-audio-pipeline
```

Keep branch names lowercase, use hyphens (not underscores), and keep them short.

### Workflow

#### 1. Start a feature

```bash
git checkout develop
git pull origin develop
git checkout -b feature/my-feature
```

#### 2. Make changes and commit

```bash
git add <files>
git commit -m "feat: add clipboard fallback for Wayland"
```

See [Commit messages](#commit-messages) for the format.

#### 3. Keep your branch up to date

```bash
git fetch origin
git rebase origin/develop
```

Prefer **rebase** over merge to keep a linear history on your feature branch. If the branch has already been pushed and shared, use merge instead to avoid rewriting public history.

#### 4. Push and create a Pull Request

```bash
git push -u origin feature/my-feature
```

Create a PR targeting **`develop`** (not `main`). Fill in the PR template.

#### 5. Review and merge

- At least one approval is required before merging.
- Use **squash merge** for feature branches to keep `develop` history clean.
- Delete the branch after merging.

#### 6. Releasing to main

When `develop` is stable:

```bash
git checkout main
git pull origin main
git merge develop
git tag -a v1.x.x -m "Release v1.x.x"
git push origin main --tags
```

Only maintainers merge into `main`.

### Hotfixes

For urgent fixes to production code:

```bash
git checkout main
git pull origin main
git checkout -b fix/critical-bug
# ... fix, commit, push, PR targeting main ...
```

After the hotfix is merged into `main`, back-merge it into `develop`:

```bash
git checkout develop
git merge main
git push origin develop
```

## Commit Messages

Follow [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>: <short summary>

<optional body — explain why, not what>
```

### Types

| Type | When to use |
|------|-------------|
| `feat` | New feature or functionality |
| `fix` | Bug fix |
| `docs` | Documentation changes only |
| `refactor` | Code change that neither fixes a bug nor adds a feature |
| `test` | Adding or correcting tests |
| `chore` | Build process, CI, dependency updates |
| `perf` | Performance improvement |

### Examples

```
feat: add macOS audio recording via Core Audio
fix: handle missing pw-record gracefully on minimal installs
docs: add macOS installation instructions to README
refactor: extract normalize() into BaseAudioRecorder
chore: add requirements-macos.txt
```

Keep the summary under 72 characters. Use imperative mood ("add", not "added" or "adds").

## Pull Request Guidelines

### Before opening a PR

- [ ] Your branch is based on the latest `develop`
- [ ] Code runs without errors on your platform
- [ ] You've tested the changes manually (see the test commands in the relevant plan doc)
- [ ] No unrelated changes are included (keep PRs focused)

### PR title and description

- **Title:** Same format as commit messages (e.g., `feat: add macOS support`)
- **Description:** Include:
  - What changed and why
  - How to test it
  - Any platform-specific notes (Linux-only, macOS-only, etc.)

### PR scope

Keep PRs small and focused. One PR should do one thing. If you're making a large change, break it into reviewable chunks:

- Good: "Add MacAudioRecorder class" → "Add MacTranscriber class" → "Add text injection for macOS"
- Bad: "Add all macOS support" (1000+ lines in one PR)

## Project Structure

Understanding where code lives helps you put changes in the right place:

```
tak/                                # Project root
├── run.sh                          # Cross-platform launcher
├── requirements-linux.txt
├── requirements-macos.txt
├── README.md
├── CONTRIBUTING.md                 # This file
├── CLAUDE.md
├── LICENSE
├── docs/
│   ├── architecture.md
│   ├── platform-architecture.md
│   └── macos-implementation-plan.md
├── tak/                            # Python package
│   ├── __init__.py                 # Package marker
│   ├── __main__.py                 # Entry point (platform detection, backend wiring)
│   ├── app.py                      # Shared core (TakApp, base classes, CLI, constants)
│   ├── platforms/
│   │   ├── linux.py                # Linux backend (faster-whisper, PipeWire/ALSA, xdotool)
│   │   └── macos.py                # macOS backend (mlx-whisper, Core Audio, AppleScript)
│   └── ui/                         # UI layer (planned)
└── .gitignore
```

### Where to put new code

| Change | File |
|--------|------|
| Platform-agnostic logic (shared by all platforms) | `tak/app.py` |
| Linux-specific feature or fix | `tak/platforms/linux.py` |
| macOS-specific feature or fix | `tak/platforms/macos.py` |
| New platform backend | New `tak/platforms/<platform>.py` file |
| CLI argument changes | `tak/app.py` (`parse_args()`) |
| Entry point / platform wiring | `tak/__main__.py` |

**Design rule:** No `if IS_MACOS` / `if IS_LINUX` inside `tak/app.py`. Platform branching only happens in `tak/__main__.py`.

## Development Setup

### Linux

```bash
sudo apt install xdotool xclip libportaudio2
conda create -n tak python=3.11 -y
conda activate tak
pip install -r requirements-linux.txt
```

### macOS

```bash
brew install portaudio
conda create -n tak python=3.11 -y
conda activate tak
pip install -r requirements-macos.txt
```

Then grant Accessibility permission: System Settings → Privacy & Security → Accessibility → add your terminal app.

### Running

```bash
./run.sh                    # via launcher
python -m tak               # directly (after activating conda env)
python -m tak --cpu         # CPU-only mode (no GPU needed)
```

## Code Style

- Python 3.11+
- No linter/formatter is enforced yet — just be consistent with the existing code
- Use type hints for function signatures
- Keep platform modules self-contained — they should be deletable without breaking other platforms
- Prefer standard library over new dependencies when reasonable

## Getting Help

- Open an [issue](https://github.com/lchonkan/tak/issues) for bugs or feature requests
- Check `docs/` for architecture details and implementation plans

## License

By contributing to TAK, you agree that your contributions will be licensed under the [MIT License](LICENSE).
