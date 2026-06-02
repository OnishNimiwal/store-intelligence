import uuid
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import DBEvent, get_db
from app.metrics import get_store_metrics
from app.models import AnomalyItem, StoreAnomaliesResponse

router = APIRouter(prefix="/stores", tags=["Analytics"])

BASELINE_CONVERSION = 0.20
CONVERSION_DROP_THRESHOLD = 0.15


@router.get("/{store_id}/anomalies", response_model=StoreAnomaliesResponse)
def get_store_anomalies(store_id: str, db: Session = Depends(get_db)):
    anomalies = []
    now = datetime.utcnow()
    metrics = get_store_metrics(store_id=store_id, db=db)

    if metrics.current_queue_depth > 5:
        anomalies.append(
            AnomalyItem(
                anomaly_id=f"ANOM_Q_{uuid.uuid4().hex[:8]}",
                type="BILLING_QUEUE_SPIKE",
                severity="CRITICAL" if metrics.current_queue_depth > 8 else "WARN",
                timestamp=now,
                details=f"Billing queue depth has reached {metrics.current_queue_depth} customers.",
                suggested_action="Deploy an additional billing operator immediately and open Backup Register 2.",
            )
        )

    if metrics.unique_visitors >= 5 and metrics.conversion_rate < CONVERSION_DROP_THRESHOLD:
        anomalies.append(
            AnomalyItem(
                anomaly_id=f"ANOM_C_{uuid.uuid4().hex[:8]}",
                type="CONVERSION_DROP",
                severity="WARN",
                timestamp=now,
                details=(
                    f"Store conversion rate is {round(metrics.conversion_rate * 100, 2)}% "
                    f"(below baseline {BASELINE_CONVERSION * 100:.0f}%)."
                ),
                suggested_action="Inspect checkout zone bottlenecks and verify POS terminal connectivity.",
            )
        )

    all_zones = (
        db.query(func.distinct(DBEvent.zone_id))
        .filter(DBEvent.store_id == store_id)
        .filter(DBEvent.zone_id.isnot(None))
        .filter(DBEvent.zone_id != "BILLING")
        .filter(DBEvent.is_staff == False)
        .all()
    )
    for (zone,) in all_zones:
        if not zone:
            continue
        latest = (
            db.query(DBEvent.timestamp)
            .filter(DBEvent.store_id == store_id)
            .filter(DBEvent.zone_id == zone)
            .filter(DBEvent.is_staff == False)
            .order_by(DBEvent.timestamp.desc())
            .first()
        )
        if not latest:
            continue
        last_active = latest[0]
        if last_active.tzinfo:
            last_active = last_active.replace(tzinfo=None)
        inactive = now - last_active
        if inactive > timedelta(minutes=30):
            inactive_mins = int(inactive.total_seconds() / 60)
            anomalies.append(
                AnomalyItem(
                    anomaly_id=f"ANOM_DZ_{uuid.uuid4().hex[:8]}",
                    type="DEAD_ZONE",
                    severity="INFO",
                    timestamp=now,
                    details=f"No customer activity in '{zone}' for {inactive_mins} minutes.",
                    suggested_action=f"Verify camera coverage and merchandising for zone '{zone}'.",
                )
            )

    return StoreAnomaliesResponse(store_id=store_id, anomalies=anomalies)
