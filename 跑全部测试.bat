@echo off
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
echo Running ALL test suites (node + python required) ...
python run_all_tests.py
echo.
pause
