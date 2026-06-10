"""Tests for the platform-filtered key map in tak.core.keymap."""

import types

from pynput import keyboard

from tak.core import keymap
from tak.core.keymap import KEY_MAP, _build_key_map


class TestKeyMap:
    def test_common_keys_present(self):
        for name in ("ctrl_r", "alt_r", "shift_l", "f1", "caps_lock"):
            assert name in KEY_MAP

    def test_values_are_key_enum_members(self):
        for value in KEY_MAP.values():
            assert isinstance(value, keyboard.Key)

    def test_missing_platform_keys_are_skipped(self, monkeypatch):
        # A platform whose Key enum only exposes a subset of the entries.
        class PartialKey:
            ctrl_r = "CTRL_R"
            alt_r = "ALT_R"

        monkeypatch.setattr(
            keymap, "keyboard", types.SimpleNamespace(Key=PartialKey)
        )
        result = _build_key_map()
        assert result == {"ctrl_r": "CTRL_R", "alt_r": "ALT_R"}

    def test_empty_key_enum_yields_empty_map(self, monkeypatch):
        monkeypatch.setattr(
            keymap, "keyboard", types.SimpleNamespace(Key=object())
        )
        assert _build_key_map() == {}
