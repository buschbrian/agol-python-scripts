// Zoom check: does a vector tile layer keep drawing past its service's last level (17, 1:2,257)?
// Query parameters: layer (item id) or webmap (web map id, every layer in it), mode, center (lon,lat), scale.
// mode:
//   item       the layer as Layer.fromPortalItem gives it (the item's styles/root.json)
//   maxscale0  the same, with maxScale set to 0 after load
//   tiles      the item's style with its source rewritten from "url" (the VectorTileServer) to a "tiles" template,
//              given to a new VectorTileLayer
//   patch      the item (or web map) loaded as usual, with each item's styles/root.json rewritten that way in flight by
//              a request interceptor: what ArcGIS Online would serve if the resource were replaced. Nothing is written.
//   svcmax0    the item (or web map) as usual, with the VectorTileServer JSON's maxScale set to 0 in flight
//   svclods    the same, with the VectorTileServer JSON's tileInfo LODs extended to level 22 in flight (maxScale kept)
// The state goes to window.zoom (ready once the view has settled).

const [esriConfig, esriId, Map, WebMap, MapView, Layer, VectorTileLayer, reactiveUtils] = await $arcgis.import([
  "@arcgis/core/config.js",
  "@arcgis/core/identity/IdentityManager.js",
  "@arcgis/core/Map.js",
  "@arcgis/core/WebMap.js",
  "@arcgis/core/views/MapView.js",
  "@arcgis/core/layers/Layer.js",
  "@arcgis/core/layers/VectorTileLayer.js",
  "@arcgis/core/core/reactiveUtils.js",
]);
const { default: token } = await import(`./token.js?${Date.now()}`);

const zoom = (window.zoom = { errors: [], ready: false, tileRequests: [] });
window.addEventListener("error", (e) => zoom.errors.push(String(e.message)));
window.addEventListener("unhandledrejection", (e) => zoom.errors.push(String(e.reason?.message || e.reason)));
const out = document.getElementById("out");
const log = (s) => { out.textContent += `${s}\n`; };

for (const server of ["https://www.arcgis.com/sharing/rest", "https://tiles.arcgis.com/tiles/XRrSFvEwSsReIxuA/arcgis/rest/services"]) {
  esriId.registerToken({ server, token: token.token, expires: token.expires * 1000, ssl: true });
}
new PerformanceObserver((list) => {
  for (const e of list.getEntries()) {
    // The city's own services only, not the basemap's.
    const m = e.name.match(/XRrSFvEwSsReIxuA\/arcgis\/rest\/services\/(\w+)\/VectorTileServer\/tile\/(\d+)\/(\d+)\/(\d+)/);
    if (m) zoom.tileRequests.push(`${m[1].replace("_2023_lidar_planning_estimate", "")} ${m[2]}/${m[3]}/${m[4]} ${e.responseStatus}`);
  }
}).observe({ type: "resource", buffered: true });

const params = new URLSearchParams(location.search);
const mode = params.get("mode") || "item";
const tilesSource = (source) => {
  source.tiles = [`${source.url}/tile/{z}/{y}/{x}.pbf`];
  delete source.url;
};
if (mode === "patch") {
  esriConfig.request.interceptors.push({
    urls: /\/content\/items\/\w+\/resources\/styles\/root\.json/,
    after(response) {
      for (const source of Object.values(response.data.sources)) if (source.url) tilesSource(source);
      zoom.patched = (zoom.patched || 0) + 1;
    },
  });
}
if (mode === "svcmax0" || mode === "svclods") {
  esriConfig.request.interceptors.push({
    urls: /\/VectorTileServer\/?$/,
    after(response) {
      const d = response.data;
      if (!d?.tileInfo) return;
      if (mode === "svcmax0") d.maxScale = 0;
      else {
        while (d.tileInfo.lods.at(-1).level < 22) {
          const last = d.tileInfo.lods.at(-1);
          d.tileInfo.lods.push({ level: last.level + 1, resolution: last.resolution / 2, scale: last.scale / 2 });
        }
      }
      zoom.patched = (zoom.patched || 0) + 1;
    },
  });
}
let map, layers;
if (params.get("webmap")) {
  map = new WebMap({ portalItem: { id: params.get("webmap") } });
  await map.load();
  await Promise.all(map.allLayers.map((l) => l.load().catch(() => null)));
  layers = map.allLayers.filter((l) => l.type === "vector-tile" && !map.basemap.baseLayers.includes(l)
                                     && !map.basemap.referenceLayers.includes(l)).toArray();
  document.getElementById("title").textContent = `${map.portalItem.title} [${mode}]`;
} else {
  let layer = await Layer.fromPortalItem({ portalItem: { id: params.get("layer") } });
  await layer.load();
  if (mode === "maxscale0") layer.maxScale = 0;
  if (mode === "tiles") {
    const style = structuredClone(layer.currentStyleInfo.style);
    Object.values(style.sources).forEach(tilesSource);
    layer = new VectorTileLayer({ style, title: `${layer.title} (tiles source)` });
    await layer.load();
  }
  layers = [layer];
  map = new Map({ basemap: "gray-vector", layers });
  document.getElementById("title").textContent = `${layer.title} [${mode}]`;
}

const view = new MapView({ container: "view", map });
await view.when();
const [x, y] = (params.get("center") || "-111.8452,40.6876").split(",").map(Number);
await view.goTo({ center: [x, y], scale: Number(params.get("scale") || 1128) }, { animate: false });
await reactiveUtils.whenOnce(() => !view.updating);
await new Promise((r) => setTimeout(r, 1000));
Object.assign(zoom, { mode, scale: view.scale, zoom: view.zoom, layers: layers.map((layer) => {
  const lv = view.layerViews.find((v) => v.layer === layer);
  return {
    title: layer.title, minScale: layer.minScale, maxScale: layer.maxScale, styleUrl: layer.currentStyleInfo?.styleUrl,
    lods: `${layer.tileInfo?.lods[0]?.level}-${layer.tileInfo?.lods.at(-1)?.level}`,
    sources: Object.values(layer.currentStyleInfo?.style?.sources || {}).map((s) => (s.url ? "url" : "tiles") + ` maxzoom ${s.maxzoom}`),
    suspended: lv?.suspended, visibleAtCurrentScale: layer.visibleAtCurrentScale, loadError: layer.loadError?.message,
  };
}) });
log(JSON.stringify({ ...zoom, tileRequests: zoom.tileRequests.slice(-8) }, null, 1));
zoom.ready = true;
