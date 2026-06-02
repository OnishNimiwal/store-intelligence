# PROMPT: Generate health endpoint tests including STALE_FEED warning when last event is old.
# CHANGES MADE: Seeded old timestamp event and asserted warning code in response.

from datetime import datetime, timedelta

from app.database import DBEvent
from tests.conftest import TestingSessionLocal


def test_health_stale_feed_warning(client):
    db = TestingSessionLocal()
    old = datetime.utcnow() - timedelta(minutes=20)
    db.add(
        DBEvent(
            event_id="stale-1",
            store_id="STORE_STALE",
            camera_id="CAM_ENTRY_01",
            visitor_id="VIS_S1",
            event_type="ENTRY",
            timestamp=old,
            confidence=0.9,
        )
    )
    db.commit()
    db.close()

    health = client.get("/health").json()
    assert health["status"] == "warning"
    assert any(w["code"] == "STALE_FEED" for w in health.get("warnings", []))
