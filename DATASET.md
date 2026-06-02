# Dataset setup (your machine)

## Location

```
C:\Users\NIKKA\Desktop\apex-retail-dataset\
├── CAM 1.mp4          ← entry camera
├── CAM 2.mp4          ← floor camera
├── CAM 3.mp4          ← billing camera
├── CAM 4.mp4          ← extra floor angle
├── CAM 5.mp4          ← extra billing angle
├── store_layout.json  (copied from repo)
├── sample_events.jsonl
└── assertions.py
```

Configured in [`.env`](.env):

```
DATASET_ROOT=C:/Users/NIKKA/Desktop/apex-retail-dataset
```

## Full GPU processing (Google Colab)

For **whole videos** (not the 900-frame local test), use GPU on Colab. Step-by-step guide: **[docs/COLAB_GPU.md](docs/COLAB_GPU.md)**.

## Run pipeline on all clips

```powershell
cd C:\Users\NIKKA\OneDrive\Desktop\store-intelligence
.\.venv\Scripts\Activate.ps1
pip install -r requirements-pipeline.txt

# Full clips (slow on CPU — use Colab/GPU if available)
.\pipeline\run_dataset.ps1

# Quick test (~2–5 min per clip)
$env:PIPELINE_MAX_FRAMES = "900"
.\pipeline\run_dataset.ps1

python scripts\ingest_file.py data\out\events.jsonl
```

## Docker

1. Open **Docker Desktop** and wait until it says “Running”.
2. New PowerShell:

```powershell
cd C:\Users\NIKKA\OneDrive\Desktop\store-intelligence
& "C:\Program Files\Docker\Docker\resources\bin\docker.exe" compose up --build -d
python scripts\ingest_file.py sample_events.jsonl
curl http://localhost:8000/health
```

API: http://localhost:8000 · Dashboard: http://localhost:8501
