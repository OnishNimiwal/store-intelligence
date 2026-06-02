from fastapi import APIRouter, Depends
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.database import DBEvent, get_db
from app.metrics import _converted_visitors, _customer_visitor_ids, load_pos_transactions
from app.models import FunnelStage, StoreFunnelResponse

router = APIRouter(prefix="/stores", tags=["Analytics"])


@router.get("/{store_id}/funnel", response_model=StoreFunnelResponse)
def get_store_funnel(store_id: str, db: Session = Depends(get_db)):
    entry_visitor_ids = _customer_visitor_ids(db, store_id)
    entry_count = len(entry_visitor_ids)

    if entry_count == 0:
        empty = FunnelStage(stage_name="Entry", count=0, drop_off_pct=0.0)
        return StoreFunnelResponse(
            store_id=store_id,
            stages=[
                empty,
                FunnelStage(stage_name="Zone Visit", count=0, drop_off_pct=0.0),
                FunnelStage(stage_name="Billing Queue", count=0, drop_off_pct=0.0),
                FunnelStage(stage_name="Purchase", count=0, drop_off_pct=0.0),
            ],
        )

    zone_rows = (
        db.query(func.distinct(DBEvent.visitor_id))
        .filter(DBEvent.store_id == store_id)
        .filter(DBEvent.is_staff == False)
        .filter(DBEvent.zone_id.isnot(None))
        .filter(DBEvent.zone_id != "BILLING")
        .all()
    )
    zone_visitor_ids = {v[0] for v in zone_rows}.intersection(entry_visitor_ids)
    zone_count = len(zone_visitor_ids)

    queue_rows = (
        db.query(func.distinct(DBEvent.visitor_id))
        .filter(DBEvent.store_id == store_id)
        .filter(DBEvent.is_staff == False)
        .filter(or_(DBEvent.event_type == "BILLING_QUEUE_JOIN", DBEvent.zone_id == "BILLING"))
        .all()
    )
    queue_visitor_ids = {v[0] for v in queue_rows}.intersection(entry_visitor_ids)
    queue_count = len(queue_visitor_ids)

    transactions = load_pos_transactions(store_id)
    purchase_visitor_ids = _converted_visitors(db, store_id, transactions)
    purchase_visitor_ids = purchase_visitor_ids.intersection(queue_visitor_ids)
    purchase_count = len(purchase_visitor_ids)

    drop_off_zone = round(((entry_count - zone_count) / entry_count) * 100, 2) if entry_count else 0.0
    drop_off_queue = round(((zone_count - queue_count) / zone_count) * 100, 2) if zone_count else 0.0
    drop_off_purchase = round(((queue_count - purchase_count) / queue_count) * 100, 2) if queue_count else 0.0

    return StoreFunnelResponse(
        store_id=store_id,
        stages=[
            FunnelStage(stage_name="Entry", count=entry_count, drop_off_pct=0.0),
            FunnelStage(stage_name="Zone Visit", count=zone_count, drop_off_pct=drop_off_zone),
            FunnelStage(stage_name="Billing Queue", count=queue_count, drop_off_pct=drop_off_queue),
            FunnelStage(stage_name="Purchase", count=purchase_count, drop_off_pct=drop_off_purchase),
        ],
    )
