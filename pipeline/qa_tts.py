"""QA: transcribe some narration wavs back to text to verify TTS intelligibility."""
import os, sys, torch
os.add_dll_directory(os.path.join(os.path.dirname(torch.__file__), "lib"))
from faster_whisper import WhisperModel
sys.path.insert(0, os.path.dirname(__file__))
from script_beats import BEATS

ids = [int(x) for x in sys.argv[1:]] or [1, 6, 9, 30, 70, 77, 86, 112]
m = WhisperModel("large-v3", device="cuda", compute_type="float16")
for i in ids:
    segs, _ = m.transcribe(rf"d:\final_I2V\review_tool\work\aud\{i:03d}.wav", language="vi", beam_size=5)
    txt = " ".join(s.text.strip() for s in segs)
    print(f"--- {i}\nSCRIPT: {BEATS[i-1][1]}\nASR   : {txt}", flush=True)

