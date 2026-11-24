"""Local video inspection, frame-accurate audio extraction, and the Windows picker."""
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4
import json
import mimetypes
import os
import shutil
import subprocess
import sys


VIDEO_EXTENSIONS = {".avi", ".m4v", ".mkv", ".mov", ".mp4", ".mpeg", ".mpg", ".webm"}


@dataclass(frozen=True)
class AudioTrack:
    index: int
    label: str
    default: bool


@dataclass(frozen=True)
class Video:
    path: Path
    token: str
    tracks: tuple[AudioTrack, ...]

    def payload(self):
        return {
            "name": self.path.name,
            "token": self.token,
            "tracks": [{"index": track.index, "label": track.label} for track in self.tracks],
            "default": next((track.index for track in self.tracks if track.default),
                            self.tracks[0].index if self.tracks else None),
        }

    @property
    def mime(self):
        return mimetypes.guess_type(str(self.path))[0] or "application/octet-stream"


def run_tool(args, timeout=None):
    try:
        return subprocess.run(
            args, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            encoding="utf-8", errors="replace", timeout=timeout, check=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            env={**os.environ, "PYTHONUTF8": "1"},
        ).stdout
    except subprocess.TimeoutExpired as error:
        raise RuntimeError("The media operation timed out.") from error
    except subprocess.CalledProcessError as error:
        detail = error.stderr.strip().splitlines()
        raise RuntimeError(detail[-1] if detail else "The media tool could not open the file.") from error


def choose_video():
    path = json.loads(run_tool([sys.executable, str(Path(__file__).resolve())]))
    if path:
        return inspect_video(Path(path))


def choose_export_folder():
    selected = json.loads(run_tool([sys.executable, str(Path(__file__).resolve()), "--export-folder"], timeout=3600))
    return Path(selected) if selected else None


def inspect_video(path):
    if path.suffix.lower() not in VIDEO_EXTENSIONS or not path.is_file():
        raise ValueError("Choose an existing MP4, MOV, MKV, WebM, AVI, or MPEG video.")
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        raise RuntimeError("FFprobe is unavailable. Add the FFmpeg tools to Windows PATH and reopen Caption Baby.")
    metadata = json.loads(run_tool([
        ffprobe, "-v", "error", "-protocol_whitelist", "file,pipe", "-show_entries",
        "stream=index,codec_type,codec_name:stream_disposition=default,attached_pic:stream_tags=language,title",
        "-of", "json", str(path),
    ], timeout=30))
    if not any(stream.get("codec_type") == "video" and not stream.get("disposition", {}).get("attached_pic")
               for stream in metadata.get("streams", ())):
        raise ValueError("This file does not contain a video track.")
    tracks = []
    for stream in metadata["streams"]:
        if stream.get("codec_type") != "audio":
            continue
        tags = stream.get("tags", {})
        label = f"Track {len(tracks) + 1}"
        for info in (tags.get("title"), tags.get("language"), stream.get("codec_name")):
            if info and info != "und":
                label += f"  |  {info}"
        tracks.append(AudioTrack(stream["index"], label, bool(stream.get("disposition", {}).get("default"))))
    return Video(path.resolve(), uuid4().hex, tuple(tracks))


def extract_audio(video, track_index, destination):
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("FFmpeg is unavailable. Add it to Windows PATH and reopen Caption Baby.")
    run_tool([
        ffmpeg, "-nostdin", "-v", "error", "-protocol_whitelist", "file,pipe",
        "-copyts", "-start_at_zero",
        "-i", str(video.path), "-map", f"0:{track_index}", "-vn", "-sn", "-dn",
        "-af", "aresample=16000:async=1:first_pts=0", "-ac", "1", "-c:a", "pcm_s16le",
        "-f", "wav", str(destination),
    ], timeout=1800)


if __name__ == "__main__":
    from tkinter import Tk, filedialog

    window = Tk()
    window.withdraw()
    window.attributes("-topmost", True)
    try:
        if "--export-folder" in sys.argv:
            selected = filedialog.askdirectory(parent=window, title="Choose captioned video export folder")
        else:
            selected = filedialog.askopenfilename(
                parent=window, title="Open a video in Caption Baby",
                filetypes=[("Video", " ".join("*" + ext for ext in sorted(VIDEO_EXTENSIONS)))],
            )
        print(json.dumps(selected))
    finally:
        window.destroy()
