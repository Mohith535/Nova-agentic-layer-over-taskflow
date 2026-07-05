@echo off
REM ============================================================
REM  Nova - uninstaller. Removes Nova and/or its companions,
REM  and (only if you ask) your data. Your data is kept by
REM  default and nothing is deleted until you confirm.
REM  Double-click this, or run:  uninstall.bat
REM ============================================================
where python >nul 2>nul
if errorlevel 1 (
  echo Python is not on PATH. Open this folder in a terminal and run:  python uninstall.py
  echo.
  pause
  exit /b 1
)
python "%~dp0uninstall.py"
echo.
pause
