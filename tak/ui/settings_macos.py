"""TAK macOS settings — preferences window and NSUserDefaults persistence."""

from __future__ import annotations

import threading
from typing import Optional

import objc

import AppKit
import Foundation

from tak.config import TakConfig
from tak.ui.design import (
    rgb, BG_CARD, TEXT, TEXT_DIM, ACCENT, GREEN, PINK,
    RADIUS, CardView, avenir_heavy, avenir_medium, make_label,
)
from tak.ui.splash_macos import BarView, is_model_cached, download_model


# ─── NSUserDefaults keys ────────────────────────────────────────────────

_DEFAULTS_PREFIX = "tak_"
_KEY_TRIGGER = f"{_DEFAULTS_PREFIX}trigger_key"
_KEY_MODEL = f"{_DEFAULTS_PREFIX}model"
_KEY_CLIPBOARD = f"{_DEFAULTS_PREFIX}use_clipboard"
_KEY_DEVICE = f"{_DEFAULTS_PREFIX}audio_device"

_REGISTERED = False


def _register_defaults():
    global _REGISTERED
    if _REGISTERED:
        return
    AppKit.NSUserDefaults.standardUserDefaults().registerDefaults_({
        _KEY_TRIGGER: "alt_r",
        _KEY_MODEL: "turbo",
        _KEY_CLIPBOARD: True,
        _KEY_DEVICE: -1,  # -1 = system default
    })
    _REGISTERED = True


def load_config() -> TakConfig:
    _register_defaults()
    defaults = AppKit.NSUserDefaults.standardUserDefaults()
    device_val = int(defaults.integerForKey_(_KEY_DEVICE))
    model = str(defaults.stringForKey_(_KEY_MODEL) or "turbo")
    if model in _DEPRECATED_MODELS:
        model = "small"
        defaults.setObject_forKey_(model, _KEY_MODEL)
    return TakConfig(
        trigger_key=str(defaults.stringForKey_(_KEY_TRIGGER) or "alt_r"),
        model=model,
        use_clipboard=bool(defaults.boolForKey_(_KEY_CLIPBOARD)),
        audio_device=None if device_val < 0 else device_val,
    )


def save_config(config: TakConfig) -> None:
    _register_defaults()
    defaults = AppKit.NSUserDefaults.standardUserDefaults()
    defaults.setObject_forKey_(config.trigger_key, _KEY_TRIGGER)
    defaults.setObject_forKey_(config.model, _KEY_MODEL)
    defaults.setBool_forKey_(config.use_clipboard, _KEY_CLIPBOARD)
    defaults.setInteger_forKey_(
        config.audio_device if config.audio_device is not None else -1,
        _KEY_DEVICE,
    )


# ─── Trigger key options ──────────────────────────────────────────────

_TRIGGER_KEYS = [
    ("alt_r",   "Right Option (\u2325)"),
    ("shift_r", "Right Shift (\u21e7)"),
    ("cmd_r",   "Right Command (\u2318)"),
]

_TRIGGER_KEY_IDS = [k for k, _ in _TRIGGER_KEYS]
_TRIGGER_KEY_LABELS = [v for _, v in _TRIGGER_KEYS]


# ─── Model display names ───────────────────────────────────────────────

_MODEL_INFO = {
    "small":    "small (~460 MB)",
    "medium":   "medium (~1.5 GB)",
    "large-v3": "large-v3 (~3 GB, most accurate)",
    "turbo":    "turbo (~2 GB, fast + accurate)",
}

# MLX Hub repo IDs (mirrors tak.platforms.macos.MLX_MODELS)
_MLX_MODELS = {
    "small":    "mlx-community/whisper-small-mlx",
    "medium":   "mlx-community/whisper-medium-mlx-fp32",
    "large-v3": "mlx-community/whisper-large-v3-mlx",
    "turbo":    "mlx-community/whisper-large-v3-turbo",
}

_DEPRECATED_MODELS = {"tiny", "base"}


# ─── Model recommendation data ────────────────────────────────────────

_MODEL_RECS = [
    ("8 GB RAM (any chip)",     "small"),
    ("16 GB RAM (M1 / M2)",     "turbo"),
    ("16 GB+ RAM (M3 / M4)",    "turbo"),
    ("24 GB+ RAM (Pro / Max)",  "large-v3"),
]

_LANG_TIP = "For Spanish or other non-English languages, prefer medium or larger for better accuracy."


# ─── Info tooltip panel ───────────────────────────────────────────────

_TIP_W, _TIP_H = 300, 220
_TIP_PAD = 16


class _TooltipCard(AppKit.NSView):
    """Rounded semi-transparent card for the tooltip panel."""

    def drawRect_(self, rect):
        b = self.bounds()
        path = AppKit.NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(
            b, RADIUS, RADIUS
        )
        rgb(13, 17, 23, 0.95).set()
        path.fill()
        rgb(33, 38, 45, 0.6).set()
        path.setLineWidth_(0.5)
        path.stroke()


class _InfoTooltipPanel:
    """Floating info panel showing model recommendations."""

    def __init__(self):
        self._panel: Optional[AppKit.NSPanel] = None
        self._global_monitor = None
        self._local_monitor = None

    def toggle(self, anchor_button, parent_window):
        if self._panel and self._panel.isVisible():
            self.dismiss()
            return
        self._build()
        self._position_near(anchor_button, parent_window)
        self._panel.orderFront_(None)
        self._install_click_monitors()

    def dismiss(self):
        if self._panel:
            self._panel.orderOut_(None)
        self._remove_monitors()

    def _build(self):
        self._panel = AppKit.NSPanel.alloc().initWithContentRect_styleMask_backing_defer_(
            Foundation.NSMakeRect(0, 0, _TIP_W, _TIP_H),
            AppKit.NSWindowStyleMaskBorderless | AppKit.NSWindowStyleMaskNonactivatingPanel,
            AppKit.NSBackingStoreBuffered,
            False,
        )
        self._panel.setLevel_(AppKit.NSFloatingWindowLevel + 1)
        self._panel.setOpaque_(False)
        self._panel.setBackgroundColor_(AppKit.NSColor.clearColor())
        self._panel.setHasShadow_(True)
        self._panel.setAppearance_(
            AppKit.NSAppearance.appearanceNamed_("NSAppearanceNameDarkAqua")
        )

        card = _TooltipCard.alloc().initWithFrame_(
            Foundation.NSMakeRect(0, 0, _TIP_W, _TIP_H)
        )
        self._panel.contentView().addSubview_(card)

        cw = _TIP_W - 2 * _TIP_PAD
        cy = _TIP_H - _TIP_PAD

        # Title
        cy -= 18
        title = make_label("Choosing a Model", 14, bold=True, color=TEXT)
        title.setFrame_(Foundation.NSMakeRect(_TIP_PAD, cy, cw, 18))
        card.addSubview_(title)
        cy -= 18

        # Table header
        cy -= 14
        hdr_setup = make_label("Setup", 10, color=TEXT_DIM)
        hdr_setup.setFrame_(Foundation.NSMakeRect(_TIP_PAD, cy, 160, 14))
        card.addSubview_(hdr_setup)
        hdr_model = make_label("Model", 10, color=TEXT_DIM)
        hdr_model.setFrame_(Foundation.NSMakeRect(_TIP_PAD + 164, cy, cw - 164, 14))
        card.addSubview_(hdr_model)
        cy -= 6

        # Header separator
        sep = AppKit.NSView.alloc().initWithFrame_(
            Foundation.NSMakeRect(_TIP_PAD, cy, cw, 1)
        )
        sep.setWantsLayer_(True)
        sep.layer().setBackgroundColor_(rgb(33, 38, 45, 0.6).CGColor())
        card.addSubview_(sep)
        cy -= 6

        # Recommendation rows
        for setup_label, model_key in _MODEL_RECS:
            cy -= 18
            setup_lbl = make_label(setup_label, 11, color=TEXT)
            setup_lbl.setFrame_(Foundation.NSMakeRect(_TIP_PAD, cy, 160, 18))
            card.addSubview_(setup_lbl)
            model_lbl = make_label(model_key, 11, bold=True, color=ACCENT)
            model_lbl.setFrame_(Foundation.NSMakeRect(_TIP_PAD + 164, cy, cw - 164, 18))
            card.addSubview_(model_lbl)
            cy -= 2

        # Separator before tip
        cy -= 8
        sep2 = AppKit.NSView.alloc().initWithFrame_(
            Foundation.NSMakeRect(_TIP_PAD, cy, cw, 1)
        )
        sep2.setWantsLayer_(True)
        sep2.layer().setBackgroundColor_(rgb(33, 38, 45, 0.6).CGColor())
        card.addSubview_(sep2)
        cy -= 8

        # Language tip
        tip = AppKit.NSTextField.wrappingLabelWithString_(_LANG_TIP)
        tip.setFont_(avenir_medium(10))
        tip.setTextColor_(PINK)
        tip.setBezeled_(False)
        tip.setDrawsBackground_(False)
        tip.setEditable_(False)
        tip.setSelectable_(False)
        tip.setFrame_(Foundation.NSMakeRect(_TIP_PAD, _TIP_PAD, cw, cy - _TIP_PAD))
        card.addSubview_(tip)

    def _position_near(self, button, parent_window):
        btn_rect = button.convertRect_toView_(button.bounds(), None)
        win_frame = parent_window.frame()
        screen_x = win_frame.origin.x + btn_rect.origin.x
        screen_y = win_frame.origin.y + btn_rect.origin.y - _TIP_H - 4

        screen = AppKit.NSScreen.mainScreen().visibleFrame()
        if screen_x + _TIP_W > screen.origin.x + screen.size.width:
            screen_x = screen.origin.x + screen.size.width - _TIP_W - 8
        if screen_y < screen.origin.y:
            screen_y = win_frame.origin.y + btn_rect.origin.y + btn_rect.size.height + 4

        self._panel.setFrameOrigin_(Foundation.NSMakePoint(screen_x, screen_y))

    def _install_click_monitors(self):
        def _handle_global(event):
            if self._panel and self._panel.isVisible():
                click_loc = AppKit.NSEvent.mouseLocation()
                if not AppKit.NSMouseInRect(click_loc, self._panel.frame(), False):
                    self.dismiss()

        def _handle_local(event):
            if self._panel and self._panel.isVisible():
                click_loc = AppKit.NSEvent.mouseLocation()
                if not AppKit.NSMouseInRect(click_loc, self._panel.frame(), False):
                    self.dismiss()
            return event

        self._global_monitor = AppKit.NSEvent.addGlobalMonitorForEventsMatchingMask_handler_(
            AppKit.NSLeftMouseDownMask, _handle_global
        )
        self._local_monitor = AppKit.NSEvent.addLocalMonitorForEventsMatchingMask_handler_(
            AppKit.NSLeftMouseDownMask, _handle_local
        )

    def _remove_monitors(self):
        if self._global_monitor:
            AppKit.NSEvent.removeMonitor_(self._global_monitor)
            self._global_monitor = None
        if self._local_monitor:
            AppKit.NSEvent.removeMonitor_(self._local_monitor)
            self._local_monitor = None


# ─── Borderless panel that accepts keyboard focus ─────────────────────

class _SettingsPanel(AppKit.NSPanel):
    """NSPanel subclass that can become key for interactive controls."""

    def canBecomeKeyWindow(self):
        return True


# ─── Preferences window ────────────────────────────────────────────────

_W, _H = 420, 420
_PAD = 28


class SettingsWindow(AppKit.NSObject):
    """macOS preferences panel matching the TAK design system."""

    def init(self):
        self = objc.super(SettingsWindow, self).init()
        if self is None:
            return None
        self._panel: Optional[AppKit.NSPanel] = None
        self._downloading = False
        return self

    def _build(self):
        sf = AppKit.NSScreen.mainScreen().frame()
        x = (sf.size.width - _W) / 2
        y = (sf.size.height - _H) / 2

        self._panel = _SettingsPanel.alloc().initWithContentRect_styleMask_backing_defer_(
            Foundation.NSMakeRect(x, y, _W, _H),
            AppKit.NSWindowStyleMaskBorderless,
            AppKit.NSBackingStoreBuffered,
            False,
        )
        self._panel.setLevel_(AppKit.NSFloatingWindowLevel)
        self._panel.setOpaque_(False)
        self._panel.setBackgroundColor_(AppKit.NSColor.clearColor())
        self._panel.setHasShadow_(True)
        self._panel.setMovableByWindowBackground_(True)

        # Dark appearance so native controls (popups, checkboxes) render dark
        self._panel.setAppearance_(
            AppKit.NSAppearance.appearanceNamed_("NSAppearanceNameDarkAqua")
        )

        self._card = CardView.alloc().initWithFrame_(Foundation.NSMakeRect(0, 0, _W, _H))
        self._panel.contentView().addSubview_(self._card)
        card = self._card
        cw = _W - 2 * _PAD

        config = load_config()

        # Layout top-down (AppKit y=0 at bottom)
        cy = _H - _PAD

        # ── Header ─────────────────────────────────────────────────
        cy -= 28
        title = make_label("TAK", 22, bold=True, color=TEXT)
        title.setFrame_(Foundation.NSMakeRect(_PAD, cy, cw - 24, 28))
        card.addSubview_(title)

        # Close button (top-right)
        close_btn = AppKit.NSButton.alloc().initWithFrame_(
            Foundation.NSMakeRect(_W - _PAD - 20, cy + 4, 20, 20)
        )
        close_btn.setBordered_(False)
        close_btn.setAttributedTitle_(
            AppKit.NSAttributedString.alloc().initWithString_attributes_(
                "\u00d7",
                {
                    AppKit.NSFontAttributeName: avenir_medium(18),
                    AppKit.NSForegroundColorAttributeName: TEXT_DIM,
                },
            )
        )
        close_btn.setTarget_(self)
        close_btn.setAction_("closePanel:")
        card.addSubview_(close_btn)
        cy -= 6

        cy -= 18
        subtitle = make_label("Preferences", 13, color=TEXT_DIM)
        subtitle.setFrame_(Foundation.NSMakeRect(_PAD, cy, cw, 18))
        card.addSubview_(subtitle)
        cy -= 24

        # ── Settings ───────────────────────────────────────────────
        label_w = 130
        control_x = _PAD + label_w + 12
        control_w = _W - _PAD - control_x

        # Trigger Key
        cy -= 26
        self._add_row_label(card, "Trigger Key", _PAD, cy, label_w)
        self._key_popup = self._add_popup(card, control_x, cy, control_w)
        for label in _TRIGGER_KEY_LABELS:
            self._key_popup.addItemWithTitle_(label)
        if config.trigger_key in _TRIGGER_KEY_IDS:
            self._key_popup.selectItemAtIndex_(
                _TRIGGER_KEY_IDS.index(config.trigger_key)
            )
        self._key_popup.setTarget_(self)
        self._key_popup.setAction_("onSettingChanged:")
        cy -= 12

        # Whisper Model
        cy -= 26
        info_btn_size = 16
        model_label_w = label_w - info_btn_size - 4
        model_label = make_label("Whisper Model", 13, color=TEXT_DIM)
        model_label.setFrame_(Foundation.NSMakeRect(_PAD, cy, model_label_w, 18))
        model_label.setAlignment_(AppKit.NSTextAlignmentRight)
        card.addSubview_(model_label)

        self._info_btn = AppKit.NSButton.alloc().initWithFrame_(
            Foundation.NSMakeRect(
                _PAD + model_label_w + 4, cy + 1,
                info_btn_size, info_btn_size,
            )
        )
        self._info_btn.setBordered_(False)
        self._info_btn.setWantsLayer_(True)
        self._info_btn.layer().setCornerRadius_(info_btn_size / 2)
        self._info_btn.layer().setBackgroundColor_(rgb(33, 38, 45, 0.8).CGColor())
        self._info_btn.setAttributedTitle_(
            AppKit.NSAttributedString.alloc().initWithString_attributes_(
                "i",
                {
                    AppKit.NSFontAttributeName: AppKit.NSFont.fontWithName_size_(
                        "Avenir-MediumOblique", 9
                    ) or avenir_medium(9),
                    AppKit.NSForegroundColorAttributeName: TEXT_DIM,
                },
            )
        )
        self._info_btn.setTarget_(self)
        self._info_btn.setAction_("onInfoToggle:")
        card.addSubview_(self._info_btn)

        self._info_tooltip = _InfoTooltipPanel()

        self._model_popup = self._add_popup(card, control_x, cy, control_w)
        for key in _MODEL_INFO:
            self._model_popup.addItemWithTitle_(_MODEL_INFO[key])
        current_display = _MODEL_INFO.get(config.model, config.model)
        self._model_popup.selectItemWithTitle_(current_display)
        self._model_popup.setTarget_(self)
        self._model_popup.setAction_("onSettingChanged:")
        cy -= 12

        # Audio Device
        cy -= 26
        self._add_row_label(card, "Audio Device", _PAD, cy, label_w)
        self._device_popup = self._add_popup(card, control_x, cy, control_w)
        self._device_indices: list[Optional[int]] = [None]
        self._device_popup.addItemWithTitle_("System Default")
        try:
            import sounddevice as sd
            devices = sd.query_devices()
            for i, dev in enumerate(devices):
                if dev["max_input_channels"] > 0:
                    self._device_popup.addItemWithTitle_(dev["name"])
                    self._device_indices.append(i)
        except Exception:
            pass
        if config.audio_device is not None:
            try:
                idx = self._device_indices.index(config.audio_device)
                self._device_popup.selectItemAtIndex_(idx)
            except ValueError:
                pass
        self._device_popup.setTarget_(self)
        self._device_popup.setAction_("onSettingChanged:")
        cy -= 12

        # Clipboard
        cy -= 22
        self._clipboard_check = AppKit.NSButton.alloc().initWithFrame_(
            Foundation.NSMakeRect(_PAD, cy, cw, 22)
        )
        self._clipboard_check.setButtonType_(AppKit.NSButtonTypeSwitch)
        self._clipboard_check.setFont_(avenir_medium(13))
        self._clipboard_check.setAttributedTitle_(
            AppKit.NSAttributedString.alloc().initWithString_attributes_(
                "Use clipboard paste (\u2318V)",
                {
                    AppKit.NSFontAttributeName: avenir_medium(13),
                    AppKit.NSForegroundColorAttributeName: TEXT,
                },
            )
        )
        self._clipboard_check.setState_(
            AppKit.NSControlStateValueOn if config.use_clipboard
            else AppKit.NSControlStateValueOff
        )
        self._clipboard_check.setTarget_(self)
        self._clipboard_check.setAction_("onSettingChanged:")
        card.addSubview_(self._clipboard_check)
        cy -= 16

        # ── Download progress section (hidden, overlaps bottom) ───
        # These views occupy the same space as info/separator/donate
        # and are swapped in when a model download is needed.
        self._progress_views: list = []
        cy_p = cy

        cy_p -= 16
        self._dl_status = make_label("", 12, color=TEXT_DIM)
        self._dl_status.setFrame_(Foundation.NSMakeRect(_PAD, cy_p, cw, 16))
        self._dl_status.setHidden_(True)
        card.addSubview_(self._dl_status)
        self._progress_views.append(self._dl_status)
        cy_p -= 2

        cy_p -= 16
        self._dl_model = make_label("", 12, color=ACCENT)
        self._dl_model.setFrame_(Foundation.NSMakeRect(_PAD, cy_p, cw, 16))
        self._dl_model.setHidden_(True)
        card.addSubview_(self._dl_model)
        self._progress_views.append(self._dl_model)
        cy_p -= 10

        cy_p -= 6
        self._dl_bar = BarView.alloc().initWithFrame_(
            Foundation.NSMakeRect(_PAD, cy_p, cw, 6)
        )
        self._dl_bar.setHidden_(True)
        card.addSubview_(self._dl_bar)
        self._progress_views.append(self._dl_bar)
        cy_p -= 8

        cy_p -= 14
        self._dl_stats = make_label("", 10, color=TEXT_DIM, mono=True)
        self._dl_stats.setFrame_(Foundation.NSMakeRect(_PAD, cy_p, cw, 14))
        self._dl_stats.setHidden_(True)
        card.addSubview_(self._dl_stats)
        self._progress_views.append(self._dl_stats)
        cy_p -= 2

        cy_p -= 14
        self._dl_speed = make_label("", 10, color=TEXT_DIM, mono=True)
        self._dl_speed.setFrame_(Foundation.NSMakeRect(_PAD, cy_p, cw, 14))
        self._dl_speed.setHidden_(True)
        card.addSubview_(self._dl_speed)
        self._progress_views.append(self._dl_speed)

        # ── Bottom section (info, separator, donate) ──────────────
        self._bottom_views: list = []

        cy -= 15
        info = make_label("Changes take effect on next launch.", 11, color=TEXT_DIM)
        info.setFrame_(Foundation.NSMakeRect(_PAD, cy, cw, 15))
        card.addSubview_(info)
        self._bottom_views.append(info)
        cy -= 24

        # ── Separator ──────────────────────────────────────────────
        sep_view = AppKit.NSView.alloc().initWithFrame_(
            Foundation.NSMakeRect(_PAD, cy, cw, 1)
        )
        sep_view.setWantsLayer_(True)
        sep_view.layer().setBackgroundColor_(
            rgb(33, 38, 45, 0.6).CGColor()
        )
        card.addSubview_(sep_view)
        self._bottom_views.append(sep_view)
        cy -= 24

        # ── Donate button ─────────────────────────────────────────
        btn_w, btn_h = 120, 28
        cy -= btn_h
        donate = AppKit.NSButton.alloc().initWithFrame_(
            Foundation.NSMakeRect((_W - btn_w) / 2, cy, btn_w, btn_h)
        )
        donate.setBordered_(False)
        donate.setWantsLayer_(True)
        donate.layer().setCornerRadius_(RADIUS / 2)
        donate.layer().setBackgroundColor_(ACCENT.CGColor())
        donate.setAttributedTitle_(
            AppKit.NSAttributedString.alloc().initWithString_attributes_(
                "\u2665  Donate",
                {
                    AppKit.NSFontAttributeName: avenir_medium(13),
                    AppKit.NSForegroundColorAttributeName: rgb(13, 17, 23),
                },
            )
        )
        donate.setTarget_(self)
        donate.setAction_("onDonate:")
        card.addSubview_(donate)
        self._bottom_views.append(donate)

    # ── Helpers ────────────────────────────────────────────────────

    def _add_row_label(self, parent, text, x, y, w):
        label = make_label(text, 13, color=TEXT_DIM)
        label.setFrame_(Foundation.NSMakeRect(x, y, w, 18))
        label.setAlignment_(AppKit.NSTextAlignmentRight)
        parent.addSubview_(label)

    def _add_popup(self, parent, x, y, w):
        popup = AppKit.NSPopUpButton.alloc().initWithFrame_pullsDown_(
            Foundation.NSMakeRect(x, y - 2, w, 26), False
        )
        popup.setFont_(avenir_medium(12))
        parent.addSubview_(popup)
        return popup

    def _on_main(self, fn):
        if AppKit.NSThread.isMainThread():
            fn()
        else:
            AppKit.NSOperationQueue.mainQueue().addOperationWithBlock_(fn)

    def _read_model_key(self) -> str:
        selected = str(self._model_popup.titleOfSelectedItem())
        for key, display in _MODEL_INFO.items():
            if display == selected:
                return key
        return "turbo"

    # ── Download progress ─────────────────────────────────────────

    def _show_download_ui(self, model_repo: str):
        for v in self._bottom_views:
            v.setHidden_(True)
        self._dl_status.setStringValue_("Downloading speech model")
        self._dl_status.setTextColor_(TEXT_DIM)
        self._dl_model.setStringValue_(model_repo)
        self._dl_model.setTextColor_(ACCENT)
        self._dl_bar.setProgress_(0.0)
        self._dl_bar.setFillColor_(ACCENT)
        self._dl_stats.setStringValue_("")
        self._dl_speed.setStringValue_("")
        for v in self._progress_views:
            v.setHidden_(False)
        self._model_popup.setEnabled_(False)

    def _hide_download_ui(self):
        for v in self._progress_views:
            v.setHidden_(True)
        for v in self._bottom_views:
            v.setHidden_(False)
        self._model_popup.setEnabled_(True)
        self._downloading = False

    def update_progress(self, progress, downloaded, total, speed, eta):
        """Called by _DownloadProgress from the download thread."""
        def _do():
            self._dl_bar.setProgress_(progress)
            self._dl_stats.setStringValue_(
                f"{int(progress * 100)}%  \u00b7  {downloaded} / {total}"
            )
            self._dl_speed.setStringValue_(f"{speed}  \u00b7  {eta}")
        self._on_main(_do)

    def _start_download(self, model_key: str, model_repo: str):
        self._downloading = True
        self._show_download_ui(model_repo)

        def _work():
            try:
                download_model(model_repo, self)
                self._on_main(self._download_complete)
            except Exception as exc:
                msg = str(exc)
                self._on_main(lambda: self._download_failed(msg))

        threading.Thread(target=_work, daemon=True).start()

    def _download_complete(self):
        self._dl_status.setStringValue_("Download complete")
        self._dl_status.setTextColor_(GREEN)
        self._dl_bar.setProgress_(1.0)
        self._dl_bar.setFillColor_(GREEN)
        self._dl_stats.setStringValue_("")
        self._dl_speed.setStringValue_("")
        self._downloading = False
        AppKit.NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
            2.0, self, "onHideProgress:", None, False
        )
        self._show_restart_alert()

    def _download_failed(self, message: str):
        self._dl_status.setStringValue_("Download failed")
        self._dl_status.setTextColor_(PINK)
        self._dl_bar.setFillColor_(PINK)
        self._dl_model.setStringValue_(message)
        self._dl_model.setTextColor_(TEXT_DIM)
        self._dl_stats.setStringValue_("")
        self._dl_speed.setStringValue_("")
        AppKit.NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
            3.0, self, "onHideProgress:", None, False
        )

    @objc.typedSelector(b"v@:@")
    def onHideProgress_(self, timer):
        self._dl_model.setTextColor_(ACCENT)
        self._hide_download_ui()

    # ── Actions ────────────────────────────────────────────────────

    @objc.typedSelector(b"v@:@")
    def closePanel_(self, sender):
        self._info_tooltip.dismiss()
        self._panel.orderOut_(None)

    @objc.typedSelector(b"v@:@")
    def onInfoToggle_(self, sender):
        self._info_tooltip.toggle(self._info_btn, self._panel)

    @objc.typedSelector(b"v@:@")
    def onDonate_(self, sender):
        pass  # placeholder — donation URL will be added later

    @objc.typedSelector(b"v@:@")
    def onSettingChanged_(self, sender):
        """Persist all settings to NSUserDefaults on any change."""
        if self._downloading:
            return

        key_idx = self._key_popup.indexOfSelectedItem()
        trigger_key = (
            _TRIGGER_KEY_IDS[key_idx]
            if key_idx < len(_TRIGGER_KEY_IDS)
            else "alt_r"
        )

        model_key = self._read_model_key()

        device_idx = self._device_popup.indexOfSelectedItem()
        audio_device = (
            self._device_indices[device_idx]
            if device_idx < len(self._device_indices)
            else None
        )

        config = TakConfig(
            trigger_key=trigger_key,
            model=model_key,
            use_clipboard=(
                self._clipboard_check.state() == AppKit.NSControlStateValueOn
            ),
            audio_device=audio_device,
        )
        save_config(config)

        # If the selected model isn't cached locally, download it first
        model_repo = _MLX_MODELS.get(model_key, model_key)
        if not is_model_cached(model_repo):
            self._start_download(model_key, model_repo)
        else:
            self._show_restart_alert()

    def _show_restart_alert(self):
        alert = AppKit.NSAlert.alloc().init()
        alert.setMessageText_("Restart Required")
        alert.setInformativeText_(
            "Changes will take effect after restarting the app."
        )
        alert.addButtonWithTitle_("OK")
        alert.setAlertStyle_(AppKit.NSAlertStyleInformational)
        alert.runModal()

    def show(self):
        if self._panel is None:
            self._build()
        self._panel.makeKeyAndOrderFront_(None)
        AppKit.NSApp.activateIgnoringOtherApps_(True)
