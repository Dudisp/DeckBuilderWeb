# Build script for packaging the Deck Builder app as a Windows executable
# Uses PyInstaller and PyWebView

Write-Host "=== Deck Builder - Windows Build Script ===" -ForegroundColor Cyan
Write-Host ""

# Check if virtual environment exists
if (-not (Test-Path "venv")) {
    Write-Host "Virtual environment not found. Creating one..." -ForegroundColor Yellow
    python -m venv venv
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Failed to create virtual environment" -ForegroundColor Red
        exit 1
    }
}

# Activate virtual environment
Write-Host "Activating virtual environment..." -ForegroundColor Green
& ".\venv\Scripts\Activate.ps1"

# Install/upgrade dependencies
Write-Host "Installing dependencies..." -ForegroundColor Green
pip install --upgrade pip
pip install -r requirements.txt
pip install pyinstaller

# Clean previous builds
Write-Host "Cleaning previous builds..." -ForegroundColor Green
if (Test-Path "build") { Remove-Item -Recurse -Force "build" }
if (Test-Path "dist") { Remove-Item -Recurse -Force "dist" }
if (Test-Path "__pycache__") { Remove-Item -Recurse -Force "__pycache__" }

# Build with PyInstaller
Write-Host "Building executable with PyInstaller..." -ForegroundColor Green
pyinstaller --clean --noconfirm run_desktop.spec

if ($LASTEXITCODE -eq 0) {
    Write-Host ""
    Write-Host "=== Build Successful! ===" -ForegroundColor Green
    Write-Host "Executable location: dist\run_desktop.exe" -ForegroundColor Cyan
    Write-Host ""

    # Optional: Test the executable
    $response = Read-Host "Would you like to test the executable? (y/n)"
    if ($response -eq "y" -or $response -eq "Y") {
        Write-Host "Launching executable..." -ForegroundColor Green
        Start-Process -FilePath ".\dist\run_desktop.exe"
    }
} else {
    Write-Host ""
    Write-Host "=== Build Failed ===" -ForegroundColor Red
    Write-Host "Check the output above for errors" -ForegroundColor Yellow
    exit 1
}

