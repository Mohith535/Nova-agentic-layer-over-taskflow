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
nova web
