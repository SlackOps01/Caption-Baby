# Caption Baby

Caption Baby is a desktop caption editor. On Windows it can caption the active DaVinci Resolve Studio timeline, render its audio mix, transcribe speech locally with NVIDIA Parakeet TDT 0.6B v3 and place timed caption graphics on a new video track. On macOS and Linux, use an exported WAV or video file to caption media. Each successful transcription also produces a UTF-8 SRT.

## Install a desktop release

Choose the package for your operating system from the repository's GitHub
Releases. Windows gets an x64 installer, Linux gets x64 AppImage and Debian
packages, and macOS gets separate Intel and Apple Silicon disk images. These
packages include the Python engine and FFmpeg tools; model weights download
only when selected.

The macOS app is currently unsigned and unnotarized. On Linux, install a
distribution with the WebKitGTK 4.1 runtime. Direct Resolve timeline access is
currently Windows-only; opening exported video or WAV files works across the
three desktop builds.

## Set up the Windows source checkout

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

Use **Open video** to select a local export. Select the dialogue track if the video has multiple audio tracks, then click **Generate captions**. Release builds include FFmpeg and FFprobe; local development builds require them on PATH. Caption Baby extracts only the selected audio track and keeps the video on disk for preview. Browser-compatible exports, such as H.264 MP4, support preview playback and scrubbing.

To caption an audio export, render the **Entire Timeline** as a single audio-only WAV using 16-bit Linear PCM. Drop the export on the viewer or click **Open WAV**. Click a transcript row or timeline block to seek to that caption. Edit its text in the Inspector, then click **Save edit**. The style controls apply to the preview.

Use **Download SRT** or **Show folder**, then import the SRT into Resolve. With an empty subtitle track available, place the subtitles at the start of the audio range. Direct timeline access and placement use the Resolve Studio API.

## Use the captions

- **Visible captions** appear on a new video track named **Caption Baby**, with transparent PNG clips in a dedicated Media Pool bin. Keep the output folder on disk so Resolve can find the graphics. Each run creates its own track and output folder.
- **Editable subtitles** are available in **Captions.srt**. Hide the Caption Baby video track if you use the editable subtitles after generating Studio overlays.
- **Deliver settings** are used for the temporary WAV render. The app removes its render job and restores the previous format, codec, and render mode. Check other Deliver settings before your next export.

The prototype uses a fixed caption style. A live check needs an open Resolve Studio project with a short speech timeline.

### Standalone desktop releases

The GitHub Actions release workflow builds a Windows x64 NSIS installer, Linux
x64 AppImage and Debian package, and macOS disk images for Intel and Apple
Silicon. Its Python engine and FFmpeg/FFprobe tools are included in the
packages. Transcription models are downloaded on demand into the user's local
app data.

To publish, push a version tag such as `v0.1.1`, or open **Actions → Desktop
release → Run workflow** and enter a new release tag. Both routes build the
platform packages and attach them to a GitHub Release. The release is created
after every platform build succeeds.

Windows 10 and 11 use the bundled WebView2 installer. Linux AppImage and Debian
packages require a compatible WebKitGTK 4.1 runtime. macOS builds are unsigned
and unnotarized, so Gatekeeper may require opening the app from Finder's
context menu. Resolve's direct timeline integration is currently supported
only on Windows; video and WAV captioning works in the macOS and Linux builds.
