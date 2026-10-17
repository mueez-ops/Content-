"""2D face rig for the baby still (assets/baby.jpg, 1024x1024).

Every control is a smooth displacement field in source pixels. A pose is a
weighted sum of fields, applied with one backward remap, so the still can open
its mouth, squint, tilt its head and kick its feet without any new pixels
being painted.
"""
import cv2
import numpy as np

SIZE = 1024

# Landmarks measured on assets/baby.jpg (source pixels).
MOUTH = (528, 520)          # centre of the open mouth
EYE_L = (412, 400, 58, 48)  # cx, cy, rx, ry (viewer's left)
EYE_R = (620, 377, 57, 52)
CHEEK_L = (365, 485)
CHEEK_R = (695, 468)
BROW_L = (400, 312)
BROW_R = (632, 292)
HEAD_C = (518, 340)
NECK = (520, 640)           # pivot for head tilt
TUFT = (500, 62)
FOOT_L = (330, 890)
FOOT_R = (670, 900)
HAND_L = (405, 870)
HAND_R = (540, 880)


def _smoothstep(a, b, x):
    t = np.clip((x - a) / (b - a), 0.0, 1.0)
    return t * t * (3 - 2 * t)


def _gauss(X, Y, cx, cy, sx, sy):
    return np.exp(-0.5 * (((X - cx) / sx) ** 2 + ((Y - cy) / sy) ** 2))


def build_fields():
    """Unit displacement fields, each a (dx, dy) pair of float32 arrays."""
    Y, X = np.mgrid[0:SIZE, 0:SIZE].astype(np.float32)
    z = np.zeros_like(X)
    F = {}

    # Jaw drop: everything between the upper lip and the chin slides down,
    # so the mouth interior stretches open. The lip line is tilted (the
    # baby's right corner sits higher), and the chin fades out into the collar.
    mx, my = MOUTH
    lip = 499 - 0.12 * (X - mx)
    chin = 598 - 0.05 * (X - mx)
    wx = np.exp(-0.5 * ((X - mx) / 72) ** 2)
    wy = _smoothstep(lip, lip + 50, Y) * (1 - _smoothstep(chin, chin + 75, Y))
    F["jaw"] = (z, wx * wy)

    # Smile: mouth corners pull out and up.
    g = _gauss(X, Y, mx, my - 5, 85, 38)
    u = np.clip((X - mx) / 67, -1.4, 1.4)
    F["smile"] = (u * g, -np.abs(u) * g * 0.55)

    # Squint: cheek pushes the lower lid up, upper lid drops a little.
    # A narrow horizontal falloff bends the lower lid into a crescent.
    for name, (ex, ey, rx, ry) in (("l", EYE_L), ("r", EYE_R)):
        bx = np.exp(-0.5 * ((X - ex) / (rx * 0.85)) ** 2)
        low = _smoothstep(ey - 0.15 * ry, ey + ry, Y) * (1 - _smoothstep(ey + ry, ey + ry + 75, Y))
        up = (1 - _smoothstep(ey - ry, ey + 0.1 * ry, Y)) * _smoothstep(ey - ry - 60, ey - ry, Y)
        F["lid_low_" + name] = (z, -bx * low)
        F["lid_up_" + name] = (z, bx * up)

    # Cheeks rise and puff outwards.
    for name, (cx, cy), side in (("l", CHEEK_L, -1), ("r", CHEEK_R, 1)):
        g = _gauss(X, Y, cx, cy, 60, 50)
        F["cheek_" + name] = (side * 0.35 * g, -g)

    # Brows lift.
    g = _gauss(X, Y, *BROW_L, 75, 38) + _gauss(X, Y, *BROW_R, 75, 38)
    F["brow"] = (z, -g)

    # Head: everything inside a soft circle around the head, cut off above
    # the shoulders so the body and the toys stay put.
    hx, hy = HEAD_C
    r = np.sqrt((X - hx) ** 2 + (Y - hy) ** 2)
    wh = (1 - _smoothstep(330, 430, r)) * (1 - _smoothstep(585, 675, Y))
    F["head_x"] = (wh, z)
    F["head_y"] = (z, wh)
    px, py = NECK
    F["head_rot"] = (-(Y - py) * wh, (X - px) * wh)  # per radian

    # Hair tuft wobble.
    g = _gauss(X, Y, *TUFT, 55, 48) * (1 - _smoothstep(110, 160, Y))
    F["tuft_x"] = (g, z)
    F["tuft_y"] = (z, g)

    # Feet kick up, hands bounce.
    for name, (cx, cy) in (("foot_l", FOOT_L), ("foot_r", FOOT_R)):
        F[name] = (z, -_gauss(X, Y, cx, cy, 80, 62))
    for name, (cx, cy), side in (("hand_l", HAND_L, 1), ("hand_r", HAND_R, -1)):
        g = _gauss(X, Y, cx, cy, 52, 46)
        F[name] = (side * 0.4 * g, -g)

    return {k: (dx.astype(np.float32), dy.astype(np.float32)) for k, (dx, dy) in F.items()}


class Rig:
    def __init__(self, image_bgr):
        assert image_bgr.shape[:2] == (SIZE, SIZE)
        self.img = image_bgr
        self.fields = build_fields()
        Y, X = np.mgrid[0:SIZE, 0:SIZE].astype(np.float32)
        self.X, self.Y = X, Y

    def pose(self, **amps):
        """Render the still with the given field amplitudes (pixels; radians for head_rot)."""
        dx = np.zeros((SIZE, SIZE), np.float32)
        dy = np.zeros((SIZE, SIZE), np.float32)
        for k, a in amps.items():
            if a:
                fx, fy = self.fields[k]
                dx += a * fx
                dy += a * fy
        return cv2.remap(self.img, self.X - dx, self.Y - dy, cv2.INTER_CUBIC,
                         borderMode=cv2.BORDER_REFLECT)


def laugh_pose(mouth, laugh, t, kick=0.0, kick_side=1):
    """Map the animation drivers to field amplitudes.

    mouth: 0..1, follows each "ha" of the laugh audio.
    laugh: 0..1, slow envelope of how hard the baby is laughing.
    t: seconds, for the secondary wobble.
    kick: 0..1 foot kick, kick_side +1 / -1 picks the leading foot.
    """
    m, L = mouth, laugh
    wob = np.sin(2 * np.pi * 2.6 * t)
    sway = np.sin(2 * np.pi * 0.55 * t)
    return dict(
        jaw=-12 + 44 * m,
        smile=7 * L + 3 * m,
        lid_low_l=30 * L, lid_low_r=30 * L,
        lid_up_l=11 * L, lid_up_r=11 * L,
        cheek_l=9 * L + 3 * m, cheek_r=9 * L + 3 * m,
        brow=5 * L + 3 * m,
        head_y=-9 * m - 4 * L,
        head_x=4 * sway * L,
        head_rot=0.045 * sway * L + 0.012 * wob * m,
        tuft_x=7 * wob * (0.4 + L) + 4 * sway,
        tuft_y=-3 * m,
        foot_l=kick * (16 if kick_side > 0 else 7),
        foot_r=kick * (7 if kick_side > 0 else 16),
        hand_l=6 * m, hand_r=6 * m,
    )
