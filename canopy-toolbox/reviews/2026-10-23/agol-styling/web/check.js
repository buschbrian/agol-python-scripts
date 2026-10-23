// Styling check: open a web map, a web scene or one layer item as ArcGIS Online would, signed in with ArcGIS Pro's
// token (from serve_check.py), and report how each layer loaded and which style each vector tile layer used.
// Query parameters: item (web map or web scene id) or layer (a layer item id, added to a light grey basemap);
// bm (bookmark index), slide (slide index), center (lon,lat) and scale; popup (lon,lat) opens the pop-up there.
// The state goes to window.check (ready once the view has settled).

const [esriId, Portal, PortalItem, WebMap, WebScene, Map, MapView, SceneView, Layer, Legend, Point, reactiveUtils] =
  await $arcgis.import([
    "@arcgis/core/identity/IdentityManager.js",
    "@arcgis/core/portal/Portal.js",
    "@arcgis/core/portal/PortalItem.js",
    "@arcgis/core/WebMap.js",
    "@arcgis/core/WebScene.js",
    "@arcgis/core/Map.js",
    "@arcgis/core/views/MapView.js",
    "@arcgis/core/views/SceneView.js",
    "@arcgis/core/layers/Layer.js",
    "@arcgis/core/widgets/Legend.js",
    "@arcgis/core/geometry/Point.js",
    "@arcgis/core/core/reactiveUtils.js",
  ]);
const { default: token } = await import(`./token.js?${Date.now()}`);

const check = (window.check = { errors: [], layers: [], ready: false });
window.addEventListener("error", (e) => check.errors.push(String(e.message)));
window.addEventListener("unhandledrejection", (e) => check.errors.push(String(e.reason?.message || e.reason)));
const out = document.getElementById("out");
const log = (s) => { out.textContent += `${s}\n`; };

for (const server of ["https://www.arcgis.com/sharing/rest", "https://tiles.arcgis.com/tiles/XRrSFvEwSsReIxuA/arcgis/rest/services",
                      "https://services9.arcgis.com/XRrSFvEwSsReIxuA/arcgis/rest/services"]) {
  esriId.registerToken({ server, token: token.token, expires: token.expires * 1000, ssl: true });
}

const params = new URLSearchParams(location.search);
// Thumbnail mode: the map alone at 600 x 400 (ArcGIS Online's item thumbnail size), without widgets or attribution.
if (params.get("thumb")) document.body.classList.add("thumb");
let map, view;
if (params.get("item")) {
  const item = new PortalItem({ id: params.get("item") });
  await item.load();
  document.getElementById("title").textContent = item.title;
  const is3d = item.type === "Web Scene";
  map = is3d ? new WebScene({ portalItem: item }) : new WebMap({ portalItem: item });
  view = new (is3d ? SceneView : MapView)({ container: "view", map });
} else {
  const [id, sublayer] = params.get("layer").split("/");
  const layer = sublayer === undefined
    ? await Layer.fromPortalItem({ portalItem: { id } })
    : await Layer.fromPortalItem({ portalItem: { id }, layerId: Number(sublayer) });
  document.getElementById("title").textContent = layer.title;
  map = new Map({ basemap: params.get("basemap") || "gray-vector", layers: [layer] });
  view = new MapView({ container: "view", map });
}
await map.load?.();
await view.when();
new Legend({ view, container: "legend" });
if (params.get("thumb")) view.ui.components = [];

if (params.get("bm") && map.bookmarks?.length) {
  const bm = map.bookmarks.at(Number(params.get("bm")));
  log(`bookmark: ${bm.name}`);
  await view.goTo(bm.viewpoint, { animate: false });
}
if (params.get("slide") && map.presentation?.slides?.length) {
  const slide = map.presentation.slides.at(Number(params.get("slide")));
  log(`slide: ${slide.title.text}`);
  await slide.applyTo(view, { animate: false });
}
if (params.get("center")) {
  const [x, y] = params.get("center").split(",").map(Number);
  await view.goTo({ center: [x, y], scale: Number(params.get("scale") || 10000) }, { animate: false });
} else if (params.get("scale")) {
  await view.goTo({ scale: Number(params.get("scale")) }, { animate: false });
}
for (const id of (params.get("hide") || "").split(",").filter(Boolean)) {
  const layer = map.findLayerById(id);
  if (layer) layer.visible = false;
}

await reactiveUtils.whenOnce(() => !view.updating);
for (const layer of map.allLayers) {
  if (map.basemap?.baseLayers.includes(layer) || map.basemap?.referenceLayers.includes(layer)) continue;
  const row = { title: layer.title, type: layer.type, loadStatus: layer.loadStatus, visible: layer.visible,
                opacity: layer.opacity, blendMode: layer.blendMode, minScale: layer.minScale, maxScale: layer.maxScale,
                error: layer.loadError?.message };
  if (layer.type === "vector-tile") row.styleUrl = layer.currentStyleInfo?.styleUrl;
  check.layers.push(row);
}
if (map.ground) {
  check.ground = map.ground.layers.map((l) => ({ title: l.title, loadStatus: l.loadStatus, error: l.loadError?.message }));
}
log(`scale 1:${Math.round(view.scale)}`);
for (const row of check.layers) log(`${row.title}: ${row.loadStatus}${row.error ? " " + row.error : ""}`);

if (params.get("popup")) {
  const [x, y] = params.get("popup").split(",").map(Number);
  await view.openPopup({ location: new Point({ longitude: x, latitude: y }), fetchFeatures: true });
  await reactiveUtils.whenOnce(() => view.popup?.selectedFeature);
  await new Promise((r) => setTimeout(r, 1500));
  check.popup = view.popup.selectedFeature ? { title: view.popup.title } : null;
}
check.scale = view.scale;
check.ready = true;
