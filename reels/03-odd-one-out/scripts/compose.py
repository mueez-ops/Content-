"""Renders "Find the Odd One Out" -> build/odd_one_out_short.mp4.

Run make_audio.py first. `python compose.py 0 300` renders just those frames
to build/ for checking; `python compose.py --mux` re-muxes audio only.
"""
import json
import os
import subprocess
import sys

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from timeline import COLS, DURATION, END_START, ENTER, EXIT, FPS, H, ROWS, SCHEDULE, W

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
A = lambda *p: os.path.join(ROOT, "assets", *p)
FONT = A("fonts", "LuckiestGuy-Regular.woff")
NF = int(round(DURATION * FPS))
rng = np.random.default_rng(5)

INK = (20, 14, 40)
WHITE = (255, 255, 255)
YELLOW = (255, 212, 0)
YT_RED = (255, 0, 51)
BG_TOP, BG_BOTTOM = (79, 172, 254), (106, 61, 232)   # RGB
CONFETTI = [(255, 212, 0), (255, 79, 163), (34, 211, 238), (46, 204, 113), (255, 138, 0), (255, 255, 255)]

# Grid geometry (screen px). The grid stays clear of the Shorts UI: the right
# column of buttons and the caption area along the bottom.
CELL = 130
EMOJI = 108
GRID_X0 = W // 2 - COLS * CELL // 2
GRID_Y0 = 360
PAD = 26
TITLE_Y, PILL_Y = 165, 272
BAR_Y, NUM_Y = 1478, 1572


def ease(x):
    x = np.clip(x, 0, 1)
    return x * x * (3 - 2 * x)


def back(x, over=0.18):
    """0 -> 1 with an overshoot bump, for pops."""
    x = np.clip(x, 0, 1)
    return (1 + over) * ease(x / 0.65) - over * ease((x - 0.65) / 0.35)


def cell_xy(c, r):
    return GRID_X0 + CELL * c + CELL / 2, GRID_Y0 + CELL * r + CELL / 2


# ---------------------------------------------------------------- sprites

def font(size):
    return ImageFont.truetype(FONT, size)


def emoji(code, size, flip=False):
    im = Image.open(A("emoji", code + ".webp")).convert("RGBA").resize((size, size), Image.LANCZOS)
    return im.transpose(Image.FLIP_LEFT_RIGHT) if flip else im


def text_sprite(parts, size, stroke=None, pad=36):
    f = font(size)
    stroke = stroke if stroke is not None else max(5, size // 11)
    widths = []
    for p in parts:
        if p[0] == "emoji":
            widths.append(int(size * 1.1))
        else:
            b = f.getbbox(p[0], stroke_width=stroke)
            widths.append(b[2] - b[0])
    gap = int(size * 0.16)
    w = sum(widths) + gap * (len(parts) - 1) + 2 * pad
    h = int(size * 1.35) + 2 * pad
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    x = pad
    for p, pw in zip(parts, widths):
        if p[0] == "emoji":
            im.alpha_composite(emoji(p[1], int(size * 1.1)), (x, pad))
        else:
            b = f.getbbox(p[0], stroke_width=stroke)
            d.text((x - b[0], pad + int(size * 0.12)), p[0], font=f, fill=p[1],
                   stroke_width=stroke, stroke_fill=INK)
        x += pw + gap
    a = im.split()[3].filter(ImageFilter.GaussianBlur(size / 14))
    sh = Image.new("RGBA", im.size, (0, 0, 0, 0))
    sh.putalpha(a.point(lambda v: int(v * 0.5)))
    base = Image.new("RGBA", im.size, (0, 0, 0, 0))
    base.alpha_composite(sh, (0, int(size / 12)))
    base.alpha_composite(im)
    return base


def pill_sprite(text, size, fill, color=WHITE, outline=WHITE):
    f = font(size)
    b = f.getbbox(text)
    tw, th = b[2] - b[0], b[3] - b[1]
    w, h = tw + int(size * 1.3), th + int(size * 0.85)
    pad = 30
    im = Image.new("RGBA", (w + 2 * pad, h + 2 * pad), (0, 0, 0, 0))
    sh = Image.new("RGBA", im.size, (0, 0, 0, 0))
    ImageDraw.Draw(sh).rounded_rectangle((pad, pad + 10, pad + w, pad + h + 10), h // 2, fill=(0, 0, 0, 110))
    im.alpha_composite(sh.filter(ImageFilter.GaussianBlur(10)))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((pad, pad, pad + w, pad + h), h // 2, fill=fill, outline=outline, width=6)
    d.text((pad + (w - tw) // 2 - b[0], pad + (h - th) // 2 - b[1]), text, font=f, fill=color)
    return im


def circle_sprite(r, fill, text=None, size=None):
    pad = 24
    im = Image.new("RGBA", (2 * (r + pad),) * 2, (0, 0, 0, 0))
    sh = Image.new("RGBA", im.size, (0, 0, 0, 0))
    ImageDraw.Draw(sh).ellipse((pad, pad + 8, pad + 2 * r, pad + 2 * r + 8), fill=(0, 0, 0, 110))
    im.alpha_composite(sh.filter(ImageFilter.GaussianBlur(8)))
    d = ImageDraw.Draw(im)
    d.ellipse((pad, pad, pad + 2 * r, pad + 2 * r), fill=fill, outline=WHITE, width=7)
    if text:
        f = font(size)
        b = f.getbbox(text)
        d.text((pad + r - (b[0] + b[2]) / 2, pad + r - (b[1] + b[3]) / 2), text, font=f, fill=WHITE,
               stroke_width=4, stroke_fill=INK)
    return im


def card_sprite():
    w, h = COLS * CELL + 2 * PAD, ROWS * CELL + 2 * PAD
    pad = 40
    im = Image.new("RGBA", (w + 2 * pad, h + 2 * pad), (0, 0, 0, 0))
    sh = Image.new("RGBA", im.size, (0, 0, 0, 0))
    ImageDraw.Draw(sh).rounded_rectangle((pad, pad + 16, pad + w, pad + h + 16), 46, fill=(20, 0, 60, 120))
    im.alpha_composite(sh.filter(ImageFilter.GaussianBlur(18)))
    ImageDraw.Draw(im).rounded_rectangle((pad, pad, pad + w, pad + h), 46, fill=(255, 255, 255, 245))
    return im


def soft_dot(r):
    s = 2 * r
    y, x = np.mgrid[0:s, 0:s]
    a = np.clip(1 - np.hypot(x - r, y - r) / r, 0, 1) ** 1.5
    im = np.zeros((s, s, 4), np.uint8)
    im[..., :3] = 255
    im[..., 3] = (a * 255).astype(np.uint8)
    return Image.fromarray(im, "RGBA")


class Sprite:
    def __init__(self, im):
        a = np.asarray(im).astype(np.float32) / 255.0
        a = np.ascontiguousarray(a[..., [2, 1, 0, 3]])
        a[..., :3] *= a[..., 3:4]
        self.a = a
        self.h, self.w = a.shape[:2]


def blit(frame, sp, cx, cy, scale=1.0, angle=0.0, alpha=1.0):
    if alpha <= 0.003 or scale <= 0.01:
        return
    M = cv2.getRotationMatrix2D((sp.w / 2, sp.h / 2), angle, scale)
    M[0, 2] += cx - sp.w / 2
    M[1, 2] += cy - sp.h / 2
    corners = np.array([[0, 0, 1], [sp.w, 0, 1], [0, sp.h, 1], [sp.w, sp.h, 1]], np.float64) @ M.T
    x0, y0 = np.floor(corners.min(0)).astype(int)
    x1, y1 = np.ceil(corners.max(0)).astype(int)
    x0, y0, x1, y1 = max(x0, 0), max(y0, 0), min(x1, W), min(y1, H)
    if x1 <= x0 or y1 <= y0:
        return
    M[0, 2] -= x0
    M[1, 2] -= y0
    roi = cv2.warpAffine(sp.a, M, (x1 - x0, y1 - y0), flags=cv2.INTER_LINEAR,
                         borderMode=cv2.BORDER_CONSTANT, borderValue=(0, 0, 0, 0)) * alpha
    dst = frame[y0:y1, x0:x1]
    dst *= 1 - roi[..., 3:4]
    dst += roi[..., :3]


def bgr(rgb):
    return (rgb[2] / 255, rgb[1] / 255, rgb[0] / 255)


# ---------------------------------------------------------------- scene

class Scene:
    def __init__(self):
        g = np.linspace(0, 1, H, dtype=np.float32)[:, None, None]
        top, bot = np.array(bgr(BG_TOP), np.float32), np.array(bgr(BG_BOTTOM), np.float32)
        self.bg = np.broadcast_to(top * (1 - g) + bot * g, (H, W, 3)).copy()
        self.dot = Sprite(soft_dot(90))
        self.dots = [dict(x=rng.uniform(0, W), y=rng.uniform(0, H), s=rng.uniform(0.6, 1.8),
                          v=rng.uniform(15, 45), a=rng.uniform(0.06, 0.14)) for _ in range(16)]

        self.card = Sprite(card_sprite())
        self.title = Sprite(text_sprite([("FIND THE ODD ONE OUT", WHITE), ("emoji", "1f440")], 70))
        self.pills = [Sprite(pill_sprite(f"LEVEL {lv['index'] + 1}/3 · {lv['name']}", 50, lv["color"]))
                      for lv in SCHEDULE]
        self.cells = []
        for lv in SCHEDULE:
            base = Sprite(emoji(lv["base"], EMOJI))
            odd = Sprite(emoji(lv["odd"], EMOJI) if lv["odd"] else emoji(lv["base"], EMOJI, flip=True))
            self.cells.append((base, odd))
        self.nums = {}
        for n in range(1, 10):
            for warn in (False, True):
                self.nums[(n, warn)] = Sprite(circle_sprite(62, (255, 59, 48) if warn else (46, 160, 255),
                                                           str(n), 84))
        self.found = Sprite(text_sprite([("FOUND IT?", WHITE), ("emoji", "2705")], 92))
        self.wow = Sprite(text_sprite([("WOW!", YELLOW), ("emoji", "1f525"), ("DID YOU GET IT?", WHITE)], 70))
        self.end1 = Sprite(text_sprite([("HOW MANY", WHITE)], 120))
        self.end2 = Sprite(text_sprite([("DID YOU ", WHITE), ("FIND?", YELLOW)], 120))
        self.end_bubbles = [Sprite(circle_sprite(95, lv["color"], str(i + 1), 130)) for i, lv in enumerate(SCHEDULE)]
        self.end3 = Sprite(text_sprite([("COMMENT BELOW", WHITE), ("emoji", "1f447")], 80))
        self.sub = Sprite(pill_sprite("SUBSCRIBE", 80, YT_RED))
        self._plan_confetti()

    def _plan_confetti(self):
        self.confetti = []
        for lv in SCHEDULE:
            cx, cy = cell_xy(*lv["cell"])
            n = 46 if lv["index"] < 2 else 90
            for _ in range(n):
                a = rng.uniform(0, 2 * np.pi)
                v = rng.uniform(400, 1300) * (1.3 if lv["index"] == 2 else 1)
                self.confetti.append(dict(t=lv["reveal"] + rng.uniform(0, 0.05), x=cx, y=cy,
                                          vx=np.cos(a) * v, vy=np.sin(a) * v - 500, g=1800, life=1.6,
                                          rot=rng.uniform(0, 360), vrot=rng.uniform(-720, 720),
                                          w=rng.uniform(10, 18), h=rng.uniform(18, 30),
                                          color=CONFETTI[rng.integers(len(CONFETTI))]))
        # Gentle rain over the end card.
        for _ in range(60):
            self.confetti.append(dict(t=END_START + rng.uniform(0, 2.5), x=rng.uniform(0, W), y=-40,
                                      vx=rng.uniform(-60, 60), vy=rng.uniform(250, 450), g=0, life=4.5,
                                      rot=rng.uniform(0, 360), vrot=rng.uniform(-360, 360),
                                      w=rng.uniform(10, 16), h=rng.uniform(16, 26),
                                      color=CONFETTI[rng.integers(len(CONFETTI))]))

    def draw_confetti(self, out, t):
        for p in self.confetti:
            dt = t - p["t"]
            if not 0 <= dt < p["life"]:
                continue
            x = p["x"] + p["vx"] * dt
            y = p["y"] + p["vy"] * dt + 0.5 * p["g"] * dt * dt
            if not (-50 < x < W + 50 and -50 < y < H + 50):
                continue
            a = np.radians(p["rot"] + p["vrot"] * dt)
            flip = abs(np.cos(dt * 9 + p["rot"]))   # tumbling: width flickers
            hw, hh = p["w"] / 2 * (0.3 + 0.7 * flip), p["h"] / 2
            c, s = np.cos(a), np.sin(a)
            pts = np.array([[-hw, -hh], [hw, -hh], [hw, hh], [-hw, hh]]) @ [[c, s], [-s, c]] + [x, y]
            cv2.fillPoly(out, [np.round(pts * 16).astype(np.int32)], bgr(p["color"]), cv2.LINE_AA, shift=4)

    def background(self, t):
        out = self.bg.copy()
        for d in self.dots:
            y = (d["y"] - d["v"] * t) % (H + 200) - 100
            x = d["x"] + 30 * np.sin(t * 0.5 + d["y"])
            blit(out, self.dot, x, y, d["s"], 0, d["a"])
        return out

    def level_at(self, t):
        for lv in SCHEDULE:
            if lv["enter"] <= t < lv["exit"] + EXIT:
                return lv
        return None

    def grid(self, out, lv, t):
        base, odd = self.cells[lv["index"]]
        oc, orow = lv["cell"]
        rev = t - lv["reveal"]
        dim = ease(rev / 0.2) if rev >= 0 else 0
        for r in range(ROWS):
            for c in range(COLS):
                wave = (r + c) / (ROWS + COLS - 2)
                if lv["index"] and t < lv["start"]:
                    s = back((t - lv["enter"] - wave * (ENTER - 0.2)) / 0.2)
                else:
                    s = 1.0
                if t >= lv["exit"]:
                    s *= 1 - ease((t - lv["exit"] - wave * (EXIT - 0.15)) / 0.15)
                if s <= 0.01:
                    continue
                x, y = cell_xy(c, r)
                is_odd = (c, r) == (oc, orow)
                if is_odd:
                    continue
                # A gentle idle bob keeps the grid alive without giving anything away.
                bob = 1 + 0.025 * np.sin(t * 5 + c * 0.9 + r * 1.3)
                blit(out, base, x, y, s * bob * (1 - 0.12 * dim), 0, 1 - 0.75 * dim)
        x, y = cell_xy(oc, orow)
        s = 1.0
        if lv["index"] and t < lv["start"]:
            s = back((t - lv["enter"] - (oc + orow) / (ROWS + COLS - 2) * (ENTER - 0.2)) / 0.2)
        if t >= lv["exit"]:
            s *= 1 - ease((t - lv["exit"]) / 0.18)
        bob = 1 + 0.025 * np.sin(t * 5 + oc * 0.9 + orow * 1.3)
        pop = 1 + 0.55 * back(rev / 0.3, 0.3) if rev >= 0 else 1
        if rev >= 0:
            # Red ring drawn around the answer, plus an expanding pulse.
            k = ease(rev / 0.3)
            rr = int(66 * pop * s)
            if rr > 2:
                fade = 1 - ease((t - lv["exit"]) / 0.15) if t >= lv["exit"] else 1
                cv2.ellipse(out, (int(x), int(y)), (rr, rr), -90, 0, 360 * k, (0.2, 0.2, 1.0), 12, cv2.LINE_AA)
                ring = rev % 0.8 / 0.8
                if rev > 0.3 and fade > 0:
                    rp = int(rr * (1 + 0.6 * ring))
                    ov = out.copy()
                    cv2.circle(ov, (int(x), int(y)), rp, (0.3, 0.85, 1.0), 6, cv2.LINE_AA)
                    a = (1 - ring) * 0.8 * fade
                    out[:] = out * (1 - a) + ov * a
        blit(out, odd, x, y, s * bob * pop, 8 * np.sin(rev * 14) * np.exp(-rev * 3) if rev >= 0 else 0, 1)

    def timer(self, out, lv, t):
        if t >= lv["reveal"]:
            return
        n = lv["seconds"]
        rem = np.clip(lv["start"] + n - t, 0, n)
        frac = rem / n
        appear = back((t - lv["enter"]) / 0.3) if lv["index"] else 1
        # Bar.
        x0, x1 = 190, 890
        track = out.copy()
        cv2.rectangle(track, (x0, BAR_Y - 15), (x1, BAR_Y + 15), (0.25, 0.1, 0.15), -1, cv2.LINE_AA)
        a = 0.45 * appear
        out[:] = out * (1 - a) + track * a
        col = np.array(bgr((46, 204, 113))) if frac > 0.5 else (
            np.array(bgr((255, 200, 0))) if frac > 0.25 else np.array(bgr((255, 59, 48))))
        xe = int(x0 + (x1 - x0) * frac * appear)
        if xe > x0 + 30:
            cv2.rectangle(out, (x0 + 15, BAR_Y - 15), (xe - 15, BAR_Y + 15), tuple(col), -1, cv2.LINE_AA)
            cv2.circle(out, (x0 + 15, BAR_Y), 15, tuple(col), -1, cv2.LINE_AA)
            cv2.circle(out, (xe - 15, BAR_Y), 15, tuple(col), -1, cv2.LINE_AA)
        # Number with a kick on every second.
        num = max(1, int(np.ceil(rem - 1e-6)))
        since = (n - rem) % 1.0 if t >= lv["start"] else 1.0
        warn = num <= 2 and t >= lv["start"]
        kick = 1 + (0.32 if warn else 0.2) * np.exp(-since * 9)
        shake = 6 * np.sin(t * 60) * np.exp(-since * 6) if warn else 0
        blit(out, self.nums[(num, warn)], 540 + shake, NUM_Y, kick * appear)

    def reveal_banner(self, out, lv, t):
        rev = t - lv["reveal"]
        if rev < 0.15 or t >= lv["exit"] + EXIT:
            return
        sp = self.wow if lv["index"] == len(SCHEDULE) - 1 else self.found
        s = back((rev - 0.15) / 0.22, 0.25)
        if t >= lv["exit"]:
            s *= 1 - ease((t - lv["exit"]) / 0.2)
        blit(out, sp, 540, NUM_Y - 40, s * (1 + 0.03 * np.sin(rev * 8)), -3 + 2 * np.sin(rev * 5))

    def end_card(self, out, t):
        dt = t - END_START
        if dt < 0:
            return
        blit(out, self.end1, 540, 560, back((dt - 0.05) / 0.3), -3)
        blit(out, self.end2, 540, 715, back((dt - 0.2) / 0.3), 2)
        for i, sp in enumerate(self.end_bubbles):
            s = back((dt - 0.45 - 0.12 * i) / 0.3, 0.3)
            bob = 14 * np.sin(dt * 5 + i * 1.6)
            blit(out, sp, 290 + 250 * i, 1000 + bob, s)
        blit(out, self.end3, 540, 1230, back((dt - 0.9) / 0.3), 0)
        beat = 1 + 0.05 * max(0, np.sin(dt * 2 * np.pi * 2)) ** 4
        blit(out, self.sub, 540, 1410, back((dt - 1.15) / 0.3) * beat, 0)

    def frame(self, i):
        t = i / FPS
        out = self.background(t)
        lv = self.level_at(t)
        if lv is not None or t < END_START:
            # The card leaves with the last level.
            k = 1 - ease((t - END_START + 0.25) / 0.25) if t > END_START - 0.25 else 1
            cy = GRID_Y0 + ROWS * CELL / 2
            blit(out, self.card, 540, cy, 0.9 + 0.1 * k, 0, k)
        if lv is not None:
            self.grid(out, lv, t)
            self.timer(out, lv, t)
        # Title on top, level pill pops with each level.
        blit(out, self.title, 540, TITLE_Y, 1 + 0.02 * np.sin(t * 3))
        if lv is not None and t < END_START:
            s = back((t - lv["enter"]) / 0.3, 0.3) if lv["index"] else 1
            if t >= lv["exit"]:
                s *= 1 - ease((t - lv["exit"]) / 0.2)
            blit(out, self.pills[lv["index"]], 540, PILL_Y, s)
        if lv is not None:
            self.reveal_banner(out, lv, t)
        self.end_card(out, t)
        self.draw_confetti(out, t)
        return np.clip(out * 255, 0, 255).astype(np.uint8)


def mux():
    """Lift the mix to -14 LUFS (YouTube's reference) under a limiter, stereo AAC, onto the picture."""
    picture = os.path.join(ROOT, "build/picture.mp4")
    mix = os.path.join(ROOT, "audio/mix.wav")
    up = "pan=stereo|c0=c0|c1=c0"
    probe = subprocess.run(["ffmpeg", "-hide_banner", "-i", mix, "-af", f"{up},ebur128", "-f", "null", "-"],
                           capture_output=True, text=True).stderr
    lufs = float(probe[probe.rindex("Summary:"):].split("I:")[1].split()[0])
    gain = -14 - lufs + 0.3
    final = os.path.join(ROOT, "build/odd_one_out_short.mp4")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", picture, "-i", mix,
                    "-af", f"{up},volume={gain:.2f}dB,alimiter=limit=0.79:attack=3:release=60:level=disabled",
                    "-ar", "48000", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest",
                    "-movflags", "+faststart", final], check=True)
    print(f"wrote {final} (mix {lufs:.1f} LUFS, gain {gain:+.1f} dB)")


def main():
    if sys.argv[1:] == ["--mux"]:
        return mux()
    sc = Scene()
    os.makedirs(os.path.join(ROOT, "build"), exist_ok=True)
    only = [int(a) for a in sys.argv[1:]]
    if only:
        for i in only:
            cv2.imwrite(os.path.join(ROOT, f"build/frame_{i:04d}.jpg"), sc.frame(i), [cv2.IMWRITE_JPEG_QUALITY, 92])
        return
    picture = os.path.join(ROOT, "build/picture.mp4")
    ff = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "bgr24",
                           "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-preset", "slow",
                           "-crf", "16", "-pix_fmt", "yuv420p", picture], stdin=subprocess.PIPE)
    for i in range(NF):
        ff.stdin.write(sc.frame(i).tobytes())
        if i % 120 == 0:
            print(f"frame {i}/{NF}", flush=True)
    ff.stdin.close()
    ff.wait()
    mux()
    # Thumbnail: level 1 mid-countdown (the puzzle itself is the best cover).
    cv2.imwrite(os.path.join(ROOT, "build/cover.jpg"), sc.frame(int(1.0 * FPS)), [cv2.IMWRITE_JPEG_QUALITY, 92])


if __name__ == "__main__":
    main()
