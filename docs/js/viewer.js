import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";

const canvas = document.getElementById("view");
const loadingEl = document.getElementById("loading");
const splitEl = document.getElementById("split");
const statusEl = document.getElementById("status");
const sceneSelect = document.getElementById("scene-select");

const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: false });
renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
renderer.setClearColor(0x111111, 1);
renderer.outputColorSpace = THREE.SRGBColorSpace;

const camera = new THREE.PerspectiveCamera(55, 1, 0.01, 5000);
const controls = new OrbitControls(camera, canvas);
controls.enableDamping = true;
controls.rotateSpeed = 0.7;
controls.touches = { ONE: THREE.TOUCH.ROTATE, TWO: THREE.TOUCH.DOLLY_PAN };

const sceneOurs = new THREE.Scene();
const sceneGt = new THREE.Scene();
const sceneOverlay = new THREE.Scene();
for (const s of [sceneOurs, sceneGt, sceneOverlay]) {
  s.add(new THREE.AmbientLight(0xffffff, 0.7));
  const d = new THREE.DirectionalLight(0xffffff, 0.85);
  d.position.set(0.4, 1, 0.6);
  s.add(d);
}

let pointsObj = null;
let gtObj = null;
let overlayPoints = null;
let overlayGt = null;
let mode = "browse";
let split = 0.5;
let dragging = false;
let autoRotate = false;
let scenes = [];
let current = null;

function isMobile() {
  return window.matchMedia("(max-width: 700px)").matches || navigator.maxTouchPoints > 1 && innerWidth < 1100;
}

function resize() {
  const w = canvas.clientWidth || canvas.parentElement.clientWidth;
  const h = canvas.clientHeight || 480;
  renderer.setSize(w, h, false);
  camera.aspect = w / Math.max(h, 1);
  camera.updateProjectionMatrix();
}
window.addEventListener("resize", resize);

function setLoading(on, msg) {
  loadingEl.classList.toggle("hidden", !on);
  if (msg) loadingEl.textContent = msg;
}

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
  return { pos, col, min, max };
}

function makePoints(pos, col) {
  const g = new THREE.BufferGeometry();
  g.setAttribute("position", new THREE.BufferAttribute(pos, 3));
  g.setAttribute("color", new THREE.BufferAttribute(col, 3));
  g.computeBoundingSphere();
  const r = g.boundingSphere ? g.boundingSphere.radius : 1;
  const m = new THREE.PointsMaterial({
    size: Math.max(r * 0.0035, 0.02),
    vertexColors: true,
    sizeAttenuation: true,
  });
  return new THREE.Points(g, m);
}

function fitCamera(obj) {
  const box = new THREE.Box3().setFromObject(obj);
  const size = box.getSize(new THREE.Vector3());
  const center = box.getCenter(new THREE.Vector3());
  const r = Math.max(size.x, size.y, size.z, 0.01);
  camera.near = r / 400;
  camera.far = r * 40;
  camera.updateProjectionMatrix();
  camera.position.copy(center).add(new THREE.Vector3(0.15 * r, 0.12 * r, 0.9 * r));
  controls.target.copy(center);
  controls.minDistance = r * 0.05;
  controls.maxDistance = r * 8;
  controls.update();
}

function clearGroup(scene) {
  [...scene.children].forEach((c) => {
    if (c.isLight) return;
    scene.remove(c);
    if (c.geometry) c.geometry.dispose();
    if (c.material) c.material.dispose();
  });
}

async function loadPoints(url) {
  const res = await fetch(url);
  if (!res.ok) throw new Error("Failed to load points");
  return parsePnts(await res.arrayBuffer());
}

async function loadGt(url) {
  const loader = new GLTFLoader();
  const gltf = await loader.loadAsync(url);
  gltf.scene.traverse((o) => {
    if (o.isMesh) {
      o.material = new THREE.MeshStandardMaterial({
        color: 0xd4a090,
        roughness: 0.55,
        metalness: 0.02,
        transparent: true,
        opacity: 0.92,
        side: THREE.DoubleSide,
      });
    }
  });
  return gltf.scene;
}

export async function loadScene(id) {
  current = scenes.find((s) => s.id === id);
  if (!current) return;
  setLoading(true, "Loading reconstruction…");
  const lod = isMobile() ? "mobile" : "desktop";
  const pinfo = current.points[lod] || current.points.desktop;
  try {
    const { pos, col } = await loadPoints(pinfo.url);
    clearGroup(sceneOurs);
    clearGroup(sceneGt);
    clearGroup(sceneOverlay);
    pointsObj = makePoints(pos, col);
    overlayPoints = makePoints(pos, col);
    sceneOurs.add(pointsObj);
    sceneOverlay.add(overlayPoints);
    gtObj = null;
    overlayGt = null;
    if (current.gt && (mode === "compare" || mode === "overlay")) {
      setLoading(true, "Loading ground truth…");
      const gt = await loadGt(current.gt.url);
      gtObj = gt;
      overlayGt = gt.clone(true);
      overlayGt.traverse((o) => {
        if (o.isMesh) {
          o.material = o.material.clone();
          o.material.opacity = 0.35;
          o.material.transparent = true;
        }
      });
      sceneGt.add(gtObj);
      sceneOverlay.add(overlayGt);
    }
    fitCamera(pointsObj);
    statusEl.textContent = `${current.label} · ${(pinfo.count / 1000).toFixed(0)}k points` +
      (current.gt && mode !== "browse" ? " · GT mesh (dataset, not our output)" : "");
    updateSplitUi();
  } catch (e) {
    console.error(e);
    statusEl.textContent = "Could not load this scene on this device.";
  }
  setLoading(false);
}

function updateSplitUi() {
  const show = mode === "compare" && gtObj;
  splitEl.style.display = show ? "block" : "none";
  document.getElementById("badge-l").style.display = show ? "block" : "none";
  document.getElementById("badge-r").style.display = show ? "block" : "none";
  if (show) splitEl.style.left = `${split * 100}%`;
}

export function setMode(next) {
  mode = next;
  document.querySelectorAll("[data-mode]").forEach((b) => b.classList.toggle("active", b.dataset.mode === mode));
  if (current) loadScene(current.id);
}

function render() {
  requestAnimationFrame(render);
  if (autoRotate) controls.autoRotate = true;
  else controls.autoRotate = false;
  controls.update();
  resize();
  const w = canvas.width;
  const h = canvas.height;
  renderer.setViewport(0, 0, w, h);
  if (mode === "overlay") {
    renderer.setScissorTest(false);
    renderer.render(sceneOverlay, camera);
  } else if (mode === "compare" && gtObj) {
    const x = Math.floor(split * w);
    renderer.setScissorTest(true);
    renderer.setViewport(0, 0, w, h);
    renderer.setScissor(0, 0, x, h);
    renderer.render(sceneOurs, camera);
    renderer.setScissor(x, 0, w - x, h);
    renderer.render(sceneGt, camera);
    renderer.setScissorTest(false);
  } else {
    renderer.setScissorTest(false);
    renderer.render(sceneOurs, camera);
  }
}

function pointerFrac(ev) {
  const r = canvas.getBoundingClientRect();
  const x = (ev.touches ? ev.touches[0].clientX : ev.clientX) - r.left;
  return Math.min(0.92, Math.max(0.08, x / r.width));
}

splitEl.addEventListener("pointerdown", (e) => {
  dragging = true;
  splitEl.setPointerCapture(e.pointerId);
  controls.enabled = false;
});
window.addEventListener("pointermove", (e) => {
  if (!dragging) return;
  split = pointerFrac(e);
  splitEl.style.left = `${split * 100}%`;
});
window.addEventListener("pointerup", () => {
  dragging = false;
  controls.enabled = true;
});

export async function init() {
  const res = await fetch("data/scenes.json");
  scenes = await res.json();
  sceneSelect.innerHTML = scenes.map((s) => {
    const tag = s.gt ? " · GT" : "";
    return `<option value="${s.id}">${s.label}${tag}</option>`;
  }).join("");
  sceneSelect.addEventListener("change", () => loadScene(sceneSelect.value));
  document.querySelectorAll("[data-mode]").forEach((b) => {
    b.addEventListener("click", () => {
      const m = b.dataset.mode;
      if (m === "compare" || m === "overlay") {
        const has = scenes.find((s) => s.id === sceneSelect.value)?.gt;
        if (!has) {
          const first = scenes.find((s) => s.gt);
          if (first) sceneSelect.value = first.id;
        }
      }
      setMode(m);
    });
  });
  document.getElementById("btn-reset").addEventListener("click", () => {
    if (pointsObj) fitCamera(pointsObj);
  });
  document.getElementById("btn-spin").addEventListener("click", (e) => {
    autoRotate = !autoRotate;
    e.currentTarget.classList.toggle("active", autoRotate);
  });
  if (location.hash === "#poster") {
    document.body.classList.add("poster");
    autoRotate = true;
    document.getElementById("btn-spin").classList.add("active");
  }
  const start = scenes.find((s) => s.modes.includes("browse")) || scenes[0];
  sceneSelect.value = start.id;
  document.querySelectorAll("[data-mode]").forEach((b) => b.classList.toggle("active", b.dataset.mode === "browse"));
  await loadScene(start.id);
  render();
}
