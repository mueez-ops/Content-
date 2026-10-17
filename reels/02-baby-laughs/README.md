# Short 02 — "Try not to laugh" baby

A 15 s YouTube Short, vertical 1080×1920 at 60 fps. The supplied baby still is rigged in 2D so the baby laughs nonstop: the mouth opens on every "ha", the eyes squint, the cheeks and brows lift, the head tilts, the hair tuft wobbles and the feet kick. It's built to hook doomscrollers and kids: a "TRY NOT TO LAUGH" title is on frame 0, the laughing starts at full volume on frame 0, and the clip loops back into the laugh with no end card.

| File | What it is |
|---|---|
| `build/baby_laughs_short.mp4` | Final Short, ready to upload (H.264 + stereo AAC, -14 LUFS) |
| `build/cover.jpg` | Thumbnail frame (the big laugh) |
| `audio/mix.wav` | Final mix; `laugh.wav`, `music.wav` and `sfx.wav` are the stems |

## Timeline

| Time | What happens |
|---|---|
| 0.0–3.4 s | Big **TRY NOT TO LAUGH 😂** title over a zoomed-in, laughing baby. After that it shrinks to a badge that stays at the top. |
| 0–15 s | Colored **HA / HAHA / HEHE** words pop up on strong laugh syllables, and 😂🤣😆 rise up the side lanes (kept off the face). The camera punches in a little on every hard "ha". |
| 6.4–8.1 s | **WAIT FOR IT 👀** while the camera slowly pushes in, then 0.3 s of silence |
| 8.2 s | **The big laugh:** white flash, punch-in on the face, screen shake, an emoji burst and **HAHAHAHA!** |
| 12.4–15 s | **DID YOU SMILE? 😍** with a bouncing red **SUBSCRIBE** button, 👇 and hearts |

## Sound

- **Laugh:** a real recording, "Laughing Boy of 16 Months" by Joseph Sardin, [BigSoundBank #0980](https://bigsoundbank.com/laughing-boy-of-16-months-s0980.html). It's licensed **CC0** (public domain), so it's free for monetized use and needs no credit. The 6.9 s recording is cut into pieces and re-sequenced to fill 15 s. Pieces are pitch-shifted by ±2 semitones so the repeats don't sound copy-pasted. The edit list is `LAUGH_EDIT` in `scripts/timeline.py`.
- **Music:** an original ukulele-and-glockenspiel loop at 120 BPM, synthesised in `make_audio.py`. It ducks under the laugh.
- **SFX:** synthesised pops, a boing, whooshes and sparkles.

## Assets and licenses

| Asset | Source | License |
|---|---|---|
| `assets/baby.jpg` | Supplied image | Yours |
| `assets/audio/bigsoundbank_0980_…flac` | BigSoundBank | CC0 |
| `assets/fonts/LuckiestGuy-Regular.woff` | Luckiest Guy (Google Fonts, via `@fontsource/luckiest-guy`) | Apache 2.0 |
| `assets/emoji/*.webp` | Microsoft Fluent Emoji 3D (via `@lobehub/fluent-emoji-3d`) | MIT |

## How the animation works

`scripts/face_rig.py` defines smooth displacement fields on the 1024×1024 still: jaw drop, smile, lower and upper lids, cheeks, brows, head translate and rotate, hair tuft, feet and hands. A pose is a weighted sum of these fields applied with one `cv2.remap`, so no new pixels are painted. `laugh_pose()` maps two drivers taken from `audio/laugh.wav` to field amplitudes:

- `mouth` is a fast envelope that follows each "ha" (22 ms attack, 65 ms release, 25 ms visual lead).
- `laugh` is a slow envelope for how hard the baby is laughing. It drives the squint, cheeks and head sway.

Landmark coordinates are measured on this image, at the top of `face_rig.py`. To reuse the rig on a different still, re-measure them.

## Rebuild

```bash
pip install numpy scipy pillow opencv-python-headless
cd scripts
python make_audio.py      # soundtrack + events.json -> audio/
python compose.py         # picture + mux -> build/  (~3 min on 4 cores)
python compose.py 0 495   # just render those frame numbers to build/ for checking
python compose.py --mux   # re-mux audio only, after changing the mix
```

Copy and timings are in `scripts/timeline.py`. Colors, the camera and the overlays are in `scripts/compose.py`.

## Upload tips

- Title idea: *Try not to laugh 😂 this baby can't stop giggling #shorts*
- Use the first second as the thumbnail, or pick `build/cover.jpg` in the mobile app.
- The audio is a real CC0 laugh, so there are no Content ID issues. You can also add a trending sound at low volume in the Shorts editor.
