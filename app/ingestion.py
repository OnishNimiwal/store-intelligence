import logging
import uuid
from datetime import datetime
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import DBEvent, get_db
from app.models import EventSchema, IngestResponse

logger = logging.getLogger("store_intelligence")
router = APIRouter(prefix="/events", tags=["Ingestion"])


def format_ts(ts_str: str) -> str:
    if ts_str and not ts_str.endswith("Z") and "+" not in ts_str and "-" not in ts_str[10:]:
        return ts_str + "Z"
    return ts_str


def normalize_raw_event(raw: dict) -> List[dict]:
    event_type = raw.get("event_type")
    if not event_type:
        return [raw]

    if event_type in ("entry", "exit", "reentry"):
        id_token = raw.get("id_token")
        store_code = raw.get("store_code") or raw.get("store_id")
        camera_id = raw.get("camera_id")
        timestamp = raw.get("event_timestamp") or raw.get("timestamp")
        is_staff = raw.get("is_staff", False)

        if id_token and timestamp:
            timestamp_formatted = format_ts(timestamp)
            namespace = uuid.NAMESPACE_DNS
            evt_id = str(uuid.uuid5(namespace, f"{id_token}_{timestamp_formatted}_{event_type}"))

            f1_event = {
                "event_id": raw.get("event_id") or evt_id,
                "store_id": store_code,
                "camera_id": camera_id,
                "visitor_id": id_token,
                "event_type": event_type.upper(),
                "timestamp": timestamp_formatted,
                "zone_id": None,
                "dwell_ms": 0,
                "is_staff": is_staff,
                "confidence": raw.get("confidence", 1.0),
                "metadata": {
                    "session_seq": 1 if event_type == "entry" else (2 if event_type == "reentry" else 999),
                    "sku_zone": None,
                    "queue_depth": None,
                },
            }
            return [f1_event]

    elif event_type in ("zone_entered", "zone_exited"):
        track_id = raw.get("track_id")
        store_id = raw.get("store_id") or raw.get("store_code")
        camera_id = raw.get("camera_id")
        zone_id = raw.get("zone_id")
        zone_name = raw.get("zone_name")
        timestamp = raw.get("event_time") or raw.get("timestamp")

        if track_id is not None and timestamp:
            timestamp_formatted = format_ts(timestamp)
            f1_type = "ZONE_ENTER" if event_type == "zone_entered" else "ZONE_EXIT"
            namespace = uuid.NAMESPACE_DNS
            evt_id = str(uuid.uuid5(namespace, f"{track_id}_{timestamp_formatted}_{f1_type}"))

            f1_event = {
                "event_id": raw.get("event_id") or evt_id,
                "store_id": store_id,
                "camera_id": camera_id,
                "visitor_id": f"VIS_{track_id}",
                "event_type": f1_type,
                "timestamp": timestamp_formatted,
                "zone_id": zone_id,
                "dwell_ms": 0,
                "is_staff": False,
                "confidence": raw.get("confidence", 1.0),
                "metadata": {
                    "sku_zone": zone_name,
                    "session_seq": None,
                    "queue_depth": None,
                },
            }
            return [f1_event]

    elif event_type in ("queue_completed", "queue_abandoned"):
        track_id = raw.get("track_id")
        store_id = raw.get("store_id") or raw.get("store_code")
        camera_id = raw.get("camera_id")
        zone_id = raw.get("zone_id")
        zone_name = raw.get("zone_name")
        queue_join_ts = raw.get("queue_join_ts")
        queue_exit_ts = raw.get("queue_exit_ts")
        wait_seconds = raw.get("wait_seconds", 0)
        queue_position = raw.get("queue_position_at_join")
        abandoned = raw.get("abandoned", False) or (event_type == "queue_abandoned")

        events = []
        namespace = uuid.NAMESPACE_DNS

        if track_id is not None and queue_join_ts:
            join_ts_formatted = format_ts(queue_join_ts)
            join_evt_id = str(uuid.uuid5(namespace, f"{track_id}_{join_ts_formatted}_BILLING_QUEUE_JOIN"))
            events.append({
                "event_id": join_evt_id,
                "store_id": store_id,
                "camera_id": camera_id,
                "visitor_id": f"VIS_{track_id}",
                "event_type": "BILLING_QUEUE_JOIN",
                "timestamp": join_ts_formatted,
                "zone_id": "BILLING",
                "dwell_ms": 0,
                "is_staff": False,
                "confidence": raw.get("confidence", 1.0),
                "metadata": {
                    "queue_depth": queue_position,
                    "sku_zone": zone_name,
                    "session_seq": None,
                },
            })

        if track_id is not None and queue_exit_ts:
            exit_ts_formatted = format_ts(queue_exit_ts)
            exit_f1_type = "BILLING_QUEUE_ABANDON" if abandoned else "ZONE_EXIT"
            exit_evt_id = str(uuid.uuid5(namespace, f"{track_id}_{exit_ts_formatted}_{exit_f1_type}"))
            events.append({
                "event_id": exit_evt_id,
                "store_id": store_id,
                "camera_id": camera_id,
                "visitor_id": f"VIS_{track_id}",
                "event_type": exit_f1_type,
                "timestamp": exit_ts_formatted,
                "zone_id": "BILLING",
                "dwell_ms": int(wait_seconds * 1000) if wait_seconds else 0,
                "is_staff": False,
                "confidence": raw.get("confidence", 1.0),
                "metadata": {
                    "queue_depth": None,
                    "sku_zone": zone_name,
                    "session_seq": None,
                },
            })

        if events:
            return events

    return [raw]


@router.post("/ingest", response_model=IngestResponse, status_code=status.HTTP_201_CREATED)
def ingest_events(payload: List[Dict[str, Any]], db: Session = Depends(get_db)):
    # Normalize payload first
    normalized_payload: List[Dict[str, Any]] = []
    for raw_event in payload:
        normalized_payload.extend(normalize_raw_event(raw_event))

    if len(normalized_payload) > 500:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Batch size exceeds maximum limit of 500 events.",
        )

    ingested_count = 0
    errors: List[Dict[str, Any]] = []
    events_to_insert = []
    seen_event_ids: set[str] = set()

    for idx, raw_event in enumerate(normalized_payload):
        if raw_event.get("event_type") == "ZONE_EXIT":
            visitor_id = raw_event.get("visitor_id")
            zone_id = raw_event.get("zone_id")
            store_id = raw_event.get("store_id")
            exit_ts_str = raw_event.get("timestamp")
            
            enter_ts_str = None
            for prev_evt in reversed(normalized_payload[:idx]):
                if (
                    prev_evt.get("event_type") == "ZONE_ENTER"
                    and prev_evt.get("visitor_id") == visitor_id
                    and prev_evt.get("zone_id") == zone_id
                    and prev_evt.get("store_id") == store_id
                ):
                    enter_ts_str = prev_evt.get("timestamp")
                    break
            
            if not enter_ts_str:
                last_enter = (
                    db.query(DBEvent.timestamp)
                    .filter(DBEvent.store_id == store_id)
                    .filter(DBEvent.visitor_id == visitor_id)
                    .filter(DBEvent.zone_id == zone_id)
                    .filter(DBEvent.event_type == "ZONE_ENTER")
                    .order_by(DBEvent.timestamp.desc())
                    .first()
                )
                if last_enter:
                    enter_ts_str = last_enter[0].isoformat()
            
            if enter_ts_str:
                try:
                    exit_ts = datetime.fromisoformat(exit_ts_str.replace("Z", "+00:00")).replace(tzinfo=None)
                    enter_ts = datetime.fromisoformat(enter_ts_str.replace("Z", "+00:00")).replace(tzinfo=None)
                    duration_sec = (exit_ts - enter_ts).total_seconds()
                    if duration_sec > 0:
                        raw_event["dwell_ms"] = int(duration_sec * 1000)
                except Exception:
                    pass

        try:
            validated = EventSchema(**raw_event)
            if validated.event_id in seen_event_ids:
                errors.append(
                    {
                        "index": idx,
                        "event_id": validated.event_id,
                        "error": "Duplicate event_id within the same batch payload.",
                    }
                )
                continue
            seen_event_ids.add(validated.event_id)

            existing = db.query(DBEvent.event_id).filter(DBEvent.event_id == validated.event_id).first()
            if existing:
                ingested_count += 1
                continue

            meta = validated.metadata
            events_to_insert.append(
                DBEvent(
                    event_id=validated.event_id,
                    store_id=validated.store_id,
                    camera_id=validated.camera_id,
                    visitor_id=validated.visitor_id,
                    event_type=validated.event_type,
                    timestamp=validated.timestamp,
                    zone_id=validated.zone_id,
                    dwell_ms=validated.dwell_ms,
                    is_staff=validated.is_staff,
                    confidence=validated.confidence,
                    queue_depth=meta.queue_depth if meta else None,
                    sku_zone=meta.sku_zone if meta else None,
                    session_seq=meta.session_seq if meta else None,
                )
            )
        except Exception as exc:
            logger.warning("Validation failed for event at index %s: %s", idx, exc)
            errors.append(
                {
                    "index": idx,
                    "event_id": raw_event.get("event_id", "unknown"),
                    "error": str(exc),
                }
            )

    if events_to_insert:
        try:
            db.bulk_save_objects(events_to_insert)
            db.commit()
            ingested_count += len(events_to_insert)
        except Exception as exc:
            db.rollback()
            logger.error("Bulk insert database error: %s", exc)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Database unavailable. Unable to save events.",
            ) from exc

    return IngestResponse(success=len(errors) == 0, ingested_count=ingested_count, errors=errors)
