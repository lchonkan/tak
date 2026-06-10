"""Tests for hardware-free helper functions in the platform backends.

These import the backend modules (sounddevice is stubbed in conftest) but never
construct a recorder/transcriber or touch real audio, AppleScript, or xdotool.
"""

import subprocess
import wave

import numpy as np

from tak.backend import linux, macos


class TestWriteWav:
    def test_roundtrip_format(self, tmp_path):
        path = str(tmp_path / "out.wav")
        audio = np.array([0.0, 0.5, -0.5], dtype=np.float32)
        macos._write_wav(path, audio, 16000)

        with wave.open(path, "r") as wf:
            assert wf.getnchannels() == 1
            assert wf.getsampwidth() == 2
            assert wf.getframerate() == 16000
            assert wf.getnframes() == 3

    def test_clips_out_of_range_samples(self, tmp_path):
        path = str(tmp_path / "clip.wav")
        audio = np.array([2.0, -2.0], dtype=np.float32)  # beyond [-1, 1]
        macos._write_wav(path, audio, 16000)

        with wave.open(path, "r") as wf:
            raw = np.frombuffer(wf.readframes(wf.getnframes()), dtype=np.int16)
        assert raw[0] == 32767
        assert raw[1] == -32768


class TestMacTypeTextEscaping:
    def test_quotes_and_backslashes_are_escaped(self, monkeypatch):
        captured = {}

        def fake_run(cmd, **kwargs):
            captured["input"] = kwargs.get("input", b"").decode("utf-8")
            return subprocess.CompletedProcess(cmd, 0)

        monkeypatch.setattr(macos.subprocess, "run", fake_run)
        assert macos.type_text('a"b\\c') is True
        assert r'a\"b\\c' in captured["input"]

    def test_blank_text_is_not_typed(self, monkeypatch):
        called = False

        def fake_run(*a, **k):
            nonlocal called
            called = True

        monkeypatch.setattr(macos.subprocess, "run", fake_run)
        assert macos.type_text("   ") is False
        assert called is False


class TestLinuxTypeText:
    def test_blank_text_is_not_typed(self, monkeypatch):
        called = False

        def fake_run(*a, **k):
            nonlocal called
            called = True

        monkeypatch.setattr(linux.subprocess, "run", fake_run)
        assert linux.type_text("") is False
        assert called is False

    def test_missing_xdotool_returns_false(self, monkeypatch):
        def fake_run(*a, **k):
            raise FileNotFoundError

        monkeypatch.setattr(linux.subprocess, "run", fake_run)
        assert linux.type_text("hi") is False

    def test_timeout_returns_false(self, monkeypatch):
        def fake_run(*a, **k):
            raise subprocess.TimeoutExpired(cmd="xdotool", timeout=30)

        monkeypatch.setattr(linux.subprocess, "run", fake_run)
        assert linux.type_text("hi") is False

    def test_called_process_error_returns_false(self, monkeypatch):
        def fake_run(*a, **k):
            raise subprocess.CalledProcessError(returncode=1, cmd="xdotool")

        monkeypatch.setattr(linux.subprocess, "run", fake_run)
        assert linux.type_text("hi") is False
