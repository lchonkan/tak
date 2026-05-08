"""Shared model metadata used by UI and backends.

Centralizes MLX Whisper Hub repo IDs so the UI doesn't need to mirror backend
constants and the backend doesn't need to be imported by UI.
"""

from __future__ import annotations


# Keys used throughout the app/UI.
MLX_MODELS: dict[str, str] = {
    "small":    "mlx-community/whisper-small-mlx",
    "medium":   "mlx-community/whisper-medium-mlx-fp32",
    "large-v3": "mlx-community/whisper-large-v3-mlx",
    "turbo":    "mlx-community/whisper-large-v3-turbo",
}

