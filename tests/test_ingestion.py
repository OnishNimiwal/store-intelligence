# PROMPT: Write pytest tests for POST /events/ingest batch limits, partial errors, and malformed events.
# CHANGES MADE: Added batch size 501 rejection test and partial success with one bad event.

def test_batch_size_limit(client):
    payload = [
        {
            "event_id": f"evt_{i}",
            "store_id": "STORE_BLR_002",
            "camera_id": "CAM_ENTRY_01",
            "visitor_id": f"VIS_{i}",
            "event_type": "ENTRY",
            "timestamp": "2026-03-03T14:00:00Z",
            "confidence": 0.9,
        }
        for i in range(501)
    ]
    res = client.post("/events/ingest", json=payload)
    assert res.status_code == 400


def test_partial_success_on_malformed(client):
    payload = [
        {
            "event_id": "good-1",
            "store_id": "STORE_PARTIAL",
            "camera_id": "CAM_ENTRY_01",
            "visitor_id": "VIS_P1",
            "event_type": "ENTRY",
            "timestamp": "2026-03-03T14:00:00Z",
            "confidence": 0.9,
        },
        {"event_id": "bad-1", "store_id": "STORE_PARTIAL"},
    ]
    res = client.post("/events/ingest", json=payload)
    assert res.status_code == 201
    body = res.json()
    assert body["ingested_count"] == 1
    assert len(body["errors"]) == 1
    assert body["success"] is False
