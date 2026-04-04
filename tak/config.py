"""TAK configuration — platform-agnostic settings container."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class TakConfig:
    """User-configurable TAK settings."""

    trigger_key: str = "alt_r"
    model: str = "turbo"
    use_clipboard: bool = True
    audio_device: Optional[int] = None
