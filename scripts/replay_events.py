"""Replay JSONL events in real time (or accelerated) for live dashboard demo."""
import argparse
import json
import os
import time
from datetime import datetime
from pathlib import Path

import requests

API_URL = os.getenv("API_URL", "http://localhost:8000")


def parse_ts(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("jsonl_path", type=str)
    parser.add_argument("--speed", type=float, default=10.0, help="Time compression factor")
    parser.add_argument("--api-url", default=API_URL)
    args = parser.parse_args()

    path = Path(args.jsonl_path)
    events = []
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                events.append(json.loads(line))
    events.sort(key=lambda e: e["timestamp"])

    url = f"{args.api_url.rstrip('/')}/events/ingest"
    prev_ts = None
    for event in events:
        ts = parse_ts(event["timestamp"])
        if prev_ts is not None:
            delta = (ts - prev_ts).total_seconds() / args.speed
            if delta > 0:
                time.sleep(min(delta, 2.0))
        prev_ts = ts
        response = requests.post(url, json=[event], timeout=30)
        response.raise_for_status()
        print(f"Ingested {event['event_type']} {event['visitor_id']}")


if __name__ == "__main__":
    main()
