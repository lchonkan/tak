"""Audio resampling and base classes for platform recorders/transcribers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

import numpy as np

from tak.core.console import C, status


def _resample(audio: np.ndarray, orig_sr: int, target_sr: int) -> np.ndarray:
    """Resample audio from orig_sr to target_sr using linear interpolation.

    Good enough for speech — avoids pulling in scipy/librosa.
    """
    if orig_sr == target_sr:
        return audio
    duration = len(audio) / orig_sr
    target_len = int(duration * target_sr)
    indices = np.linspace(0, len(audio) - 1, target_len)
    return np.interp(indices, np.arange(len(audio)), audio).astype(np.float32)


class BaseAudioRecorder(ABC):
    """Interface for platform-specific audio recorders."""

    @abstractmethod
    def start(self) -> None:
        ...

    @abstractmethod
    def stop(self) -> Optional[np.ndarray]:
        ...

    @staticmethod
    def normalize(audio: np.ndarray) -> np.ndarray:
        """Auto-normalize quiet audio so Whisper can hear it."""
        peak = np.max(np.abs(audio))
        if peak > 1e-6:
            gain = min(0.9 / peak, 200.0)
            if gain > 1.5:
                status(f"Mic level low (peak {peak:.4f}), boosting {gain:.0f}×", C.YELLOW)
            audio = audio * gain
        return audio


class BaseTranscriber(ABC):
    """Interface for platform-specific transcribers."""

    @abstractmethod
    def transcribe(self, audio: np.ndarray) -> str:
        ...
