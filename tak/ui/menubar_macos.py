"""TAK macOS menu bar — status item with dropdown menu."""

from __future__ import annotations

import AppKit
import Foundation
import objc


# ─── Programmatic icon drawing ─────────────────────────────────────────

def _make_mic_icon(size: float = 18.0) -> AppKit.NSImage:
    """Draw a microphone template icon for the menu bar."""
    img = AppKit.NSImage.alloc().initWithSize_(Foundation.NSMakeSize(size, size))
    img.lockFocus()

    color = AppKit.NSColor.blackColor()
    color.set()

    # Mic body (rounded rect)
    body = Foundation.NSMakeRect(6, 5, 6, 9)
    body_path = AppKit.NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(
        body, 3, 3
    )
    body_path.setLineWidth_(1.4)
    body_path.stroke()

    # Arc (cup under mic)
    arc = AppKit.NSBezierPath.bezierPath()
    arc.moveToPoint_(Foundation.NSMakePoint(4, 8))
    arc.curveToPoint_controlPoint1_controlPoint2_(
        Foundation.NSMakePoint(14, 8),
        Foundation.NSMakePoint(4, 16),
        Foundation.NSMakePoint(14, 16),
    )
    arc.setLineWidth_(1.4)
    arc.stroke()

    # Stand (vertical line from arc to base)
    stand = AppKit.NSBezierPath.bezierPath()
    stand.moveToPoint_(Foundation.NSMakePoint(9, 8))
    stand.lineToPoint_(Foundation.NSMakePoint(9, 4))
    stand.setLineWidth_(1.4)
    stand.stroke()

    # Base (horizontal line)
    base = AppKit.NSBezierPath.bezierPath()
    base.moveToPoint_(Foundation.NSMakePoint(6, 4))
    base.lineToPoint_(Foundation.NSMakePoint(12, 4))
    base.setLineWidth_(1.4)
    base.stroke()

    img.unlockFocus()
    img.setTemplate_(True)
    return img


def _make_mic_icon_with_dot(
    size: float = 18.0,
    dot_color: AppKit.NSColor = None,
) -> AppKit.NSImage:
    """Draw a microphone icon with a colored status dot (non-template)."""
    img = AppKit.NSImage.alloc().initWithSize_(Foundation.NSMakeSize(size, size))
    img.lockFocus()

    # Draw mic in dark gray (non-template, explicit color)
    gray = AppKit.NSColor.colorWithCalibratedWhite_alpha_(0.2, 1.0)
    gray.set()

    body = Foundation.NSMakeRect(6, 5, 6, 9)
    body_path = AppKit.NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(
        body, 3, 3
    )
    body_path.setLineWidth_(1.4)
    body_path.stroke()

    arc = AppKit.NSBezierPath.bezierPath()
    arc.moveToPoint_(Foundation.NSMakePoint(4, 8))
    arc.curveToPoint_controlPoint1_controlPoint2_(
        Foundation.NSMakePoint(14, 8),
        Foundation.NSMakePoint(4, 16),
        Foundation.NSMakePoint(14, 16),
    )
    arc.setLineWidth_(1.4)
    arc.stroke()

    stand = AppKit.NSBezierPath.bezierPath()
    stand.moveToPoint_(Foundation.NSMakePoint(9, 8))
    stand.lineToPoint_(Foundation.NSMakePoint(9, 4))
    stand.setLineWidth_(1.4)
    stand.stroke()

    base = AppKit.NSBezierPath.bezierPath()
    base.moveToPoint_(Foundation.NSMakePoint(6, 4))
    base.lineToPoint_(Foundation.NSMakePoint(12, 4))
    base.setLineWidth_(1.4)
    base.stroke()

    # Status dot (top-right corner)
    if dot_color:
        dot_color.set()
        dot_rect = Foundation.NSMakeRect(12, 12, 5, 5)
        dot_path = AppKit.NSBezierPath.bezierPathWithOvalInRect_(dot_rect)
        dot_path.fill()

    img.unlockFocus()
    img.setTemplate_(False)
    return img


_RED = AppKit.NSColor.colorWithCalibratedRed_green_blue_alpha_(0.9, 0.2, 0.2, 1.0)
_YELLOW = AppKit.NSColor.colorWithCalibratedRed_green_blue_alpha_(0.85, 0.65, 0.1, 1.0)
_ORANGE = AppKit.NSColor.colorWithCalibratedRed_green_blue_alpha_(1.0, 0.6, 0.0, 1.0)


# ─── Menu bar controller ───────────────────────────────────────────────

class MacMenuBar(AppKit.NSObject):
    """macOS menu bar status item with state-driven icon and dropdown menu."""

    def init(self):
        self = objc.super(MacMenuBar, self).init()
        if self is None:
            return None
        self._setup()
        return self

    def _setup(self):
        # Ensure NSApplication exists before creating status bar items —
        # NSStatusBar requires an active window server connection.
        ns_app = AppKit.NSApplication.sharedApplication()
        ns_app.setActivationPolicy_(AppKit.NSApplicationActivationPolicyAccessory)

        self._status_item = AppKit.NSStatusBar.systemStatusBar().statusItemWithLength_(
            AppKit.NSVariableStatusItemLength
        )

        # Use drawn template icon (adapts to light/dark menu bar automatically)
        self._icon_idle = _make_mic_icon()
        self._icon_recording = _make_mic_icon_with_dot(dot_color=_RED)
        self._icon_transcribing = _make_mic_icon_with_dot(dot_color=_YELLOW)

        button = self._status_item.button()
        button.setImage_(self._icon_idle)
        button.setTitle_("")  # image-only; title empty but present
        button.setImagePosition_(AppKit.NSImageOnly)
        button.setToolTip_("TAK — Talk to Keyboard")
        self._status_item.setVisible_(True)

        self._settings_window = None
        self._build_menu()

    def _build_menu(self):
        menu = AppKit.NSMenu.alloc().init()

        # Status label (disabled, just informational)
        self._status_label = AppKit.NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "Idle", None, ""
        )
        self._status_label.setEnabled_(False)
        menu.addItem_(self._status_label)

        menu.addItem_(AppKit.NSMenuItem.separatorItem())

        # Preferences
        prefs_item = AppKit.NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "Preferences\u2026", "openSettings:", ","
        )
        prefs_item.setTarget_(self)
        menu.addItem_(prefs_item)

        menu.addItem_(AppKit.NSMenuItem.separatorItem())

        # Uninstall
        uninstall_item = AppKit.NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "Uninstall TAK\u2026", "uninstallApp:", ""
        )
        uninstall_item.setTarget_(self)
        menu.addItem_(uninstall_item)

        # Quit
        quit_item = AppKit.NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "Quit TAK", "quitApp:", "q"
        )
        quit_item.setTarget_(self)
        menu.addItem_(quit_item)

        self._status_item.setMenu_(menu)

    # ── Accessibility state ─────────────────────────────────────────

    def set_needs_accessibility(self) -> None:
        """Show that accessibility permission is required."""
        self._icon_warning = _make_mic_icon_with_dot(dot_color=_ORANGE)

        def _inner():
            self._status_item.button().setImage_(self._icon_warning)
            self._status_label.setTitle_("Accessibility Required")

            # Insert "Grant Accessibility…" item after the status label
            if not hasattr(self, "_accessibility_item"):
                menu = self._status_item.menu()
                self._accessibility_item = AppKit.NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                    "Grant Accessibility\u2026", "openAccessibility:", ""
                )
                self._accessibility_item.setTarget_(self)
                menu.insertItem_atIndex_(self._accessibility_item, 1)

        if AppKit.NSThread.isMainThread():
            _inner()
        else:
            AppKit.NSOperationQueue.mainQueue().addOperationWithBlock_(_inner)

    def clear_needs_accessibility(self) -> None:
        """Remove the accessibility warning and restore idle state."""
        def _inner():
            if hasattr(self, "_accessibility_item"):
                self._status_item.menu().removeItem_(self._accessibility_item)
                del self._accessibility_item
            self.set_idle()

        if AppKit.NSThread.isMainThread():
            _inner()
        else:
            AppKit.NSOperationQueue.mainQueue().addOperationWithBlock_(_inner)

    # ── Menu actions ────────────────────────────────────────────────

    @objc.typedSelector(b"v@:@")
    def openAccessibility_(self, sender):
        import subprocess
        subprocess.Popen([
            "open", "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility"
        ])

    @objc.typedSelector(b"v@:@")
    def openSettings_(self, sender):
        if self._settings_window is None:
            from tak.ui.settings_macos import SettingsWindow
            self._settings_window = SettingsWindow.alloc().init()
        self._settings_window.show()

    @objc.typedSelector(b"v@:@")
    def uninstallApp_(self, sender):
        alert = AppKit.NSAlert.alloc().init()
        alert.setMessageText_("Uninstall TAK?")
        alert.setInformativeText_(
            "This will remove:\n"
            "\u2022 TAK.app\n"
            "\u2022 Saved preferences\n"
            "\u2022 Log files\n"
            "\u2022 Downloaded Whisper models\n"
            "\u2022 Microphone & Accessibility permissions\n\n"
            "This cannot be undone."
        )
        alert.setAlertStyle_(AppKit.NSAlertStyleCritical)
        alert.addButtonWithTitle_("Uninstall")
        alert.addButtonWithTitle_("Cancel")

        # Style the Uninstall button as destructive
        alert.buttons()[0].setHasDestructiveAction_(True)

        AppKit.NSApp.activateIgnoringOtherApps_(True)
        response = alert.runModal()
        if response == AppKit.NSAlertFirstButtonReturn:
            self._perform_uninstall()

    def _perform_uninstall(self):
        import os
        import shutil
        import subprocess

        bundle_path = Foundation.NSBundle.mainBundle().bundlePath()
        bundle_id = Foundation.NSBundle.mainBundle().bundleIdentifier() or "com.tak.app"

        # 1. Clear NSUserDefaults
        AppKit.NSUserDefaults.standardUserDefaults().removePersistentDomainForName_(bundle_id)

        # 2. Remove log directory
        log_dir = os.path.expanduser("~/Library/Logs/TAK")
        if os.path.isdir(log_dir):
            shutil.rmtree(log_dir, ignore_errors=True)

        # 3. Remove cached Whisper models
        hf_cache = os.path.expanduser("~/.cache/huggingface/hub")
        if os.path.isdir(hf_cache):
            for entry in os.listdir(hf_cache):
                if entry.startswith("models--mlx-community--whisper"):
                    shutil.rmtree(os.path.join(hf_cache, entry), ignore_errors=True)

        # 4. Reset macOS permissions
        subprocess.run(["tccutil", "reset", "Microphone", bundle_id],
                       capture_output=True)
        subprocess.run(["tccutil", "reset", "Accessibility", bundle_id],
                       capture_output=True)

        # 5. Move app to Trash (works even while running — macOS allows it)
        if bundle_path.endswith(".app"):
            workspace = AppKit.NSWorkspace.sharedWorkspace()
            url = Foundation.NSURL.fileURLWithPath_(bundle_path)
            workspace.recycleURLs_completionHandler_([url], None)

        # 6. Quit
        AppKit.NSApp.terminate_(None)

    @objc.typedSelector(b"v@:@")
    def quitApp_(self, sender):
        from tak.ui.overlay_macos import stop_app_loop
        stop_app_loop()

    # ── State updates (thread-safe) ─────────────────────────────────

    def _update_on_main(self, icon: AppKit.NSImage, label: str):
        def _inner():
            self._status_item.button().setImage_(icon)
            self._status_label.setTitle_(label)

        if AppKit.NSThread.isMainThread():
            _inner()
        else:
            AppKit.NSOperationQueue.mainQueue().addOperationWithBlock_(_inner)

    def set_recording(self) -> None:
        self._update_on_main(self._icon_recording, "Recording\u2026")

    def set_transcribing(self) -> None:
        self._update_on_main(self._icon_transcribing, "Transcribing\u2026")

    def set_idle(self) -> None:
        self._update_on_main(self._icon_idle, "Idle")
