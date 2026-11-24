"""Stage the Windows installer payload from x64 CPython 3.12 and FFmpeg."""
import os
from importlib.metadata import distribution
from pathlib import Path
import shutil
import struct
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / "src-tauri" / "target" / "windows-payload"
MODULES = ("app", "asr_models", "captioning", "media_input", "resolve_bridge", "video_export")


def copy_installed_dependencies(destination):
    """Stage just the dependency graph from the prepared local virtualenv."""
    from pip._vendor.packaging.requirements import Requirement

    visited = set()
    requirements = (ROOT / "requirements.txt").read_text().splitlines()
    pending = [Requirement(line) for line in [*requirements, "pip"] if line.strip()]
    while pending:
        requirement = pending.pop()
        key = (requirement.name.lower().replace("_", "-"), frozenset(requirement.extras))
        if key in visited:
            continue
        visited.add(key)
        package = distribution(requirement.name)
        if package.version not in requirement.specifier or package.files is None:
            raise SystemExit(f"Install {requirement} in the build environment first.")
        for record in package.files:
            if ".." in record.parts or not package.locate_file(record).is_file():
                continue
            target = destination / record
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(package.locate_file(record), target)
        for raw in package.requires or ():
            dependency = Requirement(raw)
            if not dependency.marker or any(
                dependency.marker.evaluate({"extra": extra})
                for extra in ("", *requirement.extras)
            ):
                pending.append(dependency)


def main():
    if sys.platform != "win32" or struct.calcsize("P") != 8 or sys.version_info[:2] != (3, 12):
        raise SystemExit("Staging requires Windows x64 CPython 3.12.")
    base = Path(sys.base_prefix)
    if not (base / "tcl").is_dir():
        raise SystemExit("Install CPython with Tcl/Tk enabled for the file and folder pickers.")
    tools = [shutil.which(name) for name in ("ffmpeg", "ffprobe")]
    if not all(tools):
        raise SystemExit("FFmpeg and FFprobe must be available on the build machine.")
    if DEST.exists():
        if DEST.resolve() != DEST or DEST.parent.resolve() != DEST.parent:
            raise SystemExit("Refusing to replace a redirected installer payload.")
        shutil.rmtree(DEST)
    runtime = DEST / "python"
    runtime.mkdir(parents=True)
    for name in ("python.exe", "python312.dll", "python3.dll", "LICENSE.txt"):
        shutil.copy2(base / name, runtime)
    vswhere = Path(os.environ["ProgramFiles(x86)"]) / "Microsoft Visual Studio/Installer/vswhere.exe"
    if not vswhere.is_file():
        raise SystemExit("Visual Studio Build Tools with the x64 C++ redistributable files are required.")
    installation = subprocess.check_output(
        [str(vswhere), "-latest", "-products", "*", "-requires",
         "Microsoft.VisualStudio.Component.VC.Tools.x86.x64", "-property", "installationPath"],
        text=True,
    ).strip()
    candidates = list(Path(installation).glob("VC/Redist/MSVC/*/x64/Microsoft.VC*.CRT"))
    if not candidates:
        raise SystemExit("Could not find the Visual C++ x64 redistributable DLLs.")
    crt = max(candidates, key=lambda path: tuple(map(int, path.parents[1].name.split("."))))
    for path in crt.glob("*.dll"):
        shutil.copy2(path, runtime)
    for name in ("DLLs", "Lib", "tcl"):
        shutil.copytree(base / name, runtime / name,
                        ignore=shutil.ignore_patterns("site-packages", "__pycache__"))
    packages = runtime / "Lib" / "site-packages"
    if "--installed" in sys.argv:
        copy_installed_dependencies(packages)
    else:
        subprocess.run([sys.executable, "-m", "pip", "install", "--only-binary=:all:",
                        "--target", str(packages), "-r", str(ROOT / "requirements.txt"), "pip"], check=True)
    for name in MODULES:
        shutil.copy2(ROOT / f"{name}.py", DEST)
    shutil.copytree(ROOT / "web", DEST / "web")
    for tool in tools:
        shutil.copy2(tool, DEST / Path(tool).name.lower())
    tool_directory = Path(tools[0]).parent
    for name in ("LICENSE", "COPYING", "README.txt"):
        for directory in (tool_directory, tool_directory.parent):
            source = directory / name
            if source.is_file():
                shutil.copy2(source, DEST / f"ffmpeg-{name}")
                break
    env = {**os.environ, "PYTHONNOUSERSITE": "1"}
    subprocess.run([str(runtime / "python.exe"), "-c",
                    "import app, tkinter, numpy, onnxruntime, onnx_asr; assert tkinter.Tcl().eval('info patchlevel')"],
                   cwd=DEST, env=env, check=True)
    for name in ("ffmpeg.exe", "ffprobe.exe"):
        subprocess.run([str(DEST / name), "-version"], check=True,
                       stdout=subprocess.DEVNULL)
    subprocess.run([str(runtime / "python.exe"), "-m", "pip", "--version"], check=True)
    print(f"Windows payload staged at {DEST}")


if __name__ == "__main__":
    main()


