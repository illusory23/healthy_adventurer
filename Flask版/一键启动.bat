@echo off
REM ============================================================
REM  One-click launcher - double-click this file to start the game.
REM  v1.68: ONE window only (the server runs in this window), and
REM  the browser opens automatically once the server is ready.
REM  This is a thin wrapper around run.bat; keep pure ASCII + CRLF.
REM ============================================================
cd /d "%~dp0"
call "%~dp0run.bat"
exit /b
