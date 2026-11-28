"""Reel 03 "The Viral Formula": shared timing for picture and sound.

100 BPM at 30 fps: 1 beat = 0.6 s = 18 frames. Each scene is one voiceover
line; its kinetic type is timed from the word timestamps in audio/vo/words.json
(faster-whisper on the Kokoro takes), so words appear as they are spoken.
"""
import json
import os

FPS = 30
BPM = 100
BEAT = 18
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# (key, start beat, length in beats, vo line index, transition INTO this scene)
SCENES = [
    ("stopwatch", 0, 4, 0, None),
    ("hook", 4, 5, 1, "silhouette"),     # light -> dark through the stopwatch's shape
    ("idea", 9, 4, 2, "invert_smear"),
    ("beat", 13, 5, 3, "white_shape"),
    ("screen", 18, 6, 4, "whip"),
    ("sound", 24, 3, 5, "zoom"),
    ("loop", 27, 4, 6, "invert_shape"),
    ("cta", 31, 8, 7, "spin"),
]
NF = (31 + 8) * BEAT                    # 702 frames = 23.4 s
VO_LEAD = 3                             # frames between a cut and its line

# Text for each scene: lead (small), big (bold blue), script (handwritten),
# each tied to the VO word indices that say it (None = shown after the line).
TEXT = {
    "stopwatch": dict(lead=("you've got", (0, 1)), big=("HALF A SECOND", (2, 4)), script=("to stop the scroll", (5, 8))),
    "hook": dict(lead=("the first frame", (1, 3)), big=("IS THE HOOK", (4, 6)), script=("not the intro", (7, 9))),
    "idea": dict(lead=("one video", (0, 1)), big=("ONE IDEA", (2, 3)), script=("nothing more", None)),
    "beat": dict(lead=("cut on", (0, 1)), big=("EVERY BEAT", (2, 3)), script=("so nothing sits still", (4, 7))),
    "screen": dict(lead=("put the words", (0, 2)), big=("ON SCREEN", (3, 4)), caption=("most people watch on mute", (5, 9))),
    "sound": dict(lead=("sound is", (0, 1)), big=("HALF THE EDIT", (2, 4))),
    "loop": dict(lead=("end where you started", (1, 4)), big=("SO IT LOOPS", (5, 7)), script=("watch it again", None)),
    "cta": dict(lead=("or just hand it to", (0, 5)), big=("HALFSECOND", (6, 7)), dm=("DM “EDIT”", (8, 9))),
}


def scene_frames(key):
    for k, b0, nb, _, _ in SCENES:
        if k == key:
            return b0 * BEAT, (b0 + nb) * BEAT
    raise KeyError(key)


def vo_starts():
    """Global frame at which each VO line starts."""
    return {vi: b0 * BEAT + VO_LEAD + (1 if vi == 0 else 0) for _, b0, _, vi, _ in SCENES}


def words():
    """Per scene: list of (word, start_frame, end_frame) in global frames."""
    wj = json.load(open(os.path.join(ROOT, "audio", "vo", "words.json")))
    st = vo_starts()
    out = {}
    for k, _, _, vi, _ in SCENES:
        out[k] = [(w, st[vi] + a * FPS, st[vi] + b * FPS) for w, a, b, _ in wj[f"{vi:02d}.wav"]]
    return out


def accents():
    """Werner-style one/two-frame hits inside scenes: (frame, kind).
    kind: invert, white_shape. Placed on key spoken words and on the beat scene's beats."""
    w = words()
    out = [(round(w["hook"][4][1]), "invert"),                 # "IS (the hook)"
           (round(w["sound"][2][1]), "invert"),                # "HALF (the edit)"
           (round(w["cta"][6][1]), "white_shape")]             # "HALF(second)"
    b0, _ = scene_frames("beat")
    out += [(b0 + BEAT * k, "invert" if k % 2 else "white_shape") for k in (2, 3, 4)]
    return sorted(out)


def boundaries():
    """(frame, transition type, scene before, scene after)."""
    return [(SCENES[i][1] * BEAT, SCENES[i][4], SCENES[i - 1][0], SCENES[i][0]) for i in range(1, len(SCENES))]
