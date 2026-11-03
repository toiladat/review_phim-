"""Shot boundary detection with PySceneDetect -> work/shots.json [[start,end],...] in seconds."""
import json, time
from scenedetect import open_video, SceneManager
from scenedetect.detectors import ContentDetector

SRC = r"d:\final_I2V\review_tool\1.mp4"
t0 = time.time()
video = open_video(SRC, backend="opencv")
sm = SceneManager()
sm.auto_downscale = False
sm.downscale = 6
sm.add_detector(ContentDetector(threshold=27.0, min_scene_len=8))
sm.detect_scenes(video, show_progress=False)
scenes = sm.get_scene_list()
shots = [[round(a.get_seconds(), 3), round(b.get_seconds(), 3)] for a, b in scenes]
json.dump(shots, open(r"d:\final_I2V\review_tool\work\shots.json", "w"))
print("shots", len(shots), "time", time.time() - t0)

