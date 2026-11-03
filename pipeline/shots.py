"""Shot boundary detection with PySceneDetect -> work/shots.json [[start,end],...] in seconds.
Uses multi-process chunked detection for long videos (>30 min) for 8x speedup."""
import glob, json, os, time
from concurrent.futures import ProcessPoolExecutor
import cv2
from scenedetect import open_video, SceneManager, FrameTimecode
from scenedetect.detectors import ContentDetector

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
inp_dir = os.path.join(ROOT, "input")
cands = sorted(glob.glob(os.path.join(inp_dir, "*.mp4")))
SRC = os.path.join(inp_dir, "1.mp4") if os.path.exists(os.path.join(inp_dir, "1.mp4")) else (cands[0] if cands else os.path.join(ROOT, "1.mp4"))
WORK = os.path.join(ROOT, "work")
os.makedirs(WORK, exist_ok=True)


def detect_chunk(args):
    src, t_start, t_end, frame_skip = args
    video = open_video(src, backend="opencv")
    fps = video.frame_rate
    start_tc = FrameTimecode(timecode=t_start, fps=fps)
    end_tc = FrameTimecode(timecode=t_end, fps=fps)
    video.seek(start_tc)
    sm = SceneManager()
    sm.auto_downscale = False
    sm.downscale = 8
    sm.add_detector(ContentDetector(threshold=27.0, min_scene_len=8))
    sm.detect_scenes(video, end_time=end_tc, frame_skip=frame_skip, show_progress=False)
    scenes = sm.get_scene_list(start_in_scene=True)
    return [[round(a.get_seconds(), 3), round(b.get_seconds(), 3)] for a, b in scenes]


if __name__ == "__main__":
    t0 = time.time()
    cap = cv2.VideoCapture(SRC)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    dur = cap.get(cv2.CAP_PROP_FRAME_COUNT) / fps
    cap.release()

    n_workers = 8 if dur > 1800 else 1
    frame_skip = 1 if dur > 5400 else 0
    chunk_len = dur / n_workers
    tasks = [(SRC, round(i * chunk_len, 2), round(min(dur, (i + 1) * chunk_len), 2), frame_skip) for i in range(n_workers)]

    shots = []
    if n_workers > 1:
        with ProcessPoolExecutor(n_workers) as ex:
            for part in ex.map(detect_chunk, tasks):
                shots.extend(part)
    else:
        shots = detect_chunk(tasks[0])

    json.dump(shots, open(os.path.join(WORK, "shots.json"), "w"))
    print("shots", len(shots), "time", round(time.time() - t0, 1))
