"""TAK macOS overlay — floating recording indicator using PyObjC."""

from __future__ import annotations

import objc

from tak.ui import BaseOverlay

import AppKit
import Foundation


# ─── Pill-shaped overlay view ───────────────────────────────────────────
class _PillView(AppKit.NSView):
    """Custom view that draws a colored rounded pill with a label."""

    def initWithFrame_(self, frame):
        self = objc.super(_PillView, self).initWithFrame_(frame)
        if self is None:
            return None
        self._fill_color = AppKit.NSColor.redColor()
        self._label = "REC"
        return self

    def setFillColor_(self, color):
        self._fill_color = color
        self.setNeedsDisplay_(True)

    def setLabel_(self, label):
        self._label = label
        self.setNeedsDisplay_(True)

    def drawRect_(self, rect):
        path = AppKit.NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(
            self.bounds(), 12, 12
        )
        self._fill_color.set()
        path.fill()

        attrs = {
            AppKit.NSFontAttributeName: AppKit.NSFont.boldSystemFontOfSize_(11),
            AppKit.NSForegroundColorAttributeName: AppKit.NSColor.whiteColor(),
        }
        text = Foundation.NSAttributedString.alloc().initWithString_attributes_(
            self._label, attrs
        )
        text_size = text.size()
        text_rect = Foundation.NSMakeRect(
            (self.bounds().size.width - text_size.width) / 2,
            (self.bounds().size.height - text_size.height) / 2,
            text_size.width,
            text_size.height,
        )
        text.drawInRect_(text_rect)


# ─── Colors ─────────────────────────────────────────────────────────────
_RED = AppKit.NSColor.colorWithCalibratedRed_green_blue_alpha_(0.9, 0.2, 0.2, 0.92)
_YELLOW = AppKit.NSColor.colorWithCalibratedRed_green_blue_alpha_(0.85, 0.65, 0.1, 0.92)

_PILL_W, _PILL_H = 70, 26
_MARGIN_BOTTOM = 10  # gap from bottom of screen


# ─── Per-screen panel builder ───────────────────────────────────────────
def _make_panel():
    """Create a single floating pill panel (not yet positioned)."""
    panel_rect = Foundation.NSMakeRect(0, 0, _PILL_W, _PILL_H)

    panel = AppKit.NSPanel.alloc().initWithContentRect_styleMask_backing_defer_(
        panel_rect,
        AppKit.NSWindowStyleMaskBorderless | AppKit.NSWindowStyleMaskNonactivatingPanel,
        AppKit.NSBackingStoreBuffered,
        False,
    )
    panel.setLevel_(AppKit.NSStatusWindowLevel)
    panel.setOpaque_(False)
    panel.setBackgroundColor_(AppKit.NSColor.clearColor())
    panel.setIgnoresMouseEvents_(True)
    panel.setHasShadow_(True)
    panel.setCollectionBehavior_(
        AppKit.NSWindowCollectionBehaviorCanJoinAllSpaces
        | AppKit.NSWindowCollectionBehaviorStationary
        | AppKit.NSWindowCollectionBehaviorFullScreenAuxiliary
    )

    pill = _PillView.alloc().initWithFrame_(
        Foundation.NSMakeRect(0, 0, _PILL_W, _PILL_H)
    )
    panel.contentView().addSubview_(pill)

    return panel, pill


def _center_bottom(screen):
    """Return (x, y) to place a pill centered at the bottom of a screen."""
    frame = screen.visibleFrame()
    x = frame.origin.x + (frame.size.width - _PILL_W) / 2
    y = frame.origin.y + _MARGIN_BOTTOM
    return (x, y)


# ─── Overlay controller ────────────────────────────────────────────────
class MacOverlay(BaseOverlay):
    """Floating pill overlay on every screen, centered at the bottom."""

    def __init__(self):
        self._panels = []  # list of (panel, pill) tuples

    def _sync_screens(self):
        """Ensure one panel per screen, creating/removing as needed.

        Must be called on the main thread.
        """
        screens = AppKit.NSScreen.screens()
        current_count = len(self._panels)
        needed = len(screens)

        # Add panels for new screens
        while len(self._panels) < needed:
            self._panels.append(_make_panel())

        # Remove extra panels
        while len(self._panels) > needed:
            panel, _ = self._panels.pop()
            panel.orderOut_(None)

        # Position each panel at center-bottom of its screen
        for (panel, _), screen in zip(self._panels, screens):
            x, y = _center_bottom(screen)
            panel.setFrameOrigin_(Foundation.NSMakePoint(x, y))

    def _do_show(self, color, label):
        """Show overlays on all screens. Thread-safe."""
        def _inner():
            self._sync_screens()
            for panel, pill in self._panels:
                pill.setFillColor_(color)
                pill.setLabel_(label)
                panel.orderFront_(None)

        if AppKit.NSThread.isMainThread():
            _inner()
        else:
            AppKit.NSOperationQueue.mainQueue().addOperationWithBlock_(_inner)

    def show_recording(self) -> None:
        self._do_show(_RED, "REC")

    def show_transcribing(self) -> None:
        self._do_show(_YELLOW, "...")

    def hide(self) -> None:
        def _inner():
            for panel, _ in self._panels:
                panel.orderOut_(None)

        if AppKit.NSThread.isMainThread():
            _inner()
        else:
            AppKit.NSOperationQueue.mainQueue().addOperationWithBlock_(_inner)


# ─── NSApplication run loop ─────────────────────────────────────────────
def run_app_loop():
    """Start the macOS NSApplication run loop on the main thread.

    This blocks until the app is terminated (Ctrl+C or app quit).
    Must be called from the main thread.
    """
    app = AppKit.NSApplication.sharedApplication()
    app.setActivationPolicy_(AppKit.NSApplicationActivationPolicyAccessory)
    app.run()


def stop_app_loop():
    """Stop the NSApplication run loop."""
    AppKit.NSApp.stop_(None)
    # Post a dummy event to unblock the run loop
    event = AppKit.NSEvent.otherEventWithType_location_modifierFlags_timestamp_windowNumber_context_subtype_data1_data2_(
        AppKit.NSEventTypeApplicationDefined,
        Foundation.NSMakePoint(0, 0),
        0, 0, 0, None, 0, 0, 0,
    )
    AppKit.NSApp.postEvent_atStart_(event, True)
