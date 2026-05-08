"""Main push-to-talk application controller."""

from __future__ import annotations

import threading
import traceback
from typing import Optional, Callable

import numpy as np
from pynput import keyboard

from tak.core.audio import BaseAudioRecorder, BaseTranscriber
from tak.core.console import C, announce, banner, error, status, warn
from tak.core.constants import MIN_RECORDING_SECONDS, WHISPER_RATE
from tak.core.keymap import KEY_MAP


class TakApp:
    """Main push-to-talk application."""

    def __init__(
        self,
        trigger_key,
        recorder: BaseAudioRecorder,
        transcriber: BaseTranscriber,
        type_fn: Callable[[str], bool],
        clipboard_fn: Callable[[str], bool],
        use_clipboard: bool = False,
        platform_label: str = "",
        on_recording: Optional[Callable[[], None]] = None,
        on_transcribing: Optional[Callable[[], None]] = None,
        on_idle: Optional[Callable[[], None]] = None,
        accessibility_check: Optional[Callable[[], bool]] = None,
    ):
        self.trigger_key = trigger_key
        self.recorder = recorder
        self.transcriber = transcriber
        self._type_fn = type_fn
        self._clipboard_fn = clipboard_fn
        self.use_clipboard = use_clipboard
        self._platform_label = platform_label
        self._pressed = False
        self._lock = threading.Lock()
        self._processing = False
        self._on_recording = on_recording or (lambda: None)
        self._on_transcribing = on_transcribing or (lambda: None)
        self._on_idle = on_idle or (lambda: None)
        self._accessibility_check = accessibility_check

    def _on_press(self, key):
        """Handle key press — start recording."""
        if key == self.trigger_key and not self._pressed:
            if self._accessibility_check and not self._accessibility_check():
                return
            with self._lock:
                if self._processing:
                    return  # still transcribing previous clip
                self._pressed = True
            self.recorder.start()
            self._on_recording()

    def _on_release(self, key):
        """Handle key release — stop recording, transcribe, type."""
        if key != self.trigger_key:
            return
        with self._lock:
            if not self._pressed:
                return
            self._pressed = False
        audio = self.recorder.stop()

        if audio is None or len(audio) < WHISPER_RATE * MIN_RECORDING_SECONDS:
            warn("Too short — skipped (hold key longer)")
            self._on_idle()
            return

        self._on_transcribing()
        threading.Thread(target=self._process, args=(audio,), daemon=True).start()

    def _process(self, audio: np.ndarray):
        """Transcribe and type the result."""
        with self._lock:
            self._processing = True

        try:
            text = self.transcriber.transcribe(audio)

            if not text:
                warn("No speech detected")
                return

            announce(f"「{text}」")

            if self.use_clipboard:
                ok = self._clipboard_fn(text)
            else:
                ok = self._type_fn(text)

            if ok:
                status("Typed into focused window ✓", C.GREEN)
            else:
                warn("Could not type text — make sure a text field is focused")
        except Exception as e:
            error(f"Transcription error: {e}\n{traceback.format_exc()}")
        finally:
            with self._lock:
                self._processing = False
            self._on_idle()

    def restart_listener(self):
        """Stop and restart the pynput key listener."""
        self._listener.stop()
        self._listener = keyboard.Listener(
            on_press=self._on_press,
            on_release=self._on_release,
        )
        self._listener.start()

    def run(self, main_loop: Optional[Callable[[], None]] = None):
        """Start the application.

        If main_loop is provided, the pynput listener runs in a daemon thread
        and main_loop takes over the main thread (required for GUI event loops
        on macOS). Otherwise, the listener blocks the main thread directly.
        """
        banner(self._platform_label)
        key_name = getattr(self.trigger_key, 'name', None) or next(
            (k for k, v in KEY_MAP.items() if v == self.trigger_key), str(self.trigger_key)
        )
        print(f"  {C.BOLD}Push-to-talk key:{C.RESET}  {C.CYAN}{key_name}{C.RESET}")
        print(f"  {C.BOLD}Input method:{C.RESET}      {'clipboard paste' if self.use_clipboard else 'simulated keystrokes'}")
        print(f"  {C.BOLD}Languages:{C.RESET}         English · Español (auto-detect)")
        print()
        print(f"  {C.DIM}Hold the key to speak, release to transcribe & type.{C.RESET}")
        print(f"  {C.DIM}Press Ctrl+C to quit.{C.RESET}")
        print()

        self._listener = keyboard.Listener(
            on_press=self._on_press,
            on_release=self._on_release,
        )
        self._listener.start()

        try:
            if main_loop:
                main_loop()
            else:
                self._listener.join()
        except KeyboardInterrupt:
            print(f"\n  {C.DIM}Bye! 👋{C.RESET}\n")
        finally:
            self._listener.stop()
