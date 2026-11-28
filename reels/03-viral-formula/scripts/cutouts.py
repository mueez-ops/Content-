"""Cut the subjects out (run one name per process if memory is tight: BiRefNet is large) of assets/src/ with rembg (BiRefNet) -> assets/cutouts/*.png (RGBA, trimmed)."""
import os, sys
import numpy as np
from PIL import Image
from rembg import new_session, remove

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC, OUT = os.path.join(ROOT, "assets", "src"), os.path.join(ROOT, "assets", "cutouts")
os.makedirs(OUT, exist_ok=True)
names = sys.argv[1:] or ["watch_hanhart", "mithridates", "verus", "artemision", "chalcedony", "reel", "hermes"]
sess = new_session(os.environ.get("MODEL", "birefnet-general"))
for n in names:
    im = Image.open(os.path.join(SRC, n + ".jpg")).convert("RGB")
    if max(im.size) > 2600:
        im.thumbnail((2600, 2600), Image.LANCZOS)
    out = remove(im, session=sess, post_process_mask=True)
    a = np.asarray(out)[..., 3]
    ys, xs = np.nonzero(a > 8)
    pad = 6
    box = (max(0, xs.min() - pad), max(0, ys.min() - pad), min(a.shape[1], xs.max() + pad), min(a.shape[0], ys.max() + pad))
    out.crop(box).save(os.path.join(OUT, n + ".png"))
    print(n, out.crop(box).size, flush=True)
