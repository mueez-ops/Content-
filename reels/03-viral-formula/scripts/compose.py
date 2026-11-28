"""Reel 03 "The Viral Formula": editorial cut-out reel with Werner-style FX.

Look: cloudy paper, museum cut-outs with mist, navy/royal-blue kinetic type
typed in sync with the voiceover, barcodes / crop marks / sparkles / fine print,
split navy panels with subjects breaking out of frame. Punch: silhouette-mask
transitions, colour inversions, white subject flashes, smears, whips, zoom and
spin blur, beat punches.

    python scripts/compose.py              # all frames -> build/frames
    python scripts/compose.py --only 0,90  # selected frames
"""
import argparse
import math
import os
import sys
from functools import lru_cache
from multiprocessing import Pool

import cv2
import numpy as np
import soundfile as sf
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import timeline as T  # noqa: E402

ROOT = T.ROOT
W, H = 1080, 1920
OUT = os.path.join(ROOT, "build", "frames")
CUT = os.path.join(ROOT, "assets", "cutouts")
SRC = os.path.join(ROOT, "assets", "src")
FONTS = os.path.join(ROOT, "assets", "fonts")
FONTS01 = os.path.join(ROOT, "..", "01-half-second", "assets", "fonts")
cv2.setNumThreads(1)


def C(*rgb):
    return np.array(rgb, np.float32) / 255


STYLE = {
    "paper": C(233, 235, 241),
    "ink": C(24, 27, 44),           # lead text
    "blue": C(40, 62, 222),         # big words (reference royal blue)
    "blue_dark": C(80, 104, 255),   # big words on dark
    "navy": C(14, 20, 48),          # split panels
    "accent": C(255, 77, 34),       # halfsecond orange (logo half)
    "grain": 0.016,
    "vignette": 0.10,
}
P = STYLE

F_XB, F_B, F_SB, F_M, F_R = ("Poppins-ExtraBold.ttf", "Poppins-Bold.ttf", "Poppins-SemiBold.ttf",
                             "Poppins-Medium.ttf", "Poppins-Regular.ttf")
F_SCRIPT = "Kalam-Bold.ttf"


def clamp(x, a=0.0, b=1.0):
    return max(a, min(b, x))


def eo(x):
    x = clamp(x)
    return 1 - (1 - x) ** 3


def eio(x):
    x = clamp(x)
    return x * x * (3 - 2 * x)


# ------------------------------------------------------------------ paper + mist
@lru_cache(1)
def paper():
    rng = np.random.default_rng(5)
    n = np.zeros((H, W), np.float32)
    for cell, amp in ((6, 0.005), (30, 0.008), (120, 0.013), (400, 0.012)):
        small = rng.standard_normal((H // cell + 3, W // cell + 3)).astype(np.float32)
        up = cv2.resize(small, (W + 3 * cell, H + 3 * cell), interpolation=cv2.INTER_CUBIC)[:H, :W]
        up = cv2.GaussianBlur(up, (0, 0), cell * 0.5)
        n += up / (up.std() + 1e-6) * amp
    # soft marbled veins
    v = cv2.GaussianBlur(rng.standard_normal((H // 8, W // 8)).astype(np.float32), (0, 0), 6)
    v = cv2.resize(np.abs(v / v.std()), (W, H), interpolation=cv2.INTER_CUBIC)
    n -= np.exp(-v * 6) * 0.008
    img = P["paper"][None, None, :] * (1 + n[..., None])
    fib = cv2.GaussianBlur(rng.standard_normal((H, W)).astype(np.float32), (0, 0), 0.6)
    img += fib[..., None] * 0.006
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    r = np.sqrt(((xx - W / 2) / W) ** 2 + ((yy - H / 2) / H) ** 2)
    img *= (1 - 0.06 * r ** 2)[..., None]
    return np.clip(img, 0, 1).astype(np.float32)


@lru_cache(4)
def mist_tex(seed=0, w=2 * W, h=560):
    rng = np.random.default_rng(seed)
    n = np.zeros((h, w), np.float32)
    for cell, amp in ((18, 0.25), (60, 0.5), (180, 1.0)):
        s = rng.standard_normal((h // cell + 3, w // cell + 3)).astype(np.float32)
        up = cv2.resize(s, (w + 3 * cell, h + 3 * cell), interpolation=cv2.INTER_CUBIC)[:h, :w]
        n += cv2.GaussianBlur(up, (0, 0), cell * 0.45) * amp
    n = (n - n.mean()) / n.std()
    a = np.clip((n + 0.3) / 1.6, 0, 1) ** 1.4
    prof = np.exp(-((np.linspace(0, 1, h) - 0.62) / 0.26) ** 2)
    a *= prof[:, None]
    # wrap horizontally so it can scroll seamlessly
    k = 200
    a[:, :k] = a[:, :k] * np.linspace(0, 1, k)[None] + a[:, -k:] * np.linspace(1, 0, k)[None]
    return cv2.GaussianBlur(a, (0, 0), 3)


def mist(img, y_center, f, strength=0.85, seed=0, speed=0.7, tint=None):
    tex = mist_tex(seed)
    h, w = tex.shape
    off = int(f * speed) % (w - W)
    a = tex[:, off:off + W] * strength
    y0 = int(y_center - h * 0.62)
    ya, yb = max(0, y0), min(H, y0 + h)
    if yb <= ya:
        return img
    a = a[ya - y0:yb - y0, :, None]
    col = np.ones(3, np.float32) * 0.985 if tint is None else tint
    img[ya:yb] = img[ya:yb] * (1 - a) + col * a
    return img


# ------------------------------------------------------------------ cut-outs
@lru_cache(16)
def cutout(name, crop=None):
    """Premultiplied float RGBA of a cut-out; crop = (y0, y1) fractions."""
    im = cv2.imread(os.path.join(CUT, name + ".png"), cv2.IMREAD_UNCHANGED)
    im = cv2.cvtColor(im, cv2.COLOR_BGRA2RGBA).astype(np.float32) / 255
    if crop:
        h = im.shape[0]
        im = im[int(crop[0] * h):int(crop[1] * h)]
        # feather the cut edge at the bottom
        if crop[1] < 1:
            k = min(160, im.shape[0] // 6)
            im[-k:, :, 3] *= np.linspace(1, 0, k)[:, None] ** 1.5
    im[..., :3] *= im[..., 3:4]
    return im


def grade_cut(rgb, sat=0.92, contrast=1.05, lift=0.0, cool=0.0):
    lum = rgb @ np.array([0.2126, 0.7152, 0.0722], np.float32)
    rgb = lum[..., None] + (rgb - lum[..., None]) * sat
    rgb = 0.5 + (rgb - 0.5) * contrast + lift
    if cool:
        rgb = rgb + np.array([-0.5, 0, 1], np.float32) * cool
    return np.clip(rgb, 0, 1)


def place(img, name, cx, cy, height, f=0, rot=0.0, crop=None, shadow=0.2, grade=None, alpha_out=None, keep=1.0):
    """Composite a cut-out centred at (cx, cy) scaled to `height` px. Returns full-frame mask."""
    src = cutout(name, crop)
    sh, sw = src.shape[:2]
    s = height / sh
    M = cv2.getRotationMatrix2D((sw / 2, sh / 2), rot, s)
    M[0, 2] += cx - sw / 2
    M[1, 2] += cy - sh / 2
    lay = cv2.warpAffine(src, M, (W, H), flags=cv2.INTER_AREA if s < 0.8 else cv2.INTER_CUBIC,
                         borderMode=cv2.BORDER_CONSTANT, borderValue=0)
    a = np.clip(lay[..., 3:4], 0, 1) * keep
    rgb = lay[..., :3]
    if grade:
        un = rgb / np.maximum(lay[..., 3:4], 1e-4)
        rgb = grade_cut(un, **grade) * lay[..., 3:4]
    rgb = rgb * keep
    if shadow > 0:
        q = 6
        sm = cv2.resize(a[..., 0], (W // q, H // q), interpolation=cv2.INTER_AREA)
        sm = cv2.GaussianBlur(sm, (0, 0), 7)
        sm = cv2.resize(sm, (W, H), interpolation=cv2.INTER_LINEAR)
        sm = np.roll(sm, 26, axis=0)
        img *= (1 - shadow * sm)[..., None]
    img[:] = img * (1 - a) + rgb
    return a[..., 0]


# ------------------------------------------------------------------ type
@lru_cache(None)
def font(name, size):
    d = FONTS if os.path.exists(os.path.join(FONTS, name)) else FONTS01
    return ImageFont.truetype(os.path.join(d, name), int(size))


@lru_cache(512)
def line_patch(text, fname, size, tracking=0):
    """Alpha patch of a text line + per-character x ranges + baseline y."""
    f = font(fname, size)
    asc, desc = f.getmetrics()
    xs = [0.0]
    for i in range(1, len(text) + 1):
        xs.append(f.getlength(text[:i]) + tracking * i)
    pad = int(size * 0.35)
    wpx = int(xs[-1]) + 2 * pad
    im = Image.new("L", (wpx, asc + desc + 2 * pad), 0)
    d = ImageDraw.Draw(im)
    for i, ch in enumerate(text):
        d.text((pad + xs[i], pad + asc), ch, font=f, fill=255, anchor="ls")
    a = np.asarray(im, np.float32) / 255
    return a, [pad + x for x in xs], pad + asc


def fit(text, fname, size, tracking, max_w):
    w = font(fname, size).getlength(text) + tracking * len(text)
    return int(size * min(1.0, max_w / w))


def text_line(img, text, fname, size, color, cx, base_y, prog=None, tracking=0, anchor="c", blur_max=7, rise=16,
              unit="char", glow=0.0):
    """Draw a line centred at cx (anchor c) or starting at cx (l) / ending at cx (r) with its
    baseline at base_y. prog(i) -> 0..1 reveal for unit i (char or word)."""
    a, xs, base = line_patch(text, fname, size, tracking)
    full_w = xs[-1] - xs[0]
    x0 = {"c": cx - full_w / 2, "l": cx, "r": cx - full_w}[anchor] - xs[0]
    y0 = base_y - base
    col = np.asarray(color, np.float32)
    if unit == "word":
        spans, i = [], 0
        for wd in text.split(" "):
            spans.append((i, i + len(wd)))
            i += len(wd) + 1
    else:
        spans = [(i, i + 1) for i in range(len(text))]
    for k, (i0, i1) in enumerate(spans):
        p = 1.0 if prog is None else clamp(prog(k))
        if p <= 0:
            continue
        xa = int(xs[i0] - (size * 0.12 if i0 else xs[0]))
        xb = int(xs[i1] + size * 0.12) if i1 < len(text) else a.shape[1]
        xa = max(0, xa)
        piece = a[:, xa:xb]
        if p < 1:
            sig = (1 - eo(p)) * blur_max
            if sig > 0.3:
                piece = cv2.GaussianBlur(piece, (0, 0), sig)
            piece = piece * eo(p)
        dx = int(x0 + xa + (1 - eo(p)) * 0)
        dy = int(y0 + (1 - eo(p)) * rise)
        _blit(img, piece, col, dx, dy, glow)
    return img


def _blit(img, piece, col, dx, dy, glow=0.0):
    ph, pw = piece.shape
    xa, ya = max(0, dx), max(0, dy)
    xb, yb = min(W, dx + pw), min(H, dy + ph)
    if xb <= xa or yb <= ya:
        return
    sub = piece[ya - dy:yb - dy, xa - dx:xb - dx]
    reg = img[ya:yb, xa:xb]
    if glow:
        g = cv2.GaussianBlur(sub, (0, 0), 10) * glow
        reg += g[..., None] * col * 0.6
    reg[:] = reg * (1 - sub[..., None]) + col * sub[..., None]


def word_window(ws, rng_):
    """Start/end frames for a word-index range of a scene's VO."""
    i0, i1 = rng_
    i1 = min(i1, len(ws) - 1)
    return ws[i0][1], ws[i1][2]


def reveal_chars(f, start, end, n, settle=6):
    span = max(end - start, n * 0.9)
    return lambda i: (f - (start + span * i / max(1, n))) / settle


def typed(img, f, ws, spec, fname, size, color, cx, y, tracking=0, anchor="c", unit="char", glow=0.0,
          after=None, blur_max=7):
    text, wr = spec
    if wr is None:
        s0 = after if after is not None else 0
        st, en = s0, s0 + 10
    else:
        st, en = word_window(ws, wr)
        st -= 2
    n = len(text) if unit == "char" else len(text.split(" "))
    text_line(img, text, fname, size, color, cx, y, reveal_chars(f, st, en, n), tracking, anchor, blur_max,
              unit=unit, glow=glow)


# ------------------------------------------------------------------ decor
def _c(col):
    return tuple(float(v) for v in col)


def barcode(img, cx, y, w=150, h=58, seed=1, col=None):
    rng = np.random.default_rng(seed)
    x = cx - w / 2
    col = _c(P["ink"] if col is None else col)
    while x < cx + w / 2:
        bw = rng.choice([2, 2, 3, 4, 6])
        if rng.random() > 0.35:
            cv2.rectangle(img, (int(x), int(y)), (int(x + bw - 1), int(y + h)), col, -1)
        x += bw + rng.choice([2, 3, 4])


def corners(img, x0, y0, x1, y1, L=42, col=None, t=2):
    col = _c(P["ink"] * 0.9 if col is None else col)
    for (x, y, dx, dy) in ((x0, y0, 1, 1), (x1, y0, -1, 1), (x0, y1, 1, -1), (x1, y1, -1, -1)):
        cv2.line(img, (x, y), (x + dx * L, y), col, t, cv2.LINE_AA)
        cv2.line(img, (x, y), (x, y + dy * L), col, t, cv2.LINE_AA)


def sparkle(img, cx, cy, r, col=None, f=0, phase=0.0):
    k = 0.75 + 0.25 * math.sin(f / 5 + phase)
    r = r * k
    col = _c(P["ink"] if col is None else col)
    pts = []
    for i in range(8):
        ang = i * math.pi / 4 - math.pi / 2
        rr = r if i % 2 == 0 else r * 0.16
        pts.append((cx + rr * math.cos(ang), cy + rr * math.sin(ang)))
    cv2.fillPoly(img, [np.array(pts, np.int32)], col, cv2.LINE_AA)


def fine(img, text, x, y, size=20, col=None, anchor="l", fname=F_M, op=1.0):
    col = (P["ink"] * 0.85 if col is None else col)
    a, xs, base = line_patch(text, fname, size, 0)
    full = xs[-1] - xs[0]
    x0 = {"c": x - full / 2, "l": x, "r": x - full}[anchor] - xs[0]
    _blit(img, a * op, np.asarray(col, np.float32), int(x0), int(y - base))


def para(img, lines, cx, y, size=22, lh=1.45, col=None, op=1.0):
    for i, ln in enumerate(lines):
        fine(img, ln, cx, y + i * size * lh, size, col, "c", F_M, op)


def badge4k(img, x, y, col=None):
    col = P["ink"] if col is None else col
    cv2.rectangle(img, (x, y), (x + 62, y + 36), _c(col), 2, cv2.LINE_AA)
    fine(img, "4K", x + 31, y + 28, 24, col, "c", F_XB)
    fine(img, "QUALITY ISN'T", x + 74, y + 15, 13, col, "l", F_B)
    fine(img, "ONLY ABOUT 4K", x + 74, y + 32, 13, col, "l", F_B)


def dim_bracket(img, x, y0, y1, col=None):
    col = _c(P["ink"] * 0.8 if col is None else col)
    for y in range(int(y0), int(y1), 12):
        cv2.line(img, (x, y), (x, min(int(y1), y + 6)), col, 2, cv2.LINE_AA)
    for y in (y0, (y0 + y1) / 2, y1):
        cv2.rectangle(img, (x - 6, int(y) - 6), (x + 6, int(y) + 6), col, -1)
    cv2.line(img, (x - 80, int(y0)), (x, int(y0)), col, 1, cv2.LINE_AA)
    cv2.line(img, (x - 80, int(y1)), (x, int(y1)), col, 1, cv2.LINE_AA)


def rrect(img, x0, y0, x1, y1, r, col, thick=-1):
    col = _c(col)
    if thick < 0:
        cv2.rectangle(img, (x0 + r, y0), (x1 - r, y1), col, -1)
        cv2.rectangle(img, (x0, y0 + r), (x1, y1 - r), col, -1)
        for cx, cy in ((x0 + r, y0 + r), (x1 - r, y0 + r), (x0 + r, y1 - r), (x1 - r, y1 - r)):
            cv2.circle(img, (cx, cy), r, col, -1, cv2.LINE_AA)
    else:
        for (p0, p1) in (((x0 + r, y0), (x1 - r, y0)), ((x0 + r, y1), (x1 - r, y1)),
                         ((x0, y0 + r), (x0, y1 - r)), ((x1, y0 + r), (x1, y1 - r))):
            cv2.line(img, p0, p1, col, thick, cv2.LINE_AA)
        for (cx, cy, a0) in ((x0 + r, y0 + r, 180), (x1 - r, y0 + r, 270), (x1 - r, y1 - r, 0), (x0 + r, y1 - r, 90)):
            cv2.ellipse(img, (cx, cy), (r, r), 0, a0, a0 + 90, col, thick, cv2.LINE_AA)


# ------------------------------------------------------------------ audio-reactive data
@lru_cache(1)
def bands():
    """Per-frame band energies (NF x 32) and overview envelope of the music bed."""
    a, sr = sf.read(os.path.join(ROOT, "audio", "music.wav"), dtype="float32")
    a = a.mean(1) if a.ndim > 1 else a
    hop = sr // T.FPS
    win = 4096
    edges = np.geomspace(60, 9000, 33)
    out = np.zeros((T.NF + 2, 32), np.float32)
    freqs = np.fft.rfftfreq(win, 1 / sr)
    hann = np.hanning(win).astype(np.float32)
    for f in range(T.NF + 2):
        s = a[f * hop: f * hop + win]
        if len(s) < win:
            s = np.pad(s, (0, win - len(s)))
        sp = np.abs(np.fft.rfft(s * hann))
        for b in range(32):
            m = (freqs >= edges[b]) & (freqs < edges[b + 1])
            out[f, b] = np.log1p(sp[m].mean() * 3) if m.any() else 0
    out /= out.max() + 1e-6
    env = np.array([np.sqrt(np.mean(a[i * hop:(i + 1) * hop] ** 2)) for i in range(T.NF + 2)])
    return out, env / (env.max() + 1e-6)


# ------------------------------------------------------------------ scenes
WORDS = None


def ws(key):
    global WORDS
    if WORDS is None:
        WORDS = T.words()
    return WORDS[key]


def scene_stopwatch(f):
    img = paper().copy()
    k = f - T.scene_frames("stopwatch")[0]
    w = ws("stopwatch")
    tx = T.TEXT["stopwatch"]
    badge4k(img, 70, 120)
    fine(img, "reel 03", W - 70, 135, 18, anchor="r", fname=F_SB)
    fine(img, "(the viral formula)", W - 70, 158, 16, anchor="r")
    barcode(img, W / 2, 230, 170, 60, seed=3)
    # subject: slow push + float
    s = 1 + 0.035 * eio(k / 72)
    yf = math.sin(k / 22) * 6
    m = place(img, "stopwatch", 540, 1130 + yf, 900 * s, f, rot=-4 + 2 * math.sin(k / 30), shadow=0.22,
              grade=dict(sat=0.95, contrast=1.06))
    mist(img, 1610, f, 0.9, seed=1)
    dim_bracket(img, 975, 700, 1560)
    fine(img, "0.5s", 955, 1140, 20, anchor="r", fname=F_SB)
    typed(img, f, w, tx["lead"], F_M, 54, P["ink"], W / 2, 375)
    typed(img, f, w, tx["big"], F_XB, fit(tx["big"][0], F_XB, 124, -2, 960), P["blue"], W / 2, 500, tracking=-2)
    typed(img, f, w, tx["script"], F_SCRIPT, 62, P["blue"], 925, 585, anchor="r", unit="word")
    para(img, ["every scroll is a split-second decision.", "win it before the thumb moves."], W / 2, 1745, 22)
    return img, m


def scene_hook(f):
    k = f - T.scene_frames("hook")[0]
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    r = np.sqrt(((xx - 560) / 700) ** 2 + ((yy - 640) / 900) ** 2)
    img = (C(9, 10, 15)[None, None] + C(46, 50, 62)[None, None] * np.exp(-r ** 2 * 1.6)[..., None]).astype(np.float32)
    s = 1.0 + 0.05 * eio(k / 90)
    m = place(img, "mithridates", 545, 760, 1420 * s, f, shadow=0.0,
              grade=dict(sat=0.7, contrast=1.18, lift=-0.03, cool=0.015))
    # film frame lines + labels
    cv2.rectangle(img, (40, 70), (W - 40, H - 70), _c(C(70, 74, 90)), 1, cv2.LINE_AA)
    fine(img, "00:00:00:01", 64, 108, 18, C(150, 155, 175), fname=F_SB)
    fine(img, "frame 001", W - 64, 108, 18, C(150, 155, 175), anchor="r", fname=F_SB)
    cv2.ellipse(img, (78, 1820), (14, 9), 0, 0, 360, _c(C(150, 155, 175)), 2, cv2.LINE_AA)
    cv2.ellipse(img, (104, 1820), (14, 9), 0, 0, 360, _c(C(150, 155, 175)), 2, cv2.LINE_AA)
    w = ws("hook")
    tx = T.TEXT["hook"]
    # dark gradient behind the type for legibility
    g = np.clip((yy[:, :1] - 1080) / 380, 0, 1) * 0.65
    img *= (1 - g)[..., None] if g.ndim == 2 else 1
    typed(img, f, w, tx["lead"], F_M, 52, C(236, 238, 245), W / 2, 1295)
    typed(img, f, w, tx["big"], F_XB, fit(tx["big"][0], F_XB, 128, -2, 960), P["blue_dark"], W / 2, 1430,
          tracking=-2, glow=0.35)
    typed(img, f, w, tx["script"], F_SCRIPT, 62, C(236, 238, 245), W / 2 + 160, 1515, unit="word")
    return img, m


def scene_idea(f):
    img = paper().copy()
    k = f - T.scene_frames("idea")[0]
    w = ws("idea")
    tx = T.TEXT["idea"]
    badge4k(img, 70, 120)
    fine(img, "soft frames", W - 70, 135, 18, anchor="r", fname=F_SB)
    fine(img, "(one idea per video)", W - 70, 158, 16, anchor="r")
    s = 1 + 0.03 * eio(k / 72)
    m = place(img, "verus", 540, 1100, 900 * s, f, crop=(0.0, 0.86), shadow=0.2, grade=dict(sat=0.85, contrast=1.08))
    mist(img, 1560, f, 0.95, seed=2)
    sparkle(img, 860, 760, 46, f=f)
    sparkle(img, 905, 700, 20, f=f, phase=2)
    sparkle(img, 205, 980, 30, f=f, phase=4)
    typed(img, f, w, tx["lead"], F_M, 54, P["ink"], W / 2, 330)
    typed(img, f, w, tx["big"], F_XB, 150, P["blue"], W / 2, 480, tracking=-3)
    typed(img, f, w, tx["script"], F_SCRIPT, 60, P["blue"], 900, 565, anchor="r", unit="word", after=w[-1][2] + 2)
    para(img, ["pick the one thing you want them to remember.", "everything else is noise."], W / 2, 1745, 22)
    return img, m


def scene_beat(f):
    img = paper().copy()
    f0, f1 = T.scene_frames("beat")
    k = f - f0
    w = ws("beat")
    tx = T.TEXT["beat"]
    kb = (f - f0) % T.BEAT
    pulse = 1 + 0.05 * max(0, 1 - kb / 5) ** 2
    corners(img, 80, 640, 1000, 1290)
    m = place(img, "artemision", 540, 980, 1150 * pulse, f, crop=(0.0, 0.53), shadow=0.18,
              grade=dict(sat=0.9, contrast=1.1))
    mist(img, 1230, f, 0.75, seed=3, speed=1.6)
    # player UI driven by the real music envelope
    _, env = bands()
    x0, x1, yb = 130, 950, 1430
    nb = 64
    prog = clamp(k / (f1 - f0))
    for i in range(nb):
        fi = int(i / nb * T.NF)
        hgt = 8 + 70 * env[min(len(env) - 1, fi)] ** 0.8
        x = x0 + (x1 - x0) * i / nb
        col = P["blue"] if i / nb <= (f0 + prog * (f1 - f0)) / T.NF else C(170, 175, 190)
        cv2.rectangle(img, (int(x), int(yb - hgt / 2)), (int(x + 7), int(yb + hgt / 2)), _c(col), -1)
    px = x0 + (x1 - x0) * (f / T.NF)
    cv2.line(img, (int(px), yb - 55), (int(px), yb + 55), _c(P["ink"]), 2, cv2.LINE_AA)
    cv2.circle(img, (int(px), yb + 62), 7, _c(P["ink"]), -1, cv2.LINE_AA)
    # beat markers
    for bbeat in range(T.NF // T.BEAT):
        x = x0 + (x1 - x0) * bbeat * T.BEAT / T.NF
        cv2.line(img, (int(x), yb + 80), (int(x), yb + 90), _c(C(120, 125, 140)), 2)
    cy = 1560
    ic = _c(P["ink"])
    cv2.polylines(img, [np.array([[380, cy - 12], [395, cy], [380, cy + 12]], np.int32)], False, ic, 3, cv2.LINE_AA)
    cv2.line(img, (330, cy), (395, cy), ic, 3, cv2.LINE_AA)
    cv2.fillPoly(img, [np.array([[470, cy], [495, cy - 15], [495, cy + 15]], np.int32)], ic, cv2.LINE_AA)
    cv2.rectangle(img, (464, cy - 15), (468, cy + 15), ic, -1)
    cv2.rectangle(img, (528, cy - 18), (536, cy + 18), ic, -1)
    cv2.rectangle(img, (548, cy - 18), (556, cy + 18), ic, -1)
    cv2.fillPoly(img, [np.array([[615, cy], [590, cy - 15], [590, cy + 15]], np.int32)], ic, cv2.LINE_AA)
    cv2.rectangle(img, (617, cy - 15), (621, cy + 15), ic, -1)
    cv2.line(img, (690, cy - 12), (714, cy + 12), ic, 3, cv2.LINE_AA)
    cv2.line(img, (714, cy - 12), (690, cy + 12), ic, 3, cv2.LINE_AA)
    fine(img, "00:0%d" % (f // 30 % 10), x0, yb + 120, 18, fname=F_SB)
    fine(img, "00:23", x1, yb + 120, 18, anchor="r", fname=F_SB)
    typed(img, f, w, tx["lead"], F_M, 54, P["ink"], W / 2, 300)
    typed(img, f, w, tx["big"], F_XB, fit(tx["big"][0], F_XB, 140, -3, 960), P["blue"], W / 2, 440, tracking=-3)
    typed(img, f, w, tx["script"], F_SCRIPT, 58, P["blue"], 930, 525, anchor="r", unit="word")
    return img, m


@lru_cache(1)
def engraving():
    im = cv2.cvtColor(cv2.imread(os.path.join(SRC, "harpocrates.jpg")), cv2.COLOR_BGR2RGB).astype(np.float32) / 255
    h, w = im.shape[:2]
    # face + finger-to-lips region of the oval print
    return im[int(h * 0.12):int(h * 0.80), int(w * 0.14):int(w * 0.86)]


def scene_screen(f):
    img = paper().copy()
    f0, f1 = T.scene_frames("screen")
    k = f - f0
    w = ws("screen")
    tx = T.TEXT["screen"]
    typed(img, f, w, tx["lead"], F_M, 54, P["ink"], W / 2, 260)
    typed(img, f, w, tx["big"], F_XB, 150, P["blue"], W / 2, 410, tracking=-3)
    sparkle(img, 920, 200, 40, f=f)
    sparkle(img, 965, 255, 16, f=f, phase=1.5)
    # navy panel
    py0 = 520
    rrect(img, 60, py0, W - 60, 1800, 46, P["navy"])
    rrect(img, 90, py0 + 30, W - 90, 1770, 32, C(60, 72, 120), 2)
    fine(img, "CAPTIONS ON", 120, py0 + 80, 18, C(150, 160, 205), fname=F_B)
    fine(img, "85% WATCH ON MUTE", W - 120, py0 + 80, 18, C(150, 160, 205), anchor="r", fname=F_B)
    # phone (drawn into its own layer, then tilted)
    pw, ph = 560, 1060
    ox, oy = 20, 20
    sub = np.zeros((ph + 40, pw + 40, 3), np.float32)
    alpha = np.zeros((ph + 40, pw + 40), np.float32)
    rrect(sub, ox, oy, ox + pw, oy + ph, 70, C(12, 12, 14))
    rrect(alpha, ox, oy, ox + pw, oy + ph, 70, np.array([1.0]))
    sx0, sy0, sx1, sy1 = ox + 18, oy + 18, ox + pw - 18, oy + ph - 18
    eng = engraving()
    sw, shh = sx1 - sx0, sy1 - sy0
    # slow push inside the screen
    z = 1.0 + 0.08 * eio(k / (f1 - f0))
    eh, ew = eng.shape[:2]
    ch = eh * 0.80 / z                                   # face + finger region of the print
    cw = ch * sw / shh
    fcx, fcy = ew * 0.47, eh * 0.50
    y0c = int(clamp(fcy - ch / 2, 0, eh - ch)); x0c = int(clamp(fcx - cw / 2, 0, ew - cw))
    crop = eng[y0c:y0c + int(ch), x0c:x0c + int(cw)]
    crop = cv2.resize(crop, (sw, shh), interpolation=cv2.INTER_AREA)
    crop = 0.12 + crop * 0.86
    mask = np.zeros((shh, sw), np.float32)
    rrect(mask, 0, 0, sw - 1, shh - 1, 54, np.array([1.0]))
    sub[sy0:sy1, sx0:sx1] = sub[sy0:sy1, sx0:sx1] * (1 - mask[..., None]) + crop * mask[..., None]
    cv2.ellipse(sub, (ox + pw // 2, oy + 48), (62, 18), 0, 0, 360, (0.02, 0.02, 0.02), -1, cv2.LINE_AA)
    # mute icon
    mx, my = sx1 - 70, sy0 + 80
    cv2.fillPoly(sub, [np.array([[mx - 22, my - 9], [mx - 10, my - 9], [mx + 4, my - 22], [mx + 4, my + 22],
                                 [mx - 10, my + 9], [mx - 22, my + 9]], np.int32)], (1, 1, 1), cv2.LINE_AA)
    cv2.line(sub, (mx + 14, my - 10), (mx + 32, my + 10), (1, 1, 1), 4, cv2.LINE_AA)
    cv2.line(sub, (mx + 32, my - 10), (mx + 14, my + 10), (1, 1, 1), 4, cv2.LINE_AA)
    # burned-in captions, word by word, in two lines
    cap = tx["caption"][0].split(" ")
    wl = w[tx["caption"][1][0]:tx["caption"][1][1] + 1]
    shown = [cw_ for cw_, (wd, a, b) in zip(cap, wl) if f >= a - 1]
    if shown:
        lines = [" ".join(shown[:2]), " ".join(shown[2:])]
        for li, ln in enumerate(lines):
            if not ln:
                continue
            ap, xs, base = line_patch(ln.upper(), F_XB, 58, 0)
            wpx = xs[-1] - xs[0]
            bx = int(ox + pw / 2 - wpx / 2 - xs[0])
            by = int(sy1 - 260 + li * 78 - base)
            st = cv2.dilate(ap, np.ones((7, 7), np.uint8))
            for (pc, col) in ((st, (0.03, 0.03, 0.05)), (ap, (1.0, 1.0, 1.0))):
                hh, ww = pc.shape
                xa, ya = max(0, bx), max(0, by)
                xb, yb = min(sub.shape[1], bx + ww), min(sub.shape[0], by + hh)
                pcs = pc[ya - by:yb - by, xa - bx:xb - bx]
                sub[ya:yb, xa:xb] = sub[ya:yb, xa:xb] * (1 - pcs[..., None]) + np.array(col, np.float32) * pcs[..., None]
    # progress bar
    cv2.rectangle(sub, (sx0 + 30, sy1 - 40), (sx1 - 30, sy1 - 34), (0.5, 0.5, 0.5), -1)
    cv2.rectangle(sub, (sx0 + 30, sy1 - 40), (int(sx0 + 30 + (sw - 60) * clamp(k / (f1 - f0))), sy1 - 34),
                  (1, 1, 1), -1)
    sub *= alpha[..., None]
    lay = np.concatenate([sub, alpha[..., None]], 2)
    rot = -4 + 1.5 * math.sin(k / 25)
    Mx = cv2.getRotationMatrix2D(((pw + 40) / 2, (ph + 40) / 2), rot, 1.0)
    Mx[0, 2] += 540 - (pw + 40) / 2
    Mx[1, 2] += 1185 + math.sin(k / 18) * 6 - (ph + 40) / 2
    big = cv2.warpAffine(lay, Mx, (W, H), flags=cv2.INTER_CUBIC, borderValue=0)
    a = np.clip(big[..., 3:4], 0, 1)
    sm = cv2.GaussianBlur(cv2.resize(a[..., 0], (W // 6, H // 6)), (0, 0), 6)
    sm = np.roll(cv2.resize(sm, (W, H)), 30, axis=0)
    img *= (1 - 0.45 * sm)[..., None]
    img[:] = img * (1 - a) + big[..., :3]
    return img, a[..., 0]


def scene_sound(f):
    img = paper().copy()
    f0, f1 = T.scene_frames("sound")
    k = f - f0
    w = ws("sound")
    tx = T.TEXT["sound"]
    typed(img, f, w, tx["lead"], F_M, 54, P["ink"], W / 2, 320)
    typed(img, f, w, tx["big"], F_XB, fit(tx["big"][0], F_XB, 130, -2, 960), P["blue"], W / 2, 460, tracking=-2)
    s = 1 + 0.03 * eio(k / 54)
    m = place(img, "chalcedony", 540, 1040, 880 * s, f, shadow=0.2, grade=dict(sat=0.9, contrast=1.04))
    mist(img, 1460, f, 0.85, seed=4)
    bd, _ = bands()
    e = bd[min(f, len(bd) - 1)]
    nb, x0, x1, yb = 32, 130, 950, 1600
    for i in range(nb):
        hgt = 10 + 160 * e[i] ** 1.6
        x = x0 + (x1 - x0) * i / nb
        col = P["blue"] if i < nb // 2 else C(175, 180, 195)       # literally half
        cv2.rectangle(img, (int(x), int(yb - hgt)), (int(x + 16), int(yb)), _c(col), -1)
    cv2.line(img, (x0, yb + 12), (x1 + 16, yb + 12), _c(P["ink"]), 2, cv2.LINE_AA)
    fine(img, "VO", x0, yb + 48, 18, fname=F_B)
    fine(img, "MUSIC", (x0 + x1) / 2 - 60, yb + 48, 18, fname=F_B)
    fine(img, "SFX", x1 + 16, yb + 48, 18, anchor="r", fname=F_B)
    sparkle(img, 860, 760, 34, f=f)
    return img, m


def scene_loop(f):
    img = paper().copy()
    f0, f1 = T.scene_frames("loop")
    k = f - f0
    w = ws("loop")
    tx = T.TEXT["loop"]
    typed(img, f, w, tx["lead"], F_M, 50, P["ink"], W / 2, 290)
    typed(img, f, w, tx["big"], F_XB, fit(tx["big"][0], F_XB, 140, -3, 960), P["blue"], W / 2, 430, tracking=-3)
    cx, cy = 540, 1060
    # orbit ring with a moving arrow
    rr = 430
    ang0 = -k * 4.0
    for a in range(0, 360, 6):
        if (a // 6) % 2 == 0:
            a1, a2 = math.radians(a + ang0), math.radians(a + 3 + ang0)
            cv2.line(img, (int(cx + rr * math.cos(a1)), int(cy + rr * math.sin(a1))),
                     (int(cx + rr * math.cos(a2)), int(cy + rr * math.sin(a2))), _c(P["ink"] * 0.8), 2, cv2.LINE_AA)
    ah = math.radians(ang0 - 90)
    hx, hy = cx + rr * math.cos(ah), cy + rr * math.sin(ah)
    tang = ah - math.pi / 2
    pts = [(hx + 26 * math.cos(tang), hy + 26 * math.sin(tang)),
           (hx + 14 * math.cos(tang + 2.4), hy + 14 * math.sin(tang + 2.4)),
           (hx + 14 * math.cos(tang - 2.4), hy + 14 * math.sin(tang - 2.4))]
    cv2.fillPoly(img, [np.array(pts, np.int32)], _c(P["blue"]), cv2.LINE_AA)
    m = place(img, "reel", cx, cy, 720, f, rot=k * 7.5, shadow=0.22, grade=dict(sat=0.9, contrast=1.08))
    mist(img, 1480, f, 0.7, seed=5)
    typed(img, f, w, tx["script"], F_SCRIPT, 64, P["blue"], W / 2, 1600, unit="word", after=w[-1][2] + 2)
    fine(img, "↻  replay value = reach", W / 2, 1690, 20, anchor="c", fname=F_SB)
    barcode(img, W / 2, 1760, 130, 44, seed=9)
    return img, m


def logo(img, cx, cy, scale=0.5, col=None, p=1.0):
    col = P["ink"] if col is None else col
    r = int(70 * scale)
    fi, fw = font("InstrumentSerif-Italic.ttf", 150 * scale), font("InstrumentSerif-Regular.ttf", 150 * scale)
    w1, w2 = fi.getlength("half"), fw.getlength("second")
    gap = 26 * scale
    x0 = cx - (2 * r + gap + w1 + w2) / 2
    c = (int(x0 + r), int(cy))
    cv2.circle(img, c, r, _c(col), max(2, int(6 * scale)), cv2.LINE_AA)
    cv2.ellipse(img, c, (r - 1, r - 1), 90, 0, 180 * eo(p), _c(P["accent"]), -1, cv2.LINE_AA)
    a, xs, base = line_patch("half", "InstrumentSerif-Italic.ttf", int(150 * scale))
    _blit(img, a, col, int(x0 + 2 * r + gap - xs[0]), int(cy + 50 * scale - base))
    a2, xs2, base2 = line_patch("second", "InstrumentSerif-Regular.ttf", int(150 * scale))
    _blit(img, a2, col, int(x0 + 2 * r + gap + w1 - xs2[0]), int(cy + 50 * scale - base2))


def outline_text(img, text, size, cx, y, col, t=3):
    a, xs, base = line_patch(text, F_XB, size, 0)
    e = cv2.erode(a, np.ones((2 * t + 1, 2 * t + 1), np.uint8))
    ring = np.clip(a - e, 0, 1)
    wpx = xs[-1] - xs[0]
    _blit(img, ring, col, int(cx - wpx / 2 - xs[0]), int(y - base))


def scene_cta(f):
    img = paper().copy()
    f0, f1 = T.scene_frames("cta")
    k = f - f0
    w = ws("cta")
    tx = T.TEXT["cta"]
    logo(img, W / 2, 150, 0.42, p=clamp(k / 14))
    typed(img, f, w, tx["lead"], F_M, 52, P["ink"], W / 2, 300)
    typed(img, f, w, tx["big"], F_XB, fit(tx["big"][0], F_XB, 150, -3, 960), P["blue"], W / 2, 440, tracking=-3)
    st, _ = word_window(w, tx["big"][1])
    fine(img, "VIDEO EDITING AGENCY", W / 2, 505, 20, anchor="c", fname=F_B, op=clamp((f - st - 6) / 8))
    corners(img, 70, 90, W - 70, 540, 36)
    sparkle(img, 940, 600, 36, f=f)
    sparkle(img, 140, 560, 22, f=f, phase=3)
    py0 = 640
    rrect(img, 60, py0, W - 60, 1810, 46, P["navy"])
    rrect(img, 90, py0 + 30, W - 90, 1780, 32, C(60, 72, 120), 2)
    outline_text(img, "we", 330, 300, 1020, C(70, 84, 140), 3)
    outline_text(img, "edit", 300, 720, 1350, C(70, 84, 140), 3)
    s = 1 + 0.025 * eio(k / 140)
    m = place(img, "hermes", 600, 1205, 1300 * s, f, crop=(0.0, 0.43), shadow=0.0, grade=dict(sat=0.9, contrast=1.1))
    # brush "edit" over the subject
    p = clamp((f - st) / 8)
    if p > 0:
        a, xs, base = line_patch("edit.", F_SCRIPT, 270, 0)
        a = cv2.warpAffine(a, cv2.getRotationMatrix2D((a.shape[1] / 2, a.shape[0] / 2), 9, 1.0), (a.shape[1], a.shape[0]))
        sh_ = cv2.GaussianBlur(a, (0, 0), 8) * 0.35
        _blit(img, sh_ * eo(p), C(5, 8, 25), int(130 - (1 - eo(p)) * 40), int(1450 - base + 10))
        _blit(img, a * eo(p), C(250, 250, 252), int(120 - (1 - eo(p)) * 40), int(1440 - base))
    # DM pill
    d0, _ = word_window(w, tx["dm"][1])
    q = clamp((f - d0 + 2) / 6)
    if q > 0:
        sc = 1.25 - 0.25 * eo(q)
        pw_, ph_ = int(600 * sc), int(124 * sc)
        x0, y0 = int(540 - pw_ / 2), int(1600 - ph_ / 2)
        rrect(img, x0, y0, x0 + pw_, y0 + ph_, ph_ // 2, P["blue"] * eo(q) + P["navy"] * (1 - eo(q)))
        text_line(img, tx["dm"][0], F_XB, int(66 * sc), C(255, 255, 255), 540, 1600 + 24 * sc)
    fine(img, "link in bio  →  halfsecond", W / 2, 1745, 20, C(170, 180, 220), anchor="c", fname=F_SB,
         op=clamp((f - d0 - 10) / 8))
    return img, m


SCENE_FN = {"stopwatch": scene_stopwatch, "hook": scene_hook, "idea": scene_idea, "beat": scene_beat,
            "screen": scene_screen, "sound": scene_sound, "loop": scene_loop, "cta": scene_cta}


def scene_at(f):
    for key, b0, nb, _, _ in T.SCENES:
        if b0 * T.BEAT <= f < (b0 + nb) * T.BEAT:
            return key
    return T.SCENES[-1][0]


# ------------------------------------------------------------------ FX
def invert(x):
    return 1 - x


def white_shape(x, m):
    """Ref1-style: the subject becomes a white silhouette over the inverted frame."""
    return invert(x) * (1 - m[..., None]) + m[..., None] * 0.985


def dir_blur(x, length, vertical=False):
    if length < 2:
        return x
    q = 4
    sm = cv2.resize(x, (W // q, H // q), interpolation=cv2.INTER_AREA)
    L = max(3, int(length / q) | 1)
    k = np.zeros((L, L), np.float32)
    if vertical:
        k[:, L // 2] = 1
    else:
        k[L // 2, :] = 1
    sm = cv2.filter2D(sm, -1, k / L, borderType=cv2.BORDER_REFLECT)
    big = cv2.resize(sm, (W, H), interpolation=cv2.INTER_LINEAR)
    mix = clamp(length / 50)
    return x * (1 - mix) + big * mix


def zoom_blur(x, amt, steps=8):
    if amt < 0.004:
        return x
    acc = x.copy()
    for i in range(1, steps):
        M = cv2.getRotationMatrix2D((W / 2, H / 2), 0, 1 + amt * i / (steps - 1))
        acc += cv2.warpAffine(x, M, (W, H), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
    return acc / steps


def spin_blur(x, deg, steps=9, cx=W / 2, cy=H / 2):
    if abs(deg) < 0.3:
        return x
    acc = np.zeros_like(x)
    for i in range(steps):
        M = cv2.getRotationMatrix2D((cx, cy), deg * (i / (steps - 1) - 0.5), 1.0)
        acc += cv2.warpAffine(x, M, (W, H), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
    return acc / steps


def xform(x, s=1.0, rot=0.0, dx=0.0, dy=0.0):
    M = cv2.getRotationMatrix2D((W / 2, H / 2), rot, s)
    M[0, 2] += dx
    M[1, 2] += dy
    return cv2.warpAffine(x, M, (W, H), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)


def chroma(x, amt):
    if amt < 0.0005:
        return x
    out = x.copy()
    for c, s in ((0, 1 + amt), (2, 1 - amt)):
        M = cv2.getRotationMatrix2D((W / 2, H / 2), 0, s)
        out[..., c] = cv2.warpAffine(x[..., c], M, (W, H), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
    return out


def scale_mask(m, s, cx, cy):
    M = cv2.getRotationMatrix2D((cx, cy), 0, s)
    return cv2.warpAffine(m, M, (W, H), flags=cv2.INTER_LINEAR, borderValue=0)


def mask_centre(m):
    ys, xs = np.nonzero(m > 0.5)
    if len(xs) == 0:
        return W / 2, H / 2
    return float(xs.mean()), float(ys.mean())


def frame(f):
    BND = T.boundaries()
    # which transition (if any) affects this frame
    for b, kind, ka, kb in BND:
        if b - 6 <= f < b + 5:
            return transition(f, b, kind, ka, kb)
    key = scene_at(f)
    img, m = SCENE_FN[key](f)
    if key in ("screen", "loop", "cta", "idea", "stopwatch"):        # beat punch (whole frame)
        kb = f % T.BEAT
        if kb < 5:
            img = xform(img, 1 + 0.018 * (1 - kb / 5) ** 2)
    return accent(f, img, m)


def accent(f, img, m):
    for af, kind in T.accents():
        d = f - af
        if 0 <= d < 2:
            if kind == "invert":
                img = invert(img)
            else:
                img = white_shape(img, m) if d == 0 else invert(img)
            img = chroma(img, 0.006)
        elif 2 <= d < 6:
            img = xform(img, 1 + 0.04 * (1 - eo((d - 2) / 4)))
    return img


def transition(f, b, kind, ka, kb):
    fa, fb = SCENE_FN[ka], SCENE_FN[kb]
    d = f - b                                     # <0: outgoing, >=0: incoming
    if kind == "silhouette":
        if d < -4:
            img, m = fa(f)
            return img
        if d < 0:
            A, m = fa(b - 5)
            B, _ = fb(b)
            u = (d + 5) / 4                          # 0.25..1
            cx, cy = mask_centre(m)
            sm = scale_mask(m, 1 + 9 * u ** 2.2, cx, cy)
            out = A * (1 - sm[..., None]) + B * sm[..., None]
            edge = np.clip(sm - cv2.erode(sm, np.ones((9, 9), np.uint8)), 0, 1)
            out = out + edge[..., None] * 0.9
            return zoom_blur(out, 0.06 * u)
        B, m = fb(f)
        if d < 2:
            return chroma(invert(B), 0.01)
        return xform(B, 1 + 0.06 * (1 - eo((d - 2) / 3)))
    if kind == "invert_smear":
        if d < -2:
            return fa(f)[0]
        if d < 0:
            A, _ = fa(f)
            A = dir_blur(A, 60 * (d + 3), vertical=True)
            return invert(A) if d == -1 else A
        B, _ = fb(f)
        B = dir_blur(xform(B, 1, 0, 0, -60 * max(0, 3 - d)), 140 * max(0, 1 - d / 3), vertical=True)
        return invert(B) if d == 0 else B
    if kind in ("white_shape", "invert_shape"):
        if d < -2:
            return fa(f)[0]
        if d < 0:
            A, m = fa(f)
            return white_shape(A, m) if (kind == "white_shape" and d == -1) else invert(A) if d == -1 else A
        B, m = fb(f)
        if d == 0:
            if kind == "white_shape":
                return chroma(white_shape(B, m), 0.01)
            return invert(B) * (1 - m[..., None]) + B * m[..., None]     # subject stays, world inverts
        if d == 1:
            return invert(B)
        return xform(B, 1 + 0.07 * (1 - eo((d - 2) / 3)))
    if kind == "whip":
        if d < -3:
            return fa(f)[0]
        if d < 0:
            A, _ = fa(f)
            q = (d + 4) / 3
            return dir_blur(xform(A, 1, 0, -W * 0.8 * q ** 2), 180 * q)
        B, _ = fb(f)
        q = 1 - eo((d + 1) / 4)
        return dir_blur(xform(B, 1, 0, W * 0.8 * q), 180 * q)
    if kind == "zoom":
        if d < -3:
            return fa(f)[0]
        if d < 0:
            A, _ = fa(f)
            q = (d + 4) / 3
            return zoom_blur(xform(A, 1 + 0.5 * q ** 2), 0.25 * q)
        B, _ = fb(f)
        q = 1 - eo((d + 1) / 4)
        return zoom_blur(xform(B, 1 + 0.35 * q), 0.25 * q)
    if kind == "spin":
        if d < -4:
            return fa(f)[0]
        if d < 0:
            A, _ = fa(f)
            q = (d + 5) / 4
            return spin_blur(xform(A, 1 + 0.15 * q, -40 * q ** 2), 50 * q, cy=1060)
        B, _ = fb(f)
        q = 1 - eo((d + 1) / 4)
        out = spin_blur(xform(B, 1 + 0.12 * q, 35 * q), 50 * q)
        return invert(out) if d == 0 else out
    return fa(f)[0] if d < 0 else fb(f)[0]


# ------------------------------------------------------------------ finish
_VIG = None
_GR = None


def finish(x, f):
    global _VIG, _GR
    if _VIG is None:
        yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
        r = np.sqrt(((xx - W / 2) / (W * 0.7)) ** 2 + ((yy - H / 2) / (H * 0.7)) ** 2)
        _VIG = (1 - P["vignette"] * np.clip(r, 0, 1.3) ** 2)[..., None].astype(np.float32)
        g = np.random.default_rng(9)
        _GR = [cv2.GaussianBlur(g.standard_normal((H, W)).astype(np.float32), (0, 0), 0.6) for _ in range(4)]
        _GR = [t / t.std() for t in _GR]
    x = x * _VIG
    rng = np.random.default_rng(f)
    g = np.roll(_GR[f % 4], (int(rng.integers(0, H)), int(rng.integers(0, W))), (0, 1))
    x = x + g[..., None] * P["grain"]
    return np.clip(x, 0, 1)


def render(fs):
    for f in fs:
        y = finish(frame(f), f)
        cv2.imwrite(os.path.join(OUT, f"{f:04d}.png"), cv2.cvtColor((y * 255 + 0.5).astype(np.uint8), cv2.COLOR_RGB2BGR),
                    [cv2.IMWRITE_PNG_COMPRESSION, 1])
    return len(fs)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default=None)
    ap.add_argument("--procs", type=int, default=4)
    a = ap.parse_args()
    os.makedirs(OUT, exist_ok=True)
    fs = [int(v) for v in a.only.split(",")] if a.only else list(range(T.NF))
    bands()                                    # warm cache before forking
    chunks = [fs[i::a.procs * 4] for i in range(a.procs * 4)]
    with Pool(a.procs) as p:
        n = sum(p.map(render, [c for c in chunks if c]))
    print("rendered", n)


if __name__ == "__main__":
    main()
