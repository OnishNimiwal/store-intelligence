# Store Intelligence API

End-to-end retail analytics: CCTV → detection pipeline → FastAPI → live dashboard.

## Setup & Quickstart

### Method 1: Using Docker Compose (Recommended)

Running via Docker spins up both the FastAPI API service (port `8000`) and the premium Streamlit dashboard (port `8501`) instantly in isolated containers.

1. **Clone the repository and copy the environment variables**:
   ```bash
   git clone <your-repo-url>
   cd store-intelligence
   cp .env.example .env
   ```
2. **Start the containers** (automatically builds images and starts services):
   ```bash
   docker compose up --build -d
   ```
3. **Ingest event data to populate the empty database**:
   Since database files are gitignored, your initial database will be blank. Seed it from your host machine terminal:
   * **To use the actual Colab-generated tracking events (Detections from video) [Store 1]**:
     ```bash
     python scripts/ingest_file.py colab_events.jsonl
     ```
   * **To use generated sample events [Store 2]**:
     ```bash
     python scripts/generate_sample_events.py
     python scripts/ingest_file.py sample_events.jsonl
     ```
4. **Open the Live Dashboard**:
   Go to **`http://localhost:8501`** in your browser.
   * If you ingested **Colab events**, select **Store 1** in the sidebar.
   * If you ingested **sample events**, select **Store 2** in the sidebar.

*(Note: If you run into build errors on Windows OneDrive, right-click the project folder and select **Always keep on this device**, or run `.\scripts\docker_build.ps1` to rebuild).*

---

### Method 2: Running Locally (Without Docker)

1. **Clone the repository and set up a Python virtual environment**:
   ```bash
   git clone <your-repo-url>
   cd store-intelligence
   python -m venv .venv
   ```
2. **Activate the virtual environment**:
   * **Windows (Command Prompt / Git CMD)**:
     ```cmd
     .venv\Scripts\activate
     ```
   * **Windows (PowerShell)**:
     ```powershell
     .venv\Scripts\Activate.ps1
     ```
   * **Linux/macOS (Bash/Zsh)**:
     ```bash
     source .venv/bin/activate
     ```
3. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```
4. **Start the FastAPI server**:
   ```bash
   uvicorn app.main:app --port 8000
   ```
5. **In a new terminal window** (activate the `.venv` first), **ingest the events**:
   * **For actual Colab events [Store 1]**:
     ```bash
     python scripts/ingest_file.py colab_events.jsonl
     ```
   * **For sample events [Store 2]**:
     ```bash
     python scripts/generate_sample_events.py
     python scripts/ingest_file.py sample_events.jsonl
     ```
6. **Launch the Streamlit Dashboard**:
   ```bash
   streamlit run app/dashboard.py
   ```
   Access the dashboard at **`http://localhost:8501`** and select the active store location in the sidebar dropdown (**Store 1** for Colab events, **Store 2** for sample events).

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
