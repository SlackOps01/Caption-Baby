@echo off
setlocal
cd /d "%~dp0"
set "PATH=%CD%\.venv\tauri-cli\bin;%USERPROFILE%\.cargo\bin;%PATH%"
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" scripts\stage_windows.py --installed || exit /b 1
) else (
    py -3.12 scripts\stage_windows.py || exit /b 1
)
cd src-tauri
cargo tauri build --config tauri.windows-installer.conf.json --bundles nsis -- --locked




