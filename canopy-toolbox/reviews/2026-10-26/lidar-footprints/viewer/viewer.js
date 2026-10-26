// Two synchronized scenes of the Chambers Ave pilot block: the public three-way hybrid (roofer LoD2.2 on the county
// footprints, Esri LOD2.0 or LOD1.2 where roofer failed) and roofer LoD2.2 on the LiDAR-first outlines. Both packages come
// through serve_scene.py's local I3S shim. As in the October 24 viewer the scene is global with no terrain: for each bookmark
// the layers are lowered by that building's ground elevation so it stands on the imagery. Unvalidated LiDAR planning estimates.

const [Map, SceneView, SceneLayer, TileLayer, Basemap, Point, MeshSymbol3D, FillSymbol3DLayer, SolidEdges3D,
  UniqueValueRenderer, reactiveUtils] = await $arcgis.import([
  "@arcgis/core/Map.js",
  "@arcgis/core/views/SceneView.js",
  "@arcgis/core/layers/SceneLayer.js",
  "@arcgis/core/layers/TileLayer.js",
  "@arcgis/core/Basemap.js",
  "@arcgis/core/geometry/Point.js",
  "@arcgis/core/symbols/MeshSymbol3D.js",
  "@arcgis/core/symbols/FillSymbol3DLayer.js",
  "@arcgis/core/symbols/edges/SolidEdges3D.js",
  "@arcgis/core/renderers/UniqueValueRenderer.js",
  "@arcgis/core/core/reactiveUtils.js",
]);

const state = (window.state = { errors: [], loaded: false });
window.addEventListener("error", (e) => state.errors.push(String(e.message)));
window.addEventListener("unhandledrejection", (e) => state.errors.push(String(e.reason?.message || e.reason)));

const symbol = (rgb) => new MeshSymbol3D({ symbolLayers: [new FillSymbol3DLayer({
  material: { color: rgb }, edges: new SolidEdges3D({ color: [45, 55, 65, 0.6], size: 0.6 }) })] });
const byLevel = new UniqueValueRenderer({ field: "LEVEL", defaultSymbol: symbol([207, 213, 219]), uniqueValueInfos: [
  { value: "roofer LoD2.2", symbol: symbol([207, 213, 219]) },
  { value: "Esri LOD2.0", symbol: symbol([91, 143, 214]) },
  { value: "Esri LOD1.2", symbol: symbol([240, 162, 75]) }] });

const imagery = () => new Basemap({ baseLayers: [new TileLayer({
  url: "https://services.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer" })] });

const PANELS = [{ key: "now", fields: ["FP_ID", "LEVEL"] }, { key: "lidar", fields: ["FP_ID", "LB_ID", "LEVEL"] }];
for (const p of PANELS) {
  p.layer = new SceneLayer({ url: `${location.origin}/i3s/${p.key}/SceneServer/layers/0`, title: p.key,
    elevationInfo: { mode: "absolute-height", offset: 0 }, outFields: p.fields, renderer: byLevel });
  p.map = new Map({ basemap: imagery(), layers: [p.layer],
    ground: { surfaceColor: "#c8cdc0", opacity: 1, navigationConstraint: { type: "none" } } });
  p.view = new SceneView({ container: p.key, viewingMode: "global", map: p.map,
    environment: { atmosphereEnabled: false, starsEnabled: false, background: { type: "color", color: [226, 231, 236] },
      lighting: { type: "virtual", directShadowsEnabled: false } },
    ui: { components: ["zoom", "navigation-toggle", "compass"] } });
  p.view.constraints.collision = { enabled: false };
}
const views = PANELS.map((p) => p.view);

// Moving one view moves the other (only the view the pointer is in drives).
let active = null;
for (const p of PANELS) {
  for (const type of ["pointerdown", "wheel", "keydown"]) p.view.container.addEventListener(type, () => { active = p.view; }, { passive: true });
  reactiveUtils.watch(() => p.view.viewpoint, (vp) => {
    if (active !== p.view || !vp) return;
    for (const o of views) if (o !== p.view) o.viewpoint = vp;
  });
}

const fmt = (v) => (v === "" || v === undefined ? "none" : `${Math.round(Number(v)).toLocaleString()} m²`);
async function show(b) {
  active = null;
  for (const p of PANELS) p.layer.elevationInfo = { mode: "absolute-height", offset: -b.ground_z };
  const target = new Point({ longitude: b.lon, latitude: b.lat, z: 6, spatialReference: { wkid: 4326 } });
  const scale = Math.max(1100, 14 * b.size_m);
  await Promise.all(views.map((v) => v.goTo({ target, heading: 20, tilt: 55, scale }, { animate: false })
    .catch((e) => state.errors.push(e.message))));
  document.getElementById("caption").innerHTML = b.id === "block"
    ? "<b>The pilot block</b>: 62 LiDAR-first buildings, 29 matching a county footprint, 16 with none, 11 reshaped, " +
      "4 over several county outlines, 2 split. Buildings on a slope float or sink a little away from the bookmark's own ground."
    : `<b>${b.title}</b> · LiDAR outline ${fmt(b.lidar_m2)}, county ${fmt(b.county_m2)}` +
      `${b.county_ids ? ` (county ${b.county_ids.split(";").join(", ")})` : ""} · roofer roof: ${b.roof_type}` +
      `${b.rmse !== null && b.rmse !== undefined ? `, fit RMSE ${Number(b.rmse).toFixed(2)} m` : ""} · ground ${b.ground_z} m`;
}

const data = await (await fetch("bookmarks.json")).json();
const marks = data.bookmarks;
const select = document.getElementById("bookmarks");
marks.forEach((b, i) => select.add(new Option(b.title, String(i))));
const go = async (i) => { select.value = String(i); await show(marks[i]); };
select.addEventListener("change", () => go(Number(select.value)));
document.getElementById("prev").addEventListener("click", () => go((Number(select.value) + marks.length - 1) % marks.length));
document.getElementById("next").addEventListener("click", () => go((Number(select.value) + 1) % marks.length));
document.getElementById("imagery").addEventListener("change", (e) => {
  for (const p of PANELS) p.map.basemap = e.target.checked ? imagery() : null;
});

for (const p of PANELS) {
  try { await p.layer.load(); await p.view.whenLayerView(p.layer); }
  catch (e) { state.errors.push(`${p.key}: ${e.name} ${e.message}`); }
}
state.loaded = true;
await go(0);

// For the record: state.shoot(i) shows bookmark i, waits for both views to finish drawing, and POSTs one PNG per panel to
// serve_scene.py (/save/<bookmark>_<panel>.png in its OUT folder).
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
state.shoot = async (i, width = 900) => {
  await go(i);
  for (let calm = 0, t0 = Date.now(); calm < 4 && Date.now() - t0 < 30000; await sleep(500)) calm = views.every((v) => !v.updating) ? calm + 1 : 0;
  const names = [];
  for (const p of PANELS) {
    const c = p.view.container;
    const s = await p.view.takeScreenshot({ format: "png", width, height: Math.round(width * c.clientHeight / c.clientWidth) });
    const name = `${marks[i].id}_${p.key}.png`;
    await fetch(`/save/${name}`, { method: "POST", body: await (await fetch(s.dataUrl)).blob() });
    names.push(name);
  }
  return names;
};
