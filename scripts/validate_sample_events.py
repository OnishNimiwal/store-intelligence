"""Validate all lines in sample_events.jsonl against EventSchema."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.models import EventSchema


def main():
    candidates = [
        ROOT / "sample_events.jsonl",
        Path(sys.argv[1]) if len(sys.argv) > 1 else None,
    ]
    path = next((p for p in candidates if p and p.exists()), None)
    if not path:
        print("sample_events.jsonl not found. Run: python scripts/generate_sample_events.py")
        sys.exit(1)

    failed = 0
    with open(path, encoding="utf-8") as handle:
        for i, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                EventSchema(**json.loads(line))
            except Exception as exc:
                failed += 1
                print(f"Line {i}: FAIL - {exc}")
    total = sum(1 for _ in open(path, encoding="utf-8") if _.strip())
    print(f"Validated {total} events, {failed} failures")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
