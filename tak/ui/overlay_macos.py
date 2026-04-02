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


# ─── Overlay controller ────────────────────────────────────────────────
class MacOverlay(BaseOverlay):
    """Floating pill overlay for recording/transcribing state."""

    def __init__(self):
        self._panel = None
        self._pill = None
        self._built = False

    def _build(self):
        """Build the NSPanel and pill view. Must be called on the main thread."""
        if self._built:
            return

        screen = AppKit.NSScreen.mainScreen()
        screen_frame = screen.visibleFrame()

        pill_w, pill_h = 70, 26
        x = screen_frame.origin.x + (screen_frame.size.width - pill_w) / 2
        y = screen_frame.origin.y + screen_frame.size.height - pill_h - 8

        panel_rect = Foundation.NSMakeRect(x, y, pill_w, pill_h)

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
            Foundation.NSMakeRect(0, 0, pill_w, pill_h)
        )
        panel.contentView().addSubview_(pill)

        self._panel = panel
        self._pill = pill
        self._built = True

    def _dispatch(self, block):
        """Run block on the main thread."""
        AppKit.NSApp.performSelectorOnMainThread_withObject_waitUntilDone_(
            Foundation.NSSelectorFromString("performBlock:"), block, False
        )

    def _do_show(self, color, label):
        """Show the overlay with given color and label. Thread-safe."""
        def _inner():
            self._build()
            self._pill.setFillColor_(color)
            self._pill.setLabel_(label)
            self._panel.orderFront_(None)

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
            if self._panel:
                self._panel.orderOut_(None)

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
