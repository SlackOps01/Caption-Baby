@echo off
cd /d "%~dp0"
set "CARGO=%USERPROFILE%\.cargo\bin\cargo.exe"
if not exist "%CARGO%" set "CARGO=cargo"
"%CARGO%" build --locked --manifest-path src-tauri\Cargo.toml --release
if errorlevel 1 (
    pause
    exit /b 1
)
echo Built src-tauri\target\release\caption-baby.exe.
pause
