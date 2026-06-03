import csv
import logging
from datetime import datetime, timedelta
from typing import Dict, List

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import pos_csv_path
from app.database import DBEvent, get_db
from app.models import StoreMetricsResponse

logger = logging.getLogger("store_intelligence")
router = APIRouter(prefix="/stores", tags=["Analytics"])


def load_pos_transactions(store_id: str) -> List[Dict]:
    path = pos_csv_path()
    transactions: List[Dict] = []
    if not path.exists():
        return transactions
    try:
        with open(path, mode="r", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                row_store_id = (row.get("store_id") or "").strip()
                if row_store_id != store_id:
                    continue
                
                ts = None
                order_date = row.get("order_date")
                order_time = row.get("order_time")
                if order_date and order_time:
                    try:
                        # Parse 10-04-2026 16:55:36 format
                        ts = datetime.strptime(f"{order_date.strip()} {order_time.strip()}", "%d-%m-%Y %H:%M:%S")
                    except ValueError:
                        pass
                
                if ts is None:
                    ts_str = row.get("timestamp")
                    if ts_str:
                        try:
                            ts = datetime.fromisoformat(ts_str.strip().replace("Z", "+00:00")).replace(tzinfo=None)
                        except ValueError:
                            pass
                
                if ts is None:
                    continue
                
                val_str = row.get("total_amount") or row.get("basket_value_inr") or row.get("NMV") or row.get("GMV") or "0"
                try:
                    basket_value = float(val_str.strip())
                except ValueError:
                    basket_value = 0.0
                    
                transactions.append(
                    {
                        "timestamp": ts,
                        "basket_value": basket_value,
                    }
                )
    except OSError as exc:
        logger.warning("Could not read POS file %s: %s", path, exc)
    return transactions


def _customer_visitor_ids(db: Session, store_id: str):
    rows = (
        db.query(func.distinct(DBEvent.visitor_id))
        .filter(DBEvent.store_id == store_id)
        .filter(DBEvent.is_staff == False)
        .filter(DBEvent.event_type.in_(["ENTRY", "REENTRY"]))
        .all()
    )
    ids = {row[0] for row in rows}
    if ids:
        return ids
    rows = (
        db.query(func.distinct(DBEvent.visitor_id))
        .filter(DBEvent.store_id == store_id)
        .filter(DBEvent.is_staff == False)
        .all()
    )
    return {row[0] for row in rows}


def _converted_visitors(db: Session, store_id: str, transactions: List[Dict]) -> set:
    converted = set()
    if not transactions:
        return converted
    billing_events = (
        db.query(DBEvent.visitor_id, DBEvent.timestamp)
        .filter(DBEvent.store_id == store_id)
        .filter(DBEvent.is_staff == False)
        .filter(DBEvent.zone_id.in_(["BILLING", "Billing Counter Queue"]))
        .all()
    )
    for txn in transactions:
        txn_time = txn["timestamp"]
        window_start = txn_time - timedelta(minutes=5)
        for visitor_id, event_time in billing_events:
            event_naive = event_time.replace(tzinfo=None) if event_time.tzinfo else event_time
            if window_start <= event_naive <= txn_time:
                converted.add(visitor_id)
    return converted


@router.get("/{store_id}/metrics", response_model=StoreMetricsResponse)
def get_store_metrics(store_id: str, db: Session = Depends(get_db)):
    visitor_ids = _customer_visitor_ids(db, store_id)
    unique_visitors = len(visitor_ids)

    if unique_visitors == 0:
        return StoreMetricsResponse(
            store_id=store_id,
            unique_visitors=0,
            conversion_rate=0.0,
            avg_dwell_per_zone={},
            current_queue_depth=0,
            abandonment_rate=0.0,
        )

    transactions = load_pos_transactions(store_id)
    converted_visitors = _converted_visitors(db, store_id, transactions)
    conversion_rate = len(converted_visitors) / unique_visitors

    avg_dwell_query = (
        db.query(DBEvent.zone_id, func.avg(DBEvent.dwell_ms))
        .filter(DBEvent.store_id == store_id)
        .filter(DBEvent.is_staff == False)
        .filter(DBEvent.zone_id.isnot(None))
        .filter(DBEvent.dwell_ms > 0)
        .group_by(DBEvent.zone_id)
        .all()
    )
    avg_dwell_per_zone = {
        zone_id: round(avg_dwell / 1000.0, 1) for zone_id, avg_dwell in avg_dwell_query if zone_id
    }

    latest_queue = (
        db.query(DBEvent.queue_depth)
        .filter(DBEvent.store_id == store_id)
        .filter(DBEvent.queue_depth.isnot(None))
        .order_by(DBEvent.timestamp.desc())
        .first()
    )
    current_queue_depth = latest_queue[0] if latest_queue else 0

    joins = (
        db.query(func.count(DBEvent.event_id))
        .filter(DBEvent.store_id == store_id)
        .filter(DBEvent.event_type == "BILLING_QUEUE_JOIN")
        .filter(DBEvent.is_staff == False)
        .scalar()
        or 0
    )
    abandons = (
        db.query(func.count(DBEvent.event_id))
        .filter(DBEvent.store_id == store_id)
        .filter(DBEvent.event_type == "BILLING_QUEUE_ABANDON")
        .filter(DBEvent.is_staff == False)
        .scalar()
        or 0
    )

    if joins > 0:
        abandonment_rate = abandons / joins
    else:
        billing_visitors = (
            db.query(func.distinct(DBEvent.visitor_id))
            .filter(DBEvent.store_id == store_id)
            .filter(DBEvent.zone_id == "BILLING")
            .filter(DBEvent.is_staff == False)
            .all()
        )
        billing_set = {v[0] for v in billing_visitors}
        if billing_set:
            abandonment_rate = len(billing_set - converted_visitors) / len(billing_set)
        else:
            abandonment_rate = 0.0

    return StoreMetricsResponse(
        store_id=store_id,
        unique_visitors=unique_visitors,
        conversion_rate=round(conversion_rate, 4),
        avg_dwell_per_zone=avg_dwell_per_zone,
        current_queue_depth=current_queue_depth,
        abandonment_rate=round(abandonment_rate, 4),
    )


@router.get("/{store_id}/raw-events")
def get_raw_events(store_id: str, db: Session = Depends(get_db)):
    events = (
        db.query(DBEvent)
        .filter(DBEvent.store_id == store_id)
        .order_by(DBEvent.timestamp.asc())
        .all()
    )
    return [
        {
            "event_id": e.event_id,
            "store_id": e.store_id,
            "camera_id": e.camera_id,
            "visitor_id": e.visitor_id,
            "event_type": e.event_type,
            "timestamp": e.timestamp.isoformat() if e.timestamp else None,
            "zone_id": e.zone_id,
            "dwell_ms": e.dwell_ms,
            "is_staff": e.is_staff,
            "confidence": e.confidence,
            "queue_depth": e.queue_depth,
            "sku_zone": e.sku_zone,
            "session_seq": e.session_seq,
        }
        for e in events
    ]


@router.get("/{store_id}/linked-conversions")
def get_linked_conversions(store_id: str, db: Session = Depends(get_db)):
    transactions = load_pos_transactions(store_id)
    if not transactions:
        return []
    
    billing_events = (
        db.query(DBEvent.visitor_id, DBEvent.timestamp, DBEvent.event_type)
        .filter(DBEvent.store_id == store_id)
        .filter(DBEvent.is_staff == False)
        .filter(DBEvent.zone_id.in_(["BILLING", "Billing Counter Queue"]))
        .all()
    )
    
    linked = []
    for idx, txn in enumerate(transactions):
        txn_time = txn["timestamp"]
        window_start = txn_time - timedelta(minutes=5)
        converted_visitors = set()
        matching_events = []
        
        for visitor_id, event_time, event_type in billing_events:
            event_naive = event_time.replace(tzinfo=None) if event_time.tzinfo else event_time
            if window_start <= event_naive <= txn_time:
                converted_visitors.add(visitor_id)
                matching_events.append({
                    "visitor_id": visitor_id,
                    "event_time": event_naive.isoformat(),
                    "event_type": event_type,
                })
                
        linked.append({
            "transaction_index": idx + 1,
            "timestamp": txn_time.isoformat(),
            "basket_value": txn["basket_value"],
            "converted_visitors_count": len(converted_visitors),
            "converted_visitor_ids": list(converted_visitors),
            "matching_billing_presence": matching_events,
        })
    return linked
