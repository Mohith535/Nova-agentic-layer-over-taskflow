@echo off
REM ============================================================
REM  Nova — one-command setup (Windows)
REM  Creates an isolated environment, installs Nova, and opens
REM  the console with demo data. No API key needed to explore.
REM ============================================================
setlocal

where python >nul 2>nul
if errorlevel 1 (
  echo Python is not on PATH. Install Python 3.11+ from https://python.org and re-run.
  exit /b 1
)

echo [1/3] Creating virtual environment (.venv)...
python -m venv .venv || exit /b 1
call .venv\Scripts\activate.bat

echo [2/3] Installing Nova and dependencies...
python -m pip install --upgrade pip >nul
pip install -e . || exit /b 1

echo [3/3] Launching the Nova console...
echo.
echo   The browser will open at http://127.0.0.1:8765
echo   Demo data is loaded automatically - no API key required to explore.
echo   For live AI: copy .env.example to .env and add a free Gemini key
echo   (https://aistudio.google.com/apikey), then restart.
echo.
nova web
