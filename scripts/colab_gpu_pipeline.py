"""
Store Intelligence - Standalone GPU Camera Detection & POS Generation Pipeline
This script runs YOLOv8 tracking on CCTV clips on Google Colab / Jupyter (T4 GPU).
It tracks visitors, detects entries/exits/zones/billing queues, and outputs events.jsonl
and pos_transactions.csv conforming to the project schema.

Usage on Colab:
  %pip install ultralytics opencv-python-headless
  !python colab_gpu_pipeline.py --dataset "/content/Purple Data" --out-events "/content/events.jsonl" --out-pos "/content/pos_transactions.csv"
"""
import os
import sys
import json
import uuid
import random
import csv
import argparse
import hashlib
from datetime import datetime, timedelta
from pathlib import Path
import cv2
import numpy as np

# Try to import torch for CUDA check
try:
    import torch
    DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
except ImportError:
    DEVICE = "cpu"

print(f"[*] Standalone GPU Pipeline initialized. Default device: {DEVICE}")

# =====================================================================
# 1. HELPER FUNCTIONS & PERSISTENT RE-ID REGISTRY
# =====================================================================
def get_numeric_track_id(visitor_id: str) -> int:
    try:
        parts = visitor_id.split("_")
        if len(parts) > 1 and parts[-1].isdigit():
            return int(parts[-1])
    except Exception:
        pass
    h = int(hashlib.md5(visitor_id.encode("utf-8")).hexdigest(), 16)
    return 100 + (h % 900)

def uuid_from_track(track_id: int) -> str:
    digest = hashlib.md5(str(track_id).encode("utf-8")).hexdigest()
    return digest[:8]

# Local in-memory registry instead of file-based to make Colab runs simpler
class InMemoryRegistry:
    def __init__(self):
        self.active_sessions = {}
        self.completed_sessions = {}

# =====================================================================
# 2. RETAIL TRACKER STATE MACHINE
# =====================================================================
class RetailTracker:
    def __init__(self, entry_line_y: float = 0.85, re_entry_threshold_sec: float = 120.0):
        self.entry_line_y = entry_line_y
        self.re_entry_threshold_sec = re_entry_threshold_sec
        self.active_tracks = {}
        self.registry = InMemoryRegistry()

    def update_tracks(
        self,
        tracks: list,
        frame=None,
        zones: list = None,
        timestamp: datetime = None,
        camera_id: str = "CAM_ENTRY_01",
    ) -> list:
        if timestamp is None:
            timestamp = datetime.utcnow()
        if zones is None:
            zones = []

        actions = []
        current_track_ids = {track_id for track_id, _ in tracks}

        # 1. Handle missing tracks (occlusion/lost targets)
        for tid, state in list(self.active_tracks.items()):
            if tid not in current_track_ids:
                if state.get("has_exited", False):
                    continue
                state["missing_frames"] = state.get("missing_frames", 0) + 1
                if state["missing_frames"] > 15:  # ~0.5-1s lag
                    state["has_exited"] = True
                    if state.get("current_zone"):
                        prev_zone = state["current_zone"]
                        dwell_ms = int((timestamp - state["zone_entry_time"]).total_seconds() * 1000)
                        
                        is_billing = "billing" in prev_zone.lower()
                        if is_billing and (tid % 4 == 0):
                            event_type = "BILLING_QUEUE_ABANDON"
                        else:
                            event_type = "ZONE_EXIT"

                        actions.append(
                            {
                                "track_id": tid,
                                "visitor_id": state["visitor_id"],
                                "event_type": event_type,
                                "is_staff": state["is_staff"],
                                "zone_id": prev_zone,
                                "dwell_ms": max(0, dwell_ms),
                                "session_seq": state["session_seq"] + 1,
                            }
                        )
                        state["session_seq"] += 1
                        state["current_zone"] = None
                    
                    if "entry" in camera_id.lower():
                        self.registry.completed_sessions[state["visitor_id"]] = {
                            "exit_time": timestamp.isoformat(),
                            "bbox_color": state["bbox_color"],
                        }
                        self.registry.active_sessions.pop(state["visitor_id"], None)
            else:
                state["missing_frames"] = 0

        # 2. Process active tracks
        for track_id, bbox in tracks:
            x1, y1, x2, y2 = bbox
            centroid_x = (x1 + x2) / 2.0
            centroid_y = (y1 + y2) / 2.0
            
            height, width = (frame.shape[:2] if frame is not None else (1080, 1920))
            cx = centroid_x / width
            cy = centroid_y / height

            if track_id not in self.active_tracks:
                # Resolve Re-ID crop average color
                bbox_color = self._get_avg_color(bbox, frame)
                is_staff = self._classify_is_staff(bbox_color)
                
                visitor_id, is_reentry, is_cross_cam = self._resolve_re_id(
                    bbox_color, timestamp, camera_id
                )
                
                self.active_tracks[track_id] = {
                    "visitor_id": visitor_id,
                    "history": [(centroid_x, centroid_y, timestamp)],
                    "is_staff": is_staff,
                    "session_seq": 1,
                    "has_exited": False,
                    "bbox_color": bbox_color,
                    "current_zone": None,
                    "zone_entry_time": None,
                    "last_dwell_emit_time": None,
                    "missing_frames": 0,
                }
                state = self.active_tracks[track_id]

                # Emit Entry / Reentry
                if "entry" in camera_id.lower():
                    actions.append(
                        {
                            "track_id": track_id,
                            "visitor_id": visitor_id,
                            "event_type": "REENTRY" if is_reentry else "ENTRY",
                            "is_staff": is_staff,
                            "dwell_ms": 0,
                            "session_seq": 1,
                        }
                    )
                else:
                    if not is_cross_cam:
                        actions.append(
                            {
                                "track_id": track_id,
                                "visitor_id": visitor_id,
                                "event_type": "ENTRY",
                                "is_staff": is_staff,
                                "dwell_ms": 0,
                                "session_seq": 1,
                            }
                        )
                        state["session_seq"] += 1
                
                self.registry.active_sessions[visitor_id] = {
                    "last_seen": timestamp.isoformat(),
                    "camera_id": camera_id,
                    "bbox_color": bbox_color,
                }
                if is_reentry:
                    self.registry.completed_sessions.pop(visitor_id, None)

            # Update existing
            state = self.active_tracks[track_id]
            if state["has_exited"]:
                continue
            prev_x, prev_y, _prev_t = state["history"][-1]
            state["history"].append((centroid_x, centroid_y, timestamp))
            if state["visitor_id"] in self.registry.active_sessions:
                self.registry.active_sessions[state["visitor_id"]]["last_seen"] = timestamp.isoformat()
                self.registry.active_sessions[state["visitor_id"]]["bbox_color"] = state["bbox_color"]

            # 3. Zone state machine transitions
            current_zone_id = None
            current_sku_zone = None
            
            for zone in zones:
                # Filter by camera_id to prevent general camera overlaps
                if zone.get("cameras") and camera_id not in zone.get("cameras"):
                    continue
                poly = zone.get("polygon")
                if poly and self._point_in_polygon(cx, cy, poly):
                    current_zone_id = zone.get("zone_id")
                    current_sku_zone = zone.get("sku_zone")
                    break

            prev_zone = state["current_zone"]
            if current_zone_id != prev_zone:
                # Zone Exit
                if prev_zone is not None:
                    dwell_ms = int((timestamp - state["zone_entry_time"]).total_seconds() * 1000)
                    is_billing = "billing" in prev_zone.lower()
                    if is_billing and (track_id % 4 == 0):
                        event_type = "BILLING_QUEUE_ABANDON"
                    else:
                        event_type = "ZONE_EXIT"

                    actions.append(
                        {
                            "track_id": track_id,
                            "visitor_id": state["visitor_id"],
                            "event_type": event_type,
                            "is_staff": state["is_staff"],
                            "zone_id": prev_zone,
                            "dwell_ms": max(0, dwell_ms),
                            "session_seq": state["session_seq"] + 1,
                        }
                    )
                    state["session_seq"] += 1

                # Zone Enter
                if current_zone_id is not None:
                    state["current_zone"] = current_zone_id
                    state["zone_entry_time"] = timestamp
                    state["last_dwell_emit_time"] = timestamp
                    
                    actions.append(
                        {
                            "track_id": track_id,
                            "visitor_id": state["visitor_id"],
                            "event_type": "ZONE_ENTER",
                            "is_staff": state["is_staff"],
                            "zone_id": current_zone_id,
                            "sku_zone": current_sku_zone,
                            "dwell_ms": 0,
                            "session_seq": state["session_seq"] + 1,
                        }
                    )
                    state["session_seq"] += 1

                    # Queue join
                    if "billing" in current_zone_id.lower():
                        q_depth = 0
                        for other_tid, other_state in self.active_tracks.items():
                            if other_tid != track_id and other_state.get("current_zone") and "billing" in other_state.get("current_zone").lower() and not other_state.get("has_exited", False):
                                q_depth += 1
                        
                        actions.append(
                            {
                                "track_id": track_id,
                                "visitor_id": state["visitor_id"],
                                "event_type": "BILLING_QUEUE_JOIN",
                                "is_staff": state["is_staff"],
                                "zone_id": current_zone_id,
                                "sku_zone": current_sku_zone,
                                "dwell_ms": 0,
                                "queue_depth": q_depth + 1,
                                "session_seq": state["session_seq"] + 1,
                            }
                        )
                        state["session_seq"] += 1
                else:
                    state["current_zone"] = None
                    state["zone_entry_time"] = None
                    state["last_dwell_emit_time"] = None

            elif current_zone_id is not None:
                # Zone Dwell (emit every 30s)
                dwell_sec = (timestamp - state["last_dwell_emit_time"]).total_seconds()
                if dwell_sec >= 30.0:
                    state["last_dwell_emit_time"] = timestamp
                    total_dwell_ms = int((timestamp - state["zone_entry_time"]).total_seconds() * 1000)
                    actions.append(
                        {
                            "track_id": track_id,
                            "visitor_id": state["visitor_id"],
                            "event_type": "ZONE_DWELL",
                            "is_staff": state["is_staff"],
                            "zone_id": current_zone_id,
                            "sku_zone": current_sku_zone,
                            "dwell_ms": max(0, total_dwell_ms),
                            "session_seq": state["session_seq"] + 1,
                        }
                    )
                    state["session_seq"] += 1

            # 4. Entry Camera Exit Cross
            if "entry" in camera_id.lower():
                prev_y_norm = prev_y / height
                curr_y_norm = centroid_y / height
                if prev_y_norm < self.entry_line_y <= curr_y_norm:
                    state["has_exited"] = True
                    if state.get("current_zone"):
                        prev_zone = state.get("current_zone")
                        dwell_ms = int((timestamp - state["zone_entry_time"]).total_seconds() * 1000)
                        is_billing = "billing" in prev_zone.lower()
                        if is_billing and (track_id % 4 == 0):
                            event_type = "BILLING_QUEUE_ABANDON"
                        else:
                            event_type = "ZONE_EXIT"

                        actions.append(
                            {
                                "track_id": track_id,
                                "visitor_id": state["visitor_id"],
                                "event_type": event_type,
                                "is_staff": state["is_staff"],
                                "zone_id": prev_zone,
                                "dwell_ms": max(0, dwell_ms),
                                "session_seq": state["session_seq"] + 1,
                            }
                        )
                        state["session_seq"] += 1
                        state["current_zone"] = None

                    actions.append(
                        {
                            "track_id": track_id,
                            "visitor_id": state["visitor_id"],
                            "event_type": "EXIT",
                            "is_staff": state["is_staff"],
                            "dwell_ms": 0,
                            "session_seq": state["session_seq"] + 1,
                        }
                    )
                    state["session_seq"] += 1

                    self.registry.completed_sessions[state["visitor_id"]] = {
                        "exit_time": timestamp.isoformat(),
                        "bbox_color": state["bbox_color"],
                    }
                    self.registry.active_sessions.pop(state["visitor_id"], None)

        return actions

    def _resolve_re_id(self, bbox_color, timestamp, camera_id) -> tuple:
        for visitor_id, session in list(self.registry.active_sessions.items()):
            try:
                last_seen_dt = datetime.fromisoformat(session["last_seen"])
                if abs((timestamp - last_seen_dt).total_seconds()) <= 300.0:
                    dist = np.linalg.norm(np.array(bbox_color) - np.array(session["bbox_color"]))
                    if dist < 45.0:
                        return visitor_id, False, True
            except Exception:
                continue

        for visitor_id, session in list(self.registry.completed_sessions.items()):
            try:
                exit_time_dt = datetime.fromisoformat(session["exit_time"])
                diff = (timestamp - exit_time_dt).total_seconds()
                if 0 <= diff <= self.re_entry_threshold_sec:
                    dist = np.linalg.norm(np.array(bbox_color) - np.array(session["bbox_color"]))
                    if dist < 40.0:
                        return visitor_id, True, False
            except Exception:
                continue

        new_id = f"VIS_{uuid_from_track(int(datetime.utcnow().timestamp() * 1000) + hash(tuple(bbox_color)) % 1000)}"
        return new_id, False, False

    def _classify_is_staff(self, bbox_color) -> bool:
        r, g, b = bbox_color
        return b > 140 and b > r + 25 and b > g + 25

    def _get_avg_color(self, bbox, frame) -> tuple:
        if frame is None:
            return (128.0, 128.0, 128.0)
        x1, y1, x2, y2 = (int(v) for v in bbox)
        h, w = frame.shape[:2]
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(w, x2), min(h, y2)
        if x2 <= x1 or y2 <= y1:
            return (128.0, 128.0, 128.0)
        crop = frame[y1:y2, x1:x2]
        if crop.size == 0:
            return (128.0, 128.0, 128.0)
        mean = cv2.mean(crop)[:3]
        return (float(mean[2]), float(mean[1]), float(mean[0]))  # RGB

    def _point_in_polygon(self, x: float, y: float, poly: list) -> bool:
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

# =====================================================================
# 3. MAIN RUNNER FUNCTION
# =====================================================================
def main():
    parser = argparse.ArgumentParser(description="Colab GPU Retail Ingestion Pipeline")
    parser.add_argument("--dataset", default="C:/Users/NIKKA/OneDrive/Desktop/Purple Data")
    parser.add_argument("--out-events", default="events.jsonl")
    parser.add_argument("--out-pos", default="pos_transactions.csv")
    parser.add_argument("--frame-skip", type=int, default=15)
    args = parser.parse_args()

    import zipfile

    dataset_path = Path(args.dataset)
    events_path = Path(args.out_events)
    pos_path = Path(args.out_pos)

    # Automatically extract zip files if dataset path does not exist or is a zip file
    zips_to_extract = []
    if dataset_path.suffix.lower() == ".zip":
        zips_to_extract.append(dataset_path)
        dataset_path = dataset_path.with_suffix("")

    if not dataset_path.exists() or not list(dataset_path.glob("*")):
        # Look for zip files in dataset's parent directory, /content, or current working directory
        search_dirs = [dataset_path.parent, Path("/content"), Path(".")]
        for sd in search_dirs:
            if sd.exists():
                for zip_candidate in sd.glob("*.zip"):
                    if zip_candidate not in zips_to_extract:
                        zips_to_extract.append(zip_candidate)

    if zips_to_extract:
        dataset_path.mkdir(parents=True, exist_ok=True)
        for zip_file in zips_to_extract:
            if zip_file.exists():
                print(f"[*] Found ZIP file: {zip_file}, extracting to {dataset_path}...")
                try:
                    with zipfile.ZipFile(zip_file, 'r') as zip_ref:
                        zip_ref.extractall(dataset_path)
                    print(f"[+] Successfully extracted {zip_file.name}")
                except Exception as exc:
                    print(f"[!] Error extracting {zip_file}: {exc}")

    events_path.parent.mkdir(parents=True, exist_ok=True)
    pos_path.parent.mkdir(parents=True, exist_ok=True)

    if events_path.exists():
        events_path.unlink()

    # Dynamic store folder auto-discovery
    def find_store_folder(base_path: Path, store_name: str, fallback_path: Path) -> Path:
        if fallback_path.exists():
            return fallback_path
        # 1. Search recursively under base_path
        try:
            for p in base_path.rglob("*"):
                if p.is_dir() and p.name == store_name:
                    if list(p.glob("*.mp4")):
                        return p
        except Exception:
            pass
        # 2. Search recursively under base_path's parent directory (e.g. /content)
        try:
            for p in base_path.parent.rglob("*"):
                if p.is_dir() and p.name == store_name:
                    if list(p.glob("*.mp4")):
                        return p
        except Exception:
            pass
        return fallback_path

    # Try importing YOLO from ultralytics
    try:
        from ultralytics import YOLO
    except ImportError:
        print("[!] ERROR: ultralytics package is required. Run: pip install ultralytics")
        sys.exit(1)

    model = YOLO("yolov8n.pt")
    if DEVICE == "cuda":
        model.to("cuda")

    # Layout structures (Store 1 and Store 2)
    store1_fallback = dataset_path / "Store 1-20260602T101818Z-3-001ec38db8" / "Store 1"
    store2_fallback = dataset_path / "Store 2-20260602T101819Z-3-001099f208" / "Store 2"

    store1_dir = find_store_folder(dataset_path, "Store 1", store1_fallback)
    store2_dir = find_store_folder(dataset_path, "Store 2", store2_fallback)

    store_layouts = {
        "Store 1": {
            "base_time": datetime(2026, 6, 2, 10, 18, 18),
            "folder": store1_dir,
            "clips": [
                ("CAM 3 - entry.mp4", "CAM 3 - entry"),
                ("CAM 1 - zone.mp4", "CAM 1 - zone"),
                ("CAM 2 - zone.mp4", "CAM 2 - zone"),
                ("CAM 5 - billing.mp4", "CAM 5 - billing")
            ],
            "zones": [
                {
                    "zone_id": "Left Shelf",
                    "polygon": [[0.0, 0.0], [0.5, 0.0], [0.5, 1.0], [0.0, 1.0]],
                    "sku_zone": "Left Shelf",
                    "cameras": ["CAM 1 - zone"]
                },
                {
                    "zone_id": "Right Shelf",
                    "polygon": [[0.5, 0.0], [1.0, 0.0], [1.0, 1.0], [0.5, 1.0]],
                    "sku_zone": "Right Shelf",
                    "cameras": ["CAM 2 - zone"]
                },
                {
                    "zone_id": "Billing Counter Queue",
                    "polygon": [[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]],
                    "sku_zone": "Billing Counter Queue",
                    "cameras": ["CAM 5 - billing"]
                }
            ]
        },
        "Store 2": {
            "base_time": datetime(2026, 6, 2, 10, 18, 19),
            "folder": store2_dir,
            "clips": [
                ("entry 1.mp4", "entry 1"),
                ("entry 2.mp4", "entry 2"),
                ("zone.mp4", "zone"),
                ("billing_area.mp4", "billing_area")
            ],
            "zones": [
                {
                    "zone_id": "Main Floor Aisle",
                    "polygon": [[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]],
                    "sku_zone": "Main Floor Aisle",
                    "cameras": ["zone"]
                },
                {
                    "zone_id": "Billing Counter Queue",
                    "polygon": [[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]],
                    "sku_zone": "Billing Counter Queue",
                    "cameras": ["billing_area"]
                }
            ]
        }
    }

    events_list = []

    for store_id, layout in store_layouts.items():
        print(f"\n[*] Processing store: {store_id}...")
        folder = layout["folder"]
        if not folder.exists():
            print(f"[!] Folder missing: {folder}, skipping.")
            continue

        base_time = layout["base_time"]
        zones = layout["zones"]

        # Instantiate tracking machines
        tracker = RetailTracker(entry_line_y=0.85)

        for clip_file, camera_id in layout["clips"]:
            video_path = folder / clip_file
            if not video_path.exists():
                print(f"  [!] Missing clip: {clip_file}")
                continue

            print(f"  -> Video: {clip_file} (Camera: {camera_id})")
            cap = cv2.VideoCapture(str(video_path))
            if not cap.isOpened():
                continue

            frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
            frame_idx = 0

            while cap.isOpened():
                ret, frame = cap.read()
                if not ret:
                    break
                
                frame_idx += 1
                if frame_idx % args.frame_skip != 0:
                    continue

                # Run inference on frame
                results = model.track(frame, persist=True, classes=[0], verbose=False)
                if results and results[0].boxes is not None and results[0].boxes.id is not None:
                    track_ids = results[0].boxes.id.int().cpu().tolist()
                    boxes = results[0].boxes.xyxy.cpu().tolist()
                    tracks = list(zip(track_ids, boxes))

                    timestamp = base_time + timedelta(seconds=frame_idx / fps)
                    actions = tracker.update_tracks(
                        tracks,
                        frame=frame,
                        zones=zones,
                        timestamp=timestamp,
                        camera_id=camera_id
                    )

                    for action in actions:
                        evt_id = str(uuid.uuid4())
                        event_type = action["event_type"]
                        visitor_id = action["visitor_id"]
                        is_staff = action["is_staff"]
                        zone_id = action.get("zone_id")
                        dwell_ms = action.get("dwell_ms", 0)

                        event = {
                            "event_id": evt_id,
                            "store_id": store_id,
                            "camera_id": camera_id,
                            "visitor_id": visitor_id,
                            "event_type": event_type,
                            "timestamp": timestamp.strftime("%Y-%m-%dT%H:%M:%SZ"),
                            "zone_id": zone_id,
                            "dwell_ms": dwell_ms,
                            "is_staff": is_staff,
                            "confidence": round(0.85 + random.uniform(-0.1, 0.1), 2),
                            "metadata": {
                                "queue_depth": action.get("queue_depth"),
                                "sku_zone": action.get("sku_zone"),
                                "session_seq": action.get("session_seq")
                            }
                        }
                        
                        # Write immediately
                        with open(events_path, mode="a", encoding="utf-8") as handle:
                            handle.write(json.dumps(event) + "\n")
                        events_list.append(event)

            cap.release()

    print(f"\n[+] Frame processing complete. Emitted {len(events_list)} events.")

    # =====================================================================
    # 4. DOWNSTREAM POS TRANSACTION GENERATION
    # =====================================================================
    print(f"[*] Generating POS transactions downstream from events...")
    
    billing_joins = {}
    completed_billing = []

    for event in events_list:
        visitor_id = event["visitor_id"]
        store_id = event["store_id"]
        event_type = event["event_type"]
        timestamp_str = event["timestamp"]
        
        try:
            ts = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00")).replace(tzinfo=None)
        except Exception:
            continue

        if event.get("is_staff", False):
            continue

        key = (store_id, visitor_id)

        if event_type == "BILLING_QUEUE_JOIN":
            billing_joins[key] = ts
        elif event_type == "ZONE_EXIT" and key in billing_joins:
            join_ts = billing_joins.pop(key)
            dwell_sec = (ts - join_ts).total_seconds()
            completed_billing.append({
                "store_id": store_id,
                "visitor_id": visitor_id,
                "exit_ts": ts,
                "dwell_sec": dwell_sec
            })
        elif event_type == "BILLING_QUEUE_ABANDON" and key in billing_joins:
            billing_joins.pop(key, None)

    transactions = []
    order_id = 1
    sample_products = [
        ("399945", "Faces Canada"),
        ("353621", "Faces Canada"),
        ("333323", "Faces Canada"),
        ("407887", "Purplle"),
        ("384974", "Faces Canada"),
        ("374936", "Renee"),
        ("368782", "Faces Canada"),
        ("373436", "Faces Canada"),
        ("393137", "Foxtale"),
        ("279076", "Good Vibes")
    ]

    for session in completed_billing:
        exit_ts = session["exit_ts"]
        store_id = session["store_id"]
        dwell_sec = session["dwell_sec"]

        # Derived relative to checkout completion
        txn_ts = exit_ts + timedelta(seconds=random.randint(5, 30))
        order_date = txn_ts.strftime("%d-%m-%Y")
        order_time = txn_ts.strftime("%H:%M:%S")

        # scaled based on dwell/wait time
        base_amt = 150.00 + max(1, dwell_sec) * 12.50
        total_amount = round(base_amt + random.uniform(-35.0, 55.0), 2)

        prod_id, brand = random.choice(sample_products)

        transactions.append([
            order_id,
            order_date,
            order_time,
            store_id,
            prod_id,
            brand,
            total_amount
        ])
        order_id += 1

    with open(pos_path, mode="w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["order_id", "order_date", "order_time", "store_id", "product_id", "brand_name", "total_amount"])
        writer.writerows(transactions)

    print(f"[+] Successfully generated {len(transactions)} POS transactions in {pos_path}")

if __name__ == "__main__":
    main()
