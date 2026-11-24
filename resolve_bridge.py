"""DaVinci Resolve scripting and caption overlay placement on Windows."""
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
import importlib
import os
import sys
import time


@dataclass(frozen=True)
class Timeline:
    project_id: str
    timeline_id: str
    name: str
    start: int
    end: int
    fps: Fraction
    width: int
    height: int


def connect():
    if sys.platform != "win32":
        raise RuntimeError(
            "Direct DaVinci Resolve timeline access is currently supported by the Windows build. "
            "On macOS and Linux, open a WAV or video export to generate captions."
        )
    api = Path(os.environ.get("RESOLVE_SCRIPT_API") or (
        Path(os.environ["PROGRAMDATA"])
        / "Blackmagic Design/DaVinci Resolve/Support/Developer/Scripting"
    ))
    library = Path(os.environ.get("RESOLVE_SCRIPT_LIB") or (
        Path(os.environ["ProgramFiles"]) / "Blackmagic Design/DaVinci Resolve/fusionscript.dll"
    ))
    modules = str(api / "Modules")
    if modules not in sys.path:
        sys.path.insert(0, modules)
    os.environ.setdefault("RESOLVE_SCRIPT_LIB", str(library))
    resolve = importlib.import_module("DaVinciResolveScript").scriptapp("Resolve")
    if not resolve:
        raise RuntimeError(
            "Direct timeline access needs Resolve Studio with External scripting using set to Local. "
            "Use Open WAV for an audio export."
        )
    return resolve


def active(resolve):
    manager = resolve.GetProjectManager()
    project = manager.GetCurrentProject() if manager else None
    timeline = project.GetCurrentTimeline() if project else None
    if not timeline:
        raise RuntimeError("Open a project and select the timeline you want to caption.")

    def setting(key):
        return timeline.GetSetting(key) or project.GetSetting(key)

    raw_fps = setting("timelineFrameRate").split()[0]
    fractional = {"23.976": 24000, "23.98": 24000, "29.97": 30000,
                  "47.952": 48000, "59.94": 60000, "119.88": 120000}
    fps = Fraction(fractional[raw_fps], 1001) if raw_fps in fractional else Fraction(raw_fps)
    snapshot = Timeline(
        project.GetUniqueId(), timeline.GetUniqueId(), timeline.GetName(),
        timeline.GetStartFrame(), timeline.GetEndFrame(), fps,
        int(setting("timelineResolutionWidth")), int(setting("timelineResolutionHeight")),
    )
    return project, timeline, snapshot


def render_audio(project, folder, report):
    if project.IsRenderingInProgress():
        raise RuntimeError("Wait for the current Resolve render to finish.")
    old_format = project.GetCurrentRenderFormatAndCodec() or {}
    old_mode = project.GetCurrentRenderMode()
    job = None
    running = False
    try:
        codecs = project.GetAudioRenderCodecs("wav") or project.GetRenderCodecs("wav") or {}
        pcm = next((value for name, value in codecs.items()
                    if "pcm" in name.lower() or "pcm" in value.lower()), "LinearPCM")
        if not project.SetCurrentRenderMode(1):
            raise RuntimeError("Resolve could not switch to Single Clip rendering.")
        if not project.SetRenderSettings({
            "SelectAllFrames": True, "ExportVideo": False, "ExportAudio": True,
            "AudioFormat": "wav", "AudioCodec": pcm, "AudioBitDepth": 16,
            "AudioSampleRate": 48000, "ExportSubtitle": False, "TargetDir": str(folder),
            "CustomName": "timeline-audio", "UseUniqueFilenames": False,
        }):
            raise RuntimeError("Resolve rejected the WAV render settings.")
        job = project.AddRenderJob()
        if not job or not project.StartRendering([job]):
            raise RuntimeError("Resolve could not start the audio render.")
        running = True
        deadline = time.monotonic() + 3600
        while True:
            status = project.GetRenderJobStatus(job) or {}
            state = str(status.get("JobStatus", "")).lower()
            if state == "complete":
                running = False
                break
            if state in {"failed", "cancelled", "canceled"}:
                running = False
                raise RuntimeError(f"Resolve audio render {state}. Check the Deliver page.")
            if time.monotonic() >= deadline:
                raise RuntimeError("Resolve audio render timed out.")
            report(f"Rendering the timeline mix… {status.get('CompletionPercentage', 0)}%")
            time.sleep(0.6)
        files = list(folder.glob("*.wav"))
        if len(files) != 1 or not files[0].stat().st_size:
            raise RuntimeError("Resolve did not produce a single WAV file. Check the Deliver audio settings.")
        return files[0]
    finally:
        if running and project.IsRenderingInProgress():
            project.StopRendering()
        if job:
            project.DeleteRenderJob(job)
        if old_format.get("format") and old_format.get("codec"):
            project.SetCurrentRenderFormatAndCodec(old_format["format"], old_format["codec"])
        if old_mode in (0, 1):
            project.SetCurrentRenderMode(old_mode)


def make_overlays(folder, cues, snapshot):
    from PIL import Image, ImageDraw, ImageFont

    width, height = snapshot.width, snapshot.height
    font_path = Path(os.environ["WINDIR"]) / "Fonts/arialbd.ttf"
    size = max(12, round(min(width, height) * 0.055))
    paths = []
    for index, (_, _, text) in enumerate(cues, 1):
        image = Image.new("RGBA", (width, height))
        draw = ImageDraw.Draw(image)
        font = ImageFont.truetype(str(font_path), size)
        stroke = max(1, size // 13)
        spacing = max(2, size // 8)
        bounds = draw.multiline_textbbox((0, 0), text, font=font, align="center",
                                         spacing=spacing, stroke_width=stroke)
        text_width = bounds[2] - bounds[0]
        if text_width > width * 0.86:
            font = ImageFont.truetype(str(font_path), max(8, int(size * width * 0.84 / text_width)))
            bounds = draw.multiline_textbbox((0, 0), text, font=font, align="center",
                                             spacing=spacing, stroke_width=stroke)
        x = (width - bounds[2] - bounds[0]) / 2
        y = height * 0.88 - bounds[3]
        draw.multiline_text((x, y), text, font=font, fill="white", align="center",
                            spacing=spacing, stroke_width=stroke, stroke_fill="black")
        path = folder / f"Caption-{index:04d}-overlay.png"
        image.save(path, compress_level=1)
        paths.append(path)
    return paths


def place_overlays(project, timeline, snapshot, cues, paths):
    pool = project.GetMediaPool()
    current_folder = pool.GetCurrentFolder()
    folder = pool.AddSubFolder(pool.GetRootFolder(), f"Caption Baby {paths[0].parent.name}")
    if not folder:
        raise RuntimeError("Resolve could not create a Media Pool bin for the captions.")
    imported = []
    track = None
    try:
        if not pool.SetCurrentFolder(folder):
            raise RuntimeError("Resolve could not select the caption bin.")
        for path in paths:
            items = pool.ImportMedia([str(path)]) or []
            imported.extend(items)
            if len(items) != 1:
                raise RuntimeError(f"Resolve could not import {path.name}.")
        if not timeline.AddTrack("video"):
            raise RuntimeError("Resolve could not add the caption track.")
        track = timeline.GetTrackCount("video")
        timeline.SetTrackName("video", track, "Caption Baby")
        for (start, end, _), media in zip(cues, imported, strict=True):
            duration = end - start
            clip_info = {
                "mediaPoolItem": media, "startFrame": 0, "endFrame": duration,
                "recordFrame": snapshot.start + start, "trackIndex": track, "mediaType": 1,
            }
            items = pool.AppendToTimeline([clip_info]) or []
            if len(items) != 1 or items[0].GetStart() != snapshot.start + start:
                raise RuntimeError("Resolve placed a caption at an unexpected frame.")
            adjustment = duration - items[0].GetDuration()
            if adjustment in (-1, 1) and timeline.DeleteClips(items, False):
                clip_info["endFrame"] += adjustment
                items = pool.AppendToTimeline([clip_info]) or []
            if (len(items) != 1 or items[0].GetStart() != snapshot.start + start
                    or items[0].GetDuration() != duration):
                raise RuntimeError("Resolve returned an unexpected caption duration.")
    except Exception:
        cleaned = track is None or timeline.DeleteTrack("video", track)
        if cleaned:
            if imported:
                pool.DeleteClips(imported)
            pool.DeleteFolders([folder])
        else:
            raise RuntimeError("Resolve left a partial Caption Baby track. Remove that track before retrying.")
        raise
    finally:
        if current_folder:
            pool.SetCurrentFolder(current_folder)
