"""Builds the soundtrack: laugh edit, ukulele/glockenspiel bed, pops, mix.

Outputs to audio/: laugh.wav (stem that drives the mouth), music.wav, sfx.wav,
mix.wav, and events.json (syllable onsets and labelled times).
"""
import json
import os

import numpy as np
import scipy.io.wavfile as wavfile
import scipy.signal as sig

from timeline import CTA, DURATION, LAUGH_EDIT, SR, WAIT_LEAD

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "assets/audio/bigsoundbank_0980_laughing_boy_16_months.flac")
OUT = os.path.join(ROOT, "audio")
N = int(DURATION * SR)
rng = np.random.default_rng(7)


def load_source():
    tmp = os.path.join(OUT, "_src.wav")
    os.system(f'ffmpeg -y -loglevel error -i "{SRC}" -ac 1 -ar {SR} "{tmp}"')
    sr, x = wavfile.read(tmp)
    os.remove(tmp)
    x = x.astype(np.float64) / 32768
    # Gentle high-pass for room rumble.
    return sig.sosfiltfilt(sig.butter(2, 90, "hp", fs=SR, output="sos"), x)


def fade(x, ms):
    n = min(int(ms * SR / 1000), len(x) // 2)
    r = np.sin(np.linspace(0, np.pi / 2, n)) ** 2
    x = x.copy()
    x[:n] *= r
    x[-n:] *= r[::-1]
    return x


def laugh_edit(src):
    out = np.zeros(N)
    events = {}
    pos = 0
    xf = int(0.012 * SR)
    for piece in LAUGH_EDIT:
        if piece[0] is None:
            pos += int(piece[1] * SR)
            continue
        a, b, st, gain = piece[:4]
        seg = src[int(a * SR):int(b * SR)]
        if st:
            # Resampling shifts pitch and speed together, like a faster laugh.
            seg = sig.resample(seg, int(len(seg) / 2 ** (st / 12)))
        seg = fade(seg, 12) * gain
        if len(piece) > 4:
            events[piece[4]] = pos / SR
        start = max(0, pos - xf) if pos else 0
        end = min(N, start + len(seg))
        out[start:end] += seg[:end - start]
        pos = start + len(seg)
    if pos < N:
        print(f"laugh edit ends at {pos / SR:.2f}s")
    out[-int(0.06 * SR):] *= np.linspace(1, 0, int(0.06 * SR))
    return out / np.abs(out).max() * 0.9, events


def onsets(x):
    """Syllable onsets: peaks of a 10 ms RMS envelope, at least 140 ms apart."""
    hop = SR // 100
    env = np.sqrt(np.convolve(x ** 2, np.ones(hop) / hop, "same"))[::hop]
    db = 20 * np.log10(env + 1e-9)
    peaks, props = sig.find_peaks(db, height=-24, distance=14, prominence=6)
    return [(p / 100, float(h)) for p, h in zip(peaks, props["peak_heights"])]


# ---- music: 120 BPM, C G Am F, ukulele strums + glockenspiel ----

def karplus(freq, dur, bright=0.5):
    n = int(dur * SR)
    p = int(SR / freq)
    buf = rng.uniform(-1, 1, p)
    buf = sig.lfilter([bright, 1 - bright], [1], buf)
    out = np.empty(n)
    for i in range(n):
        out[i] = buf[i % p]
        buf[i % p] = 0.996 * 0.5 * (buf[i % p] + buf[(i + 1) % p])
    return out


def glock(freq, dur):
    t = np.arange(int(dur * SR)) / SR
    tone = (np.sin(2 * np.pi * freq * t) + 0.35 * np.sin(2 * np.pi * freq * 2.76 * t) * np.exp(-t * 9)
            + 0.15 * np.sin(2 * np.pi * freq * 5.4 * t) * np.exp(-t * 16))
    return tone * np.exp(-t * 3.2) * np.minimum(1, t * 400)


def note(n):
    return 440 * 2 ** ((n - 69) / 12)


def music():
    out = np.zeros(N + SR)
    beat = 0.5
    chords = [[60, 64, 67, 72], [55, 59, 62, 67], [57, 60, 64, 69], [53, 57, 60, 65]]
    # Glockenspiel line, one note per eighth, -1 = rest. Two bars per row.
    melody = [76, -1, 79, 76, 72, -1, 74, 76, 74, -1, 71, 74, 79, -1, 77, 74,
              72, -1, 76, 72, 69, -1, 72, 76, 77, -1, 76, 72, 74, 72, 69, 67]
    cache = {}

    def add(x, t, g):
        i = int(t * SR)
        if i < len(out):
            out[i:i + len(x)] += g * x[:len(out) - i]

    for b in range(int(DURATION / beat)):
        t = b * beat
        ch = chords[(b // 4) % 4]
        # Down-strum on every beat, up-strum on the off-beat.
        for k, n in enumerate(ch):
            key = (n, 1.2)
            if key not in cache:
                cache[key] = karplus(note(n), 1.2, 0.6)
            add(cache[key], t + k * 0.012, 0.16)
            add(cache[key], t + beat / 2 + (3 - k) * 0.01, 0.08)
        if b % 2 == 0:
            add(karplus(note(ch[0] - 12), 1.0, 0.8), t, 0.22)
    for i, n in enumerate(melody * 2):
        if n > 0:
            add(glock(note(n + 12), 0.9), i * beat / 2, 0.10)
    out = out[:N]
    out = sig.sosfilt(sig.butter(2, 120, "hp", fs=SR, output="sos"), out)
    return out / np.abs(out).max()


# ---- sfx ----

def pop(f0=900, f1=300, dur=0.09):
    t = np.arange(int(dur * SR)) / SR
    f = f1 + (f0 - f1) * np.exp(-t * 60)
    return np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 40)


def boing(dur=0.45):
    t = np.arange(int(dur * SR)) / SR
    f = 260 + 140 * np.sin(2 * np.pi * 9 * t) * np.exp(-t * 4) + 200 * t
    return np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 6) * np.minimum(1, t * 300)


def whoosh(dur=0.45):
    n = int(dur * SR)
    noise = rng.normal(0, 1, n)
    env = np.sin(np.linspace(0, np.pi, n)) ** 2
    lo = sig.sosfilt(sig.butter(2, [600, 3500], "bp", fs=SR, output="sos"), noise)
    return lo * env


def sparkle(dur=0.6):
    out = np.zeros(int(dur * SR))
    for i, n in enumerate([84, 88, 91, 96]):
        g = glock(note(n), dur - i * 0.05)
        out[int(i * 0.05 * SR):][:len(g)] += g
    return out


def sfx(events):
    out = np.zeros(N + SR)

    def add(x, t, g):
        i = int(t * SR)
        out[i:i + len(x)] += g * x[:len(out) - i]

    add(pop(1200, 400), 0.0, 0.5)               # hook title
    add(boing(), 0.05, 0.25)
    add(pop(), 3.4, 0.35)                       # title shrinks to badge
    big = events["big"]
    add(whoosh(), big - WAIT_LEAD, 0.25)        # "wait for it"
    add(whoosh(0.3), big - 0.3, 0.35)           # punch-in
    add(sparkle(), big, 0.3)
    add(pop(1000, 350), CTA[0], 0.45)
    add(sparkle(), CTA[0] + 0.05, 0.2)
    return out[:N]


def write(name, x):
    wavfile.write(os.path.join(OUT, name), SR, (np.clip(x, -1, 1) * 32767).astype(np.int16))


def main():
    os.makedirs(OUT, exist_ok=True)
    laugh, events = laugh_edit(load_source())
    mus = music()
    fx = sfx(events)
    # Duck the bed under the laugh so the baby stays on top.
    env = np.sqrt(np.convolve(laugh ** 2, np.ones(SR // 20) / (SR // 20), "same"))
    duck = 1 - 0.45 * np.clip(env / 0.15, 0, 1)
    mix = laugh * 1.0 + mus * 0.16 * duck + fx * 0.8
    mix = mix / np.abs(mix).max() * 0.95
    write("laugh.wav", laugh)
    write("music.wav", mus)
    write("sfx.wav", fx)
    write("mix.wav", mix)
    events["onsets"] = onsets(laugh)
    with open(os.path.join(OUT, "events.json"), "w") as f:
        json.dump(events, f, indent=1)
    print(f"big laugh at {events['big']:.2f}s, {len(events['onsets'])} syllables")


if __name__ == "__main__":
    main()
