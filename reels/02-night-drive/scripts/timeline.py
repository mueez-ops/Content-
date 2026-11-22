"""Reel 02 "Night Drive": the single source of truth for timing.

Everything runs on a 150 BPM grid at 30 fps, so 1 beat = 0.4 s = 12 frames and
1 bar = 48 frames. compose.py (picture) and make_audio.py (sound) both import
this file, so a cut moved here moves its whoosh/impact too.
"""

FPS = 30
BPM = 150
BEAT = 12                      # frames per beat
NF = 528                       # 17.6 s, 44 beats

DROP = 8 * BEAT                # 96  : headlight flare -> beat drops
BREAK = 23 * BEAT              # 276 : tape-stop break (one beat of silence)
BACK = 24 * BEAT               # 288 : beat returns as the neon sign switches on
OUTRO = 32 * BEAT              # 384 : filtered slow-mo hero
END = 36 * BEAT                # 432 : end card

# Source clips (Mixkit IDs). All 4K 3840x2160 unless noted.
CLIPS = {
    "63": "Close up of red sports car (taillight / panel)",
    "64": "Accelerating car dashboard",
    "65": "Closeup of sports car engine",
    "49": "Closeup of red sports car (headlight flare)",
    "50": "Red sports car side view (wheel)",
    "74": "Red sports car",
    "50998": "Top view of the traffic around a roundabout at night",
    "39917": "Wheels of a motorcycle traveling fast down a road",
    "41943": "Speedometer of a motorcycle",
    "4136": "Motorbike racing through tunnels (1920x1080)",
    "42037": "View out of a car window at night",
    "42039": "View from inside a car in night traffic",
    "42048": "Top aerial spinning shot of night traffic (1080x1920 vertical)",
    "41154": "Neon light of a hotel flickering in the dark",
    "4447": "Neon signs with Japanese letters (1920x1080)",
    "44553": "Reflection of a stylish woman in a car mirror",
    "49878": "Big city at night from an aerial shot (1080x1920 vertical)",
    "41161": "Night movement of a main avenue of a big city",
    "3463": "Sparks of fire on a black background (1080x1920, overlay)",
    "1960": "White smoke with black background (overlay)",
}


def S(clip, f0, n, src, spd=1.0, cx=0.5, cx1=None, z=(1.06, 1.06), rot=(0.0, 0.0),
      tin="cut", tout=None, grade=None, overlay=None, shake=0.0):
    """One shot. spd is a constant or (start, end) speed for a ramp; src is the
    source time in seconds at the shot's first frame; cx is the horizontal
    centre of the vertical crop (0..1 of the source width)."""
    return dict(clip=clip, f0=f0, n=n, src=src, spd=spd, cx=cx, cx1=cx if cx1 is None else cx1,
                z=z, rot=rot, tin=tin, tout=tout, grade=grade or {}, overlay=overlay, shake=shake)


MOODY = {"sat": 0.82, "contrast": 1.2, "exposure": 0.9}

SHOTS = [
    # ---- hook / build (0-96): slow, dark, close. Riser underneath.
    S("63", 0, 24, 0.2, 0.55, cx=0.62, z=(1.10, 1.18), grade=MOODY),
    S("50", 24, 24, 1.5, 0.6, cx=0.55, z=(1.16, 1.08), tin="flash_s", grade={**MOODY, "exposure": 1.35}),
    S("64", 48, 24, 2.0, 1.0, cx=0.56, z=(1.22, 1.32), tin="flash_s", grade=MOODY),
    S("49", 72, 24, 1.3, (1.0, 3.4), cx=0.55, z=(1.08, 1.20), tin="flash_s", tout="whiteout", grade=MOODY),
    # ---- drop (96-276)
    S("49", 96, 24, 4.25, (2.0, 0.7), cx=0.56, z=(1.06, 1.10), tin="drop", shake=1.0),
    S("65", 120, 12, 0.6, 2.0, cx=0.56, cx1=0.46, tin="punch", grade={"exposure": 1.2}),
    S("64", 132, 12, 9.0, 3.0, cx=0.56, z=(1.22, 1.30), tin="punch", tout="zoom"),
    S("50998", 144, 24, 0.5, 1.5, cx=0.5, z=(1.14, 1.04), rot=(0, 22), tin="zoom", grade={"exposure": 1.15}),
    S("39917", 168, 12, 3.0, 1.2, cx=0.36, tin="whip", shake=0.6),
    S("41943", 180, 12, 1.0, 2.5, cx=0.42, z=(1.08, 1.16), tin="punch"),
    S("4136", 192, 24, 0.0, (3.0, 0.8), cx=0.45, tin="flash", tout="whip", shake=0.8),
    S("42037", 216, 12, 1.0, 1.5, cx=0.45, tin="whip"),
    S("42039", 228, 12, 2.5, 3.0, cx=0.5, tin="glitch"),
    S("42048", 240, 24, 5.0, 2.0, cx=0.5, z=(1.18, 1.06), rot=(-8, 0), tin="punch"),
    S("74", 264, 12, 1.0, 1.0, cx=0.45, tin="whip"),
    # ---- break (276-288) runs straight into the neon switching on at 288
    S("41154", 276, 36, 2.36, 1.0, cx=0.33, z=(1.04, 1.16), tin="glitch", overlay=("sparks", 288)),
    S("4447", 312, 12, 4.0, 1.5, cx=0.5, z=(1.08, 1.12), tin="punch"),
    S("44553", 324, 24, 9.0, (2.0, 0.6), cx=0.25, tin="flash"),
    S("49878", 348, 12, 3.0, 3.0, cx=0.5, z=(1.10, 1.20), tin="zoom"),
    S("41161", 360, 12, 4.0, 3.0, cx=0.5, tin="whip"),
    S("50", 372, 12, 5.0, 2.0, cx=0.55, z=(1.10, 1.18), tin="punch", tout="zoom", grade={"exposure": 1.3}),
    # ---- outro hero (384-432): slow-mo, desaturated, filtered music
    S("49", 384, 48, 4.6, 0.55, cx=0.55, z=(1.04, 1.16), tin="zoom",
      grade={"sat": 0.55, "contrast": 1.25, "exposure": 0.95}, overlay=("sparks", 384)),
]

# Kinetic type. kind: big = Anton single line, count = countdown digit,
# stack = stacked outro lines, tag = Space Mono technique label.
TEXT = [
    ("big", "WAIT FOR IT", 0, 48),
    ("sub", "SOUND ON", 24, 48),
    ("count", "3", 48, 60),
    ("count", "2", 60, 72),
    ("count", "1", 72, 86),
    ("tag", "01  SPEED RAMPS", 100, 168),
    ("tag", "02  MOTION BLUR", 168, 240),
    ("tag", "03  TRANSITIONS", 240, 312),
    ("tag", "04  COLOUR + VFX", 312, 384),
    ("big", "STOP", 240, 248),
    ("big", "THE", 248, 256),
    ("big", "SCROLL.", 256, 272),
    ("stack", ("YOUR BRAND", 384), ("DESERVES", 396), ("THIS.", 408)),
]

# Sound-design hits that are not implied by a shot's transition.
SFX = [
    (0, "impact", 0.9), (0, "whoosh", 0.5),
    (24, "tick", 0.7), (48, "tick", 0.8), (60, "tick", 0.8), (72, "tick", 0.9),
    (36, "riser", 1.0),                     # 36 -> 96
    (84, "revcym", 0.9),                    # swells into the drop
    (DROP, "impact_big", 1.0), (DROP, "subdrop", 1.0),
    (144, "impact", 0.6), (240, "impact", 0.8), (248, "tick", 0.6), (256, "impact", 0.7),
    (BREAK, "glitch", 0.8),
    (BACK, "impact_big", 0.9), (BACK, "neon", 0.6),
    (OUTRO, "impact", 0.8), (OUTRO, "subdrop", 0.7),
    (396, "tick", 0.6), (408, "impact", 0.9),
    (420, "riser_s", 0.7),
    (END, "impact_big", 1.0), (END, "glitch", 0.7), (END, "subdrop", 0.9),
    (456, "tick", 0.6),
]

# Transition-in types that get an automatic SFX.
TIN_SFX = {"whip": "whoosh", "zoom": "whoosh_up", "glitch": "glitch", "punch": "hit", "flash": "hit"}
