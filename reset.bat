@echo off
REM ============================================================
REM  Nova - reset to a fresh state (for re-testing the setup)
REM  Removes this folder's .venv + .env, the demo board data in
REM  %USERPROFILE%\.taskflow, and a sibling opportunity-hunter clone.
REM  Leaves the Nova source intact - just re-run setup.bat afterwards.
REM ============================================================
setlocal

echo This will DELETE:
echo    - .venv                       (the virtual environment here)
echo    - .env                        (your saved keys here)
echo    - %USERPROFILE%\.taskflow     (Nova's demo / board data)
echo    - ..\opportunity-hunter       (only if it exists)
echo.
set /p ok="Type  yes  to confirm: "
if /i not "%ok%"=="yes" (
  echo Cancelled - nothing was deleted.
  exit /b 0
)

if exist ".venv" rmdir /s /q ".venv"
if exist ".env" del /q ".env"
if exist "%USERPROFILE%\.taskflow" rmdir /s /q "%USERPROFILE%\.taskflow"
if exist "..\opportunity-hunter" rmdir /s /q "..\opportunity-hunter"

echo.
echo Done. Re-run  setup.bat  for a fresh install.
echo (For a 100%% clean test, delete this whole 'nova' folder and re-clone.)
