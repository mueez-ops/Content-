# Reel 02 — "Night Drive"

This is the second reel for **halfsecond**. It's a 17.6 s high-energy VFX edit for TikTok, Instagram Reels and YouTube Shorts: vertical 1080×1920, 30 fps, every cut on a 150 BPM grid. It shows off what the agency does: speed ramps, motion blur, transitions, colour and VFX, with each technique labelled on screen as it happens.

| File | What it is |
|---|---|
| `build/halfsecond_reel_02.mp4` | Main upload: 1080×1920, 30 fps, original music + sound design, −11 LUFS |
| `build/halfsecond_reel_02_no_music.mp4` | Same picture, sound effects only. Use it if you want to add a trending sound inside TikTok or Instagram (the whooshes and hits stay in sync). |
| `build/halfsecond_reel_02_4k.mp4` | 2160×3840 upscale of the same master for YouTube Shorts. YouTube gives 4K uploads a higher-bitrate encode, so it looks sharper on phones. |
| `build/cover.jpg` | Cover frame for the grid ("YOUR BRAND DESERVES THIS.") |

## Timeline (150 BPM, so 1 beat = 0.4 s = 12 frames)

| Time | Frames | Section |
|---|---|---|
| 0.0–3.2 s | 0–95 | **Hook.** "WAIT FOR IT" is on the very first frame, then "SOUND ON" and a 3·2·1 countdown over dark close-ups of a red roadster (tail light, wheel, rev counter). A riser builds as the headlight flares to white. |
| 3.2–11.0 s | 96–275 | **Drop.** The bass hits on the white flash and the car is revealed. After that it's a cut every 1–2 beats: engine, rev needle, a spinning aerial roundabout, motorbike wheel and tach, a tunnel POV, a window whip, night traffic, and an aerial highway with "STOP / THE / SCROLL." |
| 11.0–11.4 s | 276–287 | **Break.** The music tape-stops, the picture goes dark and glitchy, and a dead hotel sign sits in silence… |
| 11.4–12.8 s | 288–383 | …then the neon flicks on exactly as the beat comes back, with sparks. Neon signs, a blue car portrait, a city aerial and an avenue follow. |
| 12.8–14.4 s | 384–431 | **Hero.** Slow-mo headlight with filtered "underwater" music and "YOUR BRAND / DESERVES / THIS." |
| 14.4–17.6 s | 432–527 | **End card.** The halfsecond logo glitches in, followed by "VIDEO EDITING AGENCY", "Your brand next?" and **DM "EDIT"**. |

Text stays inside the TikTok/Reels safe area (nothing important below y = 1500 or under the right-hand icon column).

## Effects (all in `scripts/compose.py`)

- **Speed ramps:** each shot can run at a constant speed or ramp (e.g. 3× → 0.8×). Slow sections use **optical-flow frame interpolation** (OpenCV DIS) so 24 fps footage stays smooth. Fast sections get real **multi-frame motion blur** made by averaging the source frames under a 360° shutter.
- **Transitions:** punch-in, zoom (radial blur in and out), whip pan (directional blur), glitch (slice displacement and RGB split), white flash and white-out.
- **Impact FX:** decaying camera shake, chromatic aberration, a beat-synced zoom pulse on every beat of the drop, and flash frames.
- **Look:** teal shadows and warm highlights, S-curve contrast, highlight bloom/halation, a soft highlight shoulder, vignette, fine film grain and a light sharpen. Every shot is supersampled down from a 4K crop.
- **Type:** Anton display type with a pop, RGB split and glow; Space Mono technique labels with a typewriter reveal; the halfsecond logo from Reel 01 (disc with a sweeping orange half, Instrument Serif wordmark).

Style values (grade, bloom, grain, palette) are in `STYLE` at the top of `compose.py`. Every timing decision (shots, in-points, speeds, crops, transitions, text, SFX hits) is in `scripts/timeline.py`. Both the picture and the audio read it, so moving a cut moves its sound too.

## Rebuild

```bash
pip install numpy scipy pillow opencv-python-headless   # plus ffmpeg
scripts/fetch_sources.sh        # 4K clips from Mixkit -> source/ (~650 MB, not committed)
python scripts/make_audio.py    # music + SFX -> audio/
python scripts/compose.py       # 528 frames -> build/frames/ (about 5 min on 4 cores)
scripts/encode.sh               # -> build/*.mp4 + cover.jpg
```

`python scripts/compose.py --only 0,96,288` renders just those frames, which is handy for checking changes.

## Sources and rights

- **Footage:** [Mixkit](https://mixkit.co) stock videos under the Mixkit License (free for commercial use, no attribution required). The clip IDs and titles are in `CLIPS` in `timeline.py`, and the files come from `https://assets.mixkit.co/videos/<id>/<id>-2160.mp4`. Most are native 4K; 4136 and 4447 are 1080p, and 42048, 49878 and 3463 are native vertical 1080×1920.
- **Music and SFX:** an original drift-phonk track (808s, cowbell riff, claps, hats) and all sound design are synthesised from scratch in `make_audio.py`. There are no samples or licensed tracks, so there's nothing for Content ID to claim.
- **Fonts:** shared with Reel 01 (`../01-half-second/assets/fonts`, SIL OFL).
