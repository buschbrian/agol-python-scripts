// COG drawing check: does the ArcGIS Maps SDK draw each COG cell in the colour its value calls for? For each COG, map
// scale, place (places.json) and interpolation, the COG is drawn in alternating two-colour bands sized to the values in
// view, and sampled pixels' drawn colours are compared with identify, which reads the full-resolution cell exactly
// (cog-alignment). Only "interior" pixels count: those whose 3 x 3 neighbourhood, one drawn-level cell apart (the
// overview cell at that scale, or 0.5 m), identifies into one band, so averaging in overviews and bilinear resampling
// cannot fairly change their colour. The view is shot when it reports itself settled and again later, to catch
// transient drawing.
// Query parameters: data (data server URL), mode (sweep, the default, or one), and for mode=one: cog, scale, place,
// interp. run=1 starts at once. Results go to window.check and OUT (sweep.json, or one_<config>.json).

const [ImageryTileLayer, ClassBreaksRenderer, Point, projectOperator, reactiveUtils, kernel] = await $arcgis.import([
  "@arcgis/core/layers/ImageryTileLayer.js",
  "@arcgis/core/renderers/ClassBreaksRenderer.js",
  "@arcgis/core/geometry/Point.js",
  "@arcgis/core/geometry/operators/projectOperator.js",
  "@arcgis/core/core/reactiveUtils.js",
  "@arcgis/core/kernel.js",
]);

const params = new URLSearchParams(location.search);
const DATA = params.get("data") || "http://127.0.0.1:8796/";
const MODE = params.get("mode") || "sweep";
const COGS = ["terrain_m", "slope_percent", "chm_m", "hillshade"];
// The view's own levels (the basemap's), so the scale asked for is the scale drawn: zoom 22, 19, 17, 15 and 13.
const SCALES = [70.5310735, 564.248588, 2256.994353, 9027.977411, 36111.909643];
const INTERPS = ["nearest", "bilinear"];
const N = 150, TRIES = 1200, LATER_MS = 3000, LATEST_MS = 15000;
const COLORS = [[0, 90, 255], [255, 140, 0]];
const R = 6378137, CELL = 0.5, TILE = 512, X0 = 422149, Y0 = 4507383;  // the COGs' grid (EPSG:6341)
const mercator = { wkid: 3857 };

const check = (window.check = { errors: [], configs: [] });
window.addEventListener("error", (e) => check.errors.push(String(e.message)));
window.addEventListener("unhandledrejection", (e) => check.errors.push(String(e.reason?.message || e.reason)));
const out = document.getElementById("out");
const log = (s) => { out.textContent += `\n${s}`; };
const save = (name, body) => fetch(`/save/${name}`, { method: "POST", body });
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const toGround = (y) => Math.cos(Math.atan(Math.sinh(y / R)));

const { places } = await (await fetch("places.json")).json();
const view = document.getElementById("map");
view.basemap = "gray-vector";
await view.componentOnReady();
await projectOperator.load();
const wanted = MODE === "one" ? [params.get("cog")] : COGS;
const layers = Object.fromEntries(wanted.map((name) =>
  [name, new ImageryTileLayer({ url: new URL(`${name}.tif`, DATA).href, visible: false })]));
view.map.addMany(Object.values(layers));
await Promise.all(Object.values(layers).map((l) => l.load()));
check.sdk = { version: kernel.version, fullVersion: kernel.fullVersion, buildDate: kernel.buildDate };
out.textContent = `SDK ${check.sdk.fullVersion || check.sdk.version}`;

async function values(layer, pts) {
  return Promise.all(pts.map(([x, y]) => layer.identify(new Point({ x, y, spatialReference: mercator }))
    .then((r) => (r?.value ? r.value[0] : null))));
}

// Bands: about six across the 10th-90th percentile of values on a 7 x 7 grid over the coming view.
function bands(vals) {
  const v = vals.filter((x) => x !== null).sort((a, b) => a - b);
  if (v.length < 10) return null;
  const q = (p) => v[Math.min(v.length - 1, Math.floor(p * v.length))];
  let lo = q(0.1), hi = q(0.9);
  if (hi - lo <= 0) { lo = v[0]; hi = v[v.length - 1]; }
  if (hi - lo <= 0) return null;
  const step = (hi - lo) / 6, base = lo, first = -10, last = 16;
  const index = (x) => { const i = Math.floor((x - base) / step); return i >= first && i < last ? i : null; };
  const renderer = new ClassBreaksRenderer({
    field: "value",
    classBreakInfos: Array.from({ length: last - first }, (_, k) => {
      const i = first + k;
      return { minValue: base + i * step, maxValue: base + (i + 1) * step,
               symbol: { type: "simple-fill", color: [...COLORS[((i % 2) + 2) % 2], 1], outline: null } };
    }),
  });
  return { base, step, index, renderer };
}

async function settle(lv) {
  await reactiveUtils.whenOnce(() => view.stationary);
  await sleep(300);
  await reactiveUtils.whenOnce(() => !view.updating && !lv.updating);
}
async function shot() {
  const w = view.view.width, h = view.view.height;
  const s = await view.takeScreenshot({ format: "png", width: w, height: h });
  return { w, h, d: s.data.data, url: s.dataUrl };
}
const parity = (s, x, y) => {
  const i = (y * s.w + x) * 4;
  for (const [k, c] of COLORS.entries()) if (c.every((v, j) => Math.abs(v - s.d[i + j]) <= 3)) return k;
  return null;
};

async function measure(cog, scale, place, interp, laterShots) {
  const layer = layers[cog];
  for (const l of Object.values(layers)) l.visible = l === layer;
  layer.interpolation = interp;
  const lv = await view.whenLayerView(layer);
  const [cx, cy] = place.mercator;
  const res = scale * 0.0254 / 96, w = view.view.width, h = view.view.height;
  const pts = [];
  for (let i = 0; i < 7; i++) for (let j = 0; j < 7; j++)
    pts.push([cx + ((i + 0.5) / 7 - 0.5) * w * res, cy + ((j + 0.5) / 7 - 0.5) * h * res]);
  const b = bands(await values(layer, pts));
  const config = { cog, scale: Math.round(scale), place: place.name, interp };
  if (!b) return { ...config, skipped: "no spread of values in view" };
  layer.renderer = b.renderer;   // before the move, so the view draws once
  const t0 = performance.now();
  await view.goTo({ target: new Point({ x: cx, y: cy, spatialReference: mercator }), scale }, { animate: false });
  await settle(lv);
  const settledMs = Math.round(performance.now() - t0);
  const shots = [await shot()];
  for (const ms of laterShots) { await sleep(ms); shots.push(await shot()); }

  // The drawn level's cell, conservatively: the coarsest overview no finer than a screen pixel.
  const cellMerc = CELL / toGround(cy);
  const L = cellMerc * 2 ** Math.max(0, Math.ceil(Math.log2(view.view.resolution / cellMerc)));
  let seed = 12345, tries = 0, coloured = 0, rawWrong = 0;
  const rnd = () => (seed = (seed * 16807) % 2147483647) / 2147483647;
  const interior = [];
  while (interior.length < N && tries < TRIES) {
    const batch = [];
    while (batch.length < 16 && tries < TRIES) {
      tries++;
      const x = Math.floor(rnd() * w), y = Math.floor(rnd() * h);
      const drawn = parity(shots[0], x, y);
      if (drawn !== null) batch.push({ x, y, drawn, p: view.toMap({ x: x + 0.5, y: y + 0.5 }) });
    }
    await Promise.all(batch.map(async (c) => {
      const ring = [];
      for (const dx of [0, -L, L]) for (const dy of [0, -L, L]) ring.push([c.p.x + dx, c.p.y + dy]);
      const v = await values(layer, ring);
      if (v[0] === null) return;
      const i0 = b.index(v[0]);
      if (i0 === null) return;
      coloured++;
      const want = ((i0 % 2) + 2) % 2;
      if (want !== c.drawn) rawWrong++;
      if (v.every((x) => x !== null && b.index(x) === i0) && interior.length < N) interior.push({ ...c, value: v[0], want });
    }));
  }
  const wrong = shots.map((s) => interior.filter((c) => parity(s, c.x, c.y) !== c.want));
  const where = wrong[wrong.length - 1].slice(0, 40).map((c) => {
    const u = projectOperator.execute(c.p, { wkid: 6341 });
    const col = Math.floor((u.x - X0) / CELL), row = Math.floor((Y0 - u.y) / CELL);
    return { px: [c.x, c.y], col, row, tile: [Math.floor(col / TILE), Math.floor(row / TILE)], value: c.value,
             want: c.want, drawn: parity(shots[shots.length - 1], c.x, c.y) };
  });
  const result = {
    ...config, zoom: view.zoom, resolution_m: view.view.resolution, check_spacing_m: L, settled_ms: settledMs,
    band_step: b.step, interior: interior.length, coloured_sampled: coloured, wrong_any_sampled: rawWrong,
    wrong_interior: wrong.map((x) => x.length), shots_ms: [0, ...laterShots.map((_, i) => laterShots.slice(0, i + 1).reduce((a, c) => a + c, 0))],
    wrong_where: where,
  };
  if (wrong.some((x) => x.length)) {
    const tag = `${cog}_1-${config.scale}_${place.name}_${interp}`;
    await save(`wrong_${tag}.png`, await (await fetch(shots[shots.length - 1].url)).blob());
    if (wrong[0].length && shots.length > 1) await save(`wrong_${tag}_first.png`, await (await fetch(shots[0].url)).blob());
  }
  return result;
}

async function sweep() {
  for (const cog of COGS) for (const interp of INTERPS) for (const scale of SCALES) {
    // The smallest scale shows the whole city from any place: run it once.
    for (const place of scale > 20000 ? places.slice(0, 1) : places) {
      const r = await measure(cog, scale, place, interp, [LATER_MS]);
      check.configs.push(r);
      log(`${cog} 1:${Math.round(scale)} ${place.name} ${interp}: ` +
          (r.skipped ? r.skipped : `${r.wrong_interior.join(" -> ")} of ${r.interior} wrong (any: ${r.wrong_any_sampled}/${r.coloured_sampled})`));
      await save("sweep.json", JSON.stringify(check, null, 1));
    }
  }
  check.done = true;
}

// One configuration on a fresh page. warm=full first draws the layer at its full extent (as the COG trial did) before
// going to the place; warm=place first goes straight to the place with the layer's default renderer; again=1 then
// moves the view one screen east and back and measures again.
async function one() {
  const cog = params.get("cog"), interp = params.get("interp") || "nearest", warm = params.get("warm") || "none";
  const scale = SCALES.find((s) => Math.round(s) === Number(params.get("scale"))) ?? Number(params.get("scale"));
  const place = places.find((p) => p.name === params.get("place"));
  if (warm === "full" || warm === "place" || warm === "fullbands") {
    // place: straight to the place with the layer's own (default) renderer, as a shared link would open, then bands;
    // fullbands: the full extent first, but already with a class breaks renderer (10 m bands)
    const layer = layers[cog];
    layer.visible = true;
    layer.interpolation = interp;
    if (warm === "fullbands") {
      layer.renderer = new ClassBreaksRenderer({ field: "value", classBreakInfos: Array.from({ length: 120 }, (_, i) => ({
        minValue: 1200 + 10 * i, maxValue: 1210 + 10 * i,
        symbol: { type: "simple-fill", color: [...COLORS[i % 2], 1], outline: null } })) });
    }
    await view.goTo(warm !== "place" ? layer.fullExtent
      : { target: new Point({ x: place.mercator[0], y: place.mercator[1], spatialReference: mercator }), scale },
    { animate: false });
    await settle(await view.whenLayerView(layer));
    if (warm === "place") await save(`first_default_${cog}_1-${Math.round(scale)}_${place.name}.png`,
      await (await fetch((await shot()).url)).blob());
  }
  const r = await measure(cog, scale, place, interp, [LATER_MS, LATEST_MS - LATER_MS]);
  check.configs.push({ ...r, warm });
  log(`${r.cog} 1:${r.scale} ${r.place} ${r.interp} warm=${warm}: ${r.wrong_interior?.join(" -> ")} of ${r.interior} wrong at 0, 3, 15 s`);
  if (params.get("again") === "1") {
    const lv = await view.whenLayerView(layers[cog]);
    await view.goTo(new Point({ x: place.mercator[0] + view.view.width * view.view.resolution, y: place.mercator[1],
                                spatialReference: mercator }), { animate: false });
    await settle(lv);
    const r2 = await measure(cog, scale, place, interp, [LATER_MS]);
    check.configs.push({ ...r2, warm, after: "moved one screen east and back" });
    log(`  after moving away and back: ${r2.wrong_interior?.join(" -> ")} of ${r2.interior} wrong`);
  }
  const tag = `${r.cog}_1-${r.scale}_${r.place}_${r.interp}_warm-${warm}${params.get("again") === "1" ? "_again" : ""}`;
  await save(`one_${tag}.json`, JSON.stringify(check, null, 1));
  check.done = true;
}

check.ready = true;
check.run = MODE === "one" ? one : sweep;
if (params.get("run") === "1") await check.run();
