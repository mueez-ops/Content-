# Short 03 — "Find the Odd One Out: 3 Levels"

A 24.7 s YouTube Short, vertical 1080×1920 at 60 fps. It's an interactive puzzle for all ages: no voiceover, big readable text, and the puzzle is already on screen on frame 0 with the timer running. Every picture and sound is made by the scripts here, so none of it is AI-generated.

The other scripts, plus the YouTube policy checklist, are in [`SCRIPTS.md`](SCRIPTS.md).

| File | What it is |
|---|---|
| `build/odd_one_out_short.mp4` | Final Short, ready to upload (H.264 + stereo AAC, about -15 LUFS) |
| `build/cover.jpg` | Thumbnail: level 1 mid-countdown |
| `audio/mix.wav` | Final mix; `music.wav` and `sfx.wav` are the stems |

## Timeline

| Time | Level | Puzzle | Timer |
|---|---|---|---|
| 0.0–5.7 s | 1/3 EASY (green) | 47 🍎, one 🍅 | 4 s |
| 6.0–13.2 s | 2/3 MEDIUM (orange) | 47 😃, one 😄 | 5 s |
| 13.5–21.9 s | 3/3 HARD (red) | 47 🐔, one facing the other way | 6 s |
| 21.9–24.7 s | End card | **HOW MANY DID YOU FIND?** with bubbles 1 · 2 · 3, **COMMENT BELOW 👇** and **SUBSCRIBE** | |

Each level follows the same pattern:
1. The cells pop in as a wave, with a whoosh and bubble pops.
2. The clock ticks once per second. The bar goes green → yellow → red, and on the last 2 seconds the number turns red, pulses and the tick gets higher.
3. Reveal: the other cells dim, a red ring draws itself around the answer, confetti bursts and a ding plays. The banner reads **FOUND IT? ✅**, or **WOW! 🔥 DID YOU GET IT?** on level 3.

The grid sits inside the Shorts safe area, clear of the like and comment buttons on the right and the caption at the bottom, so the answer is never hidden behind the app UI.

## Make the next episode

Edit `LEVELS` in `scripts/timeline.py`:
- `base` and `odd` are emoji codepoints from `@lobehub/fluent-emoji-3d`. Set `odd: None` to use a mirrored copy of the base emoji.
- `cell` is where the odd one sits, as (col, row).
- `seconds` is how long the timer runs.

Then rebuild:

```bash
pip install numpy scipy pillow opencv-python-headless
npm pack @lobehub/fluent-emoji-3d   # copy the .webp files you need from package/assets/ into assets/emoji/
cd scripts
python make_audio.py
python compose.py          # ~4 min
python compose.py 0 300    # render single frames to build/ for checking
```

These pairs also tested well: 🐭/🐹 (`1f42d`/`1f439`), 🐶/🐺 (`1f436`/`1f43a`), 🍊/🍑 (`1f34a`/`1f351`), 🐟/🐠 (`1f41f`/`1f420`), 🚗/🚕 (`1f697`/`1f695`), and a mirrored 🐌 (`1f40c`) or 🦊 (`1f98a`).

## Assets and licenses

| Asset | License |
|---|---|
| Fluent Emoji 3D (Microsoft, via `@lobehub/fluent-emoji-3d`) | MIT |
| Luckiest Guy font | Apache 2.0 |
| Music and SFX | Original, synthesized in `make_audio.py` |

## Upload

- **Title:** `Find the odd one out 👀 Can you get all 3? #puzzle #shorts`
- **Description:** `Level 3 is tricky! Comment how many you found 👇`
- **Audience:** answer "Made for kids" honestly (see the checklist in `SCRIPTS.md`).
- **Altered content:** No. It isn't realistic and isn't AI-generated.
