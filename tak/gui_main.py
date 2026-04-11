"""TAK GUI entry point — macOS .app bundle launcher.

This replaces CLI argument parsing with NSUserDefaults-backed config.
Used by PyInstaller (TAK.spec) as the main script for TAK.app.
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
    # the system dialog directing the user to System Settings > Accessibility.
    # The app continues launching regardless — pynput silently ignores key
    # events until the permission is granted (no restart needed).
    import ApplicationServices
    from Foundation import NSDictionary
    opts = NSDictionary.dictionaryWithObject_forKey_(True, "AXTrustedCheckOptionPrompt")
    _needs_accessibility = not ApplicationServices.AXIsProcessTrustedWithOptions(opts)
    if _needs_accessibility:
        logging.info("Accessibility permission not yet granted — system prompt shown, continuing launch")

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

    # ── Model download + loading with splash overlay ──────────────────
    import threading
    import AppKit
    import Foundation

    ns_app = AppKit.NSApplication.sharedApplication()
    ns_app.setActivationPolicy_(AppKit.NSApplicationActivationPolicyAccessory)

    from tak.ui.splash_macos import DownloadSplash, is_model_cached, download_model

    model_repo = backend.MLX_MODELS.get(config.model, config.model)
    splash = DownloadSplash()

    def _run_bg(fn):
        """Run fn in a background thread, pumping NSRunLoop for UI updates."""
        box, err, done = [None], [None], threading.Event()
        def _work():
            try:
                box[0] = fn()
            except Exception as exc:
                err[0] = exc
            finally:
                done.set()
        t = threading.Thread(target=_work, daemon=True)
        t.start()
        rl = Foundation.NSRunLoop.currentRunLoop()
        while not done.is_set():
            rl.runMode_beforeDate_(
                Foundation.NSDefaultRunLoopMode,
                Foundation.NSDate.dateWithTimeIntervalSinceNow_(0.05),
            )
        t.join()
        if err[0]:
            raise err[0]
        return box[0]

    if not is_model_cached(model_repo):
        logging.info("Model not cached — downloading %s", model_repo)
        splash.show_download(model_repo)
        try:
            _run_bg(lambda: download_model(model_repo, splash))
        except Exception as exc:
            logging.error("Download failed: %s", exc)
            splash.hide()
            alert = AppKit.NSAlert.alloc().init()
            alert.setMessageText_("Model Download Failed")
            alert.setInformativeText_(
                f"Could not download the speech model.\n\n{exc}\n\n"
                "Check your internet connection and try again."
            )
            alert.addButtonWithTitle_("Quit")
            ns_app.activateIgnoringOtherApps_(True)
            alert.runModal()
            sys.exit(1)

    logging.info("Loading model %s...", config.model)
    splash.show_loading(model_repo)
    transcriber = _run_bg(lambda: backend.MacTranscriber(config.model))
    splash.hide()
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

    # Accessibility gate — checked on each trigger key press.
    # Once confirmed, remembers for the rest of the session.
    _accessibility_confirmed = not _needs_accessibility
    _showing_alert = False

    def _check_accessibility() -> bool:
        nonlocal _accessibility_confirmed, _showing_alert
        if _accessibility_confirmed:
            return True
        if ApplicationServices.AXIsProcessTrusted():
            _accessibility_confirmed = True
            logging.info("Accessibility permission confirmed for session")
            menubar.clear_needs_accessibility()
            return True
        # Not granted — show confirmation dialog on the main thread.
        # Guard against re-entrant alerts (user holds key while dialog is up).
        if _showing_alert:
            return False
        _showing_alert = True
        logging.info("Accessibility not granted on key press — showing dialog")

        def _show_alert():
            nonlocal _showing_alert
            ns_app.activateIgnoringOtherApps_(True)
            alert = AppKit.NSAlert.alloc().init()
            alert.setMessageText_("Accessibility Permission Required")
            alert.setInformativeText_(
                "TAK needs Accessibility permission to detect your "
                "push-to-talk key and paste transcribed text.\n\n"
                "Please enable TAK in System Settings \u2192 Privacy & Security "
                "\u2192 Accessibility."
            )
            alert.addButtonWithTitle_("Open System Settings")
            alert.addButtonWithTitle_("Cancel")
            response = alert.runModal()
            if response == AppKit.NSAlertFirstButtonReturn:
                import subprocess
                subprocess.Popen([
                    "open",
                    "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility",
                ])
            _showing_alert = False

        AppKit.NSOperationQueue.mainQueue().addOperationWithBlock_(_show_alert)
        return False

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
        accessibility_check=_check_accessibility if _needs_accessibility else None,
    )

    if _needs_accessibility:
        menubar.set_needs_accessibility()

    logging.info("TAK ready — trigger=%s model=%s", config.trigger_key, config.model)
    app.run(main_loop=run_app_loop)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import logging
        import traceback
        logging.error("TAK crashed:\n%s", traceback.format_exc())
