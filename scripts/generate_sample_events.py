"""Generate sample_events.jsonl (200 events) for schema validation and API testing."""
import json
import random
import uuid
from datetime import datetime, timedelta
from pathlib import Path

STORE_ID = "Store 2"
OUTPUT = Path(__file__).resolve().parent.parent / "sample_events.jsonl"
EVENT_TYPES = [
    "ENTRY",
    "EXIT",
    "ZONE_ENTER",
    "ZONE_EXIT",
    "ZONE_DWELL",
    "BILLING_QUEUE_JOIN",
    "BILLING_QUEUE_ABANDON",
    "REENTRY",
]
ZONES = ["SKINCARE", "COSMETICS", "BILLING"]
SKU = {"SKINCARE": "MOISTURISER", "COSMETICS": "LIPSTICK", "BILLING": "CHECKOUT"}


def main():
    events = []
    base = datetime(2026, 3, 3, 14, 0, 0)
    visitors = [f"VIS_{i:04d}" for i in range(1, 41)]

    for vidx, visitor in enumerate(visitors):
        is_staff = vidx % 8 == 0
        t = base + timedelta(minutes=vidx * 3)
        session_seq = 1

        def add(event_type, **kwargs):
            nonlocal session_seq, t
            zone_id = kwargs.pop("zone_id", None)
            events.append(
                {
                    "event_id": str(uuid.uuid4()),
                    "store_id": STORE_ID,
                    "camera_id": kwargs.pop("camera_id", "CAM_ENTRY_01"),
                    "visitor_id": visitor,
                    "event_type": event_type,
                    "timestamp": t.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "zone_id": zone_id,
                    "dwell_ms": kwargs.pop("dwell_ms", 0),
                    "is_staff": is_staff,
                    "confidence": round(random.uniform(0.72, 0.98), 2),
                    "metadata": {
                        "queue_depth": kwargs.pop("queue_depth", None),
                        "sku_zone": SKU.get(zone_id) if zone_id else None,
                        "session_seq": session_seq,
                    },
                }
            )
            session_seq += 1

        add("ENTRY")
        t += timedelta(seconds=30)
        zone = ZONES[vidx % 2]
        add("ZONE_ENTER", zone_id=zone, camera_id="CAM_FLOOR_02")
        t += timedelta(seconds=40)
        add("ZONE_DWELL", zone_id=zone, dwell_ms=30000, camera_id="CAM_FLOOR_02")
        if not is_staff and vidx % 4 != 0:
            t += timedelta(minutes=2)
            add(
                "BILLING_QUEUE_JOIN",
                zone_id="BILLING",
                camera_id="CAM_BILLING_03",
                queue_depth=random.randint(1, 5),
            )
            if vidx % 9 == 0:
                t += timedelta(minutes=1)
                add("BILLING_QUEUE_ABANDON", zone_id="BILLING", camera_id="CAM_BILLING_03")
        t += timedelta(minutes=1)
        add("EXIT")
        if vidx % 11 == 0:
            t += timedelta(minutes=5)
            add("REENTRY")

    while len(events) < 200:
        visitor = random.choice(visitors)
        zone = random.choice(ZONES)
        t = base + timedelta(minutes=random.randint(0, 180))
        events.append(
            {
                "event_id": str(uuid.uuid4()),
                "store_id": STORE_ID,
                "camera_id": "CAM_FLOOR_02",
                "visitor_id": visitor,
                "event_type": random.choice(["ZONE_ENTER", "ZONE_DWELL", "ZONE_EXIT"]),
                "timestamp": t.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "zone_id": zone,
                "dwell_ms": random.choice([0, 15000, 30000, 45000]),
                "is_staff": False,
                "confidence": round(random.uniform(0.7, 0.95), 2),
                "metadata": {
                    "queue_depth": None,
                    "sku_zone": SKU[zone],
                    "session_seq": random.randint(1, 8),
                },
            }
        )

    events = events[:200]
    with open(OUTPUT, "w", encoding="utf-8") as handle:
        for event in events:
            handle.write(json.dumps(event) + "\n")
    print(f"Wrote {len(events)} events to {OUTPUT}")


if __name__ == "__main__":
    main()
