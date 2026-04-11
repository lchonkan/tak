"""
TAK Core — Platform-agnostic shared code.

Contains TakApp, CLI parser, color helpers, constants, base classes,
resampling, and key mapping. No platform-specific imports.
"""

from __future__ import annotations

import argparse
import threading
import time
from abc import ABC, abstractmethod
from typing import Optional, Callable

import numpy as np
from pynput import keyboard

# ─── constants ──────────────────────────────────────────────────────────
WHISPER_RATE = 16000  # Whisper expects 16 kHz
CHANNELS = 1
DTYPE = "int16"
BLOCK_SIZE = 1024  # frames per audio callback


# ─── color helpers ──────────────────────────────────────────────────────
class C:
    RESET  = "\033[0m"
    BOLD   = "\033[1m"
    DIM    = "\033[2m"
    RED    = "\033[91m"
    GREEN  = "\033[92m"
    YELLOW = "\033[93m"
    CYAN   = "\033[96m"
    BLUE   = "\033[94m"
    MAG    = "\033[95m"

def banner(platform_label: str = ""):
    print(f"""
{C.CYAN}{C.BOLD}╔══════════════════════════════════════════╗
║            TAK · Talk to Keyboard        ║
║  {platform_label:^40s}║
╚══════════════════════════════════════════╝{C.RESET}
""")

def status(msg: str, color: str = C.DIM):
    print(f"  {color}▸ {msg}{C.RESET}")

def announce(msg: str):
    print(f"\n  {C.GREEN}{C.BOLD}✔ {msg}{C.RESET}")

def warn(msg: str):
    print(f"  {C.YELLOW}⚠ {msg}{C.RESET}")

def error(msg: str):
    print(f"  {C.RED}✖ {msg}{C.RESET}")


# ─── resampling ──────────────────────────────────────────────────────────
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


# ─── key name mapping ───────────────────────────────────────────────────
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


# ─── base classes ────────────────────────────────────────────────────────
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


# ─── main application ──────────────────────────────────────────────────
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
        if key == self.trigger_key and self._pressed:
            self._pressed = False
            audio = self.recorder.stop()

            if audio is None or len(audio) < WHISPER_RATE * 0.3:
                warn("Too short — skipped (hold key longer)")
                self._on_idle()
                return

            self._on_transcribing()
            # Run transcription in a thread to avoid blocking the key listener
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
            error(f"Transcription error: {e}")
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


# ─── CLI ────────────────────────────────────────────────────────────────
def parse_args():
    parser = argparse.ArgumentParser(
        prog="tak",
        description="TAK — Talk to Keyboard. Push-to-talk speech-to-text.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m tak                          # Hold default key to talk
  python -m tak --key scroll_lock        # Use Scroll Lock instead
  python -m tak --key caps_lock          # Use Caps Lock
  python -m tak --model large-v3         # More accurate (slower)
  python -m tak --model turbo            # Fast + accurate (macOS default)
  python -m tak --clipboard              # Use clipboard paste
  python -m tak --cpu                    # Run on CPU (no GPU needed)

Available keys:
  alt_r (macOS default), ctrl_r (Linux default), ctrl_l, alt_l,
  shift_r, shift_l, scroll_lock, pause, insert, f1-f12, caps_lock
        """,
    )
    parser.add_argument("--key", "-k", default="ctrl_r",
                        help="Key to hold for push-to-talk (default: alt_r on macOS, ctrl_r on Linux)")
    parser.add_argument("--model", "-m", default=None,
                        help="Whisper model size (default: turbo on macOS, medium on Linux)")
    parser.add_argument("--clipboard", "-c", action="store_true",
                        help="Use clipboard paste instead of simulated typing (always on for macOS)")
    parser.add_argument("--cpu", action="store_true",
                        help="Force CPU inference (default: uses CUDA if available)")
    parser.add_argument("--device", "-d", type=int, default=None,
                        help="Audio input device index (see: python -m sounddevice)")
    return parser.parse_args()
