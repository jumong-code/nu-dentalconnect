$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

try {
    $venvPython = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
    if (!(Test-Path $venvPython)) {
        throw "Virtual environment not found. Run first_time_startup.ps1 first."
    }

    $env:FLASK_APP = "run.py"

    Write-Host
    Write-Host "  NU DentalConnect - Debug mode" -ForegroundColor Magenta
    Write-Host "  Development server with auto-reload on code changes." -ForegroundColor Cyan
    Write-Host
    Write-Host "  Open in your browser: http://127.0.0.1:5000" -ForegroundColor Green
    Write-Host "  Press Ctrl+C to stop the server" -ForegroundColor Yellow
    Write-Host

    & $venvPython -m flask run --debug
    if ($LASTEXITCODE -ne 0 -and $LASTEXITCODE -ne -1073741510) {
        throw "The server stopped unexpectedly (exit code $LASTEXITCODE)."
    }

    Write-Host
    Write-Host "  + Server stopped." -ForegroundColor Magenta

} catch {
    Write-Host
    Write-Host "  ! An error occurred:" -ForegroundColor Red
    Write-Host "  $($_.Exception.Message)" -ForegroundColor Yellow
    Write-Host
    Write-Host "  Press Enter to close this window..." -ForegroundColor DarkGray
    [void][System.Console]::ReadLine()
}