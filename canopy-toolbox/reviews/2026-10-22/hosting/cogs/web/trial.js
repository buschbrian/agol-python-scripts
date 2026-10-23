// Slope COG trial: ArcGIS Maps SDK ImageryTileLayer reading a COG over HTTP range requests.
// Query parameters: file (path under the data server, default slope_percent.tif), sr (3857 with a basemap, or 6341 with
// no basemap), data (data server URL), interp (nearest or bilinear), tol (largest identify error accepted, 0 for a
// lossless COG), check=1 (run the point checks once the layer has drawn).
// Results go to window.trial so a test harness can read them.

const [ImageryTileLayer, ClassBreaksRenderer, Point, projectOperator, reactiveUtils, kernel] = await $arcgis.import([
  "@arcgis/core/layers/ImageryTileLayer.js",
  "@arcgis/core/renderers/ClassBreaksRenderer.js",
  "@arcgis/core/geometry/Point.js",
  "@arcgis/core/geometry/operators/projectOperator.js",
  "@arcgis/core/core/reactiveUtils.js",
  "@arcgis/core/kernel.js",
]);

const params = new URLSearchParams(location.search);
const DATA = params.get("data") || "http://127.0.0.1:8792/";
const FILE = params.get("file") || "slope_percent.tif";
const SR = params.get("sr") || "3857";
const TOL = Number(params.get("tol") || 0);
const URL_ = new URL(FILE, DATA).href;
// Grid of the city rasters (EPSG:6341, 0.5 m), to report the clicked cell.
const GRID = { x0: 422149, y0: 4507383, cell: 0.5 };
const BREAKS = [10, 15, 20, 25, 30];
const COLORS = ["#fef0d9", "#fdd49e", "#fdbb84", "#fc8d59", "#e34a33", "#b30000"];
const LABELS = ["under 10%", "10-15%", "15-20%", "20-25%", "25-30%", "30% and over"];

const trial = (window.trial = { url: URL_, sr: SR, interpolation: params.get("interp") || "nearest", errors: [], timings: {} });
window.addEventListener("error", (e) => trial.errors.push(String(e.message)));
window.addEventListener("unhandledrejection", (e) => trial.errors.push(String(e.reason?.message || e.reason)));

const view = document.getElementById("map");
const info = document.getElementById("info");
const show = (dl, rows) => {
  dl.innerHTML = rows.map(([k, v]) => `<dt>${k}</dt><dd>${v}</dd>`).join("");
};

function classRenderer() {
  const edges = [-1e9, ...BREAKS, 1e9];
  return new ClassBreaksRenderer({
    field: "value",
    classBreakInfos: COLORS.map((color, i) => ({
      minValue: edges[i], maxValue: edges[i + 1], label: LABELS[i], symbol: { type: "simple-fill", color, outline: null },
    })),
  });
}
document.getElementById("legend").innerHTML =
  COLORS.map((c, i) => `<div><span style="background:${c}"></span>${LABELS[i]}</div>`).join("");

const t0 = performance.now();
if (SR === "6341") {
  view.spatialReference = { wkid: 6341 };
} else {
  view.basemap = "gray-vector";
}
await view.componentOnReady();
const layer = new ImageryTileLayer({ url: URL_, title: FILE });
let defaultRenderer;
try {
  await layer.load();
} catch (e) {
  trial.errors.push(`load: ${e.message}`);
  show(info, [["error", e.message]]);
  throw e;
}
trial.timings.layer_loaded_ms = Math.round(performance.now() - t0);
defaultRenderer = layer.renderer?.clone();
trial.defaultInterpolation = layer.interpolation;
// The layer resamples bilinearly by default, which blends neighbouring cells before they are classed; classes need
// nearest. The `interp` parameter keeps the default for comparison.
const INTERP = params.get("interp") || "nearest";
layer.interpolation = INTERP;
layer.renderer = classRenderer();
// With sr=6341 there is no basemap, and the zoom stops at the layer's finest level, one screen pixel per cell. Loosening
// view.constraints to zoom closer moved the drawn centre 32 cells off the view's centre in 5.1.27, so the checks run at
// one pixel per cell there, which nearest resampling still draws exactly.
view.map.add(layer);
const layerView = await view.whenLayerView(layer);
await view.goTo(layer.fullExtent);
await reactiveUtils.whenOnce(() => !layerView.updating);
trial.timings.first_draw_ms = Math.round(performance.now() - t0);
await projectOperator.load();

const ri = layer.serviceRasterInfo ?? layer.rasterInfo;  // 5.x: serviceRasterInfo
trial.rasterInfo = {
  pixelType: ri.pixelType, noDataValue: ri.noDataValue, wkid: ri.spatialReference?.wkid,
  view_wkid: view.spatialReference.wkid, width: ri.width, height: ri.height, bandCount: ri.bandCount,
  levels: layer.tileInfo?.lods?.length, statistics: ri.statistics,
};
trial.sdk = { version: kernel.version, fullVersion: kernel.fullVersion, buildDate: kernel.buildDate };

function dataRequests() {
  const entries = performance.getEntriesByType("resource").filter((e) => e.name.startsWith(DATA));
  return { requests: entries.length, bytes: entries.reduce((s, e) => s + (e.transferSize || e.encodedBodySize || 0), 0) };
}
function showInfo() {
  const d = dataRequests();
  show(info, [
    ["SDK", `${trial.sdk.fullVersion || trial.sdk.version}`],
    ["COG", URL_],
    ["pixel type", ri.pixelType], ["NoData", String(ri.noDataValue)],
    ["layer SR", ri.spatialReference?.wkid], ["view SR", view.spatialReference.wkid],
    ["size", `${ri.width} x ${ri.height}`],
    ["loaded", `${trial.timings.layer_loaded_ms} ms`], ["first draw", `${trial.timings.first_draw_ms} ms`],
    ["COG requests", `${d.requests} (${(d.bytes / 1e6).toFixed(2)} MB)`],
  ]);
}
trial.firstDraw = dataRequests();
showInfo();

document.getElementById("renderer").addEventListener("change", (e) => {
  layer.renderer = e.target.value === "classes" ? classRenderer() : defaultRenderer;
});

const cellOf = (p) => ({ col: Math.floor((p.x - GRID.x0) / GRID.cell), row: Math.floor((GRID.y0 - p.y) / GRID.cell) });
const valueOf = (r) => (r?.value ? r.value[0] : null);

view.addEventListener("arcgisViewClick", async ({ detail: { mapPoint } }) => {
  const t = performance.now();
  const result = await layer.identify(mapPoint);
  const ms = Math.round(performance.now() - t);
  const utm = projectOperator.execute(mapPoint, { wkid: 6341 });
  const cell = cellOf(utm);
  trial.lastClick = { x: utm.x, y: utm.y, ...cell, value: valueOf(result), ms };
  show(document.getElementById("click"), [
    ["value", valueOf(result) === null ? "NoData" : String(valueOf(result))],
    ["EPSG:6341", `${utm.x.toFixed(2)}, ${utm.y.toFixed(2)}`], ["cell", `col ${cell.col}, row ${cell.row}`],
    ["identify", `${ms} ms`],
  ]);
  showInfo();
});

const hex = (c) => [1, 3, 5].map((i) => parseInt(c.slice(i, i + 2), 16));
function expectedClass(v) {
  if (v === null) return null;
  let k = 0;
  while (k < BREAKS.length && v >= BREAKS[k]) k++;
  return k;
}
function nearestClass(rgba) {
  let best = null, dist = Infinity;
  COLORS.forEach((c, i) => {
    const d = Math.max(...hex(c).map((ch, j) => Math.abs(ch - rgba[j])));
    if (d < dist) { dist = d; best = i; }
  });
  return dist <= 3 ? best : null;
}

async function runChecks() {
  const spec = await (await fetch("points.json")).json();
  const rows = [];
  for (const p of spec.points) {
    const utm = new Point({ x: p.x, y: p.y, spatialReference: { wkid: 6341 } });
    const inView = projectOperator.execute(utm, view.spatialReference);
    const direct = valueOf(await layer.identify(utm));
    const viaView = valueOf(await layer.identify(inView));
    // Draw the cell large (about 30 px) and read the rendered colour at the screen centre, once the view has settled:
    // updating can still be false straight after goTo, before the new tiles are requested.
    await view.goTo({ target: inView, scale: 70 }, { animate: false });
    await reactiveUtils.whenOnce(() => view.stationary);
    await new Promise((r) => setTimeout(r, 500));
    await reactiveUtils.whenOnce(() => !layerView.updating && !view.updating);
    // The arcgis-map element has no width or height of its own; its MapView does.
    const centre = { x: Math.round(view.view.width / 2), y: Math.round(view.view.height / 2) };
    const shot = await view.takeScreenshot({ area: { ...centre, width: 1, height: 1 }, format: "png" });
    const rgba = Array.from(shot.data.data.slice(0, 4));
    const atCentre = cellOf(projectOperator.execute(view.toMap(centre), { wkid: 6341 }));
    const want = expectedClass(p.slope_percent);
    const drawn = nearestClass(rgba);
    rows.push({
      col: p.col, row: p.row, gdal: p.slope_percent, identify_6341: direct, identify_view_sr: viaView,
      value_ok: [direct, viaView].every((v) => (v === null || p.slope_percent === null
        ? v === p.slope_percent : Math.abs(v - p.slope_percent) <= TOL)),
      abs_error: direct === null || p.slope_percent === null ? null : Math.abs(direct - p.slope_percent),
      centre_cell: atCentre, centre_on_cell: atCentre.col === p.col && atCentre.row === p.row,
      class_expected: want, class_drawn: drawn, rgba, class_ok: want === drawn,
    });
  }
  trial.checks = rows;
  trial.checks_ok = rows.every((r) => r.value_ok && r.class_ok && r.centre_on_cell);
  trial.tolerance = TOL;
  const cls = (k) => (k === null ? "none" : LABELS[k]);
  document.getElementById("checks").innerHTML =
    "<tr><th>cell</th><th>GDAL</th><th>identify</th><th>class drawn</th></tr>" +
    rows.map((r) => `<tr><td>${r.col}, ${r.row}</td><td>${r.gdal ?? "NoData"}</td>` +
      `<td class="${r.value_ok ? "ok" : "bad"}">${r.identify_6341 ?? "NoData"}</td>` +
      `<td class="${r.class_ok ? "ok" : "bad"}">${cls(r.class_drawn)}</td></tr>`).join("");
  await view.goTo(layer.fullExtent, { animate: false });
  return rows;
}
document.getElementById("run").addEventListener("click", runChecks);
trial.runChecks = runChecks;
trial.ready = true;
if (params.get("check") === "1") await runChecks();
