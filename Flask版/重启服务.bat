@echo off
REM Restart the server cleanly: kill ALL PIDs on 5899, then start a new one.
setlocal enabledelayedexpansion
cd /d "%~dp0"
echo [1/2] Stopping server on port 5899 ...
set N=0
for /f "tokens=5" %%p in ('netstat -ano -p tcp ^| findstr /r /c:":5899 .*LISTENING"') do (
  taskkill /f /pid %%p >nul 2>&1
  if not errorlevel 1 set /a N+=1
)
echo       stopped !N! process(es^).
timeout /t 1 /nobreak >nul
echo [2/2] Starting new server window ...
start "AdventurerGame" python app.py
echo.
echo Done. The server is starting in a new window (port 5899).
pause
