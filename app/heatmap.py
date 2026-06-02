from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import DBEvent, get_db
from app.metrics import _customer_visitor_ids
from app.models import HeatmapItem, StoreHeatmapResponse

router = APIRouter(prefix="/stores", tags=["Analytics"])


@router.get("/{store_id}/heatmap", response_model=StoreHeatmapResponse)
def get_store_heatmap(store_id: str, db: Session = Depends(get_db)):
    unique_sessions = len(_customer_visitor_ids(db, store_id))
    data_confidence = unique_sessions >= 20

    zone_stats = (
        db.query(
            DBEvent.zone_id,
            func.count(func.distinct(DBEvent.visitor_id)).label("frequency"),
            func.avg(DBEvent.dwell_ms).label("avg_dwell_ms"),
        )
        .filter(DBEvent.store_id == store_id)
        .filter(DBEvent.is_staff == False)
        .filter(DBEvent.zone_id.isnot(None))
        .group_by(DBEvent.zone_id)
        .all()
    )

    raw_scores = {}
    max_raw_score = 0.0
    for zone_id, freq, avg_dwell_ms in zone_stats:
        if not zone_id:
            continue
        avg_dwell_sec = (avg_dwell_ms or 0) / 1000.0
        raw_score = freq * avg_dwell_sec
        raw_scores[zone_id] = {"freq": freq, "dwell": avg_dwell_sec, "raw": raw_score}
        max_raw_score = max(max_raw_score, raw_score)

    heatmap_items = []
    for zone_id, stats in raw_scores.items():
        score = round((stats["raw"] / max_raw_score) * 100.0, 1) if max_raw_score > 0 else 0.0
        heatmap_items.append(
            HeatmapItem(
                zone_id=zone_id,
                visit_frequency=stats["freq"],
                avg_dwell_sec=round(stats["dwell"], 1),
                score=score,
            )
        )
    heatmap_items.sort(key=lambda item: item.score, reverse=True)

    return StoreHeatmapResponse(
        store_id=store_id,
        heatmap=heatmap_items,
        data_confidence=data_confidence,
    )
