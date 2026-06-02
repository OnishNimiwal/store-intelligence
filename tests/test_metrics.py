# PROMPT: Generate FastAPI endpoint tests with TestClient. Mock DB, ingest events, verify /metrics, /funnel, /heatmap. Staff exclusion and empty store.
# CHANGES MADE: Shared seeded_store fixture for related analytics tests; re-entry funnel test.

import pytest

STORE = "STORE_TEST_001"

EVENTS = [
    {
        "event_id": "evt_cust1_entry",
        "store_id": STORE,
        "camera_id": "CAM_ENTRY_01",
        "visitor_id": "VIS_CUST_1",
        "event_type": "ENTRY",
        "timestamp": "2026-03-03T14:35:00Z",
        "confidence": 0.95,
    },
    {
        "event_id": "evt_cust1_billing",
        "store_id": STORE,
        "camera_id": "CAM_BILLING_03",
        "visitor_id": "VIS_CUST_1",
        "event_type": "BILLING_QUEUE_JOIN",
        "timestamp": "2026-03-03T14:38:00Z",
        "zone_id": "BILLING",
        "confidence": 0.90,
        "metadata": {"queue_depth": 1},
    },
    {
        "event_id": "evt_cust2_entry",
        "store_id": STORE,
        "camera_id": "CAM_ENTRY_01",
        "visitor_id": "VIS_CUST_2",
        "event_type": "ENTRY",
        "timestamp": "2026-03-03T14:36:00Z",
        "confidence": 0.95,
    },
    {
        "event_id": "evt_cust2_skincare",
        "store_id": STORE,
        "camera_id": "CAM_FLOOR_02",
        "visitor_id": "VIS_CUST_2",
        "event_type": "ZONE_DWELL",
        "timestamp": "2026-03-03T14:37:00Z",
        "zone_id": "SKINCARE",
        "dwell_ms": 45000,
        "confidence": 0.85,
    },
    {
        "event_id": "evt_staff_entry",
        "store_id": STORE,
        "camera_id": "CAM_ENTRY_01",
        "visitor_id": "VIS_STAFF_1",
        "event_type": "ENTRY",
        "timestamp": "2026-03-03T14:35:00Z",
        "is_staff": True,
        "confidence": 0.99,
    },
]


@pytest.fixture
def seeded_client(client):
    response = client.post("/events/ingest", json=EVENTS)
    assert response.status_code == 201
    return client


def test_ingestion_and_metrics_calculation(seeded_client):
    response_dup = seeded_client.post("/events/ingest", json=EVENTS)
    assert response_dup.status_code == 201
    assert response_dup.json()["ingested_count"] == 5

    metrics = seeded_client.get(f"/stores/{STORE}/metrics").json()
    assert metrics["unique_visitors"] == 2
    assert metrics["avg_dwell_per_zone"]["SKINCARE"] == 45.0
    assert metrics["current_queue_depth"] == 1
    assert metrics["conversion_rate"] == 0.5


def test_funnel_endpoints(seeded_client):
    funnel = seeded_client.get(f"/stores/{STORE}/funnel").json()
    stages = {s["stage_name"]: s for s in funnel["stages"]}
    assert stages["Entry"]["count"] == 2
    assert stages["Zone Visit"]["count"] == 1
    assert stages["Billing Queue"]["count"] == 1
    assert stages["Purchase"]["count"] == 1
    assert stages["Zone Visit"]["drop_off_pct"] == 50.0


def test_heatmap_endpoints(seeded_client):
    heatmap = seeded_client.get(f"/stores/{STORE}/heatmap").json()
    assert heatmap["data_confidence"] is False
    assert len(heatmap["heatmap"]) > 0


def test_empty_store_handling(client):
    metrics = client.get("/stores/STORE_EMPTY/metrics").json()
    assert metrics["unique_visitors"] == 0
    assert metrics["conversion_rate"] == 0.0
    assert metrics["avg_dwell_per_zone"] == {}


def test_reentry_funnel_not_double_counted(client):
    events = [
        {
            "event_id": "re1",
            "store_id": "STORE_RE_001",
            "camera_id": "CAM_ENTRY_01",
            "visitor_id": "VIS_RE",
            "event_type": "ENTRY",
            "timestamp": "2026-03-03T10:00:00Z",
            "confidence": 0.9,
        },
        {
            "event_id": "re2",
            "store_id": "STORE_RE_001",
            "camera_id": "CAM_ENTRY_01",
            "visitor_id": "VIS_RE",
            "event_type": "REENTRY",
            "timestamp": "2026-03-03T12:00:00Z",
            "confidence": 0.9,
        },
    ]
    client.post("/events/ingest", json=events)
    funnel = client.get("/stores/STORE_RE_001/funnel").json()
    entry_count = next(s for s in funnel["stages"] if s["stage_name"] == "Entry")["count"]
    assert entry_count == 1
