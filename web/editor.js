"use strict";

document.body.classList.toggle('desktop', window.captionBabyDesktop === true);

const $ = (id) => document.getElementById(id);
const video = $("preview");
const seek = $("seek");
const transcript = $("cue-list");
let cues = [];
let selected = -1;
let visibleCaption = -1;
let videoUrl = "";
let nativeVideo = null;
let choosingVideo = false;
let duration = 0;
let ready = false;
let running = false;
let submitting = false;
let statusRequest = false;
let statusErrors = 0;
let editing = false;
let saving = false;
let stopped = false;
let search = "";
let nodes = [];
let blocks = [];
let wordStyles = {};
let selectedWord = -1;

function drawWords() {
  const list = $("word-list");
  const words = selected >= 0 ? cues[selected].text.match(/\S+/g) || [] : [];
  list.replaceChildren(...words.map((word, index) => {
    const button = document.createElement("button");
    button.className = "small word-chip";
    button.textContent = word;
    button.setAttribute("aria-pressed", String(index === selectedWord));
    button.onclick = () => {
      selectedWord = index;
      const style = wordStyles[String(selected + 1)]?.[String(index)] || {};
      $("word-color").value = style.color || "#ffffff";
      $("word-size").value = String(style.size || 100);
      $("word-color").disabled = $("word-size").disabled = false;
      drawWords();
    };
    return button;
  }));
}

function paintCaption(index) {
  const overlay = $("overlay");
  overlay.replaceChildren();
  if (index < 0) return;
  let word = 0;
  for (const part of cues[index].text.split(/(\s+)/)) {
    if (/^\s+$/.test(part) || !part) { overlay.append(document.createTextNode(part)); continue; }
    const span = document.createElement("span");
    const style = wordStyles[String(index + 1)]?.[String(word)] || {};
    span.textContent = part;
    if (style.color) span.style.color = style.color;
    if (style.size) span.style.fontSize = style.size + "%";
    overlay.append(span);
    word++;
  }
}
let models = [];

function seconds(timestamp) {
  const [h, m, s] = timestamp.replace(",", ".").split(":").map(Number);
  return h * 3600 + m * 60 + s;
}

function timecode(value) {
  const ticks = Math.max(0, Math.round(value * 100));
  const minute = String(Math.floor(ticks / 6000)).padStart(2, "0");
  const second = String(Math.floor(ticks / 100) % 60).padStart(2, "0");
  return minute + ":" + second + "." + String(ticks % 100).padStart(2, "0");
}

function status(message, state = "idle") {
  $("status").textContent = message;
  $("status").dataset.state = state;
}

async function api(route, options) {
  const response = await fetch("api/" + route, options);
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.message || "The local editor request failed.");
  return data;
}

function setBusy(value) {
  running = value;
  const model = selectedModel();
  for (const id of ["open-wav", "resolve"]) $(id).disabled = value || !model?.installed;
  $("close").disabled = value;
  $("save").disabled = value || selected < 0;
  $("open-video").disabled = value || choosingVideo;
  $("caption-video").disabled = value || !model?.installed || !nativeVideo?.tracks.length;
  $("audio-track").disabled = value || !nativeVideo?.tracks.length;
  $("cue-text").disabled = value || selected < 0 || saving;
  for (const id of ["uppercase", "lowercase"]) $(id).disabled = value || selected < 0;
  $("export-original").disabled = $("export-video").disabled = value || !nativeVideo || !cues.length;
  $("model-choice").disabled = value || !models.length;
  $("download-model").hidden = !model || model.installed;
  $("download-model").disabled = value;
  $("model-detail").textContent = model
    ? model.language + " · " + model.note + (model.installed ? " · Ready" : "")
    : "";
}

function selectedModel() {
  return models.find((model) => model.id === $("model-choice").value);
}

async function refreshModels() {
  const previous = $("model-choice").value;
  const result = await api("models", {cache: "no-store", signal: AbortSignal.timeout(5000)});
  models = result.models;
  const choice = $("model-choice");
  choice.replaceChildren(...models.map((model) => new Option(model.name + " · " + model.size, model.id)));
  choice.value = models.some((model) => model.id === previous) ? previous :
    models.find((model) => model.id === result.default && model.installed)?.id ||
    models.find((model) => model.installed)?.id || models[0].id;
  setBusy(running);
}

async function downloadSelectedModel() {
  const model = selectedModel();
  if (running || !model || model.installed) return;
  submitting = true;
  statusErrors = 0;
  setBusy(true);
  status("Downloading " + model.name + "…", "working");
  try {
    await api("models/download", {method:"POST", headers:{"X-Caption-Model":model.id},
                                  signal:AbortSignal.timeout(10000)});
  } catch (error) {
    fail(error);
    return;
  } finally {
    submitting = false;
  }
  await poll();
}

function updateDuration() {
  duration = Math.max(Number.isFinite(video.duration) ? video.duration : 0, cues.at(-1)?.endTime || 0);
  seek.max = duration || 1;
  seek.disabled = !duration;
  $("duration").textContent = timecode(duration);
  drawTimeline();
}

function drawTimeline() {
  const divisor = duration || 1;
  const ruler = $("ruler");
  ruler.replaceChildren(...Array.from({length: 6}, (_, index) => {
    const tick = document.createElement("span");
    tick.textContent = timecode(duration * index / 5).split(".")[0];
    return tick;
  }));
  blocks = cues.map((cue, index) => {
    const block = document.createElement("button");
    block.className = "cue-block";
    block.style.left = (cue.startTime / divisor * 100) + "%";
    block.style.width = Math.max(.3, (cue.endTime - cue.startTime) / divisor * 100) + "%";
    block.title = cue.text;
    block.textContent = cue.text;
    block.setAttribute("aria-label", timecode(cue.startTime) + " " + cue.text);
    block.classList.toggle("is-selected", index === selected);
    block.addEventListener("click", (event) => { event.stopPropagation(); select(index); });
    return block;
  });
  $("blocks").replaceChildren(...blocks);
  $("playhead").style.left = (Number(seek.value) / divisor * 100) + "%";
}

function drawTranscript() {
  nodes = cues.map((cue, index) => {
    if (search && !cue.text.toLocaleLowerCase().includes(search)) return null;
    const row = document.createElement("button");
    row.className = "cue-row";
    row.setAttribute("aria-selected", String(index === selected));
    row.classList.toggle("is-playing", index === visibleCaption);
    const timestamp = document.createElement("span");
    timestamp.className = "timecode";
    timestamp.textContent = timecode(cue.startTime);
    const words = document.createElement("span");
    words.textContent = cue.text.replaceAll("\n", " ");
    row.append(timestamp, words);
    row.addEventListener("click", () => select(index));
    return row;
  });
  transcript.replaceChildren(...nodes.filter(Boolean));
  $("cue-count").textContent = String(cues.length);
  $("empty-transcript").hidden = Boolean(cues.length);
}

function activeCue(time) {
  let left = 0;
  let right = cues.length - 1;
  while (left <= right) {
    const middle = (left + right) >> 1;
    if (cues[middle].startTime <= time) left = middle + 1;
    else right = middle - 1;
  }
  return right >= 0 && time < cues[right].endTime ? right : -1;
}

function showCaption(index) {
  if (visibleCaption !== index) {
    nodes[visibleCaption]?.classList.remove("is-playing");
    const row = nodes[index];
    row?.classList.add("is-playing");
    if (row && ready && !video.paused) {
      const listBounds = transcript.getBoundingClientRect();
      const top = listBounds.top + transcript.clientTop;
      const bottom = top + transcript.clientHeight;
      const bounds = row.getBoundingClientRect();
      if (bounds.top < top || bounds.bottom > bottom) {
        transcript.scrollTop += bounds.top < top ? bounds.top - top : bounds.bottom - bottom;
      }
    }
    visibleCaption = index;
  }
  const overlay = $("overlay");
  overlay.hidden = index < 0;
  if (index >= 0) paintCaption(index);
}

function position(time) {
  seek.value = time;
  $("position").textContent = timecode(time);
  $("playhead").style.left = (duration ? time / duration * 100 : 0) + "%";
  const index = activeCue(time);
  if (index !== visibleCaption || $("overlay").hidden !== (index < 0)) showCaption(index);
}

function jump(time) {
  if (ready) video.currentTime = Math.min(time, video.duration);
  position(time);
}

function select(index) {
  if (!cues[index]) return;
  if (saving) return;
  if (editing) {
    status("Save your caption edit before selecting another row.");
    return;
  }
  nodes[selected]?.setAttribute("aria-selected", "false");
  blocks[selected]?.classList.remove("is-selected");
  selected = index;
  selectedWord = -1;
  $("word-color").disabled = $("word-size").disabled = true;
  drawWords();
  const cue = cues[index];
  nodes[index]?.setAttribute("aria-selected", "true");
  blocks[index]?.classList.add("is-selected");
  nodes[index]?.scrollIntoView({block: "nearest"});
  $("cue-text").disabled = false;
  $("cue-text").value = cue.text;
  $("cue-time").textContent = timecode(cue.startTime) + " — " + timecode(cue.endTime);
  $("save").disabled = running;
  setBusy(running);
  jump(cue.startTime);
  showCaption(index);
}

function setCues(raw, selection = 0) {
  wordStyles = {};
  const loaded = raw.map((cue) => ({...cue, startTime: seconds(cue.start), endTime: seconds(cue.end)}));
  selected = -1;
  visibleCaption = -1;
  editing = false;
  cues = loaded;
  $("cue-text").value = "";
  $("cue-text").disabled = true;
  $("cue-time").textContent = "No caption selected";
  $("save").disabled = true;
  $("download").hidden = !cues.length;
  $("show-output").disabled = !cues.length;
  drawTranscript();
  updateDuration();
  if (cues.length) select(Math.max(0, Math.min(selection, cues.length - 1)));
  else position(ready ? video.currentTime : 0);
}

async function poll() {
  if (stopped || statusRequest) return;
  statusRequest = true;
  try {
    const job = await api("status", {cache: "no-store", signal: AbortSignal.timeout(5000)});
    statusErrors = 0;
    if (job.state === "working") {
      setBusy(true);
      status(job.message, "working");
    } else if (!submitting) {
      setBusy(false);
      if (job.message) status(job.message, job.state);
      if (job.state === "done") {
        if (job.model_download) await refreshModels();
        if (job.cues) setCues(job.cues);
      }
    }
  } catch (error) {
    statusErrors += 1;
    if (statusErrors >= 3 && !submitting) {
      fail(new Error("The local engine stopped responding. Try opening the WAV again."));
    }
  } finally {
    statusRequest = false;
  }
}

function fail(error) {
  setBusy(false);
  status(error.message, "error");
}

async function transcribe(file, sourceVideo = null) {
  if (running || saving) return;
  const model = selectedModel();
  if (!model?.installed) {
    status("Choose and download a transcription model first.", "error");
    return;
  }
  if (editing) {
    status("Save your caption edit before loading new audio.");
    return;
  }
  if (file && !/\.wav$/i.test(file.name)) {
    status("Choose a WAV file for transcription.", "error");
    return;
  }
  if (file) $("source-name").textContent = file.name.replace(/\.wav$/i, "");
  if (sourceVideo) $("source-name").textContent = sourceVideo.name;
  submitting = true;
  statusErrors = 0;
  setBusy(true);
  const route = sourceVideo ? "video/transcribe" : file ? "transcribe" : "resolve";
  status(sourceVideo ? "Starting video captions…" : file ? "Reading the timeline WAV…" :
    "Connecting to Resolve Studio…", "working");
  try {
    await api(route, {
      method: "POST",
      body: sourceVideo ? JSON.stringify({token: sourceVideo.token, track: Number($("audio-track").value)}) :
        file || undefined,
      headers: {"X-Caption-Model":model.id, ...(sourceVideo ? {"Content-Type":"application/json"} : {})},
      signal: AbortSignal.timeout(120000),
    });
  } catch (error) {
    fail(error);
    return;
  } finally {
    submitting = false;
  }
  await poll();
}

async function save() {
  if (selected < 0 || running || saving) return;
  const text = $("cue-text").value.trim();
  const next = cues.map((cue, index) => ({text: index === selected ? text : cue.text}));
  $("save").disabled = true;
  $("cue-text").disabled = true;
  saving = true;
  try {
    const result = await api("save", {method: "POST", headers: {"Content-Type": "application/json"},
                                     body: JSON.stringify(next)});
    cues[selected].text = text;
    delete wordStyles[String(selected + 1)];
    selectedWord = -1;
    $("word-color").disabled = $("word-size").disabled = true;
    drawWords();
    editing = false;
    drawTranscript();
    drawTimeline();
    showCaption(selected);
    status(result.message);
  } catch (error) {
    status(error.message, "error");
  } finally {
    saving = false;
    $("cue-text").disabled = false;
    $("save").disabled = false;
  }
}

function fitVideo() {
  const stage = $("stage");
  const ratio = ready ? video.videoWidth / video.videoHeight : 9 / 16;
  const width = Math.max(1, Math.min(stage.clientWidth - 28, (stage.clientHeight - 28) * ratio));
  $("viewport").style.width = width + "px";
  $("viewport").style.height = width / ratio + "px";
}

function loadVideo(url) {
  if (videoUrl.startsWith("blob:")) URL.revokeObjectURL(videoUrl);
  ready = false;
  $("play").disabled = true;
  video.hidden = true;
  $("empty-preview").hidden = false;
  videoUrl = url;
  video.src = videoUrl;
  video.load();
  status("Loading preview…");
}

function setVideoSource(source) {
  nativeVideo = source;
  const tracks = $("audio-track");
  tracks.replaceChildren();
  $("video-tools").hidden = !source;
  for (const track of source?.tracks || []) {
    tracks.add(new Option(track.label, String(track.index)));
  }
  if (source?.tracks.length) tracks.value = String(source.default);
  $("track-label").hidden = tracks.hidden = (source?.tracks.length || 0) <= 1;
  setBusy(running);
}

async function chooseVideo() {
  if (choosingVideo || running) return;
  choosingVideo = true;
  $("open-video").disabled = true;
  try {
    const {video: source} = await api("video/choose", {method: "POST"});
    if (!source) return;
    setVideoSource(source);
    loadVideo("api/video/preview/" + source.token);
    if (!source.tracks.length) status("This video has no audio track.", "error");
  } catch (error) {
    status(error.message, "error");
  } finally {
    choosingVideo = false;
    setBusy(running);
  }
}

$("open-wav").addEventListener("click", () => $("wav-file").click());
$("open-video").addEventListener("click", chooseVideo);
$("caption-video").addEventListener("click", () => transcribe(null, nativeVideo));
$("wav-file").addEventListener("change", (event) => {
  const file = event.target.files[0];
  event.target.value = "";
  if (file) transcribe(file);
});
$("resolve").addEventListener("click", () => transcribe(null));
$("search").addEventListener("input", (event) => {
  search = event.target.value.trim().toLocaleLowerCase();
  drawTranscript();
});
$("cue-text").addEventListener("input", (event) => {
  editing = event.target.value.trim() !== cues[selected]?.text;
});
$("save").addEventListener("click", save);
for (const id of ["word-color", "word-size"]) {
  $(id).addEventListener("input", () => {
    if (selected < 0 || selectedWord < 0) return;
    const caption = wordStyles[String(selected + 1)] ||= {};
    const style = caption[String(selectedWord)] ||= {};
    if (id === "word-color") style.color = $("word-color").value;
    else style.size = Number($("word-size").value);
    paintCaption(selected);
  });
}
for (const [id, convert] of [["uppercase", (text) => text.toLocaleUpperCase()],
                             ["lowercase", (text) => text.toLocaleLowerCase()]]) {
  $(id).addEventListener("click", () => {
    $("cue-text").value = convert($("cue-text").value);
    $("cue-text").dispatchEvent(new Event("input"));
  });
}
async function exportVideo(preserveEncoding) {
  if (editing) { status("Save your caption edit before exporting."); return; }
  const viewport = $("viewport");
  const previewWidth = viewport.clientWidth;
  const previewHeight = viewport.clientHeight;
  const fontSize = parseFloat(getComputedStyle($("overlay")).fontSize);
  submitting = true;
  setBusy(true);
  status("Starting video export…", "working");
  try {
    await api("video/export", {method:"POST", headers:{"Content-Type":"application/json"},
      body:JSON.stringify({token:nativeVideo.token, size:$("text-size").value,
                           position:$("caption-height").value, styles:wordStyles, look:$("overlay").dataset.look, preserve_encoding:preserveEncoding,
                           preview:previewWidth > 1 && previewHeight > 1 ? [previewWidth, previewHeight, fontSize] : null})});
  } catch (error) { fail(error); return; }
  finally { submitting = false; }
  await poll();
}
$("export-video").addEventListener("click", () => exportVideo(false));
$("export-original").addEventListener("click", () => exportVideo(true));
$("previous").addEventListener("click", () => select(Math.max(0, selected - 1)));
$("next").addEventListener("click", () => select(Math.min(cues.length - 1, selected + 1)));
$("play").addEventListener("click", () => {
  if (!video.paused) video.pause();
  else video.play().catch((error) => status(error.message, "error"));
});
video.addEventListener("play", () => { $("play").textContent = "Ⅱ"; $("play").ariaLabel = "Pause"; });
video.addEventListener("pause", () => { $("play").textContent = "▶"; $("play").ariaLabel = "Play"; });
video.addEventListener("timeupdate", () => { if (ready) position(video.currentTime); });
video.addEventListener("loadedmetadata", () => {
  ready = Boolean(video.videoWidth);
  $("play").disabled = !ready;
  video.hidden = !ready;
  $("empty-preview").hidden = ready;
  fitVideo();
  updateDuration();
  if (selected >= 0) jump(cues[selected].startTime);
  if (!running) {
    if (nativeVideo && !nativeVideo.tracks.length) status("This video has no audio track.", "error");
    else status(ready ? "Preview loaded." : "This file has no playable video track.");
  }
});
video.addEventListener("error", () => {
  ready = false;
  video.hidden = true;
  $("empty-preview").hidden = false;
  fitVideo();
  if (!running) {
    status(nativeVideo?.tracks.length
      ? "Preview unavailable in this codec. You can still generate captions from its audio."
      : "Preview unavailable. Try an H.264 MP4 export.", "error");
  }
});
seek.addEventListener("input", () => jump(Number(seek.value)));
$("track").addEventListener("click", (event) => {
  const box = $("track").getBoundingClientRect();
  jump(Math.max(0, Math.min(1, (event.clientX - box.left) / box.width)) * duration);
});
$("guides").addEventListener("change", (event) => {
  document.querySelector(".safe-area").hidden = !event.target.checked;
});
for (const button of document.querySelectorAll(".look")) {
  button.addEventListener("click", () => {
    for (const other of document.querySelectorAll(".look")) other.setAttribute("aria-pressed", String(other === button));
    $("overlay").dataset.look = button.dataset.look;
  });
}
$("text-size").addEventListener("input", (event) => {
  $("size-value").textContent = event.target.value + "%";
  $("overlay").style.setProperty("--caption-size", Number(event.target.value) / 100);
});
$("caption-height").addEventListener("input", (event) => {
  $("height-value").textContent = event.target.value + "%";
  $("overlay").style.setProperty("--caption-y", event.target.value + "%");
});
$("show-output").addEventListener("click", () => {
  api("show-output", {method: "POST"}).catch((error) => status(error.message, "error"));
});
$("close").addEventListener("click", async () => {
  if (saving || editing) { status("Save your caption edit before stopping the editor."); return; }
  try {
    const result = await api("close", {method: "POST"});
    stopped = true;
    setBusy(true);
    status(result.message + " You can close this tab.");
  } catch (error) {
    status(error.message, "error");
  }
});
const stage = $("stage");
stage.addEventListener("dragover", (event) => {
  event.preventDefault();
  document.body.classList.add("dragging");
});
stage.addEventListener("dragleave", (event) => {
  if (!stage.contains(event.relatedTarget)) document.body.classList.remove("dragging");
});
stage.addEventListener("drop", (event) => {
  event.preventDefault();
  document.body.classList.remove("dragging");
  const file = event.dataTransfer.files[0];
  if (!file) return;
  if (/\.wav$/i.test(file.name)) transcribe(file);
  else {
    setVideoSource(null);
    loadVideo(URL.createObjectURL(file));
  }
});
new ResizeObserver(fitVideo).observe(stage);
updateDuration();
$("model-choice").addEventListener("change", () => setBusy(running));
$("download-model").addEventListener("click", downloadSelectedModel);
setBusy(false);
refreshModels().catch(fail);
setInterval(() => { if (running && !submitting) void poll(); }, 650);
window.addEventListener("focus", () => { if (running && !submitting) void poll(); });
document.addEventListener("visibilitychange", () => {
  if (!document.hidden && running && !submitting) void poll();
});
void poll();
