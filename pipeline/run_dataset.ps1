# Process all videos in apex-retail-dataset
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$DatasetRoot = if ($env:DATASET_ROOT) { $env:DATASET_ROOT } else { "C:\Users\NIKKA\Desktop\apex-retail-dataset" }
$Layout = if ($env:STORE_LAYOUT_PATH) { $env:STORE_LAYOUT_PATH } else { Join-Path $Root "store_layout.json" }
$Out = Join-Path $Root "data\out\events.jsonl"
$StoreId = "STORE_BLR_002"
$ClipStart = "2026-03-03T14:00:00Z"
$MaxFrames = if ($env:PIPELINE_MAX_FRAMES) { [int]$env:PIPELINE_MAX_FRAMES } else { 0 }
$FrameSkip = if ($env:PIPELINE_FRAME_SKIP) { [int]$env:PIPELINE_FRAME_SKIP } else { 3 }

$Clips = @(
    @{ File = "CAM 1.mp4"; Camera = "CAM_ENTRY_01" },
    @{ File = "CAM 2.mp4"; Camera = "CAM_FLOOR_02" },
    @{ File = "CAM 3.mp4"; Camera = "CAM_BILLING_03" },
    @{ File = "CAM 4.mp4"; Camera = "CAM_FLOOR_02" },
    @{ File = "CAM 5.mp4"; Camera = "CAM_BILLING_03" }
)

New-Item -ItemType Directory -Force -Path (Split-Path $Out) | Out-Null
if (Test-Path $Out) { Remove-Item $Out }

$idx = 0
foreach ($clip in $Clips) {
    $video = Join-Path $DatasetRoot $clip.File
    if (-not (Test-Path $video)) {
        Write-Warning "Skip missing: $video"
        continue
    }
    Write-Host "`n=== $($clip.File) -> $($clip.Camera) ==="
    $pyArgs = @(
        "-m", "pipeline.detect",
        "--video", $video,
        "--store-layout", $Layout,
        "--store-id", $StoreId,
        "--camera-id", $clip.Camera,
        "--clip-start", $ClipStart,
        "--output", $Out,
        "--frame-skip", $FrameSkip
    )
    if ($MaxFrames -gt 0) { $pyArgs += @("--max-frames", "$MaxFrames") }
    if ($idx -gt 0) { $pyArgs += "--append" }
    $idx++
    & python @pyArgs
}

Write-Host "`nOutput: $Out"
Write-Host "Next: python scripts/ingest_file.py `"$Out`""
