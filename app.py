"""Caption Baby local media and transcription server."""
from datetime import datetime
from fractions import Fraction
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Lock, Thread
from uuid import uuid4
import json
import os
import re
import subprocess
import sys
import time
import wave
import webbrowser

from asr_models import DEFAULT_MODEL, MODELS, is_installed, model_list
from captioning import Caption, frame_captions, write_srt
from media_input import choose_export_folder, choose_video, extract_audio
from resolve_bridge import active, connect, make_overlays, place_overlays, render_audio


def run_caption_worker(arguments, log_path, timeout):
    worker = Path(__file__).resolve().with_name("captioning.py")
    if getattr(sys, "frozen", False):
        worker_command = [sys.executable, "--caption-worker", *map(str, arguments)]
    else:
        worker_command = [sys.executable, "-u", str(worker), *map(str, arguments)]
    with log_path.open("wb") as worker_log:
        completed = subprocess.run(
            worker_command,
            stdin=subprocess.DEVNULL, stdout=worker_log, stderr=subprocess.STDOUT,
            timeout=timeout, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            env={**os.environ, "PYTHONUTF8": "1"},
        )
    if completed.returncode:
        print(log_path.read_text(encoding="utf-8", errors="replace"), file=sys.stderr, flush=True)
        raise RuntimeError("The local model failed. Check the audio file or model installation.")


def transcribe(audio, report, model=DEFAULT_MODEL):
    report(f"Transcribing locally with {MODELS[model]['name']}…")
    with TemporaryDirectory(prefix="caption-baby-worker-") as work:
        result = Path(work) / "captions.json"
        try:
            run_caption_worker((audio, result, model), Path(work) / "model.log", 3600)
        except subprocess.TimeoutExpired as error:
            raise RuntimeError("Transcription timed out. Try a shorter WAV export.") from error
        return [Caption(**item) for item in json.loads(result.read_text(encoding="utf-8"))]


def generate(output, add_track, report, model=DEFAULT_MODEL):
    resolve = connect()
    project, _, snapshot = active(resolve)
    frame_count = snapshot.end - snapshot.start
    if frame_count <= 0:
        raise RuntimeError("The active timeline is empty.")
    report(f"Rendering audio from {snapshot.name}…")
    with TemporaryDirectory(prefix="caption-baby-") as temporary:
        audio = render_audio(project, Path(temporary), report)
        with wave.open(str(audio)) as wav:
            duration = wav.getnframes() / wav.getframerate()
        if abs(duration * float(snapshot.fps) - frame_count) > 2:
            raise RuntimeError("The rendered audio length differs from the timeline. Check the Deliver settings.")
        cues = frame_captions(transcribe(audio, report, model), snapshot.fps, frame_count)
    if not cues:
        return "No speech was detected.", None

    folder = output / f"{datetime.now():%Y%m%d-%H%M%S}-{uuid4().hex[:6]}"
    folder.mkdir(parents=True)
    write_srt(folder / "Captions.srt", cues, snapshot.fps)
    if not add_track:
        return f"Saved {len(cues)} captions to Captions.srt.", folder

    try:
        report("Preparing caption overlays…")
        paths = make_overlays(folder, cues, snapshot)
        live_project, live_timeline, live_snapshot = active(resolve)
        if live_snapshot != snapshot:
            raise RuntimeError("The active timeline changed while captions were generating.")
        report("Adding a caption track in Resolve…")
        place_overlays(live_project, live_timeline, snapshot, cues, paths)
    except Exception as error:
        return f"Saved Captions.srt. Resolve placement failed. {error}", folder
    return f"Added {len(cues)} captions to {snapshot.name}. SRT saved.", folder


def caption_wav(audio, output, report, model=DEFAULT_MODEL):
    report("Checking the WAV file…")
    with wave.open(str(audio)) as wav:
        samples, sample_rate = wav.getnframes(), wav.getframerate()
    fps = Fraction(1000)
    cues = frame_captions(transcribe(audio, report, model), fps, round(samples * fps / sample_rate))
    if not cues:
        return "No speech was detected.", None
    folder = output / f"{datetime.now():%Y%m%d-%H%M%S}-{uuid4().hex[:6]}"
    folder.mkdir(parents=True)
    write_srt(folder / "Captions.srt", cues, fps)
    return f"Saved {len(cues)} captions to Captions.srt.", folder


WEB = (Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent)) / "web")
TIMING = re.compile(r"\d{2,}:\d{2}:\d{2},\d{3} --> \d{2,}:\d{2}:\d{2},\d{3}")
MAX_AUDIO_BYTES = 1024 * 1024 * 1024


def read_cues(file):
    cues = []
    for block in re.split(r"\n[ \t]*\n", file.read_text(encoding="utf-8-sig").strip()):
        _, timing, text = block.split("\n", 2)
        if not TIMING.fullmatch(timing):
            raise ValueError("The generated subtitle file contains an invalid timestamp.")
        start, end = timing.split(" --> ")
        cues.append({"start": start, "end": end, "text": text})
    return cues


class EditorServer(ThreadingHTTPServer):
    def __init__(self, from_resolve=False):
        super().__init__(("127.0.0.1", 0), EditorHandler)
        self.origin = f"http://127.0.0.1:{self.server_port}"
        self.prefix = f"/{uuid4().hex}/"
        self.output = Path.home() / "Documents" / "Caption Baby Exports"
        self.lock = Lock()
        self.busy = False
        self.job = {"state": "idle"}
        self.subtitle = None
        self.video = None
        self.picker_open = False
        self.last_export = None
        if from_resolve:
            self.job["message"] = "Opened from Resolve. Use Open WAV or connect to a Studio timeline."

    def reserve(self, message):
        with self.lock:
            if self.busy:
                return False
            self.busy = True
            self.job = {"state": "working", "message": message}
            return True

    def update(self, state, message, **details):
        with self.lock:
            self.job = {"state": state, "message": message, **details}
            if state in {"done", "error"}:
                self.busy = False

    def process(self, audio=None, temporary=None, *, video=None, track=None, model=DEFAULT_MODEL):
        try:
            report = lambda message: self.update("working", message)
            if video:
                report("Extracting the selected audio track…")
                with TemporaryDirectory(prefix="caption-baby-video-") as work:
                    extracted = Path(work) / "audio.wav"
                    extract_audio(video, track, extracted)
                    message, folder = caption_wav(extracted, self.output, report, model)
            elif audio:
                message, folder = caption_wav(audio, self.output, report, model)
            else:
                message, folder = generate(self.output, True, report, model)
            file = folder / "Captions.srt" if folder else None
            cues = read_cues(file) if file else []
            if file:
                with self.lock:
                    self.subtitle = file
            self.update("done", message, cues=cues)
        except Exception as error:
            self.update("error", str(error))
            print(f"Caption job failed: {type(error).__name__}: {error}", file=sys.stderr, flush=True)
        finally:
            if temporary:
                temporary.cleanup()

    def download_model(self, model):
        try:
            with TemporaryDirectory(prefix="caption-baby-model-") as work:
                run_caption_worker(("--download", model), Path(work) / "download.log", 1800)
            self.update("done", f"{MODELS[model]['name']} is ready.", model_download=True)
        except (OSError, RuntimeError, subprocess.TimeoutExpired) as error:
            self.update("error", f"Could not download {MODELS[model]['name']}. {error}")

    def export_video(self, video, subtitle, size, position, styles, preserve_encoding, folder, look, preview):
        try:
            from video_export import render
            self.update("working", "Rendering captioned video…")
            target = render(video.path, subtitle, folder, size, position, styles, preserve_encoding=preserve_encoding, look=look, preview=preview)
            with self.lock:
                self.last_export = target
            self.update("done", f"Exported {target.name}.", exported=True)
        except Exception as error:
            self.update("error", str(error))



class EditorHandler(BaseHTTPRequestHandler):
    def log_message(self, _format, *_args):
        pass

    def send_bytes(self, payload, mime, status=HTTPStatus.OK, filename=None):
        self.send_response(status)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy",
                         "default-src 'self'; media-src 'self' blob:; img-src 'self' blob: data:; "
                         "style-src 'self' 'unsafe-inline'; frame-ancestors 'none'; base-uri 'none'")
        if filename:
            self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.end_headers()
        self.wfile.write(payload)

    def respond(self, value, status=HTTPStatus.OK):
        self.send_bytes(json.dumps(value).encode(), "application/json", status)

    def route(self):
        if self.headers.get("Host") != f"127.0.0.1:{self.server.server_port}":
            return None
        if not self.path.startswith(self.server.prefix):
            return None
        return self.path[len(self.server.prefix):]

    def do_GET(self):
        route = self.route()
        assets = {"": ("index.html", "text/html; charset=utf-8"),
                  "editor.css": ("editor.css", "text/css"),
                  "editor.js": ("editor.js", "text/javascript"),
                  "workspace.js": ("workspace.js", "text/javascript")}
        if route in assets:
            filename, mime = assets[route]
            self.send_bytes((WEB / filename).read_bytes(), mime)
        elif route == "api/status":
            with self.server.lock:
                job = self.server.job.copy()
            self.respond(job)
        elif route == "api/models":
            self.respond({"models": model_list(), "default": DEFAULT_MODEL})
        elif route == "api/subtitle" and self.server.subtitle:
            self.send_bytes(self.server.subtitle.read_bytes(), "application/x-subrip", filename="Captions.srt")
        elif route and route.startswith("api/video/preview/"):
            self.serve_video(route.removeprefix("api/video/preview/"))
        else:
            self.send_error(HTTPStatus.NOT_FOUND)

    def do_POST(self):
        route = self.route()
        if not route or self.headers.get("Origin") != self.server.origin:
            self.send_error(HTTPStatus.FORBIDDEN)
            return
        if route == "api/transcribe":
            self.start_audio()
        elif route == "api/models/download":
            self.start_model_download()
        elif route == "api/video/choose":
            self.choose_media()
        elif route == "api/video/transcribe":
            self.start_video()
        elif route == "api/video/export":
            self.start_export()
        elif route == "api/resolve":
            model = self.request_model()
            if model is None:
                return
            if not self.server.reserve("Connecting to Resolve Studio…"):
                self.respond({"message": "A transcription is already running."}, HTTPStatus.CONFLICT)
                return
            Thread(target=self.server.process, kwargs={"model": model}, daemon=True).start()
            self.respond({"state": "working"}, HTTPStatus.ACCEPTED)
        elif route == "api/save":
            self.save_cues()
        elif route == "api/show-output" and self.server.subtitle:
            try:
                folder = (self.server.last_export or self.server.subtitle).parent
                if sys.platform == "win32":
                    os.startfile(folder)
                elif sys.platform == "darwin":
                    subprocess.Popen(["open", str(folder)])
                else:
                    subprocess.Popen(["xdg-open", str(folder)])
            except (OSError, AttributeError) as error:
                self.respond({"message": str(error)}, HTTPStatus.BAD_REQUEST)
            else:
                self.respond({"message": "Opened the caption folder."})
        elif route == "api/close":
            with self.server.lock:
                busy = self.server.busy
            if busy:
                self.respond({"message": "Wait for the current transcription to finish."}, HTTPStatus.CONFLICT)
                return
            self.respond({"message": "Editor stopped."})
            Thread(target=self.server.shutdown, daemon=True).start()
        else:
            self.send_error(HTTPStatus.NOT_FOUND)

    def choose_media(self):
        with self.server.lock:
            if self.server.picker_open:
                self.respond({"message": "The video picker is already open."}, HTTPStatus.CONFLICT)
                return
            self.server.picker_open = True
        try:
            video = choose_video()
            if video:
                with self.server.lock:
                    self.server.video = video
            self.respond({"video": video.payload() if video else None})
        except (OSError, ValueError, RuntimeError) as error:
            self.respond({"message": str(error)}, HTTPStatus.BAD_REQUEST)
        finally:
            with self.server.lock:
                self.server.picker_open = False

    def request_model(self, *, for_download=False):
        selected = self.headers.get("X-Caption-Model", DEFAULT_MODEL)
        if selected not in MODELS:
            self.respond({"message": "Choose a supported transcription model."}, HTTPStatus.BAD_REQUEST)
            return None
        if not for_download and not is_installed(selected):
            self.respond({"message": f"Download {MODELS[selected]['name']} before transcribing."},
                         HTTPStatus.CONFLICT)
            return None
        return selected

    def start_model_download(self):
        model = self.request_model(for_download=True)
        if model is None:
            return
        if not self.server.reserve(f"Downloading {MODELS[model]['name']}…"):
            self.respond({"message": "An editor job is already running."}, HTTPStatus.CONFLICT)
            return
        try:
            Thread(target=self.server.download_model, args=(model,), daemon=True).start()
        except RuntimeError as error:
            self.server.update("error", str(error))
            self.respond({"message": "Could not start the model download."}, HTTPStatus.SERVICE_UNAVAILABLE)
            return
        self.respond({"state": "working"}, HTTPStatus.ACCEPTED)

    def start_export(self):
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length < 1024 * 1024:
                raise ValueError("Invalid export settings.")
            options = json.loads(self.rfile.read(length))
            with self.server.lock:
                video, subtitle = self.server.video, self.server.subtitle
            if not video or options["token"] != video.token or not subtitle:
                raise ValueError("Open a video and generate captions first.")
            size, position = int(options["size"]), int(options["position"])
            preserve_encoding = options.get("preserve_encoding", False)
            if not isinstance(preserve_encoding, bool):
                raise ValueError("Invalid export mode.")
            look = options.get("look", "Editorial")
            if look not in ("Editorial", "Clean", "Block"):
                raise ValueError("Invalid caption look.")
            preview = options.get("preview")
            if preview is not None and (
                not isinstance(preview, list) or len(preview) != 3
                or any(type(value) not in (int, float) for value in preview)
                or not all(2 <= value <= 16384 for value in preview[:2])
                or not 8 <= preview[2] <= 64
            ):
                raise ValueError("Invalid preview dimensions.")
            styles = options.get("styles", {})
            if not isinstance(styles, dict):
                raise ValueError("Invalid word styles.")
            if not 70 <= size <= 135 or not 20 <= position <= 88:
                raise ValueError("Invalid caption style settings.")
        except (ValueError, KeyError, TypeError) as error:
            self.respond({"message": str(error)}, HTTPStatus.BAD_REQUEST)
            return
        if not self.server.reserve("Starting video export…"):
            self.respond({"message": "An editor job is already running."}, HTTPStatus.CONFLICT)
            return
        try:
            folder = choose_export_folder()
        except (OSError, ValueError, RuntimeError) as error:
            self.server.update("error", str(error))
            self.respond({"message": str(error)}, HTTPStatus.BAD_REQUEST)
            return
        if folder is None:
            self.server.update("done", "Export canceled.")
            self.respond({"state": "canceled"})
            return
        Thread(target=self.server.export_video,
               args=(video, subtitle, size, position, styles, preserve_encoding, folder, look, preview),
               daemon=True).start()
        self.respond({"state": "working"}, HTTPStatus.ACCEPTED)

    def start_video(self):
        model = self.request_model()
        if model is None:
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 1024:
                raise ValueError("Invalid video selection.")
            selection = json.loads(self.rfile.read(length))
            with self.server.lock:
                video = self.server.video
            track = selection["track"]
            if not video or selection["token"] != video.token:
                raise ValueError("Open the video again before generating captions.")
            if type(track) is not int or not any(stream.index == track for stream in video.tracks):
                raise ValueError("Choose an audio track from this video.")
        except (AttributeError, KeyError, TypeError, ValueError) as error:
            self.respond({"message": str(error)}, HTTPStatus.BAD_REQUEST)
            return
        if not self.server.reserve("Starting video transcription…"):
            self.respond({"message": "A transcription is already running."}, HTTPStatus.CONFLICT)
            return
        try:
            Thread(target=self.server.process, kwargs={"video": video, "track": track, "model": model},
                   daemon=True).start()
        except RuntimeError as error:
            self.server.update("error", str(error))
            self.respond({"message": "Could not start video transcription."}, HTTPStatus.SERVICE_UNAVAILABLE)
            return
        self.respond({"state": "working"}, HTTPStatus.ACCEPTED)

    def serve_video(self, token):
        with self.server.lock:
            video = self.server.video
        if not video or token != video.token:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        try:
            file = video.path.open("rb")
        except OSError:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        with file:
            size = os.fstat(file.fileno()).st_size
            first, last = 0, size - 1
            status = HTTPStatus.OK
            requested = self.headers.get("Range")
            if requested:
                match = re.fullmatch(r"bytes=(\d*)-(\d*)", requested)
                if match and (match[1] or match[2]):
                    if match[1]:
                        first = int(match[1])
                        last = min(last, int(match[2])) if match[2] else last
                    else:
                        first = max(0, size - int(match[2]))
                if not match or not (match[1] or match[2]) or first > last:
                    self.send_response(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE)
                    self.send_header("Content-Range", f"bytes */{size}")
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
                status = HTTPStatus.PARTIAL_CONTENT
            remaining = last - first + 1
            self.send_response(status)
            self.send_header("Content-Type", video.mime)
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Content-Length", str(remaining))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            if status == HTTPStatus.PARTIAL_CONTENT:
                self.send_header("Content-Range", f"bytes {first}-{last}/{size}")
            self.end_headers()
            file.seek(first)
            try:
                while remaining:
                    block = file.read(min(1024 * 1024, remaining))
                    if not block:
                        break
                    self.wfile.write(block)
                    remaining -= len(block)
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                pass

    def start_audio(self):
        model = self.request_model()
        if model is None:
            return
        try:
            remaining = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            remaining = 0
        if not 0 < remaining <= MAX_AUDIO_BYTES:
            self.respond({"message": "Choose a WAV file smaller than 1 GB."}, HTTPStatus.BAD_REQUEST)
            return
        if not self.server.reserve("Receiving the timeline WAV…"):
            self.respond({"message": "A transcription is already running."}, HTTPStatus.CONFLICT)
            return
        temporary = None
        previous_timeout = self.connection.gettimeout()
        try:
            self.connection.settimeout(20)
            temporary = TemporaryDirectory(prefix="caption-baby-")
            audio = Path(temporary.name) / "timeline.wav"
            with audio.open("wb") as file:
                while remaining:
                    block = self.rfile.read(min(remaining, 1024 * 1024))
                    if not block:
                        raise ValueError("The WAV upload was interrupted.")
                    file.write(block)
                    remaining -= len(block)
        except (OSError, ValueError) as error:
            message = "The audio transfer stopped. Select the WAV again." if isinstance(error, TimeoutError) else str(error)
            self.server.update("error", message)
            if temporary:
                temporary.cleanup()
            self.respond({"message": message}, HTTPStatus.BAD_REQUEST)
            return
        finally:
            self.connection.settimeout(previous_timeout)
        self.server.update("working", "WAV received. Starting transcription…")
        try:
            Thread(target=self.server.process, args=(audio, temporary), kwargs={"model": model}, daemon=True).start()
        except RuntimeError as error:
            self.server.update("error", "Could not start transcription. Try opening the WAV again.")
            temporary.cleanup()
            print(f"Could not start caption worker: {error}", file=sys.stderr, flush=True)
            self.respond(self.server.job, HTTPStatus.SERVICE_UNAVAILABLE)
            return
        self.respond({"state": "working"}, HTTPStatus.ACCEPTED)

    def save_cues(self):
        file = self.server.subtitle
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not file or not 0 < length <= 8 * 1024 * 1024:
                raise ValueError("Open a generated transcript before saving captions.")
            incoming = json.loads(self.rfile.read(length))
            original = read_cues(file)
            if not isinstance(incoming, list) or len(incoming) != len(original):
                raise ValueError("The caption count changed.")
            blocks = []
            for index, (cue, previous) in enumerate(zip(incoming, original, strict=True), 1):
                text = cue["text"].strip()
                if not text or re.search(r"\n\s*\n|\r", text):
                    raise ValueError("Caption text must contain words and no blank lines.")
                blocks.append(f'{index}\n{previous["start"]} --> {previous["end"]}\n{text}')
            with self.server.lock:
                if self.server.busy or self.server.subtitle != file:
                    raise ValueError("The active transcript changed. Wait for the export and try again.")
                temporary = file.with_suffix(".tmp")
                temporary.write_text("\n\n".join(blocks) + "\n", encoding="utf-8")
                temporary.replace(file)
                self.server.job["cues"] = read_cues(file)
            self.respond({"message": "Caption edits saved."})
        except (KeyError, TypeError, AttributeError, ValueError, OSError) as error:
            self.respond({"message": str(error)}, HTTPStatus.BAD_REQUEST)


def main(from_resolve=False, desktop_engine=False):
    with EditorServer(from_resolve) as server:
        url = server.origin + server.prefix
        if desktop_engine:
            print(url, flush=True)

            def stop_after_parent_exits():
                sys.stdin.buffer.read()
                while True:
                    with server.lock:
                        if not server.busy:
                            break
                    time.sleep(0.15)
                server.shutdown()

            Thread(target=stop_after_parent_exits, daemon=True).start()
        else:
            print(f"Caption Baby running at {url}", flush=True)
            webbrowser.open(url)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    if "--caption-worker" in sys.argv:
        from captioning import run_cli
        run_cli(sys.argv[sys.argv.index("--caption-worker") + 1:])
    elif "--file-picker" in sys.argv:
        from media_input import file_picker_main
        file_picker_main(sys.argv[sys.argv.index("--file-picker") + 1:])
    else:
        main(from_resolve="--from-resolve" in sys.argv, desktop_engine="--desktop-engine" in sys.argv)
