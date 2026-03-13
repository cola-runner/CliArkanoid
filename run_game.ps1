$python = "C:\Users\16498\AppData\Local\Programs\Python\Python313\python.exe"

if (-not (Test-Path $python)) {
    Write-Error "Compatible Python runtime not found at $python"
    exit 1
}

& $python "$PSScriptRoot\pinball.py"
