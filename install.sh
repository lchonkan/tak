#!/usr/bin/env bash
# TAK Installer — Cross-platform (macOS + Linux)
# Usage: ./install.sh
#
# Installs system dependencies, creates a conda environment,
# installs Python packages, and verifies the setup.

set -euo pipefail

# ─── Colors ──────────────────────────────────────────────────────────────
RED='\033[0;91m'
GREEN='\033[0;92m'
YELLOW='\033[0;93m'
CYAN='\033[0;96m'
BOLD='\033[1m'
DIM='\033[2m'
RESET='\033[0m'

info()  { echo -e "  ${CYAN}▸${RESET} $1"; }
ok()    { echo -e "  ${GREEN}✔${RESET} $1"; }
warn()  { echo -e "  ${YELLOW}⚠${RESET} $1"; }
fail()  { echo -e "  ${RED}✖${RESET} $1"; }
step()  { echo -e "\n${BOLD}$1${RESET}"; }

# ─── Banner ──────────────────────────────────────────────────────────────
echo -e "
${CYAN}${BOLD}╔══════════════════════════════════════════╗
║          TAK Installer                   ║
║          Talk to Keyboard                ║
╚══════════════════════════════════════════╝${RESET}
"

# ─── Detect platform ─────────────────────────────────────────────────────
OS="$(uname -s)"
ARCH="$(uname -m)"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

case "$OS" in
    Darwin) PLATFORM="macos" ;;
    Linux)  PLATFORM="linux" ;;
    *)      fail "Unsupported platform: $OS"; exit 1 ;;
esac

info "Platform: ${BOLD}$OS $ARCH${RESET}"
info "Install directory: ${BOLD}$SCRIPT_DIR${RESET}"

# ─── Check for conda ────────────────────────────────────────────────────
step "Checking prerequisites..."

if ! command -v conda &>/dev/null; then
    fail "Conda not found. Install Miniconda first:"
    echo "    https://docs.anaconda.com/miniconda/"
    exit 1
fi
ok "Conda found: $(conda --version)"

# ─── System dependencies ────────────────────────────────────────────────
step "Installing system dependencies..."

if [[ "$PLATFORM" == "macos" ]]; then
    if ! command -v brew &>/dev/null; then
        fail "Homebrew not found. Install it first:"
        echo '    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"'
        exit 1
    fi
    ok "Homebrew found"

    BREW_DEPS=(portaudio ffmpeg)
    for dep in "${BREW_DEPS[@]}"; do
        if brew list "$dep" &>/dev/null; then
            ok "$dep already installed"
        else
            info "Installing $dep..."
            brew install "$dep"
            ok "$dep installed"
        fi
    done

elif [[ "$PLATFORM" == "linux" ]]; then
    APT_DEPS=(xdotool xclip libportaudio2)
    MISSING=()
    for dep in "${APT_DEPS[@]}"; do
        if dpkg -s "$dep" &>/dev/null 2>&1; then
            ok "$dep already installed"
        else
            MISSING+=("$dep")
        fi
    done

    if [[ ${#MISSING[@]} -gt 0 ]]; then
        info "Installing: ${MISSING[*]}"
        sudo apt install -y "${MISSING[@]}"
        ok "System packages installed"
    fi
fi

# ─── Conda environment ──────────────────────────────────────────────────
step "Setting up Python environment..."

ENV_NAME="tak"

# Initialize conda for this script
eval "$(conda shell.bash hook)"

if conda env list | grep -q "^${ENV_NAME} "; then
    ok "Conda environment '$ENV_NAME' already exists"
    conda activate "$ENV_NAME"
else
    info "Creating conda environment '$ENV_NAME' (Python 3.11)..."
    conda create -n "$ENV_NAME" python=3.11 -y -q
    conda activate "$ENV_NAME"
    ok "Environment created and activated"
fi

info "Python: $(python --version) at $(which python)"

# ─── Python dependencies ────────────────────────────────────────────────
step "Installing Python dependencies..."

if [[ "$PLATFORM" == "macos" ]]; then
    REQ_FILE="$SCRIPT_DIR/requirements-macos.txt"
else
    REQ_FILE="$SCRIPT_DIR/requirements-linux.txt"
fi

if [[ ! -f "$REQ_FILE" ]]; then
    fail "Requirements file not found: $REQ_FILE"
    exit 1
fi

pip install -q -r "$REQ_FILE"
ok "Python packages installed from $(basename "$REQ_FILE")"

# ─── Verify imports ─────────────────────────────────────────────────────
step "Verifying installation..."

if [[ "$PLATFORM" == "macos" ]]; then
    python -c "import mlx_whisper; import sounddevice; import pynput; print('OK')" 2>/dev/null \
        && ok "All macOS imports verified" \
        || { fail "Import verification failed"; exit 1; }
else
    python -c "import faster_whisper; import sounddevice; import pynput; print('OK')" 2>/dev/null \
        && ok "All Linux imports verified" \
        || { fail "Import verification failed"; exit 1; }
fi

# ─── Platform-specific permissions ───────────────────────────────────────
step "Permissions setup..."

if [[ "$PLATFORM" == "macos" ]]; then
    warn "Accessibility permission required for key detection."
    echo -e "    ${DIM}System Settings → Privacy & Security → Accessibility${RESET}"
    echo -e "    ${DIM}Add your terminal app (Terminal.app / iTerm2 / VS Code)${RESET}"
    echo ""
    warn "Microphone permission will be requested on first recording."

elif [[ "$PLATFORM" == "linux" ]]; then
    if groups | grep -q '\binput\b'; then
        ok "User is in the 'input' group"
    else
        info "Adding user to 'input' group for key detection..."
        sudo usermod -aG input "$USER"
        warn "Log out and back in for the group change to take effect."
    fi
fi

# ─── Make run.sh executable ──────────────────────────────────────────────
chmod +x "$SCRIPT_DIR/run.sh"

# ─── Done ────────────────────────────────────────────────────────────────
echo -e "
${GREEN}${BOLD}╔══════════════════════════════════════════╗
║          Installation complete!           ║
╚══════════════════════════════════════════╝${RESET}

  To start TAK:

    ${CYAN}cd $SCRIPT_DIR${RESET}
    ${CYAN}./run.sh${RESET}

  First run will download the Whisper model (~1.5 GB).
"

if [[ "$PLATFORM" == "macos" ]]; then
    echo -e "  Default key: ${BOLD}Right Option${RESET} (hold to speak, release to type)"
else
    echo -e "  Default key: ${BOLD}Right Ctrl${RESET} (hold to speak, release to type)"
fi

echo -e "  ${DIM}Press Ctrl+C in the terminal to quit.${RESET}
"
