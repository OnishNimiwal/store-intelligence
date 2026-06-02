"""
Run all CCTV clips — designed for Google Colab (avoids `python -m pipeline.detect` path issues).

Usage on Colab (after extracting zip):
  %cd /content/collab-upload/store-intelligence
  !python scripts/colab_run_all.py \\
      --dataset /content/drive/MyDrive/apex-retail-dataset \\
      --layout /content/drive/MyDrive/apex-retail-dataset/store_layout.json
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def run_one(video: str, layout: str, camera: str, output: str, append: bool, frame_skip: int, max_frames: int) -> None:
    import pipeline.detect as detect_module

    argv = [
        "detect",
        "--video",
        video,
        "--store-layout",
        layout,
        "--store-id",
        "STORE_BLR_002",
        "--camera-id",
        camera,
        "--output",
        output,
        "--frame-skip",
        str(frame_skip),
    ]
    if append:
        argv.append("--append")
    if max_frames > 0:
        argv.extend(["--max-frames", str(max_frames)])

    old = sys.argv
    try:
        sys.argv = argv
        detect_module.main()
    finally:
        sys.argv = old


def main() -> None:
    parser = argparse.ArgumentParser(description="Colab batch runner for all CAM clips")
    parser.add_argument(
        "--dataset",
        default="/content/drive/MyDrive/apex-retail-dataset",
        help="Folder containing CAM 1.mp4 .. CAM 5.mp4",
    )
    parser.add_argument(
        "--layout",
        default="/content/drive/MyDrive/apex-retail-dataset/store_layout.json",
    )
    parser.add_argument(
        "--output",
        default=str(ROOT / "data" / "out" / "events.jsonl"),
    )
    parser.add_argument("--frame-skip", type=int, default=2)
    parser.add_argument("--max-frames", type=int, default=0, help="0 = full video")
    args = parser.parse_args()

    dataset = Path(args.dataset)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        output.unlink()

    clips = [
        ("CAM 1.mp4", "CAM_ENTRY_01"),
        ("CAM 2.mp4", "CAM_FLOOR_02"),
        ("CAM 3.mp4", "CAM_BILLING_03"),
        ("CAM 4.mp4", "CAM_FLOOR_02"),
        ("CAM 5.mp4", "CAM_BILLING_03"),
    ]

    append = False
    for fname, camera in clips:
        video = dataset / fname
        if not video.exists():
            print(f"SKIP missing: {video}")
            continue
        print(f"\n=== {fname} -> {camera} ===")
        run_one(
            str(video),
            args.layout,
            camera,
            str(output),
            append=append,
            frame_skip=args.frame_skip,
            max_frames=args.max_frames,
        )
        append = True

    if output.exists():
        lines = sum(1 for _ in output.open(encoding="utf-8"))
        print(f"\nDone: {output} ({lines} events)")
    else:
        print("\nNo output file created.")


if __name__ == "__main__":
    main()
