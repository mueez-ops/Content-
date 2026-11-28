"""Voiceover for Reel 03, generated locally with Kokoro (Apache-2.0, kokoro-onnx).
One WAV per script line in audio/vo/, plus vo_lines.json with durations."""
import json, os, sys
import numpy as np, soundfile as sf
from kokoro_onnx import Kokoro

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODEL = sys.argv[1] if len(sys.argv) > 1 else "kokoro"
VOICE = os.environ.get("VOICE", "af_heart")
LINES = [
    "You've got half a second to stop the scroll.",
    "So the first frame is the hook. Not the intro.",
    "One video. One idea.",
    "Cut on every beat, so nothing sits still.",
    "Put the words on screen. Most people watch on mute.",
    "Sound is half the edit.",
    "And end where you started, so it loops.",
    "Or just hand it to us. Half-second. DM: edit.",
]
k = Kokoro(os.path.join(MODEL, "kokoro-v1.0.onnx"), os.path.join(MODEL, "voices-v1.0.bin"))
out = []
for i, line in enumerate(LINES):
    a, sr = k.create(line, voice=VOICE, speed=1.04, lang="en-us")
    # trim leading/trailing silence
    nz = np.nonzero(np.abs(a) > 0.01)[0]
    a = a[max(0, nz[0] - int(0.02 * sr)): nz[-1] + int(0.08 * sr)]
    p = os.path.join(ROOT, "audio", "vo", f"{i:02d}.wav")
    sf.write(p, a, sr)
    out.append({"i": i, "text": line, "dur": round(len(a) / sr, 3), "sr": sr})
    print(i, f"{len(a)/sr:.2f}s", line)
json.dump(out, open(os.path.join(ROOT, "audio", "vo", "vo_lines.json"), "w"), indent=1)
