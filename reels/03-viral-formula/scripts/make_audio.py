"""Reel 03 soundtrack: original 100 BPM music bed + sound design, mixed under
the Kokoro voiceover with ducking. Everything is synthesised here (no samples).

Writes audio/music.wav, audio/sfx.wav, audio/vo.wav, audio/mix.wav and
audio/mix_no_music.wav (VO + SFX) at 48 kHz stereo.
"""
import json
import os
import sys

import numpy as np
import soundfile as sf
from scipy.signal import butter, sosfilt, fftconvolve, resample_poly

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import timeline as T  # noqa: E402

SR = 48000
ROOT = T.ROOT
DUR = T.NF / T.FPS + 1.0
N = int(DUR * SR)
SPB = 60 / T.BPM
rng = np.random.default_rng(3)


def fr(f):
    return int(round(f / T.FPS * SR))


def bt(b):
    return int(round(b * SPB * SR))


def lp(x, f, o=2):
    return sosfilt(butter(o, f, "low", fs=SR, output="sos"), x)


def hp(x, f, o=2):
    return sosfilt(butter(o, f, "high", fs=SR, output="sos"), x)


def bp(x, lo, hi, o=2):
    return sosfilt(butter(o, [lo, min(hi, SR / 2 - 200)], "band", fs=SR, output="sos"), x)


def add(buf, x, at, g=1.0):
    if at < 0:
        x, at = x[-at:], 0
    e = min(len(buf), at + len(x))
    if e > at:
        buf[at:e] += x[: e - at] * g


def mtof(m):
    return 440 * 2 ** ((m - 69) / 12)


def reverb(x, secs=2.0, wet=0.3, damp=5000, seed=1):
    r = np.random.default_rng(seed)
    n = int(secs * SR)
    t = np.arange(n) / SR
    ir = lp(r.standard_normal(n) * np.exp(-t * 6.9 / secs), damp)
    ir /= np.sqrt(np.sum(ir ** 2))
    return x + fftconvolve(x, ir)[: len(x)] * wet


# ------------------------------------------------------------------ instruments
def piano(m, length=2.6, vel=0.6):
    f0 = mtof(m)
    n = int(length * SR)
    t = np.arange(n) / SR
    x = np.zeros(n)
    B = 0.00035
    for k in range(1, 12):
        fk = k * f0 * np.sqrt(1 + B * k * k)
        if fk > 12000:
            break
        amp = (1 / k ** 1.25) * (1.0 if k > 1 else 1.2)
        dec = 0.9 / (1 + 0.35 * k) * (1.4 if f0 < 200 else 1.0)
        x += amp * np.sin(2 * np.pi * fk * t + rng.uniform(0, 6.28)) * (0.65 * np.exp(-t / (dec * 0.25)) + 0.35 * np.exp(-t / (dec * 2.2)))
    att = int(0.004 * SR)
    x[:att] *= np.linspace(0, 1, att)
    ham = bp(rng.standard_normal(int(0.02 * SR)), 1500, 6000) * np.exp(-np.arange(int(0.02 * SR)) / SR / 0.004) * 0.15
    x[: len(ham)] += ham
    rel = int(0.25 * SR)
    x[-rel:] *= np.linspace(1, 0, rel)
    return lp(x, 2500 + 4000 * vel) * vel * 0.35


def pluck(m, length=0.5, g=0.3):
    f = mtof(m)
    n = int(length * SR)
    t = np.arange(n) / SR
    saw = 2 * ((t * f) % 1) - 1 + 0.5 * (2 * ((t * f * 1.004) % 1) - 1)
    env = np.exp(-t / 0.12)
    out = np.zeros(n)
    # decaying low-pass sweep, in chunks
    for i, (a, b) in enumerate(zip(range(0, n, 2400), range(2400, n + 2400, 2400))):
        c = 600 + 5000 * np.exp(-a / SR / 0.08)
        seg = saw[max(0, a - 1200):b]
        out[a:b] = lp(seg, c)[-(min(b, n) - a):]
    return out * env * g


def kick(g=1.0):
    n = int(0.4 * SR)
    t = np.arange(n) / SR
    f = 46 + 110 * np.exp(-t * 32)
    x = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t / 0.22)
    x[:200] += hp(rng.standard_normal(200), 3000) * 0.3
    return np.tanh(x * 1.5) * g


def clap(g=1.0):
    n = int(0.3 * SR)
    t = np.arange(n) / SR
    x = bp(rng.standard_normal(n), 900, 6000) * np.exp(-t / 0.07)
    for d in (0.007, 0.015):
        k = int(d * SR)
        x[k:] += bp(rng.standard_normal(n - k), 900, 6000) * np.exp(-t[: n - k] / 0.012) * 0.6
    return reverb(x, 0.8, 0.25) * g * 0.6


def hat(g=0.2, open_=False):
    n = int((0.18 if open_ else 0.045) * SR)
    t = np.arange(n) / SR
    return hp(rng.standard_normal(n), 8000, 4) * np.exp(-t / (0.06 if open_ else 0.012)) * g


def shaker(g=0.12):
    n = int(0.07 * SR)
    t = np.arange(n) / SR
    return bp(rng.standard_normal(n), 4000, 11000) * np.sin(np.pi * t / t[-1]) ** 2 * g


def sub(m, length, g=0.5):
    f = mtof(m)
    n = int(length * SR)
    t = np.arange(n) / SR
    x = np.sin(2 * np.pi * f * t) + 0.25 * np.sin(4 * np.pi * f * t)
    e = np.minimum(1, t / 0.01) * np.minimum(1, (length - t) / 0.05).clip(0, 1)
    return np.tanh(x * 1.3) * e * g


# ------------------------------------------------------------------ SFX
def sweep_bp(x, f0, f1, q=1.4, chunks=48):
    out = np.zeros_like(x)
    L = len(x)
    edges = np.linspace(0, L, chunks + 1).astype(int)
    for i in range(chunks):
        a, b = edges[i], edges[i + 1]
        c = f0 * (f1 / f0) ** (i / (chunks - 1))
        seg = x[max(0, a - 2048): b]
        out[a:b] = bp(seg, c / (1 + 1 / q), c * (1 + 1 / q))[-(b - a):]
    return out


def sfx(kind):
    if kind == "whoosh":
        n = int(0.45 * SR)
        t = np.arange(n) / SR
        return sweep_bp(rng.standard_normal(n), 300, 6000) * np.sin(np.pi * t / t[-1]) ** 2 * 1.4
    if kind == "whoosh_up":
        n = int(0.4 * SR)
        t = np.arange(n) / SR
        return sweep_bp(rng.standard_normal(n), 250, 9000) * (t / t[-1]) ** 2 * 1.6
    if kind == "swirl":
        n = int(0.6 * SR)
        t = np.arange(n) / SR
        x = sweep_bp(rng.standard_normal(n), 2000, 400) * np.sin(np.pi * t / t[-1]) ** 1.5
        return x * (0.6 + 0.4 * np.sin(2 * np.pi * 14 * t)) * 1.5
    if kind in ("impact", "impact_big"):
        big = kind == "impact_big"
        n = int((1.8 if big else 0.9) * SR)
        t = np.arange(n) / SR
        boom = np.sin(2 * np.pi * np.cumsum(40 + 70 * np.exp(-t * 16)) / SR) * np.exp(-t / (0.7 if big else 0.3))
        crack = lp(rng.standard_normal(n), 4000) * np.exp(-t / 0.04)
        return reverb(np.tanh((boom * 1.6 + crack * 0.6) * 1.3), 2.0, 0.3, 3000) * (0.9 if big else 0.6)
    if kind == "shutter":
        n = int(0.12 * SR)
        t = np.arange(n) / SR
        x = hp(rng.standard_normal(n), 2500) * (np.exp(-t / 0.006) + 0.6 * np.exp(-np.maximum(t - 0.045, 0) / 0.006) * (t > 0.045))
        return x * 0.7
    if kind == "zap":
        n = int(0.16 * SR)
        t = np.arange(n) / SR
        f = 2400 * np.exp(-t * 22) + 120
        x = np.sign(np.sin(2 * np.pi * np.cumsum(f) / SR)) * np.exp(-t / 0.05)
        return lp(x, 6000) * 0.25
    if kind == "riser":
        n = int(1.2 * SR)
        t = np.arange(n) / SR
        k = t / t[-1]
        return (sweep_bp(rng.standard_normal(n), 300, 8000, 2.0) * k ** 2.2 + np.sin(2 * np.pi * np.cumsum(220 * 2 ** (k * 2)) / SR) * k ** 2 * 0.15) * 0.8
    if kind == "revswell":
        n = int(0.7 * SR)
        x = reverb(hp(rng.standard_normal(n), 3000) * np.exp(-np.arange(n) / SR / 0.15), 1.0, 0.6)[::-1]
        return x * np.linspace(0, 1, n) ** 1.5 * 0.9
    raise ValueError(kind)


TSFX = {"silhouette": [("whoosh_up", -8, 0.8), ("impact_big", 0, 0.9)],
        "invert_smear": [("shutter", 0, 0.9), ("whoosh", 0, 0.7)],
        "white_shape": [("impact", 0, 0.9), ("zap", 0, 0.6)],
        "whip": [("whoosh", 0, 0.9)],
        "zoom": [("whoosh_up", -6, 0.8), ("impact", 0, 0.5)],
        "invert_shape": [("zap", 0, 0.8), ("shutter", 0, 0.6)],
        "spin": [("swirl", -9, 0.9), ("impact_big", 0, 1.0)]}


def sfx_track():
    buf = np.zeros(N)
    add(buf, sfx("impact"), 0, 0.7)                    # hook on frame 0
    for f, kind, a, b in T.boundaries():
        for name, off, g in TSFX[kind]:
            x = sfx(name)
            at = fr(f + off)
            if name in ("whoosh", "swirl"):
                at -= len(x) // 2
            if name == "whoosh_up":
                at = fr(f) - len(x)
            add(buf, x, at, g)
    for f, kind in T.accents():
        add(buf, sfx("zap" if kind == "invert" else "shutter"), fr(f), 0.45)
    b_beat, _ = T.scene_frames("beat")
    add(buf, sfx("riser"), fr(b_beat) - int(1.2 * SR), 0.6)
    b_cta, _ = T.scene_frames("cta")
    add(buf, sfx("revswell"), fr(b_cta) - int(0.7 * SR), 0.7)
    return buf


# ------------------------------------------------------------------ music
def music():
    piano_b = np.zeros(N)
    drums = np.zeros(N)
    bass = np.zeros(N)
    plk = np.zeros(N)
    # Fmaj7 - G6 - Am7 - Em7 (one bar each)
    chords = [[53, 57, 60, 64], [55, 59, 62, 64], [57, 60, 64, 67], [52, 55, 59, 62]]
    roots = [41, 43, 45, 40]
    motif = [72, None, 71, 69, None, 67, 69, None]       # 8ths over a bar
    sc = {k: (b0, b0 + nb) for k, b0, nb, _, _ in T.SCENES}
    total = T.NF // T.BEAT + 4

    def in_(key, b):
        return sc[key][0] <= b < sc[key][1]

    for bar in range(total // 4 + 1):
        b0 = bar * 4
        ch, rt = chords[bar % 4], roots[bar % 4]
        dark = any(in_("hook", b0 + d) for d in range(4)) and in_("hook", b0 + 1)
        for m in ch:
            add(piano_b, piano(m + (0 if not dark else -12), 4 * SPB + 0.6, 0.45 if dark else 0.6), bt(b0) + rng.integers(0, 300))
        if not dark:
            add(piano_b, piano(rt + 12, 3.0, 0.5), bt(b0))
        for s in range(8):                                # 8th positions
            b = b0 + s / 2
            if b >= total:
                break
            full = in_("beat", b) or in_("screen", b) or in_("loop", b) or (in_("cta", b) and b < sc["cta"][1] - 2)
            light = in_("stopwatch", b) or in_("idea", b)
            at = bt(b) + (int(0.018 * SR) if s % 2 else 0)  # light swing
            if in_("hook", b):
                if s in (0, 1):
                    add(drums, kick(0.55 if s == 0 else 0.35), at)
                if s == 0:
                    add(bass, sub(rt, 1.6, 0.5), at)
                continue
            if in_("sound", b):                           # "sound is half the edit": everything thins out
                if s == 0:
                    add(drums, kick(0.6), at)
                    add(bass, sub(rt, 1.0, 0.4), at)
                continue
            if full or light:
                if s in (0, 4) or (full and s == 5):
                    add(drums, kick(0.9 if full else 0.6), at)
                if s in (0, 4):
                    add(bass, sub(rt, 1.1, 0.55 if full else 0.4), at)
                if full and s in (2, 6):
                    add(drums, clap(0.7), at)
                if light and s == 4:
                    add(drums, clap(0.35), at)
                add(drums, hat(0.16 if full else 0.08), at)
                add(drums, shaker(0.08), at + int(SPB / 4 * SR))
                if full and s == 7:
                    add(drums, hat(0.12, True), at)
            if (full or in_("cta", b)) and motif[s] is not None:
                add(plk, pluck(motif[s] + (0 if bar % 2 == 0 else -2), 0.45, 0.22), at)
    # last chord rings out over the end card
    end_b = sc["cta"][1] - 2
    for m in chords[0]:
        add(piano_b, piano(m, 3.5, 0.7), bt(end_b))
    add(bass, sub(41, 2.5, 0.5), bt(end_b))
    add(drums, kick(1.0), bt(end_b))

    piano_b = reverb(piano_b, 2.4, 0.35, 6000)
    plk = reverb(plk, 1.6, 0.3, 7000, seed=4)
    drums = reverb(drums, 0.7, 0.06)
    mix = hp(piano_b * 0.8 + drums * 0.85 + bass * 0.55 + plk * 0.9, 35)
    # dark hook scene: low-pass the whole bed
    a, b = [fr(v) for v in T.scene_frames("hook")]
    mix[a:b] = lp(mix[a - 4096:b], 900, 4)[4096:]
    # "half the edit": filter to half the bandwidth
    a, b = [fr(v) for v in T.scene_frames("sound")]
    mix[a:b] = lp(mix[a - 4096:b], 1400, 4)[4096:]
    return mix


def vo_track():
    buf = np.zeros(N)
    st = T.vo_starts()
    for vi, f in st.items():
        a, sr = sf.read(os.path.join(ROOT, "audio", "vo", f"{vi:02d}.wav"), dtype="float64")
        if a.ndim > 1:
            a = a.mean(1)
        a = resample_poly(a, SR // 1000, sr // 1000) if sr != SR else a
        # gentle presence + warmth
        a = a + 0.25 * hp(a, 3500) + 0.15 * lp(a, 200)
        add(buf, a, fr(f), 1.0)
    return buf


def duck(music_, vo):
    env = np.abs(vo)
    env = lp(env, 6) * 4
    g = 1 - 0.55 * np.clip(env / (env.max() * 0.25 + 1e-9), 0, 1)
    return music_ * g


def norm(x, peak=0.89):
    return x / (np.max(np.abs(x)) + 1e-9) * peak


def main():
    m = music()
    s = sfx_track()
    v = vo_track()
    m = norm(m, 0.5)
    s = norm(s, 0.6)
    v = norm(v, 0.85)
    md = duck(m, v)
    fade = int(0.8 * SR)
    end = fr(T.NF) + int(0.3 * SR)
    out = {}
    for name, x in (("music", m), ("sfx", s), ("vo", v),
                    ("mix", np.tanh((md * 0.85 + s * 0.7 + v) * 1.05)),
                    ("mix_no_music", np.tanh((s * 0.7 + v) * 1.05))):
        x = x[:end].copy()
        x[-fade:] *= np.linspace(1, 0, fade)
        st = np.stack([x, x], 1)
        d = int(0.009 * SR)
        if name in ("music", "mix"):
            st[d:, 1] = x[d:] * 0.9 + x[:-d] * 0.1
        sf.write(os.path.join(ROOT, "audio", f"{name}.wav"), norm(st, 0.89).astype(np.float32), SR, subtype="PCM_16")
        out[name] = len(x) / SR
    print(json.dumps(out))


if __name__ == "__main__":
    main()
