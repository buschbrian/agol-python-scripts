// Click-through training-label page. Blind by design: the data carries no class, model or triage field.
"use strict";
const PAGE_VERSION = "2026-10-22 split v2, priority, recheck, calibration with split";
const CALIBRATION_FILTERS = ["open", "all", "answered"];

const EXPORT_KEYS = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "0"];
const COLOUR_MODES = ["imagery", "height", "intensity", "returns"];
const state = { meta: null, units: [], list: [], pos: 0, answers: {}, reviewer: "", colour: 0, current: null,
                split: null };   // split in progress: { z (m above ground), above (label) }
const $ = (id) => document.getElementById(id);

function storage(key, value) {
  try {
    if (value === undefined) return localStorage.getItem(key);
    localStorage.setItem(key, value);
  } catch (e) { return null; }
}

async function getJSON(url) {
  const r = await fetch(url, { cache: "no-store" });
  if (!r.ok) throw new Error(`${url}: ${r.status}`);
  return r.json();
}

// ---------------------------------------------------------------- 3D view
const view = { renderer: null, scene: null, camera: null, controls: null, points: null, ring: null };

function init3d() {
  const host = $("view3d");
  view.renderer = new THREE.WebGLRenderer({ antialias: true });
  view.renderer.setPixelRatio(window.devicePixelRatio);
  host.appendChild(view.renderer.domElement);
  view.scene = new THREE.Scene();
  view.scene.background = new THREE.Color(0x0b0f14);
  view.camera = new THREE.PerspectiveCamera(50, 1, 0.1, 500);
  view.camera.up.set(0, 0, 1);
  view.controls = new THREE.OrbitControls(view.camera, view.renderer.domElement);
  view.controls.enableDamping = true;
  const resize = () => {
    const w = host.clientWidth, h = host.clientHeight;
    view.renderer.setSize(w, h);
    view.camera.aspect = w / h;
    view.camera.updateProjectionMatrix();
  };
  new ResizeObserver(resize).observe(host);
  resize();
  (function loop() { requestAnimationFrame(loop); view.controls.update(); view.renderer.render(view.scene, view.camera); })();
}

function resetCamera(unit) {
  const mid = (unit.Z_LOW + unit.Z_HIGH) / 2;
  view.controls.target.set(0, 0, mid);
  view.camera.position.set(-14, -18, mid + 14);
  view.controls.update();
}

function decode(buffer, n) {
  return {
    x: new Float32Array(buffer, 0, n), y: new Float32Array(buffer, 4 * n, n), z: new Float32Array(buffer, 8 * n, n),
    r: new Uint8Array(buffer, 12 * n, n), g: new Uint8Array(buffer, 13 * n, n), b: new Uint8Array(buffer, 14 * n, n),
    intensity: new Uint8Array(buffer, 15 * n, n), returns: new Uint8Array(buffer, 16 * n, n), n,
  };
}

function inPatch(p, i, u) {
  return Math.hypot(p.x[i], p.y[i]) <= u.R && p.z[i] >= u.Z_LOW && p.z[i] <= u.Z_HIGH;
}

function rampColour(t) {            // dark blue -> teal -> yellow, readable on the dark background
  t = Math.min(1, Math.max(0, t));
  const stops = [[0.15, 0.25, 0.65], [0.1, 0.65, 0.65], [0.95, 0.85, 0.2]];
  const s = t < 0.5 ? 0 : 1, f = t < 0.5 ? t * 2 : (t - 0.5) * 2;
  return stops[s].map((a, k) => a + (stops[s + 1][k] - a) * f);
}

function pointColour(p, i, u, mode, zmax) {
  if (inPatch(p, i, u)) return [1.0, 0.25, 0.2];            // the patch: always red
  if (mode === "imagery") return [p.r[i] / 255, p.g[i] / 255, p.b[i] / 255];
  if (mode === "height") return rampColour(p.z[i] / Math.max(zmax, 1));
  if (mode === "intensity") { const v = p.intensity[i] / 255; return [v, v, v]; }
  const rn = p.returns[i] >> 4, nr = p.returns[i] & 15;     // returns: single green, first orange, later purple
  if (nr <= 1) return [0.35, 0.8, 0.4];
  return rn === 1 ? [0.95, 0.6, 0.2] : [0.6, 0.45, 0.95];
}

function draw3d(p, u) {
  if (view.points) { view.scene.remove(view.points); view.points.geometry.dispose(); }
  if (view.ring) { view.scene.remove(view.ring); view.ring.geometry.dispose(); }
  const mode = COLOUR_MODES[state.colour];
  let zmax = 0;
  for (let i = 0; i < p.n; i++) zmax = Math.max(zmax, p.z[i]);
  const pos = new Float32Array(p.n * 3), col = new Float32Array(p.n * 3);
  for (let i = 0; i < p.n; i++) {
    pos[3 * i] = p.x[i]; pos[3 * i + 1] = p.y[i]; pos[3 * i + 2] = p.z[i];
    const c = pointColour(p, i, u, mode, zmax);
    col[3 * i] = c[0]; col[3 * i + 1] = c[1]; col[3 * i + 2] = c[2];
  }
  const g = new THREE.BufferGeometry();
  g.setAttribute("position", new THREE.BufferAttribute(pos, 3));
  g.setAttribute("color", new THREE.BufferAttribute(col, 3));
  view.points = new THREE.Points(g, new THREE.PointsMaterial({ size: 0.16, vertexColors: true }));
  view.scene.add(view.points);
  const outline = [];                                       // the patch: top and bottom rims and four uprights
  for (let k = 0; k < 48; k++) {
    const a = 2 * Math.PI * k / 48, b = 2 * Math.PI * (k + 1) / 48;
    for (const z of [u.Z_LOW, u.Z_HIGH]) outline.push(u.R * Math.cos(a), u.R * Math.sin(a), z, u.R * Math.cos(b), u.R * Math.sin(b), z);
  }
  for (let k = 0; k < 4; k++) {
    const a = Math.PI * k / 2;
    outline.push(u.R * Math.cos(a), u.R * Math.sin(a), u.Z_LOW, u.R * Math.cos(a), u.R * Math.sin(a), u.Z_HIGH);
  }
  const lines = new THREE.BufferGeometry();
  lines.setAttribute("position", new THREE.BufferAttribute(new Float32Array(outline), 3));
  view.ring = new THREE.LineSegments(lines, new THREE.LineBasicMaterial({ color: 0xff3b30 }));
  view.scene.add(view.ring);
  if (view.splitRing) { view.scene.remove(view.splitRing); view.splitRing.geometry.dispose(); view.splitRing = null; }
  const z = splitHeight(u);
  if (z !== null) {
    const ring = [];
    for (let k = 0; k < 48; k++) {
      const a = 2 * Math.PI * k / 48, b = 2 * Math.PI * (k + 1) / 48;
      ring.push(u.R * Math.cos(a), u.R * Math.sin(a), z, u.R * Math.cos(b), u.R * Math.sin(b), z);
    }
    const g2 = new THREE.BufferGeometry();
    g2.setAttribute("position", new THREE.BufferAttribute(new Float32Array(ring), 3));
    view.splitRing = new THREE.LineSegments(g2, new THREE.LineBasicMaterial({ color: 0xffd60a }));
    view.scene.add(view.splitRing);
  }
  $("colour-mode").textContent = mode;
}

// ---------------------------------------------------------------- imagery map (layers from <data>/imagery-layers.json)
const imagery = { map: null, patch: null, extent: null, ready: false };

async function initImagery() {
  const cfg = await getJSON("/api/imagery");
  const note = $("map-note");
  if (!cfg.layers.length) {
    note.hidden = false;
    note.textContent = cfg.error ? `Imagery file problem: ${cfg.error}` :
      `No high-resolution layer yet. Copy imagery-layers.example.json to ${cfg.file}, put your own Discover tile link in it, and reload.`;
    return showTab("chip");
  }
  imagery.map = L.map("map", { maxZoom: 22, zoomSnap: 0.5 });
  const layers = {};
  const wanted = storage("labelPage.layer");
  cfg.layers.forEach((l, i) => {
    const name = l.date ? `${l.name} (${l.date})` : l.name;
    layers[name] = l.type === "wms"
      ? L.tileLayer.wms(l.url, { layers: l.layers, format: l.format, version: "1.1.1", transparent: false, maxZoom: 22,
                                 attribution: l.attribution })
      : L.tileLayer(l.url, { maxZoom: 22, maxNativeZoom: l.maxNativeZoom, attribution: l.attribution });
    if ((wanted && wanted === name) || (!wanted && i === 0)) layers[name].addTo(imagery.map);
  });
  if (!Object.values(layers).some((t) => imagery.map.hasLayer(t))) Object.values(layers)[0].addTo(imagery.map);
  L.control.layers(layers, null, { collapsed: true }).addTo(imagery.map);
  imagery.map.on("baselayerchange", (e) => storage("labelPage.layer", e.name));
  imagery.ready = true;
  showTab("map");
}

function showTab(which) {
  const map = which === "map" && imagery.ready;
  $("map").hidden = !map;
  $("chip-figure").hidden = map;
  $("tab-map").setAttribute("aria-selected", String(map));
  $("tab-chip").setAttribute("aria-selected", String(!map));
  if (map) { imagery.map.invalidateSize(); if (state.current) placeOnMap(state.current); }
}

function placeOnMap(u) {
  if (!imagery.ready || u.LAT === undefined) return;
  imagery.map.setView([u.LAT, u.LON], 20, { animate: false });
  if (imagery.patch) imagery.patch.remove();
  if (imagery.extent) imagery.extent.remove();
  imagery.extent = L.circle([u.LAT, u.LON], { radius: state.meta.radius_m, color: "#ffd60a", weight: 1, dashArray: "4 4", fill: false }).addTo(imagery.map);
  imagery.patch = L.circle([u.LAT, u.LON], { radius: u.R, color: "#ff3b30", weight: 2, fill: false }).addTo(imagery.map);
}

// ---------------------------------------------------------------- side sections
function drawSection(canvas, p, u, axis) {
  const ctx = canvas.getContext("2d"), W = canvas.width, H = canvas.height, half = 1.5, span = 12;
  ctx.fillStyle = "#0b0f14"; ctx.fillRect(0, 0, W, H);
  const across = axis === "x" ? p.y : p.x, along = axis === "x" ? p.x : p.y;
  let zmin = Math.min(0, u.Z_LOW - 1), zmax = u.Z_HIGH + 2;
  for (let i = 0; i < p.n; i++) if (Math.abs(across[i]) <= half && Math.abs(along[i]) <= span) zmax = Math.max(zmax, p.z[i] + 0.5);
  const scale = Math.min(W / (2 * span), H / (zmax - zmin));
  const sx = (v) => W / 2 + v * scale, sz = (v) => H - (v - zmin) * scale;
  canvas.toHeight = (py) => zmin + (H - py) / scale;          // used to pick a split height with the mouse
  ctx.strokeStyle = "#2c3845"; ctx.fillStyle = "#6d7d8d"; ctx.font = "11px system-ui"; ctx.lineWidth = 1;
  for (let m = Math.ceil(zmin); m <= zmax; m += 2) { ctx.beginPath(); ctx.moveTo(0, sz(m)); ctx.lineTo(W, sz(m)); ctx.stroke(); ctx.fillText(`${m} m`, 4, sz(m) - 2); }
  ctx.strokeStyle = "#ff3b30";
  ctx.strokeRect(sx(-u.R), sz(u.Z_HIGH), 2 * u.R * scale, (u.Z_HIGH - u.Z_LOW) * scale);
  for (let i = 0; i < p.n; i++) {
    if (Math.abs(across[i]) > half || Math.abs(along[i]) > span) continue;
    const c = inPatch(p, i, u) ? [1, 0.25, 0.2] : pointColour(p, i, u, COLOUR_MODES[state.colour], zmax);
    ctx.fillStyle = `rgb(${c[0] * 255 | 0},${c[1] * 255 | 0},${c[2] * 255 | 0})`;
    ctx.fillRect(sx(along[i]) - 1, sz(p.z[i]) - 1, 2, 2);
  }
  const z = splitHeight(u);
  if (z !== null) {
    ctx.strokeStyle = "#ffd60a"; ctx.setLineDash([6, 4]); ctx.lineWidth = 1.5;
    ctx.beginPath(); ctx.moveTo(sx(-u.R - 1), sz(z)); ctx.lineTo(sx(u.R + 1), sz(z)); ctx.stroke();
    ctx.setLineDash([]); ctx.fillStyle = "#ffd60a"; ctx.fillText("split " + z.toFixed(2) + " m", sx(u.R + 1.2), sz(z) + 4);
  }
}

// ---------------------------------------------------------------- split answers (LABEL above SPLIT_Z, LABEL_BELOW below)
function splitHeight(u) {                 // metres above ground, from the split in progress or the saved answer
  if (state.split && state.split.z !== null && state.current === u) return state.split.z;
  const a = state.answers[u.UNIT_ID];
  return a && a.SPLIT_Z !== null && a.SPLIT_Z !== undefined && a.SPLIT_Z !== "" ? Number(a.SPLIT_Z) - u.GROUND_Z : null;
}

function splitText(a, u) {
  return a.LABEL + " above " + (Number(a.SPLIT_Z) - u.GROUND_Z).toFixed(2) + " m, " + a.LABEL_BELOW + " below";
}

function splitBanner() {
  const b = $("split-banner");
  if (!state.split) { b.hidden = true; return; }
  b.hidden = false;
  const z = state.split.z.toFixed(2);
  const top = state.cal ? " (the top, which is scored)" : "", under = state.cal ? " (the object under it)" : "";
  b.innerHTML = state.split.above
    ? `Split at ${z} m · above: <b>${state.split.above}</b> · now press the label key for the points <b>BELOW</b> the line${under} · <kbd>Esc</kbd> cancels`
    : `Split at ${z} m · move the yellow line with <kbd>↑</kbd> <kbd>↓</kbd> (Shift = 50 cm) or click a section · then press the label key for the points <b>ABOVE</b> the line${top} · <kbd>Esc</kbd> cancels`;
}

function startSplit() {
  const u = state.current;
  if (!u) return;
  if (!state.reviewer) return askReviewer();          // ask before the split, so it is not lost at the save
  state.split = { z: (u.Z_LOW + u.Z_HIGH) / 2, above: null };
  redraw();
  splitBanner();
}

function moveSplit(step) {
  const u = state.current;
  if (!state.split || state.split.above) return;
  state.split.z = Math.min(u.Z_HIGH - 0.05, Math.max(u.Z_LOW + 0.05, state.split.z + step));
  redraw();
  splitBanner();
}

function cancelSplit() {
  state.split = null;
  redraw();
  splitBanner();
  setStatus("Split cancelled.");
}

function pickSplit(canvas, event) {
  if (!state.split || !canvas.toHeight) return;
  const rect = canvas.getBoundingClientRect();
  const z = canvas.toHeight((event.clientY - rect.top) * canvas.height / rect.height);
  const u = state.current;
  if (!(z > u.Z_LOW && z < u.Z_HIGH)) {
    return setStatus("Pick a height inside the patch (" + u.Z_LOW.toFixed(1) + " to " + u.Z_HIGH.toFixed(1) + " m).", "error");
  }
  state.split = { z, above: null };
  redraw();
  splitBanner();
}

function splitLabel(code) {             // true when the key was used by the split in progress
  if (!state.split) return false;
  const exported = state.meta.labels.find((l) => l.code === code).exported;
  if (!exported) { setStatus("Each part of a split needs a real class, not mixed or unsure.", "error"); return true; }
  if (!state.split.above) {
    state.split.above = code;
    splitBanner();
    return true;
  }
  if (code === state.split.above) { setStatus("The two parts need different labels.", "error"); return true; }
  const z = state.split.z, above = state.split.above;
  state.split = null;
  splitBanner();
  save(above, true, { LABEL_BELOW: code, SPLIT_Z: (z + state.current.GROUND_Z).toFixed(3) });
  return true;
}

// ---------------------------------------------------------------- unit list and display
function buildList() {
  const filter = $("filter").value, queue = $("queue").value;
  if (filter === "priority" || filter === "recheck") {
    // priority: units chosen to test the refinement rules; recheck: answers to look at again. Reasons are not shown.
    const byId = Object.fromEntries(state.units.map((u) => [u.UNIT_ID, u]));
    const ids = (filter === "priority" ? state.priority : state.recheck) || [];
    state.list = ids.map((id) => byId[id])
      .filter((u) => u && (!queue || u.QUEUE_NO === queue) && (filter === "recheck" || !u.SAVED_LABEL));
    storage("labelPage.filter", filter);
    storage("labelPage.queue", queue);
    return;
  }
  state.list = state.units.filter((u) => {
    if (queue && u.QUEUE_NO !== queue) return false;
    const answered = !!state.answers[u.UNIT_ID], saved = !!u.SAVED_LABEL;
    if (filter === "open") return !answered && !saved;
    if (filter === "answered") return answered;
    if (filter === "mixed") return answered && state.answers[u.UNIT_ID].LABEL === "MIXED";
    if (filter === "audit") return u.AUDIT;
    return true;
  });
  storage("labelPage.filter", filter);
  storage("labelPage.queue", queue);
}

function updateProgress() {
  const done = state.units.filter((u) => u.SAVED_LABEL || state.answers[u.UNIT_ID]).length;
  $("progress-bar").style.width = `${100 * done / state.units.length}%`;
  const page = Object.keys(state.answers).length;
  $("progress-text").textContent = `${done} of ${state.units.length} units labelled (${page} on this page, waiting for import)`;
}

async function show(pos) {
  if (!state.list.length) {
    $("unit-id").textContent = "nothing to label with this filter";
    $("position").textContent = "";
    return;
  }
  state.pos = Math.max(0, Math.min(pos, state.list.length - 1));
  const u = state.list[state.pos];
  state.current = u;
  state.split = null;
  splitBanner();
  storage("labelPage.unit", u.UNIT_ID);
  $("unit-id").textContent = u.UNIT_ID;
  $("audit-badge").hidden = !u.AUDIT;
  $("position").textContent = `${state.pos + 1} / ${state.list.length}`;
  $("chip").src = `/data/chips/${u.UNIT_ID}.png`;
  placeOnMap(u);
  const ringR = 50 * u.R / (state.meta.chip_m / 2);
  $("chip-ring").querySelector("circle").setAttribute("r", ringR.toFixed(2));
  const h = u.PATCH_HEIGHT;
  // Calibration: no heights, so nothing printed can hint at a stratum (the points themselves are the evidence).
  $("facts").innerHTML = state.cal ? [
    ["Question", "What is the highest object within 1 m (the red column) of this point?"],
    ["Review order", `${u.REVIEW_ORDER} of ${state.units.length}: label in order, do not skip`],
    ["Points within 1 m", `${u.PATCH_POINTS}`],
    ["Already in labels.csv", u.SAVED_LABEL ? `${u.SAVED_LABEL} (${u.SAVED_REVIEWER || "?"})` : "no"],
    ...(state.answers[u.UNIT_ID] && state.answers[u.UNIT_ID].LABEL_BELOW ? [["Split", splitText(state.answers[u.UNIT_ID], u)]] : []),
  ].map(([k, v]) => `<dt>${k}</dt><dd>${v}</dd>`).join("") : [
    ["Patch", `${u.R.toFixed(1)} m radius, ${u.Z_LOW.toFixed(1)} to ${u.Z_HIGH.toFixed(1)} m above ground`],
    ["Patch points", `${u.PATCH_POINTS}`],
    ["Patch heights", h ? `${h.min.toFixed(1)} to ${h.max.toFixed(1)} m (mean ${h.mean.toFixed(1)})` : "—"],
    ["Already in Pro", u.SAVED_LABEL ? `${u.SAVED_LABEL} (${u.SAVED_REVIEWER || "?"})` : "no"],
    ...(state.answers[u.UNIT_ID] && state.answers[u.UNIT_ID].LABEL_BELOW ? [["Split", splitText(state.answers[u.UNIT_ID], u)]] : []),
  ].map(([k, v]) => `<dt>${k}</dt><dd>${v}</dd>`).join("");
  const answer = state.answers[u.UNIT_ID] || {};
  $("notes").value = answer.NOTES || "";
  $("usable").value = answer.IMAGERY_USABLE || "";
  markButtons(answer.LABEL, u.SAVED_LABEL);
  setStatus("");
  const buffer = await (await fetch(`/data/points/${u.UNIT_ID}.bin`)).arrayBuffer();
  if (state.current !== u) return;                       // moved on while loading
  state.points = decode(buffer, u.POINTS);
  draw3d(state.points, u);
  resetCamera(u);
  drawSection($("section-ew"), state.points, u, "x");
  drawSection($("section-ns"), state.points, u, "y");
}

function redraw() {
  if (!state.points || !state.current) return;
  draw3d(state.points, state.current);
  drawSection($("section-ew"), state.points, state.current, "x");
  drawSection($("section-ns"), state.points, state.current, "y");
}

function markButtons(label, saved) {
  const a = state.current && state.answers[state.current.UNIT_ID];
  const below = a && a.LABEL_BELOW;
  document.querySelectorAll(".labels button").forEach((b) => {
    b.classList.toggle("chosen", b.dataset.code === label);
    b.classList.toggle("chosen-below", !!below && b.dataset.code === below);
    b.classList.toggle("saved-before", b.dataset.code === saved && b.dataset.code !== label);
  });
}

function setStatus(text, kind) {
  $("status").textContent = text;
  $("status").className = kind || "";
}

function nextOpen(from) {          // the list stays as built, so earlier answers can be revisited with the left arrow
  for (let i = from + 1; i < state.list.length; i++) {
    const u = state.list[i];
    if (!state.answers[u.UNIT_ID] && !u.SAVED_LABEL) return i;
  }
  return Math.min(from + 1, state.list.length - 1);
}

async function save(label, advance = true, extra = {}) {
  const u = state.current;
  if (!u) return;
  if (!state.reviewer) return askReviewer();
  const where = state.cal ? "labels.csv" : "Pro", how = state.cal ? "import-page --replace" : "restore --replace";
  if (u.SAVED_LABEL && label && u.SAVED_LABEL !== label &&
      !confirmed(`${u.UNIT_ID} already has ${u.SAVED_LABEL} in ${where}. Importing ${label} will need ${how}. Save anyway?`)) return;
  const body = { UNIT_ID: u.UNIT_ID, LABEL: label || "", NOTES: $("notes").value, IMAGERY_USABLE: $("usable").value,
                 REVIEWER: state.reviewer, LABEL_BELOW: "", SPLIT_Z: "", ...extra };
  const r = await fetch("/api/answer", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  const reply = await r.json();
  if (!r.ok) return setStatus(reply.error || "Not saved", "error");
  if (label) state.answers[u.UNIT_ID] = reply.saved; else delete state.answers[u.UNIT_ID];
  markButtons(label, u.SAVED_LABEL);
  updateProgress();
  redraw();
  const saved = state.answers[u.UNIT_ID];
  const message = !label ? "Cleared " + u.UNIT_ID : saved && saved.LABEL_BELOW ? "Saved " + u.UNIT_ID + ": " + splitText(saved, u)
    : "Saved " + u.UNIT_ID + ": " + label;
  if (label && advance && $("auto-advance").checked) await show(nextOpen(state.pos));
  setStatus(message, "ok");
}

function askReviewer() {
  // An inline box, not prompt(): the Claude desktop browser pane does not support prompt() (October 22), and a save that
  // waited on it failed silently before reaching the server.
  $("reviewer").focus();
  setStatus("Not saved: type your initials in the Initials box (top right), then label again.", "error");
}

function setReviewer() {
  state.reviewer = $("reviewer").value.trim().slice(0, 64);
  storage("labelPage.reviewer", state.reviewer);
}

function showReviewer() {
  $("reviewer").value = state.reviewer;
}

function confirmed(message) {      // confirm() where the browser has it; otherwise refuse and say why
  try { return confirm(message); } catch (e) {
    setStatus(`Not saved: ${message} This browser cannot ask, so clear the unit or use --replace on import.`, "error");
    return false;
  }
}

function buildLabelButtons() {
  const host = $("labels");
  let k = 0;
  for (const l of state.meta.labels) {
    const key = l.exported ? EXPORT_KEYS[k++] : (l.code === "MIXED" ? "M" : "U");
    const b = document.createElement("button");
    b.dataset.code = l.code;
    b.dataset.key = key;
    b.title = l.description;
    b.innerHTML = `<kbd>${key}</kbd> ${l.code.replaceAll("_", " ").toLowerCase()}`;
    b.addEventListener("click", () => { if (!splitLabel(l.code)) save(l.code); });
    host.appendChild(b);
  }
}

function keys(e) {
  if (e.target.tagName === "TEXTAREA" || e.target.tagName === "INPUT") {
    if (e.key === "Escape" || (e.key === "Enter" && e.target.tagName === "INPUT")) e.target.blur();
    return;
  }
  if (e.key === "Escape" && state.split) return cancelSplit();
  if (e.target.tagName === "SELECT" || e.ctrlKey || e.altKey || e.metaKey) return;
  const key = e.key.length === 1 ? e.key.toUpperCase() : e.key;
  const button = [...document.querySelectorAll(".labels button")].find((b) => b.dataset.key === key);
  if (button) { e.preventDefault(); if (splitLabel(button.dataset.code)) return; return save(button.dataset.code); }
  if (key === "S") { e.preventDefault(); return startSplit(); }
  if (state.split && (key === "ArrowUp" || key === "ArrowDown")) {
    e.preventDefault();
    return moveSplit((key === "ArrowUp" ? 1 : -1) * (e.shiftKey ? 0.5 : 0.1));
  }
  if (key === "ArrowRight" || key === "Enter") { e.preventDefault(); show(state.pos + 1); }
  else if (key === "ArrowLeft") { e.preventDefault(); show(state.pos - 1); }
  else if (key === "Backspace") { e.preventDefault(); save(""); }
  else if (key === "C") { state.colour = (state.colour + 1) % COLOUR_MODES.length; redraw(); }
  else if (key === "R") resetCamera(state.current);
  else if (key === "N") { e.preventDefault(); $("notes").focus(); }
  else if (key === "I") showTab($("map").hidden ? "map" : "chip");
}

function calibrationLayout() {    // a treetop calibration packet: one question per point, no split, no queues
  document.title = "Treetop Calibration";
  $("page-title").textContent = "Treetop calibration";
  for (const o of [...$("filter").options]) if (!CALIBRATION_FILTERS.includes(o.value)) o.remove();
  $("queue-label").hidden = true;
  $("usable-row").hidden = true;
  $("split").title = "S: a stacked column (e.g. wire over a tree): the top label, which is scored, then the object below";
  $("footer-note").innerHTML = "The red column is everything within 1 m of the point; label the highest object in it (only that " +
    "label is scored). For two stacked objects, such as a wire over a tree, press S: the label above the line, then the one " +
    "below. Ground under an object needs no split. Nothing on this page shows a flag, stratum or model class. Answers are " +
    "saved to <code id=\"csv-path\"></code>; copy them into the packet with <code>label_page.bat import-calibration --apply</code>.";
}

async function main() {
  $("version").textContent = "page " + PAGE_VERSION;
  init3d();
  state.meta = await getJSON("/data/units.json");
  state.units = state.meta.units;
  state.cal = state.meta.mode === "calibration";
  if (state.cal) calibrationLayout();
  if (!state.cal) {
    state.priority = await getJSON("/data/priority.json").then((p) => p.order).catch(() => []);
    state.recheck = await getJSON("/data/recheck.json").then((p) => p.order).catch(() => []);
  }
  const server = await getJSON("/api/state");
  state.answers = server.answers;
  $("csv-path").textContent = server.csv;
  state.reviewer = storage("labelPage.reviewer") || "";
  if (state.reviewer === "TEST") state.reviewer = "";      // left over from testing on October 20; ask again
  showReviewer();
  $("reviewer").addEventListener("input", setReviewer);
  window.addEventListener("unhandledrejection", (e) => setStatus(`Not saved: ${(e.reason && e.reason.message) || e.reason}`, "error"));
  buildLabelButtons();
  for (const q of [...new Set(state.units.map((u) => u.QUEUE_NO))].sort()) {
    const o = document.createElement("option"); o.value = q; o.textContent = q; $("queue").appendChild(o);
  }
  $("filter").value = storage("labelPage.filter") || "open";
  if (state.cal && !CALIBRATION_FILTERS.includes($("filter").value)) $("filter").value = "open";
  $("queue").value = storage("labelPage.queue") || "";
  for (const id of ["filter", "queue"]) $(id).addEventListener("change", () => { buildList(); show(0); });
  $("prev").addEventListener("click", () => show(state.pos - 1));
  $("next").addEventListener("click", () => show(state.pos + 1));
  $("clear").addEventListener("click", () => save(""));
  $("colour-mode").addEventListener("click", () => { state.colour = (state.colour + 1) % COLOUR_MODES.length; redraw(); });
  $("reset-view").addEventListener("click", () => resetCamera(state.current));
  $("tab-map").addEventListener("click", () => showTab("map"));
  for (const id of ["section-ew", "section-ns"]) $(id).addEventListener("click", (e) => pickSplit($(id), e));
  $("split").addEventListener("click", startSplit);
  $("tab-chip").addEventListener("click", () => showTab("chip"));
  initImagery().catch((e) => { $("map-note").hidden = false; $("map-note").textContent = `Imagery map unavailable: ${e.message}`; showTab("chip"); });
  window.addEventListener("pagehide", () => { state.unloading = true; });
  for (const [id, field] of [["notes", "NOTES"], ["usable", "IMAGERY_USABLE"]]) {
    // Re-save the chosen label with the new note or imagery flag: only for a real edit, never while the page unloads.
    $(id).addEventListener("change", (e) => {
      const a = state.current && state.answers[state.current.UNIT_ID];
      if (!a || state.unloading || !e.isTrusted || ($(id).value || "") === (a[field] || "")) return;
      save(a.LABEL, false, { LABEL_BELOW: a.LABEL_BELOW || "", SPLIT_Z: a.SPLIT_Z ?? "" });
    });
  }
  document.addEventListener("keydown", keys);
  buildList();
  updateProgress();
  const last = storage("labelPage.unit");
  const at = state.list.findIndex((u) => u.UNIT_ID === last);
  show(at >= 0 ? at : 0);
}

main().catch((e) => setStatus(`Could not start: ${e.message}`, "error"));
