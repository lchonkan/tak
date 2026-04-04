"""TAK macOS settings — preferences window and NSUserDefaults persistence."""

from __future__ import annotations

from typing import Optional

import objc

import AppKit
import Foundation

from tak.config import TakConfig


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
    return TakConfig(
        trigger_key=str(defaults.stringForKey_(_KEY_TRIGGER) or "alt_r"),
        model=str(defaults.stringForKey_(_KEY_MODEL) or "turbo"),
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
    ("alt_r",   "Right Option (⌥)"),
    ("shift_r", "Right Shift (⇧)"),
    ("cmd_r",   "Right Command (⌘)"),
]

_TRIGGER_KEY_IDS = [k for k, _ in _TRIGGER_KEYS]
_TRIGGER_KEY_LABELS = [v for _, v in _TRIGGER_KEYS]


# ─── Model display names ───────────────────────────────────────────────

_MODEL_INFO = {
    "tiny":     "tiny (~75 MB, fastest)",
    "base":     "base (~140 MB, fast)",
    "small":    "small (~460 MB)",
    "medium":   "medium (~1.5 GB)",
    "large-v3": "large-v3 (~3 GB, most accurate)",
    "turbo":    "turbo (~2 GB, fast + accurate)",
}


# ─── Preferences window ────────────────────────────────────────────────

class SettingsWindow(AppKit.NSObject):
    """macOS preferences window backed by NSUserDefaults."""

    def init(self):
        self = objc.super(SettingsWindow, self).init()
        if self is None:
            return None
        self._window: Optional[AppKit.NSWindow] = None
        return self

    def _build(self):
        w, h = 420, 280
        rect = Foundation.NSMakeRect(0, 0, w, h)

        self._window = AppKit.NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            rect,
            (
                AppKit.NSWindowStyleMaskTitled
                | AppKit.NSWindowStyleMaskClosable
            ),
            AppKit.NSBackingStoreBuffered,
            False,
        )
        self._window.setTitle_("TAK Preferences")
        self._window.center()
        self._window.setReleasedWhenClosed_(False)

        content = self._window.contentView()
        config = load_config()

        y = h - 50
        label_x = 20
        control_x = 160
        control_w = 220

        # ── Trigger Key ─────────────────────────────────────────────
        self._add_label(content, "Trigger Key:", label_x, y)
        self._key_popup = AppKit.NSPopUpButton.alloc().initWithFrame_pullsDown_(
            Foundation.NSMakeRect(control_x, y - 4, control_w, 26), False
        )
        for label in _TRIGGER_KEY_LABELS:
            self._key_popup.addItemWithTitle_(label)
        # Select current
        if config.trigger_key in _TRIGGER_KEY_IDS:
            idx = _TRIGGER_KEY_IDS.index(config.trigger_key)
            self._key_popup.selectItemAtIndex_(idx)
        self._key_popup.setTarget_(self)
        self._key_popup.setAction_("onSettingChanged:")
        content.addSubview_(self._key_popup)

        y -= 44

        # ── Whisper Model ───────────────────────────────────────────
        self._add_label(content, "Whisper Model:", label_x, y)
        self._model_popup = AppKit.NSPopUpButton.alloc().initWithFrame_pullsDown_(
            Foundation.NSMakeRect(control_x, y - 4, control_w, 26), False
        )
        model_keys = list(_MODEL_INFO.keys())
        for key in model_keys:
            self._model_popup.addItemWithTitle_(_MODEL_INFO[key])
        current_display = _MODEL_INFO.get(config.model, config.model)
        self._model_popup.selectItemWithTitle_(current_display)
        self._model_popup.setTarget_(self)
        self._model_popup.setAction_("onSettingChanged:")
        content.addSubview_(self._model_popup)

        y -= 44

        # ── Audio Device ────────────────────────────────────────────
        self._add_label(content, "Audio Device:", label_x, y)
        self._device_popup = AppKit.NSPopUpButton.alloc().initWithFrame_pullsDown_(
            Foundation.NSMakeRect(control_x, y - 4, control_w, 26), False
        )
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
        content.addSubview_(self._device_popup)

        y -= 44

        # ── Clipboard mode ──────────────────────────────────────────
        self._clipboard_check = AppKit.NSButton.alloc().initWithFrame_(
            Foundation.NSMakeRect(label_x, y, control_x + control_w - label_x, 22)
        )
        self._clipboard_check.setButtonType_(AppKit.NSButtonTypeSwitch)
        self._clipboard_check.setTitle_("Use clipboard paste (Cmd+V)")
        self._clipboard_check.setState_(
            AppKit.NSControlStateValueOn if config.use_clipboard
            else AppKit.NSControlStateValueOff
        )
        self._clipboard_check.setTarget_(self)
        self._clipboard_check.setAction_("onSettingChanged:")
        content.addSubview_(self._clipboard_check)

        y -= 40

        # ── Info label ──────────────────────────────────────────────
        info = AppKit.NSTextField.labelWithString_(
            "Changes take effect on next launch."
        )
        info.setFrame_(Foundation.NSMakeRect(label_x, y, control_x + control_w - label_x, 18))
        info.setTextColor_(AppKit.NSColor.secondaryLabelColor())
        info.setFont_(AppKit.NSFont.systemFontOfSize_(11))
        content.addSubview_(info)

    def _add_label(self, parent, text: str, x: float, y: float):
        label = AppKit.NSTextField.labelWithString_(text)
        label.setFrame_(Foundation.NSMakeRect(x, y, 130, 18))
        label.setAlignment_(AppKit.NSTextAlignmentRight)
        label.setFont_(AppKit.NSFont.systemFontOfSize_(13))
        parent.addSubview_(label)

    @objc.typedSelector(b"v@:@")
    def onSettingChanged_(self, sender):
        """Persist all settings to NSUserDefaults on any change."""
        # Resolve trigger key from dropdown index
        key_idx = self._key_popup.indexOfSelectedItem()
        trigger_key = _TRIGGER_KEY_IDS[key_idx] if key_idx < len(_TRIGGER_KEY_IDS) else "alt_r"

        # Resolve model key from display name
        selected_model_display = str(self._model_popup.titleOfSelectedItem())
        model_key = "turbo"
        for key, display in _MODEL_INFO.items():
            if display == selected_model_display:
                model_key = key
                break

        # Resolve device index
        device_idx = self._device_popup.indexOfSelectedItem()
        audio_device = self._device_indices[device_idx] if device_idx < len(self._device_indices) else None

        config = TakConfig(
            trigger_key=trigger_key,
            model=model_key,
            use_clipboard=self._clipboard_check.state() == AppKit.NSControlStateValueOn,
            audio_device=audio_device,
        )
        save_config(config)

    def show(self):
        if self._window is None:
            self._build()
        self._window.makeKeyAndOrderFront_(None)
        AppKit.NSApp.activateIgnoringOtherApps_(True)
