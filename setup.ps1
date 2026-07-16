# Acts XVII:XI Project — first-run setup
# Run from PowerShell: .\setup.ps1

Set-Location $PSScriptRoot

python -m venv .venv
.\.venv\Scripts\Activate.ps1

pip install -r requirements.txt

# Seed the sample verses (replace with your full KJV file when ready)
python loader.py sample_kjv.txt

Write-Host ""
Write-Host "Setup complete. Start the API with:"
Write-Host "  .\.venv\Scripts\Activate.ps1"
Write-Host "  python app.py"
