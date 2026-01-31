# Build script for PrusaTray Windows executable
# Creates a standalone .exe file using PyInstaller

param(
    [switch]$Clean,
    [switch]$SkipTests
)

$ErrorActionPreference = "Stop"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "PrusaTray Windows Build Script" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Clean previous builds if requested
if ($Clean) {
    Write-Host "Cleaning previous builds..." -ForegroundColor Yellow
    Remove-Item -Path "build" -Recurse -Force -ErrorAction SilentlyContinue
    Remove-Item -Path "dist" -Recurse -Force -ErrorAction SilentlyContinue
    Remove-Item -Path "*.spec" -Force -ErrorAction SilentlyContinue
    Write-Host "âœ“ Cleaned" -ForegroundColor Green
    Write-Host ""
}

# Check if virtual environment exists
if (-not (Test-Path ".venv")) {
    Write-Host "Creating virtual environment..." -ForegroundColor Yellow
    python -m venv .venv
    Write-Host "âœ“ Virtual environment created" -ForegroundColor Green
    Write-Host ""
}

# Activate virtual environment
Write-Host "Activating virtual environment..." -ForegroundColor Yellow
& .\.venv\Scripts\Activate.ps1

# Install/upgrade dependencies
Write-Host "Installing dependencies..." -ForegroundColor Yellow
python -m pip install --upgrade pip
pip install -r requirements.txt
Write-Host "âœ“ Dependencies installed" -ForegroundColor Green
Write-Host ""

# Run smoke tests unless skipped
if (-not $SkipTests) {
    Write-Host "Running smoke tests..." -ForegroundColor Yellow
    
    # Test imports
    Write-Host "  Testing imports..." -ForegroundColor Gray
    python -c "import tray_prusa; print('âœ“ Imports OK')"
    if ($LASTEXITCODE -ne 0) {
        Write-Host "âœ— Import test failed" -ForegroundColor Red
        exit 1
    }
    
    # Test parser
    Write-Host "  Testing parser..." -ForegroundColor Gray
    python -m unittest test_parser -v
    if ($LASTEXITCODE -ne 0) {
        Write-Host "âœ— Parser tests failed" -ForegroundColor Red
        exit 1
    }
    
    Write-Host "âœ“ All tests passed" -ForegroundColor Green
    Write-Host ""
}

# Build executable with PyInstaller
Write-Host "Building Windows executable..." -ForegroundColor Yellow
Write-Host "  This may take a few minutes..." -ForegroundColor Gray
Write-Host ""

pyinstaller `
    --name=PrusaTray `
    --onefile `
    --windowed `
    --noconsole `
    --icon=NONE `
    "--add-data=tray_prusa;tray_prusa" `
    --hidden-import=PySide6.QtCore `
    --hidden-import=PySide6.QtGui `
    --hidden-import=PySide6.QtWidgets `
    --hidden-import=PySide6.QtNetwork `
    --hidden-import=keyring.backends.Windows `
    --collect-all=keyring `
    --noconfirm `
    tray_prusa/__main__.py

if ($LASTEXITCODE -ne 0) {
    Write-Host "âœ— Build failed" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "âœ“ Build completed successfully!" -ForegroundColor Green
Write-Host ""
Write-Host "Executable location:" -ForegroundColor Cyan
Write-Host "  $(Resolve-Path 'dist\PrusaTray.exe')" -ForegroundColor White
Write-Host ""

# Show file size
$exeSize = (Get-Item "dist\PrusaTray.exe").Length / 1MB
Write-Host "File size: $([math]::Round($exeSize, 2)) MB" -ForegroundColor Gray
Write-Host ""

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Build Complete!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "To run the executable:" -ForegroundColor Yellow
Write-Host '  .\dist\PrusaTray.exe' -ForegroundColor White
Write-Host ""
