# PROMPT: Generate pytest tests for event schema validation, staff flags, and invalid type rejection.
# CHANGES MADE: Added catalogue event types list and metadata optional fields test.

import pytest

from app.models import EventSchema

CATALOGUE = [
    "ENTRY",
    "EXIT",
    "ZONE_ENTER",
    "ZONE_EXIT",
    "ZONE_DWELL",
    "BILLING_QUEUE_JOIN",
    "BILLING_QUEUE_ABANDON",
    "REENTRY",
]


def test_event_schema_validation_happy_path():
    raw = {
        "event_id": "8905b221-a0a3-48df-b4a1-db9b015175e1",
        "store_id": "Store 2",
        "camera_id": "CAM_ENTRY_01",
        "visitor_id": "VIS_c8a2f1",
        "event_type": "ZONE_DWELL",
        "timestamp": "2026-03-03T14:22:10Z",
        "zone_id": "SKINCARE",
        "dwell_ms": 8400,
        "is_staff": False,
        "confidence": 0.91,
        "metadata": {"queue_depth": None, "sku_zone": "MOISTURISER", "session_seq": 5},
    }
    validated = EventSchema(**raw)
    assert validated.event_type in CATALOGUE
    assert validated.metadata.sku_zone == "MOISTURISER"


def test_event_schema_validation_invalid_type():
    invalid = {
        "event_id": "8905b221-a0a3-48df-b4a1-db9b015175e1",
        "store_id": "Store 2",
        "camera_id": "CAM_ENTRY_01",
        "visitor_id": "VIS_c8a2f1",
        "event_type": "ZONE_DWELL",
        "timestamp": "not-a-timestamp",
        "dwell_ms": "bad",
        "is_staff": "maybe",
        "confidence": "high",
    }
    with pytest.raises(Exception):
        EventSchema(**invalid)


def test_staff_flag_propagation():
    raw = {
        "event_id": "a189fcd2-a0e1-4cbb-a309-fa938e21a8d0",
        "store_id": "Store 2",
        "camera_id": "CAM_FLOOR_02",
        "visitor_id": "VIS_staff_01",
        "event_type": "ZONE_ENTER",
        "timestamp": "2026-03-03T14:25:00Z",
        "zone_id": "SKINCARE",
        "is_staff": True,
        "confidence": 0.99,
        "metadata": {"session_seq": 1},
    }
    assert EventSchema(**raw).is_staff is True
