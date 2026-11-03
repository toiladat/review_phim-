"""Contact sheets: one thumbnail every STEP seconds, labelled with timestamp."""
import cv2, numpy as np, os

SRC = r"d:\final_I2V\review_tool\1.mp4"
OUT = r"d:\final_I2V\review_tool\work\sheets"
STEP, COLS, ROWS, TW, TH = 6, 8, 4, 160, 284
os.makedirs(OUT, exist_ok=True)
cap = cv2.VideoCapture(SRC)
dur = cap.get(7) / cap.get(5)
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
        lab = f"{int(t)//60}:{int(t)%60:02d}"
        cv2.rectangle(th, (0, 0), (78, 24), (0, 0, 0), -1)
        cv2.putText(th, lab, (3, 18), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
        r, c = divmod(k, COLS)
        sheet[r * TH:(r + 1) * TH, c * TW:(c + 1) * TW] = th
    t0 = times[si]
    cv2.imwrite(os.path.join(OUT, f"sheet_{int(t0):04d}.jpg"), sheet, [cv2.IMWRITE_JPEG_QUALITY, 80])
    print("sheet", int(t0), flush=True)

