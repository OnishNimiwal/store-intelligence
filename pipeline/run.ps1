$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Out = Join-Path $Root "data\out\events.jsonl"
New-Item -ItemType Directory -Force -Path (Split-Path $Out) | Out-Null

$Layout = Join-Path $Root "store_layout.json"
python -m pipeline.detect --simulate --store-id STORE_BLR_002 --output $Out --store-layout $Layout
Write-Host "Pipeline output: $Out"
