// Three synchronized scenes of the same buildings: the Esri LOD2.0 hybrid, roofer's LoD2.2 alone, and the three-way hybrid.
// Each view reads its scene layer package through the local I3S shim (serve_scene.py). The packages are WGS84, which a local
// scene in a projected system would refuse, and Web Mercator would stretch east-west by 1.3 here, so the scene is global. It has no
// terrain: the ground is the globe's surface at 0 m, and for each bookmark the layers are lowered by the building's ground elevation, so the building
// stands on the plane (neighbours on a slope float or sink a little). Query parameters: auto=1 shoots every bookmark and
// POSTs three PNGs per bookmark to /save/<id>_<panel>.png; w sets the screenshot width (default 1200; the height follows the
// panel's aspect); only=<id> shoots one bookmark.
// Unvalidated LiDAR planning estimates.

const [Map, SceneView, SceneLayer, Point, MeshSymbol3D, FillSymbol3DLayer, SolidEdges3D, UniqueValueRenderer,
  ClassBreaksRenderer, reactiveUtils, kernel] = await $arcgis.import([
  "@arcgis/core/Map.js",
  "@arcgis/core/views/SceneView.js",
  "@arcgis/core/layers/SceneLayer.js",
  "@arcgis/core/geometry/Point.js",
  "@arcgis/core/symbols/MeshSymbol3D.js",
  "@arcgis/core/symbols/FillSymbol3DLayer.js",
  "@arcgis/core/symbols/edges/SolidEdges3D.js",
  "@arcgis/core/renderers/UniqueValueRenderer.js",
  "@arcgis/core/renderers/ClassBreaksRenderer.js",
  "@arcgis/core/core/reactiveUtils.js",
  "@arcgis/core/kernel.js",
]);

const params = new URLSearchParams(location.search);
const AUTO = params.get("auto") === "1";
const SHOT_W = Number(params.get("w") || 1200), SHOT_H = Number(params.get("h") || 900);
const state = (window.state = { errors: [], loaded: false, done: false, shots: [], version: kernel.fullVersion });
window.addEventListener("error", (e) => state.errors.push(String(e.message)));
window.addEventListener("unhandledrejection", (e) => state.errors.push(String(e.reason?.message || e.reason)));
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const save = (name, body) => fetch(`/save/${name}`, { method: "POST", body });

const COLORS = { roofer: [207, 213, 219], esri20: [91, 143, 214], esri12: [240, 162, 75] };
const symbol = (rgb, edges) => new MeshSymbol3D({
  symbolLayers: [new FillSymbol3DLayer({
    material: { color: rgb }, edges: edges ? new SolidEdges3D({ color: [45, 55, 65, 0.55], size: 0.6 }) : null })],
});
// How each package says which model a building comes from.
function renderer(key, tint, edges) {
  const grey = [207, 213, 219];
  if (!tint) return { type: "simple", symbol: symbol(grey, edges) };
  if (key === "roofer") return { type: "simple", symbol: symbol(COLORS.roofer, edges) };
  if (key === "esri") {      // field LOD: 1.2 or 2.0
    return new ClassBreaksRenderer({ field: "LOD", classBreakInfos: [
      { minValue: 0, maxValue: 1.6, symbol: symbol(COLORS.esri12, edges) },
      { minValue: 1.6, maxValue: 9, symbol: symbol(COLORS.esri20, edges) }] });
  }
  return new UniqueValueRenderer({ field: "LEVEL", defaultSymbol: symbol(grey, edges), uniqueValueInfos: [
    { value: "roofer LoD2.2", symbol: symbol(COLORS.roofer, edges) },
    { value: "Esri LOD2.0", symbol: symbol(COLORS.esri20, edges) },
    { value: "Esri LOD1.2", symbol: symbol(COLORS.esri12, edges) }] });
}

const PANELS = [{ key: "esri", id: "v0" }, { key: "roofer", id: "v1" }, { key: "threeway", id: "v2" }];
for (const p of PANELS) {
  const fields = p.key === "esri" ? ["FP_ID", "LOD"] : p.key === "threeway" ? ["FP_ID", "LEVEL"] : ["FP_ID"];
  p.layer = new SceneLayer({ url: `${location.origin}/i3s/${p.key}/SceneServer/layers/0`, title: p.key,
    elevationInfo: { mode: "absolute-height", offset: 0 }, outFields: fields });
  p.layer.renderer = renderer(p.key, true, true);
  p.view = new SceneView({
    container: p.id, viewingMode: "global",
    map: new Map({ layers: [p.layer], ground: { surfaceColor: "#c8cdc0", opacity: 1, navigationConstraint: { type: "none" } } }),
    environment: { atmosphereEnabled: false, starsEnabled: false, background: { type: "color", color: [226, 231, 236] },
      lighting: { type: "sun", date: new Date("2026-06-21T20:00:00Z"), directShadowsEnabled: false } },
    ui: { components: [] },
  });
  p.view.constraints.collision = { enabled: false };
}
const views = PANELS.map((p) => p.view);

// Moving one view moves the others (only the view the pointer is in drives).
let active = null;
for (const p of PANELS) {
  for (const type of ["pointerdown", "wheel", "keydown"]) p.view.container.addEventListener(type, () => { active = p.view; }, { passive: true });
  reactiveUtils.watch(() => p.view.viewpoint, (vp) => {
    if (active !== p.view || !vp) return;
    for (const o of views) if (o !== p.view) o.viewpoint = vp;
  });
}

let bookmarks = [];
async function ready() {
  for (const p of PANELS) {
    try { await p.layer.load(); await p.view.whenLayerView(p.layer); }
    catch (e) { state.errors.push(`${p.key}: ${e.name} | ${e.message} | ${(() => { const d = { ...(e.details || {}) }; delete d.layer; delete d.view; return JSON.stringify(d, (k, v) => (v instanceof Error ? `${v.name}: ${v.message} ${JSON.stringify(v.details || {}).slice(0, 300)}` : v)).slice(0, 700); })()}`); }
  }
  state.loaded = true;
}
async function settle(maxMs = 25000) {
  const t0 = Date.now();
  let calm = 0;
  while (Date.now()-t0 < maxMs && calm < 4) {
    calm = views.every((v) => !v.updating) ? calm+1 : 0;
    await sleep(500);
  }
}
async function show(b) {
  active = null;
  for (const p of PANELS) p.layer.elevationInfo = { mode: "absolute-height", offset: -b.ground_z };
  const target = new Point({ longitude: b.lon, latitude: b.lat, z: 6, spatialReference: { wkid: 4326 } });
  const scale = Math.max(500, 9 * b.size_m);
  const heading = (b.fp_id * 37) % 360;
  await Promise.all(views.map((v) => v.goTo({ target, heading, tilt: 58, scale }, { animate: false }).catch((e) => state.errors.push(e.message))));
  const r = b.roofer, e = b.esri_lod20;
  document.getElementById("caption").innerHTML =
    `<b>${b.title}</b> &middot; ${b.type}, ${b.footprint_m2} m&sup2;, roof cover ${b.roof_cover_pct}% &middot; ` +
    `roofer: ${r.verdict}${r.note ? " (" + r.note + ")" : ""}, p95 ${r.p95_m} m, within 1 m ${r.within_1_pct}%, top ${r.top_minus_lidar_m} m vs lidar ` +
    `&middot; Esri LOD2.0: ${e.verdict}${e.note ? " (" + e.note + ")" : ""}, p95 ${e.p95_m} m, within 1 m ${e.within_1_pct}% ` +
    `&middot; Esri LOD1.2: p95 ${b.esri_lod12.p95_m} m &middot; three-way uses <b>${b.three_way_level}</b>`;
}
function restyle() {
  const tint = document.getElementById("tint").checked, edges = document.getElementById("edges").checked;
  for (const p of PANELS) p.layer.renderer = renderer(p.key, tint, edges);
}

async function shoot(b) {
  const out = [];
  for (const p of PANELS) {
    const c = p.view.container;
    const s = await Promise.race([
      p.view.takeScreenshot({ format: "png", width: SHOT_W, height: Math.round(SHOT_W * c.clientHeight / c.clientWidth) }),
      sleep(45000).then(() => { throw new Error(`screenshot of ${p.key} timed out`); })]);
    const blob = await (await fetch(s.dataUrl)).blob();
    const name = `${b.id}_${p.key}.png`;
    await save(name, blob);
    out.push(name);
  }
  state.shots.push(...out);
}

const data = await (await fetch("bookmarks.json")).json();
bookmarks = data.bookmarks;
const select = document.getElementById("bookmarks");
bookmarks.forEach((b, i) => select.add(new Option(`${b.id} ${b.title}`, String(i))));
const go = async (i) => { select.value = String(i); await show(bookmarks[i]); };
select.addEventListener("change", () => go(Number(select.value)));
document.getElementById("prev").addEventListener("click", () => go((Number(select.value)+bookmarks.length-1) % bookmarks.length));
document.getElementById("next").addEventListener("click", () => go((Number(select.value)+1) % bookmarks.length));
document.getElementById("tint").addEventListener("change", restyle);
document.getElementById("edges").addEventListener("change", restyle);

await ready();
if (AUTO) {
  // A lost WebGL context (three software-rendered views) hangs takeScreenshot: reload at the same bookmark once, then skip it.
  const from = Number(params.get("from") || 0), tries = Number(params.get("try") || 0);
  for (let i = from; i < bookmarks.length; i++) {
    if (params.get("only") && params.get("only") !== bookmarks[i].id) continue;
    try {
      await go(i);
      await sleep(1500);
      await settle();
      await shoot(bookmarks[i]);
    } catch (e) {
      await save(`error_${bookmarks[i].id}_try${tries}.txt`, `${e.message}`);
      const next = tries >= 1 ? i+1 : i;
      location.href = `?auto=1&w=${SHOT_W}&from=${next}&try=${tries >= 1 ? 0 : tries+1}`;
      await sleep(60000);
    }
  }
  state.done = true;
  document.getElementById("caption").textContent = `Done: ${state.shots.length} screenshots in this load. Errors: ${state.errors.length}.`;
} else {
  await go(0);
}
