"""Fix Colab output where every event was marked is_staff=true (placeholder color bug)."""
import json
import sys
from pathlib import Path

path = Path(sys.argv[1] if len(sys.argv) > 1 else "data/out/events.jsonl")
lines = []
fixed = 0
for line in path.read_text(encoding="utf-8").splitlines():
    if not line.strip():
        continue
    e = json.loads(line)
    if e.get("is_staff"):
        e["is_staff"] = False
        fixed += 1
    lines.append(json.dumps(e))

path.write_text("\n".join(lines) + "\n", encoding="utf-8")
print(f"Updated {fixed} events in {path}")
print("Re-ingest: python scripts/ingest_file.py", path)
