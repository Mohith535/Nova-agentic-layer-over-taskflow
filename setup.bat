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

echo [1/4] Creating virtual environment (.venv)...
python -m venv .venv || exit /b 1
call .venv\Scripts\activate.bat

echo [2/4] Installing Nova and dependencies...
python -m pip install --upgrade pip >nul
pip install -e . || exit /b 1

echo [3/4] Configuring your keys (interactive - press Enter to skip any)...
echo.
python configure.py

echo [4/4] Launching the Nova console...
echo.
echo   The browser will open at http://127.0.0.1:8765
echo   Demo data is loaded automatically - no API key required to explore.
echo   (Re-run 'python configure.py' any time to add or change a key.)
echo.
nova web
