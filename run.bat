@echo off
REM ============================================================
REM  Nova - launch the console (after setup.bat has installed it)
REM  Double-click this, or run  run.bat  any time to open Nova.
REM ============================================================
setlocal

if not exist ".venv\Scripts\activate.bat" (
  echo No environment found here. Run  setup.bat  first.
  exit /b 1
)

call .venv\Scripts\activate.bat
echo.
echo ============================================================
echo   Nova is starting at  http://127.0.0.1:8765
echo.
echo   Ctrl+C stops the console but keeps THIS window ready, so you
echo   can then run any of these right here (no setup needed):
echo       nova web        open the console again
echo       nova doctor     health check - key, data, Hunter
echo       nova ask "hi"   ask Nova anything
echo ============================================================
echo.
REM Hand off to a shell that already has the environment active, then start the console in
REM it. This means an isolated install still gives full command access without the user ever
REM needing to know how to "activate a venv".
cmd /k nova web
