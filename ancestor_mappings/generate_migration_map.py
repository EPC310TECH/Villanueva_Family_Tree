#!/usr/bin/env python3
"""
generate_migration_map.py
=========================
Generates migration-map.html — interactive Leaflet map with time slider
showing the family's geographic movement 607 AD → present.

Output: ancestor_mappings/migration-map.html
"""

import json, re, os, math

HERE    = os.path.dirname(os.path.abspath(__file__))
TREE    = os.path.join(HERE, "the-tree.html")
OUT     = os.path.join(HERE, "migration-map.html")

# ── coordinate tables ─────────────────────────────────────────────────────────
# region → (lat, lng)  — tried first; country → (lat,lng) used as fallback

REGION_COORDS = {
    # Iberian kingdoms / regions
    "Asturias":                    (43.40, -6.00),
    "León":                        (42.60, -5.57),
    "Leon":                        (42.60, -5.57),
    "Castilla":                    (41.80, -4.00),
    "Castile":                     (41.80, -4.00),
    "Castilla y León":             (41.50, -4.50),
    "Navarra":                     (42.70, -1.50),
    "Navarre":                     (42.70, -1.50),
    "Pamplona":                    (42.82, -1.64),
    "Aragón":                      (41.60, -0.90),
    "Aragon":                      (41.60, -0.90),
    "Cataluña":                    (41.60,  1.80),
    "Catalonia":                   (41.60,  1.80),
    "Vizcaya":                     (43.28, -2.70),
    "Galicia":                     (42.80, -8.00),
    "Galicie":                     (42.80, -8.00),
    "Coimbra":                     (40.21, -8.42),
    "Portugal":                    (39.50, -8.10),
    "Sevilla":                     (37.39, -5.99),
    "Toledo":                      (39.86, -4.02),
    "Burgos":                      (42.34, -3.70),
    "España":                      (40.41, -3.70),
    "Spain":                       (40.41, -3.70),
    "Extremadura":                 (39.20, -6.15),
    "Andalusia":                   (37.50, -4.50),
    "Granada":                     (37.18, -3.60),
    "Lara":                        (42.05, -3.71),
    "Soria":                       (41.76, -2.46),
    "Albacete":                    (39.00, -1.86),
    "Palencia":                    (42.01, -4.53),
    "Mérida":                      (38.92, -6.35),
    "Salamanca":                   (40.97, -5.66),
    "Valladolid":                  (41.65, -4.72),
    "Cabrera":                     (41.82,  2.16),
    "Trastámara":                  (43.10, -7.50),
    "Maia":                        (41.23, -8.62),
    "Monterroso":                  (42.60, -7.84),
    "Monforte de Lemos":           (42.52, -7.51),
    "Villanueva de la Serena":     (38.98, -5.79),
    "Ribadouro":                   (41.08, -8.21),
    "Bragança":                    (41.81, -6.76),
    "Celanova":                    (42.15, -7.95),
    "Jerez de la Frontera":        (36.69, -6.14),

    # French regions / counties
    "France":                      (46.00,  2.50),
    "Toulouse":                    (43.60,  1.44),
    "Gascogne":                    (43.70, -0.50),
    "Gascony":                     (43.70, -0.50),
    "Anjou":                       (47.47, -0.55),
    "Burgundy":                    (47.00,  4.85),
    "Bourgogne":                   (47.00,  4.85),
    "Lorraine":                    (48.70,  6.18),
    "Normandy":                    (49.00,  0.50),
    "Normandie":                   (49.00,  0.50),
    "Provence":                    (43.80,  5.50),
    "Bretagne":                    (48.20, -2.90),
    "Brittany":                    (48.20, -2.90),
    "Comminges":                   (43.05,  0.58),
    "Foix":                        (42.96,  1.60),
    "Flanders":                    (51.00,  3.50),
    "Hainaut":                     (50.38,  4.04),
    "Champagne":                   (48.80,  4.00),
    "Blois":                       (47.59,  1.33),
    "Poitou":                      (46.58,  0.34),
    "Poitiers":                    (46.58,  0.34),
    "Languedoc":                   (43.60,  3.88),
    "Vermandois":                  (49.80,  3.30),
    "Corbeil":                     (48.62,  2.48),
    "Bigorre":                     (43.10,  0.00),
    "Carcassonne":                 (43.21,  2.35),
    "Béziers":                     (43.35,  3.22),
    "Narbonne":                    (43.18,  3.00),
    "Narbona":                     (43.18,  3.00),
    "Forez":                       (45.74,  3.86),
    "Gévaudan":                    (44.52,  3.50),
    "Millau":                      (44.10,  3.08),
    "Rouergue":                    (44.35,  2.57),
    "Melgueil":                    (43.52,  4.05),
    "Aurillac":                    (44.93,  2.44),
    "Brioude":                     (45.30,  3.38),
    "Montpellier":                 (43.61,  3.88),
    "Vence":                       (43.72,  7.11),
    "Sisteron":                    (44.20,  5.94),
    "Forcalquier":                 (43.96,  5.78),
    "Sabran":                      (44.05,  4.64),
    "Comtat":                      (44.05,  4.90),
    "Chalon":                      (46.78,  4.85),
    "Tonnerre":                    (47.86,  3.98),
    "Semur":                       (47.49,  4.34),
    "Nevers":                      (46.99,  3.16),
    "Dijon":                       (47.32,  5.04),
    "Anjou":                       (47.47, -0.55),
    "Mayenne":                     (48.30, -0.61),
    "Thouars":                     (46.98, -0.22),
    "Saumur":                      (47.26, -0.08),
    "Preuilly":                    (46.85,  0.93),
    "Bueil":                       (47.55,  0.55),
    "Chartres":                    (48.45,  1.49),
    "Nogent":                      (48.51,  3.50),
    "Montfort":                    (48.76,  0.47),
    "Ramerupt":                    (48.44,  4.30),
    "Roucy":                       (49.43,  3.80),
    "Vergy":                       (47.22,  5.00),
    "Coucy":                       (49.52,  3.32),
    "Montdidier":                  (49.65,  2.57),
    "Gometz":                      (48.68,  2.12),
    "Beaugency":                   (47.78,  1.63),

    # Iberian Peninsula — Catalan counties
    "Pallars":                     (42.40,  1.00),
    "Urgel":                       (42.10,  1.10),
    "Cerdanya":                    (42.40,  1.90),
    "Besalú":                      (42.20,  2.70),
    "Ribagorza":                   (42.30,  0.50),
    "Castellvell":                 (41.45,  1.50),
    "Cabrera (Girona)":            (41.72,  2.76),
    "Moncada":                     (41.50,  2.19),
    "Gurb":                        (41.95,  2.25),
    "Tost":                        (42.10,  1.28),

    # Other European
    "England":                     (52.50, -1.50),
    "Scots":                       (56.50, -3.50),
    "Scotland":                    (56.50, -3.50),
    "Italy":                       (42.50, 12.50),
    "Canavese":                    (45.40,  7.80),
    "Saxony":                      (51.00, 13.00),
    "Swabia":                      (48.00,  9.50),
    "Hungary":                     (47.00, 19.00),
    "Bohemia":                     (50.00, 15.50),
    "Mysia":                       (40.20, 28.00),

    # Mexico / New Spain
    "Mexico":                      (23.00,-102.00),
    "Zacatecas":                   (22.77,-102.58),
    "Jalisco":                     (20.67,-103.35),
    "Jerez de Garcia Salinas":     (22.65,-102.98),
    "Jerez":                       (22.65,-102.98),
    "District Of Jerez":           (22.65,-102.98),
    "san jose de la Isla":         (22.05,-102.30),
    "Jerez de García Salinas":     (22.65,-102.98),
    "Nueva Vizcaya":               (26.00,-106.00),
    "Guanajuato":                  (21.00,-101.26),
    "Michoacán":                   (19.50,-101.70),
    "Veracruz":                    (19.18, -96.14),
    "Ciudad de México":            (19.43, -99.13),
    "Nueva España":                (23.00,-102.00),

    # USA
    "United States":               (37.00, -95.00),
}

COUNTRY_COORDS = {
    "Spain":          (40.00, -3.50),
    "France":         (46.00,  2.50),
    "Portugal":       (39.50, -8.00),
    "England":        (52.50, -1.50),
    "Italy":          (42.50, 12.50),
    "Mexico":         (23.00,-102.00),
    "United States":  (37.00, -95.00),
}

# ── historical eras ───────────────────────────────────────────────────────────
ERAS = [
    (607,  718,  "Pre-Reconquista Iberia",
     "The earliest documented ancestors — counts and lords of northern Iberia before the Moorish conquest of 711."),
    (718,  910,  "Kingdom of Asturias",
     "Christian resistance in the north. Pelayo's victory at Covadonga launches the Reconquista."),
    (910,  1037, "Kingdoms of León & Navarre",
     "León and Navarre emerge as the dominant Christian kingdoms. Your Navarrese and Leonese royal ancestors flourish here."),
    (1037, 1200, "Castile, Aragon & the Crusades",
     "Castile gains independence. French noble connections appear through crusading marriages. Fernán González's descendants multiply."),
    (1200, 1400, "Crown of Castile",
     "The great noble houses — Haro, Lara, Velasco — dominate Castilian politics. Your ancestry concentrates in northern Castile."),
    (1400, 1492, "Late Medieval Iberia",
     "The Catholic Monarchs Fernando and Isabel begin unifying Spain. The Velasco family holds the Constableship of Castile."),
    (1492, 1550, "Conquest of New Spain",
     "Columbus reaches the Americas. Your ancestors among the first conquistadors — Bobadilla, Temiño de Velasco — cross the Atlantic."),
    (1550, 1700, "Colonial Mexico",
     "The family roots in New Spain. Silver mining in Zacatecas fuels the colonial economy. Your Jasso-Villanueva ancestors settle here."),
    (1700, 1821, "Late Colonial & Bourbon Era",
     "Spain's Bourbon kings reform the colonies. Your family established around Jerez de García Salinas, Zacatecas."),
    (1821, 1910, "Independent Mexico",
     "Mexico achieves independence in 1821. The Villanueva-Jasso family through revolution and reform."),
    (1910, 1990, "Modern Mexico",
     "The Mexican Revolution and 20th century. The family's documented history reaches the present generation."),
]

def get_era(year):
    for start, end, name, desc in ERAS:
        if start <= year <= end:
            return name, desc
    return "Unknown Era", ""

# ── load graph ────────────────────────────────────────────────────────────────
with open(TREE, encoding="utf-8") as f:
    raw = f.read()

m   = re.search(r'const GRAPH\s*=\s*(\{.*?\});', raw, re.DOTALL)
graph = json.loads(m.group(1))
nodes = graph["nodes"]

# ── assign coordinates ────────────────────────────────────────────────────────
def get_coords(node, nid):
    region  = (node.get("region") or "").strip()
    country = (node.get("country") or "").strip()

    base = REGION_COORDS.get(region) or COUNTRY_COORDS.get(country)
    if base is None:
        return None

    lat0, lng0 = base
    # deterministic jitter using node id (so same node always in same spot)
    lat_j = math.sin(nid * 1.6180339887) * 0.45
    lng_j = math.cos(nid * 2.7182818284) * 0.70
    return round(lat0 + lat_j, 4), round(lng0 + lng_j, 4)

# ── build map data ────────────────────────────────────────────────────────────
map_nodes = []
skipped   = 0

for n in nodes:
    if not n.get("birth"):
        skipped += 1
        continue
    coords = get_coords(n, n["id"])
    if coords is None:
        skipped += 1
        continue

    lat, lng = coords
    map_nodes.append({
        "b":  n["birth"],
        "d":  n.get("death") or None,
        "n":  n["name"],
        "g":  n.get("gen", 0),
        "c":  n.get("cat","untitled"),
        "la": lat,
        "lo": lng,
        "t":  (n.get("titles") or "")[:80],
        "h":  (n.get("house")  or ""),
        "m":  n.get("mult", 1),
    })

print(f"Map nodes: {len(map_nodes)}  |  skipped (no birth/coords): {skipped}")
payload = json.dumps(map_nodes, ensure_ascii=False, separators=(",",":"))

# ── era JSON for JS ───────────────────────────────────────────────────────────
eras_js = json.dumps([
    {"s": s, "e": e, "name": nm, "desc": ds}
    for s, e, nm, ds in ERAS
], ensure_ascii=False, separators=(",",":"))

# ── HTML template ─────────────────────────────────────────────────────────────
HTML = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Migration Map — Villanueva Family Tree</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
html,body{{height:100%;background:#111009;font-family:ui-sans-serif,system-ui,sans-serif}}

/* ── map ── */
#map{{position:fixed;inset:0;z-index:0}}

/* ── era panel ── */
#panel{{
  position:fixed;top:16px;left:16px;z-index:900;
  background:rgba(17,10,5,.88);border:1px solid rgba(200,168,75,.22);
  border-radius:10px;padding:16px 20px;max-width:280px;
  backdrop-filter:blur(6px);
}}
#panel a{{color:#c8a84b;font-size:.72rem;text-decoration:none}}
#panel a:hover{{text-decoration:underline}}
#year-display{{font-size:2rem;font-weight:800;color:#e8b820;line-height:1;margin-bottom:4px;font-variant-numeric:tabular-nums}}
#era-name{{font-size:.78rem;letter-spacing:.1em;text-transform:uppercase;color:#c8a84b;margin-bottom:8px}}
#era-desc{{font-size:.77rem;color:#a89b7a;line-height:1.55;margin-bottom:12px}}
#stats{{font-size:.73rem;color:#6b6050;border-top:1px solid rgba(200,168,75,.12);padding-top:10px;display:flex;gap:14px}}
#stats span{{display:flex;flex-direction:column;gap:1px}}
.stat-n{{font-size:1rem;font-weight:700;color:#e8dfcc}}
.stat-l{{font-size:.62rem;letter-spacing:.08em;text-transform:uppercase;color:#6b6050}}

/* ── legend ── */
#legend{{
  position:fixed;top:16px;right:16px;z-index:900;
  background:rgba(17,10,5,.88);border:1px solid rgba(200,168,75,.22);
  border-radius:10px;padding:12px 16px;
  backdrop-filter:blur(6px);
}}
.leg-row{{display:flex;align-items:center;gap:8px;font-size:.73rem;color:#a89b7a;margin-bottom:6px}}
.leg-row:last-child{{margin-bottom:0}}
.leg-dot{{width:10px;height:10px;border-radius:50%;flex-shrink:0}}

/* ── bottom bar ── */
#controls{{
  position:fixed;bottom:0;left:0;right:0;z-index:900;
  background:rgba(13,9,5,.92);border-top:1px solid rgba(200,168,75,.15);
  padding:14px 24px 18px;
  backdrop-filter:blur(8px);
}}
.ctrl-row{{display:flex;align-items:center;gap:14px;max-width:900px;margin:0 auto}}

#play-btn{{
  width:40px;height:40px;border-radius:50%;border:1px solid #c8a84b;
  background:transparent;color:#e8b820;font-size:1.1rem;cursor:pointer;
  flex-shrink:0;display:flex;align-items:center;justify-content:center;
  transition:background .15s
}}
#play-btn:hover{{background:rgba(200,168,75,.15)}}
#play-btn.playing{{background:rgba(200,168,75,.2)}}

#slider{{
  flex:1;-webkit-appearance:none;appearance:none;height:4px;
  background:rgba(200,168,75,.2);border-radius:2px;outline:none;cursor:pointer
}}
#slider::-webkit-slider-thumb{{
  -webkit-appearance:none;width:18px;height:18px;border-radius:50%;
  background:#e8b820;border:2px solid #1a1610;cursor:pointer;
  box-shadow:0 0 8px rgba(232,184,32,.5)
}}
#slider-label{{
  font-size:.78rem;color:#6b6050;white-space:nowrap;min-width:80px;text-align:right;
  font-variant-numeric:tabular-nums
}}

/* speed selector */
#speed-sel{{
  background:rgba(200,168,75,.08);border:1px solid rgba(200,168,75,.2);
  color:#a89b7a;font-size:.72rem;padding:4px 8px;border-radius:4px;cursor:pointer;
  outline:none
}}
#speed-sel option{{background:#1a1610}}

/* ── Leaflet popup override ── */
.leaflet-popup-content-wrapper{{
  background:rgba(23,18,10,.96);border:1px solid rgba(200,168,75,.3);
  border-radius:8px;box-shadow:0 4px 20px rgba(0,0,0,.8);color:#e8dfcc
}}
.leaflet-popup-tip{{background:rgba(23,18,10,.96)}}
.leaflet-popup-content{{margin:12px 16px;font-size:.83rem;line-height:1.6}}
.mpop-name{{font-weight:700;color:#e8dfcc;font-size:.95rem;margin-bottom:3px}}
.mpop-rel{{font-size:.75rem;color:#e8b820;margin-bottom:4px}}
.mpop-dates{{font-size:.77rem;color:#a89b7a}}
.mpop-titles{{font-size:.72rem;color:#7a6e5a;margin-top:4px;font-style:italic}}
.mpop-house{{font-size:.72rem;color:#c8a84b;margin-top:3px}}

/* nav */
.topnav{{
  position:fixed;top:16px;left:50%;transform:translateX(-50%);z-index:901;
  background:rgba(17,10,5,.88);border:1px solid rgba(200,168,75,.18);
  border-radius:99px;padding:6px 18px;display:flex;gap:16px;
  font-size:.72rem;letter-spacing:.08em;backdrop-filter:blur(6px)
}}
.topnav a{{color:#c8a84b;text-decoration:none}}
.topnav a:hover{{color:#e8b820}}
.topnav .sep{{color:rgba(200,168,75,.3)}}
</style>
</head>
<body>

<div id="map"></div>

<nav class="topnav">
  <a href="../index.html">Home</a>
  <span class="sep">·</span>
  <a href="the-tree.html">Family Tree</a>
  <span class="sep">·</span>
  <a href="houses/index.html">Noble Houses</a>
</nav>

<div id="panel">
  <div id="year-display">900 AD</div>
  <div id="era-name">Kingdom of León &amp; Navarre</div>
  <div id="era-desc">León and Navarre emerge as the dominant Christian kingdoms.</div>
  <div id="stats">
    <span><span class="stat-n" id="stat-visible">0</span><span class="stat-l">Visible</span></span>
    <span><span class="stat-n" id="stat-total">{len(map_nodes)}</span><span class="stat-l">Mappable</span></span>
    <span><span class="stat-n" id="stat-region">Iberia</span><span class="stat-l">Region</span></span>
  </div>
</div>

<div id="legend">
  <div class="leg-row"><div class="leg-dot" style="background:#e8b820"></div>Royalty</div>
  <div class="leg-row"><div class="leg-dot" style="background:#c83040"></div>Nobility</div>
  <div class="leg-row"><div class="leg-dot" style="background:#2d78d8"></div>Military</div>
  <div class="leg-row"><div class="leg-dot" style="background:#18a870"></div>Civic</div>
  <div class="leg-row"><div class="leg-dot" style="background:#9040c0"></div>Clergy</div>
  <div class="leg-row"><div class="leg-dot" style="background:#c86828"></div>Indigenous</div>
  <div class="leg-row"><div class="leg-dot" style="background:#5a5248"></div>Untitled</div>
</div>

<div id="controls">
  <div class="ctrl-row">
    <button id="play-btn" title="Play / Pause">▶</button>
    <select id="speed-sel" title="Playback speed">
      <option value="5">Slow</option>
      <option value="15" selected>Normal</option>
      <option value="40">Fast</option>
      <option value="100">Turbo</option>
    </select>
    <input id="slider" type="range" min="607" max="1990" step="1" value="900">
    <div id="slider-label">Year 900 AD</div>
  </div>
</div>

<script>
// ── data ──────────────────────────────────────────────────────────────────────
const NODES = {payload};
const ERAS  = {eras_js};

// ── helpers ───────────────────────────────────────────────────────────────────
const CAT_COLOR = {{
  royal:     '#e8b820',
  noble:     '#c83040',
  nobility:  '#c83040',
  military:  '#2d78d8',
  official:  '#18a870',
  clergy:    '#9040c0',
  indigenous:'#c86828',
  untitled:  '#5a5248',
}};

function catColor(c) {{ return CAT_COLOR[c] || '#5a5248'; }}
function catRadius(c, m) {{
  const base = c === 'royal' ? 7 : c === 'noble' ? 5.5 : c === 'military' ? 5 : 4;
  return m > 100 ? base + 2 : m > 10 ? base + 1 : base;
}}

function getEra(yr) {{
  for (const e of ERAS) if (yr >= e.s && yr <= e.e) return e;
  return ERAS[ERAS.length - 1];
}}

function genLabel(g) {{
  if (g === 0) return 'you';
  if (g === 1) return 'parent';
  if (g === 2) return 'grandparent';
  if (g === 3) return 'great-grandparent';
  return `${{g - 2}}th great-grandparent`;
}}

function regionLabel(yr) {{
  if (yr > 1821) return 'Mexico';
  if (yr > 1492) return 'Iberia + New Spain';
  if (yr > 1200) return 'Iberia + France';
  return 'Iberia';
}}

// ── map init ──────────────────────────────────────────────────────────────────
const map = L.map('map', {{
  center: [43, -4],
  zoom: 5,
  zoomControl: false,
  attributionControl: true,
}});

L.tileLayer(
  'https://{{s}}.basemaps.cartocdn.com/dark_all/{{z}}/{{x}}/{{y}}{{r}}.png',
  {{
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> &copy; <a href="https://carto.com">CARTO</a>',
    subdomains: 'abcd',
    maxZoom: 19
  }}
).addTo(map);

L.control.zoom({{ position: 'bottomright' }}).addTo(map);

// ── create markers (initially hidden) ─────────────────────────────────────────
const renderer = L.canvas({{ padding: 0.5 }});
const markers  = [];

for (const nd of NODES) {{
  const col = catColor(nd.c);
  const r   = catRadius(nd.c, nd.m);
  const mk  = L.circleMarker([nd.la, nd.lo], {{
    renderer,
    radius:      r,
    color:       col,
    weight:      1,
    opacity:     0,
    fillColor:   col,
    fillOpacity: 0,
    interactive: true,
  }});

  mk.bindPopup(
    `<div class="mpop-name">${{nd.n}}</div>` +
    `<div class="mpop-rel">Your ${{genLabel(nd.g)}} · gen ${{nd.g}}</div>` +
    `<div class="mpop-dates">b. ${{nd.b}}${{nd.d ? ' · d. ' + nd.d : ''}}</div>` +
    (nd.t ? `<div class="mpop-titles">${{nd.t}}</div>` : '') +
    (nd.h ? `<div class="mpop-house">House of ${{nd.h}}</div>` : ''),
    {{ maxWidth: 260 }}
  );

  mk.addTo(map);
  markers.push({{ mk, nd }});
}}

// ── update map for a given year ────────────────────────────────────────────────
let lastYear    = -1;
let hasPannedAmericas = false;
let hasPannedBack     = false;

function updateMap(yr) {{
  if (yr === lastYear) return;
  lastYear = yr;

  const WINDOW = 80;  // show ancestors alive within this many years
  let visible = 0;

  for (const {{ mk, nd }} of markers) {{
    const alive = nd.b <= yr && (nd.d ? nd.d >= yr - 5 : nd.b >= yr - WINDOW);
    if (!alive) {{
      if (mk.options.fillOpacity > 0) {{
        mk.setStyle({{ opacity: 0, fillOpacity: 0 }});
      }}
      continue;
    }}

    visible++;
    const age = yr - nd.b;
    // New arrivals pulse bright; older fade gently
    let fo = age < 8  ? 0.95 :
             age < 20 ? 0.80 :
             age < 40 ? 0.65 :
             age < 60 ? 0.50 : 0.35;
    let bo = fo * 0.7;
    mk.setStyle({{ opacity: bo, fillOpacity: fo }});
  }}

  // Era panel
  const era = getEra(yr);
  document.getElementById('year-display').textContent  = yr + ' AD';
  document.getElementById('era-name').textContent      = era.name;
  document.getElementById('era-desc').textContent      = era.desc;
  document.getElementById('stat-visible').textContent  = visible;
  document.getElementById('stat-region').textContent   = regionLabel(yr);
  document.getElementById('slider-label').textContent  = 'Year ' + yr + ' AD';

  // Auto-pan: when Americas open up, zoom out to show both continents
  if (yr >= 1510 && !hasPannedAmericas) {{
    hasPannedAmericas = true;
    map.flyTo([28, -45], 3, {{ duration: 2.5 }});
  }}
  // If slider goes back before Americas, return to Iberia view
  if (yr < 1490 && hasPannedAmericas) {{
    hasPannedAmericas = false;
    map.flyTo([43, -4], 5, {{ duration: 1.5 }});
  }}
}}

// ── slider & play ─────────────────────────────────────────────────────────────
const slider   = document.getElementById('slider');
const playBtn  = document.getElementById('play-btn');
const speedSel = document.getElementById('speed-sel');

slider.addEventListener('input', () => updateMap(+slider.value));
updateMap(+slider.value);

let playInterval = null;

function startPlay() {{
  if (+slider.value >= 1990) slider.value = 607;
  playBtn.textContent = '⏸';
  playBtn.classList.add('playing');
  playInterval = setInterval(() => {{
    const next = +slider.value + +speedSel.value;
    if (next > 1990) {{
      slider.value = 1990;
      updateMap(1990);
      stopPlay();
    }} else {{
      slider.value = next;
      updateMap(next);
    }}
  }}, 50);
}}

function stopPlay() {{
  clearInterval(playInterval);
  playInterval = null;
  playBtn.textContent = '▶';
  playBtn.classList.remove('playing');
}}

playBtn.addEventListener('click', () => {{
  if (playInterval) stopPlay(); else startPlay();
}});

// keyboard: space = play/pause, ←/→ = step
document.addEventListener('keydown', e => {{
  if (e.target.tagName === 'INPUT' || e.target.tagName === 'SELECT') return;
  if (e.key === ' ')          {{ e.preventDefault(); playBtn.click(); }}
  if (e.key === 'ArrowRight') {{ slider.value = Math.min(1990, +slider.value + 10); updateMap(+slider.value); }}
  if (e.key === 'ArrowLeft')  {{ slider.value = Math.max(607,  +slider.value - 10); updateMap(+slider.value); }}
}});
</script>
</body>
</html>"""

with open(OUT, "w", encoding="utf-8") as f:
    f.write(HTML)

print(f"Written: {OUT}")
print(f"  {len(map_nodes)} mapped ancestors  ·  {skipped} skipped")
