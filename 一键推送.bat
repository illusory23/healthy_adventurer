@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ============================================
echo   One-click commit + push to GitHub
echo   remote: illusory23/healthy_adventurer
echo ============================================
echo.

git add -A
git -c core.quotepath=false diff --cached --stat
git diff --cached --quiet
if not errorlevel 1 goto nochange

set "msg=%~1"
if not "%msg%"=="" goto docommit
set /p "msg=Commit message (Enter for default): "
if "%msg%"=="" set "msg=update %date% %time%"

:docommit
echo.
echo [1/3] commit: %msg%
git commit -m "%msg%"
if errorlevel 1 goto failed
goto syncpush

:nochange
echo [info] No new changes to commit.

:syncpush
echo.
echo [2/3] sync with remote (pull --rebase) ...
git pull --rebase --autostash
if errorlevel 1 goto failed

echo.
echo [3/3] pushing to GitHub ...
git push
if errorlevel 1 goto failed

echo.
echo [OK] Pushed. GitHub is up to date.
goto hold

:failed
echo.
echo [FAILED] Commit is kept locally - fix the issue and run this script again.
echo          (Rerunning is safe: it will skip the commit step and just push.)

:hold
echo.
pause
