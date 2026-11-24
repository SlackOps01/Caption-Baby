@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Run Setup Caption Baby.cmd first.
    pause
    exit /b 1
)
".venv\Scripts\python.exe" install_resolve_script.py
if errorlevel 1 (
    pause
    exit /b 1
)
echo Restart Resolve, open Edit, then look under Workspace, Scripts, Edit, Caption Baby.
pause
