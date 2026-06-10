"""Pytest configuration shared across the suite.

Makes the test suite runnable on headless CI runners that have neither an X
server nor audio hardware, by selecting pynput's dummy keyboard backend and
stubbing the optional ``sounddevice`` dependency before any ``tak`` module is
imported.
"""

import os
import sys
import types

# Ensure the package root (this directory) is importable as ``tak``.
sys.path.insert(0, os.path.dirname(__file__))

# pynput probes for an X server at import time. The dummy backend gives a real
# keyboard.Key enum without needing a display, so tak.core.app / tak.core.keymap
# import cleanly under CI.
os.environ.setdefault("PYNPUT_BACKEND_KEYBOARD", "dummy")
os.environ.setdefault("PYNPUT_BACKEND", "dummy")

# The platform backends import sounddevice at module scope. It needs PortAudio
# and audio hardware that CI lacks. Stub it so the modules import; no test
# exercises real capture.
if "sounddevice" not in sys.modules:
    try:  # pragma: no cover - prefer the real library when available
        import sounddevice  # noqa: F401
    except Exception:  # pragma: no cover - exercised only on bare runners
        _sd = types.ModuleType("sounddevice")
        _sd.InputStream = object
        _sd.default = types.SimpleNamespace(device=[None, None])
        _sd.query_devices = lambda *a, **k: {"default_samplerate": 48000}
        _sd.check_input_settings = lambda *a, **k: None
        sys.modules["sounddevice"] = _sd
