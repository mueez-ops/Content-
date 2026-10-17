"""Puzzle content and the shared schedule for the audio and picture passes."""
FPS = 60
W, H = 1080, 1920
SR = 48000
BPM = 120

COLS, ROWS = 6, 8

# Each level: the repeated emoji, the odd one (None = the base emoji mirrored),
# where the odd one sits (col, row), and how long the timer runs.
LEVELS = [
    dict(name="EASY", color=(46, 204, 113), base="1f34e", odd="1f345", cell=(4, 5), seconds=4),
    dict(name="MEDIUM", color=(255, 159, 28), base="1f603", odd="1f604", cell=(1, 2), seconds=5),
    dict(name="HARD", color=(255, 59, 48), base="1f414", odd=None, cell=(2, 6), seconds=6),
]

ENTER = 0.45     # cells pop in as a wave
REVEAL = 1.7     # dim, ring, confetti
EXIT = 0.3       # cells shrink away
END_CARD = 2.8


def schedule():
    """Absolute times for every level: enter, start (timer), reveal, exit."""
    out, t = [], 0.0
    for i, lv in enumerate(LEVELS):
        enter = t
        start = t + (ENTER if i else 0.0)   # level 1 is on screen from frame 0
        reveal = start + lv["seconds"]
        exit_ = reveal + REVEAL + (0.3 if i == len(LEVELS) - 1 else 0)
        out.append(dict(lv, index=i, enter=enter, start=start, reveal=reveal, exit=exit_))
        t = exit_ + EXIT
    return out, t - EXIT  # end card starts when the last level leaves


SCHEDULE, END_START = schedule()
DURATION = round(END_START + END_CARD, 2)
