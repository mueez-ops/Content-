"""Original drift-phonk soundtrack + sound design for Reel 02, synthesised from
scratch (no samples, no licensed audio), so it is safe for YouTube Content ID.

Writes audio/music.wav, audio/sfx.wav and audio/mix.wav (48 kHz stereo).
"""
import os
import sys

import numpy as np
from scipy.signal import butter, sosfilt, fftconvolve

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import timeline as T  # noqa: E402

SR = 48000
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "audio")
DUR = T.NF / T.FPS + 0.0
N = int(DUR * SR)
SPB = 60 / T.BPM                     # seconds per beat (0.4)
S16 = SPB / 4                        # 16th note
rng = np.random.default_rng(7)


def fr(f):                            # frame -> sample
    return int(round(f / T.FPS * SR))


def bt(b):                            # beat -> sample
    return int(round(b * SPB * SR))


def env(n, a=0.002, d=0.2, curve=4.0):
    t = np.arange(n) / SR
    e = np.exp(-t / max(d, 1e-4) * (curve / 4))
    att = int(a * SR)
    if att > 0:
        e[:att] *= np.linspace(0, 1, att)
    return e


def lp(x, f, o=2):
    return sosfilt(butter(o, f, "low", fs=SR, output="sos"), x)


def hp(x, f, o=2):
    return sosfilt(butter(o, f, "high", fs=SR, output="sos"), x)


def bp(x, lo, hi, o=2):
    return sosfilt(butter(o, [lo, hi], "band", fs=SR, output="sos"), x)


def add(buf, x, at, g=1.0):
    if at < 0:
        x, at = x[-at:], 0
    e = min(len(buf), at + len(x))
    if e > at:
        buf[at:e] += x[: e - at] * g


def note(semi, base=349.23):          # semitones from F4
    return base * 2 ** (semi / 12)


# ------------------------------------------------------------------ instruments
def kick(g=1.0):
    n = int(0.32 * SR)
    t = np.arange(n) / SR
    f = 48 + 140 * np.exp(-t * 38)
    ph = 2 * np.pi * np.cumsum(f) / SR
    x = np.sin(ph) * env(n, 0.001, 0.28)
    click = hp(rng.standard_normal(int(0.004 * SR)), 2500) * 0.5
    x[: len(click)] += click
    return np.tanh(x * 1.6) * g


def b808(freq, length, glide_to=None, g=1.0):
    n = int(length * SR)
    t = np.arange(n) / SR
    f = np.full(n, freq)
    if glide_to:
        k = np.clip((t - length * 0.45) / (length * 0.4), 0, 1)
        f = freq * (glide_to / freq) ** (k * k * (3 - 2 * k))
    f = f + 90 * np.exp(-t * 45)                     # punchy pitch hit
    x = np.sin(2 * np.pi * np.cumsum(f) / SR)
    e = np.minimum(1, t / 0.003) * np.exp(-t / (length * 0.9))
    x = np.tanh(x * e * 3.2) * 0.75                    # saturated phonk 808
    return lp(x, 900) * g


def cowbell(freq, length=0.16, g=1.0):
    n = int(length * SR)
    t = np.arange(n) / SR
    sq = lambda f: np.sign(np.sin(2 * np.pi * f * t))  # noqa: E731
    x = 0.6 * sq(freq) + 0.4 * sq(freq * 1.4836)
    x = bp(x, freq * 0.9, min(freq * 6, 15000)) * env(n, 0.001, 0.07)
    return x * g


def clap(g=1.0):
    n = int(0.35 * SR)
    x = bp(rng.standard_normal(n), 900, 5000) * env(n, 0.001, 0.09)
    for d in (0.008, 0.017):                             # flam
        k = int(d * SR)
        x[k:] += bp(rng.standard_normal(n - k), 900, 5000) * env(n - k, 0.001, 0.02) * 0.6
    t = np.arange(n) / SR
    body = np.sin(2 * np.pi * 190 * t) * env(n, 0.001, 0.05) * 0.6
    return np.tanh((x + body) * 1.4) * g


def hat(open_=False, g=1.0):
    n = int((0.22 if open_ else 0.05) * SR)
    x = hp(rng.standard_normal(n), 7500, 4) * env(n, 0.0005, 0.08 if open_ else 0.014)
    return x * g


def pad_chord(semis, length, g=1.0):
    n = int(length * SR)
    t = np.arange(n) / SR
    x = np.zeros(n)
    for s in semis:
        f = note(s, 174.61)                              # F3 based
        for det in (-0.12, 0.0, 0.11):
            fd = f * 2 ** (det / 12)
            x += (2 * ((t * fd + rng.random()) % 1) - 1)  # saw
    x = lp(x / (len(semis) * 3), 1400)
    a = np.minimum(1, t / 0.6) * np.minimum(1, (length - t) / 0.5).clip(0, 1)
    return x * a * g


def reverb(x, secs=1.6, wet=0.3, damp=4000):
    n = int(secs * SR)
    t = np.arange(n) / SR
    ir = rng.standard_normal(n) * np.exp(-t * 6.5 / secs)
    ir = lp(ir, damp)
    ir /= np.sqrt(np.sum(ir ** 2))
    return x + fftconvolve(x, ir)[: len(x)] * wet


# ------------------------------------------------------------------ SFX
def noise(n):
    return rng.standard_normal(n)


def sweep_bp(x, f0, f1, q=1.2, chunks=64):
    """Band-pass with a moving centre frequency (processed in chunks)."""
    out = np.zeros_like(x)
    L = len(x)
    edges = np.linspace(0, L, chunks + 1).astype(int)
    for i in range(chunks):
        a, b = edges[i], edges[i + 1]
        c = f0 * (f1 / f0) ** (i / (chunks - 1))
        lo, hi = c / (1 + 1 / q), min(c * (1 + 1 / q), SR / 2 - 100)
        seg = x[max(0, a - 2048): b]
        y = bp(seg, lo, hi)
        out[a:b] = y[-(b - a):]
    return out


def sfx(kind):
    if kind == "whoosh":
        n = int(0.42 * SR)
        t = np.arange(n) / SR
        x = sweep_bp(noise(n), 400, 5000) * np.sin(np.pi * t / t[-1]) ** 2
        return x * 1.6
    if kind == "whoosh_up":
        n = int(0.36 * SR)
        t = np.arange(n) / SR
        x = sweep_bp(noise(n), 300, 9000) * (t / t[-1]) ** 2
        return x * 1.8
    if kind in ("impact", "impact_big"):
        big = kind == "impact_big"
        n = int((2.2 if big else 1.0) * SR)
        t = np.arange(n) / SR
        f = 38 + 80 * np.exp(-t * 18)
        boom = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t / (0.9 if big else 0.35))
        crack = lp(noise(n), 3500) * np.exp(-t / 0.05)
        x = np.tanh((boom * 1.8 + crack * 0.7) * 1.5)
        return reverb(x, 2.4 if big else 1.2, 0.35 if big else 0.2, 2500) * (1.1 if big else 0.8)
    if kind == "hit":
        n = int(0.4 * SR)
        t = np.arange(n) / SR
        x = np.sin(2 * np.pi * (60 + 120 * np.exp(-t * 40)) * t) * np.exp(-t / 0.12)
        x += bp(noise(n), 1500, 7000) * np.exp(-t / 0.03) * 0.5
        return np.tanh(x * 1.5) * 0.55
    if kind == "subdrop":
        n = int(1.6 * SR)
        t = np.arange(n) / SR
        f = 30 + 60 * np.exp(-t * 2.5)
        return np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t / 0.8) * 0.9
    if kind == "tick":
        n = int(0.12 * SR)
        t = np.arange(n) / SR
        x = np.sin(2 * np.pi * 2200 * t) * np.exp(-t / 0.012) + hp(noise(n), 4000) * np.exp(-t / 0.006) * 0.6
        return reverb(x, 0.8, 0.25) * 0.6
    if kind in ("riser", "riser_s"):
        secs = 2.0 if kind == "riser" else 0.4
        n = int(secs * SR)
        t = np.arange(n) / SR
        k = t / secs
        x = sweep_bp(noise(n), 200, 9000, 2.0) * k ** 2.2
        f = 110 * 2 ** (k * 3)
        x += np.sin(2 * np.pi * np.cumsum(f) / SR) * k ** 2 * 0.25
        return x * 0.9
    if kind == "revcym":
        n = int(0.5 * SR)
        x = hp(noise(n), 5000) * np.exp(-np.arange(n) / SR / 0.2)
        x = reverb(x, 0.9, 0.5)[::-1]
        return x * 1.0 * np.linspace(0, 1, n) ** 1.5
    if kind == "glitch":
        n = int(0.32 * SR)
        x = np.zeros(n)
        i = 0
        while i < n:
            L = int(rng.uniform(0.008, 0.035) * SR)
            f = rng.choice([180, 420, 900, 1800, 3200])
            tt = np.arange(min(L, n - i)) / SR
            x[i:i + len(tt)] = np.sign(np.sin(2 * np.pi * f * tt)) * rng.uniform(0.2, 0.7)
            i += L + int(rng.uniform(0, 0.012) * SR)
        x = np.round(x * 6) / 6                          # bit-crush
        return lp(x, 7000) * 0.5
    if kind == "neon":
        n = int(0.9 * SR)
        t = np.arange(n) / SR
        buzz = np.sign(np.sin(2 * np.pi * 120 * t)) * 0.3 + np.sin(2 * np.pi * 240 * t) * 0.2
        flick = (rng.random(n // 480 + 1) > 0.35).repeat(480)[:n]
        x = lp(buzz, 3000) * flick * np.exp(-t / 0.5)
        x[: int(0.01 * SR)] += noise(int(0.01 * SR)) * 0.6
        return x * 0.6
    raise ValueError(kind)


# ------------------------------------------------------------------ music
def music():
    L = np.zeros(N + SR)
    drums = np.zeros_like(L)
    bass = np.zeros_like(L)
    bells = np.zeros_like(L)
    pads = np.zeros_like(L)

    # F minor phonk cowbell riffs (16 steps / bar), None = rest. Semitones from F4.
    riff_a = [0, None, 0, None, 3, None, 0, None, 8, None, 7, None, 3, None, 5, None]
    riff_b = [0, None, 0, None, 3, None, 0, 3, 10, None, 8, None, 7, None, 3, 2]
    roots = [0, 0, -4, -2]                            # F, F, Db, Eb (per bar)
    chords = [(0, 3, 7), (0, 3, 7), (-4, 0, 3), (-2, 2, 5)]

    drop_b, break_b, back_b, outro_b, end_b = (T.DROP // T.BEAT, T.BREAK // T.BEAT, T.BACK // T.BEAT,
                                               T.OUTRO // T.BEAT, T.END // T.BEAT)
    total_beats = T.NF // T.BEAT

    for bar in range(total_beats // 4 + 1):
        b0 = bar * 4
        chord = chords[bar % 4]
        root = roots[bar % 4]
        # pads everywhere except the drop (keeps the drop punchy), quiet under it
        pg = 0.33 if b0 < drop_b or b0 >= outro_b else 0.12
        add(pads, pad_chord(chord, 4 * SPB + 0.4), bt(b0), pg)

        riff = riff_a if bar % 2 == 0 else riff_b
        for s in range(16):
            beat = b0 + s / 4
            if beat >= end_b + 4:
                break
            in_drop = drop_b <= beat < outro_b and not (break_b <= beat < back_b)
            at = bt(beat)
            # cowbell: filtered in the intro, full in the drop, octave doubled after the break
            if riff[s] is not None and (beat >= 2 and beat < end_b):
                g = 0.55 if in_drop else 0.3
                cb = cowbell(note(riff[s]), g=g)
                if not in_drop:
                    cb = lp(cb, 1200)
                add(bells, cb, at)
                if in_drop and beat >= back_b:
                    add(bells, cowbell(note(riff[s] + 12), 0.1, 0.18), at)
            if in_drop:
                if s in (0, 7, 10):
                    add(drums, kick(0.95), at)
                    gl = note(root, 43.65) * (0.5 if s == 10 and bar % 2 else 1.0)
                    add(bass, b808(note(root, 43.65), SPB * (1.6 if s != 10 else 1.4),
                                   glide_to=gl if s == 10 and bar % 2 else None), at)
                if s in (4, 12):
                    add(drums, clap(0.75), at)
                if s % 2 == 0:
                    add(drums, hat(g=0.32 if s % 4 else 0.22), at)
                if s in (14, 15) and bar % 2:              # 32nd hat rolls
                    for r in range(2):
                        add(drums, hat(g=0.2), at + int(r * S16 / 2 * SR))
                if s == 6:
                    add(drums, hat(True, 0.16), at)
            elif beat >= 4 and beat < drop_b and s % 2 == 0:  # intro hats creeping in
                add(drums, hat(g=0.10 + 0.12 * (beat - 4) / 4), at)

    # outro: 808 sustain + filtered bells; end card: one long 808 slide
    add(bass, b808(note(0, 43.65), 4 * SPB, g=0.8), bt(outro_b))
    add(bass, b808(note(0, 43.65), 3.2, glide_to=note(-12, 43.65) * 0.75, g=1.0), bt(end_b))
    add(drums, kick(1.0), bt(outro_b))
    add(drums, kick(1.0), bt(end_b))

    bells = reverb(bells, 1.4, 0.28, 6000)
    drums = reverb(drums, 0.9, 0.08)
    pads = reverb(pads, 2.5, 0.4, 3000)
    mix = drums * 0.95 + bass * 0.85 + bells * 0.9 + pads * 0.55

    # outro: low-pass "underwater" filter (384-432)
    a, b = fr(T.OUTRO), fr(T.END)
    mix[a:b] = lp(mix[a - 4096:b], 650, 4)[4096:]

    # tape stop into the break (BREAK -> BACK): playback slows to zero
    a, b = fr(T.BREAK), fr(T.BACK)
    n = b - a
    seg = mix[a - n: a].copy()                       # replay the last beat as it slows
    sp = np.linspace(1, 0, n) ** 1.3
    pos = np.cumsum(sp)
    pos = pos / pos[-1] * (n * 0.55)
    tape = np.interp(pos, np.arange(n), seg) * np.linspace(1, 0, n) ** 0.5
    mix[a:b] = lp(tape, 3000)
    # hard gap right before the drop for contrast
    g0 = fr(T.DROP) - int(0.12 * SR)
    mix[g0:fr(T.DROP)] *= np.linspace(1, 0.05, fr(T.DROP) - g0)
    return mix[:N]


def sfx_track():
    buf = np.zeros(N + 3 * SR)
    events = list(T.SFX)
    for s in T.SHOTS:
        if s["tin"] in T.TIN_SFX and s["f0"] not in (T.DROP,):
            events.append((s["f0"], T.TIN_SFX[s["tin"]], 0.55))
        if s["tout"] in ("whip", "zoom"):
            events.append((s["f0"] + s["n"] - 4, "whoosh", 0.4))
    for f, kind, g in events:
        x = sfx(kind)
        at = fr(f)
        if kind == "riser":
            at = fr(T.DROP) - len(x)          # ends exactly on the drop
        elif kind == "riser_s":
            at = fr(T.END) - len(x)
        elif kind in ("revcym", "whoosh_up"):
            at = fr(f) - len(x) + (fr(T.DROP) - fr(f) if kind == "revcym" else 0)
            if kind == "whoosh_up":
                at = fr(f) - len(x)           # swells into the cut
        elif kind == "whoosh":
            at = fr(f) - int(0.2 * SR)        # centred on the cut
        add(buf, x, at, g)
    return buf[:N]


def write(path, x):
    from scipy.io import wavfile
    wavfile.write(path, SR, (np.clip(x, -1, 1) * 32767).astype(np.int16))


def main():
    os.makedirs(OUT, exist_ok=True)
    m = music()
    s = sfx_track()
    fade = int(0.6 * SR)
    for x in (m, s):
        x[-fade:] *= np.linspace(1, 0, fade)
    m2 = np.stack([m, m], 1)
    # widen bells/pads a touch with a Haas copy on the right channel
    d = int(0.011 * SR)
    m2[d:, 1] = m[d:] * 0.85 + m[:-d] * 0.15
    s2 = np.stack([s, s], 1)
    pk = lambda x: np.max(np.abs(x)) + 1e-9  # noqa: E731
    mix = np.tanh((m2 * 0.8 + s2 * 0.75) * 0.95)
    write(os.path.join(OUT, "music.wav"), m2 / pk(m2) * 0.89)
    write(os.path.join(OUT, "sfx.wav"), s2 / pk(s2) * 0.89)
    write(os.path.join(OUT, "mix.wav"), mix / pk(mix) * 0.89)
    print("audio written:", OUT, f"{N / SR:.2f}s")


if __name__ == "__main__":
    main()
