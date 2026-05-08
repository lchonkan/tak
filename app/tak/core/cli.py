"""CLI argument parser for `python -m tak`."""

from __future__ import annotations

import argparse


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
