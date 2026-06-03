import os
import cv2
from pathlib import Path

DATA_PATH = Path("C:/Users/NIKKA/OneDrive/Desktop/Purple Data")

def inspect_video(path):
    cap = cv2.VideoCapture(str(path))
    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = cap.get(cv2.CAP_PROP_FPS) or 15.0
    duration = frame_count / fps
    cap.release()
    print(f"File: {path.name} | Frame Count: {frame_count} | FPS: {fps:.2f} | Duration: {duration:.2f}s")

print("--- Store 1 ---")
store1_dir = DATA_PATH / "Store 1-20260602T101818Z-3-001ec38db8" / "Store 1"
for p in store1_dir.glob("*.mp4"):
    inspect_video(p)

print("\n--- Store 2 ---")
store2_dir = DATA_PATH / "Store 2-20260602T101819Z-3-001099f208" / "Store 2"
for p in store2_dir.glob("*.mp4"):
    inspect_video(p)
