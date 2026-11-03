"""ASR transcript with faster-whisper (fills SRT gaps > 40s automatically if work/srt_condensed.json exists,
or transcribes full video if --full is passed or SRT is missing).
Output: work/asr.json and work/asr_gaps.txt
"""
import glob, json, os, subprocess, sys, time
import cv2
import torch  # noqa: F401  (loads CUDA libs such as cublas64_12.dll)
os.add_dll_directory(os.path.join(os.path.dirname(torch.__file__), "lib"))
os.environ["PATH"] = os.path.join(os.path.dirname(torch.__file__), "lib") + os.pathsep + os.environ["PATH"]
from faster_whisper import WhisperModel

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FF = os.path.join(ROOT, "tools", "ffmpeg.exe")
WORK = os.path.join(ROOT, "work")
os.makedirs(WORK, exist_ok=True)


def find_video():
    inp_dir = os.path.join(ROOT, "input")
    p1 = os.path.join(inp_dir, "1.mp4")
    if os.path.exists(p1):
        return p1
    cands = sorted(glob.glob(os.path.join(inp_dir, "*.mp4")))
    return cands[0] if cands else os.path.join(ROOT, "1.mp4")


def fmt(s):
    s = int(s)
    return f"{s // 3600:d}:{s % 3600 // 60:02d}:{s % 60:02d}"


SRC = find_video()
OUT = os.path.join(WORK, "asr.json")
GAPS_TXT = os.path.join(WORK, "asr_gaps.txt")
SRT_JSON = os.path.join(WORK, "srt_condensed.json")

args = [a for a in sys.argv[1:] if a != "--full"]
force_full = "--full" in sys.argv[1:]
extra = " ".join(args).strip()
prompt = "以下是普通话的句子，请使用简体中文标点符号。" + (f" {extra}" if extra else "")

t0 = time.time()
model = WhisperModel("large-v3", device="cuda", compute_type="float16")

gaps = []
if not force_full and os.path.exists(SRT_JSON):
    cap = cv2.VideoCapture(SRC)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    dur = cap.get(cv2.CAP_PROP_FRAME_COUNT) / fps
    cap.release()
    subs = json.load(open(SRT_JSON, encoding="utf-8"))
    prev = 0.0
    for st, en, _ in subs:
        if st - prev > 40.0:
            gaps.append((max(0.0, prev - 1.0), min(dur, st + 1.0)))
        prev = max(prev, en)
    if dur - prev > 40.0:
        gaps.append((max(0.0, prev - 1.0), dur))

res = []
if gaps:
    print(f"Running targeted gap ASR on {len(gaps)} gaps...", flush=True)
    gap_lines = []
    tmp_wav = os.path.join(WORK, "_gap_tmp.wav")
    for gi, (ga, gb) in enumerate(gaps):
        subprocess.run(
            [FF, "-y", "-hide_banner", "-loglevel", "error",
             "-ss", f"{ga:.2f}", "-t", f"{gb - ga:.2f}", "-i", SRC,
             "-vn", "-ac", "1", "-ar", "16000", tmp_wav],
            check=True,
        )
        segs, _ = model.transcribe(tmp_wav, language="zh", vad_filter=True, beam_size=5, initial_prompt=prompt)
        gap_lines.append(f"=== GAP {gi + 1}: {fmt(ga)} -> {fmt(gb)} ===")
        for s in segs:
            ast, aen, txt = round(ga + s.start, 2), round(ga + s.end, 2), s.text.strip()
            res.append([ast, aen, txt])
            gap_lines.append(f"[{fmt(ast)}] {txt}")
        print(f"gap {gi + 1}/{len(gaps)} ({fmt(ga)}..{fmt(gb)}) -> {len(res)} total segs", flush=True)
    if os.path.exists(tmp_wav):
        os.remove(tmp_wav)
    open(GAPS_TXT, "w", encoding="utf-8").write("\n".join(gap_lines) + "\n")
else:
    segs, _ = model.transcribe(SRC, language="zh", vad_filter=True, beam_size=5, initial_prompt=prompt)
    for s in segs:
        res.append([round(s.start, 2), round(s.end, 2), s.text.strip()])
        if len(res) % 100 == 0:
            print(len(res), s.end, flush=True)

json.dump(res, open(OUT, "w", encoding="utf-8"), ensure_ascii=False)
print("done", len(res), round(time.time() - t0, 1))
