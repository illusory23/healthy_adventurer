@echo off
REM Stop ALL server processes listening on port 5899.
REM (v1.39: kills every PID, fixing the old double-process issue)
setlocal enabledelayedexpansion
set N=0
for /f "tokens=5" %%p in ('netstat -ano -p tcp ^| findstr /r /c:":5899 .*LISTENING"') do (
  taskkill /f /pid %%p >nul 2>&1
  if not errorlevel 1 set /a N+=1
)
if "!N!"=="0" (
  echo Nothing is listening on port 5899.
) else (
  echo Stopped !N! process(es^) on port 5899.
)
echo.
pause
