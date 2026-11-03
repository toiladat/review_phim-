"""Estimate the vertical band where burned-in subtitles appear."""
import cv2, numpy as np, json, random

SRC = r"d:\final_I2V\review_tool\1.mp4"
cap = cv2.VideoCapture(SRC)
fps = cap.get(5); n = int(cap.get(7))
random.seed(1)
rows_hist = np.zeros(1920)
bands = []
for i in range(400):
    t = random.uniform(0, n / fps - 1)
    cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
    ok, img = cap.read()
    if not ok:
        continue
    g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    white = (g > 225).astype(np.uint8)
    dark = cv2.dilate((g < 50).astype(np.uint8), np.ones((7, 7), np.uint8))
    edge = white & dark
    prof = edge.sum(1)
    ys = np.where(prof > 25)[0]
    if len(ys) > 20:
        # largest contiguous cluster
        groups = np.split(ys, np.where(np.diff(ys) > 15)[0] + 1)
        gbest = max(groups, key=len)
        if len(gbest) > 30:
            bands.append((round(t, 1), int(gbest[0]), int(gbest[-1])))
            rows_hist[gbest[0]:gbest[-1] + 1] += 1
print("frames with sub:", len(bands))
tops = sorted(b[1] for b in bands); bots = sorted(b[2] for b in bands)
if bands:
    print("top pct", [tops[int(len(tops) * p)] for p in (0.02, 0.1, 0.5, 0.9, 0.98)])
    print("bot pct", [bots[int(len(bots) * p)] for p in (0.02, 0.1, 0.5, 0.9, 0.98)])
json.dump(bands, open(r"d:\final_I2V\review_tool\work\subbands.json", "w"))

