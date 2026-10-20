@echo off
REM ============================================================
REM  One-click launcher - Flask game server (port 5899)
REM  v1.68: the server runs in THIS window (single window only).
REM  Keep this file pure ASCII + CRLF (see doc 09, tech notes).
REM ============================================================
cd /d "%~dp0"

python --version >nul 2>&1
if errorlevel 1 (
  echo [ERROR] Python not found. Install Python 3 and make sure
  echo         the command "python" works in a new cmd window.
  echo.
  pause
  exit /b 1
)

REM --- Already running? Just open the game, never a second server ---
netstat -ano -p tcp | findstr /r /c:":5899 .*LISTENING" >nul
if not errorlevel 1 (
  echo The server is already running on port 5899 - opening the game...
  start "" "http://localhost:5899"
  echo To kill it and start fresh, run the restart script.
  exit /b 0
)

REM ============================================================
REM  Remote access via SakuraFrp (optional):
REM   1. In SakuraFrp Launcher, create an HTTP tunnel to
REM      local address 127.0.0.1  port 5899
REM   2. Either enable "auto start" inside the Launcher,
REM      or uncomment the next line and set your own path
REM ============================================================
REM start "SakuraFrp" "C:\SakuraFrp\SakuraFrpLauncher.exe"

REM --- Start the server here (same window) and open the browser when ready ---
title AdventurerGame - port 5899
set GAME_AUTO_OPEN=1
python app.py
set "RC=%errorlevel%"

echo.
echo Server stopped (or failed to start). Press any key to close.
pause >nul
exit /b %RC%
