import logging
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import DBEvent, get_db
from app.models import EventSchema, IngestResponse

logger = logging.getLogger("store_intelligence")
router = APIRouter(prefix="/events", tags=["Ingestion"])


@router.post("/ingest", response_model=IngestResponse, status_code=status.HTTP_201_CREATED)
def ingest_events(payload: List[Dict[str, Any]], db: Session = Depends(get_db)):
    if len(payload) > 500:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Batch size exceeds maximum limit of 500 events.",
        )

    ingested_count = 0
    errors: List[Dict[str, Any]] = []
    events_to_insert = []
    seen_event_ids: set[str] = set()

    for idx, raw_event in enumerate(payload):
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
