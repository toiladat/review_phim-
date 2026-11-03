"""Full ASR transcript of the source with faster-whisper (fills SRT gaps)."""
import json, sys, time, os
import torch  # noqa: F401  (loads CUDA libs such as cublas64_12.dll)
os.add_dll_directory(os.path.join(os.path.dirname(torch.__file__), "lib"))
os.environ["PATH"] = os.path.join(os.path.dirname(torch.__file__), "lib") + os.pathsep + os.environ["PATH"]
from faster_whisper import WhisperModel

SRC = r"d:\final_I2V\review_tool\1.mp4"
OUT = r"d:\final_I2V\review_tool\work\asr.json"

t0 = time.time()
model = WhisperModel("large-v3", device="cuda", compute_type="float16")
segs, info = model.transcribe(SRC, language="zh", vad_filter=True, beam_size=5,
                              initial_prompt="以下是普通话的句子。沈欣冉，周贺川，徐露露，徐佳佳，裴既明，刘美兰。")
res = []
for s in segs:
    res.append([round(s.start, 2), round(s.end, 2), s.text.strip()])
    if len(res) % 100 == 0:
        print(len(res), s.end, flush=True)
json.dump(res, open(OUT, "w", encoding="utf-8"), ensure_ascii=False)
print("done", len(res), time.time() - t0)
