@echo off
cd /d "%~dp0"
set "CAPTION_BABY_HOME=%CD%"
rem The installer build can leave a bundled engine beside the executable.
rem Use the source editor so local Python and frontend changes are picked up.
if exist "src-tauri\target\release\engine\app.py" goto source_editor
if exist "src-tauri\target\release\caption-baby.exe" (
    start "" "src-tauri\target\release\caption-baby.exe"
    exit /b 0
)
:source_editor
echo Opening the local Caption Baby editor in your browser.
if not exist ".venv\Scripts\python.exe" (
    echo Run Setup Caption Baby.cmd first.
    pause
    exit /b 1
)
".venv\Scripts\python.exe" app.py
if errorlevel 1 pause
