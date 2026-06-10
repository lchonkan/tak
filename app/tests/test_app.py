"""Tests for the TakApp push-to-talk state machine.

TakApp takes every backend via constructor injection, so the whole controller
can be exercised with in-memory fakes — no audio hardware, no Whisper model.
The only non-determinism is the worker thread spawned in _on_release; we replace
threading.Thread with a synchronous stand-in so the type/clipboard path runs
inline.
"""

import numpy as np
import pytest

from tak.core.app import TakApp
from tak.core.audio import BaseAudioRecorder, BaseTranscriber
from tak.core.constants import MIN_RECORDING_SECONDS, WHISPER_RATE

KEY = object()           # sentinel trigger key
OTHER_KEY = object()     # any non-trigger key

# Audio just over / under the minimum-length gate.
MIN_SAMPLES = int(WHISPER_RATE * MIN_RECORDING_SECONDS)
LONG_AUDIO = np.ones(MIN_SAMPLES + 10, dtype=np.float32)
SHORT_AUDIO = np.ones(MIN_SAMPLES - 10, dtype=np.float32)


class FakeRecorder(BaseAudioRecorder):
    def __init__(self, audio=None):
        self._audio = audio
        self.start_calls = 0
        self.stop_calls = 0

    def start(self):
        self.start_calls += 1

    def stop(self):
        self.stop_calls += 1
        return self._audio


class FakeTranscriber(BaseTranscriber):
    def __init__(self, text="hello world", exc=None):
        self._text = text
        self._exc = exc
        self.calls = []

    def transcribe(self, audio):
        self.calls.append(audio)
        if self._exc is not None:
            raise self._exc
        return self._text


class SyncThread:
    """Drop-in for threading.Thread that runs target() inline on start()."""

    def __init__(self, target=None, args=(), kwargs=None, daemon=None):
        self._target = target
        self._args = args
        self._kwargs = kwargs or {}

    def start(self):
        if self._target is not None:
            self._target(*self._args, **self._kwargs)


@pytest.fixture(autouse=True)
def _sync_threads(monkeypatch):
    monkeypatch.setattr("tak.core.app.threading.Thread", SyncThread)


def make_app(recorder=None, transcriber=None, use_clipboard=False, **kwargs):
    type_calls = []
    clip_calls = []
    events = []
    recorder = recorder or FakeRecorder(LONG_AUDIO)
    transcriber = transcriber or FakeTranscriber()

    def type_fn(text):
        type_calls.append(text)
        return kwargs.pop("type_ok", True)

    def clipboard_fn(text):
        clip_calls.append(text)
        return True

    app = TakApp(
        trigger_key=KEY,
        recorder=recorder,
        transcriber=transcriber,
        type_fn=type_fn,
        clipboard_fn=clipboard_fn,
        use_clipboard=use_clipboard,
        on_recording=lambda: events.append("recording"),
        on_transcribing=lambda: events.append("transcribing"),
        on_idle=lambda: events.append("idle"),
        **kwargs,
    )
    app.type_calls = type_calls
    app.clip_calls = clip_calls
    app.events = events
    app.recorder = recorder
    app.transcriber = transcriber
    return app


class TestKeyGating:
    def test_press_starts_recording(self):
        app = make_app()
        app._on_press(KEY)
        assert app.recorder.start_calls == 1
        assert app.events == ["recording"]

    def test_non_trigger_press_is_ignored(self):
        app = make_app()
        app._on_press(OTHER_KEY)
        assert app.recorder.start_calls == 0
        assert app.events == []

    def test_repeated_press_does_not_restart(self):
        app = make_app()
        app._on_press(KEY)
        app._on_press(KEY)  # key auto-repeat while already held
        assert app.recorder.start_calls == 1

    def test_press_blocked_while_processing(self):
        app = make_app()
        app._processing = True
        app._on_press(KEY)
        assert app.recorder.start_calls == 0

    def test_release_without_press_is_noop(self):
        app = make_app()
        app._on_release(KEY)
        assert app.recorder.stop_calls == 0

    def test_non_trigger_release_is_ignored(self):
        app = make_app()
        app._on_press(KEY)
        app._on_release(OTHER_KEY)
        assert app.recorder.stop_calls == 0

    def test_accessibility_check_blocks_recording(self):
        app = make_app(accessibility_check=lambda: False)
        app._on_press(KEY)
        assert app.recorder.start_calls == 0


class TestRecordingGate:
    def test_too_short_audio_is_skipped(self):
        app = make_app(recorder=FakeRecorder(SHORT_AUDIO))
        app._on_press(KEY)
        app._on_release(KEY)
        assert app.transcriber.calls == []
        assert app.type_calls == []
        assert "transcribing" not in app.events
        assert app.events[-1] == "idle"

    def test_none_audio_is_skipped(self):
        app = make_app(recorder=FakeRecorder(None))
        app._on_press(KEY)
        app._on_release(KEY)
        assert app.transcriber.calls == []
        assert app.events[-1] == "idle"


class TestTranscribeAndType:
    def test_full_flow_types_text(self):
        app = make_app()
        app._on_press(KEY)
        app._on_release(KEY)
        assert app.type_calls == ["hello world"]
        assert app.clip_calls == []
        assert app.events == ["recording", "transcribing", "idle"]

    def test_clipboard_mode_routes_to_clipboard_fn(self):
        app = make_app(use_clipboard=True)
        app._on_press(KEY)
        app._on_release(KEY)
        assert app.clip_calls == ["hello world"]
        assert app.type_calls == []

    def test_empty_transcription_types_nothing(self):
        app = make_app(transcriber=FakeTranscriber(text=""))
        app._on_press(KEY)
        app._on_release(KEY)
        assert app.type_calls == []
        assert app.clip_calls == []
        assert app.events[-1] == "idle"  # still returns to idle

    def test_transcriber_exception_is_caught_and_state_resets(self):
        app = make_app(transcriber=FakeTranscriber(exc=RuntimeError("boom")))
        app._on_press(KEY)
        app._on_release(KEY)  # must not raise
        assert app._processing is False
        assert app.events[-1] == "idle"

    def test_processing_flag_clears_after_success(self):
        app = make_app()
        app._on_press(KEY)
        app._on_release(KEY)
        assert app._processing is False

    def test_can_record_again_after_completion(self):
        app = make_app()
        app._on_press(KEY)
        app._on_release(KEY)
        app._on_press(KEY)
        assert app.recorder.start_calls == 2
