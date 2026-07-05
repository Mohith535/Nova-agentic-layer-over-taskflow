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
REM Step OUT of the Nova folder first, so it can be fully removed if you uninstall Nova.
cd /d "%~dp0.." 2>nul
python "%~dp0uninstall.py"
echo.
pause
