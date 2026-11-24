# Caption Baby

Caption Baby is a Windows desktop app for captioning the active DaVinci Resolve Studio timeline. It renders the timeline audio mix, transcribes speech on your CPU with NVIDIA Parakeet TDT 0.6B v3, and places timed caption graphics on a new video track. Each successful transcription also produces a UTF-8 SRT.

## Set up

1. Install 64-bit Python 3.12 from [python.org](https://www.python.org/downloads/windows/) with the Python launcher and Tcl/Tk selected.
2. Double-click **Setup Caption Baby.cmd** to install the app dependencies into its local virtual environment.
3. Double-click **Launch Caption Baby.cmd**. It opens the Tauri desktop app after a local build. The browser editor is available as a fallback. The Python engine stays on this PC and shuts down when the desktop app closes and any active job finishes.
   Each launch opens a separate editor session with its own video, transcript, and active transcription. Opening or closing one window does not change the others.
4. **Install Resolve Menu.cmd** adds a launcher under **Workspace → Scripts** on the **Edit** page. If Resolve restricts external process launches from menu scripts, the launcher reports that in **Workspace → Console**. Use **Launch Caption Baby.cmd** in File Explorer on that installation. Resolve Studio with **External scripting using → Local** is required for the editor's **From Resolve** action.

## Choose a transcription model

Select a model in the toolbar and click **Download model** if it is missing. No model weights are bundled with the app. Download sizes below describe the model assets. The Python runtime and optional decoder dependencies use additional space. Transcription runs locally after setup.

| Model | Model download | Use case | Model license |
| --- | ---: | --- | --- |
| [AuroraASR 1M ONNX](https://huggingface.co/mrfakename/AuroraASR-1M-ONNX) | 3.9 MB | Fast experimental English. Expect rougher wording, approximate timing and no punctuation. | Apache 2.0 |
| [Cactus Whistle](https://huggingface.co/Cactus-Compute/whistle) | 16.9 MB | Compact decoder with word timestamps in seven languages. Also downloads its platform runtime. | Apache 2.0 |
| [NVIDIA Parakeet v3 ONNX](https://huggingface.co/istupakov/parakeet-tdt-0.6b-v3-onnx) | About 673 MB | Higher-accuracy option with 25 languages. Includes the Silero speech detector download. | CC BY 4.0 for Parakeet |

Keep the active timeline and its edits in place when transcribing directly from Resolve Studio.

## Build the desktop app

Install a stable Windows MSVC Rust toolchain, Microsoft C++ Build Tools with a Windows SDK, and the WebView2 runtime. Run **Build Caption Baby.cmd** to compile the executable. The frontend uses plain HTML, CSS, and JavaScript, so the build needs no Node.js tooling. This workspace build uses its existing Python environment and model cache.

## Caption a video or WAV in any Resolve edition

Use **Open video** to select a local export. Select the dialogue track if the video has multiple audio tracks, then click **Generate captions**. FFmpeg and FFprobe must be on Windows PATH. Caption Baby extracts only the selected audio track and keeps the video on disk for preview. Browser-compatible exports, such as H.264 MP4, support preview playback and scrubbing.

To caption an audio export, render the **Entire Timeline** as a single audio-only WAV using 16-bit Linear PCM. Drop the export on the viewer or click **Open WAV**. Click a transcript row or timeline block to seek to that caption. Edit its text in the Inspector, then click **Save edit**. The style controls apply to the preview.

Use **Download SRT** or **Show in Explorer**, then import the SRT into Resolve. With an empty subtitle track available, place the subtitles at the start of the audio range. Direct timeline access and placement use the Resolve Studio API.

## Use the captions

- **Visible captions** appear on a new video track named **Caption Baby**, with transparent PNG clips in a dedicated Media Pool bin. Keep the output folder on disk so Resolve can find the graphics. Each run creates its own track and output folder.
- **Editable subtitles** are available in **Captions.srt**. Hide the Caption Baby video track if you use the editable subtitles after generating Studio overlays.
- **Deliver settings** are used for the temporary WAV render. The app removes its render job and restores the previous format, codec, and render mode. Check other Deliver settings before your next export.

The prototype uses a fixed caption style. A live check needs an open Resolve Studio project with a short speech timeline.

### Standalone Windows installer

The release target is Windows 10 and 11 on x64. Build with x64 CPython
3.12 (including Tcl/Tk), FFmpeg and FFprobe, Rust's MSVC toolchain and the
Tauri 2 CLI. Run `Build Windows Installer.cmd`. The NSIS installer is written
under `src-tauri/target/release/bundle/nsis`.

The installer includes Python, the media tools and the offline WebView2
installer. Transcription models are downloaded on demand into the user's
local app data. Resolve integration still requires Resolve and its scripting
support. Builds without a signing certificate may show a publisher warning.


The manually dispatched **Windows installer** GitHub Actions workflow builds
the same x64 setup package and uploads it as a workflow artifact.
