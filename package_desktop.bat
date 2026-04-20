@echo off
setlocal enabledelayedexpansion

echo ========================================
echo   Muscle Power Desktop - Package EXE
echo ========================================
echo.

:: Ensure venv + deps
if not exist ".venv" (
    echo [*] Creating virtual environment...
    uv venv
)
echo [*] Installing all dependencies (desktop extras)...
uv pip install -e ".[desktop]"

echo.
echo [*] Running PyInstaller...
call .venv\Scripts\activate.bat
pyinstaller --clean muscle_power_desktop.spec

if %errorlevel% equ 0 (
    echo.
    echo [+] Build successful!
    echo [+] Output: dist\Musclepower.exe
    echo.
) else (
    echo.
    echo [!] Build failed. Check the output above for errors.
    echo.
)

pause
