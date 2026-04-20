@echo off
setlocal enabledelayedexpansion

echo ========================================
echo   Muscle Power Desktop - Startup
echo ========================================
echo.

:: Ensure venv exists
if not exist ".venv" (
    echo [*] Creating virtual environment...
    uv venv
)

:: Install/update all dependencies including desktop extras
echo [*] Installing dependencies (including desktop extras)...
uv pip install -e ".[desktop]"

echo.
echo [*] Starting Muscle Power Desktop...
echo.

call .venv\Scripts\activate.bat
python -m muscle_power_desktop

pause
