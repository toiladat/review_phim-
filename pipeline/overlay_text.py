"""Flag shots that contain burned-in overlay text (name cards, location captions,
'to be continued' cards) OUTSIDE the subtitle band. Output: work/shot_flags.json"""
import cv2, numpy as np, json, sys

SRC = r"d:\final_I2V\review_tool\1.mp4"
shots = json.load(open(r"d:\final_I2V\review_tool\work\shots.json"))
cap = cv2.VideoCapture(SRC)
SUB_Y0, SUB_Y1 = 1235, 1585  # source coords of normal subtitle band


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
flags = []
for k, (a, b) in enumerate(shots):
    sc = []
    for f in (0.25, 0.75):
        img = at(a + (b - a) * f)
        if img is not None:
            sc.append(score(img))
    flags.append(sc)
    if k % 200 == 0:
        print(k, flush=True)
json.dump(flags, open(r"d:\final_I2V\review_tool\work\shot_flags.json", "w"))
print("done")

