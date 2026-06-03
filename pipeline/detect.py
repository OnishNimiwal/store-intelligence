"""CCTV detection + tracking pipeline. Uses YOLO when available; falls back to simulation."""
import argparse
import json
import os
import random
import sys
from datetime import datetime, timedelta
from pathlib import Path

import cv2

from pipeline.emit import EventEmitter
from pipeline.tracker import RetailTracker


def parse_args():
    parser = argparse.ArgumentParser(description="Store Intelligence detection pipeline")
    parser.add_argument("--video", type=str, help="Path to CCTV clip (.mp4)")
    parser.add_argument("--store-layout", type=str, default="store_layout.json")
    parser.add_argument("--store-id", type=str, default="STORE_BLR_002")
    parser.add_argument("--camera-id", type=str, default="CAM_ENTRY_01")
    parser.add_argument("--output", type=str, default="data/out/events.jsonl")
    parser.add_argument("--clip-start", type=str, default="2026-03-03T14:00:00Z")
    parser.add_argument("--simulate", action="store_true", help="Force simulation mode")
    parser.add_argument("--append", action="store_true", help="Append to output JSONL instead of overwriting")
    parser.add_argument("--max-frames", type=int, default=0, help="Stop after N frames (0 = full clip)")
    parser.add_argument("--frame-skip", type=int, default=2, help="Process every Nth frame")
    parser.add_argument("--format", type=str, choices=["format1", "format2"], default="format2", help="Event schema format")
    return parser.parse_args()


def point_in_polygon(x: float, y: float, poly: list) -> bool:
    inside = False
    n = len(poly)
    p1x, p1y = poly[0]
    for i in range(n + 1):
        p2x, p2y = poly[i % n]
        if y > min(p1y, p2y):
            if y <= max(p1y, p2y):
                if x <= max(p1x, p2x):
                    if p1y != p2y:
                        xinters = (y - p1y) * (p2x - p1x) / (p2y - p1y) + p1x
                    if p1x == p2x or x <= xinters:
                        inside = not inside
        p1x, p1y = p2x, p2y
    return inside


def load_layout(layout_path: str, store_id: str) -> dict:
    path = Path(layout_path)
    if not path.exists():
        return {"store_id": store_id, "zones": []}
    with open(path, encoding="utf-8") as handle:
        data = json.load(handle)
    if isinstance(data, list):
        for layout in data:
            if layout.get("store_id") == store_id:
                return layout
    elif isinstance(data, dict) and data.get("store_id") == store_id:
        return data
    return {"store_id": store_id, "zones": []}


def parse_clip_start(clip_start: str) -> datetime:
    return datetime.fromisoformat(clip_start.replace("Z", "+00:00")).replace(tzinfo=None)


def run_yolo_tracking(cap, model, fps, clip_start, args, emitter, tracker, zones):
    frame_idx = 0
    processed = 0
    skip = max(1, args.frame_skip)
    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break
        frame_idx += 1
        if frame_idx % skip != 0:
            continue
        if args.max_frames and processed >= args.max_frames:
            break
        processed += 1
        height, width = frame.shape[:2]
        results = model.track(frame, persist=True, classes=[0], verbose=False)
        if results[0].boxes is None or results[0].boxes.id is None:
            continue
        track_ids = results[0].boxes.id.int().cpu().tolist()
        boxes = results[0].boxes.xyxy.cpu().tolist()
        tracks = list(zip(track_ids, boxes))
        
        timestamp = clip_start + timedelta(seconds=frame_idx / fps)
        actions = tracker.update_tracks(
            tracks,
            frame=frame,
            zones=zones,
            timestamp=timestamp,
            camera_id=args.camera_id,
        )
        
        for action in actions:
            event = emitter.build_event(
                camera_id=args.camera_id,
                visitor_id=action["visitor_id"],
                event_type=action["event_type"],
                timestamp=timestamp,
                zone_id=action.get("zone_id"),
                dwell_ms=action.get("dwell_ms", 0),
                is_staff=action["is_staff"],
                confidence=0.9,
                queue_depth=action.get("queue_depth"),
                sku_zone=action.get("sku_zone"),
                session_seq=action["session_seq"],
            )
            emitter.emit(event, output_file=args.output)


def simulate_events(args, emitter: EventEmitter) -> None:
    clip_start = parse_clip_start(args.clip_start)
    visitors = [f"VIS_{i:04d}" for i in range(1, 26)]
    sku_map = {"SKINCARE": "MOISTURISER", "COSMETICS": "LIPSTICK", "BILLING": "CHECKOUT"}
    seq = 0
    for i, visitor in enumerate(visitors):
        is_staff = i % 7 == 0
        t = clip_start + timedelta(minutes=i * 2)
        seq += 1
        emitter.emit(
            emitter.build_event(
                "CAM_ENTRY_01", visitor, "ENTRY", t, confidence=0.94, session_seq=seq, is_staff=is_staff
            ),
            args.output,
        )
        zone = "SKINCARE" if i % 2 == 0 else "COSMETICS"
        t += timedelta(seconds=45)
        seq += 1
        emitter.emit(
            emitter.build_event(
                "CAM_FLOOR_02",
                visitor,
                "ZONE_ENTER",
                t,
                zone_id=zone,
                confidence=0.88,
                sku_zone=sku_map[zone],
                session_seq=seq,
                is_staff=is_staff,
            ),
            args.output,
        )
        t += timedelta(seconds=35)
        seq += 1
        emitter.emit(
            emitter.build_event(
                "CAM_FLOOR_02",
                visitor,
                "ZONE_DWELL",
                t,
                zone_id=zone,
                dwell_ms=30000,
                confidence=0.91,
                sku_zone=sku_map[zone],
                session_seq=seq,
                is_staff=is_staff,
            ),
            args.output,
        )
        if not is_staff and i % 3 != 0:
            t += timedelta(minutes=3)
            seq += 1
            emitter.emit(
                emitter.build_event(
                    "CAM_BILLING_03",
                    visitor,
                    "BILLING_QUEUE_JOIN",
                    t,
                    zone_id="BILLING",
                    confidence=0.95,
                    queue_depth=random.randint(1, 6),
                    session_seq=seq,
                ),
                args.output,
            )
        t += timedelta(minutes=1)
        seq += 1
        emitter.emit(
            emitter.build_event(
                "CAM_ENTRY_01", visitor, "EXIT", t, confidence=0.93, session_seq=seq, is_staff=is_staff
            ),
            args.output,
        )
    print(f"[*] Simulated events written to {args.output}")


def main():
    args = parse_args()
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    if not args.append and Path(args.output).exists():
        Path(args.output).unlink()

    emitter = EventEmitter(store_id=args.store_id, schema_format=args.format)
    tracker = RetailTracker(entry_line_y=0.85)
    layout = load_layout(args.store_layout, args.store_id)
    zones = layout.get("zones", [])

    use_simulate = args.simulate or not args.video or not Path(args.video).exists()
    if use_simulate:
        print("[*] Running simulation mode (no video or --simulate).")
        simulate_events(args, emitter)
        return

    cap = cv2.VideoCapture(args.video)
    fps = cap.get(cv2.CAP_PROP_FPS) or 15.0
    clip_start = parse_clip_start(args.clip_start)

    try:
        from ultralytics import YOLO
    except ImportError:
        cap.release()
        print(
            "[!] ultralytics required for real video. Run: pip install -r requirements-pipeline.txt",
            file=sys.stderr,
        )
        sys.exit(1)

    model = YOLO("yolov8n.pt")
    print(f"[*] YOLOv8 + ByteTrack: {args.video} (fps={fps:.1f}, skip={args.frame_skip})")
    try:
        run_yolo_tracking(cap, model, fps, clip_start, args, emitter, tracker, zones)
    finally:
        cap.release()
    print(f"[*] Events written to {args.output}")


if __name__ == "__main__":
    main()
