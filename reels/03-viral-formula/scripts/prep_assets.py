"""One-off clean-ups on the cutouts: paint the maker's name off the stopwatch dial."""
import os
import cv2
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
p = os.path.join(ROOT, "assets", "cutouts", "watch_hanhart.png")
im = cv2.imread(p, cv2.IMREAD_UNCHANGED)
x0, y0, x1, y1 = 800, 1495, 1215, 1625                      # logo box (dial wordmark)
box = im[y0:y1, x0:x1, :3]
dark = (cv2.cvtColor(box, cv2.COLOR_BGR2GRAY) < 150).astype(np.uint8) * 255
mask = np.zeros(im.shape[:2], np.uint8)
mask[y0:y1, x0:x1] = cv2.dilate(dark, np.ones((9, 9), np.uint8))
im[..., :3] = cv2.inpaint(im[..., :3], mask, 9, cv2.INPAINT_TELEA)
cv2.imwrite(os.path.join(ROOT, "assets", "cutouts", "stopwatch.png"), im)
print("stopwatch.png written")
