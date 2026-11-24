@echo off
cd /d "%~dp0"
set "CAPTION_BABY_HOME=%CD%"
if exist "src-tauri\target\release\caption-baby.exe" (
    start "" "src-tauri\target\release\caption-baby.exe"
    exit /b 0
)
echo The Tauri app has not been built on this PC. Opening the browser editor.
if not exist ".venv\Scripts\python.exe" (
    echo Run Setup Caption Baby.cmd first.
    pause
    exit /b 1
)
".venv\Scripts\python.exe" app.py
if errorlevel 1 pause
