"""Convert Parakeet token timestamps into readable captions."""
from dataclasses import asdict, dataclass
from functools import lru_cache
from pathlib import Path
import json
import math
import os
import sys
import textwrap
from tempfile import TemporaryDirectory

from asr_models import (DEFAULT_MODEL, MODELS, aurora_segments, download_aurora,
                        download_whistle, mono_wav, whistle_segments)


@dataclass(frozen=True)
class Caption:
    start: float
    end: float
    text: str


@lru_cache(maxsize=1)
def parakeet_recognizer():
    import onnx_asr
    import onnxruntime

    options = onnxruntime.SessionOptions()
    options.intra_op_num_threads = min(4, os.cpu_count() or 1)
    options.inter_op_num_threads = 1
    options.add_session_config_entry("session.intra_op.allow_spinning", "0")
    vad = onnx_asr.load_vad("silero", sess_options=options)
    model = onnx_asr.load_model("nemo-parakeet-tdt-0.6b-v3", quantization="int8", sess_options=options)
    return model.with_vad(vad).with_timestamps()


def transcribe(path, report, model=DEFAULT_MODEL):
    if model != DEFAULT_MODEL:
        report(f"Transcribing with {MODELS[model]['name']}…")
        decoder = aurora_segments if model == "aurora" else whistle_segments
        with TemporaryDirectory(prefix="caption-baby-pcm-") as folder:
            source = mono_wav(path, Path(folder))
            return [cue for segment in decoder(source) for cue in group_words(segment)]
    report("Preparing Parakeet. Model files download on first use.")
    recognizer = parakeet_recognizer()
    report("Transcribing the timeline audio locally...")
    captions = []
    for segment in recognizer.recognize(str(path), channel="mean"):
        captions.extend(group_words(segment))
    return captions


def group_words(segment):
    words = []
    for token, timestamp in zip(segment.tokens, segment.timestamps, strict=True):
        token = token.replace("▁", " ")
        if not token or not math.isfinite(timestamp):
            continue
        start = min(segment.end, segment.start + max(0, timestamp))
        if words and not token[0].isspace():
            word = words[-1]
            words[-1] = Caption(word.start, max(word.end, start + 0.08), word.text + token)
        elif token.strip():
            words.append(Caption(start, start + 0.08, token.strip()))

    if not words:
        return []

    groups = [[]]
    for word in words:
        group = groups[-1]
        if group and (
            len(group) >= 7
            or word.start - group[0].start > 2.7
            or word.start - group[-1].end > 0.65
            or group[-1].text.endswith((".", "!", "?", "…"))
            or len(" ".join(part.text for part in [*group, word])) > 64
        ):
            group = []
            groups.append(group)
        group.append(word)

    captions = []
    for index, group in enumerate(groups):
        start = group[0].start
        limit = groups[index + 1][0].start if index + 1 < len(groups) else segment.end
        end = min(limit, max(start + 0.55, group[-1].end + 0.22))
        if end > start:
            text = " ".join(word.text for word in group)
            captions.append(Caption(start, end, "\n".join(textwrap.wrap(
                text, width=36, break_on_hyphens=False
            ))))
    return captions


def frame_captions(captions, fps, frame_count):
    result = []
    previous_end = 0
    for caption in captions:
        start = max(previous_end, round(caption.start * fps))
        end = min(frame_count, max(start + 1, round(caption.end * fps)))
        if start < end:
            result.append((start, end, caption.text))
            previous_end = end
    return result


def srt_time(frame, fps):
    seconds, milliseconds = divmod(round(frame / fps * 1000), 1000)
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours:02}:{minutes:02}:{seconds:02},{milliseconds:03}"


def write_srt(path, cues, fps):
    blocks = [
        f"{index}\n{srt_time(start, fps)} --> {srt_time(end, fps)}\n{text}"
        for index, (start, end, text) in enumerate(cues, 1)
    ]
    path.write_text("\n\n".join(blocks) + "\n", encoding="utf-8")

if __name__ == "__main__":
    if sys.argv[1] == "--download":
        download = {"aurora": download_aurora, "whistle": download_whistle,
                    DEFAULT_MODEL: parakeet_recognizer}
        download[sys.argv[2]]()
    else:
        audio, output = map(Path, sys.argv[1:3])
        model = sys.argv[3] if len(sys.argv) > 3 else DEFAULT_MODEL
        captions = transcribe(audio, lambda message: print(message, file=sys.stderr, flush=True), model)
        output.write_text(json.dumps([asdict(caption) for caption in captions]), encoding="utf-8")
