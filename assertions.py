"""
Example acceptance assertions for Store Intelligence API.
Run with API up: python assertions.py
"""
import os
import sys

import requests

API_URL = os.getenv("API_URL", "http://localhost:8000")
STORE_ID = "Store 2"
passed = 0
failed = 0


def check(name: str, condition: bool, detail: str = ""):
    global passed, failed
    if condition:
        passed += 1
        print(f"  PASS: {name}")
    else:
        failed += 1
        print(f"  FAIL: {name} — {detail}")


def main():
    print(f"Running assertions against {API_URL}\n")

    # 1. Health
    r = requests.get(f"{API_URL}/health", timeout=10)
    check("GET /health returns 200", r.status_code == 200)
    health = r.json()
    check("health has status field", "status" in health)

    # 2. Ingest sample batch
    sample = {
        "event_id": "assert-test-entry-001",
        "store_id": STORE_ID,
        "camera_id": "CAM_ENTRY_01",
        "visitor_id": "VIS_ASSERT_01",
        "event_type": "ENTRY",
        "timestamp": "2026-03-03T14:10:00Z",
        "zone_id": None,
        "dwell_ms": 0,
        "is_staff": False,
        "confidence": 0.92,
        "metadata": {"session_seq": 1},
    }
    r = requests.post(f"{API_URL}/events/ingest", json=[sample], timeout=10)
    check("POST /events/ingest returns 201", r.status_code == 201, r.text)

    # 3. Idempotent re-ingest
    r2 = requests.post(f"{API_URL}/events/ingest", json=[sample], timeout=10)
    check("Idempotent re-ingest returns 201", r2.status_code == 201)
    check("Idempotent ingested_count >= 1", r2.json().get("ingested_count", 0) >= 1)

    # 4. Metrics
    r = requests.get(f"{API_URL}/stores/{STORE_ID}/metrics", timeout=10)
    check("GET /metrics returns 200", r.status_code == 200)
    m = r.json()
    check("metrics has unique_visitors", "unique_visitors" in m)
    check("metrics has conversion_rate", "conversion_rate" in m)
    check("conversion_rate is numeric 0-1", 0 <= m.get("conversion_rate", -1) <= 1)

    # 5. Funnel
    r = requests.get(f"{API_URL}/stores/{STORE_ID}/funnel", timeout=10)
    check("GET /funnel returns 200", r.status_code == 200)
    stages = {s["stage_name"]: s for s in r.json().get("stages", [])}
    check("funnel has Entry stage", "Entry" in stages)

    # 6. Heatmap
    r = requests.get(f"{API_URL}/stores/{STORE_ID}/heatmap", timeout=10)
    check("GET /heatmap returns 200", r.status_code == 200)
    check("heatmap has data_confidence", "data_confidence" in r.json())

    # 7. Anomalies
    r = requests.get(f"{API_URL}/stores/{STORE_ID}/anomalies", timeout=10)
    check("GET /anomalies returns 200", r.status_code == 200)
    check("anomalies is list", isinstance(r.json().get("anomalies"), list))

    # 8. Empty store
    r = requests.get(f"{API_URL}/stores/STORE_NONEXISTENT_XYZ/metrics", timeout=10)
    check("empty store metrics returns 200", r.status_code == 200)
    check("empty store zero visitors", r.json().get("unique_visitors") == 0)

    print(f"\nResults: {passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
