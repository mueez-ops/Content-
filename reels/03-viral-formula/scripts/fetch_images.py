"""Download the source photos (Wikimedia Commons originals) into assets/src/."""
import hashlib, os, sys, time, urllib.parse, urllib.request
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(os.path.dirname(HERE), "assets", "src")
FILES = {
    "mithridates": "Mithridate VI musée Thèbes2.jpg",
    "artemision": "Bronze Zeus or Poseidon NAMA X 15161 Athens Greece.jpg",
    "harpocrates": "Harpocrates, Philosopher MET DP825421.jpg",
    "chalcedony": "British Museum Roman Empire 18022019 Bust of a young man Chalcedony 5810.jpg",
    "reel": "16 mm Film Reel (With Film).jpg",
    "verus": "Aelius Verus Ancient Agora Museum S335 Athens.jpg",
    "hermes": "Hermes_Ingenui_Pio-Clementino_Inv544.jpg",
    "watch_hanhart": "Stoppuhr hanhart.jpg",
}
extra = dict(a.split("=", 1) for a in sys.argv[1:])
FILES.update(extra)
os.makedirs(OUT, exist_ok=True)
for key, name in FILES.items():
    n = name.replace(" ", "_")
    ext = n.rsplit(".", 1)[-1].lower()
    path = os.path.join(OUT, f"{key}.{ext}")
    if os.path.exists(path) and os.path.getsize(path) > 10000:
        continue
    h = hashlib.md5(n.encode()).hexdigest()
    q = urllib.parse.quote(n)
    orig = f"https://upload.wikimedia.org/wikipedia/commons/{h[0]}/{h[:2]}/{q}"
    thumb = f"https://upload.wikimedia.org/wikipedia/commons/thumb/{h[0]}/{h[:2]}/{q}/1920px-{q}" + (".png" if ext == "png" else "")
    for attempt in range(6):
        url = orig if attempt % 2 == 0 else thumb
        try:
            data = urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 reel-research"}), timeout=120).read()
            open(path, "wb").write(data); print("ok", key, len(data)); break
        except Exception as e:
            print("retry", key, str(e)[:40]); time.sleep(15 * (attempt + 1))
    time.sleep(10)
