"""TAK GUI entry point — macOS .app bundle launcher.

This replaces CLI argument parsing with NSUserDefaults-backed config.
Used by py2app as the main script for TAK.app.
"""

from __future__ import annotations

import logging
import multiprocessing
import os
import platform
import sys


def _setup_logging():
    """Configure logging to ~/Library/Logs/TAK/tak.log.

    Also redirects stdout/stderr so print-based output from TakApp
    (status messages, errors) is captured instead of lost in .app bundles.
    """
    log_dir = os.path.expanduser("~/Library/Logs/TAK")
    os.makedirs(log_dir, exist_ok=True)
    log_path = os.path.join(log_dir, "tak.log")
    logging.basicConfig(
        filename=log_path,
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    # Redirect stdout/stderr to log file so print() output is captured
    log_file = open(log_path, "a")
    sys.stdout = log_file
    sys.stderr = log_file


def main():
    multiprocessing.freeze_support()

    if platform.system() != "Darwin":
        raise SystemExit("TAK.app is macOS only")

    _setup_logging()
    logging.info("TAK starting")

    # Ensure Homebrew bin dirs are in PATH — Finder-launched .app bundles
    # only get /usr/bin:/bin:/usr/sbin:/sbin, missing ffmpeg and other tools.
    for brew_path in ("/opt/homebrew/bin", "/usr/local/bin"):
        if brew_path not in os.environ.get("PATH", ""):
            os.environ["PATH"] = brew_path + ":" + os.environ.get("PATH", "")

    logging.info("Importing modules...")
    from tak.platforms import macos as backend
    from tak.ui.overlay_macos import MacOverlay, run_app_loop
    from tak.ui.menubar_macos import MacMenuBar
    from tak.ui.settings_macos import load_config
    from tak.app import TakApp, KEY_MAP
    logging.info("Imports done")

    # Load config from NSUserDefaults
    config = load_config()
    logging.info("Config loaded: key=%s model=%s", config.trigger_key, config.model)

    # Prompt for Accessibility permission if not yet granted.
    # AXIsProcessTrustedWithOptions with kAXTrustedCheckOptionPrompt shows
    # a system alert directing the user to System Settings > Accessibility.
    import ApplicationServices
    from Foundation import NSDictionary
    opts = NSDictionary.dictionaryWithObject_forKey_(True, "AXTrustedCheckOptionPrompt")
    if not ApplicationServices.AXIsProcessTrustedWithOptions(opts):
        logging.warning("Accessibility permission not yet granted — user was prompted")

    backend.adjust_key_map()
    logging.info("Platform setup done")

    # Resolve trigger key
    trigger_key = KEY_MAP.get(config.trigger_key)
    if trigger_key is None:
        logging.warning("Unknown key '%s', falling back to alt_r", config.trigger_key)
        trigger_key = KEY_MAP.get("alt_r")

    # Build backends
    logging.info("Building audio recorder...")
    recorder = backend.MacAudioRecorder(device=config.audio_device)
    logging.info("Building transcriber...")
    transcriber = backend.MacTranscriber(config.model)
    logging.info("Backends ready")

    # Build UI (MacMenuBar initializes NSApplication internally)
    overlay = MacOverlay()
    menubar = MacMenuBar.alloc().init()
    logging.info("UI built — menu bar + overlay")

    def _combine(*fns):
        def _call():
            for fn in fns:
                fn()
        return _call

    # Build and run app
    app = TakApp(
        trigger_key=trigger_key,
        recorder=recorder,
        transcriber=transcriber,
        type_fn=backend.type_text,
        clipboard_fn=backend.type_text_clipboard,
        use_clipboard=config.use_clipboard,
        platform_label=backend.get_platform_label(),
        on_recording=_combine(overlay.show_recording, menubar.set_recording),
        on_transcribing=_combine(overlay.show_transcribing, menubar.set_transcribing),
        on_idle=_combine(overlay.hide, menubar.set_idle),
    )

    logging.info("TAK ready — trigger=%s model=%s", config.trigger_key, config.model)
    app.run(main_loop=run_app_loop)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import logging
        import traceback
        logging.error("TAK crashed:\n%s", traceback.format_exc())
