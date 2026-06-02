# Copy API metadata into dataset folder (videos stay where they are)
$DatasetRoot = "C:\Users\NIKKA\Desktop\apex-retail-dataset"
$Repo = Split-Path -Parent $PSScriptRoot

$Files = @("store_layout.json", "pos_transactions.csv", "sample_events.jsonl", "assertions.py")
foreach ($name in $Files) {
    $src = Join-Path $Repo $name
    if (Test-Path $src) {
        Copy-Item $src (Join-Path $DatasetRoot $name) -Force
        Write-Host "Copied $name -> $DatasetRoot"
    }
}
Write-Host "Dataset folder ready. Videos: CAM 1.mp4 .. CAM 5.mp4"
