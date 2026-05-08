"""TAK design system — shared visual tokens and helpers for macOS UI."""

from __future__ import annotations

import AppKit


# ─── Color helper ─────────────────────────────────────────────────────

def rgb(r, g, b, a=1.0):
    """Create NSColor from 0-255 RGB values."""
    return AppKit.NSColor.colorWithSRGBRed_green_blue_alpha_(
        r / 255, g / 255, b / 255, a
    )


# ─── Design tokens (mirrored from website/styles.css) ─────────────────

BG       = rgb(6, 8, 13)             # --bg:        #06080d
BG_CARD  = rgb(13, 17, 23)           # --bg-card:   #0d1117
BG_CARD2 = rgb(22, 27, 34)           # --bg-card-2: #161b22
BORDER   = rgb(33, 38, 45)           # --border:    #21262d
BORDER2  = rgb(48, 54, 61)           # --border-2:  #30363d
TEXT     = rgb(230, 237, 243)         # --text:      #e6edf3
TEXT_DIM = rgb(139, 148, 158)         # --text-dim:  #8b949e
ACCENT   = rgb(88, 166, 255)         # --accent:    #58a6ff
PURPLE   = rgb(188, 140, 255)        # --purple:    #bc8cff
PINK     = rgb(247, 120, 186)        # --pink:      #f778ba
GREEN    = rgb(63, 185, 80)           # --green:     #3fb950

RADIUS = 12.0


# ─── Shared views ─────────────────────────────────────────────────────

class CardView(AppKit.NSView):
    """Rounded card background with subtle border."""

    def drawRect_(self, rect):
        b = self.bounds()
        path = AppKit.NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(
            b, RADIUS, RADIUS
        )
        BG_CARD.set()
        path.fill()
        rgb(33, 38, 45, 0.6).set()
        path.setLineWidth_(0.5)
        path.stroke()


# ─── Font helpers ─────────────────────────────────────────────────────

def avenir_heavy(size):
    """Avenir-Heavy with bold system fallback."""
    return (
        AppKit.NSFont.fontWithName_size_("Avenir-Heavy", size)
        or AppKit.NSFont.boldSystemFontOfSize_(size)
    )


def avenir_medium(size):
    """Avenir-Medium with system fallback."""
    return (
        AppKit.NSFont.fontWithName_size_("Avenir-Medium", size)
        or AppKit.NSFont.systemFontOfSize_(size)
    )


def mono_font(size):
    """Monospaced system font."""
    return AppKit.NSFont.monospacedSystemFontOfSize_weight_(
        size, AppKit.NSFontWeightRegular
    )


def make_label(text, size, bold=False, color=None, mono=False):
    """Create a non-editable styled NSTextField label."""
    lbl = AppKit.NSTextField.labelWithString_(text)
    if mono:
        font = mono_font(size)
    elif bold:
        font = avenir_heavy(size)
    else:
        font = avenir_medium(size)
    lbl.setFont_(font)
    if color:
        lbl.setTextColor_(color)
    lbl.setBezeled_(False)
    lbl.setDrawsBackground_(False)
    lbl.setEditable_(False)
    lbl.setSelectable_(False)
    return lbl
