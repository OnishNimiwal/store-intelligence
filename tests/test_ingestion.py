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


def test_format2_normalization(client):
    payload = [
        {
            "event_type": "entry",
            "id_token": "ID_99001",
            "store_code": "store_1076",
            "camera_id": "cam1",
            "event_timestamp": "2026-03-08T18:10:05.120000",
            "is_staff": False,
        },
        {
            "event_type": "zone_entered",
            "track_id": 901,
            "store_id": "ST1076",
            "camera_id": "CAM2",
            "zone_id": "PURPLLE_MUM_1076_Z01",
            "zone_name": "Left Shelf",
            "event_time": "2026-03-08T18:10:45.280000",
        },
        {
            "event_type": "queue_completed",
            "track_id": 902,
            "store_id": "ST1076",
            "camera_id": "PURPLLE_MUM_1076_CAM6",
            "zone_id": "PURPLLE_MUM_1076_Z_BILLING_01",
            "zone_name": "Billing Counter Queue",
            "queue_join_ts": "2026-03-08T18:13:05",
            "queue_exit_ts": "2026-03-08T18:15:31",
            "wait_seconds": 146,
            "queue_position_at_join": 2,
            "abandoned": False,
        }
    ]
    res = client.post("/events/ingest", json=payload)
    assert res.status_code == 201
    body = res.json()
    # The third event (queue_completed) normalizes into 2 separate events: join and exit
    # So total ingested count should be 1 (entry) + 1 (zone_entered) + 2 (queue completed: join + exit) = 4 events!
    assert body["ingested_count"] == 4
    assert len(body["errors"]) == 0
    assert body["success"] is True


def test_ingest_idempotency(client):
    payload = [
        {
            "event_id": "idemp-1",
            "store_id": "STORE_BLR_002",
            "camera_id": "CAM_ENTRY_01",
            "visitor_id": "VIS_IDEMP_01",
            "event_type": "ENTRY",
            "timestamp": "2026-03-03T14:00:00Z",
            "confidence": 0.9,
        }
    ]
    # First ingest
    res1 = client.post("/events/ingest", json=payload)
    assert res1.status_code == 201
    assert res1.json()["ingested_count"] == 1
    assert res1.json()["success"] is True

    # Second identical ingest
    res2 = client.post("/events/ingest", json=payload)
    assert res2.status_code == 201
    assert res2.json()["ingested_count"] == 1
    assert res2.json()["success"] is True


