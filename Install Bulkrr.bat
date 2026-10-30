@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1"
if errorlevel 1 (
  echo.
  echo Installation failed. Review the messages above.
  pause
  exit /b 1
)
echo.
echo Installation complete. You can launch Bulkrr from your desktop.
pause
