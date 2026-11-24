"""Export captioned video as a subtitle track or a burned-in MP4."""
from pathlib import Path
from tempfile import TemporaryDirectory
import shutil
import subprocess
import re
import uuid

def render(video, subtitle, folder, size, position, styles=None, *, preserve_encoding=False, look="Editorial", preview=None):
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("FFmpeg is required to export captioned video.")
    folder.mkdir(parents=True, exist_ok=True)
    extension = "mkv" if preserve_encoding else "mp4"
    target = folder / f"Captioned video-{uuid.uuid4().hex[:8]}.{extension}"
    with TemporaryDirectory(prefix="caption-baby-render-") as work:
        work = Path(work)
        width, height, font_size = preview or (384, 288, 14 * size / 100)
        width, height = round(width), round(height)
        margin = round(width * .08)
        # ASS font sizes use different metrics from the preview's CSS em.
        # Calibrate against the visible line width in the portrait preview.
        if preview is not None:
            font_size *= 1.42
        base_color, border_style, outline = {
            "Editorial": ("#f1e2cb", 1, 0),
            "Clean": ("#ffffff", 1, 0),
            "Block": ("#fff2d6", 3, 4),
        }[look]

        def ass_color(color):
            return color[5:7] + color[3:5] + color[1:3]

        primary = ass_color(base_color)
        y = round(height * position / 100)
        header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 1
ScaledBorderAndShadow: yes
[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Segoe UI,{font_size},&H00{primary},&H00{primary},&H241F1B17,&H80000000,-1,0,0,0,100,100,0,0,{border_style},{outline},0,5,{margin},{margin},0,1
[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
        def time_ass(value):
            h, m, rest = value.split(":")
            seconds, ms = rest.split(",")
            return f"{int(h)}:{m}:{seconds}.{ms[:2]}"

        anchor = rf"{{\pos({width / 2},{y})\b800}}"
        shadow_anchor = rf"{{\pos({width / 2},{y + 2})\b800\bord0\shad0\blur3\1c&H000000&}}"
        events = []
        for block in re.split(r"\n\s*\n", subtitle.read_text(encoding="utf-8-sig").strip()):
            number, timing, text = block.split("\n", 2)
            start, end = timing.split(" --> ")
            pieces = re.split(r"(\s+)", text)
            word_index = 0
            result_text = []
            shadow_text = []
            for piece in pieces:
                if not piece:
                    continue
                if piece.isspace():
                    spacing = piece.replace("\n", r"\N")
                    result_text.append(spacing)
                    shadow_text.append(spacing)
                    continue
                settings = (styles or {}).get(number, {}).get(str(word_index), {})
                color = settings.get("color", base_color)
                scale = settings.get("size", 100)
                if not re.fullmatch(r"#[0-9a-fA-F]{6}", str(color)) or scale not in (80, 100, 125):
                    raise ValueError("Invalid word styling.")
                bgr = ass_color(color)
                safe = piece.replace("\\", "＼").replace("{", "｛").replace("}", "｝")
                scaling = rf"\fscx{scale}\fscy{scale}"
                result_text.append(r"{\c&H" + bgr + "&" + scaling + "}" + safe)
                shadow_text.append("{" + scaling + "}" + safe)
                word_index += 1
            timing_fields = f"{time_ass(start)},{time_ass(end)},Default,,0,0,0,,"
            if look != "Block":
                events.append(f"Dialogue: 0,{timing_fields}{shadow_anchor}{''.join(shadow_text)}")
            events.append(f"Dialogue: 1,{timing_fields}{anchor}{''.join(result_text)}")
        (work / "captions.ass").write_text(header + "\n".join(events) + "\n", encoding="utf-8")
        output = work / f"render.{extension}"
        command = [ffmpeg, "-nostdin", "-hide_banner", "-loglevel", "error", "-n", "-i", str(video)]
        if preserve_encoding:
            command += [
                "-i", "captions.ass", "-map", "0:v", "-map", "0:a?",
                "-map", "1:s:0", "-c", "copy", "-metadata:s:s:0", "title=Caption Baby",
                "-disposition:s:0", "default",
            ]
        else:
            command += [
                "-vf", "ass=captions.ass", "-map", "0:v:0", "-map", "0:a:0?",
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
                "-c:a", "aac", "-movflags", "+faststart",
            ]
        result = subprocess.run(
            [*command, str(output)],
            cwd=work, capture_output=True, text=True, timeout=3600,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if result.returncode:
            raise RuntimeError("Video export failed. " + result.stderr[-500:])
        shutil.copyfile(output, target)
    return target

