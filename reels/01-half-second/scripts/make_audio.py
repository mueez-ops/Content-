"""Synthesises the reel's soundtrack from scratch (no samples, no licensed music).

Writes two stems plus mixes into audio/:
    music.wav   - elevator muzak (boring ad), 120 BPM beat (Halfsecond version), end pad
    sfx.wav     - clock ticks, scroll whoosh, fail stamp, impacts, risers
    mix.wav     - music + sfx (used for the main export)
    sfx_only.wav- version without music (delivered alongside)

Grid: 120 BPM, so one beat = 0.5 s = 15 frames at 30 fps. The Halfsecond section
starts on the downbeat at exactly 4.0 s and every cut in compose.py lands on this grid.
"""
import os
import wave

import numpy as np
from scipy.signal import butter, fftconvolve, lfilter, sosfilt

SR = 48000
DUR = 15.0
N = int(SR * DUR)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "audio")
rng = np.random.default_rng(5)

BPM = 120
BEAT = 60 / BPM
DROP = 4.0  # first frame of the Halfsecond version
END = 12.0  # end card


def buf():
    return np.zeros((N, 2), np.float32)


def place(dst, sig, t, gain=1.0, pan=0.0):
    i = int(round(t * SR))
    if i >= N:
        return
    sig = sig[: N - i]
    if sig.ndim == 1:
        l, r = np.cos((pan + 1) * np.pi / 4), np.sin((pan + 1) * np.pi / 4)
        sig = np.stack([sig * l * 1.414, sig * r * 1.414], 1)
    dst[i : i + len(sig)] += sig * gain


def tt(d):
    return np.arange(int(d * SR)) / SR


def bp(x, lo, hi, order=2):
    return sosfilt(butter(order, [lo, hi], "bandpass", fs=SR, output="sos"), x)


def hp(x, f, order=2):
    return sosfilt(butter(order, f, "highpass", fs=SR, output="sos"), x)


def lp(x, f, order=2):
    return sosfilt(butter(order, f, "lowpass", fs=SR, output="sos"), x)


def noise(d):
    return rng.standard_normal(int(d * SR)).astype(np.float32)


def reverb(x, decay=1.6, mix=0.25, pre=0.012):
    t = tt(decay)
    ir = rng.standard_normal((len(t), 2)) * np.exp(-t * 6.0 / decay)[:, None]
    ir = lp(ir.T, 6000).T
    ir[: int(pre * SR)] = 0
    ir /= np.sqrt((ir ** 2).sum(0))
    wet = np.stack([fftconvolve(x[:, c], ir[:, c])[: len(x)] for c in range(2)], 1)
    return x * (1 - mix) + wet * mix


# ------------------------------------------------------------------ voices
def tick(pitch=4200, d=0.05):
    t = tt(d)
    click = hp(noise(d), 2000) * np.exp(-t * 900)
    ping = np.sin(2 * np.pi * pitch * t) * np.exp(-t * 160)
    wood = np.sin(2 * np.pi * pitch * 0.31 * t) * np.exp(-t * 90)
    return (0.6 * click + 0.5 * ping + 0.35 * wood).astype(np.float32)


def kick(d=0.45, hi=150, lo=44, punch=1.0):
    t = tt(d)
    f = lo + (hi - lo) * np.exp(-t * 30)
    ph = 2 * np.pi * np.cumsum(f) / SR
    body = np.sin(ph) * np.exp(-t * 7.5)
    click = hp(noise(d), 3000) * np.exp(-t * 400) * 0.25 * punch
    return np.tanh((body + click) * 1.6).astype(np.float32)


def clap(d=0.25):
    t = tt(d)
    n = bp(noise(d), 900, 5200)
    e = np.zeros_like(t)
    for o in (0.0, 0.011, 0.022):
        e += (t >= o) * np.exp(-np.clip(t - o, 0, None) * (220 if o < 0.02 else 22))
    tone = np.sin(2 * np.pi * 190 * t) * np.exp(-t * 40) * 0.3
    return (n * e * 0.7 + tone).astype(np.float32)


def hat(d=0.05, open_=False):
    d = 0.22 if open_ else d
    t = tt(d)
    return (hp(noise(d), 7000, 4) * np.exp(-t * (18 if open_ else 110)) * 0.5).astype(np.float32)


def sub(freq, d):
    t = tt(d)
    env = np.minimum(t / 0.004, 1) * np.exp(-t * 3.2)
    s = np.sin(2 * np.pi * freq * t) + 0.25 * np.sin(4 * np.pi * freq * t)
    return np.tanh(s * env * 1.8).astype(np.float32) * 0.8


def saw(freq, t):
    return 2 * ((freq * t) % 1.0) - 1


def stab(freqs, d=0.32, cutoff=2600):
    t = tt(d)
    s = sum(saw(f * dt, t) for f in freqs for dt in (0.997, 1.003))
    s = lp(s, cutoff) * np.exp(-t * 9) * np.minimum(t / 0.003, 1)
    return (s / len(freqs) * 0.9).astype(np.float32)


def pad(freqs, d, cutoff=1400, attack=0.4):
    t = tt(d)
    s = sum(saw(f * dt, t) for f in freqs for dt in (0.995, 1.0, 1.005))
    s = lp(s, cutoff)
    env = np.minimum(t / attack, 1) * np.minimum((d - t) / 0.6, 1).clip(0, 1)
    return (s * env / len(freqs) * 0.45).astype(np.float32)


def pluck(freq, d=0.6):
    """Soft marimba-ish note for the bland muzak."""
    t = tt(d)
    s = np.sin(2 * np.pi * freq * t) + 0.3 * np.sin(2 * np.pi * freq * 4 * t) * np.exp(-t * 30)
    return (s * np.exp(-t * 6) * np.minimum(t / 0.003, 1)).astype(np.float32)


def whoosh(d=0.45, lo=300, hi=6000, up=True):
    t = tt(d)
    n = noise(d)
    out = np.zeros_like(n)
    steps = 24
    for k in range(steps):
        a, b = int(k * len(n) / steps), int((k + 1) * len(n) / steps)
        x = k / (steps - 1)
        fc = lo * (hi / lo) ** (x if up else 1 - x)
        out[a:b] = bp(n, fc * 0.7, min(fc * 1.4, SR / 2 - 100))[a:b]
    env = np.sin(np.pi * np.clip(t / d, 0, 1)) ** 2
    return (out * env).astype(np.float32)


def riser(d=1.0):
    t = tt(d)
    w = whoosh(d, 400, 9000, True)
    env = (t / d) ** 2.2
    return (w / max(1e-6, np.abs(w).max()) * env).astype(np.float32)


def boom(d=2.2):
    t = tt(d)
    f = 34 + 70 * np.exp(-t * 14)
    ph = 2 * np.pi * np.cumsum(f) / SR
    b = np.sin(ph) * np.exp(-t * 1.9)
    crash = hp(noise(d), 2500) * np.exp(-t * 3.0) * 0.22
    return np.tanh((b + crash) * 1.4).astype(np.float32)


def buzz(d=0.28, f=98):
    t = tt(d)
    sq = np.sign(np.sin(2 * np.pi * f * t)) * 0.5 + np.sign(np.sin(2 * np.pi * f * 1.5 * t)) * 0.25
    return (lp(sq, 1800) * np.minimum(t / 0.005, 1) * np.exp(-t * 5)).astype(np.float32)


def note(n):
    return 440.0 * 2 ** ((n - 69) / 12)


# ------------------------------------------------------------------ arrangement
def build():
    music, sfx = buf(), buf()

    # 0-1 s: the stopwatch.
    for k in range(4):
        place(sfx, tick(4200 if k % 2 == 0 else 3300), k * 0.25, 1.0)
    place(sfx, lp(noise(1.0), 120) * 0.25 * np.minimum(tt(1.0) / 0.05, 1), 0.0, 0.5)

    # 1-4 s: the boring ad - bland elevator muzak (C major, 90 BPM), slightly muffled.
    mz = buf()
    place(mz, pad([note(48), note(52), note(55), note(59)], 3.0, cutoff=900), 1.0, 0.8)
    seq = [72, 76, 79, 76, 74, 77, 81, 77]
    for i, n in enumerate(seq):
        place(mz, pluck(note(n)), 1.0 + i * (60 / 90 / 2), 0.5, pan=0.2 * ((i % 2) * 2 - 1))
    mz = lp(mz.T, 2400).T
    # Muzak gets yanked down as the thumb scrolls past.
    t = np.arange(N) / SR
    duck = np.interp(t, [0, 2.55, 3.3, 4.0], [1, 1, 0.12, 0.0])
    music += mz * duck[:, None]

    # Scroll: whoosh at the flick, then the fail buzz + stamp thud with the X.
    place(sfx, whoosh(0.55, 500, 7000, True), 2.6, 0.55)
    place(sfx, kick(0.3, 120, 60, 0.3), 3.33, 0.55)
    place(sfx, buzz(), 3.33, 0.28)
    # Tension into the drop: accelerating ticks + riser.
    for k, tk in enumerate([3.5, 3.625, 3.75, 3.8125, 3.875, 3.9375]):
        place(sfx, tick(4800), tk, 0.25 + k * 0.05)
    place(sfx, riser(0.5), 3.5, 0.35)

    # 4-12 s: Halfsecond version - 4 bars at 120 BPM in A minor (Am F C G).
    beat = buf()
    roots = [45, 41, 48, 43]  # A2 F2 C3 G2
    chords = [[57, 60, 64], [53, 57, 60], [55, 60, 64], [55, 59, 62]]
    for bar in range(4):
        for b in range(4):
            tb = DROP + (bar * 4 + b) * BEAT
            if bar == 3 and b == 3:
                break  # drop-out on the last beat before the end card
            place(beat, kick(), tb, 0.95)
            place(beat, sub(note(roots[bar] - 12), BEAT * 0.95), tb + BEAT / 2, 0.55)
            if b in (1, 3):
                place(beat, clap(), tb, 0.55, pan=0.05)
            place(beat, hat(open_=(b == 3 and bar % 2 == 1)), tb + BEAT / 2, 0.35, pan=0.3)
            if bar >= 2:
                for s16 in (0.25, 0.75):
                    place(beat, hat(), tb + BEAT * s16, 0.2, pan=-0.3)
        st = DROP + bar * 4 * BEAT
        place(beat, stab([note(n) for n in chords[bar]]), st, 0.5, pan=-0.1)
        place(beat, stab([note(n + 12) for n in chords[bar]], 0.22, 3200), st + BEAT * 1.5, 0.32, pan=0.15)
    music += reverb(beat, 1.2, 0.12)

    # Accents tied to picture.
    place(sfx, boom(1.8), DROP, 0.8)                       # hook frame
    place(sfx, whoosh(0.3, 800, 8000, False), 4.98, 0.35)  # whip turn
    place(sfx, whoosh(0.25, 600, 6000, True), 5.47, 0.25)  # split-screen wipe
    place(sfx, kick(0.5, 90, 38, 0.6), 6.133, 0.75)        # bottle lands (frame 184)
    place(sfx, whoosh(0.4, 600, 9000, True), 8.47, 0.22)   # reverse whip
    place(sfx, riser(1.0), 10.9, 0.45)
    place(sfx, tick(4800), 11.5, 0.4)

    # 12-15 s: end card - impact, warm pad, one final tick on the logo.
    place(sfx, boom(3.0), END, 0.85)
    endpad = buf()
    place(endpad, pad([note(45), note(52), note(57), note(60), note(64)], 3.0, cutoff=1600, attack=0.05), END, 0.9)
    music += reverb(endpad, 2.2, 0.35)
    place(sfx, tick(4200), 12.5, 0.4)
    place(sfx, tick(3300), 13.0, 0.25)

    sfx = reverb(sfx, 1.4, 0.18)
    return music, sfx


def master(x, peak=0.75):
    fade = np.ones(N)
    fade[-int(0.35 * SR):] = np.linspace(1, 0, int(0.35 * SR))
    x = x * fade[:, None]
    x = np.tanh(x * 1.2) / np.tanh(1.2)
    return x / max(1e-6, np.abs(x).max()) * peak


def write(path, x):
    pcm = (np.clip(x, -1, 1) * 32767).astype("<i2")
    with wave.open(path, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    music, sfx = build()
    mix = master(music * 0.8 + sfx)
    write(os.path.join(OUT, "music.wav"), master(music))
    write(os.path.join(OUT, "sfx.wav"), master(sfx))
    write(os.path.join(OUT, "mix.wav"), mix)
    write(os.path.join(OUT, "sfx_only.wav"), master(sfx))
    print("wrote", OUT)
