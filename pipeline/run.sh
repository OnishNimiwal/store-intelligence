#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="$ROOT/data/out/events.jsonl"
mkdir -p "$(dirname "$OUT")"
python -m pipeline.detect --simulate --store-id "Store 2" --output "$OUT" --store-layout "$ROOT/store_layout.json"
echo "Pipeline output: $OUT"
