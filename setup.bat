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
  echo During install, remember to tick "Add Python to PATH".
  exit /b 1
)

REM Nova needs Python 3.11+ — fail with a clear message instead of a cryptic pip error later.
python -c "import sys; sys.exit(0 if sys.version_info[:2]>=(3,11) else 1)"
if errorlevel 1 (
  echo Nova needs Python 3.11 or newer. You currently have:
  python --version
  echo Please install Python 3.11+ from https://python.org, then re-run setup.bat.
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

echo [4/4] Setup complete - opening Nova...
echo.
echo ============================================================
echo   Nova is installed and ready. The console opens at
echo   http://127.0.0.1:8765  (demo data loads automatically).
echo.
echo   Press Ctrl+C to stop the console - THIS WINDOW STAYS OPEN
echo   and ready, so you can then run any of these right here:
echo       nova web        open the console again
echo       nova doctor     health check - verifies key, data, Hunter
echo       nova ask "hi"   ask Nova anything
echo ============================================================
echo.
REM Hand off to an interactive shell that already has the venv active, then run the
REM console in it. Ctrl+C stops the console but keeps this shell ready for nova commands.
cmd /k nova web
