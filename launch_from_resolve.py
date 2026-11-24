"""Start the editor from Resolve and record startup errors."""
from pathlib import Path
import subprocess
import traceback


root = Path(__file__).resolve().parent
log_path = root / ".venv" / "resolve-launch.log"
with log_path.open("a", encoding="utf-8") as log:
    print("Editor process started.", file=log, flush=True)
    try:
        desktop = root / "src-tauri" / "target" / "release" / "caption-baby.exe"
        if desktop.is_file():
            subprocess.Popen([str(desktop), "--from-resolve"], cwd=root)
        else:
            from app import main

            main(from_resolve=True)
    except Exception:
        traceback.print_exc(file=log)
        raise
