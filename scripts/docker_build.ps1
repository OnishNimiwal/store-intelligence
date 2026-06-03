# Build Docker images from a non-OneDrive copy (fixes "invalid file request app/__init__.py")
$ErrorActionPreference = "Stop"

$Source = "C:\Users\NIKKA\OneDrive\Desktop\store-intelligence"
$BuildDir = "C:\store-intelligence-docker"

Write-Host "Copying project to $BuildDir (materializes OneDrive files)..."
if (Test-Path $BuildDir) { Remove-Item $BuildDir -Recurse -Force }
New-Item -ItemType Directory -Path $BuildDir | Out-Null

$excludeDirs = @(".venv", "data", ".git", "__pycache__", ".pytest_cache", "htmlcov", ".cursor")
robocopy $Source $BuildDir /E /XD $excludeDirs /XF *.mp4 *.db *.jsonl /NFL /NDL /NJH /NJS /nc /ns /np | Out-Null
if ($LASTEXITCODE -ge 8) { throw "robocopy failed with code $LASTEXITCODE" }

Push-Location $BuildDir
try {
    Write-Host "Building images..."
    docker compose down 2>$null
    docker compose build api
    docker compose up -d api
    docker compose up -d dashboard
    Write-Host ""
    Write-Host "OK. API: http://localhost:8000  Dashboard: http://localhost:8501"
    Write-Host "Ingest (from original folder):"
    Write-Host "  python scripts\ingest_file.py data\out\events.jsonl"
} finally {
    Pop-Location
}
