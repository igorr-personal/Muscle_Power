@echo off
setlocal enabledelayedexpansion

echo ========================================
echo   Muscle Power - Startup Script
echo ========================================
echo.

:: Check if UV is installed
where uv >nul 2>nul
if %errorlevel% neq 0 (
    echo [!] UV not found. Installing UV...
    powershell -ExecutionPolicy Bypass -c "irm https://astral.sh/uv/install.ps1 | iex"
    echo [+] UV installed. Please restart this script.
    pause
    exit /b
)

:: Check if virtual environment exists
if not exist ".venv" (
    echo [*] Creating virtual environment...
    uv venv
)

:: Install/update dependencies
echo [*] Installing dependencies...
uv pip install -e ".[dev]"
::uv pip install streamlit-autorefresh  <-- Add this line right here

:: Check for .env file
if not exist ".env" (
    if exist ".env.example" (
        echo [!] .env file not found. Copying from .env.example...
        copy .env.example .env
    )
)

:: Activate virtual environment and run
echo [*] Starting Muscle Power...
echo [*] Open your browser at http://localhost:8503
echo.
call .venv\Scripts\activate.bat
streamlit run src\muscle_power\main.py --server.port 8503

pause
