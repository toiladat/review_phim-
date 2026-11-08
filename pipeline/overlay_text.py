"""Flag shots that contain burned-in overlay text (name cards, location captions,
'to be continued' cards) OUTSIDE the subtitle band. Output: work/shot_flags.json"""
import cv2, glob, numpy as np, json, os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
inp_dir = os.path.join(ROOT, "input")
cands = sorted(glob.glob(os.path.join(inp_dir, "*.mp4")))
SRC = os.path.join(inp_dir, "1.mp4") if os.path.exists(os.path.join(inp_dir, "1.mp4")) else (cands[0] if cands else os.path.join(ROOT, "1.mp4"))
WORK = os.path.join(ROOT, "work")
shots = json.load(open(os.path.join(WORK, "shots.json")))
cap = cv2.VideoCapture(SRC)
src_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) or 1920

meta_p = os.path.join(WORK, "video_meta.json")
if os.path.exists(meta_p):
    meta = json.load(open(meta_p))
    SUB_Y0, SUB_Y1 = meta["sub_y0"], meta["sub_y1"]
else:
    SUB_Y0, SUB_Y1 = (1235, 1585) if src_h > 1200 else (int(src_h * 0.75), int(src_h * 0.95))


def score(img):
    g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    white = (g > 230).astype(np.uint8)
    dark = cv2.dilate((g < 45).astype(np.uint8), np.ones((5, 5), np.uint8))
    edge = white & dark
    edge[SUB_Y0:SUB_Y1] = 0
    # text strokes: many small edge blobs; ignore huge regions
    n, lab, stats, _ = cv2.connectedComponentsWithStats(edge, 8)
    small = [(s[4]) for s in stats[1:] if 8 <= s[4] <= 1500 and s[2] < 120 and s[3] < 120]
    return int(sum(small)), len(small)


def at(t):
    cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
    ok, img = cap.read()
    return img if ok else None


if len(sys.argv) > 1:  # test mode: times
    for t in sys.argv[1:]:
        print(t, score(at(float(t))))
    raise SystemExit
cap.release()

from concurrent.futures import ThreadPoolExecutor

def _worker(chunk):
    idx_start, sub_shots = chunk
    c = cv2.VideoCapture(SRC)
    out = []
    for k, (a, b) in enumerate(sub_shots):
        sc = []
        for f in (0.25, 0.75):
            c.set(cv2.CAP_PROP_POS_MSEC, (a + (b - a) * f) * 1000)
            ok, img = c.read()
            if ok and img is not None:
                sc.append(score(img))
        out.append(sc)
    c.release()
    return idx_start, out

n_workers = min(8, max(1, len(shots) // 100))
step = (len(shots) + n_workers - 1) // n_workers
chunks = [(i, shots[i:i + step]) for i in range(0, len(shots), step)]
flags = []
with ThreadPoolExecutor(n_workers) as ex:
    for _, part in sorted(ex.map(_worker, chunks), key=lambda x: x[0]):
        flags.extend(part)
json.dump(flags, open(os.path.join(WORK, "shot_flags.json"), "w"))
print("done", len(flags))
