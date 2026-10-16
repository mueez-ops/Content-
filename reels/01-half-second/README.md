# Reel 01 — "You've got 0.5 seconds"

First reel for **halfsecond**. It's 15 s, vertical 1080×1920, 30 fps, built in the editorial-film-edit style: film grain, bloom/halation, black-and-white inserts, kinetic serif type, mask wipes and a three-panel split.

| File | What it is |
|---|---|
| `build/halfsecond_reel_01.mp4` | Final reel with music and SFX, ready to upload |
| `build/halfsecond_reel_01_no_music.mp4` | Same picture, SFX only. Use it if you want to add a trending sound inside Instagram. |
| `build/cover.jpg` | Cover frame for the grid |
| `assets/pfp/halfsecond_pfp.png` | Instagram profile picture: cream, black ring, orange half. It matches the end card. |
| `assets/pfp/halfsecond_pfp_dark.png` | Dark profile picture alternative |
| `build/v1/` | The previous version (red hero, thumb scroll), kept for reference |

## Timeline (120 BPM, so 1 beat = 0.5 s = 15 frames)

| Time | Frames | Section |
|---|---|---|
| 0.0–1.0 s | 0–29 | Black stopwatch card with a big **0.5s** and four clock ticks. "That's how long your ad gets." |
| 1.0–4.0 s | 30–119 | **A — The usual ad.** A realistic phone (titanium frame, side buttons, Dynamic Island, glass reflection) shows an unbranded social feed: status bar, stories, the sponsored post with "20% OFF / BUY NOW!!", action icons and a tab bar. The feed is dragged, then flicked past the ad with iOS-style deceleration, motion blur and a scroll indicator, with no hand on screen. The screen then drains to grey, an orange ✕ appears, and "Scrolled past. Nobody saw it." |
| 4.0–12.0 s | 120–359 | **B — The Halfsecond version.** The hook "They'll ask what you're wearing." is on the very first frame. After that it's macro close-ups, a whip turn, a three-panel split, the bottle dropping in, a light sweep with scent notes and the hero turntable. It ends on the hero shot (brand-orange wall, black gloss floor), with the same offer done properly: "20% off, this week only. SHOP THE DROP →". Every cut lands on the beat grid. |
| 12.0–15.0 s | 360–449 | End card with the halfsecond logo (half-filled stopwatch disc), "Your brand next? DM us." and the line "Ads built for the first half second". |

## Brand palette

The whole reel uses the profile picture's three colours. The values are in `STYLE` in `scripts/compose.py` and `BRAND_*` in `scripts/render_product.py`.

| Colour | Hex | Where it is used |
|---|---|---|
| Ink | `#0E0D0C` | Intro background, phone, the hero's black floor, hero text |
| Cream | `#ECE5D8` / `#F0E9DD` | Section A background, end card, hook text |
| Signal orange | `#FF4D22` | The "s" in 0.5s, stopwatch ring, ✕, hook underline, story rings, hero wall, logo half |

## The product

No product footage was supplied, so the product is a **3D-rendered stand-in perfume** called "VELOUR N°05". The brand is made up and the bottle was modelled in Blender. It isn't a real brand.

To use your own product (sneakers, watch, etc.), film short phone clips and put them in place of the matching `renders/<shot>/` frame folders. Export frames with `ffmpeg -i clip.mp4 renders/<shot>/%04d.png`. Then run `compose.py` again. Shots used:

| Shot folder | Use | Frames |
|---|---|---|
| `boring` | Flat, front-on, over-lit product photo (1 frame) | 1 |
| `glass_macro` | Low close-up sliding across the product | 15 |
| `cap_macro` | Detail close-up (cap / logo / laces / crown) | 20 |
| `label_macro` | Close-up of the brand name | 12 |
| `whip` | Fast spin into a front view | 15 |
| `drop` | Product drops into frame and lands | 15 |
| `sweep` | Dark product, a single light passes across it | 30 |
| `hero` | Slow turntable on a brand-orange backdrop (top third clear for text) | 45 |

## Rebuild

```bash
python -m venv venv && ./venv/bin/pip install bpy==5.2.2 numpy pillow scipy
PY=./venv/bin/python scripts/render_all.sh     # 3D shots -> renders/ (~1.5 h on 4 CPU cores)
./venv/bin/python scripts/make_audio.py        # soundtrack -> audio/
./venv/bin/python scripts/compose.py           # picture + sound -> build/
```

Style parameters (grain, bloom, palette) are in `STYLE` at the top of `scripts/compose.py`. The cut list is in `cuts()`, and copy and timings are in the `sec_*` functions.

## Sources and rights

- **Picture:** everything was made for this reel: Blender renders, the drawn UI, typography and the logo. The feed UI is a generic mock with no real platform branding.
- **Music and SFX:** synthesised from scratch in `make_audio.py`, with no samples or licensed tracks. The stems are `audio/music.wav` and `audio/sfx.wav`.
- **Fonts:** Instrument Serif, Space Mono, Anton and DM Serif Display (SIL OFL, from the Fontsource npm packages), plus Inter and Liberation Sans (OFL). All are in `assets/fonts/`.
