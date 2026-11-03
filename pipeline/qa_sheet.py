"""QA contact sheets of the final output: one frame per beat (midpoint), labelled.
Automatically adapts thumbnail dimensions for 9:16 vertical vs 16:9 horizontal outputs."""
import cv2, json, numpy as np, os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "output", "review_vi.mp4")
plan = json.load(open(os.path.join(ROOT, "work", "plan.json"), encoding="utf-8"))
cap = cv2.VideoCapture(out)
vw = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)) or 1080
vh = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) or 1920
if vw >= vh:
    TW, TH, COLS, ROWS = 320, 180, 5, 6
else:
    TW, TH, COLS, ROWS = 180, 320, 8, 4

t = 0
frames = []
for p in plan:
    mid = t + p["dur"] * 0.5
    cap.set(cv2.CAP_PROP_POS_MSEC, mid * 1000)
    ok, img = cap.read()
    th = cv2.resize(img, (TW, TH)) if ok else np.zeros((TH, TW, 3), np.uint8)
    cv2.rectangle(th, (0, 0), (60, 26), (0, 0, 0), -1)
    cv2.putText(th, str(p["i"] + 1), (3, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
    frames.append(th)
    t += p["dur"]
os.makedirs(os.path.join(ROOT, "work", "qa"), exist_ok=True)
per = COLS * ROWS
for s in range(0, len(frames), per):
    sheet = np.zeros((ROWS * TH, COLS * TW, 3), np.uint8)
    for k, f in enumerate(frames[s:s + per]):
        r, c = divmod(k, COLS)
        sheet[r * TH:(r + 1) * TH, c * TW:(c + 1) * TW] = f
    cv2.imwrite(os.path.join(ROOT, "work", "qa", f"qa_{s // per + 1}.jpg"), sheet, [cv2.IMWRITE_JPEG_QUALITY, 82])
print("ok")
