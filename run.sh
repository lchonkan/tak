#!/usr/bin/env bash
# TAK launcher — activates the conda env and runs the app
# Usage: ./run.sh [args...]
#   ./run.sh                     # default: Right-Ctrl to talk
#   ./run.sh --key scroll_lock   # use Scroll Lock
#   ./run.sh --model large-v3    # bigger model

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

eval "$(conda shell.bash hook)"
conda activate tak

# Ensure CUDA 12 libs from pip nvidia packages are on LD_LIBRARY_PATH
SITE_PKGS="$(python3 -c 'import site; print(site.getsitepackages()[0])')"
CUBLAS_LIB="$SITE_PKGS/nvidia/cublas/lib"
CUDNN_LIB="$SITE_PKGS/nvidia/cudnn/lib"

for d in "$CUBLAS_LIB" "$CUDNN_LIB"; do
    if [ -d "$d" ]; then
        export LD_LIBRARY_PATH="${d}:${LD_LIBRARY_PATH:-}"
    fi
done

exec python3 "$SCRIPT_DIR/tak.py" "$@"
