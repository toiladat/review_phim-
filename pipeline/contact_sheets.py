"""Contact sheets: one thumbnail every STEP seconds, labelled with timestamp.
Automatically adapts grid/thumbnail aspect ratio and STEP for long videos."""
import cv2, glob, numpy as np, os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
inp_dir = os.path.join(ROOT, "input")
cands = sorted(glob.glob(os.path.join(inp_dir, "*.mp4")))
SRC = os.path.join(inp_dir, "1.mp4") if os.path.exists(os.path.join(inp_dir, "1.mp4")) else (cands[0] if cands else os.path.join(ROOT, "1.mp4"))
OUT = os.path.join(ROOT, "work", "sheets")
os.makedirs(OUT, exist_ok=True)
cap = cv2.VideoCapture(SRC)
dur = cap.get(cv2.CAP_PROP_FRAME_COUNT) / (cap.get(cv2.CAP_PROP_FPS) or 29.97)
src_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
src_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

STEP = max(6, int(round(dur / 680.0)))
if src_w >= src_h:  # 16:9 horizontal
    COLS, ROWS, TW, TH = 5, 6, 284, 160
else:               # 9:16 vertical
    COLS, ROWS, TW, TH = 8, 4, 160, 284

per = COLS * ROWS
times = np.arange(1, dur, STEP)
for si in range(0, len(times), per):
    sheet = np.zeros((ROWS * TH, COLS * TW, 3), np.uint8)
    for k, t in enumerate(times[si:si + per]):
        cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
        ok, img = cap.read()
        if not ok:
            continue
        th = cv2.resize(img, (TW, TH), interpolation=cv2.INTER_AREA)
        ti = int(t)
        lab = f"{ti//3600}:{(ti%3600)//60:02d}:{ti%60:02d}" if dur >= 3600 else f"{ti//60}:{ti%60:02d}"
        cv2.rectangle(th, (0, 0), (96 if dur >= 3600 else 78, 24), (0, 0, 0), -1)
        cv2.putText(th, lab, (3, 18), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 255), 2)
        r, c = divmod(k, COLS)
        sheet[r * TH:(r + 1) * TH, c * TW:(c + 1) * TW] = th
    t0 = times[si]
    cv2.imwrite(os.path.join(OUT, f"sheet_{int(t0):05d}.jpg"), sheet, [cv2.IMWRITE_JPEG_QUALITY, 80])
    print("sheet", int(t0), flush=True)
