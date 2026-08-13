@echo off
setlocal
cd /d %~dp0

if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" main.py
    exit /b %errorlevel%
)

if exist "%USERPROFILE%\.workbuddy\binaries\python\envs\default\Scripts\python.exe" (
    "%USERPROFILE%\.workbuddy\binaries\python\envs\default\Scripts\python.exe" main.py
    exit /b %errorlevel%
)

where python >nul 2>&1
if errorlevel 1 (
    echo Python was not found. See README.md for installation instructions.
    pause
    exit /b 1
)

python main.py
