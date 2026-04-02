"""TAK UI — Visual indicators for application state."""

from __future__ import annotations

from abc import ABC, abstractmethod


class BaseOverlay(ABC):
    """Interface for platform-specific visual overlays."""

    @abstractmethod
    def show_recording(self) -> None:
        """Show overlay indicating audio is being recorded."""
        ...

    @abstractmethod
    def show_transcribing(self) -> None:
        """Show overlay indicating transcription is in progress."""
        ...

    @abstractmethod
    def hide(self) -> None:
        """Hide the overlay."""
        ...
