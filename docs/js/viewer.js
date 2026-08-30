import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { PLYLoader } from "three/addons/loaders/PLYLoader.js";

function parsePnts(buf) {
  const dv = new DataView(buf);
  const magic = String.fromCharCode(dv.getUint8(0), dv.getUint8(1), dv.getUint8(2), dv.getUint8(3));
  if (magic !== "ECD1") throw new Error("Bad point format");
  const n = dv.getUint32(4, true);
  const min = [dv.getFloat32(8, true), dv.getFloat32(12, true), dv.getFloat32(16, true)];
  const max = [dv.getFloat32(20, true), dv.getFloat32(24, true), dv.getFloat32(28, true)];
  const span = [max[0] - min[0], max[1] - min[1], max[2] - min[2]];
  const pos = new Float32Array(n * 3);
  const col = new Float32Array(n * 3);
  let o = 32;
  for (let i = 0; i < n; i++) {
    const qx = dv.getUint16(o, true);
    const qy = dv.getUint16(o + 2, true);
    const qz = dv.getUint16(o + 4, true);
    const rg = dv.getUint16(o + 6, true);
    const b = dv.getUint16(o + 8, true) & 0xff;
    o += 10;
    pos[i * 3] = min[0] + (qx / 65535) * span[0];
    pos[i * 3 + 1] = min[1] + (qy / 65535) * span[1];
    pos[i * 3 + 2] = min[2] + (qz / 65535) * span[2];
    col[i * 3] = (rg & 0xff) / 255;
    col[i * 3 + 1] = ((rg >> 8) & 0xff) / 255;
    col[i * 3 + 2] = b / 255;
  }
  return { pos, col };
}

function makePoints(pos, col) {
  const g = new THREE.BufferGeometry();
  g.setAttribute("position", new THREE.BufferAttribute(pos, 3));
  g.setAttribute("color", new THREE.BufferAttribute(col, 3));
  g.computeBoundingSphere();
  const m = new THREE.PointsMaterial({
    size: 0.012,
    vertexColors: true,
    sizeAttenuation: true,
  });
  return new THREE.Points(g, m);
}

function addLights(scene) {
  scene.add(new THREE.AmbientLight(0xffffff, 0.85));
  const d = new THREE.DirectionalLight(0xffffff, 0.9);
  d.position.set(0.5, 1, 0.7);
  scene.add(d);
  const d2 = new THREE.DirectionalLight(0xfff2e8, 0.35);
  d2.position.set(-0.6, -0.2, -0.4);
  scene.add(d2);
}

function clearGeom(scene) {
  [...scene.children].forEach((c) => {
    if (c.isLight) return;
    scene.remove(c);
    if (c.geometry) c.geometry.dispose();
    if (c.material) {
      if (Array.isArray(c.material)) c.material.forEach((m) => m.dispose());
      else c.material.dispose();
    }
  });
}

async function loadPoints(url) {
  const res = await fetch(url);
  if (!res.ok) throw new Error("Failed to load points");
  return parsePnts(await res.arrayBuffer());
}

async function loadGt(url) {
  const loader = new PLYLoader();
  const geo = await loader.loadAsync(url);
  geo.computeVertexNormals();
  const mat = new THREE.MeshStandardMaterial({
    color: 0xe0a894,
    roughness: 0.5,
    metalness: 0.0,
    side: THREE.DoubleSide,
  });
  return new THREE.Mesh(geo, mat);
}

function fillSceneSelect(select, scenes) {
  const groups = new Map();
  for (const s of scenes) {
    const key = s.dataset || "Scenes";
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(s);
  }
  select.innerHTML = "";
  for (const [label, list] of groups) {
    const og = document.createElement("optgroup");
    og.label = label;
    for (const s of list) {
      const opt = document.createElement("option");
      opt.value = s.id;
      opt.textContent = s.label;
      og.appendChild(opt);
    }
    select.appendChild(og);
  }
}

/**
 * @param {object} cfg
 * @param {HTMLCanvasElement} cfg.canvas
 * @param {HTMLElement} cfg.wrap
 * @param {HTMLElement} cfg.loadingEl
 * @param {HTMLElement} cfg.statusEl
 * @param {HTMLSelectElement} cfg.sceneSelect
 * @param {HTMLElement|null} [cfg.splitEl]
 * @param {HTMLElement|null} [cfg.badgeL]
 * @param {HTMLElement|null} [cfg.badgeR]
 * @param {ParentNode} [cfg.modeRoot]
 * @param {HTMLElement} cfg.resetBtn
 * @param {HTMLElement} cfg.spinBtn
 * @param {boolean} cfg.allowCompare
 * @param {string} cfg.manifestUrl
 */
function createViewer(cfg) {
  const {
    canvas,
    wrap,
    loadingEl,
    statusEl,
    sceneSelect,
    splitEl = null,
    badgeL = null,
    badgeR = null,
    modeRoot = document,
    resetBtn,
    spinBtn,
    allowCompare,
    manifestUrl,
  } = cfg;

  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true });
  renderer.setClearColor(0x111111, 1);
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.setScissorTest(false);

  const camera = new THREE.PerspectiveCamera(50, 1, 0.01, 20);
  const controls = new OrbitControls(camera, canvas);
  controls.enableDamping = true;
  controls.rotateSpeed = 0.75;
  controls.touches = { ONE: THREE.TOUCH.ROTATE, TWO: THREE.TOUCH.DOLLY_PAN };

  const sceneOurs = new THREE.Scene();
  const sceneGt = new THREE.Scene();
  const sceneOverlay = new THREE.Scene();
  [sceneOurs, sceneGt, sceneOverlay].forEach(addLights);

  let pointsObj = null;
  let gtObj = null;
  let overlayPoints = null;
  let overlayGt = null;
  let mode = allowCompare ? "compare" : "browse";
  let split = 0.5;
  let dragging = false;
  let autoRotate = false;
  let scenes = [];
  let current = null;

  function hasGt(sc) {
    return Boolean(sc?.gt?.url);
  }

  function isMobile() {
    return wrap.clientWidth < 700;
  }

  function sizeCanvas() {
    const cssW = Math.max(1, wrap.clientWidth);
    const cssH = Math.max(1, wrap.clientHeight);
    const pr = Math.min(window.devicePixelRatio || 1, 2);
    renderer.setPixelRatio(pr);
    renderer.setSize(cssW, cssH, false);
    camera.aspect = cssW / cssH;
    camera.updateProjectionMatrix();
    return { w: cssW, h: cssH };
  }

  function setLoading(on, msg) {
    loadingEl.classList.toggle("hidden", !on);
    if (msg) loadingEl.textContent = msg;
  }

  function fitCamera() {
    const box = new THREE.Box3();
    if (pointsObj) box.expandByObject(pointsObj);
    if (gtObj) box.expandByObject(gtObj);
    if (box.isEmpty()) return;
    const sphere = new THREE.Sphere();
    box.getBoundingSphere(sphere);
    const fov = THREE.MathUtils.degToRad(camera.fov * 0.5);
    const dist = (sphere.radius / Math.max(Math.tan(fov), 1e-4)) * 1.25;
    const dir = new THREE.Vector3(0.25, 0.18, 1).normalize();
    camera.near = Math.max(dist / 200, 0.001);
    camera.far = dist * 20;
    camera.updateProjectionMatrix();
    camera.position.copy(sphere.center).addScaledVector(dir, dist);
    controls.target.copy(sphere.center);
    controls.minDistance = sphere.radius * 0.15;
    controls.maxDistance = dist * 4;
    controls.update();
  }

  function updateCompareControls() {
    const ok = allowCompare && hasGt(current);
    modeRoot.querySelectorAll("[data-mode]").forEach((b) => {
      b.hidden = !ok;
      if (!ok) b.classList.remove("active");
    });
    if (!ok && mode !== "browse") mode = "browse";
    if (ok) {
      modeRoot.querySelectorAll("[data-mode]").forEach((b) => {
        b.classList.toggle("active", b.dataset.mode === mode);
      });
    }
  }

  function updateSplitUi() {
    const show = allowCompare && mode === "compare" && hasGt(current);
    if (splitEl) splitEl.hidden = !show;
    if (badgeL) badgeL.hidden = !show;
    if (badgeR) badgeR.hidden = !show;
    if (show && splitEl) splitEl.style.left = `${split * 100}%`;
  }

  function setMode(next) {
    if (!allowCompare || !hasGt(current)) {
      mode = "browse";
    } else {
      mode = next;
    }
    updateCompareControls();
    updateSplitUi();
  }

  async function loadScene(id) {
    current = scenes.find((s) => s.id === id);
    if (!current) return;
    setLoading(true, "Loading reconstruction…");
    const lod = isMobile() ? "mobile" : "desktop";
    const pinfo = current.points[lod] || current.points.desktop;
    try {
      const { pos, col } = await loadPoints(pinfo.url);
      clearGeom(sceneOurs);
      clearGeom(sceneGt);
      clearGeom(sceneOverlay);
      pointsObj = makePoints(pos, col);
      overlayPoints = makePoints(pos, col);
      sceneOurs.add(pointsObj);
      sceneOverlay.add(overlayPoints);
      gtObj = null;
      overlayGt = null;
      if (hasGt(current)) {
        setLoading(true, "Loading ground truth…");
        const gt = await loadGt(current.gt.url);
        gtObj = gt;
        overlayGt = gt.clone();
        overlayGt.material = overlayGt.material.clone();
        overlayGt.material.transparent = true;
        overlayGt.material.opacity = 0.38;
        overlayGt.material.depthWrite = false;
        sceneGt.add(gtObj);
        sceneOverlay.add(overlayGt);
        if (allowCompare && mode === "browse") mode = "compare";
      } else {
        mode = "browse";
      }
      sizeCanvas();
      fitCamera();
      const extra = allowCompare && !hasGt(current) ? " · no GT" : "";
      statusEl.textContent = `${current.label} · ${(pinfo.count / 1000).toFixed(0)}k points${extra}`;
      updateCompareControls();
      updateSplitUi();
    } catch (e) {
      console.error(e);
      statusEl.textContent = "Could not load this scene.";
    }
    setLoading(false);
  }

  function render() {
    requestAnimationFrame(render);
    controls.autoRotate = autoRotate;
    controls.update();
    const { w, h } = sizeCanvas();
    if (allowCompare && mode === "overlay" && hasGt(current)) {
      renderer.setScissorTest(false);
      renderer.setViewport(0, 0, w, h);
      renderer.render(sceneOverlay, camera);
    } else if (allowCompare && mode === "compare" && hasGt(current)) {
      const x = split * w;
      renderer.setScissorTest(true);
      renderer.setViewport(0, 0, w, h);
      renderer.setScissor(0, 0, Math.max(x, 0.5), h);
      renderer.render(sceneOurs, camera);
      renderer.setScissor(x, 0, Math.max(w - x, 0.5), h);
      renderer.render(sceneGt, camera);
    } else {
      renderer.setScissorTest(false);
      renderer.setViewport(0, 0, w, h);
      renderer.render(sceneOurs, camera);
    }
  }

  if (splitEl) {
    splitEl.addEventListener("pointerdown", (e) => {
      dragging = true;
      splitEl.setPointerCapture(e.pointerId);
      controls.enabled = false;
      e.preventDefault();
    });
    window.addEventListener("pointermove", (e) => {
      if (!dragging) return;
      const r = canvas.getBoundingClientRect();
      const cx = e.clientX ?? e.touches?.[0]?.clientX ?? 0;
      split = Math.min(0.9, Math.max(0.1, (cx - r.left) / Math.max(r.width, 1)));
      splitEl.style.left = `${split * 100}%`;
    });
    window.addEventListener("pointerup", () => {
      dragging = false;
      controls.enabled = true;
    });
  }

  window.addEventListener("resize", sizeCanvas);
  if (typeof ResizeObserver !== "undefined") {
    new ResizeObserver(() => sizeCanvas()).observe(wrap);
  }
  resetBtn.addEventListener("click", fitCamera);
  spinBtn.addEventListener("click", (e) => {
    autoRotate = !autoRotate;
    e.currentTarget.classList.toggle("active", autoRotate);
  });
  if (allowCompare) {
    modeRoot.querySelectorAll("[data-mode]").forEach((b) => {
      b.addEventListener("click", () => setMode(b.dataset.mode));
    });
  }
  sceneSelect.addEventListener("change", () => loadScene(sceneSelect.value));

  async function start() {
    const res = await fetch(manifestUrl);
    scenes = await res.json();
    fillSceneSelect(sceneSelect, scenes);
    if (location.hash === "#poster" && allowCompare) {
      document.body.classList.add("poster");
      autoRotate = true;
      spinBtn.classList.add("active");
    }
    setMode(allowCompare ? "compare" : "browse");
    sceneSelect.value = scenes[0].id;
    await loadScene(scenes[0].id);
    render();
  }

  return start();
}

export function initCompare() {
  return createViewer({
    canvas: document.getElementById("view"),
    wrap: document.getElementById("viewer-wrap"),
    loadingEl: document.getElementById("loading"),
    statusEl: document.getElementById("status"),
    sceneSelect: document.getElementById("scene-select"),
    splitEl: document.getElementById("split"),
    badgeL: document.getElementById("badge-l"),
    badgeR: document.getElementById("badge-r"),
    modeRoot: document.getElementById("interactive"),
    resetBtn: document.getElementById("btn-reset"),
    spinBtn: document.getElementById("btn-spin"),
    allowCompare: true,
    manifestUrl: "data/scenes.json",
  });
}

export function initEndomapper() {
  return createViewer({
    canvas: document.getElementById("em-view"),
    wrap: document.getElementById("em-viewer-wrap"),
    loadingEl: document.getElementById("em-loading"),
    statusEl: document.getElementById("em-status"),
    sceneSelect: document.getElementById("em-scene-select"),
    resetBtn: document.getElementById("em-btn-reset"),
    spinBtn: document.getElementById("em-btn-spin"),
    allowCompare: false,
    manifestUrl: "data/endomapper.json",
  });
}
