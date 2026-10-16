"""Instagram profile pictures from the halfsecond mark, in the reel's palette.

    assets/pfp/halfsecond_pfp.png       cream paper, ink ring, orange half (matches the end card)
    assets/pfp/halfsecond_pfp_dark.png  ink, cream ring, orange half
Instagram crops to a circle, so the mark sits well inside it.
"""
import os

from PIL import Image, ImageDraw

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "assets", "pfp")
INK, PAPER, ORANGE = (14, 13, 12), (236, 229, 216), (255, 77, 34)
S, K = 1080, 4


def pfp(bg, ring, path):
    im = Image.new("RGB", (S * K, S * K), bg)
    d = ImageDraw.Draw(im)
    c, r, w = S * K / 2, S * K * 0.27, int(S * K * 0.03)
    d.pieslice([c - r, c - r, c + r, c + r], 90, 270, fill=ORANGE)
    d.ellipse([c - r, c - r, c + r, c + r], outline=ring, width=w)
    im.resize((S, S), Image.LANCZOS).save(path)


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    pfp(PAPER, INK, os.path.join(OUT, "halfsecond_pfp.png"))
    pfp(INK, PAPER, os.path.join(OUT, "halfsecond_pfp_dark.png"))
    print("wrote", OUT)
