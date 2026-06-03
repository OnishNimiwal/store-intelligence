# Store Intelligence API

End-to-end retail analytics: CCTV → detection pipeline → FastAPI → live dashboard.

## Quick start (5 commands)

```bash
git clone <your-repo-url>
cd store-intelligence
cp .env.example .env
docker compose up --build
```

**Docker build fails with `input/output error` and `.venv` in the path?**  
The repo includes a [`.dockerignore`](.dockerignore) so local `.venv` is not copied into the image. Run:

```powershell
docker compose down
docker builder prune -f
docker compose build --no-cache
docker compose up -d
```

If you see **`invalid file request app/__init__.py`**, the repo is on **OneDrive** (files are cloud placeholders). Use:

```powershell
.\scripts\docker_build.ps1
```

Or: right-click the `store-intelligence` folder → **Always keep on this device**, then rebuild.

If it still fails: free disk space, restart Docker Desktop, or run the API locally (see below).

In another terminal:

```bash
python scripts/generate_sample_events.py
python scripts/ingest_file.py sample_events.jsonl
curl http://localhost:8000/stores/"Store 2"/metrics
```

## Detection pipeline

Your dataset path is configured in `.env`:

```env
DATASET_ROOT=C:/Users/NIKKA/Desktop/apex-retail-dataset
```

Expected videos: `CAM 1.mp4` … `CAM 5.mp4` (metadata files live in the repo; run `scripts/setup_dataset.ps1` to copy copies into the dataset folder).

| File | Camera role |
|------|----------------|
| CAM 1.mp4 | CAM_ENTRY_01 |
| CAM 2.mp4 | CAM_FLOOR_02 |
| CAM 3.mp4 | CAM_BILLING_03 |
| CAM 4–5.mp4 | Extra floor/billing angles |

Process **all** local clips:

```powershell
.\.venv\Scripts\Activate.ps1
pip install -r requirements-pipeline.txt
.\pipeline\run_dataset.ps1
python scripts\ingest_file.py data\out\events.jsonl
```

Quick test (~1 min per clip on CPU): `$env:PIPELINE_MAX_FRAMES=900; .\pipeline\run_dataset.ps1`

Pipeline output goes to **gitignored** `data/out/events.jsonl`.

```bash
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
.\pipeline\run.ps1
python scripts/ingest_file.py data/out/events.jsonl
```

With real video:

```bash
python -m pipeline.detect --video path/to/clip.mp4 --store-id "Store 2" --camera-id CAM_ENTRY_01 --output data/out/events.jsonl
```

## Live dashboard (Part E bonus)

- **Web UI:** http://localhost:8501 (Streamlit via `docker compose`)
- **Terminal:** `python scripts/terminal_dashboard.py`
- **Replay:** `python scripts/replay_events.py sample_events.jsonl --speed 20`

## Tests & assertions

```bash
pip install -r requirements.txt
pytest --cov=app --cov-report=term-missing
python assertions.py
python scripts/validate_sample_events.py
```

## API endpoints

| Method | Path |
|--------|------|
| POST | `/events/ingest` |
| GET | `/stores/{store_id}/metrics` |
| GET | `/stores/{store_id}/funnel` |
| GET | `/stores/{store_id}/heatmap` |
| GET | `/stores/{store_id}/anomalies` |
| GET | `/health` |

## Documentation

- [DESIGN.md](DESIGN.md) — architecture and AI-assisted decisions
- [CHOICES.md](CHOICES.md) — model, schema, and API trade-offs
