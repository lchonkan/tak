"""Tests for the argument parser in tak.core.cli."""

import pytest

from tak.core.cli import parse_args


def parse(argv, monkeypatch):
    monkeypatch.setattr("sys.argv", ["tak", *argv])
    return parse_args()


class TestDefaults:
    def test_default_values(self, monkeypatch):
        args = parse([], monkeypatch)
        assert args.key == "ctrl_r"
        assert args.model is None
        assert args.clipboard is False
        assert args.cpu is False
        assert args.device is None


class TestFlags:
    def test_long_flags(self, monkeypatch):
        args = parse(
            ["--key", "caps_lock", "--model", "small", "--clipboard",
             "--cpu", "--device", "3"],
            monkeypatch,
        )
        assert args.key == "caps_lock"
        assert args.model == "small"
        assert args.clipboard is True
        assert args.cpu is True
        assert args.device == 3

    def test_short_flags(self, monkeypatch):
        args = parse(["-k", "f5", "-m", "turbo", "-c", "-d", "1"], monkeypatch)
        assert args.key == "f5"
        assert args.model == "turbo"
        assert args.clipboard is True
        assert args.device == 1

    def test_device_must_be_int(self, monkeypatch):
        with pytest.raises(SystemExit):
            parse(["--device", "not-a-number"], monkeypatch)

    def test_help_exits_zero(self, monkeypatch):
        with pytest.raises(SystemExit) as exc:
            parse(["--help"], monkeypatch)
        assert exc.value.code == 0
