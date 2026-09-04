import { initCompare, initMethodCompare } from "./viewer.js?v=ours-frame-20260903";

/* ── BibTeX copy ─────────────────────────────────────────── */
document.getElementById("copy-bib").addEventListener("click", async () => {
  const t = document.getElementById("bibtex").innerText;
  try {
    await navigator.clipboard.writeText(t);
    document.getElementById("copy-bib").textContent = "Copied";
  } catch {
    document.getElementById("copy-bib").textContent = "Select and copy";
  }
});

/* ── Video preview ───────────────────────────────────────── */
async function initVideoPreview() {
  const section    = document.getElementById("videos");
  const expandBtn  = document.getElementById("video-expand");
  const launchIcon = expandBtn?.querySelector(".video-launch-icon");
  const launchTitle= expandBtn?.querySelector(".video-launch-title");
  const launchSub  = expandBtn?.querySelector(".video-launch-sub");
  const collapseBtn= document.getElementById("video-collapse");
  const panel      = document.getElementById("video-panel");
  const select     = document.getElementById("video-select");
  const wrap       = document.getElementById("video-wrap");
  const floatEl    = document.getElementById("video-float");
  const floatBar   = document.getElementById("video-float-bar");
  const floatBody  = document.getElementById("video-float-body");
  const floatLabel = document.getElementById("video-float-label");
  const floatClose = document.getElementById("video-float-close");
  const floatResize= document.getElementById("video-float-resize");
  const playToggle = document.getElementById("video-play-toggle");
  const progress   = document.getElementById("video-progress");
  const timeOutput = document.getElementById("video-time");
  if (!section || !expandBtn || !panel || !wrap || !floatEl) return;

  /* Load manifest */
  let scenes = [];
  try {
    const r = await fetch("data/videos.json");
    if (!r.ok) throw new Error(r.status);
    scenes = await r.json();
  } catch { return; }

  const byUrl = new Map(scenes.map((s) => [s.url, s]));

  /* Populate select */
  const groups = new Map();
  for (const s of scenes) {
    const k = s.dataset || "Scenes";
    if (!groups.has(k)) groups.set(k, []);
    groups.get(k).push(s);
  }
  for (const [label, list] of groups) {
    const og = document.createElement("optgroup");
    og.label = label;
    for (const s of list) {
      const opt = document.createElement("option");
      opt.value = s.url; opt.textContent = s.label;
      og.appendChild(opt);
    }
    select.appendChild(og);
  }
  if (scenes.length) select.value = scenes[0].url;

  /* ── Create ONE video element; move it between wrap ↔ floatBody ── */
  const video = document.createElement("video");
  video.id = "seq-video";
  video.controls = true;
  video.setAttribute("playsinline", "");
  video.loop = true;
  video.muted = true;
  video.preload = "none";
  wrap.appendChild(video);

  /* Reliable in-page controls (native controls remain available as well). */
  const formatTime = (seconds) => {
    if (!Number.isFinite(seconds)) return "0:00";
    const whole = Math.max(0, Math.floor(seconds));
    return `${Math.floor(whole / 60)}:${String(whole % 60).padStart(2, "0")}`;
  };
  function syncVideoControls() {
    const duration = Number.isFinite(video.duration) ? video.duration : 0;
    const current = Number.isFinite(video.currentTime) ? video.currentTime : 0;
    if (progress) {
      progress.disabled = duration <= 0;
      progress.value = duration > 0 ? String(Math.round((current / duration) * 1000)) : "0";
    }
    if (timeOutput) {
      timeOutput.textContent = `${formatTime(current)} / ${formatTime(duration)}`;
    }
    if (playToggle) {
      playToggle.textContent = video.paused ? "▶ Play" : "❚❚ Pause";
      playToggle.setAttribute("aria-label", video.paused ? "Play video" : "Pause video");
    }
  }
  playToggle?.addEventListener("click", () => {
    if (video.paused) video.play().catch(() => {});
    else video.pause();
  });
  progress?.addEventListener("input", () => {
    if (!Number.isFinite(video.duration) || video.duration <= 0) return;
    video.currentTime = (Number(progress.value) / 1000) * video.duration;
    syncVideoControls();
  });
  video.addEventListener("loadedmetadata", syncVideoControls);
  video.addEventListener("durationchange", syncVideoControls);
  video.addEventListener("timeupdate", syncVideoControls);
  video.addEventListener("play", syncVideoControls);
  video.addEventListener("pause", syncVideoControls);
  video.addEventListener("ended", syncVideoControls);

  /* State */
  let expanded    = false;   // panel open
  let floating    = false;   // video in mini-player
  let dismissed   = false;   // user closed mini-player this session
  let currentSrc  = "";
  let positionCustomized = false;

  const label = () => byUrl.get(select.value)?.label || "Preview";

  function updateLaunchButton() {
    expandBtn.setAttribute("aria-expanded", String(expanded));
    expandBtn.classList.toggle("is-open", expanded);
    if (launchIcon) launchIcon.textContent = expanded ? "▾" : "▶";
    if (launchTitle) {
      launchTitle.textContent = expanded
        ? "Hide input sequence previews"
        : "Watch input sequence previews";
    }
    if (launchSub) {
      launchSub.textContent = expanded
        ? "Click again to close · playback position is reset when closed"
        : "13 sequences · click to open or close · seek and pause with the video controls";
    }
  }

  /* Load + play */
  function loadSrc(url, play = true) {
    if (currentSrc !== url) {
      video.src = url;
      video.load();
      currentSrc = url;
    }
    if (play) video.play().catch(() => {});
    if (floatLabel) floatLabel.textContent = `Drag to move · ${label()}`;
  }

  /* ── Dock helpers ── */
  function showPlaceholder() {
    // Show text hint in wrap when video is floating
    if (!wrap.querySelector(".video-placeholder")) {
      const p = document.createElement("div");
      p.className = "video-placeholder";
      p.textContent = "Playing in mini player ↘";
      wrap.appendChild(p);
    }
  }
  function hidePlaceholder() {
    wrap.querySelector(".video-placeholder")?.remove();
  }

  function dockInline(play = false) {
    if (wrap.contains(video)) {
      floatEl.classList.remove("is-visible");
      floating = false;
      return;
    }
    hidePlaceholder();
    wrap.appendChild(video);
    floatEl.classList.remove("is-visible");
    floating = false;
    if (play) video.play().catch(() => {});
  }

  function dockFloat() {
    if (!expanded || dismissed) return;
    if (floatBody.contains(video) && floatEl.classList.contains("is-visible")) return;
    showPlaceholder();
    floatBody.appendChild(video);
    floatEl.classList.add("is-visible");
    if (!positionCustomized) {
      // Use the CSS bottom-right default until the user drags the player.
      floatEl.style.left = "";
      floatEl.style.top = "";
      floatEl.style.right = "";
      floatEl.style.bottom = "";
    }
    floating = true;
    if (floatLabel) floatLabel.textContent = `Drag to move · ${label()}`;
    video.play().catch(() => {});
  }

  /* ── Open / close panel ── */
  function expand() {
    expanded  = true;
    dismissed = false;
    panel.hidden = false;
    updateLaunchButton();
    loadSrc(select.value, true);
    requestAnimationFrame(syncFloatingState);
  }

  function collapse() {
    video.pause();
    video.removeAttribute("src"); video.load();
    currentSrc = "";
    dockInline();
    floatEl.classList.remove("is-visible");
    panel.hidden  = true;
    expanded  = false;
    floating  = false;
    dismissed = false;
    positionCustomized = false;
    updateLaunchButton();
  }

  expandBtn.addEventListener("click", () => {
    if (expanded) collapse();
    else expand();
  });
  collapseBtn?.addEventListener("click", collapse);
  floatClose?.addEventListener("click", () => {
    dismissed = true;
    video.pause();
    dockInline();
    floatEl.classList.remove("is-visible");
    floating = false;
  });
  select.addEventListener("change", () => {
    if (!expanded) return;
    loadSrc(select.value, true);
  });

  /*
   * The wrap stays in the document as a stable placeholder while its video is
   * floating. Only float after the complete original video area has passed
   * above the sticky-header line. A generic IntersectionObserver cannot tell
   * "scrolled past above" from "not reached below", which caused premature
   * floating on both desktop and mobile.
   */
  let scrollFrame = 0;
  function syncFloatingState() {
    scrollFrame = 0;
    if (!expanded) return;
    const topBoundary = 64;
    const rect = wrap.getBoundingClientRect();
    const passedAbove = rect.bottom <= topBoundary;
    if (passedAbove && !dismissed) {
      dockFloat();
    } else if (!passedAbove && floating) {
      dockInline(true);
    }
  }
  function scheduleFloatingSync() {
    if (!scrollFrame) scrollFrame = requestAnimationFrame(syncFloatingState);
  }
  window.addEventListener("scroll", scheduleFloatingSync, { passive: true });
  window.addEventListener("resize", scheduleFloatingSync, { passive: true });

  /* ── Drag to move ── */
  let drag = null;

  floatBar?.addEventListener("pointerdown", (e) => {
    if (!floating || e.button !== 0 || e.target.closest("button")) return;
    // Switch from bottom/right anchor to top/left so we can set position freely
    const r = floatEl.getBoundingClientRect();
    floatEl.style.right  = "auto";
    floatEl.style.bottom = "auto";
    floatEl.style.left = `${r.left}px`;
    floatEl.style.top  = `${r.top}px`;
    drag = { kind: "move", id: e.pointerId, ox: e.clientX - r.left, oy: e.clientY - r.top };
    positionCustomized = true;
    floatEl.classList.add("is-dragging");
    floatBar.setPointerCapture(e.pointerId);
    e.preventDefault();
  });

  floatResize?.addEventListener("pointerdown", (e) => {
    if (!floating || e.button !== 0) return;
    e.stopPropagation();
    const r = floatEl.getBoundingClientRect();
    floatEl.style.right = "auto";
    floatEl.style.bottom = "auto";
    floatEl.style.left = `${r.left}px`;
    floatEl.style.top = `${r.top}px`;
    drag = { kind: "resize", id: e.pointerId, startX: e.clientX, startW: r.width };
    positionCustomized = true;
    floatEl.classList.add("is-dragging");
    floatResize.setPointerCapture(e.pointerId);
    e.preventDefault();
  });

  window.addEventListener("pointermove", (e) => {
    if (!drag || e.pointerId !== drag.id) return;
    if (drag.kind === "move") {
      let left = e.clientX - drag.ox;
      let top  = e.clientY - drag.oy;
      const m = 4;
      left = Math.min(Math.max(m, left), window.innerWidth  - floatEl.offsetWidth  - m);
      top  = Math.min(Math.max(m, top),  window.innerHeight - floatEl.offsetHeight - m);
      floatEl.style.left = `${left}px`;
      floatEl.style.top  = `${top}px`;
    } else {
      const w = Math.min(
        Math.max(160, drag.startW + e.clientX - drag.startX),
        Math.min(window.innerWidth * 0.9, 420)
      );
      floatEl.style.width = `${w}px`;
    }
  });
  function finishDrag(e) {
    if (drag?.id !== e.pointerId) return;
    drag = null;
    floatEl.classList.remove("is-dragging");
  }
  window.addEventListener("pointerup", finishDrag);
  window.addEventListener("pointercancel", finishDrag);
}

initVideoPreview();
initCompare();
initMethodCompare();
