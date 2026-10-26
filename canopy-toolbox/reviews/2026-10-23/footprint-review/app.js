// Footprint review page: one item at a time, keyboard first. Answers go to the local server, which checks and saves them.
"use strict";

const QUEUES = {
  candidates: {
    question: "Is this a building the county layer is missing?",
    answers: [
      ["ACCEPT", "Accept: a separate building"],
      ["PART_OF_EXISTING", "Part of existing: addition, porch or eave of the county building"],
      ["VEHICLE", "Not a building: RV, trailer or vehicle"],
      ["REJECT", "Not a building: tree or other"],
      ["UNSURE", "Unsure"],
    ],
  },
  county: {
    question: "This county footprint has little or no 2023 LiDAR roof. What is there?",
    answers: [
      ["DEMOLISHED", "Demolished: gone"],
      ["STILL_THERE", "Still there: under trees or too small for the LiDAR"],
      ["MISPLACED", "Misplaced: the building is there, the outline is off"],
      ["UNSURE", "Unsure"],
    ],
  },
  pairs: {
    question: "Magenta is the county outline (weak 2023 roof); red is what the LiDAR sees beside it. What is the red piece?",
    answers: [
      ["OFFSET", "The same building: the county outline is off or the wrong shape"],
      ["PART_OF_EXISTING", "Part of it: an addition, porch or carport of the county building"],
      ["BOTH_REAL", "A separate building: both are real"],
      ["REBUILT", "Its replacement: the county building is gone"],
      ["NOT_A_BUILDING", "Not a building: RV, trailer, vehicle or tree"],
      ["UNSURE", "Unsure"],
    ],
  },
  newbuild: {
    question: "Does today's imagery show a building in the yellow box that the 2023 LiDAR doesn't?",
    answers: [
      ["NEW_BUILDING", "New building: in the imagery, not in the 2023 LiDAR"],
      ["NO_BUILDING", "No building here"],
      ["UNSURE", "Unsure"],
    ],
  },
  models: {
    question: "The 3D buildings modelled this county footprint without a detailed (roofer LoD 2.2) roof. What is there?",
    answers: [
      ["SIMPLE_OK", "Building there; the simple block or roof is good enough"],
      ["NEEDS_ROOF", "Building there; its roof deserves a better model"],
      ["GONE", "Gone: no building in the 2023 LiDAR (demolished or never built)"],
      ["OUTLINE_WRONG", "Building there, but the county outline is off or the wrong shape"],
      ["UNDER_TREES", "Building there, hidden under trees"],
      ["UNSURE", "Unsure"],
    ],
  },
  trees: {
    question: "Red is one CFTree tree model (crown outline; the dot is its inferred trunk). Is it one tree?",
    others: "other tree models",
    answers: [
      ["ONE_TREE", "One tree, and the model fits it"],
      ["MERGED", "Several trees merged into one model (including low or dead ones beside it)"],
      ["PART_OF_TREE", "Only part of a tree (the rest is another model)"],
      ["NOT_A_TREE", "Not a tree: roof, wire, pole or other"],
      ["SHAPE_WRONG", "A tree, but the crown or trunk is badly off"],
      ["SHRUBS", "Low shrubs or a hedge, not a tree"],
      ["BRUSH", "Brush or a scrub thicket taken as one tree"],
      ["TREE_WITH_ROOF", "A tree, but the model takes in part of a building roof"],
      ["UNSURE", "Unsure"],
    ],
  },
  tree_seams: {
    question: "Red and magenta are models from two neighbouring processing tiles that overlap. What are they?",
    others: "other tree models", focus: "the other tile's model",
    answers: [
      ["SAME_TREE", "The same whole tree twice: keep one"],
      ["SPLIT_TREE", "One tree cut in two at the tile edge"],
      ["SEPARATE_TREES", "Two separate trees"],
      ["NOT_A_TREE", "Not a tree (either one)"],
      ["UNSURE", "Unsure"],
    ],
  },
  tree_rejects: {
    question: "CFTree could not build a model here (the dot is the segment's highest return). Is there a tree?",
    others: "tree models",
    answers: [
      ["MISSED_TREE", "A tree the models are missing"],
      ["NOT_A_TREE", "Not a tree, or already covered by a neighbouring model"],
      ["UNSURE", "Unsure"],
    ],
  },
};
const GROUP_NAMES = { large_tall: "Large and tall", detached: "Detached", attached: "Against a county building (other)",
                      attached_sample: "Sample: answer these first", attached_eyes: "Needs eyes (80 m² or more, or doubtful county building)",
                      attached_lower: "Lower roof against a county building", attached_same_roof: "Corner or edge of a county roof",
                      explained_by_alignment: "Explained by realigning the county outline",
                      low_roof: "No 2023 roof", hint: "Hint", under_10: "County roof under 10%",
                      "10_50": "County roof 10-50%", "50_80": "County roof 50-80%",
                      no_model: "No 3D model at all", lod12: "LOD1.2 block fallback", lod20: "LOD2.0 roof fallback",
                      sample: "Sample: answer these first", merged: "Many treetops inside (merged?)",
                      over_roof: "Trunk inside a county footprint", seam: "Tile seam", no_terrain: "No terrain beneath",
                      no_trunk: "No valid trunk" };

const $ = (id) => document.getElementById(id);
let index = null, byId = {}, answers = {}, list = [], pos = 0, current = null, map = null, layers = null, homeView = null;
const cache = new Map();   // bundle file -> promise of {item id: detail}

function store(key, value) { try { if (value === undefined) return localStorage.getItem(key); localStorage.setItem(key, value); } catch (e) { return null; } }

function status(text, error) { const s = $("status"); s.textContent = text || ""; s.className = error ? "error" : ""; }

const NO_SERVER = "Can't reach the review server. Start it with footprint_review.bat serve and keep its window open, then reload.";

async function getJSON(url) {
  let r;
  try { r = await fetch(url, { cache: "no-store" }); } catch (e) { throw new Error(url.startsWith("/") ? NO_SERVER : e.message); }
  if (!r.ok) throw new Error(`${url}: ${r.status}`);
  return r.json();
}

function detail(id) {
  const file = byId[id].bundle;
  if (!cache.has(file)) {
    cache.set(file, getJSON(`/data/bundles/${file}`));
    if (cache.size > 4) cache.delete(cache.keys().next().value);
  }
  return cache.get(file).then((b) => b[id]);
}

function buildList() {
  const q = $("queue").value, g = $("group").value, show = $("show").value;
  list = index.items.filter((it) => it.queue === q && (!g || it.group === g) &&
    (show === "all" || (show === "open" ? !answers[it.id] : !!answers[it.id])));
}

function refreshGroups() {
  const q = $("queue").value, sel = $("group"), keep = sel.value;
  const groups = [...new Set(index.items.filter((it) => it.queue === q).map((it) => it.group))];
  sel.innerHTML = '<option value="">All</option>' + groups.map((g) => {
    const n = index.items.filter((it) => it.queue === q && it.group === g).length;
    return `<option value="${g}">${GROUP_NAMES[g] || g} (${n})</option>`; }).join("");
  sel.value = groups.includes(keep) ? keep : "";
}

function progress() {
  const q = $("queue").value, all = index.items.filter((it) => it.queue === q), done = all.filter((it) => answers[it.id]).length;
  $("progress-bar").style.width = all.length ? `${(100 * done) / all.length}%` : "0";
  $("progress-text").textContent = `${done} of ${all.length} answered in this queue`;
  $("position").textContent = list.length ? `${pos + 1} / ${list.length}` : "0 / 0";
}

function zoomFor(metres, lat, px) { return Math.log2((156543.03392 * Math.cos((lat * Math.PI) / 180) * px) / metres); }

function centreOf(rings) {
  let s = [Infinity, Infinity, -Infinity, -Infinity];
  for (const ring of rings) for (const [la, lo] of ring) s = [Math.min(s[0], la), Math.min(s[1], lo), Math.max(s[2], la), Math.max(s[3], lo)];
  return [(s[0] + s[2]) / 2, (s[1] + s[3]) / 2];
}

function drawMap(d) {
  layers.clearLayers();
  for (const ring of d.county_ll) L.polygon(ring, { color: "#ffffff", weight: 1.5, fill: false }).addTo(layers);
  for (const ring of d.cand_ll) L.polygon(ring, { color: "#00d5ff", weight: 1.5, dashArray: "4 4", fill: false }).addTo(layers);
  let focus = d.outline_ll;
  if (d.hint_ll) {
    for (const ring of d.hint_ll) L.polygon(ring, { color: "#ffd400", weight: 2.5, dashArray: "6 4", fill: false }).addTo(layers);
    focus = d.hint_ll;
  }
  for (const ring of d.focus_ll || []) L.polygon(ring, { color: "#ff3df5", weight: 3, fill: false }).addTo(layers);
  for (const ring of d.outline_ll) L.polygon(ring, { color: "#ff2a2a", weight: 2.5, fill: false }).addTo(layers);
  if (d.focus_ll && d.focus_ll.length) focus = d.focus_ll.concat(d.outline_ll);
  map.invalidateSize({ animate: false });
  const c = centreOf(focus), px = $("map").clientWidth || 600;
  homeView = [c, Math.min(21, zoomFor(d.chip.metres, c[0], px))];
  map.setView(homeView[0], homeView[1], { animate: false });
  imageryDate(c);
}

function svgPoly(rings, cls) {
  return rings.map((r) => `<polygon class="${cls}" points="${r.map((p) => p.join(",")).join(" ")}"/>`).join("");
}

function drawChip(d) {
  $("chip").src = d.chip.uri;
  const svg = $("chip-svg"), n = d.chip.size;
  svg.setAttribute("viewBox", `0 0 ${n} ${n}`);
  const w = Math.max(0.6, n / 300);
  svg.innerHTML = `<style>polygon{fill:none;vector-effect:non-scaling-stroke}.county{stroke:#fff;stroke-width:1.5}
    .cand{stroke:#00d5ff;stroke-width:1.5;stroke-dasharray:4 4}.item{stroke:#ff2a2a;stroke-width:2.5}
    .hint{stroke:#ffd400;stroke-width:2.5;stroke-dasharray:6 4}.focus{stroke:#ff3df5;stroke-width:3}</style>` +
    svgPoly(d.county_px, "county") + svgPoly(d.cand_px, "cand") + svgPoly(d.hint_px || [], "hint") +
    svgPoly(d.focus_px || [], "focus") + svgPoly(d.outline_px, "item");
  $("chip-metres").textContent = `${Math.round(d.chip.metres)} m across`;
  $("legend-others").textContent = QUEUES[d.queue].others || "other candidates";
  $("legend-focus").textContent = QUEUES[d.queue].focus || "county outline in question";
  $("profile-wrap").hidden = !d.profile;
  if (d.profile) $("profile").src = d.profile; else $("profile").removeAttribute("src");
}

function drawSide(d) {
  const q = QUEUES[d.queue], a = answers[d.id];
  $("item-id").textContent = d.id;
  $("group-badge").textContent = GROUP_NAMES[d.group] || d.group;
  $("question").textContent = q.question;
  const { "Likely type (a guess)": guess, ...rest } = d.facts;
  $("guess").hidden = !guess;
  $("guess").innerHTML = guess ? `<span class="small">Likely type (a guess from size, height, roof and parcel):</span><br>${guess}` : "";
  const earlier = (d.related || []).filter((id) => answers[id]).map((id) => [`Your answer on ${id}`, answers[id].ANSWER]);
  $("facts").innerHTML = Object.entries(rest).concat(earlier).map(([k, v]) => `<dt>${k}</dt><dd>${v ?? "—"}</dd>`).join("");
  $("answers").innerHTML = q.answers.map(([code, text], i) =>
    `<button data-code="${code}" class="${a && a.ANSWER === code ? "chosen" : ""}"><kbd>${i + 1}</kbd> ${text}</button>`).join("");
  for (const b of $("answers").querySelectorAll("button")) b.onclick = () => save(b.dataset.code);
  $("note").value = a ? a.NOTE || "" : "";
  status(a ? `Answered ${a.ANSWER} by ${a.REVIEWER} on ${a.REVIEW_DATE}` : "");
}

async function show(i) {
  progress();
  if (!list.length) {
    current = null; layers.clearLayers(); $("chip").removeAttribute("src"); $("chip-svg").innerHTML = "";
    $("item-id").textContent = "—"; $("facts").innerHTML = ""; $("answers").innerHTML = "";
    status("Nothing left to show here. Pick another queue or Show: All.");
    return;
  }
  pos = Math.max(0, Math.min(i, list.length - 1));
  progress();
  const id = list[pos].id;
  try {
    const d = await detail(id);
    if (list[pos] && list[pos].id !== id) return;
    current = d;
    drawSide(d); drawChip(d); drawMap(d);
    for (const k of [1, 2]) if (list[pos + k]) detail(list[pos + k].id);
  } catch (e) { status(`Could not load ${id}: ${e.message}`, true); }
}

async function save(code) {
  if (!current) return;
  const reviewer = $("reviewer").value.trim().toUpperCase();
  if (!reviewer) { status("Type your initials first (Initials box, top right).", true); $("reviewer").focus(); return; }
  const body = { ITEM_ID: current.id, ANSWER: code, NOTE: $("note").value, REVIEWER: reviewer };
  try {
    const r = await fetch("/api/answer", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    const out = await r.json();
    if (!r.ok) { status(out.error || `Error ${r.status}`, true); return; }
    if (out.saved) answers[current.id] = out.saved; else delete answers[current.id];
    const id = current.id;
    if (code && $("auto-advance").checked) {
      const was = pos;
      buildList();
      const at = list.findIndex((it) => it.id === id);
      show(at >= 0 ? at + 1 : was);
    } else {
      buildList();
      const at = list.findIndex((it) => it.id === id);
      if (at >= 0) { pos = at; drawSide(current); progress(); } else show(pos);
    }
    status(code ? `Saved ${id}: ${code}` : `Cleared ${id}`);
  } catch (e) { status(`Not saved. ${NO_SERVER}`, true); }
}

const dateCache = new Map();
async function imageryDate(c) {
  const key = `${c[0].toFixed(3)},${c[1].toFixed(3)}`;
  $("imagery-date").textContent = dateCache.get(key) || "";
  if (dateCache.has(key)) return;
  dateCache.set(key, "");
  try {
    // the World Imagery service's own footprint layers carry each source's date and resolution
    const url = "https://services.arcgisonline.com/arcgis/rest/services/World_Imagery/MapServer/identify" +
      `?f=json&geometry=${c[1]},${c[0]}&geometryType=esriGeometryPoint&sr=4326&layers=all&tolerance=0` +
      `&mapExtent=${c[1] - 0.001},${c[0] - 0.001},${c[1] + 0.001},${c[0] + 0.001}&imageDisplay=400,400,96&returnGeometry=false`;
    const r = await getJSON(url);
    const hit = (r.results || []).find((x) => x.layerName === "World Imagery");
    const a = hit ? hit.attributes : null;
    if (a && a.SRC_DATE2 && a.SRC_DATE2 !== "Null") {
      const res = parseFloat(a["RESOLUTION (M)"]);
      const text = `· ${a.SOURCE || ""} ${a.SRC_DATE2}${res ? ` (${Math.round(res * 1000) / 10} cm)` : ""}`;
      dateCache.set(key, text);
      $("imagery-date").textContent = text;
    }
  } catch (e) { /* the date is a convenience; the map works without it */ }
}

function keys(e) {
  if (e.target === $("note")) {
    if (e.key === "Escape") { $("note").blur(); e.preventDefault(); }
    else if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      const a = current && answers[current.id];
      if (a) { $("auto-advance").checked = false; save(a.ANSWER).then(() => { $("auto-advance").checked = true; }); }
      else status("Choose an answer with a number key; the note is saved with it.", true);
    }
    return;
  }
  if (e.target === $("reviewer") || e.target.tagName === "SELECT") { if (e.key === "Enter") e.target.blur(); return; }
  if (!current && !["ArrowLeft", "ArrowRight"].includes(e.key)) return;
  const q = current ? QUEUES[current.queue] : null;
  if (/^[1-9]$/.test(e.key) && q && q.answers[+e.key - 1]) { save(q.answers[+e.key - 1][0]); e.preventDefault(); }
  else if (e.key === "ArrowRight" || e.key === "Enter") { show(pos + 1); e.preventDefault(); }
  else if (e.key === "ArrowLeft") { show(pos - 1); e.preventDefault(); }
  else if (e.key === "Backspace") { save(""); e.preventDefault(); }
  else if (e.key === "n" || e.key === "N") { $("note").focus(); e.preventDefault(); }
  else if ((e.key === "r" || e.key === "R") && homeView) { map.setView(homeView[0], homeView[1]); e.preventDefault(); }
}

async function start() {
  map = L.map("map", { zoomSnap: 0, zoomControl: true, attributionControl: true, maxZoom: 22 });
  L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}", {
    maxNativeZoom: 21, maxZoom: 22,
    attribution: "Esri, Maxar, Earthstar Geographics, and the GIS User Community" }).addTo(map);
  layers = L.layerGroup().addTo(map);
  $("reviewer").value = store("footprint-review-reviewer") || "";
  $("reviewer").addEventListener("change", () => { $("reviewer").value = $("reviewer").value.trim().toUpperCase(); store("footprint-review-reviewer", $("reviewer").value); });
  index = await getJSON("/data/index.json");
  for (const it of index.items) byId[it.id] = it;
  const st = await getJSON("/api/state");
  answers = st.answers; $("csv-path").textContent = st.csv;
  for (const q of Object.keys(QUEUES)) if (!index.items.some((it) => it.queue === q)) $("queue").querySelector(`[value=${q}]`).disabled = true;
  const savedQueue = store("footprint-review-queue");
  if (savedQueue && index.items.some((it) => it.queue === savedQueue)) $("queue").value = savedQueue;
  refreshGroups();
  const reload = () => { buildList(); show(0); };
  $("queue").onchange = () => { store("footprint-review-queue", $("queue").value); refreshGroups(); reload(); };
  $("group").onchange = reload; $("show").onchange = reload;
  $("prev").onclick = () => show(pos - 1); $("next").onclick = () => show(pos + 1);
  $("clear").onclick = () => save(""); $("reset").onclick = () => homeView && map.setView(homeView[0], homeView[1]);
  document.addEventListener("keydown", keys);
  reload();
}

start().catch((e) => status(`Could not start: ${e.message}`, true));
