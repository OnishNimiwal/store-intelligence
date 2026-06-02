# PROMPT: Generate pytest tests for anomaly detection: queue spikes, conversion drops, dead zones with severity and suggested_action.
# CHANGES MADE: Direct DB seeding for queue depth 6 and 45-minute stale SKINCARE zone.

from datetime import datetime, timedelta

from app.database import DBEvent
from tests.conftest import TestingSessionLocal


def test_anomalies_detection_logic(client):
    db = TestingSessionLocal()
    now = datetime.utcnow()
    db_events = [
        DBEvent(
            event_id=f"evt_anom_q_{i}",
            store_id="STORE_ANOM_01",
            camera_id="CAM_BILLING_03",
            visitor_id=f"VIS_Q_{i}",
            event_type="BILLING_QUEUE_JOIN",
            timestamp=now,
            zone_id="BILLING",
            confidence=0.91,
            queue_depth=6,
        )
        for i in range(6)
    ]
    db.add_all(db_events)
    db.add(
        DBEvent(
            event_id="evt_skincare_dead",
            store_id="STORE_ANOM_01",
            camera_id="CAM_FLOOR_02",
            visitor_id="VIS_CUST_OLD",
            event_type="ZONE_ENTER",
            timestamp=now - timedelta(minutes=45),
            zone_id="SKINCARE",
            confidence=0.88,
        )
    )
    db.add(
        DBEvent(
            event_id="evt_cosmetics_active",
            store_id="STORE_ANOM_01",
            camera_id="CAM_FLOOR_02",
            visitor_id="VIS_CUST_NEW",
            event_type="ZONE_ENTER",
            timestamp=now - timedelta(minutes=5),
            zone_id="COSMETICS",
            confidence=0.89,
        )
    )
    db.commit()
    db.close()

    res = client.get("/stores/STORE_ANOM_01/anomalies").json()
    anoms = {a["type"]: a for a in res["anomalies"]}
    assert "BILLING_QUEUE_SPIKE" in anoms
    assert anoms["BILLING_QUEUE_SPIKE"]["severity"] == "WARN"
    assert "DEAD_ZONE" in anoms
    assert "skincare" in anoms["DEAD_ZONE"]["details"].lower()
