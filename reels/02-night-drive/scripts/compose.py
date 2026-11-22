"""Reel 02 "Night Drive": high-energy VFX edit compositor.

Reads 4K source clips from source/, applies speed ramps (optical-flow slow-mo,
multi-frame motion blur), punch-ins, whips, zoom blur, RGB split, glitch,
shake, flashes, a teal/orange grade with bloom and grain, and kinetic type.
Frames go to build/frames/, then encode.sh muxes picture + sound.

    python scripts/compose.py                 # all frames (4 processes)
    python scripts/compose.py --only 0,96,288 # just these frames (for checks)
"""
import argparse
import math
import os
import subprocess
import sys
from functools import lru_cache
from multiprocessing import Pool

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import timeline as T  # noqa: E402

SRC = os.path.join(ROOT, "source")
OUTDIR = os.path.join(ROOT, "build", "frames")
FONTS = os.path.join(ROOT, "..", "01-half-second", "assets", "fonts")
W, H = 1080, 1920
cv2.setNumThreads(1)

# Style parameters (kept apart from shot/timecode decisions in timeline.py).
STYLE = {
    "ink": (14, 13, 12),
    "bone": (240, 233, 221),
    "accent": (255, 77, 34),     # halfsecond signal orange
    "sat": 1.12,
    "contrast": 1.10,
    "teal": 0.055,               # shadow push
    "warm": 0.05,                # highlight push
    "bloom": 0.55,
    "bloom_tint": (1.0, 0.72, 0.55),
    "vignette": 0.34,
    "grain": 0.026,
    "sharpen": 0.28,
}
BONE = np.array(STYLE["bone"], np.float32) / 255
ACC = np.array(STYLE["accent"], np.float32) / 255
INK = np.array(STYLE["ink"], np.float32) / 255

ANTON, MONO_B, SERIF, SERIF_I = ("Anton-Regular.ttf", "SpaceMono-Bold.ttf",
                                 "InstrumentSerif-Regular.ttf", "InstrumentSerif-Italic.ttf")


# ------------------------------------------------------------------ helpers
def clamp(x, a=0.0, b=1.0):
    return max(a, min(b, x))


def eo(x):                                   # ease-out cubic
    x = clamp(x)
    return 1 - (1 - x) ** 3


def eio(x):
    x = clamp(x)
    return x * x * (3 - 2 * x)


@lru_cache(None)
def probe(clip):
    p = os.path.join(SRC, f"{clip}.mp4")
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                          "stream=width,height,r_frame_rate", "-of", "csv=p=0", p],
                         capture_output=True, text=True).stdout.strip().split(",")
    n, d = out[2].split("/")
    return int(out[0]), int(out[1]), float(n) / float(d)


def read_region(clip, t0, t1, x0, rw, scale=None):
    w, h, fps = probe(clip)
    vf = f"crop={rw}:{h}:{x0}:0"
    if scale:
        vf += f",scale={scale[0]}:{scale[1]}:flags=lanczos"
        rw, h = scale
    cmd = ["ffmpeg", "-v", "error", "-ss", f"{max(0, t0):.4f}", "-i", os.path.join(SRC, f"{clip}.mp4"),
           "-t", f"{t1 - t0:.4f}", "-vf", vf, "-f", "rawvideo", "-pix_fmt", "rgb24", "-"]
    buf = subprocess.run(cmd, capture_output=True).stdout
    fr = np.frombuffer(buf, np.uint8).reshape(-1, h, rw, 3)
    return fr, fps


# ------------------------------------------------------------------ shot sampling
def shot_speeds(s):
    n, spd = s["n"], s["spd"]
    if isinstance(spd, (int, float)):
        sp = np.full(n, float(spd))
    else:
        u = np.linspace(0, 1, n)
        sp = spd[0] + (spd[1] - spd[0]) * (u * u * (3 - 2 * u))
    ts = s["src"] + np.concatenate([[0], np.cumsum(sp[:-1])]) / T.FPS
    return ts, sp


class ShotSource:
    """Holds the decoded crop region of one shot and returns frames at any
    source time, with optical-flow in-betweens or motion blur as needed."""

    def __init__(self, s):
        self.s = s
        w, h, fps = probe(s["clip"])
        self.w, self.h, self.fps = w, h, fps
        self.ts, self.sp = shot_speeds(s)
        strip = h * 9 / 16
        zmin = min(s["z"])
        rmax = math.radians(max(abs(r) for r in s["rot"]))
        view_w = strip / zmin
        view_h = h / zmin
        bound = view_w * math.cos(rmax) + view_h * math.sin(rmax)
        pan = abs(s["cx1"] - s["cx"]) * w
        rw = int(min(w, bound + pan + 0.10 * strip))
        rw -= rw % 2
        centre = (s["cx"] + s["cx1"]) / 2 * w
        x0 = int(clamp(centre - rw / 2, 0, w - rw))
        x0 -= x0 % 2
        self.x0, self.rw = x0, rw
        self.t0 = max(0.0, self.ts.min() - 2 / fps)
        t1 = self.ts.max() + 3 / fps
        self.frames, _ = read_region(s["clip"], self.t0, t1, x0, rw)
        self.flow = {}
        self.dis = cv2.DISOpticalFlow_create(cv2.DISOPTICAL_FLOW_PRESET_MEDIUM)

    def _get(self, i):
        i = int(clamp(i, 0, len(self.frames) - 1))
        return self.frames[i]

    def _interp(self, i, a):
        key = i
        A, B = self._get(i), self._get(i + 1)
        if key not in self.flow:
            q = 0.25
            ga = cv2.cvtColor(cv2.resize(A, None, fx=q, fy=q, interpolation=cv2.INTER_AREA), cv2.COLOR_RGB2GRAY)
            gb = cv2.cvtColor(cv2.resize(B, None, fx=q, fy=q, interpolation=cv2.INTER_AREA), cv2.COLOR_RGB2GRAY)
            fab = self.dis.calc(ga, gb, None)
            fba = self.dis.calc(gb, ga, None)
            up = lambda f: (cv2.resize(f, (A.shape[1], A.shape[0])) / q).astype(np.float32)  # noqa: E731
            self.flow = {key: (up(fab), up(fba))}
        fab, fba = self.flow[key]
        a = np.float32(a)
        hh, ww = A.shape[:2]
        gx, gy = np.meshgrid(np.arange(ww, dtype=np.float32), np.arange(hh, dtype=np.float32))
        wa = cv2.remap(A, gx - a * fab[..., 0], gy - a * fab[..., 1], cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
        wb = cv2.remap(B, gx - (1 - a) * fba[..., 0], gy - (1 - a) * fba[..., 1], cv2.INTER_LINEAR,
                       borderMode=cv2.BORDER_REFLECT)
        return (wa.astype(np.float32) * (1 - a) + wb.astype(np.float32) * a)

    def frame(self, k):
        """Float32 RGB 0..1 region frame for shot-local output frame k."""
        x = (self.ts[k] - self.t0) * self.fps
        sp = self.sp[k]
        span = sp * self.fps / T.FPS                    # source frames per output frame
        if span > 1.6:                                  # motion blur (shutter ~ 1.0)
            m = int(min(8, max(2, round(span))))
            acc = np.zeros(self.frames.shape[1:], np.float32)
            for j in range(m):
                acc += self._get(round(x - span * j / m)).astype(np.float32)
            return acc / (m * 255)
        i = int(math.floor(x))
        a = x - i
        if span < 0.95 and 0.12 < a < 0.88:
            return self._interp(i, a) / 255
        return self._get(round(x)).astype(np.float32) / 255


# ------------------------------------------------------------------ image FX
def place(img, cxr, cyr, s, rot, dx=0.0, dy=0.0):
    M = cv2.getRotationMatrix2D((cxr, cyr), rot, s)
    M[0, 2] += W / 2 - cxr + dx
    M[1, 2] += H / 2 - cyr + dy
    interp = cv2.INTER_AREA if s < 0.7 else cv2.INTER_CUBIC
    if s < 0.7:                                       # pre-shrink to avoid aliasing
        f = s / 0.9
        img = cv2.resize(img, None, fx=f, fy=f, interpolation=cv2.INTER_AREA)
        M = cv2.getRotationMatrix2D((cxr * f, cyr * f), rot, 0.9)
        M[0, 2] += W / 2 - cxr * f + dx
        M[1, 2] += H / 2 - cyr * f + dy
        interp = cv2.INTER_CUBIC
    return cv2.warpAffine(img, M, (W, H), flags=interp, borderMode=cv2.BORDER_REFLECT)


def zoom_blur(x, amt, steps=7):
    if amt <= 0.003:
        return x
    acc = x.copy()
    for i in range(1, steps):
        s = 1 + amt * i / (steps - 1)
        M = cv2.getRotationMatrix2D((W / 2, H / 2), 0, s)
        acc += cv2.warpAffine(x, M, (W, H), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
    return acc / steps


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
    m = clamp(length / 60)
    return x * (1 - m) + big * m


def chroma(x, amt):
    if amt <= 0.0005:
        return x
    out = x.copy()
    for c, s in ((0, 1 + amt), (2, 1 - amt)):
        M = cv2.getRotationMatrix2D((W / 2, H / 2), 0, s)
        out[..., c] = cv2.warpAffine(x[..., c], M, (W, H), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
    return out


def glitch(x, amt, rng):
    if amt <= 0.02:
        return x
    out = x.copy()
    for _ in range(int(4 + amt * 16)):
        y = int(rng.integers(0, H))
        hh = int(rng.integers(6, 120))
        dx = int(rng.normal(0, 90 * amt))
        out[y:y + hh] = np.roll(out[y:y + hh], dx, axis=1)
    d = int(22 * amt)
    out[..., 0] = np.roll(out[..., 0], d, axis=1)
    out[..., 2] = np.roll(out[..., 2], -d, axis=1)
    if amt > 0.4:                                     # a few blown-out blocks
        for _ in range(3):
            y, xx = int(rng.integers(0, H - 80)), int(rng.integers(0, W - 200))
            out[y:y + int(rng.integers(10, 60)), xx:xx + int(rng.integers(80, 400))] *= rng.uniform(1.3, 2.2)
    return out


def grade(x, g):
    x = x * g.get("exposure", 1.0)
    lum = x @ np.array([0.2126, 0.7152, 0.0722], np.float32)
    sat = g.get("sat", 1.0) * STYLE["sat"]
    x = lum[..., None] + (x - lum[..., None]) * sat
    c = g.get("contrast", 1.0) * STYLE["contrast"]
    x = 0.42 + (np.maximum(x, 0) - 0.42) * c
    l = np.clip(lum, 0, 1)[..., None]
    x = x + (1 - l) ** 3 * np.array([-0.35, 0.4, 0.75], np.float32) * STYLE["teal"]
    x = x + l ** 2 * np.array([1.0, 0.42, -0.45], np.float32) * STYLE["warm"]
    return np.maximum((x - 0.012) / 0.988, 0)


def make_vignette():
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    r = np.sqrt(((xx - W / 2) / (W * 0.62)) ** 2 + ((yy - H / 2) / (H * 0.62)) ** 2)
    return (1 - STYLE["vignette"] * np.clip(r, 0, 1.4) ** 2.2)[..., None].astype(np.float32)


VIG = None
GRAIN = None


def finish(x, f, rng):
    global VIG, GRAIN
    if VIG is None:
        VIG = make_vignette()
        g = np.random.default_rng(3)
        GRAIN = [cv2.GaussianBlur(g.standard_normal((H, W)).astype(np.float32), (0, 0), 0.65) for _ in range(4)]
        GRAIN = [t / t.std() for t in GRAIN]
    # sharpen (sources are supersampled from 4K; this restores micro-contrast)
    bl = cv2.GaussianBlur(x, (0, 0), 1.1)
    x = x + STYLE["sharpen"] * (x - bl)
    # bloom / halation
    sm = cv2.resize(x, (W // 4, H // 4), interpolation=cv2.INTER_AREA)
    br = np.maximum(sm - 0.62, 0)
    glow = cv2.GaussianBlur(br, (0, 0), 5) + 0.8 * cv2.GaussianBlur(br, (0, 0), 18)
    glow = cv2.resize(glow, (W, H), interpolation=cv2.INTER_LINEAR)
    x = x + glow * STYLE["bloom"] * np.array(STYLE["bloom_tint"], np.float32)
    x = x * VIG
    # soft highlight shoulder
    x = np.where(x > 0.82, 0.82 + 0.18 * np.tanh((x - 0.82) / 0.18), x)
    g = np.roll(GRAIN[f % 4], (int(rng.integers(0, H)), int(rng.integers(0, W))), (0, 1))
    x = x + g[..., None] * STYLE["grain"]
    return np.clip(x, 0, 1)


# ------------------------------------------------------------------ type
@lru_cache(None)
def font(name, size):
    return ImageFont.truetype(os.path.join(FONTS, name), int(size))


@lru_cache(256)
def word_patch(text, fname, size, tracking=0):
    """Tight white RGBA-alpha patch (float32 alpha) for a text string."""
    f = font(fname, size)
    widths = [f.getlength(ch) for ch in text]
    tw = int(sum(widths) + tracking * (len(text) - 1)) + 4
    asc, desc = f.getmetrics()
    pad = int(size * 0.25)
    im = Image.new("L", (tw + 2 * pad, asc + desc + 2 * pad), 0)
    d = ImageDraw.Draw(im)
    x = pad
    for ch, w in zip(text, widths):
        d.text((x, pad), ch, font=f, fill=255)
        x += w + tracking
    a = np.asarray(im, np.float32) / 255
    ys, xs = np.nonzero(a > 0.01)
    a = a[max(0, ys.min() - pad):ys.max() + pad, max(0, xs.min() - pad):xs.max() + pad]
    return a


def fit_size(text, fname, size, tracking, max_w):
    w = sum(font(fname, size).getlength(c) for c in text) + tracking * (len(text) - 1)
    return int(size * min(1.0, max_w / w))


def stamp(x, alpha, color, cx, cy, scale=1.0, opacity=1.0, split=0.0, glow=0.0, anchor="c"):
    """Composite a text alpha patch onto x (in place) at (cx, cy)."""
    if opacity <= 0:
        return x
    a = alpha
    if abs(scale - 1) > 0.01:
        a = cv2.resize(a, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA if scale < 1 else cv2.INTER_LINEAR)
    ph, pw = a.shape
    pad = int(30 + abs(split) + (40 if glow else 0))
    a = np.pad(a, pad)
    ph, pw = a.shape
    if anchor == "c":
        x0 = int(cx - pw / 2)
    else:
        cols = np.nonzero(a.max(0) > 0.02)[0]
        x0 = int(cx - cols[0]) if anchor == "l" else int(cx - cols[-1])
    y0 = int(cy - ph / 2)
    xa, ya = max(0, x0), max(0, y0)
    xb, yb = min(W, x0 + pw), min(H, y0 + ph)
    if xb <= xa or yb <= ya:
        return x
    sub = a[ya - y0:yb - y0, xa - x0:xb - x0] * opacity
    region = x[ya:yb, xa:xb]
    if glow > 0:
        gl = cv2.GaussianBlur(sub, (0, 0), 14) * glow
        region += gl[..., None] * np.asarray(color, np.float32) * 0.9
    col = np.asarray(color, np.float32)
    if split > 0.5:
        s = int(round(split))
        for c, sh in ((0, -s), (1, 0), (2, s)):
            m = np.roll(sub, sh, axis=1)
            region[..., c] = region[..., c] * (1 - m) + col[c] * m
    else:
        region[:] = region * (1 - sub[..., None]) + col * sub[..., None]
    return x


def pop(k, frames=4):
    """(scale, opacity, split) for a word k frames after it lands."""
    p = eo(k / frames)
    return 1.32 - 0.32 * p, clamp(k / 2 + 0.35), 16 * (1 - eo(k / 5))


def draw_text(x, f):
    for item in T.TEXT:
        kind = item[0]
        if kind == "stack":
            lines = item[1:]
            if not (lines[0][1] <= f < T.END):
                continue
            ys = [760, 905, 1110]
            for i, (txt, f_in) in enumerate(lines):
                if f < f_in:
                    continue
                k = f - f_in
                sc, op, sp = pop(k)
                last = i == len(lines) - 1
                size = 250 if last else 150
                patch = word_patch(txt, ANTON, size, 6)
                stamp(x, patch, ACC if last else BONE, W / 2, ys[i], sc, op, sp, glow=0.5 if last else 0.25)
            continue
        _, txt, a, b = item
        if not (a <= f < b):
            continue
        k = f - a
        if kind == "big":
            size = fit_size(txt, ANTON, 210, 8, 900)
            patch = word_patch(txt, ANTON, size, 8)
            sc, op, sp = pop(k) if a > 0 else (1.0, 1.0, 0.0)   # the hook frame 0 is fully legible
            sc = min(sc * (1 + 0.004 * k), 1000 / patch.shape[1])
            stamp(x, patch, BONE, W / 2, 930, sc, op, sp, glow=0.35)
        elif kind == "sub":
            n = min(len(txt), k + 1)
            p = word_patch(txt[:n], MONO_B, 34, 10)
            stamp(x, p, BONE, W / 2, 1075, 1.0, 0.9)
            # orange "on air" dot blinking
            if (k // 6) % 2 == 0:
                cv2.circle(x, (int(W / 2 - p.shape[1] / 2 - 10), 1075), 9, tuple(float(c) for c in ACC), -1,
                           cv2.LINE_AA)
        elif kind == "count":
            sc, op, sp = pop(k, 3)
            sc *= 1 + 0.012 * k
            stamp(x, word_patch(txt, ANTON, 640, 0), BONE, W / 2, 920, sc, op, sp * 1.5, glow=0.45)
        elif kind == "tag":
            n = min(len(txt), (k + 1) * 2)
            p = word_patch(txt[:n], MONO_B, 30, 6)
            cv2.rectangle(x, (72, 289), (86, 303), tuple(float(c) for c in ACC), -1)
            stamp(x, p, BONE, 104, 296, 1.0, 0.92, anchor="l")
            ln = int(eo(k / 10) * 340)
            cv2.line(x, (72, 330), (72 + ln, 330), tuple(float(c) * 0.55 for c in BONE), 2, cv2.LINE_AA)
            hs = word_patch("HALFSECOND / 002", MONO_B, 26, 5)
            stamp(x, hs, BONE * 0.8, W - 72, 296, 1.0, 0.8, anchor="r")
    return x


# ------------------------------------------------------------------ overlays
@lru_cache(4)
def overlay_frames(name, t0, n):
    if name == "sparks":
        fr, fps = read_region("3463", t0, t0 + n / T.FPS + 0.3, 0, 1080)
    else:                                            # smoke, 4K landscape -> vertical crop
        w, h, _ = probe("1960")
        fr, fps = read_region("1960", t0, t0 + n / T.FPS + 0.3, (w - 1215) // 2, 1215, scale=(W, H))
    return fr, fps


def screen(x, o, op):
    return 1 - (1 - x) * (1 - o * op)


# ------------------------------------------------------------------ endcard
def draw_logo(x, cx, cy, scale, p_ring, p_word):
    r = int(70 * scale)
    col = tuple(float(c) for c in BONE)
    acc = tuple(float(c) for c in ACC)
    fi, fw = font(SERIF_I, 150 * scale), font(SERIF, 150 * scale)
    w1, w2 = fi.getlength("half"), fw.getlength("second")
    gap = 28 * scale
    total = 2 * r + gap + w1 + w2
    x0 = cx - total / 2
    c = (int(x0 + r), int(cy))
    if p_ring > 0:
        cv2.ellipse(x, c, (r, r), -90, 0, 360 * eo(p_ring * 1.6), col, max(3, int(6 * scale)), cv2.LINE_AA)
        sweep = 180 * eo(clamp((p_ring - 0.25) / 0.75))
        if sweep > 1:
            cv2.ellipse(x, c, (r - 1, r - 1), 90, 0, sweep, acc, -1, cv2.LINE_AA)
    if p_word > 0:
        q = eo(p_word)
        stamp(x, wordmark(int(150 * scale)), BONE, x0 + 2 * r + gap, cy + (1 - q) * 50, 1, q, anchor="l")


@lru_cache(4)
def wordmark(size):
    """'half' (italic) + 'second' on one baseline; vertically centred on the
    x-height so it lines up with the disc like Reel 01's logo."""
    fi, fw = font(SERIF_I, size), font(SERIF, size)
    w1, w2 = fi.getlength("half"), fw.getlength("second")
    asc = fi.getmetrics()[0]
    im = Image.new("L", (int(w1 + w2) + 40, int(size * 2)), 0)
    d = ImageDraw.Draw(im)
    base = int(size * 1.25)
    d.text((10, base), "half", font=fi, fill=255, anchor="ls")
    d.text((10 + w1, base), "second", font=fw, fill=255, anchor="ls")
    a = np.asarray(im, np.float32) / 255
    # crop so the vertical centre sits at the middle of the x-height
    xh = size * 0.45
    mid = int(base - xh / 2)
    half = int(size * 0.95)
    a = a[mid - half:mid + half]
    cols = np.nonzero(a.max(0) > 0.02)[0]
    return a[:, max(0, cols[0] - 4):cols[-1] + 4]


def endcard(f, rng):
    k = f - T.END
    x = np.ones((H, W, 3), np.float32) * INK
    sm, sfps = overlay_frames("smoke", 2.0, T.NF - T.END)
    o = sm[min(len(sm) - 1, int(k / T.FPS * sfps))].astype(np.float32) / 255
    x = screen(x, o * np.array([1.0, 0.8, 0.7], np.float32), 0.16)
    # warm floor glow behind the logo
    draw_logo(x, W / 2, 800, 1.05, clamp(k / 14), clamp((k - 4) / 10))
    if k >= 12:
        n = min(26, (k - 11) * 3)
        p = word_patch("VIDEO EDITING AGENCY"[:n], MONO_B, 30, 9)
        stamp(x, p, BONE * 0.75, W / 2, 985, 1, 0.9)
    if k >= 22:
        sc, op, sp = pop(k - 22)
        stamp(x, word_patch("Your brand next?", SERIF, 104), BONE, W / 2, 1185, sc * 0.92 + 0.08, op, sp * 0.5)
    if k >= 30:
        sc, op, sp = pop(k - 30)
        stamp(x, word_patch("DM “EDIT”", ANTON, 170, 6), ACC, W / 2, 1345, sc, op, sp, glow=0.6)
    if k >= 40:
        p = word_patch("CUTS · SPEED RAMPS · VFX · SOUND", MONO_B, 24, 5)
        stamp(x, p, BONE * 0.6, W / 2, 1460, 1, clamp((k - 40) / 6) * 0.9)
    cv2.line(x, (72, 196), (W - 72, 196), tuple(float(c) * 0.35 for c in BONE), 2, cv2.LINE_AA)
    stamp(x, word_patch("HALFSECOND / 002", MONO_B, 24, 5), BONE * 0.5, 72, 168, 1, 1, anchor="l")
    stamp(x, word_patch("NIGHT DRIVE", MONO_B, 24, 5), BONE * 0.5, W - 72, 168, 1, 1, anchor="r")
    # entrance: flash + glitch + punch
    if k < 8:
        x = glitch(x, 0.9 * (1 - k / 8), rng)
        x = chroma(x, 0.012 * (1 - k / 8))
    if k < 4:
        x = x + (1 - k / 4) ** 2 * 0.9
    return x


# ------------------------------------------------------------------ shot render
def smooth_noise(seed, t, amp):
    r = np.random.default_rng(seed)
    ph = r.uniform(0, 2 * np.pi, 6)
    fq = (1.7, 3.1, 5.3)
    dx = sum(math.sin(t * fq[i] * 2 * np.pi + ph[i]) / (i + 1) for i in range(3))
    dy = sum(math.sin(t * fq[i] * 2 * np.pi * 1.13 + ph[i + 3]) / (i + 1) for i in range(3))
    return dx * amp, dy * amp


def render_shot(si, s, only=None):
    src = ShotSource(s)
    rng = np.random.default_rng(1000 + si)
    out = []
    ov = None
    if s["overlay"]:
        name, of0 = s["overlay"]
        ov = overlay_frames(name, 1.0, s["f0"] + s["n"] - of0)
    for k in range(s["n"]):
        f = s["f0"] + k
        if only is not None and f not in only:
            continue
        u = k / max(1, s["n"] - 1)
        img = src.frame(k)
        h = src.h
        base = H / h
        z = s["z"][0] + (s["z"][1] - s["z"][0]) * eio(u)
        rot = s["rot"][0] + (s["rot"][1] - s["rot"][0]) * eio(u)
        cxp = (s["cx"] + (s["cx1"] - s["cx"]) * eio(u)) * src.w - src.x0
        dx = dy = 0.0
        # beat pulse inside the drop
        if T.DROP <= f < T.OUTRO and not (T.BREAK <= f < T.BACK):
            kb = f % T.BEAT
            z *= 1 + 0.035 * max(0, 1 - kb / 4) ** 2
        # transitions in
        tin, n_out = s["tin"], s["n"] - 1 - k
        zb = ca = wb = gl = fl = 0.0
        shake = 2.0                                   # constant subtle handheld
        if tin == "punch" and k < 6:
            z *= 1 + 0.12 * (1 - eo(k / 5)); ca = 0.007 * (1 - k / 6); shake += 14 * (1 - k / 6)
        elif tin == "drop":
            z *= 1 + 0.28 * (1 - eo(k / 9)); ca = 0.016 * max(0, 1 - k / 10)
            fl = max(0, 1 - k / 7) ** 1.5; shake += 34 * max(0, 1 - k / 18)
        elif tin in ("flash", "flash_s") and k < 5:
            fl = (0.85 if tin == "flash" else 0.45) * (1 - k / 5) ** 2
            z *= 1 + 0.06 * (1 - eo(k / 5))
        elif tin == "zoom" and k < 6:
            z *= 1 + 0.55 * (1 - eo(k / 5)); zb = 0.22 * (1 - k / 6)
        elif tin == "whip" and k < 5:
            p = eo(k / 4)
            dx += W * 0.7 * (1 - p); wb = 110 * (1 - p)
        elif tin == "glitch" and k < 6:
            gl = 0.8 * (1 - k / 6)
        # transitions out
        if s["tout"] == "zoom" and n_out < 4:
            q = 1 - n_out / 4
            z *= 1 + 0.6 * q ** 2; zb = max(zb, 0.25 * q)
        elif s["tout"] == "whip" and n_out < 3:
            q = 1 - n_out / 3
            dx -= W * 0.7 * q ** 2; wb = max(wb, 120 * q)
        elif s["tout"] == "whiteout" and n_out < 7:
            fl = max(fl, (1 - n_out / 7) ** 2)
        shake += 22 * s["shake"]
        # global accent hits
        if T.BACK <= f < T.BACK + 8:
            kk = f - T.BACK
            z *= 1 + 0.18 * (1 - eo(kk / 7)); ca = max(ca, 0.012 * (1 - kk / 8)); shake += 26 * (1 - kk / 8)
            fl = max(fl, 0.5 * (1 - kk / 4)) if kk < 4 else fl
        if 408 <= f < 414:
            kk = f - 408
            z *= 1 + 0.08 * (1 - eo(kk / 5)); shake += 16 * (1 - kk / 6); ca = max(ca, 0.008 * (1 - kk / 6))
        if T.BREAK <= f < T.BACK:                     # tape-stop break: unstable, dark, glitchy
            kk = f - T.BREAK
            gl = max(gl, 0.6 if kk in (0, 1, 5, 9, 10) else 0.0)
        sdx, sdy = smooth_noise(si, f / T.FPS, 1.0)
        jitter = rng.normal(0, 1, 2) * (shake - 2) * 0.35
        dx += sdx * shake + jitter[0]
        dy += sdy * shake + jitter[1]
        s_ = base * z
        cxp = clamp(cxp, W / (2 * s_), src.rw - W / (2 * s_)) if src.rw * s_ > W else src.rw / 2
        x = place(img, cxp, h / 2, s_, rot, dx, dy)
        x = grade(x, s["grade"])
        if T.BREAK <= f < T.BACK:
            lum = x @ np.array([0.2126, 0.7152, 0.0722], np.float32)
            x = (lum[..., None] * 0.7 + x * 0.3) * 0.85
        if ov is not None and f >= s["overlay"][1]:
            fr, ofps = ov
            o = fr[min(len(fr) - 1, int((f - s["overlay"][1]) / T.FPS * ofps))].astype(np.float32) / 255
            x = screen(x, o, 0.75 if f < T.OUTRO else 0.5)
        x = zoom_blur(x, zb)
        x = dir_blur(x, wb)
        x = chroma(x, ca)
        x = glitch(x, gl, rng)
        x = draw_text(x, f)
        if fl > 0:
            x = x + fl * (1.25 - x * 0.25)
        out.append((f, x))
    return out


def save(f, x, rng):
    y = finish(x, f, rng)
    cv2.imwrite(os.path.join(OUTDIR, f"{f:04d}.png"), cv2.cvtColor((y * 255 + 0.5).astype(np.uint8),
                                                                  cv2.COLOR_RGB2BGR), [cv2.IMWRITE_PNG_COMPRESSION, 1])


def job(arg):
    kind, idx, only = arg
    rng = np.random.default_rng(77 + (idx if kind == "shot" else 500 + idx[0]))
    if kind == "shot":
        s = T.SHOTS[idx]
        for f, x in render_shot(idx, s, only):
            save(f, x, rng)
        return f"shot {idx} ({s['clip']}) done"
    a, b = idx
    for f in range(a, b):
        if only is not None and f not in only:
            continue
        save(f, endcard(f, rng), rng)
    return f"endcard {a}-{b} done"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default=None)
    ap.add_argument("--procs", type=int, default=4)
    args = ap.parse_args()
    only = set(int(v) for v in args.only.split(",")) if args.only else None
    os.makedirs(OUTDIR, exist_ok=True)
    jobs = []
    for i, s in enumerate(T.SHOTS):
        if only is None or any(s["f0"] <= f < s["f0"] + s["n"] for f in only):
            jobs.append(("shot", i, only))
    for a in range(T.END, T.NF, 24):
        b = min(T.NF, a + 24)
        if only is None or any(a <= f < b for f in only):
            jobs.append(("end", (a, b), only))
    # longest shots first for better packing
    jobs.sort(key=lambda j: -(T.SHOTS[j[1]]["n"] if j[0] == "shot" else 24))
    with Pool(args.procs) as p:
        for msg in p.imap_unordered(job, jobs):
            print(msg, flush=True)


if __name__ == "__main__":
    main()
