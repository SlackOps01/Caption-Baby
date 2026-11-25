"""Optional local ASR models, their download assets, and small-model decoders."""
from functools import lru_cache
from hashlib import sha256
from importlib.util import find_spec
from pathlib import Path
from subprocess import DEVNULL, PIPE, STDOUT, run
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from urllib.request import urlopen
import json
import os
import platform
import shutil
import subprocess
import sys
import wave


DATA = Path(os.environ.get("CAPTION_BABY_DATA") or (Path(__file__).resolve().parent / ".venv"))
CACHE = DATA / "caption-models"
AURORA_FILES = {
    "model.onnx": (3903682, "63c1470b4f83e93d56d77782c85a7550b8751ce15c9c9bf0fcdcdc85b812093e"),
    "vocab.json": (2111, "54ea59504d834f3976d2bbce3f18edddf7defb669378d88f9f522b080cca9a46"),
}
PARAKEET_FILES = {
    "istupakov/parakeet-tdt-0.6b-v3-onnx": (
        "config.json", "encoder-model.int8.onnx", "decoder_joint-model.int8.onnx", "vocab.txt",
    ),
    "istupakov/silero-vad-onnx": ("config.json", "silero_vad.onnx"),
}
DEFAULT_MODEL = "parakeet"
MOONSHINE_MODELS = {"moonshine-tiny": "TINY", "moonshine-base": "BASE"}
MOONSHINE_RUNTIME = CACHE / "moonshine-runtime-0.1.6"
MODELS = {
    "aurora": {"name": "AuroraASR 1M", "size": "3.9 MB", "language": "English", "note": "Experimental · no punctuation"},
    "whistle": {"name": "Cactus Whistle", "size": "16.9 MB", "language": "7 languages", "note": "Compact · optional runtime"},
    "moonshine-tiny": {"name": "Moonshine Tiny", "size": "≈44 MB", "language": "English", "note": "Model size · shared runtime extra · estimated word timing"},
    "moonshine-base": {"name": "Moonshine Base", "size": "≈141 MB", "language": "English", "note": "Model size · shared runtime extra · estimated word timing"},
    "parakeet": {"name": "Parakeet v3", "size": "≈673 MB", "language": "25 languages", "note": "Higher accuracy"},
}


def is_installed(model):
    if model in MOONSHINE_MODELS:
        return moonshine_runtime_installed() and moonshine_model_path(model) is not None
    if model == "aurora":
        folder = CACHE / model
        return all((folder / name).is_file() and (folder / name).stat().st_size == size
                   for name, (size, _) in AURORA_FILES.items())
    if model == "whistle":
        return (CACHE / model / "ready").is_file()
    from huggingface_hub import try_to_load_from_cache

    return all(isinstance(try_to_load_from_cache(repo, name), str)
               for repo, files in PARAKEET_FILES.items() for name in files)


def model_list():
    moonshine_available = moonshine_runtime_installed() or moonshine_platform_supported()
    return [{"id": name, **details, "installed": is_installed(name)}
            for name, details in MODELS.items() if moonshine_available or name not in MOONSHINE_MODELS]


def moonshine_runtime_installed():
    return ((MOONSHINE_RUNTIME / "moonshine_voice" / "__init__.py").is_file()
            or find_spec("moonshine_voice") is not None)


def moonshine_platform_supported():
    machine = platform.machine().lower()
    if sys.platform == "win32":
        return machine in {"amd64", "x86_64"} and sys.maxsize > 2**32
    if sys.platform == "darwin":
        return machine == "arm64" and int(platform.release().split(".")[0]) >= 24
    if sys.platform == "linux" and machine == "x86_64":
        try:
            name, version = os.confstr("CS_GNU_LIBC_VERSION").split()
            return name == "glibc" and tuple(map(int, version.split(".")[:2])) >= (2, 34)
        except (AttributeError, OSError, ValueError):
            return False
    return False


def prepare_moonshine_runtime():
    if not moonshine_runtime_installed():
        if not moonshine_platform_supported():
            raise RuntimeError("Moonshine has no compatible runtime for this platform.")
        CACHE.mkdir(parents=True, exist_ok=True)
        with TemporaryDirectory(dir=CACHE) as temporary:
            staging = Path(temporary) / "runtime"
            args = ["install", "--disable-pip-version-check", "--only-binary=:all:",
                    "--target", str(staging), "moonshine-voice==0.1.6"]
            if getattr(sys, "frozen", False):
                from pip._internal.cli.main import main as pip_main
                status = pip_main(args)
            else:
                status = run([sys.executable, "-m", "pip", *args], stdin=DEVNULL,
                             timeout=600, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).returncode
            if status or not (staging / "moonshine_voice" / "__init__.py").is_file():
                raise RuntimeError("Could not install the Moonshine runtime.")
            try:
                staging.rename(MOONSHINE_RUNTIME)
            except OSError:
                if not moonshine_runtime_installed():
                    raise
    if MOONSHINE_RUNTIME.is_dir() and str(MOONSHINE_RUNTIME) not in sys.path:
        sys.path.insert(0, str(MOONSHINE_RUNTIME))


def moonshine_model_path(model):
    cache = CACHE / model
    try:
        folder = cache / (cache / "ready").read_text(encoding="utf-8")
    except OSError:
        return None
    files = ("encoder_model.ort", "decoder_model_merged.ort", "tokenizer.bin")
    return folder if all((folder / name).is_file() for name in files) else None


def moonshine_engine(model):
    prepare_moonshine_runtime()
    from moonshine_voice import ModelArch, Transcriber, get_model_for_language

    arch = getattr(ModelArch, MOONSHINE_MODELS[model])
    cache = (CACHE / model).resolve()
    folder = moonshine_model_path(model)
    if folder is None:
        path, arch = get_model_for_language("en", arch, cache_root=cache)
        folder = Path(path).resolve()
    engine = Transcriber(model_path=str(folder), model_arch=arch)
    if not is_installed(model):
        with TemporaryDirectory(dir=cache) as temporary:
            ready = Path(temporary) / "ready"
            ready.write_text(str(folder.resolve().relative_to(cache)), encoding="utf-8")
            ready.replace(cache / "ready")
    return engine


def moonshine_segments(path, model):
    prepare_moonshine_runtime()
    from moonshine_voice import load_wav_file

    audio, sample_rate = load_wav_file(str(path))
    block_size = 60 * sample_rate
    with moonshine_engine(model) as engine:
        for offset in range(0, len(audio), block_size):
            block = audio[offset:offset + block_size]
            transcript = engine.transcribe_without_streaming(block, sample_rate)
            for line in transcript.lines:
                words = line.text.split()
                if words and line.duration > 0:
                    start = offset / sample_rate + max(0, line.start_time)
                    end = min(start + line.duration, (offset + len(block)) / sample_rate)
                    if end > start:
                        yield SimpleNamespace(
                            start=start, end=end, tokens=[" " + word for word in words],
                            timestamps=[index * (end - start) / len(words)
                                        for index in range(len(words))],
                        )


def download_aurora():
    folder = CACHE / "aurora"
    folder.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=folder) as temporary:
        for name, (size, checksum) in AURORA_FILES.items():
            destination = folder / name
            if destination.is_file() and sha256(destination.read_bytes()).hexdigest() == checksum:
                continue
            url = f"https://huggingface.co/mrfakename/AuroraASR-1M-ONNX/resolve/main/{name}"
            with urlopen(url, timeout=30) as response:
                data = response.read(size + 1)
            if len(data) != size or sha256(data).hexdigest() != checksum:
                raise RuntimeError(f"Aurora download did not match its checksum: {name}")
            staged = Path(temporary) / name
            staged.write_bytes(data)
            staged.replace(destination)


def whistle_engine():
    os.environ["DO_NOT_TRACK"] = "1"
    os.environ["CACTUS_TELEMETRY"] = "0"
    sys.path.insert(0, str(CACHE / "whistle" / "runtime"))
    import cactus

    return cactus.Whistle()


def download_whistle():
    folder = CACHE / "whistle"
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / "runtime"
    if not (target / "cactus").is_dir():
        with TemporaryDirectory(dir=folder) as temporary:
            staging = Path(temporary) / "runtime"
            if getattr(sys, "frozen", False):
                from pip._internal.cli.main import main as pip_main

                status = pip_main(["install", "--disable-pip-version-check", "--no-deps",
                                   "--target", str(staging), "cactus-compute==4.2.7"])
                if status:
                    raise RuntimeError("Whistle's optional decoder could not be installed.")
            else:
                result = run(
                    [sys.executable, "-m", "pip", "install", "--disable-pip-version-check",
                     "--no-deps", "--target", str(staging), "cactus-compute==4.2.7"],
                    stdin=DEVNULL, stdout=PIPE, stderr=STDOUT, text=True, timeout=180,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
                if result.returncode:
                    raise RuntimeError("Whistle's optional decoder could not be installed. " + result.stdout)
            try:
                staging.rename(target)
            except OSError:
                if not (target / "cactus").is_dir():
                    raise
    whistle_engine()
    (folder / "ready").touch()


def mono_wav(path, folder):
    with wave.open(str(path)) as audio:
        if (audio.getframerate(), audio.getnchannels(), audio.getsampwidth()) == (16000, 1, 2):
            return path
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("This model needs 16 kHz mono PCM WAV. Add FFmpeg to convert other WAV files.")
    from media_input import run_tool

    converted = folder / "mono.wav"
    run_tool([ffmpeg, "-nostdin", "-v", "error", "-i", str(path), "-ac", "1",
              "-ar", "16000", "-c:a", "pcm_s16le", str(converted)], timeout=1800)
    return converted


@lru_cache(maxsize=1)
def mel_filters():
    import numpy as np

    frequencies = np.linspace(0, 8000, 257, dtype=np.float32)
    mel = lambda hertz: 2595 * np.log10(1 + hertz / 700)
    bounds = 700 * (10 ** (np.linspace(mel(20), mel(8000), 82) / 2595) - 1)
    down = (frequencies[:, None] - bounds[:-2]) / (bounds[1:-1] - bounds[:-2])
    up = (bounds[2:] - frequencies[:, None]) / (bounds[2:] - bounds[1:-1])
    return np.maximum(0, np.minimum(down, up)).astype(np.float32)


def aurora_features(samples):
    import numpy as np

    padded = np.pad(samples, (256, 256), mode="reflect")
    frames = np.lib.stride_tricks.sliding_window_view(padded, 512)[::160]
    window = np.zeros(512, dtype=np.float32)
    window[56:456] = np.hanning(401)[:-1]
    fft = np.fft.rfft(frames * window)
    power = np.abs(fft).astype(np.float32) ** 2
    mel = np.log(power @ mel_filters() + 1e-10)
    return ((mel - mel.mean(axis=0)) / (mel.std(axis=0) + 1e-5))[None].astype(np.float32)


def aurora_segments(path):
    import numpy as np
    import onnxruntime as ort

    folder = CACHE / "aurora"
    vocabulary = json.loads((folder / "vocab.json").read_text(encoding="utf-8"))["tokens"]
    options = ort.SessionOptions()
    options.intra_op_num_threads = min(4, os.cpu_count() or 1)
    options.inter_op_num_threads = 1
    session = ort.InferenceSession(str(folder / "model.onnx"), sess_options=options,
                                   providers=["CPUExecutionProvider"])
    with wave.open(str(path)) as audio:
        total = audio.getnframes()
        offset = 0
        while offset < total:
            audio.setpos(offset)
            pcm = np.frombuffer(audio.readframes(14 * 16000), dtype="<i2")
            end = len(pcm)
            if offset + end < total:
                tail = pcm[10 * 16000:].astype(np.float32).reshape(-1, 1600)
                cut = int(np.argmin(np.mean(tail ** 2, axis=1)))
                end = 10 * 16000 + cut * 1600 + 800
            if end >= 512 and np.any(np.abs(pcm[:end].astype(np.int32)) > 32):
                features = aurora_features(pcm[:end].astype(np.float32) / 32768)
                logits = session.run(None, {"input_features": features})[0][0]
                ids = logits.argmax(axis=-1)
                keep = np.flatnonzero((ids > 1) & (ids != np.r_[-1, ids[:-1]]))
                yield SimpleNamespace(tokens=[vocabulary[ids[i]] for i in keep],
                                      timestamps=[i * .04 for i in keep],
                                      start=offset / 16000, end=(offset + end) / 16000)
            offset += end


def whistle_segments(path):
    result = whistle_engine().transcribe(str(path), word_timestamps=True)
    words = result.get("words", [])
    if words:
        yield SimpleNamespace(tokens=["▁" + word.get("word", word.get("text", "")).strip() for word in words],
                              timestamps=[word["start"] for word in words],
                              start=0, end=words[-1]["end"])
