#!/usr/bin/env bash
# TAK launcher — cross-platform (Linux + macOS)
# Usage: ./run.sh [args...]

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

eval "$(conda shell.bash hook)"
conda activate tak

# Set CUDA library paths only on Linux
if [[ "$(uname)" == "Linux" ]]; then
    SITE_PKGS="$(python3 -c 'import site; print(site.getsitepackages()[0])')"
    CUBLAS_LIB="$SITE_PKGS/nvidia/cublas/lib"
    CUDNN_LIB="$SITE_PKGS/nvidia/cudnn/lib"
    for d in "$CUBLAS_LIB" "$CUDNN_LIB"; do
        if [ -d "$d" ]; then
            export LD_LIBRARY_PATH="${d}:${LD_LIBRARY_PATH:-}"
        fi
    done
fi

export PYTHONPATH="$SCRIPT_DIR:${PYTHONPATH:-}"
exec python3 -m tak "$@"
