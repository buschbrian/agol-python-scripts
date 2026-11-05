// COG alignment check: where the ArcGIS Maps SDK puts an EPSG:6341 COG in a Web Mercator view, against the hosted
// contours (packaged with WGS_1984_(ITRF08)_To_NAD_1983_2011) and against each check cell's centre projected with that
// transformation and with none (cells.json, from cells.py).
// Query parameters: data (data server URL), scale (map scale of the contour picture, default 2257), search (largest
// shift tried, in screen pixels, default 12), run=1 (run once the layers load). Results go to window.align and OUT.

const [ImageryTileLayer, VectorTileLayer, ClassBreaksRenderer, Point, projectOperator, reactiveUtils, kernel] =
  await $arcgis.import([
    "@arcgis/core/layers/ImageryTileLayer.js",
    "@arcgis/core/layers/VectorTileLayer.js",
    "@arcgis/core/renderers/ClassBreaksRenderer.js",
    "@arcgis/core/geometry/Point.js",
    "@arcgis/core/geometry/operators/projectOperator.js",
    "@arcgis/core/core/reactiveUtils.js",
    "@arcgis/core/kernel.js",
  ]);

const params = new URLSearchParams(location.search);
const DATA = params.get("data") || "http://127.0.0.1:8794/";
// 1:2,257 is the contour service's own deepest level, and the terrain COG draws cleanly there; at 1:564 it drew strips
// of missing and repeated content (README).
const SCALE = Number(params.get("scale") || 2257);
const SEARCH = Number(params.get("search") || 12);
// Which check cell the contour picture is centred on. cells.json's steep edge is cell 0, in the COGs' last, partial
// column of 512-cell tiles (from column 24,064), where the SDK drew the terrain wrongly; cell 1 is well inside.
const AT = params.get("at") ?? "1";
const MAGENTA = [255, 0, 255];  // the contour lines
const CYAN = [0, 255, 255];     // the one cell drawn in the cell test
const BANDS = ["#2b83ba", "#fdae61"];
const R = 6378137;

const align = (window.align = { errors: [] });
window.addEventListener("error", (e) => align.errors.push(String(e.message)));
window.addEventListener("unhandledrejection", (e) => align.errors.push(String(e.reason?.message || e.reason)));
const out = document.getElementById("out");
const log = (s) => { out.textContent += `\n${s}`; };
const save = (name, body) => fetch(`/save/${name}`, { method: "POST", body });
const settle = async () => {
  await reactiveUtils.whenOnce(() => view.stationary);
  await new Promise((r) => setTimeout(r, 400));
  await reactiveUtils.whenOnce(() => !view.updating);
};

const transparent = { type: "simple-fill", color: [0, 0, 0, 0], outline: null };
const fill = (color) => ({ type: "simple-fill", color, outline: null });
// 10 m bands, matched to the index contours: 2 m bands on a steep slope put an edge every few pixels.
function bandRenderer() {
  const infos = [];
  for (let z = 1200, i = 0; z < 2400; z += 10, i++) infos.push({ minValue: z, maxValue: z + 10, symbol: fill(BANDS[i % 2]) });
  return new ClassBreaksRenderer({ field: "value", classBreakInfos: infos });
}
function onlyValue(v, half) {
  return new ClassBreaksRenderer({
    field: "value",
    classBreakInfos: [
      { minValue: -1e9, maxValue: v - half, symbol: transparent },
      { minValue: v - half, maxValue: v + half, symbol: fill([...CYAN, 1]) },
      { minValue: v + half, maxValue: 1e9, symbol: transparent },
    ],
  });
}

const spec = await (await fetch("cells.json")).json();
const view = document.getElementById("map");
view.basemap = "gray-vector";
await view.componentOnReady();
const slope = new ImageryTileLayer({ url: new URL("slope_percent.tif", DATA).href, interpolation: "nearest" });
const terrain = new ImageryTileLayer({ url: new URL("terrain_m.tif", DATA).href, interpolation: "nearest", visible: false });
const contours = new VectorTileLayer({ url: `${location.origin}/proxy/contours/VectorTileServer`, visible: false });
view.map.addMany([terrain, slope, contours]);
await Promise.all([slope.load(), terrain.load(), contours.load()]);
await projectOperator.load();
terrain.renderer = bandRenderer();
// The service stops at 1:2,257 (its level 17); the proxy adds levels 18-22 to its description so the picture can be drawn
// closer, from level 17 tiles overzoomed.
const slopeView = await view.whenLayerView(slope);
const lineLayers = contours.currentStyleInfo.style.layers.filter((l) => l.type === "line").map((l) => l.id);
for (const id of lineLayers) {
  const index = /index/i.test(id);
  contours.setPaintProperties(id, { "line-color": "#ff00ff", "line-width": 2, "line-opacity": index ? 1 : 0 });
}
align.sdk = { version: kernel.version, fullVersion: kernel.fullVersion, buildDate: kernel.buildDate };
align.layers = {
  slope_wkid: (slope.serviceRasterInfo ?? slope.rasterInfo).spatialReference?.wkid,
  view_wkid: view.spatialReference.wkid, contour_style_lines: lineLayers,
};
out.textContent = `SDK ${align.sdk.fullVersion || align.sdk.version}; COG wkid ${align.layers.slope_wkid}, view wkid ` +
  `${align.layers.view_wkid}; contour line layers: ${lineLayers.join(", ")}`;

const mercator = { wkid: 3857 };
const toGround = (y) => Math.cos(Math.atan(Math.sinh(y / R)));  // Web Mercator metres to ground metres at y
const offsets = (p, c) => {
  const k = toGround(p[1]);
  const at = (q) => { const dx = p[0] - q[0], dy = p[1] - q[1]; return { dx, dy, mercator: Math.hypot(dx, dy), ground: Math.hypot(dx, dy) * k }; };
  return { itrf08: at(c.itrf08), none: at(c.none) };
};

// 1. The SDK's own projection of each cell centre, with no transformation named.
function sdkProjection() {
  return spec.cells.map((c) => {
    const p = projectOperator.execute(new Point({ x: c.x, y: c.y, spatialReference: { wkid: 6341 } }), mercator);
    return offsets([p.x, p.y], c);
  });
}

// 2. Identify on a grid of Web Mercator points around both candidate centres: the centroid of the points that return
// the cell's own value is where identify places the cell.
async function identifyCell(c) {
  const xs = [c.itrf08[0], c.none[0]], ys = [c.itrf08[1], c.none[1]];
  const step = 0.06, pad = 0.6, pts = [];
  for (let x = Math.min(...xs) - pad; x <= Math.max(...xs) + pad; x += step)
    for (let y = Math.min(...ys) - pad; y <= Math.max(...ys) + pad; y += step) pts.push([x, y]);
  const hits = [];
  for (let i = 0; i < pts.length; i += 64) {
    const batch = pts.slice(i, i + 64);
    const values = await Promise.all(batch.map(([x, y]) =>
      slope.identify(new Point({ x, y, spatialReference: mercator })).then((r) => (r?.value ? r.value[0] : null))));
    values.forEach((v, j) => { if (v === c.slope_percent) hits.push(batch[j]); });
  }
  if (!hits.length) return { hits: 0 };
  const centre = [hits.reduce((s, h) => s + h[0], 0) / hits.length, hits.reduce((s, h) => s + h[1], 0) / hits.length];
  return { hits: hits.length, grid_step_m: step, centre, ...offsets(centre, c) };
}

// 3. Draw only the cell's value and find the drawn cell on screen.
const isMagenta = (d, i) => d[i] > 200 && d[i + 1] < 90 && d[i + 2] > 200;
const isCyan = (d, i) => d[i] < 60 && d[i + 1] > 200 && d[i + 2] > 200;
async function shot() {
  const w = view.view.width, h = view.view.height;
  const s = await view.takeScreenshot({ format: "png", width: w, height: h });
  return { w, h, d: s.data.data, url: s.dataUrl };
}
async function drawnCell(c, at = "midpoint") {
  slope.renderer = onlyValue(c.slope_percent, c.nearest_other_value / 2);
  const mid = at === "itrf08" ? c.itrf08 : [(c.itrf08[0] + c.none[0]) / 2, (c.itrf08[1] + c.none[1]) / 2];
  await view.goTo({ target: new Point({ x: mid[0], y: mid[1], spatialReference: mercator }), scale: 40 }, { animate: false });
  // The view can report itself settled before the new tiles are drawn: shoot again until the cell is whole (a 0.5 m
  // cell is about 35 px across at 1:40), at most five times.
  let n = 0, sx = 0, sy = 0, attempt = 0;
  for (; attempt < 5 && n < 900; attempt++) {
    await settle();
    await reactiveUtils.whenOnce(() => !slopeView.updating);
    await new Promise((r) => setTimeout(r, 1000 * attempt));
    const { w, h, d } = await shot();
    n = 0; sx = 0; sy = 0;
    for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) if (isCyan(d, (y * w + x) * 4)) { n++; sx += x; sy += y; }
  }
  if (!n) return { pixels: 0 };
  const p = view.toMap({ x: sx / n + 0.5, y: sy / n + 0.5 });
  const res = view.view.resolution;
  return { view_centred_on: at, pixels: n, shots: attempt, cell_side_px: Math.sqrt(n), resolution_m: res, centre: [p.x, p.y],
           ...offsets([p.x, p.y], c) };
}

// 4. The contour picture: the terrain COG in alternating 2 m bands, the contours on top. Band edges and contour lines
// should coincide; the shift that best lays the contour pixels on the band edges is the offset of one from the other.
async function contourOffset() {
  const e = spec.cells[Number(AT)].itrf08;
  await view.goTo({ target: new Point({ x: e[0], y: e[1], spatialReference: mercator }), scale: SCALE }, { animate: false });
  slope.visible = false;
  terrain.visible = true; contours.visible = false; await settle();
  const bands = await shot();
  terrain.visible = false; contours.visible = true; await settle();
  const lines = await shot();
  terrain.visible = true; await settle();
  const both = await shot();
  const { w, h } = bands;
  const label = new Int8Array(w * h).fill(-1);
  const rgb = BANDS.map((c) => [1, 3, 5].map((i) => parseInt(c.slice(i, i + 2), 16)));
  for (let i = 0; i < w * h; i++) {
    rgb.forEach((c, k) => { if (Math.max(...c.map((v, j) => Math.abs(v - bands.d[i * 4 + j]))) <= 2) label[i] = k; });
  }
  // Band edges, widened by 1 px: the contour interpolates between cell centres, the bands step at cell edges.
  const edge = new Uint8Array(w * h);
  for (let y = 0; y < h - 1; y++) for (let x = 0; x < w - 1; x++) {
    const i = y * w + x, a = label[i], r = label[i + 1], b = label[i + w];
    if (a >= 0 && ((r >= 0 && r !== a) || (b >= 0 && b !== a))) edge[i] = 1;
  }
  const near = new Uint8Array(w * h), W = 1;
  for (let y = W; y < h - W; y++) for (let x = W; x < w - W; x++) {
    if (!edge[y * w + x]) continue;
    for (let dy = -W; dy <= W; dy++) for (let dx = -W; dx <= W; dx++) near[(y + dy) * w + x + dx] = 1;
  }
  const line = [];
  for (let y = SEARCH; y < h - SEARCH; y++) for (let x = SEARCH; x < w - SEARCH; x++)
    if (isMagenta(lines.d, (y * w + x) * 4)) line.push(y * w + x);
  const grid = [];
  let best = { score: -1 };
  for (let sy = -SEARCH; sy <= SEARCH; sy++) for (let sx = -SEARCH; sx <= SEARCH; sx++) {
    let hit = 0;
    const off = sy * w + sx;
    for (const i of line) hit += near[i + off];
    const score = hit / line.length;
    grid.push([sx, sy, score]);
    if (score > best.score) best = { sx, sy, score };
  }
  const zero = grid.find(([sx, sy]) => sx === 0 && sy === 0)[2];
  const res = view.view.resolution, k = toGround(e[1]);
  // Shift s lays the contours on the band edges: the COG sits at contour + s (screen y runs down).
  const dx = best.sx * res, dy = -best.sy * res;
  const sh = spec.itrf08_minus_none_mercator_m;
  const expectNone = { sx: Math.round(-sh[0] / res), sy: Math.round(sh[1] / res) };
  const atNone = grid.find(([sx, sy]) => sx === expectNone.sx && sy === expectNone.sy)?.[2];
  const tag = `cell${AT}_1-${SCALE}`;
  await save(`contours_and_bands_${tag}.png`, await (await fetch(both.url)).blob());
  await save(`contours_only_${tag}.png`, await (await fetch(lines.url)).blob());
  await save(`bands_only_${tag}.png`, await (await fetch(bands.url)).blob());
  terrain.visible = false; contours.visible = false; slope.visible = true;
  return {
    centred_on_cell: Number(AT), scale: SCALE, resolution_m: res, contour_pixels: line.length, edge_pixels: edge.reduce((s, v) => s + v, 0),
    best_shift_px: [best.sx, best.sy], best_score: best.score, score_at_zero: zero,
    score_at_untransformed_offset: atNone, untransformed_offset_px: [expectNone.sx, expectNone.sy],
    cog_minus_contours_mercator_m: [dx, dy], cog_minus_contours_ground_m: Math.hypot(dx, dy) * k,
  };
}

// 5. The published contours against the terrain COG by value: each vertex of the hosted 2 m contours
// (contour_vertices.json) should sit where the terrain is a multiple of 2 m. The terrain is identified at each vertex
// moved by a shift s; the s that brings the values closest to a multiple of 2 m is where the COG sits relative to the
// contours (COG minus contours). Identify reads full-resolution cells, so this does not depend on drawing.
async function contourVertices() {
  const { vertices } = await (await fetch("contour_vertices.json")).json();
  const d = [spec.cells[0].none[0] - spec.cells[0].itrf08[0], spec.cells[0].none[1] - spec.cells[0].itrf08[1]];
  const residual = async ([sx, sy]) => {
    const r = [];
    for (let i = 0; i < vertices.length; i += 64) {
      const batch = vertices.slice(i, i + 64);
      const values = await Promise.all(batch.map((v) => terrain.identify(
        new Point({ x: v.x + sx, y: v.y + sy, spatialReference: mercator })).then((x) => (x?.value ? x.value[0] : null))));
      for (const t of values) if (t !== null) r.push(Math.abs(t - 2 * Math.round(t / 2)));
    }
    r.sort((a, b) => a - b);
    return { shift: [sx, sy], n: r.length, median_m: r[r.length >> 1], mean_m: r.reduce((s, x) => s + x, 0) / r.length };
  };
  const grid = [];
  const STEP = 0.35, K = 5;
  for (let i = -K; i <= K; i++) for (let j = -K; j <= K; j++) grid.push(await residual([i * STEP, j * STEP]));
  const coarse = grid.reduce((a, b) => (b.mean_m < a.mean_m ? b : a));
  // then a finer grid around the coarse best
  const FINE = 0.07, KF = 4, fine = [];
  for (let i = -KF; i <= KF; i++) for (let j = -KF; j <= KF; j++)
    fine.push(await residual([coarse.shift[0] + i * FINE, coarse.shift[1] + j * FINE]));
  const best = fine.reduce((a, b) => (b.mean_m < a.mean_m ? b : a));
  const k = toGround(vertices[0].y);
  return {
    vertices: vertices.length, grid_step_m: STEP, grid_half_width_m: K * STEP, fine_step_m: FINE, coarse_best: coarse,
    fine,
    at_zero: await residual([0, 0]),
    // where the contours would read the COG if one of the two were placed with no transformation
    at_plus_untransformed: await residual(d), at_minus_untransformed: await residual([-d[0], -d[1]]),
    best, best_shift_ground_m: Math.hypot(...best.shift) * k, grid,
  };
}

async function run() {
  out.textContent = `SDK ${align.sdk.fullVersion || align.sdk.version}`;
  align.sdk_projection = sdkProjection();
  log(`SDK projection (no transformation named): ${align.sdk_projection.map((o) => o.itrf08.ground.toFixed(3)).join(", ")} m from ITRF08`);
  align.cells = [];
  for (const c of spec.cells) {
    const identify = await identifyCell(c);
    let drawn = await drawnCell(c);
    const partial = drawn.pixels < 900 ? drawn : undefined;
    // A partly drawn cell is read again with the view centred on the ITRF08 position instead; both are kept.
    if (partial) drawn = await drawnCell(c, "itrf08");
    align.cells.push({ col: c.col, row: c.row, slope_percent: c.slope_percent, identify, drawn, partial_reading: partial });
    log(`cell ${c.col},${c.row}: identify ${identify.itrf08?.ground.toFixed(3)} m from ITRF08, ` +
        `${identify.none?.ground.toFixed(3)} from none; drawn ${drawn.itrf08?.ground.toFixed(3)} / ${drawn.none?.ground.toFixed(3)}`);
  }
  align.contour_vertices = await contourVertices();
  const cv = align.contour_vertices;
  log(`contour vertices (${cv.vertices}): mean distance from a 2 m multiple ${cv.at_zero.mean_m.toFixed(3)} m as placed, ` +
      `${cv.at_plus_untransformed.mean_m.toFixed(3)} / ${cv.at_minus_untransformed.mean_m.toFixed(3)} m moved by the ` +
      `untransformed offset; best shift ${cv.best.shift.map((v) => v.toFixed(2))} m (${cv.best.mean_m.toFixed(3)})`);
  align.contours = await contourOffset();
  log(`contours: best shift ${align.contours.best_shift_px} px (score ${align.contours.best_score.toFixed(3)}, ` +
      `at zero ${align.contours.score_at_zero.toFixed(3)}); COG minus contours ${align.contours.cog_minus_contours_ground_m.toFixed(3)} m on the ground`);
  slope.renderer = null;
  await save(`results_cell${AT}_1-${SCALE}.json`, JSON.stringify(align, null, 1));
  align.done = true;
  return align;
}
document.getElementById("run").addEventListener("click", run);
align.run = run;
align.ready = true;
if (params.get("run") === "1") await run();
