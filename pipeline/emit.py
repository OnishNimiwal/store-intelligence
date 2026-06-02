import json
import uuid
from datetime import datetime
from typing import Any, Dict, Optional


class EventEmitter:
    def __init__(self, store_id: str):
        self.store_id = store_id

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

    def emit(self, event: Dict[str, Any], output_file: Optional[str] = None) -> None:
        line = json.dumps(event)
        if output_file:
            with open(output_file, mode="a", encoding="utf-8") as handle:
                handle.write(line + "\n")
        else:
            print(line)
