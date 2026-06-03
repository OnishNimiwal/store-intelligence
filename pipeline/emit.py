import hashlib
import json
import uuid
import random
from datetime import datetime, timedelta
from typing import Any, Dict, Optional


def get_demographics(visitor_id: str) -> tuple[str, int, str]:
    h = int(hashlib.md5(visitor_id.encode("utf-8")).hexdigest(), 16)
    gender = "M" if h % 2 == 0 else "F"
    age = 20 + (h % 35)  # 20 to 54
    if age < 25:
        bucket = "18-24"
    elif age < 35:
        bucket = "25-34"
    elif age < 45:
        bucket = "35-44"
    else:
        bucket = "45-54"
    return gender, age, bucket


def get_numeric_track_id(visitor_id: str) -> int:
    try:
        parts = visitor_id.split("_")
        if len(parts) > 1 and parts[1].isdigit():
            return int(parts[1])
    except Exception:
        pass
    h = int(hashlib.md5(visitor_id.encode("utf-8")).hexdigest(), 16)
    return 100 + (h % 900)  # 100 to 999


class EventEmitter:
    def __init__(self, store_id: str, schema_format: str = "format1"):
        self.store_id = store_id
        self.schema_format = schema_format

    def build_event(
        self,
        camera_id: str,
        visitor_id: str,
        event_type: str,
        timestamp: datetime,
        zone_id: Optional[str] = None,
        dwell_ms: int = 0,
        is_staff: bool = False,
        confidence: float = 1.0,
        queue_depth: Optional[int] = None,
        sku_zone: Optional[str] = None,
        session_seq: Optional[int] = None,
    ) -> Dict[str, Any]:
        
        # 1. Format 1: Problem Statement Schema
        if self.schema_format == "format1":
            formatted_timestamp = timestamp.strftime("%Y-%m-%dT%H:%M:%SZ")
            return {
                "event_id": str(uuid.uuid4()),
                "store_id": self.store_id,
                "camera_id": camera_id,
                "visitor_id": visitor_id,
                "event_type": event_type,
                "timestamp": formatted_timestamp,
                "zone_id": zone_id,
                "dwell_ms": dwell_ms,
                "is_staff": is_staff,
                "confidence": round(float(confidence), 2),
                "metadata": {
                    "queue_depth": queue_depth,
                    "sku_zone": sku_zone,
                    "session_seq": session_seq,
                },
            }
            
        # 2. Format 2: Sampleevents.jsonl Schema
        else:
            gender, age, bucket = get_demographics(visitor_id)
            track_id = get_numeric_track_id(visitor_id)
            formatted_timestamp = timestamp.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3]
            
            # Map event type
            if event_type in ("ENTRY", "REENTRY"):
                return {
                    "event_type": "entry",
                    "id_token": f"ID_{track_id}",
                    "store_code": self.store_id,
                    "camera_id": camera_id.lower() if camera_id else "cam1",
                    "event_timestamp": formatted_timestamp,
                    "is_staff": is_staff,
                    "gender_pred": gender,
                    "age_pred": age,
                    "age_bucket": bucket,
                    "is_face_hidden": False,
                    "group_id": None,
                    "group_size": None,
                }
            elif event_type == "EXIT":
                return {
                    "event_type": "exit",
                    "id_token": f"ID_{track_id}",
                    "store_code": self.store_id,
                    "camera_id": camera_id.lower() if camera_id else "cam1",
                    "event_timestamp": formatted_timestamp,
                    "is_staff": is_staff,
                    "gender_pred": gender,
                    "age_pred": age,
                    "age_bucket": bucket,
                    "is_face_hidden": False,
                    "group_id": None,
                    "group_size": None,
                }
            elif event_type == "ZONE_ENTER":
                return {
                    "event_type": "zone_entered",
                    "track_id": track_id,
                    "store_id": self.store_id,
                    "camera_id": camera_id,
                    "zone_id": zone_id or "ZONE_XYZ",
                    "zone_name": sku_zone or "Shelf Display",
                    "zone_type": "SHELF" if "shelf" in (sku_zone or "").lower() else ("BILLING" if "billing" in (zone_id or "").lower() else "DISPLAY"),
                    "is_revenue_zone": "Yes" if zone_id in ("COSMETICS", "SKINCARE", "BILLING") else "No",
                    "event_time": formatted_timestamp,
                    "zone_hotspot_x": round(random.uniform(200.0, 600.0), 1),
                    "zone_hotspot_y": round(random.uniform(150.0, 450.0), 1),
                    "gender": gender,
                    "age": age,
                    "age_bucket": bucket,
                }
            elif event_type == "ZONE_EXIT":
                return {
                    "event_type": "zone_exited",
                    "track_id": track_id,
                    "store_id": self.store_id,
                    "camera_id": camera_id,
                    "zone_id": zone_id or "ZONE_XYZ",
                    "zone_name": sku_zone or "Shelf Display",
                    "zone_type": "SHELF" if "shelf" in (sku_zone or "").lower() else ("BILLING" if "billing" in (zone_id or "").lower() else "DISPLAY"),
                    "is_revenue_zone": "Yes" if zone_id in ("COSMETICS", "SKINCARE", "BILLING") else "No",
                    "event_time": formatted_timestamp,
                    "zone_hotspot_x": round(random.uniform(200.0, 600.0), 1),
                    "zone_hotspot_y": round(random.uniform(150.0, 450.0), 1),
                    "gender": gender,
                    "age": age,
                    "age_bucket": bucket,
                }
            elif event_type in ("BILLING_QUEUE_JOIN", "BILLING_QUEUE_ABANDON"):
                is_abandon = event_type == "BILLING_QUEUE_ABANDON"
                join_time = (timestamp - timedelta(seconds=30)).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3]
                served_time = (timestamp - timedelta(seconds=10)).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] if not is_abandon else None
                exit_time = formatted_timestamp
                
                return {
                    "queue_event_id": str(uuid.uuid4()),
                    "event_type": "queue_abandoned" if is_abandon else "queue_completed",
                    "track_id": track_id,
                    "store_id": self.store_id,
                    "camera_id": camera_id,
                    "zone_id": zone_id or "BILLING_ZONE",
                    "zone_name": sku_zone or "Billing Counter Queue",
                    "zone_type": "BILLING",
                    "is_revenue_zone": "Yes",
                    "queue_join_ts": join_time,
                    "queue_served_ts": served_time,
                    "queue_exit_ts": exit_time,
                    "wait_seconds": dwell_ms // 1000 if dwell_ms else 30,
                    "queue_position_at_join": queue_depth or 2,
                    "abandoned": is_abandon,
                    "zone_hotspot_x": round(random.uniform(500.0, 700.0), 1),
                    "zone_hotspot_y": round(random.uniform(150.0, 250.0), 1),
                    "gender": gender,
                    "age": age,
                    "age_bucket": bucket,
                }
            
            # Fallback for remaining events
            return {
                "event_type": event_type.lower(),
                "id_token": f"ID_{track_id}",
                "store_code": self.store_id,
                "camera_id": camera_id,
                "event_timestamp": formatted_timestamp,
            }

    def emit(self, event: Dict[str, Any], output_file: Optional[str] = None) -> None:
        line = json.dumps(event)
        if output_file:
            with open(output_file, mode="a", encoding="utf-8") as handle:
                handle.write(line + "\n")
        else:
            print(line)
