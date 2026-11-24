@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    py -3.12 -m venv .venv || goto failed
)
".venv\Scripts\python.exe" -m pip install -r requirements.txt || goto failed
echo Installation complete. Double-click Launch Caption Baby.cmd to open the app.
pause
exit /b 0
:failed
echo Setup failed. Install 64-bit Python 3.12 with the Python launcher and try again.
pause
exit /b 1
