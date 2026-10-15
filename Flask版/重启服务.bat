@echo off
REM ============================================================
REM  Clean restart (v1.68): kill ALL PIDs on port 5899, then start
REM  the new server in THIS window (single window, no extra console).
REM  Keep this file pure ASCII + CRLF.
REM ============================================================
setlocal enabledelayedexpansion
cd /d "%~dp0"
echo [1/2] Stopping the old server on port 5899 ...
set N=0
for /f "tokens=5" %%p in ('netstat -ano -p tcp ^| findstr /r /c:":5899 .*LISTENING"') do (
  taskkill /f /pid %%p >nul 2>&1
  if not errorlevel 1 set /a N+=1
)
echo       stopped !N! process(es^).
endlocal

REM --- Wait until the port is really free (max ~10s), then start ---
for /l %%i in (1,1,10) do (
  netstat -ano -p tcp | findstr /r /c:":5899 .*LISTENING" >nul || goto start_server
  timeout /t 1 /nobreak >nul
)
:start_server
echo [2/2] Starting the new server in this window ...
call "%~dp0run.bat"
exit /b
