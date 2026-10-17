"""Renders the Short: animated baby + overlays + soundtrack -> build/.

Run make_audio.py first; the mouth, eyes and pop-ups are driven by
audio/laugh.wav and audio/events.json.
"""
import json
import os
import subprocess
import sys

import cv2
import numpy as np
import scipy.io.wavfile as wavfile
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from face_rig import Rig, laugh_pose
from timeline import CTA, DURATION, FPS, H, HOOK_END, SR, W, WAIT_LEAD

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
A = lambda *p: os.path.join(ROOT, "assets", *p)
FONT = A("fonts", "LuckiestGuy-Regular.woff")
NF = int(DURATION * FPS)
rng = np.random.default_rng(11)

YELLOW = (255, 212, 0)
PINK = (255, 79, 163)
CYAN = (34, 211, 238)
ORANGE = (255, 138, 0)
LIME = (140, 240, 40)
YT_RED = (255, 0, 51)
HA_COLORS = [YELLOW, PINK, CYAN, ORANGE, LIME]

# Camera: source pixel C sits at screen point P, at zoom S0 * z.
S0 = 1.45
C_WIDE, P_WIDE = np.array([520.0, 512.0]), np.array([540.0, 1050.0])
C_FACE, P_FACE = np.array([522.0, 440.0]), np.array([540.0, 930.0])


def ease(x):
    x = np.clip(x, 0, 1)
    return x * x * (3 - 2 * x)


# ---------------------------------------------------------------- drivers

def drivers():
    sr, x = wavfile.read(os.path.join(ROOT, "audio/laugh.wav"))
    x = x.astype(np.float64) / 32768
    hop = sr // 1000
    win = int(0.015 * sr)
    env = np.sqrt(np.convolve(x ** 2, np.ones(win) / win, "same"))[::hop]   # 1 ms steps
    db = 20 * np.log10(env + 1e-9)
    raw = np.clip((db + 36) / 24, 0, 1)

    def follow(v, att_ms, rel_ms):
        out = np.empty_like(v)
        a, r = 1 - np.exp(-1 / att_ms), 1 - np.exp(-1 / rel_ms)
        y = 0.0
        for i, s in enumerate(v):
            y += (s - y) * (a if s > y else r)
            out[i] = y
        return out

    mouth = follow(raw, 22, 65)
    laugh = np.clip(follow(raw, 120, 650) * 1.6, 0, 1)
    lead = 25  # ms: the mouth opens a touch before the sound
    t = (np.arange(NF) / FPS * 1000).astype(int) + lead
    t = np.clip(t, 0, len(mouth) - 1)
    return mouth[t], laugh[t]


# ---------------------------------------------------------------- sprites

def font(size):
    return ImageFont.truetype(FONT, size)


def emoji(code, size):
    im = Image.open(A("emoji", code + ".webp")).convert("RGBA")
    return im.resize((size, size), Image.LANCZOS)


def text_sprite(parts, size, stroke=None, shadow=True, pad=40):
    """parts: list of (text, fill) or ("emoji", code). Returns an RGBA PIL image."""
    f = font(size)
    stroke = stroke if stroke is not None else max(6, size // 11)
    widths = []
    for p in parts:
        if p[0] == "emoji":
            widths.append(int(size * 1.05))
        else:
            b = f.getbbox(p[0], stroke_width=stroke)
            widths.append(b[2] - b[0])
    gap = int(size * 0.18)
    w = sum(widths) + gap * (len(parts) - 1) + 2 * pad
    h = int(size * 1.35) + 2 * pad
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    x = pad
    for p, pw in zip(parts, widths):
        if p[0] == "emoji":
            e = emoji(p[1], int(size * 1.05))
            im.alpha_composite(e, (x, pad + int(size * 0.05)))
        else:
            b = f.getbbox(p[0], stroke_width=stroke)
            d.text((x - b[0], pad + int(size * 0.12)), p[0], font=f, fill=p[1],
                   stroke_width=stroke, stroke_fill=(15, 10, 20))
        x += pw + gap
    if shadow:
        a = im.split()[3].filter(ImageFilter.GaussianBlur(size / 14))
        sh = Image.new("RGBA", im.size, (0, 0, 0, 0))
        sh.putalpha(a.point(lambda v: int(v * 0.55)))
        base = Image.new("RGBA", im.size, (0, 0, 0, 0))
        base.alpha_composite(sh, (0, int(size / 12)))
        base.alpha_composite(im)
        im = base
    return im


def pill_sprite(text, size, fill, color=(255, 255, 255)):
    f = font(size)
    b = f.getbbox(text)
    tw, th = b[2] - b[0], b[3] - b[1]
    w, h = tw + int(size * 1.4), th + int(size * 0.9)
    pad = 30
    im = Image.new("RGBA", (w + 2 * pad, h + 2 * pad), (0, 0, 0, 0))
    sh = Image.new("RGBA", im.size, (0, 0, 0, 0))
    ImageDraw.Draw(sh).rounded_rectangle((pad, pad + 10, pad + w, pad + h + 10), h // 2, fill=(0, 0, 0, 120))
    im.alpha_composite(sh.filter(ImageFilter.GaussianBlur(10)))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((pad, pad, pad + w, pad + h), h // 2, fill=fill, outline=(255, 255, 255), width=6)
    d.text((pad + (w - tw) // 2 - b[0], pad + (h - th) // 2 - b[1]), text, font=f, fill=color)
    return im


def to_np(im):
    a = np.asarray(im).astype(np.float32) / 255.0
    return np.ascontiguousarray(a[..., [2, 1, 0, 3]])  # BGRA, premultiplied below


def premul(a):
    a = a.copy()
    a[..., :3] *= a[..., 3:4]
    return a


class Sprite:
    def __init__(self, im):
        self.a = premul(to_np(im))
        self.h, self.w = self.a.shape[:2]


def blit(frame, sp, cx, cy, scale=1.0, angle=0.0, alpha=1.0):
    """Composite sprite (premultiplied BGRA float) centred at (cx, cy) onto float BGR frame."""
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
    M2 = M.copy()
    M2[0, 2] -= x0
    M2[1, 2] -= y0
    roi = cv2.warpAffine(sp.a, M2, (x1 - x0, y1 - y0), flags=cv2.INTER_LINEAR,
                         borderMode=cv2.BORDER_CONSTANT, borderValue=(0, 0, 0, 0)) * alpha
    dst = frame[y0:y1, x0:x1]
    dst *= 1 - roi[..., 3:4]
    dst += roi[..., :3]


# ---------------------------------------------------------------- scene

class Scene:
    def __init__(self):
        img = cv2.imread(A("baby.jpg"))
        self.rig = Rig(img)
        self.mouth, self.laugh = drivers()
        ev = json.load(open(os.path.join(ROOT, "audio/events.json")))
        self.onsets = ev["onsets"]
        # The big laugh lands on the first strong syllable of the "big" piece.
        self.big = next(t for t, h in self.onsets if t >= ev["big"] - 0.02)

        # Background: the still, blown up to cover the frame and heavily blurred.
        s = H / img.shape[0]
        bg = cv2.resize(img, None, fx=s, fy=s, interpolation=cv2.INTER_LINEAR)
        x0 = int(520 * s - W / 2)
        bg = bg[:, x0:x0 + W].astype(np.float32) / 255
        bg = cv2.GaussianBlur(bg, (0, 0), 28)
        self.bg = bg * 0.72 + 0.04

        # Feathered alpha for the foreground still (only top/bottom edges ever show).
        m = np.ones((1024, 1024), np.float32)
        ramp = np.linspace(0, 1, 70, dtype=np.float32)
        m[:70] *= ramp[:, None]
        m[-70:] *= ramp[::-1, None]
        self.fg_mask = m

        # Sprites.
        self.title = Sprite(text_sprite([("TRY NOT", (255, 255, 255))], 150))
        self.title2 = Sprite(text_sprite([("TO ", (255, 255, 255)), ("LAUGH", YELLOW), ("emoji", "1f602")], 150))
        self.wait = Sprite(text_sprite([("WAIT FOR IT", (255, 255, 255)), ("emoji", "1f440")], 112))
        self.big_ha = Sprite(text_sprite([("HAHAHAHA!", YELLOW)], 140))
        self.cta1 = Sprite(text_sprite([("DID YOU SMILE?", (255, 255, 255)), ("emoji", "1f60d")], 96))
        self.cta2 = Sprite(pill_sprite("SUBSCRIBE", 92, YT_RED))
        self.cta_hand = Sprite(emoji("1f447", 120))
        words = ["HA", "HAHA", "HA HA", "HAHAHA", "HEHE", "HAHA!"]
        self.ha = {(w_, c): Sprite(text_sprite([(w_, c)], 104)) for w_ in words for c in HA_COLORS}
        self.emo = {c: Sprite(emoji(c, 150)) for c in ["1f602", "1f923", "1f606", "1f60d", "2764-fe0f"]}

        self._plan_pops()
        self._plan_particles()

    # -- event plans (deterministic) --

    def _plan_pops(self):
        self.pops = []
        last, side, k = -1, 1, 0
        words = ["HA", "HAHA", "HA HA", "HAHAHA", "HEHE", "HAHA!"]
        for t, h in self.onsets:
            if h < -21 or t - last < 0.2 or abs(t - self.big) < 1.2 or t > DURATION - 0.6:
                continue
            last = t
            side = -side
            x = 540 + side * rng.uniform(250, 340)
            y = rng.uniform(560, 860)
            self.pops.append(dict(t=t, x=x, y=y, word=words[k % len(words)],
                                  color=HA_COLORS[k % len(HA_COLORS)],
                                  rot=-side * rng.uniform(6, 16)))
            k += 1

    def _plan_particles(self):
        self.parts = []
        codes = ["1f602", "1f923", "1f606"]
        # Steady stream rising from the bottom, denser while laughing hard.
        t = 0.15
        while t < DURATION:
            li = self.laugh[min(int(t * FPS), NF - 1)]
            # Side lanes only, so nothing drifts across the baby's face.
            x = rng.uniform(60, 220) if rng.random() < 0.5 else rng.uniform(860, 1020)
            self.parts.append(dict(t=t, life=2.2, code=codes[rng.integers(3)],
                                   x=x, y=H + 80, vx=rng.uniform(-25, 25),
                                   vy=-rng.uniform(520, 760), g=0, size=rng.uniform(0.55, 0.85),
                                   spin=rng.uniform(-60, 60), sway=rng.uniform(20, 50)))
            t += 1 / (0.8 + 1.8 * li)
        # Burst outwards from a ring around the face on the big laugh.
        for i in range(22):
            a = 2 * np.pi * i / 22 + rng.uniform(-0.12, 0.12)
            v = rng.uniform(900, 1500)
            self.parts.append(dict(t=self.big + rng.uniform(0, 0.08), life=1.4, code=codes[i % 3],
                                   x=540 + 500 * np.cos(a), y=930 + 680 * np.sin(a),
                                   vx=np.cos(a) * v, vy=np.sin(a) * v - 300, g=1500,
                                   size=rng.uniform(0.6, 1.1), spin=rng.uniform(-200, 200), sway=0))
        # Hearts for the CTA.
        for i in range(8):
            self.parts.append(dict(t=CTA[0] + i * 0.18, life=2.2, code=["2764-fe0f", "1f60d"][i % 2],
                                   x=[rng.uniform(60, 220), rng.uniform(860, 1020)][i % 2], y=H + 80, vx=rng.uniform(-30, 30),
                                   vy=-rng.uniform(500, 650), g=0, size=rng.uniform(0.6, 0.85),
                                   spin=rng.uniform(-40, 40), sway=30))

    # -- per-frame --

    def kick(self, t):
        """Foot kick envelope from the nearest past strong syllable."""
        best, side = 0.0, 1
        for i, (ot, h) in enumerate(self.onsets):
            if ot > t:
                break
            if h > -22:
                k = np.exp(-(t - ot) / 0.14) * min(1, (t - ot) / 0.04)
                if k > best:
                    best, side = k, 1 if i % 2 else -1
        return best, side

    def camera(self, t, m):
        tb = self.big
        intro = 0.14 * np.exp(-t * 5)
        drift = 0.05 * t / DURATION
        punch = 0.0
        for ot, h in self.onsets:
            if 0 <= t - ot < 0.3 and h > -18:
                punch = max(punch, 0.022 * np.exp(-(t - ot) / 0.09))
        f = ease((t - tb + 0.12) / 0.12) * (1 - ease((t - tb - 1.5) / 0.8))   # big laugh face punch
        wait = ease((t - (tb - WAIT_LEAD)) / WAIT_LEAD) * (1 - ease((t - tb + 0.12) / 0.1))
        z = 1 + intro + drift + punch + 0.42 * f + 0.06 * wait
        face = max(f, 0.6 * wait, 0.35 * np.exp(-t * 3))
        C = C_WIDE + (C_FACE - C_WIDE) * face
        P = P_WIDE + (P_FACE - P_WIDE) * face
        shake_amp = 4 * m + 26 * f * np.exp(-max(0, t - tb) / 0.7)
        sx = shake_amp * (np.sin(t * 71) + 0.5 * np.sin(t * 113))
        sy = shake_amp * (np.cos(t * 83) + 0.5 * np.sin(t * 97)) - 7 * m
        rot = 0.6 * np.sin(t * 1.3) + 1.6 * f * np.sin(t * 40) * np.exp(-max(0, t - tb) / 0.5)
        return z, C, P + [sx, sy], rot

    def frame(self, i):
        t = i / FPS
        m, L = float(self.mouth[i]), float(self.laugh[i])
        k, side = self.kick(t)
        still = self.rig.pose(**laugh_pose(m, L, t, kick=k, kick_side=side)).astype(np.float32) / 255

        z, C, P, rot = self.camera(t, m)
        s = S0 * z
        M = cv2.getRotationMatrix2D((float(C[0]), float(C[1])), rot, s)
        M[:, 2] += P - C
        fg = cv2.warpAffine(still, M, (W, H), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
        a = cv2.warpAffine(self.fg_mask, M, (W, H), flags=cv2.INTER_LINEAR, borderValue=0)[..., None]
        out = self.bg * (1 - a) + fg * a

        self.overlays(out, t, m, L)

        # Flash on the big laugh.
        fl = 0.55 * np.exp(-max(0, t - self.big) / 0.09) if t >= self.big else 0
        if fl > 0.01:
            out = out * (1 - fl) + fl
        return np.clip(out * 255, 0, 255).astype(np.uint8)

    def overlays(self, out, t, m, L):
        # Particles behind the text.
        for p in self.parts:
            dt = t - p["t"]
            if 0 <= dt < p["life"]:
                x = p["x"] + p["vx"] * dt + p["sway"] * np.sin(dt * 4 + p["x"])
                y = p["y"] + p["vy"] * dt + 0.5 * p["g"] * dt * dt
                a = min(1, dt / 0.12) * min(1, (p["life"] - dt) / 0.4)
                blit(out, self.emo[p["code"]], x, y, p["size"], p["spin"] * dt, a)

        # HA pop-ups.
        for p in self.pops:
            dt = t - p["t"]
            if 0 <= dt < 0.8:
                pop = 1.3 * ease(dt / 0.09) - 0.3 * ease((dt - 0.09) / 0.12)
                a = 1 - ease((dt - 0.5) / 0.3)
                blit(out, self.ha[(p["word"], p["color"])], p["x"], p["y"] - 140 * dt,
                     pop * (1 + 0.06 * m), p["rot"], a)

        # Big laugh word.
        dt = t - self.big
        if 0 <= dt < 1.5:
            sc = 1.2 * ease(dt / 0.1) - 0.2 * ease((dt - 0.1) / 0.15)
            j = 10 * np.exp(-dt / 0.6)
            blit(out, self.big_ha, 540 + j * np.sin(t * 90), 1420 + j * np.cos(t * 77),
                 sc * (1 + 0.05 * np.sin(t * 25)), 4 * np.sin(t * 9), 1 - ease((dt - 1.2) / 0.3))

        # Wait for it.
        tw = self.big - WAIT_LEAD
        dt = t - tw
        if 0 <= dt < WAIT_LEAD:
            sc = ease(dt / 0.15) * (1 + 0.05 * np.sin(dt * 12))
            blit(out, self.wait, 540, 1450, sc, 0, 1 - ease((dt - WAIT_LEAD + 0.12) / 0.1))

        # Hook title: big from frame 0, then shrinks to a badge.
        sh = ease((t - HOOK_END) / 0.35)
        wob = 1 + 0.07 * np.exp(-t * 3) * np.sin(t * 22) + 0.03 * m * (1 - sh)
        sc = (1 - sh) * 1.0 + sh * 0.5
        y1 = (1 - sh) * 205 + sh * 95
        y2 = (1 - sh) * 375 + sh * 180
        x1 = (1 - sh) * 540 + sh * 540
        if sh < 1:
            blit(out, self.title, x1, y1, sc * wob, -3 * (1 - sh))
            blit(out, self.title2, x1, y2, sc * wob, 3 * (1 - sh))
        else:
            # Badge: single line, gentle pulse with the laugh.
            blit(out, self.title, 540 - 218, 120, 0.5 * (1 + 0.04 * m), -2)
            blit(out, self.title2, 540 + 175, 120, 0.5 * (1 + 0.04 * m), 2)

        # Call to action.
        dt = t - CTA[0]
        if dt >= 0:
            p1 = 1.2 * ease(dt / 0.12) - 0.2 * ease((dt - 0.12) / 0.12)
            blit(out, self.cta1, 540, 1440, p1, -2)
            dt2 = dt - 0.35
            if dt2 >= 0:
                p2 = 1.2 * ease(dt2 / 0.12) - 0.2 * ease((dt2 - 0.12) / 0.12)
                beat = 1 + 0.06 * max(0, np.sin(dt2 * 2 * np.pi * 2)) ** 4
                blit(out, self.cta2, 540, 1600, p2 * beat, 0)
                blit(out, self.cta_hand, 845, 1530 + 18 * np.sin(dt2 * 9), p2, -20)


def mux():
    """Gain the mix to -14 LUFS (YouTube's reference), stereo AAC, onto the picture."""
    picture = os.path.join(ROOT, "build/picture.mp4")
    mix = os.path.join(ROOT, "audio/mix.wav")
    up = "pan=stereo|c0=c0|c1=c0"
    probe = subprocess.run(["ffmpeg", "-hide_banner", "-i", mix, "-af", f"{up},ebur128=peak=true",
                            "-f", "null", "-"], capture_output=True, text=True).stderr
    summary = probe[probe.rindex("Summary:"):]
    lufs = float(summary.split("I:")[1].split()[0])
    peak = float(summary.split("Peak:")[1].split()[0])
    # Laugh peaks are spiky, so lift to target and let a limiter hold them under -2 dBFS.
    gain = -14 - lufs + 0.3
    final = os.path.join(ROOT, "build/baby_laughs_short.mp4")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", picture, "-i", mix,
                    "-af", f"{up},volume={gain:.2f}dB,alimiter=limit=0.79:attack=3:release=60:level=disabled", "-ar", "48000", "-c:v", "copy", "-c:a", "aac",
                    "-b:a", "192k", "-shortest", "-movflags", "+faststart", final], check=True)
    print(f"wrote {final} (mix {lufs:.1f} LUFS / {peak:.1f} dBFS, gain {gain:+.1f} dB)")


def main():
    if sys.argv[1:] == ["--mux"]:
        return mux()
    only = [int(a) for a in sys.argv[1:]]
    sc = Scene()
    os.makedirs(os.path.join(ROOT, "build"), exist_ok=True)
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
        if i % 60 == 0:
            print(f"frame {i}/{NF}", flush=True)
    ff.stdin.close()
    ff.wait()

    mux()
    cover = os.path.join(ROOT, "build/cover.jpg")
    cv2.imwrite(cover, sc.frame(int((sc.big + 0.25) * FPS)), [cv2.IMWRITE_JPEG_QUALITY, 92])


if __name__ == "__main__":
    main()
