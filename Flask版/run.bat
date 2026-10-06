@echo off
cd /d "%~dp0"
REM Guard: refuse to start if port 5899 is already in use (avoids double processes)
netstat -ano -p tcp | findstr /r /c:":5899 .*LISTENING" >nul
if not errorlevel 1 (
  echo Port 5899 is already in use - a server may already be running.
  echo To restart cleanly, run the restart script instead.
  echo.
  pause
  exit /b 1
)
start "AdventurerGame" python app.py
REM ============================================================
REM  Remote access via SakuraFrp (optional):
REM   1. In SakuraFrp Launcher, create an HTTP tunnel to
REM      local address 127.0.0.1  port 5899
REM   2. Either enable "auto start" inside the Launcher,
REM      or uncomment the next line and set your own path
REM ============================================================
REM start "SakuraFrp" "C:\SakuraFrp\SakuraFrpLauncher.exe"
echo.
echo  Game server is starting in a new window (port 5899).
echo  Keep this computer awake (no sleep / hibernate).
echo  First remote visit asks for the access key (see access_key.txt).
echo.
pause
