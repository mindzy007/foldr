import ctypes
from bisect import bisect_right
import json
import math
import os
import re
import subprocess
import sys
import threading
import time
import tkinter as tk
import urllib.request
import webbrowser
from ctypes import wintypes
from functools import lru_cache
from tkinter import filedialog

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont, ImageGrab, ImageTk
from version import APP_VERSION
from tkinterdnd2 import DND_FILES, TkinterDnD

import core

# ------------------------------------------------------------------ paths
if getattr(sys, "frozen", False):
    BUNDLE = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    APP_DIR = os.path.dirname(sys.executable)
else:
    BUNDLE = os.path.dirname(os.path.abspath(__file__))
    APP_DIR = BUNDLE
ASSETS = os.path.join(BUNDLE, "assets")
ICON_ORDER = ['Default', 'Important', 'Language', 'System', 'Command', 'Wrench', 'Hard Drive', 'Security', 'Password', 'Locked', 'Unlocked', 'Key', 'Game', 'Fonts', 'Capture', 'Picture', 'Video', 'Movies & TV', 'Calendar', 'Mail', 'Document', 'Note', 'Notepad', 'Data Line', 'Data Pie', 'Data Chart', 'Package', 'Grid', 'Library', 'Stack', 'Server', 'Devices', 'Live', 'Javascript', 'Number Symbol', 'Mention', 'Texture', 'Inbound', 'Outbound', 'Warning', 'Sticker', 'Compute', 'Shape', 'Favorite', 'Miscellaneous', 'Pinned', 'Location', 'Marker', 'Globe', 'Earth', 'Tagged', 'Click', 'Settings', 'Recycle', 'Delete', 'Pulse', 'Music', 'Microphone', 'Announcement', 'Users', 'User', 'Network', 'Lightning', 'Home', 'Github', 'Dropbox', 'MEGA', 'Visual Studio Code', 'Google Drive', 'Nvidia', 'Rockstar Games', 'Steam', 'Epic Games', 'VMware', 'iCloud', 'Adobe', 'Vercel', 'Slack']

# ------------------------------------------------------------------ updates
RELEASES_URL = "https://github.com/mindzy007/foldr/releases"
LATEST_API = "https://api.github.com/repos/mindzy007/foldr/releases/latest"


def _version(text):
    return tuple(int(n) for n in re.findall(r"\d+", text))


# ------------------------------------------------------------------ theme
BG = "#202020"
CARD = "#2B2B2B"
STROKE = "#383838"
TEXT = "#FFFFFF"
SUBTLE = "#9D9D9D"
ACCENT = "#60CDFF"
GOOD, BAD = "#6CCB5F", "#FF99A4"

BTN = {  # state -> (fill, border-top, text)
    "n": ("#2D2D2D", "#353535", TEXT),
    "h": ("#323232", "#3A3A3A", TEXT),
    "p": ("#272727", "#2C2C2C", "#C8C8C8"),
}
BLUE = "#5C9DFF"  # primary button blue
BTN_ACCENT = {
    "n": (BLUE, None, "#FFFFFF"),
    "h": ("#77AEFF", None, "#FFFFFF"),
    "p": ("#4A8AEB", None, "#EEF4FF"),
}

BTN_W = 112      # every button is this wide
PAD = 16         # padding inside panels
CARD_SIZE = 104  # icon card height
CARD_W = 104  # icon card width (slightly narrower = less side padding)
T_BODY, T_CAP = 14, 13  # font sizes

S = 1.0  # UI scale, set once the window exists
ICON_ZOOM = 1.0  # icon grid size (toolbar: S / M / L)


def px(v):
    return max(1, int(round(v * S)))


def zw(v):
    """Card width: follows the icon size more gently than height, so names keep room."""
    return max(1, int(round(v * S * (0.6 + 0.4 * ICON_ZOOM))))


def z(v):
    """Like px(), but also follows the icon-size setting (used by the icon cards)."""
    return max(1, int(round(v * S * ICON_ZOOM)))


# ------------------------------------------------------------------ rendering
GAMMA = [int(255 * ((i / 255) ** 0.8) + 0.5) for i in range(256)]  # slightly bolder light-on-dark text
GAMMA_BOLD = [int(255 * ((i / 255) ** 0.7) + 0.5) for i in range(256)]  # a touch heavier for small labels
FONT_DIR = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts")
SS = 4  # text supersampling: glyphs are drawn unhinted at 4x, then box-filtered down


class HQFont:
    """Font drawn the way Qt/DirectWrite does it (like the Kernel app): unhinted glyph
    outlines at high resolution, area-averaged down to device pixels. Hinting is what makes
    PIL's native-size text look uneven; this keeps true letter shapes and spacing."""

    def __init__(self, path, size, weight=400, variable=False):
        self.size = size
        self.big = ImageFont.truetype(path, size * SS)
        if variable:
            try:
                logical = size / max(S, 0.5)
                opsz = max(14, min(36, logical))  # optical size: 'Text' cut, 'Display' when large
                vals = []
                for ax in self.big.get_variation_axes():
                    name = ax["name"]
                    name = (name.decode("latin-1") if isinstance(name, bytes) else str(name)).lower()
                    v = weight if "weight" in name else opsz if "optical" in name else ax["default"]
                    vals.append(max(ax["minimum"], min(ax["maximum"], v)))
                self.big.set_variation_by_axes(vals)
            except Exception:
                pass

    def getlength(self, text):
        return self.big.getlength(text) / SS

    def getmetrics(self):
        asc, desc = self.big.getmetrics()
        return math.ceil(asc / SS), math.ceil(desc / SS)


@lru_cache(maxsize=None)
def font(size, weight="regular"):
    wght = {"regular": 400, "medium": 500, "mediumplus": 560, "semibold": 600, "bold": 700}[weight]
    # same as Kernel: a bundled "fonts" folder next to the app wins (variable or static files)
    fdir = os.path.join(BUNDLE, "fonts")
    if os.path.isdir(fdir):
        files = sorted(f for f in os.listdir(fdir) if f.lower().endswith((".ttf", ".otf")))
        keys = {"regular": ("regular", "-400"), "medium": ("medium", "-500"), "mediumplus": ("medium", "-500"),
                "semibold": ("semibold", "demibold", "-600"), "bold": ("bold", "-700")}[weight]
        pick = next((f for f in files if any(k in f.lower() for k in keys)),
                    files[-1] if files else None)
        if pick:
            try:
                return HQFont(os.path.join(fdir, pick), size, wght, variable=True)
            except OSError:
                pass
    var = os.path.join(FONT_DIR, "SegUIVar.ttf")  # fallback: Segoe UI Variable (Windows 11)
    if os.path.isfile(var):
        try:
            return HQFont(var, size, wght, variable=True)
        except OSError:
            pass
    files = {"regular": ("segoeui.ttf",), "medium": ("segoeui.ttf",), "mediumplus": ("segoeui.ttf",),
             "semibold": ("seguisb.ttf", "segoeuib.ttf"),
             "bold": ("segoeuib.ttf",)}[weight]
    for f in files + ("DejaVuSans.ttf", "arial.ttf"):
        try:
            return HQFont(os.path.join(FONT_DIR, f) if f in files else f, size)
        except OSError:
            pass
    return ImageFont.load_default(size)


def lerp(c1, c2, t):
    a = [int(c1[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(c2[i:i + 2], 16) for i in (1, 3, 5)]
    return "#%02X%02X%02X" % tuple(round(x + (y - x) * t) for x, y in zip(a, b))


def bezier(x1, y1, x2, y2):
    """CSS-style cubic-bezier easing: maps time t (0..1) to progress (0..1)."""
    def f(t):
        if t <= 0:
            return 0.0
        if t >= 1:
            return 1.0
        lo, hi = 0.0, 1.0
        for _ in range(24):  # solve x(u) = t
            u = (lo + hi) / 2
            if 3 * (1 - u) ** 2 * u * x1 + 3 * (1 - u) * u * u * x2 + u ** 3 < t:
                lo = u
            else:
                hi = u
        u = (lo + hi) / 2
        return 3 * (1 - u) ** 2 * u * y1 + 3 * (1 - u) * u * u * y2 + u ** 3
    return f


def rrect(w, h, r, fill, border=None, bw=1, ss=4):
    """Supersampled rounded rectangle (RGBA)."""
    big = Image.new("RGBA", (w * ss, h * ss), (0, 0, 0, 0))
    d = ImageDraw.Draw(big)
    if border:
        d.rounded_rectangle((0, 0, w * ss - 1, h * ss - 1), r * ss, fill=border)
        i = bw * ss
        d.rounded_rectangle((i, i, w * ss - 1 - i, h * ss - 1 - i), max(0, r - bw) * ss, fill=fill)
    else:
        d.rounded_rectangle((0, 0, w * ss - 1, h * ss - 1), r * ss, fill=fill)
    return big.resize((w, h), Image.Resampling.LANCZOS)


def put_text(img, xy, text, fnt, color, anchor="la", gamma=None, tracking=0.0, embolden=0):
    """Draw antialiased text onto an RGBA image (supersampled + unhinted for HQFont)."""
    if isinstance(fnt, HQFont):
        def render(stroke):
            big = Image.new("L", (img.width * SS, img.height * SS), 0)
            d = ImageDraw.Draw(big)
            if tracking:  # letter-spacing as a fraction of the font size (0.02 = 2%)
                extra = tracking * fnt.size * SS
                total = fnt.big.getlength(text) + extra * (len(text) - 1)
                x0 = xy[0] * SS - (total / 2 if anchor[0] == "m" else total if anchor[0] == "r" else 0)
                for i, ch in enumerate(text):  # prefix lengths keep kerning intact
                    d.text((round(x0 + fnt.big.getlength(text[:i]) + extra * i), round(xy[1] * SS)),
                           ch, font=fnt.big, fill=255, anchor="l" + anchor[1],
                           stroke_width=stroke, stroke_fill=255)
            else:
                d.text((round(xy[0] * SS), round(xy[1] * SS)), text, font=fnt.big, fill=255,
                       anchor=anchor, stroke_width=stroke, stroke_fill=255)
            return big.resize(img.size, Image.Resampling.BOX)

        mask = render(0)
        if embolden:  # 0..1: blend toward a version thickened by 0.25px per side
            mask = Image.blend(mask, render(1), min(1.0, embolden))
    else:
        mask = Image.new("L", img.size, 0)
        ImageDraw.Draw(mask).text((round(xy[0]), round(xy[1])), text, font=fnt, fill=255, anchor=anchor)
    layer = Image.new("RGBA", img.size, color)
    layer.putalpha(mask.point(gamma or GAMMA))
    img.alpha_composite(layer)


def flatten(img, bg):
    """Composite on a solid color -> opaque image (no reliance on Tk alpha)."""
    base = bg.convert("RGBA") if isinstance(bg, Image.Image) else Image.new("RGBA", img.size, bg)
    base.alpha_composite(img)
    return base.convert("RGB")


def transition_image(widget, target, duration=140):
    current = getattr(widget, "_shown_image", None)
    if current is None:
        widget._shown_image = widget._target_image = target
        photo = ImageTk.PhotoImage(target)
        widget._transition_photo = photo
        widget.configure(image=photo)
        return
    if getattr(widget, "_target_image", None) is target:
        return
    job = getattr(widget, "_transition_job", None)
    if job:
        widget.after_cancel(job)
    start = current
    widget._target_image = target
    started = time.perf_counter()

    def advance():
        progress = min(1.0, (time.perf_counter() - started) * 1000 / duration)
        eased = progress * progress * (3 - 2 * progress)
        frame = Image.blend(start, target, eased)
        photo = ImageTk.PhotoImage(frame)
        widget._shown_image = frame
        widget._transition_photo = photo
        widget.configure(image=photo)
        if progress < 1:
            widget._transition_job = widget.after(16, advance)
        else:
            widget._shown_image = target
            widget._transition_job = None

    advance()


def fit(text, fnt, max_w):
    if fnt.getlength(text) <= max_w:
        return text
    while text and fnt.getlength(text + "…") > max_w:
        text = text[:-1]
    return text + "…"


def fit_left(text, fnt, max_w):
    """Ellipsize the start (keeps the end of a path visible)."""
    if fnt.getlength(text) <= max_w:
        return text
    while text and fnt.getlength("…" + text) > max_w:
        text = text[1:]
    return "…" + text


def text_image(text, size, weight, color, bg):
    f = font(px(size), weight)
    asc, desc = f.getmetrics()
    img = Image.new("RGBA", (int(f.getlength(text)) + 3, asc + desc + 3), (0, 0, 0, 0))
    put_text(img, (1, asc + 1), text, f, color, "ls")
    return flatten(img, bg)


def grad_rrect(w, h, r, fill, top, bottom, bw=1, ss=4):
    """Rounded button with a fill and a 1px border that fades from `top` to `bottom`."""
    outer = rrect(w, h, r, "#FFFFFF", ss=ss).getchannel("A")
    grad = Image.linear_gradient("L").resize((w, h), Image.Resampling.BILINEAR)  # 0 top -> 255 bottom
    grad = grad.point(lambda v: min(255, int(v * 3.2)))  # fade out over the top ~third
    ring = Image.merge("RGB", [Image.new("L", (w, h), 0)] * 3)
    c1 = tuple(int(top[i:i + 2], 16) for i in (1, 3, 5))
    c2 = tuple(int(bottom[i:i + 2], 16) for i in (1, 3, 5))
    chans = [Image.composite(Image.new("L", (w, h), c2[k]), Image.new("L", (w, h), c1[k]), grad) for k in range(3)]
    ring = Image.merge("RGB", chans).convert("RGBA")
    ring.putalpha(outer)
    inner = rrect(w - 2 * bw, h - 2 * bw, max(0, r - bw), fill, ss=ss)
    ring.alpha_composite(inner, (bw, bw))
    return ring


def button_image(w, h, text, accent, state, bg):
    fill, border, fg = (BTN_ACCENT if accent else BTN)[state]
    if accent:
        img = rrect(w, h, px(6), fill, border, px(1))
    else:
        img = grad_rrect(w, h, px(6), fill, border, fill, px(1))
    put_text(img, (w // 2, h // 2 + (px(1) if state == "p" else 0)), text, font(px(T_BODY), "medium"), fg, "mm")
    return flatten(img, bg)


def switch_image(t, w, label, label_layer=None):
    """t in 0..1 (0 = off, 1 = on); intermediate values are animation frames."""
    H, pw, ph = px(32), px(48), px(24)
    if label_layer is None:
        label_layer = Image.new("RGBA", (w, H), (0, 0, 0, 0))
        put_text(label_layer, (pw + px(12), H // 2), label, font(px(T_BODY), "medium"), TEXT,
                 "lm", GAMMA_BOLD, tracking=0.05, embolden=0.45)
    img = label_layer.copy()
    y = (H - ph) // 2
    pill = rrect(pw, ph, ph // 2, lerp(CARD, BLUE, t), lerp("#9A9A9A", BLUE, t), px(1))
    img.alpha_composite(pill, (0, y))
    kd = px(14)  # constant knob size
    mg = (ph - kd) // 2
    kx = round(mg + (pw - kd - 2 * mg) * t)
    knob = rrect(kd, kd, kd // 2, lerp("#CFCFCF", "#FFFFFF", t))
    img.alpha_composite(knob, (kx, y + (ph - kd) // 2))
    return flatten(img, CARD)


def row_image(w, path, hover):
    H = px(54)
    img = rrect(w, H, px(8), "#3A3A3A" if hover else "#333333", "#444444", px(1))
    tx = px(14)
    maxw = w - tx - px(46)
    name = os.path.basename(path.rstrip("\\/")) or path
    f1, f2 = font(px(T_BODY)), font(px(T_CAP))
    put_text(img, (tx, H // 2 - px(2)), fit(name, f1, maxw), f1, TEXT, "ls")
    put_text(img, (tx, H // 2 + px(15)), fit_left(path, f2, maxw), f2, SUBTLE, "ls")
    put_text(img, (w - px(22), H // 2), "×", font(px(22)), TEXT if hover else SUBTLE, "mm")
    return flatten(img, CARD)


_THUMBS, _CARDS, _PHOTOS = {}, {}, {}  # zoom-aware caches: switching sizes reuses finished art


def _mtime(path):
    try:
        return os.path.getmtime(path)
    except OSError:
        return 0


def _card_image(thumb, state, name=""):
    w, h = zw(CARD_W), z(CARD_SIZE)
    fill = {"n": "#333333", "h": "#363636", "s": "#3C3C3C"}[state]
    border = {"s": "#515151", "h": fill, "n": "#404040"}[state]  # no outline on hover
    if state == "n":  # idle: no tile, only the icon + name; the tile appears on hover/selection
        img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    else:
        img = rrect(w, h, px(8), fill, border, px(1))
    if thumb is not None:
        img.alpha_composite(thumb, ((w - thumb.width) // 2, z(8) + (z(60) - thumb.height) // 2))
    if name:
        f = font(px(T_CAP) if ICON_ZOOM <= 1 else z(T_CAP), "mediumplus")  # same size for every name
        put_text(img, (w // 2, z(83)), fit(name, f, w - px(10)), f, "#FFFFFF", "mm", embolden=0.45)
    return flatten(img, CARD)


def card_image(thumb, state, name="", path=None):
    if path is None:
        return _card_image(thumb, state, name)
    key = (path, _mtime(path), state, name, ICON_ZOOM, S)
    if key not in _CARDS:
        _CARDS[key] = _card_image(thumb, state, name)
    return _CARDS[key]


def card_photo(img, key):
    """PhotoImage cache (same key as card_image) so a size switch doesn't rebuild Tk images."""
    if key not in _PHOTOS:
        _PHOTOS[key] = ImageTk.PhotoImage(img)
    return _PHOTOS[key]


def make_thumb(path):
    key = (path, _mtime(path), ICON_ZOOM, S)
    if key not in _THUMBS:
        try:
            t = z(60)
            im = Image.open(path).convert("RGBA")
            im.thumbnail((t, t), Image.Resampling.LANCZOS)
        except Exception:
            im = None
        _THUMBS[key] = im
    return _THUMBS[key]


# ------------------------------------------------------------------ widgets
class TextLabel(tk.Label):
    def __init__(self, master, text, size=T_BODY, weight="regular", color=TEXT, bg=CARD):
        super().__init__(master, bd=0, highlightthickness=0, bg=bg)
        self.fsize, self.fweight, self.fbg, self.fcolor = size, weight, bg, color
        self.set(text)

    def set(self, text, color=None):
        self.fcolor = color or self.fcolor
        self.photo = ImageTk.PhotoImage(
            text_image(text, self.fsize, self.fweight, self.fcolor, self.fbg))
        self.configure(image=self.photo)


FOOT_SIZE, FOOT_TEXT = 13, "#B8B8B8"  # status bar text (status + segments share these)
BAR = "#1C1C1C"        # status bar fill
TOOLBAR_BG = "#232323"  # icon toolbar (a touch lighter than the status bar)
BAR_HOVER = "#2B2B2B"  # status bar segment hover fill
BAR_LINE = "#383838"   # status bar dividers


class Seg(tk.Label):
    """Fluent status-bar segment: text with a divider on its left edge.
    Clickable segments fade to a lighter fill on hover."""

    def __init__(self, master, text, command=None, color=FOOT_TEXT, bg=BAR):
        self.H, self.color, self.bgc, self.command = px(34), color, bg, command
        self._build(text)
        super().__init__(master, image=self.photos["n"], bd=0, highlightthickness=0, bg=bg,
                         cursor="hand2" if command else "")
        self._shown_image = self._target_image = self.images["n"]
        self._transition_photo, self._transition_job = self.photos["n"], None
        if command:
            self.bind("<Enter>", lambda e: transition_image(self, self.images["h"], 150))
            self.bind("<Leave>", lambda e: transition_image(self, self.images["n"], 160))
            self.bind("<ButtonPress-1>", lambda e: transition_image(self, self.images["p"], 60))
            self.bind("<ButtonRelease-1>", self._release)

    def _build(self, text):
        f = font(px(FOOT_SIZE), "semibold")  # status bar segments: same weight as the update popup text
        self.W = int(f.getlength(text)) + px(32) + 1
        self.images = {}
        for state, col in (("n", self.color), ("h", "#FFFFFF"), ("p", "#9A9A9A")):
            img = Image.new("RGBA", (self.W, self.H), self.bgc)
            d = ImageDraw.Draw(img)
            d.rectangle((0, 0, 0, self.H), fill=self.bgc)
            d.line([(0, self.H * 0.3), (0, self.H * 0.7)], fill=BAR_LINE, width=1)
            put_text(img, (self.W // 2 + 1, self.H // 2), text, f, col, "mm")
            self.images[state] = flatten(img, self.bgc)
        self.photos = {k: ImageTk.PhotoImage(v) for k, v in self.images.items()}

    def set_text(self, text):
        self._build(text)
        if self._transition_job:
            self.after_cancel(self._transition_job)
            self._transition_job = None
        self._shown_image = self._target_image = self.images["n"]
        self._transition_photo = self.photos["n"]
        self.configure(image=self._transition_photo)

    def _release(self, e):
        inside = 0 <= e.x < self.W and 0 <= e.y < self.H
        transition_image(self, self.images["h" if inside else "n"], 100)
        if inside:
            self.command()


class Btn(tk.Label):
    """Fixed-width button (all buttons share BTN_W), text centered."""

    def __init__(self, master, text, command, accent=False, bg=BG, width=None, backdrop=None):
        self.W, self.H = px(width or BTN_W), px(34)
        self.accent, self.bgc, self.backdrop = accent, bg, backdrop  # backdrop: image drawn behind
        self._build_images(text)
        super().__init__(master, image=self.photos["n"], bd=0, highlightthickness=0,
                         bg=bg, cursor="hand2")
        self._shown_image = self._target_image = self.images["n"]
        self._transition_photo = self.photos["n"]
        self._transition_job = None
        self.command, self._flash_job, self._flashing = command, None, False
        self.bind("<Enter>", lambda e: self._show("h"))
        self.bind("<Leave>", lambda e: self._show("n"))
        self.bind("<ButtonPress-1>", lambda e: self._show("p", force=True))
        self.bind("<ButtonRelease-1>", self._release)

    def _build_images(self, text):
        under = self.backdrop if self.backdrop is not None else self.bgc
        self.images = {s: button_image(self.W, self.H, text, self.accent, s, under)
                       for s in ("n", "h", "p")}
        self.photos = {s: ImageTk.PhotoImage(img) for s, img in self.images.items()}

    def set_text(self, text):
        """Change the label (cancels any running hover transition)."""
        self._build_images(text)
        if self._transition_job:
            self.after_cancel(self._transition_job)
            self._transition_job = None
        over = self.winfo_containing(*self.winfo_pointerxy()) is self
        self._shown_image = self._target_image = self.images["h" if over else "n"]
        self._transition_photo = self.photos["h" if over else "n"]
        self.configure(image=self._transition_photo)

    def _show(self, state, force=False):
        if self._flashing and not force:
            return
        self._flashing = False if force else self._flashing
        transition_image(self, self.images[state])

    def _release(self, e):
        inside = 0 <= e.x < self.W and 0 <= e.y < self.H
        self._show("h" if inside else "n", force=True)
        if inside:
            self.command()

    def flash(self, text, ms=900):
        """Temporarily show an accent-colored label (feedback)."""
        if self._flash_job:
            self.after_cancel(self._flash_job)
        if self._transition_job:
            self.after_cancel(self._transition_job)
            self._transition_job = None
        flash_image = button_image(self.W, self.H, text, True, "n",
                                   self.backdrop if self.backdrop is not None else self.bgc)
        self._flash_img = ImageTk.PhotoImage(flash_image)
        self._shown_image = self._target_image = flash_image
        self._transition_photo = self._flash_img
        self.configure(image=self._flash_img)
        self._flashing = True
        self._flash_job = self.after(ms, self._unflash)

    def _unflash(self):
        self._flashing, self._flash_job = False, None
        over = self.winfo_containing(*self.winfo_pointerxy()) is self
        transition_image(self, self.images["h" if over else "n"])


class Switch(tk.Label):
    """Animated toggle: time-based bezier easing, retargets instantly if clicked mid-animation."""
    FRAMES = 40
    DURATION = 190  # ms
    EASE = staticmethod(bezier(0.2, 0.8, 0.2, 1))  # reacts instantly, then settles softly

    def __init__(self, master, label, value, command, w):
        n = self.FRAMES - 1
        H, pw = px(32), px(48)
        text = Image.new("RGBA", (w, H), (0, 0, 0, 0))
        put_text(text, (pw + px(12), H // 2), label, font(px(T_BODY), "medium"), TEXT,
                 "lm", GAMMA, tracking=0.05, embolden=0.2)  # drawn once, reused by every frame
        self.frames = [ImageTk.PhotoImage(switch_image(i / n, w, label, text))
                       for i in range(self.FRAMES)]
        self.p = self.start = self.target = 1.0 if value else 0.0
        self.value, self.command, self._job, self._t0 = value, command, None, 0.0
        super().__init__(master, image=self.frames[n if value else 0], bd=0,
                         highlightthickness=0, bg=CARD, cursor="hand2")
        self.bind("<Button-1>", self._toggle)

    def _toggle(self, e):
        self.value = not self.value
        self.start, self.target = self.p, 1.0 if self.value else 0.0
        self._t0 = time.perf_counter()
        self.command(self.value)  # fire immediately; the animation just catches up
        if self._job is None:
            self._step()

    def _step(self):
        t = min(1.0, (time.perf_counter() - self._t0) * 1000 / self.DURATION)
        self.p = self.start + (self.target - self.start) * self.EASE(t)
        self.configure(image=self.frames[round(self.p * (self.FRAMES - 1))])
        self._job = self.after(4, self._step) if t < 1 else None


class Panel(tk.Frame):
    """Rounded, bordered card: a stroke-colored frame with the fill frame inset by the border
    width, plus 4 corner images on top. Tk resizes these natively, so resizing never glitches,
    and few windows move per step (every extra native window made dragging slower).
    Put children in .inner"""

    def __init__(self, master, top_fill=None, **kw):
        super().__init__(master, bg=STROKE, **kw)
        r, bw = px(12), px(1)
        self.inner = tk.Frame(self, bg=CARD)
        self.inner.place(x=bw, y=bw, relwidth=1, relheight=1, width=-2 * bw, height=-2 * bw)
        big = rrect(2 * r, 2 * r, r, CARD, STROKE, bw)
        big_top = rrect(2 * r, 2 * r, r, top_fill or CARD, STROKE, bw)
        self.corners = []
        for (cx, cy), pos in (((0, 0), dict(x=0, y=0)),
                              ((r, 0), dict(relx=1, x=-r, y=0)),
                              ((0, r), dict(x=0, rely=1, y=-r)),
                              ((r, r), dict(relx=1, x=-r, rely=1, y=-r))):
            src = big_top if cy == 0 else big
            ph = ImageTk.PhotoImage(flatten(src.crop((cx, cy, cx + r, cy + r)), BG))
            lab = tk.Label(self, image=ph, bd=0, highlightthickness=0, bg=BG)
            lab.place(width=r, height=r, **pos)
            self.corners.append((ph, lab))


class FluentScroll(tk.Canvas):
    """Fluent / macOS-style scrollbar: a slim pill that grows on hover and fades out when idle."""
    IDLE_MS = 500  # fade out after this long without use

    def __init__(self, master, area, bg=CARD):
        self.GW, self.MG = px(12), px(4)  # gutter width, top/bottom inset
        super().__init__(master, width=self.GW, bg=bg, bd=0, highlightthickness=0)
        self.area, self.bgc = area, bg
        self.top = self.size = 0.0  # visible window as fractions of the content
        self.hover = self._h0 = self._h1 = 0.0
        self.vis = self._v0 = self._v1 = 0.0  # 0 = faded out, 1 = fully visible
        self._t0 = self._vt0 = self._vdur = 0.0
        self._anim = self._vanim = self._idle = None
        self._grab, self._hovered = None, False
        self._cache = {}
        self.item = self.create_image(0, 0, anchor="ne", state="hidden")
        self.bind("<Configure>", lambda e: self._draw())
        self.bind("<Enter>", self._enter)
        self.bind("<Leave>", self._leave)
        self.bind("<ButtonPress-1>", self._press)
        self.bind("<B1-Motion>", self._drag)
        self.bind("<ButtonRelease-1>", self._release)

    def set(self, top, bottom):
        top, size = float(top), float(bottom) - float(top)
        moved = abs(top - self.top) > 1e-6 or abs(size - self.size) > 1e-6
        self.top, self.size = top, size
        if moved and size < 0.999:
            self._poke()  # scrolling wakes the bar up
        self._draw()

    def _geometry(self):
        H = max(1, self.winfo_height() - 2 * self.MG)
        th = min(H, max(px(64), int(H * self.size)))  # long thumb, never taller than the track
        travel = max(1, H - th)
        span = max(1e-6, 1 - self.size)
        return H, th, travel, span

    def _draw(self):
        if self.winfo_height() <= 1 or self.size >= 0.999 or self.vis <= 0.001:
            self.itemconfigure(self.item, state="hidden")
            return
        H, th, travel, span = self._geometry()
        y = self.MG + round(min(1.0, self.top / span) * travel)
        e = _ease(self.hover)
        q = round(e * 48)  # fine steps -> the width grows in sub-pixel increments (no stepping)
        v = round(self.vis * 16)
        key = (q, v, th)
        if key not in self._cache:
            if len(self._cache) > 500:
                self._cache.clear()
            maxw, ss = px(6), 8
            wf = px(4) + (px(6) - px(4)) * q / 48  # fractional width, drawn anti-aliased
            big = Image.new("L", (maxw * ss, th * ss), 0)
            ImageDraw.Draw(big).rounded_rectangle(
                ((maxw - wf) * ss, 0, maxw * ss - 1, th * ss - 1), radius=wf * ss / 2, fill=255)
            color = lerp(self.bgc, lerp("#555555", "#8A8A8A", q / 48), v / 16)  # darker; fades into bg
            img = Image.new("RGBA", (maxw, th), color)
            img.putalpha(big.resize((maxw, th), Image.Resampling.LANCZOS))
            self._cache[key] = ImageTk.PhotoImage(flatten(img, self.bgc))
        self.itemconfigure(self.item, image=self._cache[key], state="normal")
        self.coords(self.item, self.GW - px(2), y)

    # ---- hover grow
    def _to(self, target):
        self._h0, self._h1, self._t0 = self.hover, target, time.perf_counter()
        if self._anim is None:
            self._step()

    def _step(self):
        t = min(1.0, (time.perf_counter() - self._t0) / 0.24)
        self.hover = self._h0 + (self._h1 - self._h0) * t
        self._draw()
        self._anim = self.after(6, self._step) if t < 1 else None

    # ---- idle fade
    def _vis_to(self, target, ms):
        self._v0, self._v1, self._vt0, self._vdur = self.vis, target, time.perf_counter(), ms / 1000
        if self._vanim is None:
            self._vis_step()

    def _vis_step(self):
        t = min(1.0, (time.perf_counter() - self._vt0) / self._vdur)
        self.vis = self._v0 + (self._v1 - self._v0) * t
        self._draw()
        self._vanim = self.after(8, self._vis_step) if t < 1 else None

    def _poke(self):
        """Show the bar and (re)start the idle timer."""
        if self._idle:
            self.after_cancel(self._idle)
        self._idle = self.after(self.IDLE_MS, self._fade_out)
        if self._v1 != 1.0:
            self._vis_to(1.0, 120)

    def _fade_out(self):
        self._idle = None
        if self._grab is not None or self._hovered:
            self._poke()  # still in use
        else:
            self._vis_to(0.0, 160)

    def _enter(self, e):
        self._hovered = True
        self._poke()
        self._to(1.0)

    def _leave(self, e):
        self._hovered = False
        if self._grab is None:
            self._to(0.0)
            self._poke()  # restart the 2 s countdown

    # ---- dragging
    def _press(self, e):
        if self.size >= 0.999:
            return
        H, th, travel, span = self._geometry()
        y = self.MG + round(min(1.0, self.top / span) * travel)
        self._grab = e.y - y if y <= e.y <= y + th else th // 2  # clicking the track jumps there
        self._to(1.0)
        self._poke()
        self._drag(e)

    def _drag(self, e):
        if self._grab is None:
            return
        H, th, travel, span = self._geometry()
        frac = min(1.0, max(0.0, (e.y - self.MG - self._grab) / travel))
        self.area.scroll_to(frac * span * self.area._scroll_height)

    def _release(self, e):
        self._grab = None
        inside = 0 <= e.x < self.GW and 0 <= e.y < self.winfo_height()
        self._hovered = inside
        self._to(1.0 if inside else 0.0)
        self._poke()


class ScrollArea(tk.Frame):
    areas = []

    def __init__(self, master, bg=CARD):
        super().__init__(master, bg=bg)
        self.canvas = tk.Canvas(self, bg=bg, bd=0, highlightthickness=0)
        self.sb = FluentScroll(self, self, bg)
        self.sb.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.body = tk.Frame(self.canvas, bg=bg)
        self.win = self.canvas.create_window(0, 0, window=self.body, anchor="nw")
        self.on_resize = None
        self.on_scroll = None  # called after the view moved (toolbar blur follows it)
        self.fixed_height = None  # content height when items sit on the canvas, not in .body
        self.x_offset = 0  # shifts the canvas content right (centres items drawn on the canvas)
        self._scroll_height = 1
        self._scroll_target = 0
        self._scroll_position = 0
        self._scroll_last_time = 0
        self._scroll_job = None
        self.canvas.bind("<Configure>", self._canvas_cfg)
        self.body.bind("<Configure>", lambda e: self._fit())
        ScrollArea.areas.append(self)

    def _canvas_cfg(self, e):
        self.canvas.itemconfigure(self.win, width=e.width)
        self._fit()
        if self.on_resize:
            self.on_resize(e.width)

    def _fit(self):
        h = max(self.fixed_height or self.body.winfo_reqheight(), self.canvas.winfo_height())
        self._scroll_height = h
        self.canvas.configure(scrollregion=(-self.x_offset, 0, self.canvas.winfo_width() - self.x_offset, h))
        self.sb.set(*self.canvas.yview())

    def smooth_scroll(self, delta):
        viewport = self.canvas.winfo_height()
        max_offset = max(0, self._scroll_height - viewport)
        if not max_offset or not delta:
            return
        if self._scroll_job is None:
            self._scroll_position = self.canvas.yview()[0] * self._scroll_height
            self._scroll_target = self._scroll_position
            self._scroll_last_time = time.perf_counter()
        self._scroll_target = min(max(self._scroll_target + delta, 0), max_offset)
        if self._scroll_job is None:
            self._scroll_job = self.after(6, self._advance_scroll)

    def _advance_scroll(self):
        self._scroll_job = None
        max_offset = max(0, self._scroll_height - self.canvas.winfo_height())
        self._scroll_target = min(max(self._scroll_target, 0), max_offset)
        now = time.perf_counter()
        elapsed = min(now - self._scroll_last_time, 0.05)
        self._scroll_last_time = now
        remaining = self._scroll_target - self._scroll_position
        self._scroll_position += remaining * (1 - math.exp(-elapsed / 0.055))
        if abs(self._scroll_target - self._scroll_position) < 0.4:
            self._scroll_position = self._scroll_target
        # only touch the canvas when the whole-pixel offset actually changed
        whole = round(self._scroll_position)
        if whole != getattr(self, "_scroll_shown", None):
            self._scroll_shown = whole
            self.canvas.yview_moveto(whole / max(1, self._scroll_height))
            self.sb.set(*self.canvas.yview())
            if self.on_scroll:
                self.on_scroll()
            self.canvas.update_idletasks()  # paint now so cards never show blank/clipped
        if self._scroll_position != self._scroll_target:
            self._scroll_job = self.after(6, self._advance_scroll)

    def scroll_to(self, offset):
        """Jump to a pixel offset (scrollbar dragging) and keep the smooth scroller in sync."""
        if self._scroll_job:
            self.after_cancel(self._scroll_job)
            self._scroll_job = None
        max_offset = max(0, self._scroll_height - self.canvas.winfo_height())
        offset = min(max(offset, 0), max_offset)
        self._scroll_position = self._scroll_target = offset
        self._scroll_shown = round(offset)
        self.canvas.yview_moveto(offset / max(1, self._scroll_height))
        self.sb.set(*self.canvas.yview())
        if self.on_scroll:
            self.on_scroll()

    def clear(self):
        if self._scroll_job:
            self.after_cancel(self._scroll_job)
            self._scroll_job = None
        for w in self.body.winfo_children():
            w.destroy()
        self.canvas.delete("card")
        self.fixed_height, self.x_offset = None, 0
        self.canvas.yview_moveto(0)
        self._scroll_position = self._scroll_target = 0
        self._scroll_shown = 0
        self.sb.set(0, 1)


class FolderDropZone(tk.Canvas):
    """Dashed drop box. Resizing is smooth because redraws are throttled and the border is never
    re-rendered whole: the antialiased corners are rendered once, and only the thin straight edges
    are rebuilt (by pasting a pre-rendered dash), and only for the axis that changed."""

    def __init__(self, master):
        super().__init__(master, height=px(150), bg=CARD, bd=0, highlightthickness=0)
        self._size = (0, 0)
        self._job = None
        self._last = 0.0
        self._items = None
        self._edge_photos = {}
        self._corner_photos, self._corner, self._dash_tile = _border_parts()
        self._title_photo = ImageTk.PhotoImage(text_image("Drag folders here", T_BODY + 3, "semibold", TEXT, CARD))
        self._sub_photo = ImageTk.PhotoImage(text_image("or click Add folder", T_CAP + 2, "regular", SUBTLE, CARD))
        self.bind("<Configure>", self._schedule)

    def _schedule(self, _event=None):
        """Many <Configure> events arrive while dragging: draw at most ~30 times a second."""
        if self._job is not None:
            return
        wait = max(0, int(33 - (time.monotonic() - self._last) * 1000))
        self._job = self.after(wait, self._draw)

    def _edge(self, length, vertical, flip):
        """Photo for one straight edge: a strip of dashes `length` long, turned/mirrored as needed."""
        strip = Image.new("L", (length, self._dash_tile.height), 0)
        for x in range(0, length, self._dash_tile.width + px(6)):
            strip.paste(self._dash_tile, (x, 0))
        if vertical:
            strip = strip.transpose(Image.Transpose.TRANSPOSE)
        if flip:
            strip = strip.transpose(Image.Transpose.FLIP_LEFT_RIGHT if vertical else Image.Transpose.FLIP_TOP_BOTTOM)
        edge = Image.new("RGBA", strip.size, "#666666")
        edge.putalpha(strip)
        return ImageTk.PhotoImage(edge)

    def _draw(self):
        self._job = None
        self._last = time.monotonic()
        width, height = self.winfo_width(), self.winfo_height()
        if (width, height) == self._size:
            return
        corner, depth = self._corner, self._dash_tile.height
        if width <= 2 * corner or height <= 2 * corner:
            return
        old_width, old_height = self._size
        self._size = (width, height)
        center_y = height // 2
        if self._items is None:  # first draw: create every item once
            self._items = {
                "title": self.create_image(0, 0, image=self._title_photo),
                "sub": self.create_image(0, 0, image=self._sub_photo),
            }
            for name, photo in zip(("tl", "tr", "bl", "br"), self._corner_photos):
                self._items[name] = self.create_image(0, 0, image=photo, anchor="nw")
            for name in ("top", "bottom", "left", "right"):
                self._items[name] = self.create_image(0, 0, anchor="nw")
        items = self._items
        if width != old_width:  # horizontal edges depend on the width only
            span = width - 2 * corner
            for name, flip in (("top", False), ("bottom", True)):
                self._edge_photos[name] = self._edge(span, False, flip)
                self.itemconfigure(items[name], image=self._edge_photos[name])
        if height != old_height:  # vertical edges depend on the height only
            span = height - 2 * corner
            for name, flip in (("left", False), ("right", True)):
                self._edge_photos[name] = self._edge(span, True, flip)
                self.itemconfigure(items[name], image=self._edge_photos[name])
        self.coords(items["tl"], 0, 0)
        self.coords(items["tr"], width - corner, 0)
        self.coords(items["bl"], 0, height - corner)
        self.coords(items["br"], width - corner, height - corner)
        self.coords(items["top"], corner, 0)
        self.coords(items["bottom"], corner, height - depth)
        self.coords(items["left"], 0, corner)
        self.coords(items["right"], width - depth, corner)
        th, sh, gap = self._title_photo.height(), self._sub_photo.height(), px(2)
        total = th + gap + sh
        self.coords(items["title"], width // 2, round(center_y - total / 2 + th / 2))
        self.coords(items["sub"], width // 2, round(center_y + total / 2 - sh / 2))


def _border_parts():
    """The size-independent parts of the dashed border, rendered once: the four antialiased
    corners (photos, cropped from a tiny dashed rounded box), the corner size, and one straight
    dash as an "L" mask whose height is the thickness of a straight edge strip."""
    pad, radius = px(2), px(10)
    corner = pad + radius
    box = _dashed_rounded_border(2 * corner, 2 * corner, pad, pad, 2 * corner - pad, 2 * corner - pad, radius)
    corners = [ImageTk.PhotoImage(box.crop(rect)) for rect in (
        (0, 0, corner, corner), (corner, 0, 2 * corner, corner),
        (0, corner, corner, 2 * corner), (corner, corner, 2 * corner, 2 * corner))]
    # a straight dash, antialiased like the corners: the line is centred on y == pad
    scale, line, dash = 4, px(1), px(8)
    depth = pad + line + 1
    tile = Image.new("L", (dash * scale, depth * scale), 0)
    ImageDraw.Draw(tile).rectangle(
        (0, round((pad - line / 2) * scale), dash * scale - 1, round((pad + line / 2) * scale) - 1), fill=255)
    return corners, corner, tile.resize((dash, depth), Image.Resampling.BOX)


def _dashed_rounded_border(width, height, x0, y0, x1, y1, radius):
    scale = 4
    points = [(x0 + radius, y0), (x1 - radius, y0)]

    def add_arc(cx, cy, start, end):
        steps = 32
        for index in range(1, steps + 1):
            angle = math.radians(start + (end - start) * index / steps)
            points.append((cx + radius * math.cos(angle), cy + radius * math.sin(angle)))

    add_arc(x1 - radius, y0 + radius, -90, 0)
    points.append((x1, y1 - radius))
    add_arc(x1 - radius, y1 - radius, 0, 90)
    points.append((x0 + radius, y1))
    add_arc(x0 + radius, y1 - radius, 90, 180)
    points.append((x0, y0 + radius))
    add_arc(x0 + radius, y0 + radius, 180, 270)

    scaled = [(round(x * scale), round(y * scale)) for x, y in points]
    distances = [0.0]
    for first, second in zip(scaled, scaled[1:]):
        distances.append(distances[-1] + math.dist(first, second))

    def point_at(distance):
        index = min(bisect_right(distances, distance), len(distances) - 1)
        start, end = scaled[index - 1], scaled[index]
        span = distances[index] - distances[index - 1]
        part = (distance - distances[index - 1]) / span if span else 0
        return (round(start[0] + (end[0] - start[0]) * part),
                round(start[1] + (end[1] - start[1]) * part))

    image = Image.new("L", (width * scale, height * scale), 0)
    draw = ImageDraw.Draw(image)
    dash, gap = px(8) * scale, px(6) * scale
    position = 0.0
    while position < distances[-1]:
        end = min(position + dash, distances[-1])
        segment = [point_at(position)]
        segment.extend(point for distance, point in zip(distances, scaled)
                       if position < distance < end)
        segment.append(point_at(end))
        draw.line(segment, fill=255, width=px(1) * scale, joint="curve")
        position += dash + gap

    mask = image.resize((width, height), Image.Resampling.LANCZOS)
    border = Image.new("RGBA", (width, height), "#666666")
    border.putalpha(mask)
    return border


class FolderRow(tk.Label):
    def __init__(self, master, path, width, on_remove):
        self.W, self.path, self.on_remove = width, path, on_remove
        self.images = {h: row_image(width, path, h) for h in (False, True)}
        self.photos = {h: ImageTk.PhotoImage(img) for h, img in self.images.items()}
        super().__init__(master, image=self.photos[False], bd=0, highlightthickness=0, bg=CARD)
        self._shown_image = self._target_image = self.images[False]
        self._transition_photo = self.photos[False]
        self._transition_job = None
        self.bind("<Enter>", lambda e: transition_image(self, self.images[True]))
        self.bind("<Leave>", lambda e: transition_image(self, self.images[False]))
        self.bind("<Button-1>", lambda e: self.on_remove(self.path) if e.x > self.W - px(44) else None)


class IconCard:
    """One icon tile, drawn as a canvas image item. (78 native Label windows made resizing the
    app very slow; items cost almost nothing to repaint.) Quacks like the widget that
    ``transition_image`` animates: after / after_cancel / configure(image=)."""

    def __init__(self, canvas, path, on_click, reveal=None, fade=300):
        self.canvas, self.path = canvas, path
        self.name = os.path.splitext(os.path.basename(path))[0]
        self.name = DISPLAY_NAMES.get(self.name.lower(), self.name)
        self.thumb = make_thumb(path)
        self.selected = self.hovered = False
        self.images = {}
        self.photos = {}
        self.item = canvas.create_image(0, 0, anchor="nw", tags="card")
        self._shown_image = self._target_image = None
        self._transition_photo = None
        self._transition_job = None
        if reveal is None:
            self.refresh()
        else:  # start blank, then fade in after `reveal` ms (staggered by the grid)
            self._reveal_blank()
            canvas.after(reveal, lambda: canvas.type(self.item) and self.refresh(duration=fade))
        canvas.tag_bind(self.item, "<Enter>", lambda e: self._hover(True))
        canvas.tag_bind(self.item, "<Leave>", lambda e: self._hover(False))
        canvas.tag_bind(self.item, "<Button-1>", lambda e: on_click(self.path))

    def _key(self, state):
        return (self.path, _mtime(self.path), state, self.name, ICON_ZOOM, S)

    def after(self, ms, func):
        return self.canvas.after(ms, func)

    def after_cancel(self, job):
        self.canvas.after_cancel(job)

    def configure(self, image):
        self.canvas.itemconfigure(self.item, image=image)

    def place(self, x, y):
        self.pos = (x, y)
        self.canvas.coords(self.item, x, y)

    def _hover(self, v):
        self.hovered = v
        self.canvas.configure(cursor="hand2" if v else "")
        self.refresh()

    def _reveal_blank(self):
        self.images["n"] = card_image(self.thumb, "n", self.name, self.path)
        self.photos["n"] = card_photo(self.images["n"], self._key("n"))
        blank = Image.new("RGB", self.images["n"].size, CARD)
        self._shown_image = blank
        self._transition_photo = ImageTk.PhotoImage(blank)
        self.configure(self._transition_photo)

    def refresh(self, duration=140):
        s = "s" if self.selected else ("h" if self.hovered else "n")
        if s not in self.photos:
            self.images[s] = card_image(self.thumb, s, self.name, self.path)
            self.photos[s] = card_photo(self.images[s], self._key(s))
        transition_image(self, self.images[s], duration)


# ------------------------------------------------------------------ app
_ease = bezier(0.16, 1, 0.3, 1)      # fast start, long soft landing (enter / slide)
_ease_in = bezier(0.32, 0, 0.67, 0)  # gentle start, quick finish (exit)


def text_rgba(text, fnt, color):
    """Small transparent text image (cheap to build, composite where needed)."""
    asc, desc = fnt.getmetrics()
    img = Image.new("RGBA", (int(fnt.getlength(text)) + 4, asc + desc + 4), (0, 0, 0, 0))
    put_text(img, (2, asc + 2), text, fnt, color, "ls")
    return img


def warm_update_dialog():
    """Build the update popup's heavy images once, off the UI thread, so the first
    click on Get Update doesn't freeze the window (fonts, shadow blur, button art)."""
    try:
        ImageGrab.grab(bbox=(0, 0, 1, 1), all_screens=True)  # loads the screen-grab backend
        d = object.__new__(UpdateDialog)
        d.m, d._bases, d.version, d.shown = px(44), {}, "0", 0.0
        d.mode = "ask"
        d._shadow = d._make_shadow(px(UpdateDialog.W) + 2 * d.m, px(UpdateDialog.H) + 2 * d.m)
        d._layer(True)
        for mode in ("download", "install"):
            d.mode = mode
            d._text_images()
    except Exception:
        pass


class UpdateDialog:
    """Centered update popup over a blurred, dimmed snapshot of the app.
    Fades/scales in and out; Install downloads the release and starts the installer."""
    W, H = 400, 196

    def __init__(self, app, version, asset, dest):
        self.app, self.root = app, app.root
        self.version, self.asset, self.dest = version, asset, dest
        self.mode, self.progress, self.shown = "ask", 0.0, 0.0  # ask -> download -> install
        self.ready = self.closing = self.cancelled = False
        self.result, self.card, self.btns = None, None, {}
        self._anim_job = self._tick_job = self._poll_job = None
        root = self.root
        root.update_idletasks()
        w, h = root.winfo_width(), root.winfo_height()
        self.size = (w, h)
        self.bg0 = self._capture(w, h)  # sharp snapshot of the window
        self.bg1 = Image.blend(self.bg0, Image.new("RGB", (w, h), "#000000"), 0.3)  # sharp, dimmed
        self.glass = Image.new("RGB", (w, h), "#202020")  # solid card fill (no blur)
        self.m = px(44)  # room around the card for its shadow
        lw, lh = px(self.W) + 2 * self.m, px(self.H) + 2 * self.m
        self.pos = ((w - lw) // 2, (h - lh) // 2)
        self._bases = {}
        self._shadow = self._make_shadow(lw, lh)
        self.overlay = tk.Label(root, bd=0, highlightthickness=0, bg=BG)
        self._show_overlay(self.bg0)
        self.overlay.place(x=0, y=0)
        self.overlay.bind("<MouseWheel>", lambda e: "break")
        self.overlay.tkraise()
        self._animate(True, self._ready)

    # ---- images
    def _capture(self, w, h):
        x, y = self.root.winfo_rootx(), self.root.winfo_rooty()
        try:
            img = ImageGrab.grab(bbox=(x, y, x + w, y + h), all_screens=True).convert("RGB")
            if img.size == (w, h):
                return img
        except Exception:
            pass
        return Image.new("RGB", (w, h), BG)  # fallback: plain dim (no blur)

    def _make_shadow(self, lw, lh):
        sh = Image.new("RGBA", (lw, lh), (0, 0, 0, 0))
        m = self.m
        ImageDraw.Draw(sh).rounded_rectangle(
            (m, m + px(8), m + px(self.W), m + px(self.H) + px(8)), px(10), fill=(0, 0, 0, 170))
        return sh.filter(ImageFilter.GaussianBlur(px(12)))

    def _shape(self):
        """Card fill + hairline outline (no text)."""
        if "shape" in self._bases:
            return self._bases["shape"]
        W, H, r, bd = px(self.W), px(self.H), px(10), px(1)
        x0, y0 = self.pos[0] + self.m, self.pos[1] + self.m
        img = self.glass.crop((x0, y0, x0 + W, y0 + H)).convert("RGBA")  # solid fill
        outer = rrect(W, H, r, "#FFFFFF").getchannel("A")
        img.putalpha(outer)
        inner = Image.new("L", (W, H), 0)
        inner.paste(rrect(W - 2 * bd, H - 2 * bd, r - bd, "#FFFFFF").getchannel("A"), (bd, bd))
        ring = Image.new("RGBA", (W, H), (255, 255, 255, 0))
        ring.putalpha(ImageChops.subtract(outer, inner).point(lambda v: int(v * 0.07)))
        img.alpha_composite(ring)
        self._bases["shape"] = img
        return img

    def _texts(self):
        """(text, font, color, y) for the current mode."""
        tf, bf = font(px(18), "semibold"), font(px(T_BODY), "semibold")  # body lines: same size + weight
        if self.mode == "ask":
            return [("Update available", tf, TEXT, px(22)),
                    (f"Foldr v{self.version} is ready to install.", bf, TEXT, px(62)),
                    (f"You\u2019re currently on version {APP_VERSION}.", bf, SUBTLE, px(90))]
        if self.mode == "download":
            return [("Downloading update", tf, TEXT, px(22)),
                    (f"Foldr v{self.version}", bf, TEXT, px(62)),
                    ("Downloading\u2026", bf, SUBTLE, px(110))]
        return [("Installing update", tf, TEXT, px(22)),
                ("Starting the installer\u2026", bf, TEXT, px(62)),
                ("Almost done", bf, SUBTLE, px(110))]

    def _text_images(self):
        """Cached [(image, x, y)] of all text on the card (percentage included)."""
        key = ("text", self.mode)
        if key not in self._bases:
            self._bases[key] = [(text_rgba(t, f, c), px(24) - 2, y) for t, f, c, y in self._texts()]
        items = list(self._bases[key])
        if self.mode != "ask":
            pad, bw = px(24), px(self.W) - 2 * px(24)
            pct = text_rgba(f"{int(min(1.0, self.shown) * 100 + 0.5)}%",
                            font(px(T_BODY), "semibold"), SUBTLE)
            items.append((pct, pad + bw - pct.width + 2, px(110)))
        return items

    def _card(self, text=True):
        img = self._shape().copy()
        if self.mode != "ask":
            pad = px(24)
            bw, bh, y = px(self.W) - 2 * pad, px(6), px(92)
            img.alpha_composite(rrect(bw, bh, bh // 2, "#3D3D3D"), (pad, y))
            fw = max(bh, int(bw * min(1.0, self.shown)))
            img.alpha_composite(rrect(fw, bh, bh // 2, BLUE), (pad, y))
        if text:
            for timg, x, y in self._text_images():
                img.alpha_composite(timg, (x, y))
        return img

    def _btn_specs(self):
        W, H = px(self.W), px(self.H)
        pad, bw, gap, y = px(24), px(BTN_W), px(8), H - px(20) - px(34)
        right = W - pad - bw
        if self.mode == "ask":
            return [("Cancel", False, right - bw - gap, y), ("Install", True, right, y)]
        return []

    def _layer(self, buttons, text=True):
        layer = self._shadow.copy()
        layer.alpha_composite(self._card(text), (self.m, self.m))
        if buttons:
            bw, bh = px(BTN_W), px(34)
            for text, accent, x, y in self._btn_specs():
                under = layer.crop((self.m + x, self.m + y, self.m + x + bw, self.m + y + bh))
                b = button_image(bw, bh, text, accent, "n", under.convert("RGB")).convert("RGBA")
                layer.alpha_composite(b, (self.m + x, self.m + y))
        return layer

    def _card_frame(self):
        x0, y0 = self.pos
        lw, lh = self._shadow.size
        crop = self.bg1.crop((x0, y0, x0 + lw, y0 + lh)).convert("RGBA")
        crop.alpha_composite(self._layer(False))
        return crop.convert("RGB")

    def _show_overlay(self, img):
        photo = getattr(self, "_overlay_photo", None)
        if photo is not None and (photo.width(), photo.height()) == img.size:
            photo.paste(img)  # in-place update: much cheaper than a new PhotoImage per frame
            return
        photo = ImageTk.PhotoImage(img)
        self._overlay_photo = photo
        self.overlay.configure(image=photo)

    def _set_card(self, img, smooth):
        card = self.card
        if smooth and getattr(card, "_shown_image", None) is not None:
            transition_image(card, img, 180)  # cross-fade between states
            return
        job = getattr(card, "_transition_job", None)
        if job:
            card.after_cancel(job)
            card._transition_job = None
        photo = ImageTk.PhotoImage(img)
        card._shown_image = card._target_image = img
        card._transition_photo = photo
        card.configure(image=photo)

    def _refresh(self, smooth=False):
        if not self.closing and self.card is not None:
            self._set_card(self._card_frame(), smooth)

    # ---- animation (time based, so it stays smooth even if frames are dropped)
    def _animate(self, forward, done):
        w, h = self.size
        layer = self._layer(True)  # card + text + buttons, all scaled together
        lw, lh = layer.size
        cx, cy = lw / 2, lh / 2
        pos = ((w - lw) // 2, (h - lh) // 2)
        t0 = time.perf_counter()
        dur = 360 if forward else 220

        def step():
            t = min(1.0, (time.perf_counter() - t0) * 1000 / dur)
            p = _ease(t) if forward else 1 - _ease_in(t)
            frame = Image.blend(self.bg0, self.bg1, p)
            s = 0.92 + 0.08 * p  # card grows slightly as it fades in
            if s < 0.9995:
                # scale about the exact center with a sub-pixel affine + bicubic sampling:
                # no integer rounding of size/offset per frame, so the text doesn't jitter
                k = 1 / s
                lay = layer.transform((lw, lh), Image.Transform.AFFINE,
                                      (k, 0, cx - cx * k, 0, k, cy - cy * k),
                                      resample=Image.Resampling.BICUBIC)
            else:
                lay = layer
            fade = min(1.0, p * 1.5)
            mask = lay.getchannel("A").point(lambda v: int(v * fade))
            frame.paste(lay.convert("RGB"), pos, mask)
            self._show_overlay(frame)
            self.overlay.update_idletasks()  # paint the overlay first ...
            dim_titlebar(self.root, 0.3 * p)  # ... then dim the title bar, so both change together
            if t < 1:
                self._anim_job = self.root.after(8, step)
            else:
                self._anim_job = None
                done()

        step()

    def _ready(self):
        if self.closing:
            return
        self.card = tk.Label(self.root, bd=0, highlightthickness=0, bg=CARD)
        self.card.bind("<MouseWheel>", lambda e: "break")
        self._set_card(self._card_frame(), False)
        self.card.place(x=self.pos[0], y=self.pos[1])
        self._show_overlay(self.bg1)
        self._add_buttons()
        self.ready = True

    def _add_buttons(self):
        frame = self._card_frame()
        bw, bh = px(BTN_W), px(34)
        for text, accent, x, y in self._btn_specs():
            under = frame.crop((self.m + x, self.m + y, self.m + x + bw, self.m + y + bh))
            b = Btn(self.card, text, self.install if accent else self.cancel,
                    accent=accent, bg=CARD, backdrop=under)
            b.place(x=self.m + x, y=self.m + y)
            self.btns[text] = (b, x)

    def _slide(self, btn, x0, x1):
        t0 = time.perf_counter()

        def step():
            if self.closing:
                return
            t = min(1.0, (time.perf_counter() - t0) / 0.2)
            btn.place(x=round(x0 + (x1 - x0) * _ease(t)))
            if t < 1:
                self.root.after(16, step)

        step()

    # ---- actions
    def default(self):  # Enter key
        if self.mode == "ask":
            self.install()

    def install(self):
        if self.mode != "ask" or self.closing or not self.ready:
            return
        if not self.asset:  # release has no file attached: open its page instead
            webbrowser.open(RELEASES_URL)
            self.close("Opened the releases page")
            return
        self.mode = "download"
        for b, _ in self.btns.values():  # both buttons vanish while downloading
            b.destroy()
        self.btns = {}
        self._refresh(True)
        threading.Thread(target=self._download, daemon=True).start()
        self._poll()
        self._tick()

    def cancel(self):
        if self.mode == "install" or self.closing:
            return
        self.close("Update cancelled" if self.mode == "download" else None)

    def _download(self):
        part = self.dest + ".part"
        try:
            req = urllib.request.Request(self.asset["browser_download_url"],
                                         headers={"User-Agent": "Foldr"})
            with urllib.request.urlopen(req, timeout=30) as r, open(part, "wb") as fh:
                total = int(self.asset.get("size") or r.headers.get("Content-Length") or 0)
                got = 0
                while True:
                    if self.cancelled:
                        raise InterruptedError
                    chunk = r.read(65536)
                    if not chunk:
                        break
                    fh.write(chunk)
                    got += len(chunk)
                    self.progress = min(1.0, got / total) if total else 1 - math.exp(-got / 8e6)
            os.replace(part, self.dest)
            self.result = ("ok", None)
        except Exception as error:
            try:
                os.remove(part)
            except OSError:
                pass
            self.result = ("cancel", None) if self.cancelled else ("err", str(error))

    def _tick(self):  # eases the bar toward the real progress
        self._tick_job = None
        if self.closing or self.mode == "ask":
            return
        diff = (1.0 if self.mode == "install" else self.progress) - self.shown
        if abs(diff) > 0.0005:
            self.shown += diff * 0.18 if abs(diff) > 0.004 else diff
            if not getattr(self.card, "_transition_job", None):
                self._set_card(self._card_frame(), False)
        self._tick_job = self.root.after(16, self._tick)

    def _poll(self):
        self._poll_job = None
        if self.closing:
            return
        if self.result is None:
            self._poll_job = self.root.after(50, self._poll)
            return
        if self.result[0] == "ok":
            self.mode = "install"
            for b, _ in self.btns.values():
                b.destroy()
            self.btns = {}
            self._refresh(True)
            self._poll_job = self.root.after(750, self._launch)
        else:
            self.close("Download failed", BAD)

    def _launch(self):
        self._poll_job = None
        if self.closing:
            return
        try:
            if self.dest.lower().endswith((".exe", ".msi")):
                os.startfile(self.dest)
                self.app.say("Installer started", GOOD)
                self.root.after(1200, self.app._close)  # exit so the installer can replace files
                return
            subprocess.Popen(["explorer", f"/select,{self.dest}"])
            self.close("Update saved to Desktop", GOOD)
        except Exception as error:
            self.close(f"Couldn't start the installer: {error}", BAD)

    def close(self, msg=None, color=SUBTLE, instant=False):
        if self.closing:
            return
        self.closing = self.cancelled = True
        for job in (self._anim_job, self._tick_job, self._poll_job):
            if job:
                self.root.after_cancel(job)
        self._anim_job = self._tick_job = self._poll_job = None
        if msg:
            self.app.say(msg, color)
        instant = instant or not self.ready
        if self.card is not None:
            self.card.destroy()  # also removes the real buttons
            self.card = None
        self.btns = {}

        def finish():
            self.overlay.destroy()
            self.root.update_idletasks()
            dim_titlebar(self.root, 0)
            if self.app.modal is self:
                self.app.modal = None

        if instant:
            finish()
        else:
            self._animate(False, finish)


def dark_titlebar(root):
    try:
        root.update_idletasks()
        user32 = ctypes.windll.user32
        user32.GetParent.argtypes = [wintypes.HWND]
        user32.GetParent.restype = wintypes.HWND
        hwnd = user32.GetParent(root.winfo_id())
        dwm = ctypes.windll.dwmapi.DwmSetWindowAttribute
        for attr, val in ((20, 1), (19, 1), (35, 0x00202020), (36, 0x00FFFFFF)):
            dwm(hwnd, attr, ctypes.byref(ctypes.c_int(val)), 4)
    except Exception:
        pass


def dim_titlebar(root, amount):
    """Darken the native title bar by `amount` (0..1 toward black), so it matches the popup's dimmed overlay."""
    try:
        user32 = ctypes.windll.user32
        user32.GetParent.argtypes = [wintypes.HWND]
        user32.GetParent.restype = wintypes.HWND
        hwnd = user32.GetParent(root.winfo_id())
        v = int(round(0x20 * (1 - amount)))
        ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 35, ctypes.byref(ctypes.c_int(v * 0x010101)), 4)
    except Exception:
        pass


def fixed_row(parent, height, bg=BG):
    f = tk.Frame(parent, bg=bg, height=height)
    f.pack_propagate(False)
    return f


# ------------------------------------------------------------------ icon palettes
PALETTE_ORDER = ["blue", "red", "orange", "yellow", "green", "teal", "purple", "pink", "gray", "grey", "graphite"]
NAME_COLORS = {"blue": "#4DA3FF", "red": "#FF5F57", "orange": "#FF9F43", "yellow": "#FFD43B",
               "green": "#4CD964", "teal": "#2EC4B6", "purple": "#B07CFF", "pink": "#FF7EB6",
               "gray": "#9AA0A6", "grey": "#9AA0A6", "graphite": "#7A7F85"}
SORTS = [("default", "Default order"), ("az", "Name A\u2013Z"), ("za", "Name Z\u2013A")]
FLY_W, FLY_ROW, FLY_PAD = 184, 34, 5  # sort flyout geometry (px at 100%)
ZOOMS = [("S", 0.8), ("M", 1.0), ("L", 1.2)]
DISPLAY_NAMES = {"visual studio code": "VS Code"}  # shorter label under the icon


def _icon_files(folder):
    try:
        return [n for n in os.listdir(folder)
                if n.lower().endswith(core.EXTS) and not n.startswith(".")
                and os.path.isfile(os.path.join(folder, n))]
    except OSError:
        return []


def _sample_color(folder, files):
    """Swatch color = the folder color of the palette's own icons (falls back to the name)."""
    try:
        pick = next((n for n in files if os.path.splitext(n)[0].lower() == "default"), files[0])
        im = Image.open(os.path.join(folder, pick)).convert("RGBA")
        im.thumbnail((48, 48))
        px_ = [p for p in im.getdata() if p[3] > 200]
        sat = [p for p in px_ if max(p[:3]) - min(p[:3]) > 35] or px_
        sat.sort(key=lambda p: sum(p[:3]))
        c = sat[int(len(sat) * 0.7)]
        return "#%02X%02X%02X" % c[:3]
    except Exception:
        return None


def find_palettes():
    """[(name, folder, swatch color)] - every sub-folder of assets/ that holds icons
    (assets/blue, assets/red, ...). Icons sitting directly in assets/ show up as 'Default'."""
    out = []
    if os.path.isdir(ASSETS):
        for n in os.listdir(ASSETS):
            d = os.path.join(ASSETS, n)
            if os.path.isdir(d) and not n.startswith(".") and _icon_files(d):
                out.append((n, d))
    key = lambda t: (PALETTE_ORDER.index(t[0].lower()) if t[0].lower() in PALETTE_ORDER else 99, t[0].lower())
    out.sort(key=key)
    if _icon_files(ASSETS):
        out.insert(0, ("Default", ASSETS))
    res = []
    for name, d in out:
        col = _sample_color(d, _icon_files(d)) or NAME_COLORS.get(name.lower(), "#4DA3FF")
        res.append((name, d, col))
    return res


# ------------------------------------------------------------------ Fluent command bar
def _ss_layer(w, h, ss=4):
    return Image.new("RGBA", (int(w) * ss, int(h) * ss), (0, 0, 0, 0)), ss


def _paste_layer(img, layer, ss, cx, cy):
    small = layer.resize((layer.width // ss, layer.height // ss), Image.Resampling.LANCZOS)
    img.alpha_composite(small, (int(round(cx - small.width / 2)), int(round(cy - small.height / 2))))


def draw_circle(img, cx, cy, r, fill=None, outline=None, width=0):
    d = int(math.ceil(2 * r)) + 4
    lay, ss = _ss_layer(d, d)
    c = d * ss / 2
    box = (c - r * ss, c - r * ss, c + r * ss, c + r * ss)
    ImageDraw.Draw(lay).ellipse(box, fill=fill, outline=outline, width=int(round(width * ss)))
    _paste_layer(img, lay, ss, cx, cy)


def draw_grid_glyph(img, cx, cy, n, color):
    t = px(14)
    d = t + 4
    lay, ss = _ss_layer(d, d)
    g = max(1.0, S * 1.5)
    sq = (t - (n - 1) * g) / n
    o = (d - t) / 2
    dr = ImageDraw.Draw(lay)
    for i in range(n):
        for j in range(n):
            x0, y0 = o + i * (sq + g), o + j * (sq + g)
            dr.rounded_rectangle((x0 * ss, y0 * ss, (x0 + sq) * ss, (y0 + sq) * ss),
                                 radius=max(1, 0.8 * ss), fill=color)
    _paste_layer(img, lay, ss, cx, cy)


def draw_sort_glyph(img, cx, cy, color):
    d = px(18)
    lay, ss = _ss_layer(d, d)
    dr = ImageDraw.Draw(lay)
    th = max(1.4, 1.5 * S)
    for i, wd in enumerate((14, 10, 6)):
        y = d / 2 + (i - 1) * 4.6 * S
        x0 = (d - 14 * S) / 2
        dr.rounded_rectangle((x0 * ss, (y - th / 2) * ss, (x0 + wd * S) * ss, (y + th / 2) * ss),
                             radius=th * ss / 2, fill=color)
    _paste_layer(img, lay, ss, cx, cy)


def draw_chevron(img, cx, cy, color, flip=0.0):
    """Drop-down chevron that rotates (0 = pointing down, 1 = pointing up) around its center."""
    d = px(14)
    lay, ss = _ss_layer(d, d)
    a = 3.6 * S
    pts = [(d / 2 - a, d / 2 - a / 2), (d / 2, d / 2 + a / 2), (d / 2 + a, d / 2 - a / 2)]
    ImageDraw.Draw(lay).line([(x * ss, y * ss) for x, y in pts], fill=color,
                             width=int(round(1.5 * S * ss)), joint="curve")
    t = flip * flip * (3 - 2 * flip)  # smoothstep: soft start and landing
    if t > 0.001:
        lay = lay.rotate(180 * t, resample=Image.Resampling.BICUBIC)
    _paste_layer(img, lay, ss, cx, cy)


_CORNER_CACHE = {}


def _top_round_mask(w, h, r):
    """Alpha mask with rounded top corners and straight sides/bottom. Same look as cropping a
    full-width supersampled rounded rect, but built from two cached corners (cheap while resizing)."""
    corners = _CORNER_CACHE.get(r)
    if corners is None:
        alpha = rrect(2 * r, 2 * r, r, (255, 255, 255, 255)).getchannel("A")
        corners = _CORNER_CACHE[r] = (alpha.crop((0, 0, r, r)), alpha.crop((r, 0, 2 * r, r)))
    mask = Image.new("L", (w, h), 255)
    if w >= 2 * r and h >= r:
        mask.paste(corners[0], (0, 0))
        mask.paste(corners[1], (w - r, 0))
    return mask


def commandbar_image(w, h, pals, active, A, bg=None):
    """Windows Fluent-style command bar: color swatches on the left, sort dropdown + icon-size
    segmented control on the right. A holds the animated 0..1 values (hover / selected / slide).
    Returns (RGB image, [(x0, y0, x1, y1, key)])."""
    g = lambda k, d=0.0: A.get(k, d)
    img = bg.convert("RGBA") if bg is not None else Image.new("RGBA", (w, h), CARD)
    regions = []
    pad, gap = px(10), px(8)
    sh = px(30)
    y0 = (h - sh) // 2
    # ---- icon size: segmented control (the highlight slides between segments)
    sw, inset = px(32), px(2)
    seg_w = sw * len(ZOOMS) + inset * 2
    seg_x = w - pad - seg_w
    img.alpha_composite(rrect(seg_w, sh, px(6), (255, 255, 255, 12), (255, 255, 255, 30), px(1)), (seg_x, y0))
    for i, (zk, _) in enumerate(ZOOMS):
        x = seg_x + inset + i * sw
        key = ("zoom", zk)
        near = g(("seg", i))  # 1 when this segment is the selected one
        hv = g(("hov", key)) * (1 - near)
        if hv > 0.01:
            img.alpha_composite(rrect(sw, sh - 2 * inset, px(4), (255, 255, 255, int(24 * hv))),
                                (x, y0 + inset))
        draw_grid_glyph(img, x + sw / 2, y0 + sh / 2 - px(1) * near, 4 - i, lerp(SUBTLE, TEXT, near))
        regions.append((x, y0, x + sw, y0 + sh, key))
    hx = seg_x + inset + g("seg") * sw  # the pill glides to the clicked button
    img.alpha_composite(rrect(sw, sh - 2 * inset, px(4), (255, 255, 255, 40)), (int(round(hx)), y0 + inset))
    img.alpha_composite(rrect(px(12), max(2, px(2)), px(1), BLUE),
                        (int(round(hx)) + (sw - px(12)) // 2, y0 + sh - inset - px(4)))
    # the highlight sits above the idle glyphs, so draw the glyphs again on top of it
    for i, (zk, _) in enumerate(ZOOMS):
        x = seg_x + inset + i * sw
        near = g(("seg", i))
        draw_grid_glyph(img, x + sw / 2, y0 + sh / 2 - px(1) * near, 4 - i, lerp(SUBTLE, TEXT, near))
    # ---- sort: drop-down button
    f = font(px(T_BODY), "mediumplus")
    label = "Sort"
    bw = px(10) + px(18) + px(6) + int(f.getlength(label)) + px(10) + px(12) + px(8)
    bx = seg_x - gap - bw
    hv, mo = g(("hov", ("sort", None))), g("menu")
    if hv > 0.01 or mo > 0.01:
        img.alpha_composite(rrect(bw, sh, px(6), (255, 255, 255, int(20 * hv + 8 * mo)),
                                  (255, 255, 255, int(32 * mo)) if mo > 0.02 else None, px(1)), (bx, y0))
    draw_sort_glyph(img, bx + px(10) + px(9), y0 + sh / 2, TEXT)
    put_text(img, (bx + px(10) + px(18) + px(6), y0 + sh // 2), label, f, TEXT, "lm", embolden=0.45)
    draw_chevron(img, bx + bw - px(8) - px(6), y0 + sh / 2, SUBTLE, mo)
    regions.append((bx, y0, bx + bw, y0 + sh, ("sort", None)))
    # ---- color swatches
    if len(pals) > 1:
        avail = bx - gap - pad
        cell = max(px(22), min(px(32), avail // len(pals)))
        x = pad
        cy = h / 2
        for name, _, color in pals:
            key = ("pal", name)
            sel, hv = g(("sel", name)), g(("hov", key))
            if hv * (1 - sel) > 0.01:
                img.alpha_composite(rrect(cell, cell, px(6), (255, 255, 255, int(24 * hv * (1 - sel)))),
                                    (x, int(cy - cell / 2)))
            cx = x + cell / 2
            draw_circle(img, cx, cy, px(8.5) + (px(7.5) - px(8.5)) * sel + px(0.6) * hv * (1 - sel), fill=color)
            if sel > 0.02:  # the white ring grows in around the swatch
                draw_circle(img, cx, cy, px(9.5) + (px(11) - px(9.5)) * sel,
                            outline=(255, 255, 255, int(255 * sel)), width=max(1.5, 1.7 * S))
            regions.append((x, int(cy - cell / 2), x + cell, int(cy + cell / 2), key))
            x += cell + px(1)
    return flatten(img, CARD), regions


class Flyout(tk.Toplevel):
    """Fluent menu flyout (used by the Sort drop-down). Rounded by Windows itself (no
    color-key fringe), glides down a few pixels while fading in, fades out on close, and
    closes when it loses focus."""

    def __init__(self, master, x_right, y, items, active, on_pick, on_close, backdrop=None):
        super().__init__(master)
        self.items, self.active, self.on_pick, self.on_close = items, active, on_pick, on_close
        self.hover, self.hv, self.closing, self._job = None, [0.0] * len(items), False, None
        self.W, self.ih, self.pad = px(FLY_W), px(FLY_ROW), px(FLY_PAD)
        self.H = self.ih * len(items) + 2 * self.pad
        self._base = self._frost(backdrop)
        self.x, self.y, self.slide = int(x_right - self.W), int(y), px(8)
        self.overrideredirect(True)
        self.configure(bg="#2C2C2C")
        try:
            self.attributes("-topmost", True)
            self.attributes("-alpha", 0.0)
        except tk.TclError:
            pass
        self.label = tk.Label(self, bd=0, highlightthickness=0, bg="#2C2C2C")
        self.label.pack()
        self.geometry(f"{self.W}x{self.H}+{self.x}+{self.y - self.slide}")
        self.update_idletasks()
        self._round_corners()
        self._no_activate()
        self.label.bind("<Motion>", self._motion)
        self.label.bind("<Leave>", lambda e: self._set_hover(None))
        self.label.bind("<Button-1>", self._click)
        self._draw()
        self._t0 = self._last = time.perf_counter()
        self._animate()  # (never takes focus: closing is handled by CommandBar's global click/Escape hooks)

    def _frost(self, backdrop):
        """Blurred, tinted copy of whatever is under the menu (plain fill if the grab failed)."""
        if backdrop is not None and backdrop.size == (self.W, self.H):
            f = 4
            small = backdrop.resize((max(1, self.W // f), max(1, self.H // f)), Image.Resampling.BOX)
            blur = small.filter(ImageFilter.GaussianBlur(max(1.0, px(14) / f))).resize(
                (self.W, self.H), Image.Resampling.BICUBIC)
            return Image.blend(blur, Image.new("RGB", blur.size, "#262626"), 0.72)
        return Image.new("RGB", (self.W, self.H), "#2C2C2C")

    def _no_activate(self):
        """Show the menu without activating it, so the main window keeps its active look
        (title bar, shadow) while the menu is open."""
        try:
            hwnd = ctypes.windll.user32.GetParent(self.winfo_id()) or self.winfo_id()
            u = ctypes.windll.user32
            ex = u.GetWindowLongW(hwnd, -20)
            u.SetWindowLongW(hwnd, -20, ex | 0x08000000 | 0x00000080)  # WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW
        except Exception:
            pass

    def _round_corners(self):
        """Windows 11 rounded corners + matching 1px border (ignored on older Windows)."""
        try:
            hwnd = ctypes.windll.user32.GetParent(self.winfo_id()) or self.winfo_id()
            dwm = ctypes.windll.dwmapi.DwmSetWindowAttribute
            dwm(hwnd, 33, ctypes.byref(ctypes.c_int(2)), 4)         # DWMWA_WINDOW_CORNER_PREFERENCE = round
            dwm(hwnd, 34, ctypes.byref(ctypes.c_int(0x454545)), 4)  # DWMWA_BORDER_COLOR
        except Exception:
            pass

    def _index(self, y):
        i = (y - self.pad) // self.ih
        return int(i) if 0 <= i < len(self.items) else None

    def _motion(self, e):
        self._set_hover(self._index(e.y))

    def _set_hover(self, i):
        if i != self.hover:
            self.hover = i
            self._ensure()

    def _ensure(self):
        if self._job is None and self.winfo_exists():
            self._job = self.after(0, self._animate)

    def _click(self, e):
        i = self._index(e.y)
        if i is not None and not self.closing:
            pick = self.items[i][0]
            self.close()
            self.on_pick(pick)

    def _draw(self):
        W, H, ih, pad = self.W, self.H, self.ih, self.pad
        img = self._base.convert("RGBA")  # square; Windows rounds the window
        ImageDraw.Draw(img).rectangle((0, 0, W - 1, H - 1), outline="#4A4A4A", width=px(1))
        f = font(px(T_BODY), "mediumplus")
        for i, (key, text) in enumerate(self.items):
            y = pad + i * ih
            if self.hv[i] > 0.01:
                img.alpha_composite(rrect(W - 2 * pad, ih - px(4), px(5), (255, 255, 255, int(26 * self.hv[i]))),
                                    (pad, y + px(2)))
            if key == self.active:
                img.alpha_composite(rrect(max(2, px(3)), px(16), px(2), BLUE),
                                    (pad + px(1), y + (ih - px(16)) // 2))
            put_text(img, (pad + px(16), y + ih // 2), text, f, TEXT, "lm", embolden=0.45)
        self.photo = ImageTk.PhotoImage(flatten(img, "#2C2C2C"))
        self.label.configure(image=self.photo)

    def _animate(self):
        self._job = None
        if not self.winfo_exists():
            return
        now = time.perf_counter()
        p = min(1.0, (now - self._t0) / (0.10 if self.closing else 0.22))
        if self.closing:
            alpha, dy = 1 - _ease_in(p), 0
        else:
            e = _ease(p)
            alpha, dy = e, int(round(self.slide * (1 - e)))
        k = 1 - math.exp(-max(now - self._last, 0.016) / 0.045)
        self._last = now
        changed = busy = False
        for i in range(len(self.items)):
            t = 1.0 if i == self.hover else 0.0
            c = self.hv[i]
            n = c + (t - c) * k
            if abs(t - n) < 0.01:
                n = t
            else:
                busy = True
            if n != c:
                changed = True
                self.hv[i] = n
        if changed:
            self._draw()
        if not self.closing:
            self.geometry(f"+{self.x}+{self.y - dy}")  # position only: the window never resizes
        try:
            self.attributes("-alpha", max(0.0, min(1.0, alpha)))
        except tk.TclError:
            pass
        if self.closing and p >= 1:
            self.destroy()
            self.on_close()
            return
        if p < 1 or busy:
            self._job = self.after(16, self._animate)

    def close(self):
        if self.closing or not self.winfo_exists():
            return
        self.closing, self._t0, self._last = True, time.perf_counter(), time.perf_counter()
        self.label.unbind("<Motion>")
        self.label.unbind("<Button-1>")
        if self._job:
            self.after_cancel(self._job)
        self._animate()


class CommandBar(tk.Frame):
    """The toolbar above the icon grid. Hover, selection and the size highlight all ease
    between states instead of snapping."""
    HEIGHT = 44

    def __init__(self, master, app):
        super().__init__(master, bg=CARD, height=px(self.HEIGHT))
        self.pack_propagate(False)
        self.app, self.hover, self.regions = app, None, []
        self.flyout, self._closed_at, self._bw, self._skip_click = None, 0.0, 0, False
        self.A, self._tick_job, self._last = {}, None, 0.0
        self._bg, self._bg_key = None, None
        self._cfg_job, self._cfg_last = None, 0.0
        self.label = tk.Label(self, bd=0, highlightthickness=0, bg=CARD)
        self.label.pack(fill="both", expand=True)
        self.bind("<Configure>", self._configure)
        self.label.bind("<Motion>", self._motion)
        self.label.bind("<Leave>", lambda e: self._set_hover(None))
        self.label.bind("<Button-1>", self._click)
        self.bind_all("<ButtonPress-1>", self._global_click, add="+")
        self.bind_all("<Escape>", lambda e: self._close_flyout(), add="+")
        self.winfo_toplevel().bind("<FocusOut>", self._window_focus_out, add="+")

    def _close_flyout(self):
        if self.flyout is not None:
            self.flyout.close()

    def _global_click(self, e):
        if self._skip_click:  # this very click is the one that opened the menu
            self._skip_click = False
            return
        fl = self.flyout
        if fl is not None and not str(e.widget).startswith(str(fl)):
            fl.close()

    def _window_focus_out(self, e):
        fl = self.flyout
        if fl is None or e.widget is not self.winfo_toplevel():
            return
        try:  # clicking the menu itself can briefly shift focus: that must not close it
            mx, my = fl.winfo_pointerx(), fl.winfo_pointery()
            if (fl.winfo_rootx() <= mx < fl.winfo_rootx() + fl.W
                    and fl.winfo_rooty() <= my < fl.winfo_rooty() + fl.H + fl.slide):
                return
        except tk.TclError:
            pass
        fl.close()

    def _targets(self):
        a, T = self.app, {}
        for name, _, _ in a.palettes_view():
            T[("sel", name)] = 1.0 if name == a.palette_name else 0.0
            T[("hov", ("pal", name))] = 1.0 if self.hover == ("pal", name) else 0.0
        for zk, _ in ZOOMS:
            T[("hov", ("zoom", zk))] = 1.0 if self.hover == ("zoom", zk) else 0.0
        T[("hov", ("sort", None))] = 1.0 if self.hover == ("sort", None) else 0.0
        T["seg"] = float([k for k, _ in ZOOMS].index(a.zoom_key))  # slider position
        for i, (zk, _) in enumerate(ZOOMS):  # glyph glow: only the clicked button lights up
            T[("seg", i)] = 1.0 if zk == a.zoom_key else 0.0
        T["menu"] = 1.0 if self.flyout is not None else 0.0
        return T

    def _configure(self, e):
        """Many <Configure> events arrive while resizing: redraw at most ~30 times a second."""
        if e.width != self._bw:
            self._bw = e.width
            if self._cfg_job is None:
                wait = max(0, int(33 - (time.monotonic() - self._cfg_last) * 1000))
                self._cfg_job = self.after(wait, self._apply_width)

    def _apply_width(self):
        self._cfg_job = None
        self._cfg_last = time.monotonic()
        if self.winfo_exists():
            self.A = self._targets()
            self._draw()

    def refresh(self):
        """State changed (hover, palette, size, menu): ease toward it."""
        if self._tick_job is None:
            self._last = time.perf_counter()
            self._tick()

    def _tick(self):
        self._tick_job = None
        if not self.winfo_exists():
            return
        now = time.perf_counter()
        k = 1 - math.exp(-max(now - self._last, 0.016) / 0.05)
        self._last = now
        busy = False
        for key, t in self._targets().items():
            c = self.A.get(key, t)
            n = c + (t - c) * k
            if abs(t - n) < 0.01:
                n = t
            else:
                busy = True
            self.A[key] = n
        self._draw()
        if busy:
            self._tick_job = self.after(16, self._tick)

    def _backdrop(self, w, h):
        """Plain toolbar fill (the icons scroll away underneath it, cut off at its edge)."""
        if self._bg_key != (w, h):
            self._bg, self._bg_key = Image.new("RGB", (w, h), TOOLBAR_BG), (w, h)
        return self._bg

    def on_scroll(self):
        self._draw()

    def _frame(self, inner, wi, h):
        """Wrap the toolbar in the panel's own border and rounded top corners, so the toolbar
        (which covers the panel's top edge) still looks like part of the panel."""
        bw, r = px(1), px(12)
        wp, ht = wi + 2 * bw, h + bw
        key = (wp, ht)
        if getattr(self, "_mask_key", None) != key:
            self._mask_key = key
            self._outer = _top_round_mask(wp, ht, r)
            self._inner = _top_round_mask(wi, h, max(1, r - bw))
        out = Image.new("RGB", (wp, ht), BG)
        out.paste(Image.new("RGB", (wp, ht), STROKE), (0, 0), self._outer)
        out.paste(inner, (bw, bw), self._inner)
        return out

    def _draw(self):
        if self._bw < 50:
            return
        a = self.app
        bw, h = px(1), px(self.HEIGHT)
        wi = self._bw - 2 * bw
        inner, regions = commandbar_image(wi, h, a.palettes_view(), a.palette_name, self.A,
                                          self._backdrop(wi, h))
        self.regions = [(x0 + bw, y0 + bw, x1 + bw, y1 + bw, key) for x0, y0, x1, y1, key in regions]
        self.photo = ImageTk.PhotoImage(self._frame(inner, wi, h))
        self.label.configure(image=self.photo)

    def _hit(self, x, y):
        for x0, y0, x1, y1, key in self.regions:
            if x0 <= x < x1 and y0 <= y < y1:
                return key
        return None

    def _motion(self, e):
        self._set_hover(self._hit(e.x, e.y))

    def _set_hover(self, key):
        if key != self.hover:
            self.hover = key
            self.label.configure(cursor="hand2" if key else "")
            self.refresh()

    def _click(self, e):
        key = self._hit(e.x, e.y)
        if not key:
            return
        kind, val = key
        if kind == "pal":
            self.app.set_palette(val)
        elif kind == "zoom":
            self.app.set_zoom(val)
        elif kind == "sort":
            self.open_sort()

    def open_sort(self):
        if self.flyout is not None or time.perf_counter() - self._closed_at < 0.25:
            return  # the click that just closed the flyout shouldn't reopen it
        x0, y0, x1, y1, _ = next(r for r in self.regions if r[4] == ("sort", None))
        rx, ry = self.label.winfo_rootx(), self.label.winfo_rooty()
        fw, fh = px(FLY_W), px(FLY_ROW) * len(SORTS) + 2 * px(FLY_PAD)
        sx, sy = rx + x1 - fw, ry + y1 + px(4)
        try:  # grab what's under the menu *before* it exists, to frost it
            under = ImageGrab.grab(bbox=(sx, sy, sx + fw, sy + fh), all_screens=True).convert("RGB")
        except Exception:
            under = None
        self.flyout = Flyout(self, rx + x1, sy, SORTS, self.app.sort_key,
                             self.app.set_sort, self._flyout_closed, under)
        self._skip_click = True
        self.after(80, lambda: setattr(self, "_skip_click", False))
        self.refresh()

    def _flyout_closed(self):
        self.flyout = None
        self._closed_at = time.perf_counter()
        self.refresh()


class App:
    def __init__(self):
        global S
        try:
            # Per-monitor V2 keeps Tk and Pillow aligned when the window moves
            # between displays with different scale factors.
            ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
        except Exception:
            try:
                ctypes.windll.shcore.SetProcessDpiAwareness(2)
            except Exception:
                try:
                    ctypes.windll.user32.SetProcessDPIAware()
                except Exception:
                    pass
        try:
            ctypes.windll.winmm.timeBeginPeriod(1)
        except Exception:
            pass
        self.root = root = TkinterDnD.Tk()
        root.attributes("-alpha", 0)  # stay invisible until fully drawn (no white flash)
        S = root.winfo_fpixels("1i") / 96
        root.title("Foldr")
        root.configure(bg=BG)
        self._window_save_job = None
        root.geometry(self._load_window_geometry())
        root.minsize(px(820), px(520))
        icon = os.path.join(BUNDLE, "icon.png")
        icon_file = os.path.join(BUNDLE, "Foldr-build.ico")
        icon_set = False
        if os.path.isfile(icon):
            try:
                with Image.open(icon) as src:
                    src = src.convert("RGBA")
                    self.app_icons = []
                    for n in (16, 20, 24, 32, 40, 48, 64, 128, 256):
                        im = src.copy()
                        im.thumbnail((n, n), Image.Resampling.LANCZOS)
                        self.app_icons.append(ImageTk.PhotoImage(im))
                root.iconphoto(True, *self.app_icons)  # Windows picks the sharpest size
                icon_set = True
            except Exception:
                pass
        if not icon_set and os.path.isfile(icon_file):
            try:
                root.iconbitmap(icon_file)
            except Exception:
                pass

        self.folders, self.selected, self.cards, self._cols = [], None, {}, 0
        self.recurse, self.hidden, self.busy = True, False, False
        self._fjob, self.log_path = None, None
        self.modal, self.latest = None, ""
        self._init_view()

        self._build()
        # a tag only the toplevel has: binding on `root` itself would also run this for every
        # child widget's <Configure> (dozens per resize step)
        root.bind_class("FoldrWindow", "<Configure>", self._schedule_window_save)
        root.bindtags(("FoldrWindow",) + root.bindtags())
        root.protocol("WM_DELETE_WINDOW", self._close)
        root.bind_all("<MouseWheel>", self._wheel)
        root.bind("<Escape>", lambda e: self.modal and self.modal.cancel())
        root.bind("<Return>", lambda e: self.modal and self.modal.default())
        self.load_icons()
        self.root.after(800, self._prewarm)
        threading.Thread(target=warm_update_dialog, daemon=True).start()
        root.update_idletasks()
        dark_titlebar(root)
        try:
            root.drop_target_register(DND_FILES)
            root.dnd_bind("<<Drop>>", self._on_drop)
        except Exception as error:
            self.say(f"Drag-and-drop unavailable: {error}", BAD)
        root.update()
        root.after(60, lambda: root.attributes("-alpha", 1))

    def _load_window_geometry(self):
        width, height = 1000, 640
        try:
            with open(os.path.join(APP_DIR, "window_size.json"), "r", encoding="utf-8") as settings:
                saved = json.load(settings)
            width = max(820, int(saved["width"]))
            height = max(520, int(saved["height"]))
        except (OSError, ValueError, TypeError, KeyError, OverflowError):
            pass
        max_width = max(820, int(self.root.winfo_screenwidth() / S) - 80)
        max_height = max(520, int(self.root.winfo_screenheight() / S) - 100)
        width, height = min(width, max_width), min(height, max_height)
        return f"{px(width)}x{px(height)}"

    def _save_window_size(self):
        self._window_save_job = None
        if self.root.state() != "normal":
            return
        width = self.root.winfo_width()
        height = self.root.winfo_height()
        if width <= 1 or height <= 1:
            return
        try:
            with open(os.path.join(APP_DIR, "window_size.json"), "w", encoding="utf-8") as settings:
                json.dump({"width": round(width / S), "height": round(height / S)}, settings)
        except OSError:
            pass

    def _schedule_window_save(self, event):
        if (event.widget is self.root and self.modal
                and (event.width, event.height) != self.modal.size):
            self.modal.close(instant=True)
        if event.widget is not self.root or self.root.state() != "normal":
            return
        if self._window_save_job is not None:
            self.root.after_cancel(self._window_save_job)
        self._window_save_job = self.root.after(500, self._save_window_size)

    def _close(self):
        if self._window_save_job is not None:
            self.root.after_cancel(self._window_save_job)
            self._window_save_job = None
        self._save_window_size()
        self.root.destroy()

    # ---- layout: two equal columns, same top/bottom edges
    def _build(self):
        # status bar (Notepad style): status left, update check + version right
        sb = fixed_row(self.root, px(34), bg=BAR)
        sb.pack(side="bottom", fill="x")
        tk.Frame(self.root, bg=BAR_LINE, height=1).pack(side="bottom", fill="x")
        Seg(sb, f"v{APP_VERSION}").pack(side="right", padx=(0, px(8)))
        self.update_btn = Seg(sb, "Check for Updates", self.check_updates)
        self.update_btn.pack(side="right")
        self.admin_btn = Seg(sb, "Run as admin", self.restart_admin)
        self.log_btn = Seg(sb, "View log", self.open_log)
        self.status = TextLabel(sb, "Drag folders in, pick an icon, hit Apply", FOOT_SIZE,
                                "semibold", color=FOOT_TEXT, bg=BAR)
        self.status.pack(side="left", padx=(px(22), 0))
        self.update_ready, self._checking = False, False
        self.update_assets = []

        main = tk.Frame(self.root, bg=BG)
        main.pack(fill="both", expand=True, padx=px(16), pady=(px(16), px(12)))
        main.columnconfigure((0, 1), weight=1, uniform="col")
        main.rowconfigure(1, weight=1)
        gl, gr = (0, px(8)), (px(8), 0)

        # headers
        lh = fixed_row(main, px(34))
        lh.grid(row=0, column=0, sticky="ew", padx=gl, pady=(0, px(10)))
        TextLabel(lh, "Foldr", 24, "semibold", bg=BG).pack(side="left")
        rh = fixed_row(main, px(34))
        rh.grid(row=0, column=1, sticky="ew", padx=gr, pady=(0, px(10)))
        TextLabel(rh, "Icons", 24, "semibold", bg=BG).pack(side="left")
        # panels
        left = Panel(main)
        left.grid(row=1, column=0, sticky="nsew", padx=gl)
        right = Panel(main)
        right.grid(row=1, column=1, sticky="nsew", padx=gr)

        sw = tk.Frame(left.inner, bg=CARD)
        sw.pack(side="bottom", fill="x", padx=px(PAD), pady=(px(6), px(PAD - 4)))
        Switch(sw, "Include subfolders", self.recurse, self._set_recurse, px(240)).pack(anchor="w")
        Switch(sw, "Include hidden folders", self.hidden, self._set_hidden, px(240)).pack(
            anchor="w", pady=(px(2), 0))
        self.folder_area = ScrollArea(left.inner)
        # the scrollbar gutter (12px) sits at the right: take it out of the right padding so the drop zone is centered
        self.folder_area.pack(fill="both", expand=True, padx=(px(PAD), max(0, px(PAD) - px(12))), pady=(px(PAD), 0))
        self.folder_area.on_resize = self._folders_resized

        self.icon_area = ScrollArea(right.inner)
        self.icon_area.pack(fill="both", expand=True, padx=px(2))
        self.icon_area.sb.pack_configure(pady=(px(CommandBar.HEIGHT) + px(4), px(6)))
        self.icon_area.on_resize = self.reflow
        self.toolbar = CommandBar(right, self)  # floats over the top of the panel + icon grid
        self.toolbar.place(x=0, y=0, relwidth=1, height=px(CommandBar.HEIGHT) + px(1))
        self.toolbar_line = tk.Frame(right.inner, bg=STROKE)
        self.toolbar_line.place(x=0, y=px(CommandBar.HEIGHT), relwidth=1, height=1)
        self.icon_area.on_scroll = self.toolbar.on_scroll

        # button bars
        bar = fixed_row(main, px(34))
        bar.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(px(12), 0))
        Btn(bar, "Add folder", self.add_folder).pack(side="left")
        Btn(bar, "Apply", self.apply, accent=True).pack(side="right")
        Btn(bar, "Reset", self.reset).pack(side="right", padx=(0, px(8)))
        Btn(bar, "Refresh", self.refresh_explorer).pack(side="right", padx=(0, px(8)))
        Btn(bar, "Clear", self.clear_folders).pack(side="left", padx=(px(8), 0))

    # ---- helpers
    def say(self, msg, color=SUBTLE):
        self.status.set(msg, FOOT_TEXT if color == SUBTLE else color)

    # ---- updates
    def check_updates(self):
        if self.update_ready:  # a newer release was already found: show the popup again
            self.show_update()
            return
        if self._checking:
            return
        self._checking = True
        self.say("Checking for updates...")
        state = {"result": None}

        def work():
            try:
                req = urllib.request.Request(LATEST_API, headers={
                    "User-Agent": "Foldr", "Accept": "application/vnd.github+json"})
                with urllib.request.urlopen(req, timeout=10) as r:
                    data = json.load(r)
                    self.update_assets = data.get("assets", [])
                    state["result"] = ("ok", data["tag_name"])
            except Exception as error:
                state["result"] = ("err", str(error))

        threading.Thread(target=work, daemon=True).start()

        def poll():
            if state["result"] is None:
                self.root.after(100, poll)
                return
            self._checking = False
            kind, value = state["result"]
            if kind == "err":
                self.say("Couldn't check for updates", BAD)
            elif _version(value) > _version(APP_VERSION):
                self.update_ready, self.latest = True, value
                self.update_btn.set_text("Get Update")
                self.say("App update is available", ACCENT)
                self.show_update()
            else:
                self.say("App is up to date", GOOD)

        self.root.after(100, poll)

    def show_update(self):
        """Ask (blurred popup) whether to install the newest release."""
        if self.modal or getattr(self, "_dialog_pending", False):
            return
        assets = [a for a in self.update_assets if a.get("browser_download_url")]
        asset = next((a for a in assets if a["name"].lower().endswith((".exe", ".msi"))),
                     next((a for a in assets if a["name"].lower().endswith(".zip")),
                          assets[0] if assets else None))
        home = os.path.expanduser("~")
        desk = next((p for p in (os.path.join(home, "Desktop"),
                                 os.path.join(os.environ.get("OneDrive", home), "Desktop"))
                     if os.path.isdir(p)), home)
        dest = os.path.join(desk, asset["name"]) if asset else ""
        self._dialog_pending = True  # a second click can't open two popups

        def build():
            self._dialog_pending = False
            try:
                self.modal = UpdateDialog(self, self.latest.lstrip("vV"), asset, dest)
            except Exception:
                self.modal = None
                self.say("App update is available", ACCENT)

        self.root.after(40, build)

    def refresh_explorer(self):
        """Reload icons and refresh Explorer windows."""
        def work():
            try:
                sh = ctypes.windll.shell32
                sh.SHChangeNotify.argtypes = [ctypes.c_long, ctypes.c_uint,
                                              ctypes.c_void_p, ctypes.c_void_p]
                sh.SHChangeNotify(0x08000000, 0x1000, None, None)  # assoc changed + flush
                sh.SHChangeNotify(0x00001000, 0x1000, None, None)  # update
                u = ctypes.windll.user32
                u.SendMessageTimeoutW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM,
                                                  ctypes.c_wchar_p, wintypes.UINT, wintypes.UINT,
                                                  ctypes.c_void_p]
                u.SendMessageTimeoutW(0xFFFF, 0x001A, 0, "ShellState", 2, 2000, None)
                import subprocess
                flags = 0x08000000  # CREATE_NO_WINDOW
                subprocess.run(["ie4uinit.exe", "-show"], creationflags=flags, timeout=10)
                subprocess.run(["ie4uinit.exe", "-ClearIconCache"], creationflags=flags, timeout=10)
                # F5 every open Explorer window
                shell = ctypes.windll.user32
                def cb(hwnd, _):
                    buf = ctypes.create_unicode_buffer(64)
                    shell.GetClassNameW(hwnd, buf, 64)
                    if buf.value == "CabinetWClass":
                        shell.PostMessageW(hwnd, 0x0111, 41504, 0)  # refresh command
                    return True
                proc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)(cb)
                shell.EnumWindows(proc, 0)
                self.root.after(0, lambda: self.say("Explorer refreshed", GOOD))
            except Exception:
                self.root.after(0, lambda: self.say("Couldn't refresh Explorer", BAD))
        self.say("Refreshing Explorer...")
        threading.Thread(target=work, daemon=True).start()

    def _set_recurse(self, v):
        self.recurse = v

    def _set_hidden(self, v):
        self.hidden = v

    def _wheel(self, e):
        if self.modal:
            return "break"
        w = self.root.winfo_containing(e.x_root, e.y_root)
        if w is self.toolbar.label:
            self.icon_area.smooth_scroll(-e.delta / 120 * px(105))
            return "break"
        while w is not None:
            for a in ScrollArea.areas:
                if w is a:
                    a.smooth_scroll(-e.delta / 120 * px(105))
                    return "break"
            w = w.master

    # ---- folders
    def _add(self, path):
        path = os.path.normpath(path)
        if os.path.isdir(path) and path not in self.folders:
            self.folders.append(path)
            return True
        return False

    def add_folder(self):
        f = filedialog.askdirectory(title="Choose a folder")
        if f and self._add(f):
            self.draw_folders()
            self.say(f"{len(self.folders)} folder(s) ready")

    def add_dropped(self, paths):
        try:
            added = sum(self._add(p) for p in paths)
            self.draw_folders()
        except Exception as error:
            self._drop_failed(str(error))
            return
        if added:
            self.say(f"Added {added} folder(s) · {len(self.folders)} ready")
        else:
            self.say("Drop folders (not files)", BAD)

    def _on_drop(self, event):
        if self.modal:
            return
        try:
            paths = self.root.tk.splitlist(event.data)
        except Exception as error:
            self._drop_failed(str(error))
            return
        self.add_dropped(paths)

    def _drop_failed(self, error):
        self.say(f"Could not add dropped folder: {error}", BAD)

    def remove_folder(self, path):
        self.folders.remove(path)
        self.draw_folders()

    def clear_folders(self):
        self.folders.clear()
        self.draw_folders()

    def _folders_resized(self, _w):
        if not self.folders and self.folder_area.body.winfo_children():
            return
        if self._fjob:
            self.root.after_cancel(self._fjob)
        self._fjob = self.root.after(180, self.draw_folders)

    def draw_folders(self):
        self._fjob = None
        w = self.folder_area.canvas.winfo_width()
        if w <= 1:
            return
        self.folder_area.clear()
        body = self.folder_area.body
        if not self.folders:
            FolderDropZone(body).pack(fill="x")
            return
        for f in self.folders:
            FolderRow(body, f, w, self.remove_folder).pack(pady=(0, px(8)))

    # ---- icons
    def load_icons(self, animate=True):
        self.icon_area.clear()
        self.cards, self._cols = {}, 0
        found = {}
        self._scan_palettes()
        base = self.palette_dir
        for n in _icon_files(base):
            found.setdefault(os.path.splitext(n)[0].lower(), (os.path.splitext(n)[0], os.path.join(base, n)))
        if self.selected and self.selected not in [p for _, p in found.values()]:  # same icon, other color
            key = os.path.splitext(os.path.basename(self.selected))[0].lower()
            self.selected = found[key][1] if key in found else None
        body = self.icon_area.body
        if not found:
            TextLabel(body, "No icons yet", 15, "semibold").pack(pady=(px(70) + px(CommandBar.HEIGHT), px(4)))
            TextLabel(body, "Add icon files to the assets folder", T_CAP, color=SUBTLE).pack()
            return
        norm = lambda x: re.sub(r"[^a-z0-9]", "", x.lower())
        order = [norm(n) for n in ICON_ORDER]  # built-in order (always works)
        for d in (ASSETS, APP_DIR, BUNDLE):  # optional order.txt overrides it
            for fn in ("order.txt", "order.txt.txt"):
                try:
                    with open(os.path.join(d, fn), encoding="utf-8-sig") as fh:
                        got = [norm(l) for l in fh if l.strip()]
                    if got:
                        order = got
                        raise StopIteration
                except OSError:
                    pass
                except StopIteration:
                    break
            else:
                continue
            break
        nat = lambda t: [int(c) if c.isdigit() else c for c in re.split(r"(\d+)", t.lower())]
        def rank(t):
            n = norm(t)
            if n in order:
                return (order.index(n), nat(t))
            part = [o for o in order if o in n]  # e.g. "folder_hard_drive" -> "harddrive"
            if part:
                return (order.index(max(part, key=len)), nat(t))
            return (len(order), nat(t))
        if self.sort_key == "az":
            ordered = sorted(found.values(), key=lambda t: nat(t[0]))
        elif self.sort_key == "za":
            ordered = sorted(found.values(), key=lambda t: nat(t[0]), reverse=True)
        else:
            ordered = sorted(found.values(), key=lambda t: rank(t[0]))
        canvas = self.icon_area.canvas
        cw, ch = canvas.winfo_width(), canvas.winfo_height()
        cols = max(1, cw // (zw(CARD_W) + 2 * px(4))) if cw > 50 else 0
        rows_on_screen = -(-ch // (z(CARD_SIZE) + 2 * px(4))) if ch > 50 else 0
        for i, (_, path) in enumerate(ordered):
            row, col = (i // cols, i % cols) if cols else (0, 0)
            visible = cols and row < rows_on_screen
            quick = animate == "quick"
            lim, rs, cs = (70, 14, 7) if quick else (420, 45, 22)
            reveal = int(min(lim, row * rs + col * cs)) if visible and animate else None
            card = IconCard(self.icon_area.canvas, path, self.select, reveal, 150 if quick else 300)
            card.selected = path == self.selected
            if reveal is None:
                card.refresh()
            self.cards[path] = card
        self.reflow()

    def reflow(self, width=None):
        if not self.cards:
            return
        area = self.icon_area
        width = width or area.canvas.winfo_width()
        margin = px(4)
        cell = z(CARD_SIZE) + 2 * margin
        cellw = zw(CARD_W) + 2 * margin
        cols = max(1, width // cellw)
        offset = max(0, (width - cols * cellw) // 2)  # the grid is centered
        changed = offset != area.x_offset
        area.x_offset = offset
        if cols != self._cols:
            self._cols = cols
            top = px(CommandBar.HEIGHT) + px(1)  # icons scroll under the toolbar, but start below it
            for i, card in enumerate(self.cards.values()):
                card.place(margin + i % cols * cellw, top + 2 * margin + i // cols * cell)
            area.fixed_height = -(-len(self.cards) // cols) * cell + top + 3 * margin
            self.cards_version += 1
            changed = True
        if changed:
            area._fit()
            if hasattr(self, "toolbar"):
                self.toolbar._draw()

    # ---- icon view (palette / sort / size), remembered between runs
    def _init_view(self):
        global ICON_ZOOM
        try:
            with open(os.path.join(APP_DIR, "settings.json"), "r", encoding="utf-8") as fh:
                saved = json.load(fh)
        except (OSError, ValueError):
            saved = {}
        self.palette_name = saved.get("palette", "")
        self.sort_key = saved.get("sort", "default") if saved.get("sort") in dict(SORTS) else "default"
        self.zoom_key = saved.get("zoom", "M") if saved.get("zoom") in dict(ZOOMS) else "M"
        ICON_ZOOM = dict(ZOOMS)[self.zoom_key]
        self.palettes, self.palette_dir = [], ASSETS
        self.cards_version = 0
        self._scan_palettes()

    def _scan_palettes(self):
        self.palettes = find_palettes()
        names = [n for n, _, _ in self.palettes]
        if self.palette_name not in names:
            pref = next((n for n in names if n.lower() in ("blue", "default")), None)
            self.palette_name = pref or (names[0] if names else "")
        self.palette_dir = next((d for n, d, _ in self.palettes if n == self.palette_name), ASSETS)

    def palettes_view(self):
        return [(n, d, c) for n, d, c in self.palettes]

    def _save_view(self):
        try:
            with open(os.path.join(APP_DIR, "settings.json"), "w", encoding="utf-8") as fh:
                json.dump({"palette": self.palette_name, "sort": self.sort_key, "zoom": self.zoom_key}, fh)
        except OSError:
            pass

    def _view_changed(self, animate="quick"):
        self.toolbar.refresh()  # the segment slides right away
        if getattr(self, "_view_job", None):
            self.root.after_cancel(self._view_job)  # rapid clicks: only rebuild for the last one
        def go():
            self._view_job = None
            self._save_view()
            self.load_icons(animate=animate)
            self._prewarm()
        self._view_job = self.root.after(1, go)

    def _prewarm(self):
        """While idle, pre-render the other icon sizes so S/M/L switches are instant."""
        global ICON_ZOOM
        if getattr(self, "_warm_job", None):
            self.root.after_cancel(self._warm_job)
        todo = [(k, v) for k, v in ZOOMS if k != self.zoom_key]
        paths = [c.path for c in self.cards.values()]
        names = {c.path: c.name for c in self.cards.values()}
        queue = [(k, v, p) for k, v in todo for p in paths]

        def chunk():
            global ICON_ZOOM
            self._warm_job = None
            keep = ICON_ZOOM
            try:
                for k, v, p in queue[:3]:
                    ICON_ZOOM = v
                    t = make_thumb(p)
                    img = card_image(t, "n", names[p], p)
                    card_photo(img, (p, _mtime(p), "n", names[p], v, S))
            finally:
                ICON_ZOOM = keep
            del queue[:3]
            if queue:
                self._warm_job = self.root.after(25, chunk)
        if queue:
            self._warm_job = self.root.after(400, chunk)

    def set_palette(self, name):
        if name != self.palette_name:
            self.palette_name = name
            self._view_changed()

    def set_sort(self, key):
        if key != self.sort_key:
            self.sort_key = key
            self._view_changed()

    def set_zoom(self, key):
        global ICON_ZOOM
        if key != self.zoom_key:
            self.zoom_key = key
            ICON_ZOOM = dict(ZOOMS)[key]
            self._view_changed()

    def select(self, path):
        self.selected = path
        for p, c in self.cards.items():
            c.selected = p == path
            c.refresh()
        self.say(f"Selected: {os.path.splitext(os.path.basename(path))[0]}")

    # ---- actions
    def _run(self, job, verb):
        """Run a folder job in a thread so the window never freezes."""
        if self.busy:
            return
        self.busy = True
        self.admin_btn.pack_forget()
        self.log_btn.pack_forget()
        state = {"n": 0, "res": None}

        def work():
            try:
                state["res"] = job(lambda n: state.__setitem__("n", n))
            except Exception as e:
                state["res"] = {"ok": 0, "failed": [("", str(e), False)], "skipped": []}

        threading.Thread(target=work, daemon=True).start()

        def poll():
            if state["res"] is None:
                self.say(f"Working... {state['n']} folders")
                self.root.after(100, poll)
            else:
                self.busy = False
                self._finish(state["res"], verb)

        poll()

    def _finish(self, res, verb):
        ok, fails, skipped = res["ok"], res["failed"], res["skipped"]
        msg = f"{verb.capitalize()} {ok} folder(s)"
        if skipped:
            msg += f" · skipped {len(skipped)}"
        if fails:
            msg += f" · {len(fails)} failed"
        if fails or skipped:
            self.log_path = core.write_log(res, verb)
        if fails and any(d for _, _, d in fails) and not core.is_admin():
            self.admin_btn.pack(side="right")
            msg += " (needs admin)"
        elif fails or skipped:
            self.log_btn.pack(side="right")
        self.say(msg, BAD if fails else GOOD)

    def open_log(self):
        try:
            os.startfile(self.log_path)
        except Exception:
            pass

    def restart_admin(self):
        if core.relaunch_admin():
            self._save_window_size()
            self.root.destroy()

    def apply(self):
        if not self.folders or not self.selected:
            return self.say("Add a folder and pick an icon first", BAD)
        folders, icon, rec, hid = list(self.folders), self.selected, self.recurse, self.hidden
        self._run(lambda p: core.apply_icon(folders, icon, rec, hid, p), "applied to")

    def reset(self):
        if not self.folders:
            return self.say("Add a folder first", BAD)
        folders, rec, hid = list(self.folders), self.recurse, self.hidden
        self._run(lambda p: core.reset_icons(folders, rec, hid, p), "reset")


if __name__ == "__main__":
    App().root.mainloop()
