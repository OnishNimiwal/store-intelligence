# Google Colab — full GPU pipeline guide

Use Colab when local CPU processing is too slow. Your 5 clips (~680 MB total) fit easily on Google Drive.

## Overview

```mermaid
flowchart LR
  PC[Videos_on_PC] --> Drive[Google_Drive]
  Drive --> Colab[Colab_GPU_YOLO]
  Colab --> JSONL[events.jsonl]
  JSONL --> PC2[Your_PC_ingest_API]
```

---

## Step 1 — Prepare files on your PC

From your machine you need:

| Item | Path |
|------|------|
| Videos | `C:\Users\NIKKA\Desktop\apex-retail-dataset\CAM 1.mp4` … `CAM 5.mp4` |
| Layout | `store-intelligence\store_layout.json` |
| Pipeline code | `store-intelligence\pipeline\` folder (`detect.py`, `tracker.py`, `emit.py`) |

Optional: zip the repo (exclude `.venv`, `data/`, `*.db`):

```powershell
cd C:\Users\NIKKA\OneDrive\Desktop
Compress-Archive -Path store-intelligence\pipeline, store-intelligence\store_layout.json -DestinationPath colab-upload.zip
```

---

## Step 2 — Upload to Google Drive

1. Go to [Google Drive](https://drive.google.com)
2. Create folder: `apex-retail-dataset`
3. Upload:
   - `CAM 1.mp4` … `CAM 5.mp4`
   - `store_layout.json`
4. Upload `colab-upload.zip` OR upload the whole `store-intelligence` project folder

---

## Step 3 — Open Colab and enable GPU

1. [Google Colab](https://colab.research.google.com) → **New notebook**
2. **Runtime → Change runtime type → Hardware accelerator: T4 GPU** → Save
3. Copy-paste the cells below **in order** (one cell per block)

---

## Step 4 — Colab cells (copy each block into a new cell)

### Cell 1 — GPU check

```python
!nvidia-smi
import torch
print("CUDA:", torch.cuda.is_available())
assert torch.cuda.is_available(), "Enable GPU: Runtime → Change runtime type → T4 GPU"
```

### Cell 2 — Mount Drive

```python
from google.colab import drive
drive.mount("/content/drive")

# EDIT this path to match your Drive folder
DATASET = "/content/drive/MyDrive/apex-retail-dataset"
PROJECT = "/content/store-intelligence"

import os
for f in ["CAM 1.mp4", "CAM 2.mp4", "store_layout.json"]:
    p = os.path.join(DATASET, f)
    print("OK" if os.path.exists(p) else "MISSING", p)
```

### Cell 3 — Install dependencies

```python
!pip install -q ultralytics opencv-python-headless numpy
```

### Cell 4 — Extract `collab-upload.zip` and fix `pipeline` import (REQUIRED)

Your Drive folder has videos + `collab-upload.zip`. The code lives **inside the zip**, not in Drive until you extract it.

```python
import zipfile, os, sys

ZIP = "/content/drive/MyDrive/apex-retail-dataset/collab-upload.zip"
PROJECT = "/content/store-intelligence"

# Extract zip (may create store-intelligence/ inside /content or inside zip root)
!rm -rf /content/store-intelligence
with zipfile.ZipFile(ZIP, "r") as z:
    z.extractall("/content")

# Find detect.py if path differs
if not os.path.isdir(f"{PROJECT}/pipeline"):
    for root, dirs, files in os.walk("/content"):
        if root.endswith("pipeline") and "detect.py" in files:
            PROJECT = os.path.dirname(root)
            break

print("PROJECT =", PROJECT)
assert os.path.isfile(f"{PROJECT}/pipeline/detect.py"), "pipeline/detect.py not found — check zip contents"

# Required so `python -m pipeline.detect` works
sys.path.insert(0, PROJECT)
os.chdir(PROJECT)
!ls -la pipeline/
```

Use layout from Drive (same folder as videos):

```python
DATASET = "/content/drive/MyDrive/apex-retail-dataset"
LAYOUT = f"{DATASET}/store_layout.json"   # NOT /content/store-intelligence/... unless you copied it
```

**Option B — clone your Git repo (after you push to GitHub):**

```python
!git clone https://github.com/YOUR_USER/store-intelligence.git /content/store-intelligence
%cd /content/store-intelligence
```

**Option C — minimal upload (paste pipeline files manually):**

Upload `detect.py`, `tracker.py`, `emit.py` into `/content/store-intelligence/pipeline/` and `store_layout.json` into `/content/store-intelligence/`.

```python
%cd /content/store-intelligence
!ls -R
```

### Cell 5 — Run full pipeline (recommended: `colab_run_all.py`)

**Use this instead of `python -m pipeline.detect` in subprocess** — it avoids `ModuleNotFoundError` when the zip extracts to `/content/collab-upload/store-intelligence`.

```python
PROJECT = "/content/collab-upload/store-intelligence"  # from Cell 4 print
DATASET = "/content/drive/MyDrive/apex-retail-dataset"
LAYOUT = f"{DATASET}/store_layout.json"

%cd {PROJECT}
!python scripts/colab_run_all.py --dataset "{DATASET}" --layout "{LAYOUT}" --frame-skip 2
```

Optional quick test (~1 min per clip): add `--max-frames 900`

Save to Drive:

```python
!cp {PROJECT}/data/out/events.jsonl {DATASET}/events.jsonl
```

---

### Cell 5 (alternate) — subprocess loop (only if PROJECT path is correct)

### Cell 5b — Run full pipeline (all 5 videos, no frame limit)

```python
import os, subprocess, sys

DATASET = "/content/drive/MyDrive/apex-retail-dataset"  # EDIT
PROJECT = "/content/store-intelligence"
LAYOUT = os.path.join(PROJECT, "store_layout.json")
if not os.path.exists(LAYOUT):
    LAYOUT = os.path.join(DATASET, "store_layout.json")

OUT = f"{PROJECT}/data/out/events.jsonl"
os.makedirs(os.path.dirname(OUT), exist_ok=True)
if os.path.exists(OUT):
    os.remove(OUT)

CLIPS = [
    ("CAM 1.mp4", "CAM_ENTRY_01"),
    ("CAM 2.mp4", "CAM_FLOOR_02"),
    ("CAM 3.mp4", "CAM_BILLING_03"),
    ("CAM 4.mp4", "CAM_FLOOR_02"),
    ("CAM 5.mp4", "CAM_BILLING_03"),
]

os.chdir(PROJECT)
sys.path.insert(0, PROJECT)
env = os.environ.copy()
env["PYTHONPATH"] = PROJECT

append = False
for fname, camera in CLIPS:
    video = os.path.join(DATASET, fname)
    if not os.path.exists(video):
        print("SKIP missing:", video)
        continue
    cmd = [
        sys.executable, "-m", "pipeline.detect",
        "--video", video,
        "--store-layout", LAYOUT,
        "--store-id", "Store 2",
        "--camera-id", camera,
        "--clip-start", "2026-03-03T14:00:00Z",
        "--output", OUT,
        "--frame-skip", "2",   # 2=every 2nd frame; use 3 for faster run
    ]
    if append:
        cmd.append("--append")
    append = True
    print("\n===", fname, "->", camera, "===")
    subprocess.run(cmd, check=True, cwd=PROJECT, env=env)

print("\nDone. Events:", OUT)
!wc -l {OUT}
```

**Full 20-minute clips at 30 fps with `frame-skip=2`:** expect roughly **1–3 hours total** on T4 for all 5 files. Colab free tier may disconnect — use **Runtime → Run all** and keep the tab open, or save checkpoints to Drive (see Cell 6).

### Cell 6 — Save copy to Drive (so you don’t lose work)

```python
import shutil
DRIVE_OUT = "/content/drive/MyDrive/apex-retail-dataset/events.jsonl"
shutil.copy(OUT, DRIVE_OUT)
print("Saved to", DRIVE_OUT)
```

### Cell 7 — Download to your PC

```python
from google.colab import files
files.download(OUT)
```

Save as: `C:\Users\NIKKA\OneDrive\Desktop\store-intelligence\data\out\events.jsonl`

---

## Step 5 — Ingest on your PC (after download)

```powershell
cd C:\Users\NIKKA\OneDrive\Desktop\store-intelligence
.\.venv\Scripts\Activate.ps1
# API running (Docker or uvicorn)
python scripts\ingest_file.py data\out\events.jsonl
curl.exe http://localhost:8000/stores/"Store 2"/metrics
```

---

## Tips

| Topic | Recommendation |
|-------|----------------|
| **Session timeout** | Copy `events.jsonl` to Drive after each video (add `--append` loop with Drive copy per clip) |
| **Speed vs quality** | `--frame-skip 3` faster; `2` more accurate |
| **RAM** | Process one video at a time (the loop already does) |
| **Challenge full set** | If you later get 15 clips (5 stores × 3 cameras), extend `CLIPS` list the same way |
| **Do not** | Commit `.mp4` or huge `events.jsonl` to Git |

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `CUDA: False` | Runtime → T4 GPU, then Runtime → Restart session |
| `No module named pipeline` | Run Cell 4: extract `collab-upload.zip`, set `PYTHONPATH`, `cwd=PROJECT` |
| `Video not found` | Fix `DATASET` path after `drive.mount` |
| Colab disconnects | Re-run from last video with `--append` and existing `events.jsonl` on Drive |

---

## What you already ran locally

You used `$env:PIPELINE_MAX_FRAMES = "900"` — that only processes ~30 seconds per clip. On Colab, **omit `--max-frames`** (Cell 5 above) for the **whole** video.
