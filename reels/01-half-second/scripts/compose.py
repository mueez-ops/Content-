"""Composites the 15 s reel: shots + kinetic type + UI mock + archival finish, then encodes.

    python compose.py                 -> build/halfsecond_reel_01.mp4 (+ _no_music.mp4)
    python compose.py --frames 120-180 --png build/check   (write PNG stills only)

Timeline (30 fps, 120 BPM => 1 beat = 15 frames):
    f000-029  0.0-1.0s   "0.5s" stopwatch card
    f030-119  1.0-4.0s   boring ad in a realistic phone feed, flick-scrolls past, X
    f120-359  4.0-12.0s  Halfsecond version, every cut on the beat grid
    f360-449  12.0-15.0s end card
Style parameters live in STYLE; shot/timecode decisions live in CUTS and the section functions.
"""
import math
import os
import subprocess
import sys
from functools import lru_cache

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
R = os.path.join(ROOT, "renders")
FONTS = os.path.join(ROOT, "assets", "fonts")
W, H, FPS, NF = 1080, 1920, 30, 450

STYLE = {
    "ink": (14, 13, 12),
    "bone": (240, 233, 221),
    "paper": (236, 229, 216),
    "accent": (255, 77, 34),
    "grain": 0.045,        # std of luminance grain on colour shots
    "grain_bw": 0.06,      # std on black & white shots
    "bloom": 0.32,
    "halation": (1.0, 0.45, 0.25),
    "vignette": 0.28,
}
INK, BONE, PAPER, ACCENT = STYLE["ink"], STYLE["bone"], STYLE["paper"], STYLE["accent"]


# ------------------------------------------------------------------ utils
def font(name, size):
    return _font(name, int(size))


@lru_cache(None)
def _font(name, size):
    return ImageFont.truetype(os.path.join(FONTS, name), size)


SERIF, SERIF_I = "InstrumentSerif-Regular.ttf", "InstrumentSerif-Italic.ttf"
MONO, MONO_B = "SpaceMono-Regular.ttf", "SpaceMono-Bold.ttf"
UGLY = "LiberationSans-Bold.ttf"
UI, UI_B = "Inter-Regular.otf", "Inter-SemiBold.otf"


def clamp(x, a=0.0, b=1.0):
    return max(a, min(b, x))


def prog(f, a, b):
    return clamp((f - a) / max(1e-6, b - a))


def ease_out(x):
    return 1 - (1 - x) ** 4


def ease_in_out(x):
    return 0.5 - 0.5 * math.cos(math.pi * x)


@lru_cache(maxsize=64)
def shot(name, idx):
    """Shot frame (1-based, clamped) scaled to the canvas."""
    d = os.path.join(R, name)
    files = sorted(x for x in os.listdir(d) if x.endswith(".png"))
    idx = int(clamp(idx, 1, len(files)))
    im = Image.open(os.path.join(d, files[idx - 1])).convert("RGB")
    if im.size != (W, H):
        im = im.resize((W, H), Image.LANCZOS)
    return im


def shot_count(name):
    return len([x for x in os.listdir(os.path.join(R, name)) if x.endswith(".png")])


def shot_blend(name, pos):
    """Fractional frame position -> blended frame (used for slight slow-motion)."""
    a = math.floor(pos)
    t = pos - a
    if t < 0.02:
        return shot(name, a)
    return Image.blend(shot(name, a), shot(name, a + 1), t)


def bw(im, tint=(1.04, 1.0, 0.93), contrast=1.12):
    a = np.asarray(im).astype(np.float32) / 255
    y = a @ np.array([0.299, 0.587, 0.114], np.float32)
    y = np.clip((y - 0.5) * contrast + 0.5, 0, 1)
    out = np.stack([y * tint[0], y * tint[1], y * tint[2]], -1)
    return Image.fromarray((np.clip(out, 0, 1) * 255).astype(np.uint8))


def zoom(im, s, cx=0.5, cy=0.5):
    if abs(s - 1) < 1e-3:
        return im
    w, h = im.size
    nw, nh = w / s, h / s
    x0, y0 = cx * w - nw / 2, cy * h - nh / 2
    return im.resize((w, h), Image.BICUBIC, box=(x0, y0, x0 + nw, y0 + nh))


def text_w(txt, f, tracking=0):
    return f.getlength(txt) + tracking * max(0, len(txt) - 1)


def draw_text(img, txt, f, xy, fill, anchor="ls", tracking=0, alpha=1.0):
    """Text with optional letter tracking + opacity, drawn via an RGBA layer."""
    if alpha <= 0:
        return
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    x, y = xy
    if tracking == 0:
        d.text((x, y), txt, font=f, fill=(*fill, int(255 * alpha)), anchor=anchor)
    else:
        tw = text_w(txt, f, tracking)
        if anchor[0] == "m":
            x -= tw / 2
        elif anchor[0] == "r":
            x -= tw
        for ch in txt:
            d.text((x, y), ch, font=f, fill=(*fill, int(255 * alpha)), anchor="l" + anchor[1])
            x += f.getlength(ch) + tracking
    img.alpha_composite(layer) if img.mode == "RGBA" else img.paste(layer, (0, 0), layer)


def rise_text(img, txt, f, xy, fill, f_now, f_in, dur=7, anchor="ls", tracking=0, dist=None):
    """Kinetic reveal: line slides up from behind a mask edge at its baseline."""
    p = ease_out(prog(f_now, f_in, f_in + dur))
    if p <= 0:
        return
    asc, desc = f.getmetrics()
    dist = dist if dist is not None else asc * 0.9
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    x, y = xy
    draw_text(layer, txt, f, (x, y + (1 - p) * dist), fill, anchor, tracking)
    # Mask: everything below baseline+descender is hidden while rising.
    m = Image.new("L", img.size, 0)
    ImageDraw.Draw(m).rectangle([0, 0, W, y + desc + 4], fill=255)
    a = ImageChops.multiply(layer.getchannel("A"), m)
    layer.putalpha(a)
    img.paste(layer, (0, 0), layer)


def grad_overlay(img, top=True, height=700, strength=0.55, color=(0, 0, 0)):
    a = np.zeros((H, 1), np.float32)
    ys = np.arange(H)[:, None]
    if top:
        a = np.clip(1 - ys / height, 0, 1) ** 1.6 * strength
    else:
        a = np.clip((ys - (H - height)) / height, 0, 1) ** 1.6 * strength
    arr = np.asarray(img).astype(np.float32)
    arr = arr * (1 - a[..., None]) + np.array(color, np.float32) * a[..., None]
    return Image.fromarray(arr.astype(np.uint8))


def tag(img, txt, f_now, f_in, y=148, x=80, color=BONE, dot=ACCENT):
    """Small archival index tag, e.g. 'A — THE USUAL AD'."""
    p = ease_out(prog(f_now, f_in, f_in + 6))
    if p <= 0:
        return
    d = ImageDraw.Draw(img)
    d.ellipse([x, y - 21, x + 14, y - 7], fill=dot)
    draw_text(img, txt, font(MONO, 30), (x + 30, y), color, tracking=3, alpha=p)


def logo(img, cx, cy, scale, f_now, f_in, color=INK, accent=ACCENT):
    """Halfsecond logo: half-filled disc + serif wordmark."""
    r = int(70 * scale)
    p = ease_out(prog(f_now, f_in, f_in + 9))
    if p <= 0:
        return
    mark = Image.new("RGBA", (2 * r + 8, 2 * r + 8), (0, 0, 0, 0))
    d = ImageDraw.Draw(mark)
    d.ellipse([4, 4, 4 + 2 * r, 4 + 2 * r], outline=(*color, 255), width=max(3, int(6 * scale)))
    # Left half fills in like a stopwatch hand sweeping half a turn.
    d.pieslice([4, 4, 4 + 2 * r, 4 + 2 * r], 90, 90 + 180 * p, fill=(*accent, 255))
    fw = font(SERIF, 150 * scale)
    fi = font(SERIF_I, 150 * scale)
    w1, w2 = fi.getlength("half"), fw.getlength("second")
    gap = 28 * scale
    total = 2 * r + gap + w1 + w2
    x0 = cx - total / 2
    img.paste(mark, (int(x0 - 4), int(cy - r - 4)), mark)
    q = ease_out(prog(f_now, f_in + 3, f_in + 12))
    base = cy + 52 * scale
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw_text(layer, "half", fi, (x0 + 2 * r + gap, base + (1 - q) * 40), color)
    draw_text(layer, "second", fw, (x0 + 2 * r + gap + w1, base + (1 - q) * 40), color)
    m = Image.new("L", img.size, 0)
    ImageDraw.Draw(m).rectangle([0, 0, W, base + 40 * scale], fill=255)
    layer.putalpha(ImageChops.multiply(layer.getchannel("A"), m))
    img.paste(layer, (0, 0), layer)


# ------------------------------------------------------------------ A: 0.5s card
def sec_intro(f):
    img = Image.new("RGB", (W, H), (10, 10, 9))
    d = ImageDraw.Draw(img)
    # Stopwatch ring drains over the first second; ticks every 0.25 s.
    cx, cy, r = W // 2, 860, 380
    frac = 1 - f / 30
    d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=(52, 50, 47), width=4)
    d.arc([cx - r, cy - r, cx + r, cy + r], -90, -90 + 360 * frac, fill=ACCENT, width=8)
    for k in range(60):
        a = math.radians(k * 6 - 90)
        l = 34 if k % 15 == 0 else 14
        d.line([(cx + (r - 20) * math.cos(a), cy + (r - 20) * math.sin(a)),
                (cx + (r - 20 - l) * math.cos(a), cy + (r - 20 - l) * math.sin(a))], fill=(90, 86, 80), width=3)
    pulse = 1 + 0.035 * math.exp(-((f % 7.5) / 2.0))
    big = font(SERIF, 420 * pulse)
    draw_text(img, "0.5", big, (cx - 70, cy + 140), BONE, anchor="ms")
    draw_text(img, "s", font(SERIF_I, 420 * pulse), (cx + big.getlength("0.5") / 2 - 60, cy + 140), ACCENT, anchor="ls")
    words = ["That's", "how", "long", "your", "ad", "gets."]
    fm = font(SERIF_I, 92)
    line = " ".join(words)
    x = cx - fm.getlength(line) / 2
    for i, wd in enumerate(words):
        rise_text(img, wd, fm, (x, 1430), BONE, f, 2 + i * 2, dur=6)
        x += fm.getlength(wd + " ")
    draw_text(img, f"00:00:{f:02d}", font(MONO, 30), (80, 148), (120, 115, 108), tracking=2)
    draw_text(img, "HALFSECOND / 001", font(MONO, 30), (W - 80, 148), (120, 115, 108), anchor="rs", tracking=2)
    return img, "color"


# ------------------------------------------------------------------ B: boring ad
# A realistic, unbranded phone + social feed. Geometry in iOS points (screen = 393 pt wide),
# drawn at 2x and downsampled for clean anti-aliased edges.
PHONE = (140, 196, 940, 1862)          # outer body on the canvas
BEZEL, FRAME_W, R_OUT = 22, 7, 120
SCREEN = (PHONE[0] + BEZEL, PHONE[1] + BEZEL, PHONE[2] - BEZEL, PHONE[3] - BEZEL)
SW, SH = SCREEN[2] - SCREEN[0], SCREEN[3] - SCREEN[1]
R_SCR = R_OUT - BEZEL
K = 2                                  # supersampling
PT = SW / 393                          # px per point at 1x
STATUS_PT, HEADER_PT, TAB_PT = 54, 44, 83
UI_TXT, UI_GREY, UI_LINE, UI_LINK = (0, 0, 0), (115, 115, 115), (219, 219, 219), (0, 55, 107)


def _pt(v, k=K):
    return v * PT * k


def _icon(d, kind, x, y, s, k=K, fill=UI_TXT, w=1.9):
    """Line icons in a generic iOS style; (x, y) is the icon centre in points, s its size in points."""
    P = lambda a, b: (_pt(x + a * s / 2, k), _pt(y + b * s / 2, k))
    lw = max(1, int(_pt(w, k)))
    if kind == "heart":
        pts = []
        for i in range(73):
            t = math.radians(i * 5)
            hx = 16 * math.sin(t) ** 3
            hy = -(13 * math.cos(t) - 5 * math.cos(2 * t) - 2 * math.cos(3 * t) - math.cos(4 * t))
            pts.append(P(hx / 17, (hy + 2) / 17))
        d.line(pts, fill=fill, width=lw, joint="curve")
    elif kind == "comment":
        d.ellipse([P(-0.92, -0.85), P(0.92, 0.85)], outline=fill, width=lw)
        d.line([P(-0.62, 0.62), P(-0.9, 0.98), P(-0.32, 0.82)], fill=(255, 255, 255), width=lw * 2)
        d.line([P(-0.62, 0.6), P(-0.9, 0.98), P(-0.36, 0.84)], fill=fill, width=lw, joint="curve")
    elif kind == "share":
        d.line([P(-0.95, -0.8), P(0.95, -0.8), P(0.05, 0.95), P(-0.12, -0.12), P(-0.95, -0.8)], fill=fill, width=lw, joint="curve")
        d.line([P(-0.12, -0.12), P(0.95, -0.8)], fill=fill, width=lw)
    elif kind == "bookmark":
        d.line([P(-0.7, -0.95), P(0.7, -0.95), P(0.7, 0.95), P(0, 0.4), P(-0.7, 0.95), P(-0.7, -0.95)], fill=fill, width=lw, joint="curve")
    elif kind == "home":
        d.polygon([P(-0.9, -0.05), P(0, -0.92), P(0.9, -0.05), P(0.9, 0.95), P(0.25, 0.95), P(0.25, 0.35),
                   P(-0.25, 0.35), P(-0.25, 0.95), P(-0.9, 0.95)], fill=fill)
    elif kind == "search":
        d.ellipse([P(-0.85, -0.85), P(0.45, 0.45)], outline=fill, width=lw)
        d.line([P(0.35, 0.35), P(0.95, 0.95)], fill=fill, width=lw)
    elif kind == "plus":
        d.rounded_rectangle([P(-0.9, -0.9), P(0.9, 0.9)], radius=_pt(s * 0.22, k), outline=fill, width=lw)
        d.line([P(0, -0.45), P(0, 0.45)], fill=fill, width=lw)
        d.line([P(-0.45, 0), P(0.45, 0)], fill=fill, width=lw)
    elif kind == "play":
        d.rounded_rectangle([P(-0.9, -0.9), P(0.9, 0.9)], radius=_pt(s * 0.22, k), outline=fill, width=lw)
        d.polygon([P(-0.25, -0.35), P(0.4, 0), P(-0.25, 0.35)], fill=fill)
    elif kind == "messages":
        d.line([P(-0.95, -0.8), P(0.95, -0.8), P(0.05, 0.95), P(-0.12, -0.12), P(-0.95, -0.8)], fill=fill, width=lw, joint="curve")
    elif kind == "dots":
        for dx in (-0.6, 0, 0.6):
            d.ellipse([P(dx - 0.11, -0.11), P(dx + 0.11, 0.11)], fill=fill)
    elif kind == "chevron":
        d.line([P(-0.3, -0.6), P(0.3, 0), P(-0.3, 0.6)], fill=fill, width=lw, joint="curve")


def _status_bar(k=1):
    """Fixed iOS status bar (time, signal, wifi, battery)."""
    im = Image.new("RGB", (int(SW * k), int(_pt(STATUS_PT, k))), (255, 255, 255))
    d = ImageDraw.Draw(im)
    d.text((_pt(62, k), _pt(31, k)), "9:41", font=font(UI_B, _pt(17, k)), fill=UI_TXT, anchor="mm")
    for i in range(4):  # signal
        x = 293 + i * 4.6
        d.rounded_rectangle([_pt(x, k), _pt(35 - 3.2 - i * 2.2, k), _pt(x + 3.2, k), _pt(35, k)], radius=_pt(0.8, k), fill=UI_TXT)
    cx, cy = _pt(323, k), _pt(35, k)
    for r in (11, 7.2, 3.4):  # wifi
        rr = _pt(r, k)
        d.arc([cx - rr, cy - rr, cx + rr, cy + rr], 225, 315, fill=UI_TXT, width=max(1, int(_pt(2.1, k))))
    d.pieslice([cx - _pt(2.6, k), cy - _pt(2.6, k), cx + _pt(2.6, k), cy + _pt(2.6, k)], 225, 315, fill=UI_TXT)
    bx = 341
    d.rounded_rectangle([_pt(bx, k), _pt(24, k), _pt(bx + 25, k), _pt(36, k)], radius=_pt(3.6, k),
                        outline=(150, 150, 150), width=max(1, int(_pt(1, k))))
    d.rounded_rectangle([_pt(bx + 2, k), _pt(26, k), _pt(bx + 19, k), _pt(34, k)], radius=_pt(2, k), fill=UI_TXT)
    d.rounded_rectangle([_pt(bx + 26, k), _pt(28, k), _pt(bx + 27.6, k), _pt(32, k)], radius=_pt(1, k), fill=(150, 150, 150))
    return im


def _header(k=1):
    im = Image.new("RGB", (int(SW * k), int(_pt(HEADER_PT, k))), (255, 255, 255))
    d = ImageDraw.Draw(im)
    d.text((_pt(16, k), _pt(22, k)), "Following", font=font(UI_B, _pt(22, k)), fill=UI_TXT, anchor="lm")
    _icon(d, "chevron", 128, 23, 10, k, w=2.0)
    _icon(d, "heart", 330, 22, 24, k)
    _icon(d, "messages", 367, 22, 23, k)
    return im


def _tab_bar(k=1):
    im = Image.new("RGB", (int(SW * k), int(_pt(TAB_PT, k))), (255, 255, 255))
    d = ImageDraw.Draw(im)
    d.line([(0, 0), (im.width, 0)], fill=UI_LINE, width=max(1, int(_pt(0.5, k))))
    for i, kind in enumerate(["home", "search", "plus", "play"]):
        _icon(d, kind, 39 + i * 78.5, 24, 24, k)
    x, y, r = 353, 24, 13
    d.ellipse([_pt(x - r, k), _pt(y - r, k), _pt(x + r, k), _pt(y + r, k)], fill=(205, 196, 186))
    # Home indicator
    d.rounded_rectangle([_pt(196.5 - 67, k), _pt(TAB_PT - 13, k), _pt(196.5 + 67, k), _pt(TAB_PT - 8, k)],
                        radius=_pt(2.5, k), fill=UI_TXT)
    return im


def _photo_landscape(w, h):
    """Procedural travel photo: dusk sky, sun, sea and two hill silhouettes."""
    yy = np.linspace(0, 1, h)[:, None]
    top, mid = np.array([92, 118, 168]), np.array([246, 170, 120])
    sky = top * (1 - yy) ** 1.4 + mid * (1 - (1 - yy) ** 1.4)
    a = np.repeat(sky[:, None, :], w, 1).reshape(h, w, 3)
    im = Image.fromarray(a.astype(np.uint8))
    d = ImageDraw.Draw(im)
    d.ellipse([w * 0.56, h * 0.42, w * 0.78, h * 0.42 + w * 0.22], fill=(255, 226, 170))
    rng = np.random.default_rng(3)
    for base, col, amp in ((0.62, (88, 74, 96), 0.08), (0.7, (52, 46, 66), 0.06)):
        xs = np.linspace(0, w, 40)
        ys = h * base - h * amp * (np.sin(xs / w * 6 + rng.uniform(0, 6)) * 0.6 + rng.uniform(-0.3, 0.3, 40))
        d.polygon([(0, h)] + list(zip(xs, ys)) + [(w, h)], fill=col)
    d.rectangle([0, h * 0.8, w, h], fill=(40, 52, 78))
    d.rectangle([w * 0.58, h * 0.8, w * 0.76, h * 0.805], fill=(255, 210, 160))
    return im.filter(ImageFilter.GaussianBlur(w / 400))


def _photo_food(w, h):
    """Procedural food photo: top-down bowl on a warm table."""
    im = Image.new("RGB", (w, h), (196, 150, 108))
    d = ImageDraw.Draw(im)
    for i in range(0, h, int(h / 9)):
        d.rectangle([0, i, w, i + h / 18], fill=(186, 140, 98))
    cx, cy, r = w * 0.5, h * 0.5, w * 0.36
    d.ellipse([cx - r + w * 0.02, cy - r + w * 0.03, cx + r + w * 0.02, cy + r + w * 0.03], fill=(150, 110, 80))
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(246, 244, 238))
    r2 = r * 0.72
    d.ellipse([cx - r2, cy - r2, cx + r2, cy + r2], fill=(232, 186, 92))
    rng = np.random.default_rng(8)
    for _ in range(26):
        a, rr = rng.uniform(0, 6.28), rng.uniform(0, r2 * 0.8)
        x, y, s = cx + rr * math.cos(a), cy + rr * math.sin(a), rng.uniform(w * 0.02, w * 0.05)
        c = [(84, 140, 70), (210, 70, 50), (250, 236, 200)][rng.integers(0, 3)]
        d.ellipse([x - s, y - s * 0.7, x + s, y + s * 0.7], fill=c)
    return im.filter(ImageFilter.GaussianBlur(w / 500))


@lru_cache(1)
def feed_content():
    """The scrolling part of the feed (stories + three posts). Returns (image at 1x, post-2 top in px)."""
    k = K
    Wc = int(SW * k)
    posts_pt = [104 + 0.5]
    post_h = 54 + 491 + 44 + 46 + 130
    total_pt = posts_pt[0] + 3 * (post_h + 12)
    cv = Image.new("RGB", (Wc, int(_pt(total_pt, k))), (255, 255, 255))
    d = ImageDraw.Draw(cv)
    # Stories row
    names = ["Your story", "maya.k", "dailyfit", "studio.no9", "leo_eats"]
    tones = [(214, 206, 196), (198, 180, 160), (170, 186, 196), (205, 170, 150), (186, 196, 170)]
    for i, (n, c) in enumerate(zip(names, tones)):
        x = 10 + i * 80 + 33
        r = 33
        if i:
            d.ellipse([_pt(x - r, k), _pt(8, k), _pt(x + r, k), _pt(8 + 2 * r, k)], outline=ACCENT, width=int(_pt(2.4, k)))
        rr = r - 4.5
        d.ellipse([_pt(x - rr, k), _pt(8 + 4.5, k), _pt(x + rr, k), _pt(8 + 4.5 + 2 * rr, k)], fill=c)
        d.text((_pt(x, k), _pt(8 + 2 * r + 13, k)), n, font=font(UI, _pt(11.5, k)), fill=UI_TXT, anchor="mm")
        if i == 0:
            d.ellipse([_pt(x + 12, k), _pt(52, k), _pt(x + 32, k), _pt(72, k)], fill=(0, 149, 246), outline=(255, 255, 255), width=int(_pt(2.5, k)))
            d.line([(_pt(x + 22, k), _pt(57, k)), (_pt(x + 22, k), _pt(67, k))], fill=(255, 255, 255), width=int(_pt(2, k)))
            d.line([(_pt(x + 17, k), _pt(62, k)), (_pt(x + 27, k), _pt(62, k))], fill=(255, 255, 255), width=int(_pt(2, k)))
    d.line([(0, _pt(104, k)), (Wc, _pt(104, k))], fill=UI_LINE, width=max(1, int(_pt(0.5, k))))

    def post(y, kind):
        name = ["yourbrand", "travelgram", "foodspot"][kind]
        sub = ["Sponsored", "Lisbon, Portugal", "Original audio"][kind]
        d.ellipse([_pt(12, k), _pt(y + 11, k), _pt(44, k), _pt(y + 43, k)], fill=[(222, 214, 204), (170, 186, 196), (205, 170, 150)][kind])
        d.text((_pt(28, k), _pt(y + 27.5, k)), name[0].upper(), font=font(UI_B, _pt(14, k)), fill=(255, 255, 255), anchor="mm")
        d.text((_pt(54, k), _pt(y + 21, k)), name, font=font(UI_B, _pt(13.5, k)), fill=UI_TXT, anchor="lm")
        d.text((_pt(54, k), _pt(y + 37, k)), sub, font=font(UI, _pt(12, k)), fill=UI_TXT, anchor="lm")
        _icon(d, "dots", 372, y + 27, 16, k)
        iy = y + 54
        iw, ih = int(_pt(393, k)), int(_pt(491, k))
        if kind == 0:
            src = shot("boring", 1)
            ch = int(W * 491 / 393)
            top = (H - ch) // 2 + 40
            photo = src.crop((0, top, W, top + ch)).resize((iw, ih), Image.LANCZOS)
            pd = ImageDraw.Draw(photo)
            # The 'design': shouty red discount + yellow button, default fonts.
            pd.text((iw / 2, ih * 0.15), "20% OFF", font=font(UGLY, iw * 0.15), fill=(230, 20, 20), anchor="mm",
                    stroke_width=int(iw * 0.006), stroke_fill=(0, 0, 0))
            bx0, by0, bx1, by1 = iw * 0.27, ih * 0.82, iw * 0.73, ih * 0.92
            pd.rounded_rectangle([bx0, by0, bx1, by1], radius=iw * 0.02, fill=(255, 221, 0), outline=(0, 0, 0), width=int(iw * 0.004))
            pd.text((iw / 2, (by0 + by1) / 2), "BUY NOW!!", font=font(UGLY, iw * 0.07), fill=(0, 0, 0), anchor="mm")
        elif kind == 1:
            photo = _photo_landscape(iw, ih)
        else:
            photo = _photo_food(iw, ih)
        cv.paste(photo, (0, int(_pt(iy, k))))
        ay = iy + 491
        if kind == 0:
            d.rectangle([0, _pt(ay, k), Wc, _pt(ay + 44, k)], fill=(239, 239, 239))
            d.text((_pt(14, k), _pt(ay + 22, k)), "Shop now", font=font(UI_B, _pt(14, k)), fill=UI_TXT, anchor="lm")
            _icon(d, "chevron", 378, ay + 22, 12, k, w=2.0)
            ay += 44
        _icon(d, "heart", 24, ay + 23, 24, k)
        _icon(d, "comment", 64, ay + 23, 23, k)
        _icon(d, "share", 104, ay + 23, 22, k)
        _icon(d, "bookmark", 372, ay + 23, 22, k)
        ty = ay + 50
        likes = ["12 likes", "2,481 likes", "8,903 likes"][kind]
        d.text((_pt(14, k), _pt(ty, k)), likes, font=font(UI_B, _pt(14, k)), fill=UI_TXT, anchor="lm")
        cap = ["New perfume available now!! 20% OFF", "golden hour never misses", "the best bowl in town"][kind]
        fb = font(UI_B, _pt(14, k))
        d.text((_pt(14, k), _pt(ty + 21, k)), name, font=fb, fill=UI_TXT, anchor="lm")
        d.text((_pt(14, k) + fb.getlength(name + " "), _pt(ty + 21, k)), cap, font=font(UI, _pt(14, k)), fill=UI_TXT, anchor="lm")
        if kind == 0:
            d.text((_pt(14, k), _pt(ty + 40, k)), "BUY NOW link in bio #perfume #sale #buynow", font=font(UI, _pt(14, k)), fill=UI_LINK, anchor="lm")
        d.text((_pt(14, k), _pt(ty + 61, k)), "View all 3 comments", font=font(UI, _pt(14, k)), fill=UI_GREY, anchor="lm")
        d.text((_pt(14, k), _pt(ty + 80, k)), ["2 hours ago", "5 hours ago", "1 day ago"][kind], font=font(UI, _pt(11, k)), fill=UI_GREY, anchor="lm")
        return y + post_h + (0 if kind else 0)

    y = posts_pt[0]
    tops = []
    for kind in range(3):
        tops.append(y)
        y = post(y, kind) + 12
    small = cv.resize((SW, int(cv.height / k)), Image.LANCZOS)
    return small, _pt(tops[1], 1)


@lru_cache(1)
def phone_layers():
    """Static device chrome: shadow, body (frame, buttons, bezel) and the glass overlay; plus the screen mask."""
    k = K
    pw, ph = (PHONE[2] - PHONE[0]) * k, (PHONE[3] - PHONE[1]) * k
    pad = 20 * k
    body = Image.new("RGBA", (pw + 2 * pad, ph + 2 * pad), (0, 0, 0, 0))
    d = ImageDraw.Draw(body)
    ti_dark, ti_mid, ti_hi = (38, 37, 40, 255), (70, 69, 74, 255), (150, 148, 152, 255)
    # Side buttons (action, volume up/down on the left, side button on the right).
    for (x0, y0, y1) in ((-5, 250, 300), (-5, 360, 450), (-5, 480, 570)):
        d.rounded_rectangle([pad + x0 * k, pad + y0 * k, pad + 10 * k, pad + y1 * k], radius=4 * k, fill=ti_mid)
    d.rounded_rectangle([pad + pw - 10 * k, pad + 400 * k, pad + pw + 5 * k, pad + 560 * k], radius=4 * k, fill=ti_mid)
    # Titanium frame with a bright machined edge, then the black bezel.
    d.rounded_rectangle([pad, pad, pad + pw, pad + ph], radius=R_OUT * k, fill=ti_dark)
    d.rounded_rectangle([pad + 1.5 * k, pad + 1.5 * k, pad + pw - 1.5 * k, pad + ph - 1.5 * k], radius=R_OUT * k - 2 * k,
                        outline=ti_hi, width=int(2 * k))
    d.rounded_rectangle([pad + 4 * k, pad + 4 * k, pad + pw - 4 * k, pad + ph - 4 * k], radius=R_OUT * k - 4 * k,
                        outline=ti_mid, width=int(3 * k))
    d.rounded_rectangle([pad + FRAME_W * k, pad + FRAME_W * k, pad + pw - FRAME_W * k, pad + ph - FRAME_W * k],
                        radius=(R_OUT - FRAME_W) * k, fill=(6, 6, 7, 255))
    # Cut the screen out.
    hole = Image.new("L", body.size, 0)
    ImageDraw.Draw(hole).rounded_rectangle([pad + BEZEL * k, pad + BEZEL * k, pad + pw - BEZEL * k, pad + ph - BEZEL * k],
                                           radius=R_SCR * k, fill=255)
    body.putalpha(ImageChops.subtract(body.getchannel("A"), hole))
    body = body.resize((body.width // k, body.height // k), Image.LANCZOS)
    smask = hole.resize(body.size, Image.LANCZOS).crop((pad // k + BEZEL, pad // k + BEZEL, pad // k + BEZEL + SW, pad // k + BEZEL + SH))
    # Glass: Dynamic Island, a soft diagonal reflection and a faint inner edge.
    glass = Image.new("RGBA", (SW * k, SH * k), (0, 0, 0, 0))
    g = ImageDraw.Draw(glass)
    iw, ih, it = _pt(126, k), _pt(37, k), _pt(11, k)
    g.rounded_rectangle([SW * k / 2 - iw / 2, it, SW * k / 2 + iw / 2, it + ih], radius=ih / 2, fill=(0, 0, 0, 255))
    g.ellipse([SW * k / 2 + iw / 2 - ih * 0.78, it + ih * 0.3, SW * k / 2 + iw / 2 - ih * 0.38, it + ih * 0.7], fill=(18, 20, 30, 255))
    glass = glass.resize((SW, SH), Image.LANCZOS)
    yy, xx = np.mgrid[0:SH, 0:SW].astype(np.float32)
    diag = (xx / SW * 0.9 + yy / SH * 0.45)
    refl = np.clip(1 - np.abs(diag - 0.42) / 0.16, 0, 1) ** 2 * 0.07 + np.clip(0.3 - diag, 0, 0.3) * 0.12
    edge = np.minimum.reduce([xx, yy, SW - 1 - xx, SH - 1 - yy])
    inner = np.clip(1 - edge / 10, 0, 1) * 0.10
    ref = np.zeros((SH, SW, 4), np.float32)
    ref[..., :3] = 255
    ref[..., 3] = refl * 255
    reflection = Image.fromarray(ref.astype(np.uint8), "RGBA")
    shade = np.zeros((SH, SW, 4), np.uint8)
    shade[..., 3] = (inner * 255).astype(np.uint8)
    glass = Image.alpha_composite(Image.alpha_composite(Image.fromarray(shade, "RGBA"), reflection), glass)
    # Soft contact shadow under the whole device.
    sh = Image.new("L", (body.width + 200, body.height + 200), 0)
    ImageDraw.Draw(sh).rounded_rectangle([100 + pad // k + 20, 100 + pad // k + 60, 100 + pad // k + pw // k - 20, 100 + pad // k + ph // k + 30],
                                          radius=R_OUT, fill=150)
    sh = sh.filter(ImageFilter.GaussianBlur(45))
    return body, smask, glass, sh, pad // k


@lru_cache(1)
def fixed_bars():
    return _status_bar(), _header(), _tab_bar()


def screen_view(f):
    """The phone screen at frame f: fixed bars + scrolling feed with velocity motion blur."""
    content, post2 = feed_content()
    sbar, hbar, tbar = fixed_bars()
    top = sbar.height + hbar.height
    vis_h = SH - top - tbar.height
    # Scroll: a short drag, then an iOS-style fling that decays onto the next post.
    drag_end, end = 82, 101
    target = post2

    def off(t):
        if t <= 78:
            return 0.0
        if t <= drag_end:
            return 34 * ease_in_out((t - 78) / (drag_end - 78))
        x = clamp((t - drag_end) / (end - drag_end))
        return 34 + (target - 34) * (1 - math.exp(-5.2 * x)) / (1 - math.exp(-5.2))

    o = off(f)
    vel = off(f + 0.5) - off(f - 0.5)
    view = Image.new("RGB", (SW, SH), (255, 255, 255))
    if vel > 3:
        n = int(clamp(vel / 3, 8, 64))
        acc = np.zeros((vis_h, SW, 3), np.float32)
        for i in range(n):
            oo = int(o + vel * 0.9 * (i / (n - 1) - 0.5))
            acc += np.asarray(content.crop((0, oo, SW, oo + vis_h)), np.float32)
        strip = Image.fromarray((acc / n).astype(np.uint8))
    else:
        strip = content.crop((0, int(o), SW, int(o) + vis_h))
    view.paste(strip, (0, top))
    view.paste(sbar, (0, 0))
    view.paste(hbar, (0, sbar.height))
    view.paste(tbar, (0, SH - tbar.height))
    # Scroll indicator while moving.
    vis = clamp(min(prog(f, 79, 81), 1 - prog(f, 102, 108)))
    if vis > 0:
        frac = vis_h / content.height
        y0 = top + (o / content.height) * vis_h
        d = ImageDraw.Draw(view, "RGBA")
        d.rounded_rectangle([SW - 9, y0 + 4, SW - 5, y0 + 4 + vis_h * frac], radius=2, fill=(0, 0, 0, int(110 * vis)))
    return view


def sec_boring(f):
    img = Image.new("RGB", (W, H), PAPER)
    tag(img, "A — THE USUAL AD", f, 30, y=140, color=INK)
    view = screen_view(f)
    failed = f >= 100
    if failed:
        view = bw(view, (0.95, 0.95, 0.95), 0.9)
        view = Image.blend(view, Image.new("RGB", view.size, (0, 0, 0)), 0.6)
    body, smask, glass, sh, pad = phone_layers()
    img.paste(INK, (PHONE[0] - pad - 100, PHONE[1] - pad - 100), sh)
    img.paste(view, SCREEN[:2], smask)
    img.paste(glass, SCREEN[:2], glass)
    img.paste(body, (PHONE[0] - pad, PHONE[1] - pad), body)
    if failed:
        d = ImageDraw.Draw(img)
        cx, cy, L = W // 2, 900, 270
        p1 = ease_out(prog(f, 100, 104))
        p2 = ease_out(prog(f, 103, 107))
        if p1 > 0:
            d.line([(cx - L, cy - L), (cx - L + 2 * L * p1, cy - L + 2 * L * p1)], fill=ACCENT, width=60)
        if p2 > 0:
            d.line([(cx + L, cy - L), (cx + L - 2 * L * p2, cy - L + 2 * L * p2)], fill=ACCENT, width=60)
        rise_text(img, "Scrolled past.", font(SERIF, 112), (W / 2, 1400), BONE, f, 104, 6, anchor="ms")
        rise_text(img, "Nobody saw it.", font(SERIF_I, 112), (W / 2, 1518), BONE, f, 108, 6, anchor="ms")
    # Gentle push-in on the device for the whole section.
    img = zoom(img, 1 + 0.03 * ease_in_out(prog(f, 30, 119)))
    return img, "paper"


# ------------------------------------------------------------------ C: Halfsecond version
def split3(f, f0):
    """Three vertical panels revealed with staggered mask wipes (archival split)."""
    img = Image.new("RGB", (W, H), (8, 8, 8))
    k = f - f0
    srcs = [bw(shot("glass_macro", 1 + k)), shot("label_macro", 6 + k // 2), bw(shot("cap_macro", 9 + k))]
    pw = W // 3
    for i, s in enumerate(srcs):
        p = ease_out(prog(f, f0 + i * 2 - 2, f0 + i * 2 + 5))
        if p <= 0:
            continue
        crop = s.crop((W // 2 - pw // 2 + (i - 1) * 120, 0, W // 2 + pw // 2 + (i - 1) * 120, H))
        hgt = int(H * p)
        top = 0 if i != 1 else H - hgt
        img.paste(crop.crop((0, top, pw, top + hgt)), (i * pw, top))
    d = ImageDraw.Draw(img)
    for i in (1, 2):
        d.line([(i * pw, 0), (i * pw, H)], fill=(8, 8, 8), width=8)
    return img


# Cut list for the Halfsecond section: (start, end, renderer). End is exclusive.
def cuts():
    return [
        (120, 135, lambda f: (shot("glass_macro", f - 119), "color")),
        (135, 143, lambda f: (bw(shot("cap_macro", f - 134)), "bw")),
        (143, 150, lambda f: (shot("label_macro", f - 142), "color")),
        (150, 165, lambda f: (shot("whip", f - 149), "color")),
        (165, 180, lambda f: (split3(f, 165), "bw")),
        (180, 195, lambda f: (shot("drop", f - 177), "color")),  # enters already falling
        (195, 225, lambda f: (bw(shot("sweep", f - 194)) if f < 210 else shot("sweep", f - 194), "bw" if f < 210 else "color")),
        (225, 233, lambda f: (bw(zoom(shot("glass_macro", f - 220), 1.15)), "bw")),
        (233, 240, lambda f: (shot("label_macro", f - 227), "color")),
        (240, 255, lambda f: (shot("whip", 255 - f), "color")),
        (255, 360, lambda f: (shot_blend("hero", 1 + (f - 255) * (shot_count("hero") - 1) / 104), "color")),
    ]


def sec_half(f):
    for a, b, fn in cuts():
        if a <= f < b:
            img, mode = fn(f)
            break
    # Punch-in on every beat: 3% scale kick that settles in 5 frames.
    beat_k = (f - 120) % 15
    if f < 255:
        img = zoom(img, 1 + 0.035 * math.exp(-beat_k / 3.0))
    img = img.convert("RGB")
    fr = f

    if fr < 150:  # The hook - fully legible on the very first frame.
        img = grad_overlay(img, True, 1250, 0.88)
        settle = 1 + 0.05 * (1 - ease_out(prog(fr, 120, 126)))
        fs, fi = font(SERIF, 168 * settle), font(SERIF_I, 168 * settle)
        draw_text(img, "They'll ask", fs, (80, 420), BONE)
        draw_text(img, "what you're", fs, (80, 580), BONE)
        draw_text(img, "wearing.", fi, (80, 740), BONE)
        ImageDraw.Draw(img).rectangle([84, 772, 84 + fi.getlength("wearing.") - 10, 780], fill=ACCENT)
        tag(img, "B — THE HALFSECOND VERSION", fr, 120, y=250)
    elif fr < 165:
        img = grad_overlay(img, False, 900, 0.6)
        rise_text(img, "Not a scent.", font(SERIF, 150), (W / 2, 1330), BONE, fr, 150, 5, anchor="ms")
    elif fr < 180:
        rise_text(img, "A signature.", font(SERIF_I, 170), (W / 2, 1000), BONE, fr, 167, 5, anchor="ms")
    elif fr < 195:
        if fr >= 184:
            draw_text(img, "N°05", font(MONO, 34), (80, 300), BONE, tracking=4, alpha=prog(fr, 184, 187))
            draw_text(img, "EAU DE PARFUM", font(MONO, 34), (W - 80, 300), BONE, anchor="rs", tracking=4,
                      alpha=prog(fr, 184, 187))
    elif fr < 225:
        img = grad_overlay(img, True, 900, 0.5)
        notes = [("TOP", "bergamot"), ("HEART", "amber"), ("BASE", "oud")]
        d = ImageDraw.Draw(img)
        for i, (k, v) in enumerate(notes):
            fin = 196 + i * 8
            p = ease_out(prog(fr, fin, fin + 6))
            if p <= 0:
                continue
            y = 330 + i * 150
            d.line([(80, y + 30), (80 + 920 * p, y + 30)], fill=(120, 112, 100), width=2)
            draw_text(img, k, font(MONO, 34), (80, y), (170, 160, 146), tracking=5, alpha=p)
            rise_text(img, v, font(SERIF_I, 110), (W - 80, y + 6), BONE, fr, fin, 6, anchor="rs")
    elif fr >= 255:
        if fr < 300:
            rise_text(img, "VELOUR", font(SERIF, 210), (W / 2, 470), INK, fr, 256, 8, anchor="ms", tracking=24)
            draw_text(img, "N°05  ·  EAU DE PARFUM", font(MONO, 32), (W / 2, 560), INK, anchor="ms",
                      tracking=4, alpha=prog(fr, 262, 268))
        else:
            draw_text(img, "VELOUR  N°05", font(MONO, 32), (W / 2, 250), INK, anchor="ms", tracking=6)
            rise_text(img, "20% off,", font(SERIF, 150), (W / 2, 420), INK, fr, 300, 6, anchor="ms")
            rise_text(img, "this week only.", font(SERIF_I, 150), (W / 2, 560), INK, fr, 304, 6, anchor="ms")
            p = ease_out(prog(fr, 312, 320))
            if p > 0:
                fm = font(MONO_B, 36)
                txt = "SHOP THE DROP"
                tw = text_w(txt, fm, 4) + 70
                draw_text(img, txt, fm, (W / 2 - 35, 650), INK, anchor="ms", tracking=4, alpha=p)
                ax = W / 2 + tw / 2 - 40  # arrow drawn by hand (the mono font has no arrow glyph)
                d = ImageDraw.Draw(img)
                d.line([(ax, 638), (ax + 40, 638)], fill=INK, width=4)
                d.line([(ax + 26, 626), (ax + 40, 638), (ax + 26, 650)], fill=INK, width=4)
                ImageDraw.Draw(img).line([(W / 2 - tw / 2, 668), (W / 2 - tw / 2 + tw * p, 668)], fill=INK, width=3)
    # Running counter: the whole Halfsecond version is still sold inside the first beat.
    if fr < 255:
        draw_text(img, f"{(fr - 120) / 30:04.1f}s", font(MONO, 30), (W - 80, 148), (200, 190, 175), anchor="rs", tracking=2)
    return img, mode


# ------------------------------------------------------------------ D: end card
def sec_end(f):
    img = Image.new("RGB", (W, H), PAPER)
    logo(img, W / 2, 720, 1.12, f, 359)
    rise_text(img, "Your brand next?", font(SERIF, 132), (W / 2, 1060), INK, f, 374, 7, anchor="ms")
    rise_text(img, "DM us.", font(SERIF_I, 132), (W / 2, 1200), ACCENT, f, 382, 7, anchor="ms")
    p = prog(f, 392, 400)
    draw_text(img, "ADS BUILT FOR THE FIRST HALF SECOND", font(MONO, 28), (W / 2, 1330), (90, 84, 76), anchor="ms",
              tracking=4, alpha=p)
    d = ImageDraw.Draw(img)
    d.line([(80, 160), (W - 80, 160)], fill=(60, 56, 50), width=2)
    draw_text(img, "HALFSECOND / 001", font(MONO, 26), (80, 140), (60, 56, 50), tracking=3)
    draw_text(img, "ADVERTISING AGENCY", font(MONO, 26), (W - 80, 140), (60, 56, 50), anchor="rs", tracking=3)
    return img, "paper"


# ------------------------------------------------------------------ finish
_rng = np.random.default_rng(11)


def finish(img, mode, f):
    a = np.asarray(img).astype(np.float32) / 255
    if mode != "paper":
        # Bloom + warm halation from highlights.
        y = a @ np.array([0.299, 0.587, 0.114], np.float32)
        hi = np.clip((y - 0.62) / 0.38, 0, 1)
        small = Image.fromarray((hi * 255).astype(np.uint8)).resize((W // 6, H // 6), Image.BILINEAR)
        glow = np.asarray(small.filter(ImageFilter.GaussianBlur(9)).resize((W, H), Image.BILINEAR), np.float32) / 255
        tint = np.array(STYLE["halation"] if mode == "color" else (1.0, 0.95, 0.88), np.float32)
        a = 1 - (1 - a) * (1 - STYLE["bloom"] * glow[..., None] * tint)
        # Lifted, slightly warm blacks (print stock feel).
        a = a * 0.95 + np.array([0.022, 0.018, 0.014], np.float32)
    # Vignette
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    v = ((xx - W / 2) / (W * 0.75)) ** 2 + ((yy - H / 2) / (H * 0.7)) ** 2
    a *= (1 - STYLE["vignette"] * np.clip(v, 0, 1) ** 1.3)[..., None] if mode != "paper" else \
        (1 - 0.12 * np.clip(v, 0, 1))[..., None]
    # Animated grain, a touch coarser than a pixel.
    g = _rng.standard_normal((H // 2, W // 2)).astype(np.float32)
    g = np.asarray(Image.fromarray(g, "F").resize((W, H), Image.BILINEAR), np.float32)
    std = STYLE["grain_bw"] if mode == "bw" else STYLE["grain"] * (0.8 if mode == "paper" else 1)
    lum = a.mean(-1, keepdims=True)
    a = a + g[..., None] * std * (0.35 + 0.65 * np.sqrt(np.clip(lum * (1 - lum) * 4, 0, 1)))
    return Image.fromarray((np.clip(a, 0, 1) * 255).astype(np.uint8))


def frame(f):
    if f < 30:
        img, mode = sec_intro(f)
    elif f < 120:
        img, mode = sec_boring(f)
    elif f < 360:
        img, mode = sec_half(f)
    else:
        img, mode = sec_end(f)
    return finish(img.convert("RGB"), mode, f)


def main():
    args = sys.argv[1:]
    fr = range(NF)
    png = None
    for i, a in enumerate(args):
        if a == "--frames":
            lo, hi = (int(x) for x in args[i + 1].split("-"))
            fr = range(lo, hi + 1)
        if a == "--png":
            png = args[i + 1]
    if png:
        os.makedirs(png, exist_ok=True)
        for f in fr:
            frame(f).save(os.path.join(png, f"{f:04d}.png"))
        return
    build = os.path.join(ROOT, "build")
    os.makedirs(build, exist_ok=True)
    silent = os.path.join(build, "picture.mp4")
    enc = subprocess.Popen([
        "ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS),
        "-i", "-", "-c:v", "libx264", "-preset", "slow", "-tune", "grain", "-crf", "18", "-maxrate", "20M", "-bufsize", "40M",
        "-pix_fmt", "yuv420p",
        "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709", silent], stdin=subprocess.PIPE)
    for f in fr:
        enc.stdin.write(frame(f).tobytes())
        if f % 30 == 0:
            print("frame", f, flush=True)
    enc.stdin.close()
    enc.wait()
    frame(24).convert("RGB").save(os.path.join(build, "cover.jpg"), quality=94)
    for name, wav in (("halfsecond_reel_01.mp4", "mix.wav"), ("halfsecond_reel_01_no_music.mp4", "sfx_only.wav")):
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", silent, "-i", os.path.join(ROOT, "audio", wav),
                        "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac", "-b:a", "256k", "-ar", "48000",
                        "-movflags", "+faststart", "-shortest", os.path.join(build, name)], check=True)
    print("done")


if __name__ == "__main__":
    main()
