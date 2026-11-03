"""Estimate the vertical band where burned-in subtitles appear (supports both 9:16 and 16:9),
generate the feathered alpha mask work/band_mask.png, and save work/video_meta.json."""
import cv2, glob, numpy as np, json, os, random

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
inp_dir = os.path.join(ROOT, "input")
cands = sorted(glob.glob(os.path.join(inp_dir, "*.mp4")))
SRC = os.path.join(inp_dir, "1.mp4") if os.path.exists(os.path.join(inp_dir, "1.mp4")) else (cands[0] if cands else os.path.join(ROOT, "1.mp4"))
WORK = os.path.join(ROOT, "work")
os.makedirs(WORK, exist_ok=True)

cap = cv2.VideoCapture(SRC)
fps = cap.get(cv2.CAP_PROP_FPS) or 29.97
n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
src_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
src_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
is_landscape = src_w >= src_h
W, H = (1920, 1080) if is_landscape else (1080, 1920)
ZOOM = 1.05

random.seed(1)
bands = []
y_min_search = int(src_h * 0.50)  # burned-in subtitles are always in the lower half
y_max_search = int(src_h * 0.96)

for i in range(400):
    t = random.uniform(0, max(1.0, n / fps - 1))
    cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
    ok, img = cap.read()
    if not ok:
        continue
    g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    white = (g > 220).astype(np.uint8)
    dark = cv2.dilate((g < 55).astype(np.uint8), np.ones((7, 7), np.uint8))
    edge = white & dark
    edge[:y_min_search, :] = 0
    edge[y_max_search:, :] = 0
    prof = edge.sum(1)
    ys = np.where(prof > 22)[0]
    if len(ys) > 16:
        groups = np.split(ys, np.where(np.diff(ys) > 15)[0] + 1)
        gbest = max(groups, key=len)
        if len(gbest) > 22:
            bands.append((round(t, 1), int(gbest[0]), int(gbest[-1])))

print(f"source: {src_w}x{src_h} ({'16:9' if is_landscape else '9:16'}), frames with sub: {len(bands)}")

if len(bands) >= 15:
    tops = sorted(b[1] for b in bands)
    bots = sorted(b[2] for b in bands)
    t_pct = [tops[int(len(tops) * p)] for p in (0.02, 0.1, 0.5, 0.9, 0.98)]
    b_pct = [bots[int(len(bots) * p)] for p in (0.02, 0.1, 0.5, 0.9, 0.98)]
    print("top pct", t_pct)
    print("bot pct", b_pct)
    sub_y0 = max(0, t_pct[0] - 20)
    sub_y1 = min(src_h, b_pct[-1] + 22)
    # Convert source coordinates to zoomed target coordinates (W x H)
    zw, zh = round(W * ZOOM / 2) * 2, round(H * ZOOM / 2) * 2
    crop_y = (zh - H) // 2
    scale_y = zh / src_h
    band_y = max(0, int(round(sub_y0 * scale_y - crop_y - 20)))
    band_y2 = min(H, int(round(sub_y1 * scale_y - crop_y + 25)))
    band_h = max(80, ((band_y2 - band_y) // 2) * 2)
    has_hardsub = True
else:
    # Fallback default band in lower region if source has very few/no detected hardsubs
    has_hardsub = len(bands) > 0
    sub_y0, sub_y1 = int(src_h * 0.78), int(src_h * 0.92)
    band_y = int(H * 0.78) if is_landscape else 1215
    band_h = int(H * 0.16) if is_landscape else 430

# Generate feathered alpha mask (work/band_mask.png)
feather = min(42, band_h // 4)
mask = np.full((band_h, W), 255, dtype=np.uint8)
for y in range(feather):
    v = int(round(255 * (y + 1) / feather))
    mask[y, :] = v
    mask[band_h - 1 - y, :] = v
cv2.imwrite(os.path.join(WORK, "band_mask.png"), mask)

meta = {
    "src_w": src_w,
    "src_h": src_h,
    "is_landscape": is_landscape,
    "W": W,
    "H": H,
    "has_hardsub": has_hardsub,
    "sub_y0": int(sub_y0),
    "sub_y1": int(sub_y1),
    "band_y": int(band_y),
    "band_h": int(band_h),
}
json.dump(meta, open(os.path.join(WORK, "video_meta.json"), "w"), indent=2)
json.dump(bands, open(os.path.join(WORK, "subbands.json"), "w"))
print("saved video_meta.json:", meta)
