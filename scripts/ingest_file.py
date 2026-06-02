"""POST events from a JSONL file to the Store Intelligence API in batches."""
import argparse
import json
import os
import sys
from pathlib import Path

import requests

API_URL = os.getenv("API_URL", "http://localhost:8000")
BATCH_SIZE = 500


def load_events(path: Path) -> list:
    events = []
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                events.append(json.loads(line))
    return events


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("jsonl_path", type=str, help="Path to events JSONL file")
    parser.add_argument("--api-url", default=API_URL)
    args = parser.parse_args()

    path = Path(args.jsonl_path)
    if not path.exists():
        print(f"File not found: {path}", file=sys.stderr)
        sys.exit(1)

    events = load_events(path)
    url = f"{args.api_url.rstrip('/')}/events/ingest"
    total = 0
    for i in range(0, len(events), BATCH_SIZE):
        batch = events[i : i + BATCH_SIZE]
        response = requests.post(url, json=batch, timeout=60)
        if response.status_code >= 500:
            print(f"Server error {response.status_code}: {response.text}", file=sys.stderr)
            sys.exit(1)
        data = response.json()
        total += data.get("ingested_count", 0)
        print(f"Batch {i // BATCH_SIZE + 1}: ingested={data.get('ingested_count')} errors={len(data.get('errors', []))}")

    print(f"Done. Total ingested (incl. idempotent skips): {total}")


if __name__ == "__main__":
    main()
