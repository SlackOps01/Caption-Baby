(() => {
  const root = document.body;
  const workspace = document.querySelector(".workspace");
  const viewer = document.querySelector(".viewer");
  const transcript = document.querySelector(".transcript");
  const inspector = document.querySelector(".inspector");
  const model = document.querySelector(".model-toolbar");
  const rail = document.createElement("nav");
  rail.className = "rail";
  rail.setAttribute("aria-label", "Workspace");
  const icon = (paths) => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${paths}</svg>`;
  const captionsIcon = icon('<rect x="3" y="5" width="18" height="14" rx="2"/><path d="M7 10h4m2 0h4M7 14h3m2 0h5"/>');
  const settingsIcon = icon('<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .34 1.88l.06.06-1.86 3.22-.08-.02a1.7 1.7 0 0 0-1.8.63l-.05.07h-3.72l-.04-.07a1.7 1.7 0 0 0-1.8-.63l-.09.02-1.86-3.22.06-.06A1.7 1.7 0 0 0 8.9 15l-.02-.08-1.86-1.07v-3.7L8.9 9.08l.02-.08a1.7 1.7 0 0 0-.34-1.88l-.06-.06 1.86-3.22.08.02a1.7 1.7 0 0 0 1.8-.63l.05-.07h3.72l.04.07a1.7 1.7 0 0 0 1.8.63l.09-.02 1.86 3.22-.06.06A1.7 1.7 0 0 0 19.4 9l.02.08 1.86 1.07v3.7l-1.86 1.07z" transform="translate(-2.15 0)"/>');
  rail.innerHTML = `<button class="rail-current" aria-current="page" title="Captions"><span class="rail-icon">${captionsIcon}</span><span>Captions</span></button><button class="rail-settings" title="Model settings" aria-expanded="false"><span class="rail-icon">${settingsIcon}</span><span>Models</span></button>`;
  root.insertBefore(rail, workspace);
  rail.querySelector(".rail-settings").addEventListener("click", () => {
    model.hidden = !model.hidden;
    rail.querySelector(".rail-settings").setAttribute("aria-expanded", String(!model.hidden));
    if (!model.hidden) document.getElementById("model-choice").focus();
  });
  model.hidden = true;

  document.getElementById("empty-open-video").addEventListener("click", () => document.getElementById("open-video").click());
  document.getElementById("empty-open-wav").addEventListener("click", () => document.getElementById("open-wav").click());
  const expand = document.getElementById("expand-viewer");
  expand.addEventListener("click", async () => {
    try {
      if (document.fullscreenElement === viewer) await document.exitFullscreen();
      else await viewer.requestFullscreen();
    } catch (_) {
      document.getElementById("status").textContent = "Preview expansion is unavailable in this window.";
    }
  });
  document.addEventListener("fullscreenchange", () => {
    const expanded = document.fullscreenElement === viewer;
    expand.textContent = expanded ? "Exit full screen" : "Expand";
    expand.setAttribute("aria-label", expanded ? "Exit full screen preview" : "Expand preview");
  });
  const timelineToggle = document.getElementById("timeline-toggle");
  timelineToggle.addEventListener("click", () => {
    const content = document.getElementById("timeline-content");
    content.hidden = !content.hidden;
    timelineToggle.setAttribute("aria-expanded", String(!content.hidden));
    document.querySelector(".timeline").classList.toggle("expanded", !content.hidden);
  });
  const inspectorBody = document.querySelector(".inspector-body");
  const tabs = document.createElement("div");
  tabs.className = "inspector-tabs";
  tabs.setAttribute("role", "tablist");
  const captionTab = document.createElement("button");
  const videoTab = document.createElement("button");
  for (const [button, label] of [[captionTab,"Caption"],[videoTab,"Video"]]) {
    button.textContent = label;
    button.setAttribute("role", "tab");
    tabs.append(button);
  }
  inspectorBody.prepend(tabs);
  const captionElements = [
    document.querySelector('label[for="cue-text"]'),
    document.getElementById("cue-text"), document.getElementById("save"),
    document.getElementById("uppercase"), document.getElementById("lowercase"),
  ];
  const wordTitle = document.getElementById("word-list").previousElementSibling;
  const wordElements = [wordTitle, document.getElementById("word-list"),
    document.querySelector('label[for="word-color"]'), document.querySelector('label[for="word-size"]')];
  const lookTitle = document.querySelector(".looks").previousElementSibling;
  const videoElements = [lookTitle, document.querySelector(".looks"),
    document.querySelector('label[for="text-size"]'), document.getElementById("text-size"),
    document.querySelector('label[for="caption-height"]'), document.getElementById("caption-height"),
    document.querySelector(".export-note")];
  inspectorBody.querySelectorAll(".divider").forEach(element => element.remove());
  const captionPanel = document.createElement("div");
  const videoPanel = document.createElement("div");
  captionPanel.className = "caption-panel";
  videoPanel.className = "video-panel";
  captionElements.forEach(element => captionPanel.append(element));
  const wordSection = document.createElement("details");
  wordSection.className = "inspector-section";
  wordSection.open = true;
  const wordSummary = document.createElement("summary");
  wordSummary.textContent = "Words";
  wordSection.append(wordSummary);
  wordElements.slice(1).forEach(element => wordSection.append(element));
  wordTitle.remove();
  captionPanel.append(wordSection);
  const timingSection = document.createElement("details");
  timingSection.className = "inspector-section";
  const timingSummary = document.createElement("summary");
  timingSummary.textContent = "Timing";
  timingSection.append(timingSummary, document.getElementById("cue-time"));
  captionPanel.append(timingSection);
  const videoSection = document.createElement("details");
  videoSection.className = "inspector-section";
  videoSection.open = true;
  const videoSummary = document.createElement("summary");
  videoSummary.textContent = "Appearance and position";
  videoSection.append(videoSummary);
  videoElements.slice(1).forEach(element => videoSection.append(element));
  lookTitle.remove();
  videoPanel.append(videoSection);
  const inspectorEmpty = document.createElement("div");
  inspectorEmpty.className = "inspector-empty";
  inspectorEmpty.innerHTML = "<strong>Select a caption</strong><p>Choose a transcript row to edit its text and words.</p>";
  inspectorBody.append(inspectorEmpty, captionPanel, videoPanel);
  const textEditor = document.getElementById("cue-text");
  function updateInspector() {
    const empty = textEditor.disabled && !document.getElementById("cue-list").children.length;
    inspectorEmpty.hidden = !empty || videoTab.getAttribute("aria-selected") === "true";
    captionPanel.hidden = empty || videoTab.getAttribute("aria-selected") === "true";
  }
  new MutationObserver(updateInspector).observe(document.getElementById("cue-list"), {childList:true});
  function activateTab(caption) {
    captionPanel.hidden = !caption;
    videoPanel.hidden = caption;
    captionTab.setAttribute("aria-selected", String(caption));
    videoTab.setAttribute("aria-selected", String(!caption));
    updateInspector();
  }
  captionTab.addEventListener("click", () => activateTab(true));
  videoTab.addEventListener("click", () => activateTab(false));
  activateTab(true);

  const sizeSelect = document.getElementById("word-size");
  const sizes = document.createElement("div");
  sizes.className = "word-size-segments";
  sizes.setAttribute("role", "group");
  sizes.setAttribute("aria-label", "Word size");
  for (const [value, label] of [["80","Small"],["100","Normal"],["125","Large"]]) {
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = label;
    button.dataset.value = value;
    button.addEventListener("click", () => {
      if (sizeSelect.disabled) return;
      sizeSelect.value = value;
      sizeSelect.dispatchEvent(new Event("input", {bubbles:true}));
      updateSize();
    });
    sizes.append(button);
  }
  sizeSelect.insertAdjacentElement("afterend", sizes);
  function updateSize() {
    for (const button of sizes.children) {
      button.disabled = sizeSelect.disabled;
      button.setAttribute("aria-pressed", String(button.dataset.value === sizeSelect.value));
    }
  }
  new MutationObserver(updateSize).observe(sizeSelect, {attributes:true, attributeFilter:["disabled"]});
  document.getElementById("word-list").addEventListener("click", () => setTimeout(updateSize));
  updateSize();

  const colorInput = document.getElementById("word-color");
  const swatches = document.createElement("div");
  swatches.className = "swatches";
  swatches.setAttribute("role", "group");
  swatches.setAttribute("aria-label", "Word color");
  for (const color of ["#ffffff","#ffd740","#3d91f5","#f1574e","#36c57c"]) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "swatch";
    button.style.backgroundColor = color;
    button.dataset.color = color;
    button.setAttribute("aria-label", color);
    button.addEventListener("click", () => {
      if (colorInput.disabled) return;
      colorInput.value = color;
      colorInput.dispatchEvent(new Event("input", {bubbles:true}));
      updateSwatches();
    });
    swatches.append(button);
  }
  colorInput.insertAdjacentElement("beforebegin", swatches);
  function updateSwatches() {
    for (const button of swatches.children) {
      button.disabled = colorInput.disabled;
      button.setAttribute("aria-pressed", String(button.dataset.color === colorInput.value));
    }
  }
  colorInput.addEventListener("input", updateSwatches);
  document.getElementById("word-list").addEventListener("click", () => setTimeout(updateSwatches));
  new MutationObserver(updateSwatches).observe(colorInput, {attributes:true, attributeFilter:["disabled"]});
  updateSwatches();

  for (const element of [viewer, transcript]) {
    const handle = document.createElement("div");
    handle.className = "resize-handle";
    handle.setAttribute("role", "separator");
    handle.setAttribute("aria-orientation", "vertical");
    handle.setAttribute("aria-label", element === viewer ? "Resize viewer" : "Resize transcript");
    handle.tabIndex = 0;
    element.append(handle);
    function adjust(delta) {
      const children = [viewer, transcript, inspector];
      const widths = children.map(child => child.getBoundingClientRect().width);
      const index = children.indexOf(element);
      const allowed = Math.min(widths[index + 1] - 240, Math.max(240 - widths[index], delta));
      widths[index] += allowed;
      widths[index + 1] -= allowed;
      workspace.style.setProperty("--columns", widths.map(width => width + "px").join(" "));
    }
    handle.addEventListener("pointerdown", event => {
      event.preventDefault();
      handle.setPointerCapture(event.pointerId);
      let last = event.clientX;
      const move = next => { adjust(next.clientX - last); last = next.clientX; };
      const up = () => { handle.removeEventListener("pointermove", move); handle.removeEventListener("pointerup", up); };
      handle.addEventListener("pointermove", move);
      handle.addEventListener("pointerup", up);
    });
    handle.addEventListener("keydown", event => {
      if (event.key === "ArrowLeft" || event.key === "ArrowRight") {
        event.preventDefault();
        adjust(event.key === "ArrowLeft" ? -10 : 10);
      }
    });
  }
})();
