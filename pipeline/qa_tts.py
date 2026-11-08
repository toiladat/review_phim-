"""QA: transcribe sample narration wavs back to text to verify TTS intelligibility."""
import os, sys, torch
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(os, "add_dll_directory"):
    dll_dir = os.path.join(os.path.dirname(torch.__file__), "lib")
    if os.path.isdir(dll_dir):
        os.add_dll_directory(dll_dir)
from faster_whisper import WhisperModel
sys.path.insert(0, os.path.dirname(__file__))
from script_beats import BEATS

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
n = len(BEATS)
default_ids = sorted(set([1, max(1, n // 4), max(1, n // 2), max(1, 3 * n // 4), n])) if n else []
ids = [int(x) for x in sys.argv[1:]] or default_ids
use_cuda = torch.cuda.is_available()
m = WhisperModel("large-v3", device="cuda" if use_cuda else "cpu", compute_type="float16" if use_cuda else "int8")
for i in ids:
    wav_p = os.path.join(ROOT, "work", "aud", f"{i:03d}.wav")
    segs, _ = m.transcribe(wav_p, language="vi", beam_size=5)
    txt = " ".join(s.text.strip() for s in segs)
    print(f"--- {i}\nSCRIPT: {BEATS[i-1][1]}\nASR   : {txt}", flush=True)
