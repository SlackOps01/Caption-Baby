"""Install the Caption Baby launcher in Resolve's per-user Edit scripts menu."""
import json
import os
from pathlib import Path


root = Path(__file__).resolve().parent
pythonw = root / ".venv" / "Scripts" / "pythonw.exe"
if not pythonw.is_file():
    raise SystemExit("Run Setup Caption Baby.cmd before installing the menu entry.")
if any(character in str(root) for character in "%!"):
    raise SystemExit("Move Caption Baby to a folder without percent signs or exclamation marks.")

scripts = Path(os.environ["APPDATA"]) / (
    "Blackmagic Design/DaVinci Resolve/Support/Fusion/Scripts/Edit"
)
scripts.mkdir(parents=True, exist_ok=True)
target = scripts / "Caption Baby.lua"
header = "-- Launch Caption Baby from Resolve's Edit scripts menu.\n"
legacy_command = f'start "" /D "{root}" "{pythonw}" "{root / "app.py"}" --from-resolve'
legacy = header + f"os.execute({json.dumps(legacy_command, ensure_ascii=False)})\n"
command = f'start "" /D "{root}" "{pythonw}" "{root / "launch_from_resolve.py"}"'
log = root / ".venv" / "resolve-launch.log"
launcher = header + f'''local log = io.open({json.dumps(str(log), ensure_ascii=False)}, "a")
if log then
    log:write("Resolve invoked the Edit menu script.\\n")
    log:close()
end
local result = os.execute({json.dumps(command, ensure_ascii=False)})
print("Caption Baby launch result: " .. tostring(result))
'''
diagnostic = launcher
launcher = header + '''if not os or not os.execute then
    print("Resolve blocked the external launcher. Open Launch Caption Baby.cmd in File Explorer.")
    return
end
''' + diagnostic[len(header):].replace("local log = io.open(", "local log = io and io.open(")
if target.exists() and target.read_text(encoding="utf-8") not in (legacy, diagnostic, launcher):
    raise SystemExit(f"An existing launcher uses that name: {target}")
target.write_text(launcher, encoding="utf-8")
print(f"Installed {target}")
