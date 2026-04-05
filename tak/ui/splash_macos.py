"""TAK macOS download splash — model download progress overlay."""

from __future__ import annotations

import os
import threading
import time

import AppKit
import Foundation
import objc

from tak.ui.design import (
    BORDER, TEXT, TEXT_DIM, ACCENT,
    CardView, make_label,
)


_W, _H = 420, 220
_PAD = 32


# ─── Custom views ─────────────────────────────────────────────────────

class _BarView(AppKit.NSView):
    """Rounded progress bar with track and accent fill."""

    def initWithFrame_(self, frame):
        self = objc.super(_BarView, self).initWithFrame_(frame)
        if self is None:
            return None
        self._pct = 0.0
        return self

    def setProgress_(self, v):
        self._pct = max(0.0, min(1.0, v))
        self.setNeedsDisplay_(True)

    def drawRect_(self, rect):
        b = self.bounds()
        r = b.size.height / 2
        track = AppKit.NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(b, r, r)
        BORDER.set()
        track.fill()
        if self._pct > 0.005:
            fw = max(b.size.height, b.size.width * self._pct)
            fr = Foundation.NSMakeRect(0, 0, fw, b.size.height)
            fill = AppKit.NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(fr, r, r)
            ACCENT.set()
            fill.fill()


# ─── Helpers ───────────────────────────────────────────────────────────

def _fmt_bytes(n):
    for u in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f} {u}"
        n /= 1024
    return f"{n:.1f} TB"


def _fmt_eta(s):
    if s < 60:
        return f"~{int(s)}s remaining"
    m, sec = divmod(int(s), 60)
    return f"~{m}m {sec}s remaining"


# ─── Splash window ────────────────────────────────────────────────────

class DownloadSplash:
    """Floating model-download / model-loading progress window."""

    def __init__(self):
        self._build()

    def _build(self):
        sf = AppKit.NSScreen.mainScreen().frame()
        x = (sf.size.width - _W) / 2
        y = (sf.size.height - _H) / 2

        self._panel = AppKit.NSPanel.alloc().initWithContentRect_styleMask_backing_defer_(
            Foundation.NSMakeRect(x, y, _W, _H),
            AppKit.NSWindowStyleMaskBorderless | AppKit.NSWindowStyleMaskNonactivatingPanel,
            AppKit.NSBackingStoreBuffered,
            False,
        )
        self._panel.setLevel_(AppKit.NSFloatingWindowLevel)
        self._panel.setOpaque_(False)
        self._panel.setBackgroundColor_(AppKit.NSColor.clearColor())
        self._panel.setHasShadow_(True)
        self._panel.setMovableByWindowBackground_(True)

        card = CardView.alloc().initWithFrame_(Foundation.NSMakeRect(0, 0, _W, _H))
        self._panel.contentView().addSubview_(card)
        cw = _W - 2 * _PAD

        # Layout top-down (AppKit y=0 is bottom)
        cy = _H - _PAD

        cy -= 28
        title = make_label("TAK", 22, bold=True, color=TEXT)
        title.setFrame_(Foundation.NSMakeRect(_PAD, cy, cw, 28))
        card.addSubview_(title)
        cy -= 6

        cy -= 18
        self._status = make_label("Preparing\u2026", 13, color=TEXT_DIM)
        self._status.setFrame_(Foundation.NSMakeRect(_PAD, cy, cw, 18))
        card.addSubview_(self._status)
        cy -= 2

        cy -= 18
        self._model = make_label("", 13, color=ACCENT)
        self._model.setFrame_(Foundation.NSMakeRect(_PAD, cy, cw, 18))
        card.addSubview_(self._model)
        cy -= 20

        cy -= 6
        self._bar = _BarView.alloc().initWithFrame_(
            Foundation.NSMakeRect(_PAD, cy, cw, 6)
        )
        card.addSubview_(self._bar)
        cy -= 16

        cy -= 15
        self._stats = make_label("", 11, color=TEXT_DIM, mono=True)
        self._stats.setFrame_(Foundation.NSMakeRect(_PAD, cy, cw, 15))
        card.addSubview_(self._stats)
        cy -= 2

        cy -= 15
        self._speed = make_label("", 11, color=TEXT_DIM, mono=True)
        self._speed.setFrame_(Foundation.NSMakeRect(_PAD, cy, cw, 15))
        card.addSubview_(self._speed)

    def _on_main(self, fn):
        if AppKit.NSThread.isMainThread():
            fn()
        else:
            AppKit.NSOperationQueue.mainQueue().addOperationWithBlock_(fn)

    def show_download(self, model_name: str):
        def _do():
            self._status.setStringValue_("Downloading speech model")
            self._model.setStringValue_(model_name)
            self._bar.setProgress_(0.0)
            self._stats.setStringValue_("")
            self._speed.setStringValue_("")
            self._panel.orderFront_(None)
        self._on_main(_do)

    def show_loading(self, model_name: str):
        def _do():
            self._status.setStringValue_("Loading model\u2026")
            self._model.setStringValue_(model_name)
            self._bar.setProgress_(1.0)
            self._stats.setStringValue_("")
            self._speed.setStringValue_("")
            self._panel.orderFront_(None)
        self._on_main(_do)

    def update_progress(self, progress, downloaded, total, speed, eta):
        def _do():
            self._bar.setProgress_(progress)
            self._stats.setStringValue_(
                f"{int(progress * 100)}%  \u00b7  {downloaded} / {total}"
            )
            self._speed.setStringValue_(f"{speed}  \u00b7  {eta}")
        self._on_main(_do)

    def hide(self):
        self._on_main(lambda: self._panel.orderOut_(None))


# ─── tqdm-compatible progress reporter ────────────────────────────────

class _DownloadProgress:
    """Minimal tqdm replacement that reports download progress to DownloadSplash.

    snapshot_download creates ONE instance with total=0, then its internal
    _AggregatedTqdm increments .total and calls .update() as files download.
    We track the first non-disabled instance as the "main" bar and read its
    .total / .n directly — no init-time size threshold needed.
    """

    _lock = threading.Lock()
    _splash: DownloadSplash | None = None
    _main_bar: "_DownloadProgress | None" = None
    _t0: float | None = None

    def __init__(self, iterable=None, *args, **kwargs):
        self.iterable = iterable
        self.total = kwargs.get("total") or 0
        self.n = 0
        self.disable = kwargs.get("disable", False)
        self._last_ui = 0.0

        if not self.disable:
            with _DownloadProgress._lock:
                if _DownloadProgress._main_bar is None:
                    _DownloadProgress._main_bar = self
                    _DownloadProgress._t0 = time.time()

    def update(self, n=1):
        self.n += n

        # Only the main bar reports to the splash
        main = _DownloadProgress._main_bar
        if main is not self:
            return

        now = time.time()
        if now - self._last_ui < 0.08:
            return
        self._last_ui = now

        total = self.total
        done = self.n
        t0 = _DownloadProgress._t0

        if total <= 0:
            return

        elapsed = max(now - (t0 or now), 0.001)
        frac = done / total
        speed = done / elapsed
        eta = (total - done) / speed if speed > 0 else 0

        splash = _DownloadProgress._splash
        if splash:
            splash.update_progress(
                progress=frac,
                downloaded=_fmt_bytes(done),
                total=_fmt_bytes(total),
                speed=f"{_fmt_bytes(speed)}/s",
                eta=_fmt_eta(eta),
            )

    def close(self): pass
    def clear(self): pass
    def display(self, *a, **kw): pass
    def set_description(self, *a, **kw): pass
    def set_description_str(self, *a, **kw): pass
    def set_postfix(self, *a, **kw): pass
    def set_postfix_str(self, *a, **kw): pass
    def refresh(self, *a, **kw): pass

    def reset(self, total=None):
        if total is not None:
            self.total = total
        self.n = 0

    def __enter__(self):
        return self

    def __exit__(self, *a):
        pass

    def __iter__(self):
        if self.iterable is None:
            return self
        for item in self.iterable:
            yield item
            self.update(1)

    def __next__(self):
        raise StopIteration

    @classmethod
    def set_lock(cls, lock):
        cls._lock = lock

    @classmethod
    def get_lock(cls):
        return cls._lock

    @classmethod
    def _reset(cls):
        with cls._lock:
            cls._splash = None
            cls._main_bar = None
            cls._t0 = None


# ─── Public helpers ────────────────────────────────────────────────────

def is_model_cached(repo_id: str) -> bool:
    """Check whether a HuggingFace model is already in the local cache."""
    if os.path.isdir(repo_id):
        return True
    try:
        from huggingface_hub import snapshot_download
        snapshot_download(repo_id, local_files_only=True)
        return True
    except Exception:
        return False


def download_model(repo_id: str, splash: DownloadSplash) -> str:
    """Download a HuggingFace model with progress reporting. Returns cache path."""
    from huggingface_hub import snapshot_download

    _DownloadProgress._reset()
    _DownloadProgress._splash = splash
    try:
        return snapshot_download(repo_id, tqdm_class=_DownloadProgress)
    finally:
        _DownloadProgress._reset()
