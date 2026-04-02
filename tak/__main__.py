#!/usr/bin/env python3
"""
TAK — Talk to Keyboard
Push-to-talk speech-to-text that types anywhere.

Cross-platform: Linux (X11) and macOS.

Usage:
    python -m tak                  # default: hold Right-Ctrl to talk
    python -m tak --key scroll_lock
    python -m tak --model large-v3
"""

from __future__ import annotations

import platform
import sys


def main():
    from tak.app import parse_args, KEY_MAP, error, warn

    args = parse_args()

    IS_MACOS = platform.system() == "Darwin"
    IS_LINUX = platform.system() == "Linux"

    # ── Import platform backend ──────────────────────────────────
    if IS_MACOS:
        from tak.platforms import macos as backend
    elif IS_LINUX:
        from tak.platforms import linux as backend
    else:
        error(f"Unsupported platform: {platform.system()}")
        sys.exit(1)

    # ── Platform-specific initialization ─────────────────────────
    backend.platform_setup()

    # ── Resolve trigger key ──────────────────────────────────────
    key_name = args.key if args.key != "ctrl_r" or not IS_MACOS else "alt_r"
    trigger_key = KEY_MAP.get(key_name)
    if trigger_key is None:
        error(f"Unknown key '{key_name}'. Available: {', '.join(KEY_MAP.keys())}")
        sys.exit(1)

    # ── Resolve model ────────────────────────────────────────────
    model_size = args.model if args.model else backend.get_default_model()

    # ── Build backends ───────────────────────────────────────────
    if IS_MACOS:
        if args.cpu:
            warn("--cpu flag ignored on macOS (MLX auto-selects best device)")
        recorder = backend.MacAudioRecorder(device=args.device)
        transcriber = backend.MacTranscriber(model_size)
    else:
        recorder = backend.LinuxAudioRecorder(device=args.device)
        device = "cpu" if args.cpu else "cuda"
        compute_type = "int8" if args.cpu else "float16"
        transcriber = backend.LinuxTranscriber(model_size, device=device, compute_type=compute_type)

    # ── Build and run app ────────────────────────────────────────
    from tak.app import TakApp

    app = TakApp(
        trigger_key=trigger_key,
        recorder=recorder,
        transcriber=transcriber,
        type_fn=backend.type_text,
        clipboard_fn=backend.type_text_clipboard,
        use_clipboard=args.clipboard or IS_MACOS,
        platform_label=backend.get_platform_label(),
    )
    app.run()


if __name__ == "__main__":
    main()
