"""Shared timing for the audio and picture passes (seconds)."""
FPS = 60
DURATION = 15.0
W, H = 1080, 1920
SR = 48000

# Laugh edit: pieces of the source recording, (start, end, semitones, gain),
# with an optional label whose start time make_audio.py writes to events.json.
# A gap is (None, seconds). The source is 6.9 s, so every piece is used about
# twice; pitch shifts of a semitone or two keep the repeats from sounding
# copy-pasted. 4.20-4.52 s is skipped because it drops into a low grunt.
LAUGH_EDIT = [
    (2.80, 3.56, 0.0, 1.00),   # opens loud on frame 0
    (0.00, 1.90, 0.0, 0.95),
    (2.00, 2.74, 0.5, 0.95),
    (4.90, 6.14, 0.0, 1.00),
    (3.62, 4.16, -0.5, 0.90),
    (2.80, 3.56, 1.5, 0.95),
    (0.00, 1.90, -1.0, 0.95),
    (None, 0.30),              # "wait for it"
    (4.90, 6.56, 1.0, 1.00, "big"),  # the big one
    (2.00, 2.74, -1.0, 1.00),
    (2.80, 3.56, 0.0, 1.00),
    (0.00, 1.06, 2.0, 0.95),
    (3.62, 4.16, -1.5, 0.90),
    (4.52, 6.14, 0.5, 1.00),
    (6.14, 6.56, 0.0, 0.90),
    (2.00, 2.74, 1.0, 0.90),   # runs past 15 s, so the loop restarts mid-laugh
]

# Picture beats.
HOOK_END = 3.4                 # big "TRY NOT TO LAUGH" title shrinks to a badge
WAIT_LEAD = 1.7               # "WAIT FOR IT" shows this long before the big laugh
CTA = (12.4, DURATION)         # "DID YOU SMILE? SUBSCRIBE"
