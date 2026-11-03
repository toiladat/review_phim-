# -*- coding: utf-8 -*-
"""Assemble the Vietnamese review video.

Stages (cached in work/):
  audio  : trim TTS mp3 -> wav, measure durations
  plan   : choose source segments for each beat + detect tight 2D subtitle box per segment
  beats  : render one mp4 per beat (zoom, tight 2D feathered blur over Chinese sub only, video-only)
  final  : concat beats, build pure Vietnamese narration track (no original audio, no burned-in subs/title),
           mux & export output/review_vi.mp4 + output/review_vi.srt + output/kich_ban_review.txt
"""
import glob, json, math, os, re, subprocess, sys, wave
from concurrent.futures import ThreadPoolExecutor
import cv2, numpy as np

sys.path.insert(0, os.path.dirname(__file__))
from script_beats import BEATS, TITLE

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _find_input(ext, default_name):
    inp_dir = os.path.join(ROOT, "input")
    p1 = os.path.join(inp_dir, default_name)
    if os.path.exists(p1):
        return p1
    cands = sorted(glob.glob(os.path.join(inp_dir, f"*.{ext}")))
    return cands[0] if cands else os.path.join(ROOT, default_name)


SRC = _find_input("mp4", "1.mp4")
SRT_PATH = _find_input("srt", "1.srt")
WORK = os.path.join(ROOT, "work")
FF = os.path.join(ROOT, "tools", "ffmpeg.exe")
TTS_DIR = os.path.join(WORK, "tts", "narration")
AUD = os.path.join(WORK, "aud")
SEG = os.path.join(WORK, "beats")
OUT = os.path.join(ROOT, "output")
FPS_NUM, FPS_DEN = 30000, 1001
FPS = FPS_NUM / FPS_DEN
PAUSE = 0.14          # silence between beats (s)
SEG_TARGET = 2.9      # preferred visual segment length (s)
ORIG_VOL = 0.0        # original soundtrack muted (0.0 = pure Vietnamese narration)
BURN_SUBS = False     # do not burn Vietnamese subtitles or title onto the video
BLUR_SUBS = False     # do not blur Chinese hard-subs when False
W, H = 1080, 1920
ZOOM = 1.05
BAND_Y, BAND_H = 1215, 430
HAS_HARDSUB = BLUR_SUBS
META_P = os.path.join(WORK, "video_meta.json")
if os.path.exists(META_P):
    _meta = json.load(open(META_P))
    W, H = _meta.get("W", W), _meta.get("H", H)
    BAND_Y, BAND_H = _meta.get("band_y", BAND_Y), _meta.get("band_h", BAND_H)
    HAS_HARDSUB = _meta.get("has_hardsub", True) and BLUR_SUBS
IS_LANDSCAPE = W >= H
MASK_2D = os.path.join(WORK, "band_mask_2d.png")
MASK_1D = os.path.join(WORK, "band_mask_1d.png")
for d in (AUD, SEG, OUT):
    os.makedirs(d, exist_ok=True)


def ensure_2d_mask():
    """Create 2D and 1D cosine-feathered alpha masks with a wide solid core."""
    mw, mh = 400, 160
    fx, fy = 14, 18
    mx = np.ones(mw, dtype=np.float32)
    my = np.ones(mh, dtype=np.float32)
    for i in range(fx):
        v = 0.5 * (1.0 - math.cos(math.pi * (i + 1) / (fx + 1)))
        mx[i] = v
        mx[mw - 1 - i] = v
    for i in range(fy):
        v = 0.5 * (1.0 - math.cos(math.pi * (i + 1) / (fy + 1)))
        my[i] = v
        my[mh - 1 - i] = v
    mask2d = (np.outer(my, mx) * 255.0).round().astype(np.uint8)
    mask1d = (np.outer(my, np.ones(mw, dtype=np.float32)) * 255.0).round().astype(np.uint8)
    cv2.imwrite(MASK_2D, mask2d)
    cv2.imwrite(MASK_1D, mask1d)


def run(cmd, quiet=True):
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        print("CMD FAILED:", " ".join(cmd)[:2000])
        print(r.stderr[-3000:])
        raise SystemExit(1)
    return r


def ts(s):
    parts = [int(x) for x in s.strip().split(":")]
    if len(parts) == 3:
        return parts[0] * 3600 + parts[1] * 60 + parts[2]
    return parts[0] * 60 + parts[1]


def parse_windows(spec):
    out = []
    for part in spec.split(","):
        a, b = part.split("-")
        out.append((float(ts(a)), float(ts(b))))
    return out


def wav_dur(p):
    with wave.open(p) as w:
        return w.getnframes() / w.getframerate()


# ---------------------------------------------------------------- audio
def stage_audio():
    info = []
    for i in range(len(BEATS)):
        src = os.path.join(TTS_DIR, f"{i + 1}.mp3")
        dst = os.path.join(AUD, f"{i + 1:03d}.wav")
        if not os.path.exists(src):
            raise SystemExit(f"missing TTS {src}")
        if not os.path.exists(dst) or os.path.getmtime(dst) < os.path.getmtime(src):
            af = ("silenceremove=start_periods=1:start_threshold=-48dB:start_silence=0.03,"
                  "areverse,silenceremove=start_periods=1:start_threshold=-48dB:start_silence=0.06,areverse")
            run([FF, "-y", "-i", src, "-af", af, "-ar", "48000", "-ac", "1", dst])
        info.append({"i": i, "wav": dst, "dur": round(wav_dur(dst), 3)})
    json.dump(info, open(os.path.join(WORK, "beats_audio.json"), "w"), indent=1)
    tot = sum(x["dur"] for x in info) + PAUSE * len(info)
    print(f"audio: {len(info)} beats, total {tot / 60:.2f} min")
    return info


# ---------------------------------------------------------------- plan
def load_exclusions():
    subs = json.load(open(os.path.join(WORK, "srt_condensed.json"), encoding="utf-8"))
    ex = []
    for st, en, tx in subs:
        if any(k in tx for k in ("待续", "法续", "佳续", "未完", "剧终", "完结")):
            ex.append((st - 2.0, en + 1.5))
    if os.path.exists(SRT_PATH):
        raw = open(SRT_PATH, encoding="utf-8", errors="ignore").read()
        for blk in re.split(r"\n\s*\n", raw.strip()):
            ls = [x.strip() for x in blk.splitlines() if x.strip()]
            if len(ls) >= 2:
                m = re.match(r"(\d+):(\d+):(\d+)[,.](\d+)\s*-->\s*(\d+):(\d+):(\d+)[,.](\d+)", ls[1] if ls[0].isdigit() else ls[0])
                if m:
                    g = [int(x) for x in m.groups()]
                    t0 = g[0]*3600 + g[1]*60 + g[2] + g[3]/1000.0
                    t1 = g[4]*3600 + g[5]*60 + g[6] + g[7]/1000.0
                    txt = "".join(ls[2:] if ls[0].isdigit() else ls[1:])
                    if any(k in txt for k in ("待续", "法续", "佳续", "未完", "剧终", "完结")) or (len(txt) <= 4 and "续" in txt):
                        ex.append((t0 - 2.2, t1 + 1.5))
    return ex


def subtract(intervals, cuts):
    res = []
    for a, b in intervals:
        segs = [(a, b)]
        for c, d in cuts:
            nxt = []
            for x, y in segs:
                if d <= x or c >= y:
                    nxt.append((x, y))
                else:
                    if c > x:
                        nxt.append((x, c))
                    if d < y:
                        nxt.append((d, y))
            segs = nxt
        res.extend(segs)
    return res


def pieces_for(windows, shots, excl, used, min_len=1.0):
    out = []
    for wa, wb in windows:
        for sa, sb in shots:
            a, b = max(sa + 0.07, wa), min(sb - 0.07, wb)
            if b - a >= min_len:
                out.append((a, b))
    out = subtract(out, excl)
    out = [p for p in out if p[1] - p[0] >= min_len]
    fresh = [p for p in subtract(out, used) if p[1] - p[0] >= min_len]
    return out, fresh


def choose(pieces, D, seg_max=3.6):
    """Pick segments (a, b, speed) from ordered pieces to fill D seconds."""
    L = sum(b - a for a, b in pieces)
    if L <= 0:
        return None
    if L <= D * 1.02:
        speed = max(L / D, 0.62)
        segs = [(a, b, speed) for a, b in pieces]
        got = L / speed
        k = 0
        while got < D - 0.02:
            a, b = pieces[k % len(pieces)]
            segs.append((a, b, speed))
            got += (b - a) / speed
            k += 1
        return segs
    subs = []
    for a, b in pieces:
        n = max(1, math.ceil((b - a) / (seg_max + 1.0)))
        step = (b - a) / n
        for j in range(n):
            subs.append((a + j * step, a + (j + 1) * step))
    caps = [min(b - a, seg_max) for a, b in subs]
    pick = None
    for k in range(1, len(subs) + 1):
        idx = sorted(set(round((j + 0.5) * len(subs) / k - 0.5) for j in range(k)))
        if sum(caps[i] for i in idx) >= D:
            pick = idx
            break
    if pick is None:
        pick = list(range(len(subs)))
        caps = [b - a for a, b in subs]
    lens = [caps[i] for i in pick]
    excess = sum(lens) - D
    while excess > 1e-3:
        room = [max(l - 0.9, 0) for l in lens]
        tr = sum(room)
        if tr <= 1e-6:
            break
        f = min(1.0, excess / tr)
        lens = [l - r * f for l, r in zip(lens, room)]
        excess = sum(lens) - D
    segs = []
    for i, l in zip(pick, lens):
        a, b = subs[i]
        mid = (a + b) / 2
        s = max(a, mid - l / 2)
        segs.append((s, min(b, s + l), 1.0))
    tot = sum(e - s for s, e, _ in segs)
    if tot < D - 0.02:
        sp = max(tot / D, 0.62)
        segs = [(s, e, sp) for s, e, _ in segs]
    return segs


def _expected_y_zoomed(t):
    if IS_LANDSCAPE:
        return (min(int(H * 0.74), max(0, BAND_Y - 10)),
                max(int(H * 0.96), min(H, BAND_Y + BAND_H + 10)))
    return (min(1235, max(0, BAND_Y - 10)),
            max(1618, min(H, BAND_Y + BAND_H + 10)))


def _detect_sub_zoomed(zimg, t):
    ya, yb = _expected_y_zoomed(t)
    x_margin = 12
    roi = zimg[ya:yb, x_margin:W - x_margin]
    g = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    white = (g > 195).astype(np.uint8)
    dark = cv2.dilate((g < 95).astype(np.uint8), np.ones((7, 7), np.uint8))
    edge = white & dark
    n, lab, stats, _ = cv2.connectedComponentsWithStats(edge, 8)
    valid = np.zeros_like(edge)
    for i in range(1, n):
        x, y, w, h, area = stats[i]
        if 4 <= area <= 3500 and w < 150 and h < 125:
            valid[lab == i] = 1
    prof = valid.sum(1)
    ys = np.where(prof > 5)[0]
    if len(ys) < 7:
        return None
    groups = np.split(ys, np.where(np.diff(ys) > 18)[0] + 1)
    gbest = max(groups, key=len)
    if len(gbest) < 9 or len(gbest) > 220:
        return None
    y0, y1 = int(gbest[0]) + ya, int(gbest[-1]) + ya
    sub_slice = valid[gbest[0]:gbest[-1] + 1, :]
    xs = np.where(sub_slice.sum(0) > 1)[0]
    if len(xs) < 8:
        return None
    x0, x1 = int(xs[0]) + x_margin, int(xs[-1]) + x_margin
    return (x0, y0, x1, y1)


def detect_all_seg_boxes(plan):
    """Multi-threaded detection of tight 2D subtitle bounding box for every segment in plan."""
    zw, zh = round(W * ZOOM / 2) * 2, round(H * ZOOM / 2) * 2
    cx, cy = (zw - W) // 2, (zh - H) // 2

    srt_lines = []
    srt_p = SRT_PATH
    if os.path.exists(srt_p):
        raw_srt = open(srt_p, encoding="utf-8", errors="ignore").read()
        for blk in re.split(r"\n\s*\n", raw_srt.strip()):
            ls = [x.strip() for x in blk.splitlines() if x.strip()]
            if len(ls) >= 2:
                m = re.match(r"(\d+):(\d+):(\d+)[,.](\d+)\s*-->\s*(\d+):(\d+):(\d+)[,.](\d+)", ls[1] if ls[0].isdigit() else ls[0])
                if m:
                    g = [int(x) for x in m.groups()]
                    t0 = g[0]*3600 + g[1]*60 + g[2] + g[3]/1000.0
                    t1 = g[4]*3600 + g[5]*60 + g[6] + g[7]/1000.0
                    txt = "\n".join(ls[2:] if ls[0].isdigit() else ls[1:])
                    srt_lines.append((t0, t1, txt))

    tasks = []
    for p in plan:
        for k, s in enumerate(p["segs"]):
            tasks.append((p["i"], k, s[0], s[1]))

    def worker(chunk):
        cap = cv2.VideoCapture(SRC)
        out = []
        for bi, sk, a, b in chunk:
            boxes = []
            for frac in (0.08, 0.22, 0.36, 0.50, 0.64, 0.78, 0.92):
                t = a + (b - a) * frac
                cap.set(cv2.CAP_PROP_POS_MSEC, float(t) * 1000.0)
                ok, img = cap.read()
                if ok and img is not None:
                    zimg = cv2.resize(img, (zw, zh), interpolation=cv2.INTER_LINEAR)[cy:cy + H, cx:cx + W]
                    bx = _detect_sub_zoomed(zimg, t)
                    if bx is not None:
                        boxes.append(bx)
            max_ch = 0
            for t0, t1, txt in srt_lines:
                if t1 >= a - 0.12 and t0 <= b + 0.12:
                    for l in txt.splitlines():
                        max_ch = max(max_ch, len(l.strip()))
            out.append((bi, sk, a, b, boxes, max_ch))
        cap.release()
        return out

    n_workers = 8
    chunks = [tasks[i::n_workers] for i in range(n_workers)]
    raw_res = []
    with ThreadPoolExecutor(n_workers) as ex:
        for res in ex.map(worker, chunks):
            raw_res.extend(res)
    raw_res.sort(key=lambda x: (x[0], x[1]))

    # Collect valid (t_mid, y0, y1) anchors from detected boxes for clean vertical interpolation
    y_anchors = []
    for bi, sk, a, b, boxes, max_ch in raw_res:
        if boxes:
            y0 = int(np.median([b_[1] for b_ in boxes]))
            y1 = int(np.median([b_[3] for b_ in boxes]))
            if y1 - y0 >= 38:
                y_anchors.append(((a + b) * 0.5, y0, y1))

    def interp_y(t_mid):
        if not y_anchors:
            return (BAND_Y + 25, BAND_Y + min(95, BAND_H - 25))
        nearest = min(y_anchors, key=lambda x: abs(x[0] - t_mid))
        return (nearest[1], nearest[2])

    char_px = 54 if IS_LANDSCAPE else 72
    for bi, sk, a, b, boxes, max_ch in raw_res:
        if boxes or max_ch > 0:
            if boxes:
                x0 = min(b_[0] for b_ in boxes)
                y0 = int(np.median([b_[1] for b_ in boxes]))
                x1 = max(b_[2] for b_ in boxes)
                y1 = int(np.median([b_[3] for b_ in boxes]))
                if y1 - y0 < 56:
                    ny0, ny1 = interp_y((a + b) * 0.5)
                    y0 = min(y0, ny0)
                    y1 = max(y1, ny1)
            else:
                y0, y1 = interp_y((a + b) * 0.5)
                x0, x1 = W // 2 - 120, W // 2 + 120
            est_w = min(W, max_ch * char_px)
            if est_w > (x1 - x0):
                x_mid = (x0 + x1) // 2
                x0 = max(0, x_mid - est_w // 2)
                x1 = min(W, x_mid + est_w // 2)
            pad_x, pad_y = 66, 24
            bx0 = 0 if (x0 - pad_x <= 36) else ((x0 - pad_x) // 2) * 2
            bx1 = W if (x1 + pad_x >= W - 36) else ((x1 + pad_x + 1) // 2) * 2
            by0 = max(0, ((y0 - pad_y) // 2) * 2)
            by1 = min(H, ((y1 + pad_y + 1) // 2) * 2)
            box = [int(bx0), int(by0), int(bx1 - bx0), int(by1 - by0)]
        else:
            box = None
        s = list(plan[bi]["segs"][sk][:3])
        s.append(box)
        plan[bi]["segs"][sk] = s


def stage_plan(info):
    shots = json.load(open(os.path.join(WORK, "shots.json")))
    flags_p = os.path.join(WORK, "shot_flags.json")
    clean = shots
    if os.path.exists(flags_p):
        flags = json.load(open(flags_p))
        clean = [s for s, f in zip(shots, flags) if not any(x[0] >= 1500 for x in f)]
        print(f"shots: {len(shots)}, without overlay text: {len(clean)}")
    excl = load_exclusions()
    used = []
    plan = []
    for (spec, text), ai in zip(BEATS, info):
        D = ai["dur"] + PAUSE
        nfr = round(D * FPS)
        D = nfr / FPS
        windows = parse_windows(spec)
        allc, freshc = pieces_for(windows, clean, excl, used)
        alls, fresh_s = pieces_for(windows, shots, excl, used)
        tot = lambda ps: sum(b - a for a, b in ps)
        for cand in (freshc, allc, fresh_s, alls):
            if tot(cand) >= D * 0.75:
                use = cand
                break
        else:
            use = max((freshc, allc, fresh_s, alls), key=tot)
        segs = choose(use, D)
        if not segs:
            raise SystemExit(f"no visuals for beat {ai['i'] + 1}: {spec}")
        used.extend((a, b) for a, b, _ in segs)
        plan.append({"i": ai["i"], "dur": D, "frames": nfr, "wav": ai["wav"], "audio_dur": ai["dur"],
                     "text": text, "segs": [list(s) for s in segs]})
    if HAS_HARDSUB:
        print("detecting tight 2D subtitle boxes per segment...", flush=True)
        detect_all_seg_boxes(plan)
    json.dump(plan, open(os.path.join(WORK, "plan.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    slow = [p["i"] + 1 for p in plan if any(s[2] < 0.95 for s in p["segs"])]
    print(f"plan ok; beats with slow-motion fill: {slow}")
    return plan


# ---------------------------------------------------------------- render beats
def vchain():
    zw, zh = round(W * ZOOM / 2) * 2, round(H * ZOOM / 2) * 2
    return (f"scale={zw}:{zh}:flags=lanczos,crop={W}:{H}:{(zw - W) // 2}:{(zh - H) // 2},setsar=1")


def render_beat(p, force=False):
    out = os.path.join(SEG, f"{p['i'] + 1:03d}.mp4")
    is_first = (p["i"] == 0)
    is_last = (p["i"] == len(BEATS) - 1)
    sig = json.dumps([p["segs"], p["frames"], ZOOM, ORIG_VOL, "tight2d_v3", is_first, is_last])
    sigf = out + ".sig"
    if not force and os.path.exists(out) and os.path.exists(sigf) and open(sigf).read() == sig:
        return out
    cmd = [FF, "-y", "-hide_banner", "-loglevel", "error"]
    fc = []
    n = len(p["segs"])
    for k, seg in enumerate(p["segs"]):
        a, b, sp = seg[0], seg[1], seg[2]
        cmd += ["-ss", f"{a:.3f}", "-t", f"{b - a:.3f}", "-i", SRC]
    # Add 2D feathered mask input at index n and 1D mask at index n+1
    cmd += ["-loop", "1", "-i", MASK_2D, "-loop", "1", "-i", MASK_1D]

    for k, seg in enumerate(p["segs"]):
        a, b, sp = seg[0], seg[1], seg[2]
        box = seg[3] if len(seg) > 3 else None
        vf = f"[{k}:v]{vchain()},fps={FPS_NUM}/{FPS_DEN}"
        if sp < 0.999:
            vf += f",setpts=PTS/{sp:.4f}"
        vf += ",setpts=PTS-STARTPTS"
        if HAS_HARDSUB and box is not None:
            bx, by, bw, bh = box
            lr = max(8, min(32, bw // 4 - 1, bh // 3 - 1))
            cr = max(4, min(16, bw // 8 - 1, bh // 6 - 1))
            m_idx = (n + 1) if bw >= W else n
            fc.append(f"{vf},split[vb{k}][vt{k}]")
            fc.append(f"[{m_idx}:v]format=gray,scale={bw}:{bh}[mk{k}]")
            fc.append(f"[vt{k}]crop={bw}:{bh}:{bx}:{by},"
                      f"boxblur=luma_radius={lr}:luma_power=3:chroma_radius={cr}:chroma_power=2,"
                      f"format=yuva420p[bl0_{k}];[bl0_{k}][mk{k}]alphamerge[bl{k}];"
                      f"[vb{k}][bl{k}]overlay={bx}:{by}:shortest=1,format=yuv420p[v{k}]")
        else:
            fc.append(f"{vf},format=yuv420p[v{k}]")

    v_concat = "".join(f"[v{k}]" for k in range(n)) + f"concat=n={n}:v=1:a=0,tpad=stop_mode=clone:stop_duration=2"
    if is_first:
        v_concat += ",fade=t=in:st=0:d=0.5"
    if is_last:
        v_concat += f",fade=t=out:st={max(0.0, p['dur'] - 1.2):.2f}:d=1.2"
    fc.append(v_concat + ",format=yuv420p[vo]")

    cmd += ["-filter_complex", ";".join(fc), "-map", "[vo]", "-an",
            "-frames:v", str(p["frames"]), "-t", f"{p['dur']:.4f}", "-r", f"{FPS_NUM}/{FPS_DEN}",
            "-c:v", "h264_nvenc", "-preset", "p5", "-rc", "vbr", "-cq", "19", "-b:v", "0", "-g", "60",
            "-pix_fmt", "yuv420p", out]
    run(cmd)
    open(sigf, "w").write(sig)
    return out


def stage_beats(plan, only=None):
    ensure_2d_mask()
    todo = [p for p in plan if only is None or p["i"] + 1 in only]
    with ThreadPoolExecutor(3) as ex:
        for k, o in enumerate(ex.map(render_beat, todo)):
            if k % 10 == 0 or k + 1 == len(todo):
                print("rendered", k + 1, "/", len(todo), flush=True)


# ---------------------------------------------------------------- subtitles
def split_chunks(text, maxlen=None):
    if maxlen is None:
        maxlen = 82 if IS_LANDSCAPE else 58
    parts = re.split(r"(?<=[,.:;?!])\s+", text.strip())
    chunks = []
    cur = ""
    for p in parts:
        if not cur:
            cur = p
        elif len(cur) + 1 + len(p) <= maxlen:
            cur += " " + p
        else:
            chunks.append(cur)
            cur = p
    if cur:
        chunks.append(cur)
    res = []
    for c in chunks:
        while len(c) > maxlen + 12:
            cut = c.rfind(" ", 0, maxlen)
            res.append(c[:cut])
            c = c[cut + 1:]
        res.append(c)
    return res


def wrap2(c, maxline=None):
    if maxline is None:
        maxline = 44 if IS_LANDSCAPE else 30
    if len(c) <= maxline:
        return c
    words = c.split()
    best, bi = 1e9, 1
    for i in range(1, len(words)):
        l1 = len(" ".join(words[:i])); l2 = len(" ".join(words[i:]))
        if max(l1, l2) < best:
            best, bi = max(l1, l2), i
    return " ".join(words[:bi]) + "\\N" + " ".join(words[bi:])


def ass_time(t):
    t = max(t, 0)
    h = int(t // 3600); m = int(t % 3600 // 60); s = t % 60
    return f"{h}:{m:02d}:{s:05.2f}"


def srt_time(t):
    ms = round(max(t, 0) * 1000)
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def build_ass_and_srt(plan, ass_path, srt_path, script_path):
    sub_fs = 48 if IS_LANDSCAPE else 64
    head = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Sub,Roboto,{sub_fs},&H00FFFFFF,&H00FFFFFF,&H00000000,&H96000000,1,0,0,0,100,100,0,0,1,5,2,5,40,40,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    ev = []
    srt_blocks = []
    idx = 1
    t0 = 0.0
    for p in plan:
        chunks = split_chunks(p["text"])
        weights = [max(len(c.split()), 1) + 0.6 * len(re.findall(r"[,.:;?!]", c)) for c in chunks]
        tot = sum(weights)
        t = t0
        for c, w_ in zip(chunks, weights):
            d = p["audio_dur"] * w_ / tot
            ev.append(f"Dialogue: 0,{ass_time(t)},{ass_time(t + d)},Sub,,0,0,0,,{{\\an5\\pos({W // 2},{BAND_Y + BAND_H // 2})}}{wrap2(c)}")
            srt_blocks.append(f"{idx}\n{srt_time(t)} --> {srt_time(t + d)}\n{c}\n")
            idx += 1
            t += d
        t0 += p["dur"]
    open(ass_path, "w", encoding="utf-8-sig").write(head + "\n".join(ev) + "\n")
    open(srt_path, "w", encoding="utf-8").write("\n".join(srt_blocks))
    open(script_path, "w", encoding="utf-8").write("\n\n".join(f"[{p['i'] + 1:03d}] {p['text']}" for p in plan) + "\n")
    return t0


# ---------------------------------------------------------------- final
def stage_final(plan, name="review_vi.mp4"):
    # 1) concat beat videos
    lst = os.path.join(WORK, "beats_list.txt")
    with open(lst, "w", encoding="utf-8") as f:
        for p in plan:
            bp = os.path.join(SEG, "%03d.mp4" % (p["i"] + 1)).replace("\\", "/")
            f.write(f"file '{bp}'\n")
    joined = os.path.join(WORK, "joined.mp4")
    run([FF, "-y", "-hide_banner", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", joined])

    # 2) narration track, each beat padded/trimmed to exact beat length (sample accurate, pure python)
    nar = os.path.join(WORK, "narration_full.wav")
    with wave.open(nar, "wb") as wo:
        wo.setnchannels(1); wo.setsampwidth(2); wo.setframerate(48000)
        t_samples = 0
        t_exact = 0.0
        for p in plan:
            with wave.open(p["wav"]) as wi:
                assert wi.getframerate() == 48000 and wi.getnchannels() == 1 and wi.getsampwidth() == 2
                data = wi.readframes(wi.getnframes())
            t_exact += p["dur"]
            need = round(t_exact * 48000) - t_samples
            data = data[:need * 2] + b"\x00\x00" * max(0, need - len(data) // 2)
            wo.writeframes(data)
            t_samples += need

    # 3) generate ASS/SRT/script files on disk, and mux video + pure Vietnamese narration audio
    ass = os.path.join(WORK, "subs_vi.ass")
    srt_out = os.path.join(OUT, "review_vi.srt")
    txt_out = os.path.join(OUT, "kich_ban_review.txt")
    total = build_ass_and_srt(plan, ass, srt_out, txt_out)
    out = os.path.join(OUT, name)
    af = (f"[1:a]aformat=channel_layouts=stereo,volume=1.0,"
          f"acompressor=threshold=-18dB:ratio=3:attack=5:release=120,"
          f"loudnorm=I=-15:TP=-1.5:LRA=11,afade=t=out:st={total - 1.2:.2f}:d=1.2[a]")
    if BURN_SUBS:
        ass_ff = ass.replace("\\", "/").replace(":", "\\:")
        fonts_ff = "C\\:/Windows/Fonts"
        vf = f"subtitles='{ass_ff}':fontsdir='{fonts_ff}'"
        run([FF, "-y", "-hide_banner", "-loglevel", "error", "-i", joined, "-i", nar, "-vf", vf,
             "-filter_complex", af, "-map", "0:v", "-map", "[a]",
             "-c:v", "h264_nvenc", "-preset", "p6", "-rc", "vbr", "-cq", "20", "-b:v", "0", "-maxrate", "16M", "-bufsize", "32M",
             "-profile:v", "high", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
             "-movflags", "+faststart", out])
    else:
        # Pure video copy (no burned-in Vietnamese subs or title) + pure Vietnamese narration audio
        run([FF, "-y", "-hide_banner", "-loglevel", "error", "-i", joined, "-i", nar,
             "-filter_complex", af, "-map", "0:v", "-map", "[a]",
             "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
             "-movflags", "+faststart", out])
    print(f"FINAL: {out}  ({total / 60:.2f} min)")
    return out


if __name__ == "__main__":
    stages = sys.argv[1:] or ["audio", "plan", "beats", "final"]
    info = stage_audio() if "audio" in stages else json.load(open(os.path.join(WORK, "beats_audio.json")))
    plan = stage_plan(info) if "plan" in stages else json.load(open(os.path.join(WORK, "plan.json"), encoding="utf-8"))
    if "beats" in stages:
        stage_beats(plan)
    if "final" in stages:
        stage_final(plan)
