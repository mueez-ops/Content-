"""Composites the 15 s reel: shots + kinetic type + UI mock + archival finish, then encodes.

    python compose.py                 -> build/halfsecond_reel_01.mp4 (+ _no_music.mp4)
    python compose.py --frames 120-180 --png build/check   (write PNG stills only)

Timeline (30 fps, 120 BPM => 1 beat = 15 frames):
    f000-029  0.0-1.0s   "0.5s" stopwatch card
    f030-119  1.0-4.0s   boring ad in a feed, thumb scrolls past, X
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
SCREEN = (100, 250, 980, 1814)  # phone screen inside the frame (9:16-ish)
SW, SH = SCREEN[2] - SCREEN[0], SCREEN[3] - SCREEN[1]


@lru_cache(1)
def feed_canvas():
    """A tall generic social feed (no real platform branding) with the boring post on top."""
    s = SW / 1080
    post_h = int(1930 * s)
    cv = Image.new("RGB", (SW, post_h * 3 + 200), (255, 255, 255))
    d = ImageDraw.Draw(cv)

    def post(y0, kind):
        d.ellipse([30 * s, y0 + 20 * s, 110 * s, y0 + 100 * s], fill=(222, 222, 222))
        draw_text(cv, "Y", font(UI_B, 40 * s), (70 * s, y0 + 75 * s), (120, 120, 120), anchor="ms")
        name = "yourbrand" if kind == 0 else ["dailyfit", "foodspot", "travelgram"][kind % 3]
        draw_text(cv, name, font(UI_B, 34 * s), (130 * s, y0 + 55 * s), (0, 0, 0))
        draw_text(cv, "Sponsored" if kind == 0 else "2h", font(UI, 28 * s), (130 * s, y0 + 92 * s), (120, 120, 120))
        draw_text(cv, "•••", font(UI_B, 34 * s), (SW - 40 * s, y0 + 70 * s), (0, 0, 0), anchor="rs")
        iy = int(y0 + 120 * s)
        ih = int(1350 * s)
        if kind == 0:
            src = shot("boring", 1)
            crop = src.crop((0, (H - 1350) // 2 + 60, W, (H - 1350) // 2 + 60 + 1350)).resize((SW, ih), Image.LANCZOS)
            cv.paste(crop, (0, iy))
            # The 'design': red shouty discount + yellow button.
            fu = font(UGLY, 150 * s)
            for dx, dy in ((4, 4), (-2, -2), (2, -2), (-2, 2)):
                draw_text(cv, "20% OFF", fu, (SW / 2 + dx * s, iy + 220 * s + dy * s), (0, 0, 0), anchor="ms")
            draw_text(cv, "20% OFF", fu, (SW / 2, iy + 220 * s), (230, 20, 20), anchor="ms")
            bx0, by0, bx1, by1 = SW / 2 - 250 * s, iy + 1130 * s, SW / 2 + 250 * s, iy + 1260 * s
            d.rounded_rectangle([bx0, by0, bx1, by1], 18, fill=(255, 221, 0), outline=(0, 0, 0), width=4)
            draw_text(cv, "BUY NOW!!", font(UGLY, 74 * s), (SW / 2, by1 - 36 * s), (0, 0, 0), anchor="ms")
            d.rectangle([0, iy + ih, SW, iy + ih + 90 * s], fill=(236, 240, 246))
            draw_text(cv, "Shop now", font(UI_B, 32 * s), (36 * s, iy + ih + 58 * s), (40, 60, 110))
            draw_text(cv, "›", font(UI_B, 44 * s), (SW - 36 * s, iy + ih + 60 * s), (40, 60, 110), anchor="rs")
        else:
            shade = [(214, 219, 224), (232, 222, 210), (206, 222, 214)][kind % 3]
            d.rectangle([0, iy, SW, iy + ih], fill=shade)
            d.ellipse([SW * 0.3, iy + ih * 0.3, SW * 0.7, iy + ih * 0.62], fill=tuple(c - 25 for c in shade))
        ay = iy + ih + (130 if kind == 0 else 40) * s
        # Generic action icons
        d.ellipse([34 * s, ay, 80 * s, ay + 44 * s], outline=(0, 0, 0), width=4)
        d.ellipse([110 * s, ay, 156 * s, ay + 44 * s], outline=(0, 0, 0), width=4)
        d.polygon([(190 * s, ay), (236 * s, ay + 22 * s), (190 * s, ay + 44 * s)], outline=(0, 0, 0))
        cap = "yourbrand New perfume available now!! 20% off" if kind == 0 else name + " a nice day out"
        draw_text(cv, cap, font(UI, 30 * s), (34 * s, ay + 100 * s), (20, 20, 20))
        draw_text(cv, "#perfume #sale #buynow" if kind == 0 else "#weekend", font(UI, 30 * s), (34 * s, ay + 145 * s), (40, 70, 140))

    for k in range(3):
        post(int(110 * s) + k * post_h, k)
    return cv


def status_bar(view):
    s = SW / 1080
    d = ImageDraw.Draw(view)
    d.rectangle([0, 0, SW, 100 * s], fill=(255, 255, 255))
    draw_text(view, "9:41", font(UI_B, 34 * s), (40 * s, 66 * s), (0, 0, 0))
    d.rounded_rectangle([SW - 120 * s, 40 * s, SW - 50 * s, 70 * s], 6, outline=(0, 0, 0), width=3)
    d.rectangle([SW - 116 * s, 44 * s, SW - 70 * s, 66 * s], fill=(0, 0, 0))


@lru_cache(1)
def thumb_sprite():
    t = Image.open(os.path.join(R, "thumb", "0001.png")).convert("RGBA")
    bb = t.getbbox()
    t = t.crop(bb)
    sc = 560 / t.width
    t = t.resize((int(t.width * sc), int(t.height * sc)), Image.LANCZOS)
    # The render ends where the digit is cut; continue the base down-right along its axis.
    ext, slope = 900, math.tan(math.radians(24))
    big = Image.new("RGBA", (t.width + int(ext * slope) + 20, t.height + ext), (0, 0, 0, 0))
    big.paste(t, (0, 0))
    a = np.asarray(t.getchannel("A"))
    last = max(i for i in range(t.height - 1, 0, -1) if a[i].max() > 200 and a[i].sum() > 255 * 80)
    row = t.crop((0, last - 6, t.width, last - 5))
    for k in range(t.height - last + ext + 6):
        big.paste(row, (int(k * slope), last - 6 + k), row)
    big.paste(t.crop((0, 0, t.width, last - 6)), (0, 0), t.crop((0, 0, t.width, last - 6)))
    t = big
    sh = Image.new("RGBA", t.size, (0, 0, 0, 0))
    sh.putalpha(t.getchannel("A").point(lambda v: int(v * 0.35)).filter(ImageFilter.GaussianBlur(22)))
    return t, sh


def sec_boring(f):
    img = Image.new("RGB", (W, H), (22, 21, 20))
    tag(img, "A — THE USUAL AD", f, 30)
    # Scroll: hold, then a flick with ease-in-out over 20 frames.
    s_p = ease_in_out(prog(f, 78, 97))
    off = s_p * 1850 * (SW / 1080)
    vel = 0.0
    if 78 <= f <= 97:
        vel = 1850 * (SW / 1080) * (ease_in_out(prog(f + 0.5, 78, 97)) - ease_in_out(prog(f - 0.5, 78, 97)))
    cv = feed_canvas()
    view = cv.crop((0, int(off), SW, int(off) + SH))
    if vel > 4:
        # Motion blur along the scroll direction.
        n = 6
        acc = np.zeros((SH, SW, 3), np.float32)
        for k in range(n):
            o = int(off + vel * (k / (n - 1) - 0.5))
            acc += np.asarray(cv.crop((0, o, SW, o + SH)), np.float32)
        view = Image.fromarray((acc / n).astype(np.uint8))
    view = view.copy()
    status_bar(view)
    failed = f >= 100
    if failed:
        view = bw(view, (0.95, 0.95, 0.95), 0.9)
        view = Image.blend(view, Image.new("RGB", view.size, (0, 0, 0)), 0.6)
    # Screen with rounded corners on the dark page.
    m = Image.new("L", (SW, SH), 0)
    ImageDraw.Draw(m).rounded_rectangle([0, 0, SW - 1, SH - 1], 46, fill=255)
    img.paste(view, SCREEN[:2], m)
    ImageDraw.Draw(img).rounded_rectangle([SCREEN[0] - 3, SCREEN[1] - 3, SCREEN[2] + 2, SCREEN[3] + 2], 49,
                                          outline=(60, 58, 55), width=3)
    # Thumb: enters, presses, drags up, leaves.
    t, sh = thumb_sprite()
    tip = (600, 1360)
    if 58 <= f <= 112:
        e = ease_out(prog(f, 58, 74))
        x = tip[0] + (1 - e) * 500
        y = tip[1] + (1 - e) * 700
        drag = ease_in_out(prog(f, 78, 92))
        y -= drag * 640
        x -= drag * 60
        leave = ease_in_out(prog(f, 94, 110))
        x += leave * 520
        y += leave * 900
        press = 1 - 0.03 * (1 if 75 <= f <= 92 else 0)
        tt = t if press == 1 else t.resize((int(t.width * press), int(t.height * press)), Image.LANCZOS)
        # sprite tip is near its top-left; offset so the nail lands on (x, y)
        px, py = int(x - tt.width * 0.18), int(y - tt.height * 0.06)
        img.paste((0, 0, 0), (px + 26, py + 34), sh.resize(tt.size) if sh.size != tt.size else sh)
        img.paste(tt, (px, py), tt)
        if 75 <= f <= 82:
            q = prog(f, 75, 82)
            d = ImageDraw.Draw(img)
            rr = 30 + q * 70
            d.ellipse([tip[0] - rr, tip[1] - rr, tip[0] + rr, tip[1] + rr], outline=(255, 255, 255), width=int(5 * (1 - q)) + 1)
    if failed:
        d = ImageDraw.Draw(img)
        cx, cy, L = W // 2, 900, 300
        p1 = ease_out(prog(f, 100, 104))
        p2 = ease_out(prog(f, 103, 107))
        if p1 > 0:
            d.line([(cx - L, cy - L), (cx - L + 2 * L * p1, cy - L + 2 * L * p1)], fill=ACCENT, width=64)
        if p2 > 0:
            d.line([(cx + L, cy - L), (cx + L - 2 * L * p2, cy - L + 2 * L * p2)], fill=ACCENT, width=64)
        rise_text(img, "Scrolled past.", font(SERIF, 120), (W / 2, 1420), BONE, f, 104, 6, anchor="ms")
        rise_text(img, "Nobody saw it.", font(SERIF_I, 120), (W / 2, 1545), BONE, f, 108, 6, anchor="ms")
    return img, "bw" if failed else "color"


# ------------------------------------------------------------------ C: Halfsecond version
def split3(f, f0):
    """Three vertical panels revealed with staggered mask wipes (archival split)."""
    img = Image.new("RGB", (W, H), (8, 8, 8))
    k = f - f0
    srcs = [bw(shot("cap_macro", 9 + k)), shot("label_macro", 6 + k // 2), bw(shot("glass_macro", 1 + k))]
    pw = W // 3
    for i, s in enumerate(srcs):
        p = ease_out(prog(f, f0 + i * 2, f0 + i * 2 + 6))
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
        (180, 195, lambda f: (shot("drop", f - 179), "color")),
        (195, 225, lambda f: (bw(shot("sweep", f - 194)) if f < 210 else shot("sweep", f - 194), "bw" if f < 210 else "color")),
        (225, 233, lambda f: (bw(zoom(shot("cap_macro", f - 212), 1.15)), "bw")),
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
        if fr >= 186:
            draw_text(img, "N°05", font(MONO, 34), (80, 300), BONE, tracking=4, alpha=prog(fr, 186, 189))
            draw_text(img, "EAU DE PARFUM", font(MONO, 34), (W - 80, 300), BONE, anchor="rs", tracking=4,
                      alpha=prog(fr, 186, 189))
    elif fr < 225:
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
            rise_text(img, "VELOUR", font(SERIF, 210), (W / 2, 470), BONE, fr, 256, 8, anchor="ms", tracking=24)
            draw_text(img, "N°05  ·  EAU DE PARFUM", font(MONO, 32), (W / 2, 560), (210, 190, 170), anchor="ms",
                      tracking=4, alpha=prog(fr, 262, 268))
        else:
            draw_text(img, "VELOUR  N°05", font(MONO, 32), (W / 2, 250), (225, 205, 185), anchor="ms", tracking=6)
            rise_text(img, "20% off,", font(SERIF, 150), (W / 2, 420), BONE, fr, 300, 6, anchor="ms")
            rise_text(img, "this week only.", font(SERIF_I, 150), (W / 2, 560), BONE, fr, 304, 6, anchor="ms")
            p = ease_out(prog(fr, 312, 320))
            if p > 0:
                fm = font(MONO_B, 36)
                txt = "SHOP THE DROP  →"
                tw = text_w(txt, fm, 4)
                draw_text(img, txt, fm, (W / 2, 650), ACCENT, anchor="ms", tracking=4, alpha=p)
                ImageDraw.Draw(img).line([(W / 2 - tw / 2, 668), (W / 2 - tw / 2 + tw * p, 668)], fill=ACCENT, width=3)
    # Running counter: the whole Halfsecond version is still sold inside the first beat.
    if fr < 255:
        draw_text(img, f"{(fr - 120) / 30:04.1f}s", font(MONO, 30), (W - 80, 148), (200, 190, 175), anchor="rs", tracking=2)
    return img, mode


# ------------------------------------------------------------------ D: end card
def sec_end(f):
    img = Image.new("RGB", (W, H), PAPER)
    logo(img, W / 2, 720, 1.12, f, 361)
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
        "-i", "-", "-c:v", "libx264", "-preset", "slow", "-crf", "16", "-pix_fmt", "yuv420p",
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
