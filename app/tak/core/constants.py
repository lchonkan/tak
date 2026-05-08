"""Shared audio constants."""

from __future__ import annotations

WHISPER_RATE = 16000  # Whisper expects 16 kHz
CHANNELS = 1
DTYPE = "int16"
BLOCK_SIZE = 1024  # frames per audio callback

MIN_RECORDING_SECONDS = 0.3
