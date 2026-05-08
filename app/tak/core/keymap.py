"""pynput key name → Key enum mapping, filtered by platform availability."""

from __future__ import annotations

from pynput import keyboard


def _build_key_map() -> dict:
    """Build key map, skipping keys that don't exist on the current platform."""
    _entries = [
        ("ctrl_r",      "ctrl_r"),
        ("ctrl_l",      "ctrl_l"),
        ("alt_r",       "alt_r"),
        ("alt_l",       "alt_l"),
        ("shift_r",     "shift_r"),
        ("shift_l",     "shift_l"),
        ("cmd_r",       "cmd_r"),
        ("scroll_lock", "scroll_lock"),
        ("pause",       "pause"),
        ("insert",      "insert"),
        ("f1",  "f1"),  ("f2",  "f2"),  ("f3",  "f3"),  ("f4",  "f4"),
        ("f5",  "f5"),  ("f6",  "f6"),  ("f7",  "f7"),  ("f8",  "f8"),
        ("f9",  "f9"),  ("f10", "f10"), ("f11", "f11"), ("f12", "f12"),
        ("caps_lock",   "caps_lock"),
    ]
    kmap = {}
    for name, attr in _entries:
        try:
            kmap[name] = getattr(keyboard.Key, attr)
        except AttributeError:
            pass  # key doesn't exist on this platform
    return kmap


KEY_MAP = _build_key_map()
