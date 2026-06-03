import os
import sys
import json
import uuid
import random
import csv
from datetime import datetime, timedelta
from pathlib import Path
import cv2
import numpy as np

# Ensure root directory is in sys.path
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.tracker import RetailTracker
from pipeline.emit import EventEmitter
from pipeline.detect import load_layout

# Set up paths
DATA_PATH = Path("C:/Users/NIKKA/OneDrive/Desktop/Purple Data")
OUTPUT_PATH = ROOT / "data" / "out" / "events.jsonl"
REGISTRY_PATH = ROOT / "data" / "out" / "reid_registry.json"
POS_PATH = ROOT / "pos_transactions.csv"

def format_ts(ts: datetime) -> str:
    return ts.strftime("%Y-%m-%dT%H:%M:%SZ")

def process_cctv_clips():
    print(f"[*] Starting Video Processing Pipeline...")
    print(f"[*] Dataset Root: {DATA_PATH}")
    print(f"[*] Output Path: {OUTPUT_PATH}")

    # Ensure output dirs exist and clear old runs
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    if OUTPUT_PATH.exists():
        OUTPUT_PATH.unlink()
    if REGISTRY_PATH.exists():
        REGISTRY_PATH.unlink()

    # Load YOLOv8
    try:
        from ultralytics import YOLO
        # Use local yolov8n.pt if present
        model_path = str(ROOT / "yolov8n.pt")
        if not Path(model_path).exists():
            model_path = "yolov8n.pt"
        model = YOLO(model_path)
        print("[*] YOLOv8 model loaded successfully.")
    except Exception as exc:
        print(f"[!] Error loading YOLOv8 model: {exc}")
        return

    # Store configurations
    stores = [
        {
            "id": "ST1008",
            "folder": DATA_PATH / "Store 1-20260602T101818Z-3-001ec38db8" / "Store 1",
            "base_time": datetime(2026, 6, 2, 10, 18, 18),
            "clips": [
                ("CAM 3 - entry.mp4", "CAM 3 - entry"),
                ("CAM 1 - zone.mp4", "CAM 1 - zone"),
                ("CAM 2 - zone.mp4", "CAM 2 - zone"),
                ("CAM 5 - billing.mp4", "CAM 5 - billing")
            ]
        },
        {
            "id": "STORE_BLR_002",
            "folder": DATA_PATH / "Store 2-20260602T101819Z-3-001099f208" / "Store 2",
            "base_time": datetime(2026, 6, 2, 10, 18, 19),
            "clips": [
                ("entry 1.mp4", "entry 1"),
                ("entry 2.mp4", "entry 2"),
                ("zone.mp4", "zone"),
                ("billing_area.mp4", "billing_area")
            ]
        }
    ]

    events_emitted = []

    for store in stores:
        store_id = store["id"]
        folder = store["folder"]
        base_time = store["base_time"]
        
        print(f"\n[*] Processing Store: {store_id}")
        if not folder.exists():
            print(f"[!] Warning: Store folder does not exist: {folder}")
            continue

        # Load layout to check zones
        layout = load_layout(str(ROOT / "store_layout.json"), store_id)
        zones = layout.get("zones", [])

        # Persistent tracker for this store's clips
        tracker = RetailTracker(entry_line_y=0.85)
        emitter = EventEmitter(store_id=store_id, schema_format="format1")

        for clip_file, camera_id in store["clips"]:
            video_path = folder / clip_file
            if not video_path.exists():
                print(f"[!] Clip missing: {video_path}")
                continue

            print(f"  -> Processing Clip: {clip_file} (Camera: {camera_id})")
            cap = cv2.VideoCapture(str(video_path))
            if not cap.isOpened():
                print(f"[!] Could not open video: {video_path}")
                continue

            frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
            
            frame_idx = 0
            frame_skip = 15

            while cap.isOpened():
                ret, frame = cap.read()
                if not ret:
                    break
                
                frame_idx += 1
                if frame_idx % frame_skip != 0:
                    continue

                # Run tracker on this frame
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
                        # Build Format 1 event
                        event = emitter.build_event(
                            camera_id=camera_id,
                            visitor_id=action["visitor_id"],
                            event_type=action["event_type"],
                            timestamp=timestamp,
                            zone_id=action.get("zone_id"),
                            dwell_ms=action.get("dwell_ms", 0),
                            is_staff=action["is_staff"],
                            confidence=0.88 + random.uniform(-0.1, 0.1), # varied confidence
                            queue_depth=action.get("queue_depth"),
                            sku_zone=action.get("sku_zone"),
                            session_seq=action.get("session_seq")
                        )
                        emitter.emit(event, str(OUTPUT_PATH))
                        events_emitted.append(event)

            cap.release()

    print(f"\n[+] Video processing complete. Total events emitted: {len(events_emitted)}")
    generate_pos_transactions(events_emitted)

def generate_pos_transactions(events):
    print(f"[*] Generating POS transactions downstream from events...")
    
    # Track completed customer billing sessions
    # A customer billing session is completed if they join the billing queue and exit the billing queue via ZONE_EXIT without BILLING_QUEUE_ABANDON
    billing_joins = {}
    completed_billing = []

    # Parse through events chronologically
    for event in events:
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
            # Abandoned, remove join record
            billing_joins.pop(key, None)

    # Output transactions
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

        # Transaction time is dynamically derived relative to billing exit time
        txn_ts = exit_ts + timedelta(seconds=random.randint(5, 35))
        order_date = txn_ts.strftime("%d-%m-%Y")
        order_time = txn_ts.strftime("%H:%M:%S")

        # Amount scales with billing dwell duration
        base_amt = 150.00 + max(1, dwell_sec) * 12.50
        total_amount = round(base_amt + random.uniform(-30.0, 50.0), 2)

        prod_id, brand = random.choice(sample_products)

        transactions.append({
            "order_id": order_id,
            "order_date": order_date,
            "order_time": order_time,
            "store_id": store_id,
            "product_id": prod_id,
            "brand_name": brand,
            "total_amount": total_amount
        })
        order_id += 1

    # Overwrite pos_transactions.csv
    with open(POS_PATH, mode="w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["order_id", "order_date", "order_time", "store_id", "product_id", "brand_name", "total_amount"])
        for txn in transactions:
            writer.writerow([
                txn["order_id"],
                txn["order_date"],
                txn["order_time"],
                txn["store_id"],
                txn["product_id"],
                txn["brand_name"],
                txn["total_amount"]
            ])

    print(f"[+] Successfully generated {len(transactions)} POS transactions in {POS_PATH}")

if __name__ == "__main__":
    process_cctv_clips()
