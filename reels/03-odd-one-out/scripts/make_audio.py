"""Soundtrack: bouncy pizzicato loop, clock ticks, pops, whooshes, dings, ta-da.

Everything is synthesized here, so there are no licensing questions.
Writes audio/music.wav, audio/sfx.wav and audio/mix.wav.
"""
import os

import numpy as np
import scipy.io.wavfile as wavfile
import scipy.signal as sig

from timeline import BPM, DURATION, END_START, SCHEDULE, SR

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "audio")
N = int(DURATION * SR)
rng = np.random.default_rng(3)


def note(n):
    return 440 * 2 ** ((n - 69) / 12)


def karplus(freq, dur, bright=0.5, decay=0.996):
    n = int(dur * SR)
    p = int(SR / freq)
    buf = sig.lfilter([bright, 1 - bright], [1], rng.uniform(-1, 1, p))
    out = np.empty(n)
    for i in range(n):
        out[i] = buf[i % p]
        buf[i % p] = decay * 0.5 * (buf[i % p] + buf[(i + 1) % p])
    return out


def bell(freq, dur, decay=3.0):
    t = np.arange(int(dur * SR)) / SR
    x = (np.sin(2 * np.pi * freq * t) + 0.4 * np.sin(2 * np.pi * freq * 2.76 * t) * np.exp(-t * 8)
         + 0.2 * np.sin(2 * np.pi * freq * 5.4 * t) * np.exp(-t * 14))
    return x * np.exp(-t * decay) * np.minimum(1, t * 500)


def tick(freq):
    t = np.arange(int(0.08 * SR)) / SR
    body = np.sin(2 * np.pi * freq * t) * np.exp(-t * 70)
    click = rng.normal(0, 1, len(t)) * np.exp(-t * 400) * 0.5
    return body + sig.sosfilt(sig.butter(2, 2000, "hp", fs=SR, output="sos"), click)


def pop(f0=1100, f1=350, dur=0.08):
    t = np.arange(int(dur * SR)) / SR
    f = f1 + (f0 - f1) * np.exp(-t * 70)
    return np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 45)


def whoosh(dur=0.4, lo=500, hi=4000):
    n = int(dur * SR)
    x = sig.sosfilt(sig.butter(2, [lo, hi], "bp", fs=SR, output="sos"), rng.normal(0, 1, n))
    return x * np.sin(np.linspace(0, np.pi, n)) ** 2


def chord_hit(notes, dur, gap=0.07, decay=2.5):
    out = np.zeros(int((dur + gap * len(notes)) * SR))
    for i, n in enumerate(notes):
        b = bell(note(n), dur, decay)
        out[int(i * gap * SR):][:len(b)] += b
    return out


def music():
    beat = 60 / BPM
    out = np.zeros(N + 2 * SR)
    # I - vi - IV - V in C, one bar each; bass on 1 and 3, chord stabs on the off-beats.
    prog = [(48, [60, 64, 67]), (45, [57, 60, 64]), (41, [57, 60, 65]), (43, [55, 59, 62])]
    hook = [72, 76, 79, 76, 74, 77, 76, 72]  # little motif every other bar
    cache = {}

    def pl(n, dur, bright, g, t):
        key = (n, dur, bright)
        if key not in cache:
            cache[key] = karplus(note(n), dur, bright, 0.993)
        i = int(t * SR)
        out[i:i + len(cache[key])] += g * cache[key][:len(out) - i]

    nbeats = int(DURATION / beat) + 1
    for b in range(nbeats):
        t = b * beat
        root, ch = prog[(b // 4) % 4]
        if b % 2 == 0:
            pl(root, 0.5, 0.8, 0.5, t)
        else:
            pl(root + 7, 0.4, 0.8, 0.3, t)
        for k, n in enumerate(ch):
            pl(n, 0.25, 0.4, 0.13, t + beat / 2 + k * 0.006)
        if (b // 4) % 2 == 1:
            n = hook[b % 4 * 2], hook[b % 4 * 2 + 1]
            for j, m in enumerate(n):
                x = bell(note(m), 0.5, 6)
                i = int((t + j * beat / 2) * SR)
                out[i:i + len(x)] += 0.07 * x[:len(out) - i]
    # Soft shaker on eighths.
    for e in range(nbeats * 2):
        x = rng.normal(0, 1, int(0.04 * SR)) * np.exp(-np.arange(int(0.04 * SR)) / SR * 90)
        i = int(e * beat / 2 * SR)
        out[i:i + len(x)] += (0.035 if e % 2 else 0.02) * x
    out = sig.sosfilt(sig.butter(2, 60, "hp", fs=SR, output="sos"), out[:N])
    return out / np.abs(out).max()


def sfx():
    out = np.zeros(N + 2 * SR)

    def add(x, t, g):
        i = int(t * SR)
        out[i:i + len(x)] += g * x[:len(out) - i]

    for lv in SCHEDULE:
        if lv["index"]:
            add(whoosh(0.35), lv["enter"] - 0.3, 0.3)
            for k in range(6):
                add(pop(900 + 120 * k, 300), lv["enter"] + 0.05 * k + 0.05, 0.22)
        n = lv["seconds"]
        for s in range(n):
            last = n - s <= 2
            add(tick(2300 if last else 1700), lv["start"] + s, 0.5 if last else 0.38)
        r = lv["reveal"]
        add(pop(1400, 500, 0.1), r, 0.4)
        add(chord_hit([79, 84, 88], 1.0), r + 0.02, 0.32)
        if lv["index"] == len(SCHEDULE) - 1:
            add(chord_hit([72, 76, 79, 84, 88, 91], 1.4, 0.06), r + 0.1, 0.3)
        add(whoosh(0.3, 1200, 7000), lv["exit"] - 0.05, 0.18)
    add(whoosh(0.4), END_START - 0.1, 0.25)
    add(chord_hit([67, 72, 76, 79, 84], 1.6, 0.09), END_START + 0.1, 0.32)
    add(pop(1200, 400, 0.1), END_START + 0.9, 0.35)
    return out[:N]


def write(name, x):
    wavfile.write(os.path.join(OUT, name), SR, (np.clip(x, -1, 1) * 32767).astype(np.int16))


def main():
    os.makedirs(OUT, exist_ok=True)
    mus, fx = music(), sfx()
    mix = mus * 0.22 + fx * 0.9
    mix[-int(0.3 * SR):] *= np.linspace(1, 0, int(0.3 * SR))
    mix = mix / np.abs(mix).max() * 0.95
    write("music.wav", mus)
    write("sfx.wav", fx)
    write("mix.wav", mix)
    print(f"duration {DURATION}s, end card at {END_START:.2f}s")


if __name__ == "__main__":
    main()
