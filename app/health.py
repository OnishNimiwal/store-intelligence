from datetime import datetime, timedelta
from typing import Any, Dict

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import DBEvent, get_db

router = APIRouter(prefix="/health", tags=["Monitoring"])


@router.get("", response_model=Dict[str, Any])
def get_service_health(db: Session = Depends(get_db)):
    now = datetime.utcnow()
    store_feeds = (
        db.query(DBEvent.store_id, func.max(DBEvent.timestamp).label("last_timestamp"))
        .group_by(DBEvent.store_id)
        .all()
    )

    status = "healthy"
    feed_statuses: Dict[str, Dict[str, str]] = {}
    stale_stores = []

    for store_id, last_timestamp in store_feeds:
        if not last_timestamp:
            continue
        last_naive = last_timestamp.replace(tzinfo=None) if last_timestamp.tzinfo else last_timestamp
        lag = now - last_naive
        is_stale = lag > timedelta(minutes=10)
        lag_seconds = int(lag.total_seconds())
        feed_statuses[store_id] = {
            "last_event_timestamp": last_naive.isoformat() + "Z",
            "lag": f"{lag_seconds // 60}m {lag_seconds % 60}s",
            "status": "STALE" if is_stale else "ACTIVE",
        }
        if is_stale:
            stale_stores.append(store_id)

    if stale_stores:
        status = "warning"

    response: Dict[str, Any] = {
        "status": status,
        "timestamp": now.isoformat() + "Z",
        "database": "connected",
        "store_feeds": feed_statuses,
    }
    if stale_stores:
        response["warnings"] = [
            {
                "code": "STALE_FEED",
                "message": f"Feed lag >10 minutes for stores: {', '.join(stale_stores)}.",
            }
        ]
    return response
