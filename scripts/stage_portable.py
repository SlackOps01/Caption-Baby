"""Bundle the Python engine and media tools for macOS or Linux release builds."""
from pathlib import Path
import os
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "src-tauri" / "target" / "portable-payload"
ENGINE = DIST / "caption-baby-engine"


def main():
    if sys.platform not in {"darwin", "linux"}:
        raise SystemExit("Portable payload staging is for macOS and Linux runners.")

    if DIST.exists():
        if DIST.resolve() != DIST or DIST.parent.resolve() != DIST.parent:
            raise SystemExit("Refusing to replace a redirected portable payload.")
        shutil.rmtree(DIST)
    DIST.mkdir(parents=True)

    separator = os.pathsep
    subprocess.run([
        sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onedir",
        "--name", "caption-baby-engine", "--distpath", str(DIST),
        "--workpath", str(ROOT / "src-tauri" / "target" / "pyinstaller-work"),
        "--specpath", str(ROOT / "src-tauri" / "target" / "pyinstaller-spec"),
        "--add-data", f"{ROOT / 'web'}{separator}web",
        "--collect-all", "onnx_asr", "--collect-all", "onnxruntime",
        "--collect-all", "huggingface_hub", "--collect-all", "pip",
        "--hidden-import", "tkinter", "--hidden-import", "tkinter.filedialog",
        str(ROOT / "app.py"),
    ], cwd=ROOT, check=True)

    from static_ffmpeg import run

    ffmpeg, ffprobe = run.get_or_fetch_platform_executables_else_raise()
    tools = ENGINE / "bin"
    tools.mkdir()
    for source, name in ((ffmpeg, "ffmpeg"), (ffprobe, "ffprobe")):
        target = tools / name
        shutil.copy2(source, target)
        target.chmod(target.stat().st_mode | 0o111)

    license_text = subprocess.run([str(ffmpeg), "-L"], check=True, capture_output=True, text=True).stdout
    (ENGINE / "FFmpeg-LICENSE.txt").write_text(
        "FFmpeg license information for the bundled media tools\n\n"
        + license_text
        + "\nBuild sources: https://github.com/zackees/ffmpeg-bins2\n",
        encoding="utf-8",
    )

    print(f"Portable engine staged at {ENGINE}")


if __name__ == "__main__":
    main()
