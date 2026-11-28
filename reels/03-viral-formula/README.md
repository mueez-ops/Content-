# Reel 03 — "The Viral Formula"

A 23.4 s vertical reel (1080×1920, 30 fps) for **halfsecond**: seven rules for making a reel go viral, told in the editorial "cut-out poster" style of the references. It uses museum sculptures cut out on soft paper, royal-blue kinetic type typed in sync with the voiceover, and barcodes, crop marks, sparkles and fine print. On top of that are werner.vfx-style hits: silhouette-mask transitions, colour inversions, white subject flashes, smears, whips, zoom and spin blur, and beat punches.

| File | What it is |
|---|---|
| `build/viral_formula_reel_03.mp4` | Main upload: voiceover + music + sound design, −11 LUFS |
| `build/viral_formula_reel_03_no_music.mp4` | Voiceover + sound design, no music. Use it to add a trending sound in TikTok or Instagram at low volume under the voice. |
| `build/viral_formula_reel_03_4k.mp4` | 2160×3840 upscale for YouTube Shorts (higher-bitrate encode on YouTube) |
| `build/cover.jpg` | Cover frame ("you've got HALF A SECOND") |

## Script and scenes (100 BPM, 1 beat = 0.6 s = 18 frames)

| Time | Scene | Voiceover | On screen | Transition in |
|---|---|---|---|---|
| 0.0 s | Stopwatch | "You've got half a second to stop the scroll." | you've got / **HALF A SECOND** / *to stop the scroll* | (hook on frame 0) |
| 2.4 s | Dark: Mithridates head | "So the first frame is the hook. Not the intro." | the first frame / **IS THE HOOK** / *not the intro* | Next scene revealed through the stopwatch's silhouette, then an inversion |
| 5.4 s | Aelius Verus bust | "One video. One idea." | one video / **ONE IDEA** / *nothing more* | Vertical smear + invert |
| 7.8 s | Artemision bronze + music player | "Cut on every beat, so nothing sits still." | cut on / **EVERY BEAT** / *so nothing sits still* | White subject silhouette over the inverted frame |
| 10.8 s | Navy panel + phone (Harpocrates "silence" print) | "Put the words on screen. Most people watch on mute." | put the words / **ON SCREEN**, plus burned-in captions on the phone | Whip pan |
| 14.4 s | Chalcedony bust + live audio bars | "Sound is half the edit." | sound is / **HALF THE EDIT** (half the bars blue; the music is filtered to half) | Zoom blur |
| 16.2 s | Spinning film reel | "And end where you started, so it loops." | end where you started / **SO IT LOOPS** / *watch it again* | Inverted world, subject kept |
| 18.6 s | CTA: Hermes breaking out of a navy panel | "Or just hand it to us. Half-second. DM: edit." | halfsecond logo / **HALFSECOND** / VIDEO EDITING AGENCY / *edit.* / **DM "EDIT"** | Spin blur |

The words appear as they are spoken. Word timestamps come from running faster-whisper over the voice takes (`audio/vo/words.json`). Beat-accurate accents (inversions, white flashes) hit on "HOOK", "HALF" and "HALFSECOND", and on the beats of the "every beat" scene.

## How it's built

- `scripts/make_vo.py`: voiceover with **Kokoro** (open model, Apache-2.0, voice `af_heart`), one WAV per line.
- `scripts/make_audio.py`: original 100 BPM bed (felt-piano chords, pluck motif, soft drums, sub), arranged per scene (muffled heartbeat under the dark hook, full drums on "every beat", band-limited on "half the edit"). Also transition SFX, and ducking under the voice.
- `scripts/fetch_images.py` → `scripts/cutouts.py` (rembg / BiRefNet) → `scripts/prep_assets.py` (removes the maker's name from the stopwatch dial).
- `scripts/compose.py`: the compositor. Style values are in `STYLE`; layout is in the `scene_*` functions; the FX are `transition()` and `accent()`.
- `scripts/timeline.py`: scenes, transitions and the text-to-word mapping. Picture and sound both read it.
- `scripts/encode.sh`: loudness-normalised MP4s + cover.

```bash
pip install numpy scipy pillow opencv-python-headless soundfile kokoro-onnx faster-whisper "rembg[cpu]"
# Kokoro model files: kokoro-v1.0.onnx + voices-v1.0.bin from github.com/thewh1teagle/kokoro-onnx releases
python scripts/make_vo.py <kokoro-model-dir>
python scripts/make_audio.py
python scripts/compose.py          # ~1.5 min on 4 cores
scripts/encode.sh
```

The source photos and cut-outs are committed, so the fetch, cut-out and voiceover steps are only needed to change them. Re-running speech recognition for the word timestamps needs the faster-whisper `base.en` model.

## Sources and rights

All photos are from Wikimedia Commons. Every one used is **CC0 or public domain**, so no attribution or share-alike obligations apply; credits are listed as a courtesy.

| Asset | File | License | Credit |
|---|---|---|---|
| Stopwatch | Stoppuhr hanhart.jpg (dial wordmark removed) | Public domain | StefanPohl |
| Mithridates VI head | Mithridate VI musée Thèbes2.jpg | CC0 | Jebulon (Archaeological Museum of Thebes) |
| Aelius Verus bust | Aelius Verus Ancient Agora Museum S335 Athens.jpg | CC0 | Jebulon (Ancient Agora Museum, Athens) |
| Artemision Bronze | Bronze Zeus or Poseidon NAMA X 15161 Athens Greece.jpg | CC0 | Jebulon (National Archaeological Museum, Athens) |
| Harpocrates print | Harpocrates, Philosopher MET DP825421.jpg | CC0 | Jan Harmensz. Muller (Metropolitan Museum of Art) |
| Chalcedony bust | British Museum Roman Empire 18022019 Bust of a young man Chalcedony 5810.jpg | CC0 | Vassil (British Museum) |
| Film reel | 16 mm Film Reel (With Film).jpg | CC0 | DiscoA340 |
| Hermes | Hermes_Ingenui_Pio-Clementino_Inv544.jpg | Public domain | Marie-Lan Nguyen (Vatican Museums) |

- **Voice:** synthesised with Kokoro (Apache-2.0), not a real person's voice.
- **Music and SFX:** synthesised from scratch, with no samples, so there's nothing for Content ID to claim.
- **Fonts:** Poppins and Kalam (SIL OFL, `assets/fonts/`), plus Instrument Serif for the logo (from Reel 01).
