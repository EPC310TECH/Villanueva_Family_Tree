#!/usr/bin/env python3
"""
generate_house_pages.py
=======================
Generates one HTML page per noble/royal house represented in antonio-jasso-lineage.html,
plus an index page. Output: ancestor_mappings/houses/
"""

import json, re, os, unicodedata, collections
from collections import deque, defaultdict

HERE    = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(HERE, "houses")
os.makedirs(OUT_DIR, exist_ok=True)

TREE_FILE = os.path.join(HERE, "antonio-jasso-lineage.html")

# ── curated historical descriptions (house_slug → HTML paragraph) ────────────

HISTORY = {
"haro": """
<p>The House of Haro (de Haro) was the most powerful noble family in medieval Castile for two centuries.
As hereditary Lords — and later Counts — of Vizcaya, they controlled the strategically vital Basque region
along the Atlantic coast. The lordship of Vizcaya gave them enormous wealth and a quasi-independent power base
that even the Kings of Castile could not easily override.</p>
<p>The house rose to prominence under <strong>Lope Díaz de Haro</strong> in the 10th century and reached its apex under
<strong>Diego López de Haro</strong> (d. 1214), who played kingmaker roles in the conflicts between Castile, León, and Navarre.
Members of this house intermarried with Navarrese and Leonese royalty, cementing their position at the top of Iberian nobility.
Your ancestors in this house include the de Aro family of colonial Mexico — direct descendants of the Lords of Vizcaya.</p>
""",

"asturias": """
<p>The Kingdom of Asturias (718–924 AD) was the first Christian kingdom to emerge in Iberia after the Moorish conquest of 711.
Founded by <strong>Pelayo</strong> after his victory at Covadonga, it became the cradle of what would eventually become Castile,
León, Portugal, and Spain. The Asturian kings saw themselves as heirs to the Visigothic monarchy and launched the
<em>Reconquista</em> — the centuries-long campaign to reclaim the Iberian Peninsula.</p>
<p>The kings of Asturias — including <strong>Alfonso II el Casto</strong>, <strong>Alfonso III el Grande</strong>, and
<strong>Ordoño I</strong> — appear in your ancestry, reflecting the deep roots of your family in the founding moment of Christian
Iberia. Their descendants spread through every noble house of the peninsula over the following centuries.</p>
""",

"lara": """
<p>The House of Lara was one of the most ancient and powerful noble families of Castile, tracing its origins to the
10th-century counts of Burgos and Lara. The family controlled vast territories in Old Castile and produced some of the most
influential magnates of medieval Iberia, including the legendary <em>Seven Lords of Lara</em> whose story became one of
the great epic cycles of medieval Spanish literature.</p>
<p>Your Lara ancestors include <strong>Gonzalo Fernández de Lara, Count of Burgos</strong> (b. 863) — father of Fernán González,
the first Count of Castile — as well as later Lara descendants who married into the Velasco and Manrique lines that connect
directly to your colonial Mexican ancestry. The Lara connection runs through Beatriz Manrique de Lara, who married El Comendador
Sancho de Velasco.</p>
""",

"coimbra": """
<p>The County of Coimbra was a crucial precursor state in the formation of Portugal. The counts of Coimbra governed the
region between the Douro and Mondego rivers — the heartland of what would become the Portuguese kingdom — from the
9th century onward. Key figures include <strong>Hermenegildo Guterres</strong> (b. 842), Count of Coimbra and Portugal,
who appears among your highest-mult ancestors with over 1,500 distinct lineage paths converging on him.</p>
<p>The Coimbra line fed directly into the early Portuguese royal dynasty and the noble families of the peninsula.
Your Coimbra ancestors mostly lived in the 9th–11th centuries, at the time when the Christian kingdoms of northwestern
Iberia were coalescing from Carolingian-era counties into distinct realms.</p>
""",

"cabrera": """
<p>The House of Cabrera (Cabrería) was a prominent viscounty in Catalonia, holding the title of Viscount of Cabrera from
the late 10th century. They were among the most powerful Catalan noble families and intermarried extensively with the
counts of Barcelona and the kings of Aragon. Your Cabrera ancestors connect through the network of Catalan and Aragonese
nobility that intersected with Castilian and Portuguese lines in the 11th–12th centuries.</p>
""",

"castro": """
<p>The House of Castro was one of the great Galician noble families, whose power rivaled the Laras in 12th–13th century
Castile. The Castros and the Laras fought a prolonged civil conflict during the minority of Alfonso VIII of Castile.
<strong>Fernando Rodríguez de Castro</strong>, known as "el Castellano," was one of the most powerful lords of his era.
Your Castro ancestors — including <strong>Urraca Fernández de Castro</strong> — connect to this turbulent lineage of
Galician lords who shaped the politics of medieval Castile and León.</p>
""",

"burgundy": """
<p>The Royal House of Burgundy had far-reaching influence across medieval Europe. A cadet branch known as the
<em>House of Burgundy-Ivrea</em> established the royal dynasties of both Castile and Portugal in the early 12th century:
<strong>Raymond of Burgundy</strong> (in your ancestry) married Urraca of Castile, founding the Castilian royal line,
while his brother Henry founded the Portuguese one. Your Burgundy ancestors thus place you within two of the most important
ruling houses of medieval Iberia.</p>
""",

"toulouse": """
<p>The County of Toulouse was one of the great sovereign territories of medieval southern France, ruling over much of
Occitania (modern Languedoc). The counts of Toulouse were among the most powerful princes of their era, patrons of
troubadour culture, and central figures in the Albigensian Crusade. Your connection runs through
<strong>Elvira Alfonso, Countess of Tolosa</strong>, an illegitimate daughter of Alfonso VI of León who married into
the Toulousain house, linking Iberian royal blood to the great southern French dynasty.</p>
""",

"velasco": """
<p>The House of Velasco rose from Castilian minor nobility in the 13th century to become one of the most powerful families
in Spain by the 15th century, holding the hereditary office of <em>Condestable de Castilla</em> (Constable of Castile)
from 1379. <strong>Pedro Fernández de Velasco y Solier, I Conde de Haro</strong> (in your direct ancestry) was a pivotal
figure in 15th-century Castile. The Velasco connection runs continuously from medieval Castile through colonial Mexico
via the Temiño de Velasco line — Baltasar Temiño y Bañuelos (your 14th great-grandfather) was himself a
<em>Capitán General</em> in New Spain's Chichimec Wars.</p>
""",

"guzmán": """
<p>The House of Guzmán was one of the great noble houses of Castile, most famous for <strong>Guzmán el Bueno</strong>
(Alonso Pérez de Guzmán), the legendary defender of Tarifa in 1294 who sacrificed his own son rather than surrender the city.
Your Guzmán ancestors include <strong>Juana de Guzmán</strong> (gen 21), connecting through the Sarmiento and Guzmán
lines that intersected with the Corral family — your 19th great-grandmother Beatriz del Corral was Juana's descendant.
The Guzmán house later intermarried with the Spanish royal family and produced the powerful Dukes of Medina Sidonia.</p>
""",

"trastámara": """
<p>The House of Trastámara began as the counts of a Galician territory in northwestern Iberia. They rose to spectacular
prominence when <strong>Henry of Trastámara</strong> (an illegitimate son of Alfonso XI of Castile) overthrew and killed
his half-brother Peter I in 1369, founding the Trastámara dynasty that would rule Castile — and eventually Spain — for
over a century. Your Trastámara ancestors predate the dynasty's rise, appearing as Galician counts in the 10th–12th centuries.</p>
""",

"saldaña": """
<p>The County of Saldaña was a medieval Castilian lordship in the region of Palencia. <strong>Diego Muñoz, 1st Count of Saldaña</strong>
(b. 900) — your 30th great-grandfather — was a key figure in the political landscape of early Castile and appears
among your highest-collapse ancestors (over 2,700 lineage paths converge on him). The Saldaña line runs through
your Ruiz de Saldaña, Fernández de Saldaña, and Gómez de Saldaña ancestors, eventually connecting to
Muniadona Fernández, condesa de Castilla — your 27th great-grandmother.</p>
""",

"villamayor": """
<p>The House of Villamayor was a Castilian noble family prominent in the 11th–13th centuries, holding lordship over
territories in northern Castile. Your Villamayor ancestors connect through the Sarmiento line — Diego Pérez Sarmiento
de Villamayor y Haro appears in your ancestry at generation 22, bridging the colonial Mexican Sarmiento heritage
with deep Castilian noble roots. The Villamayor and Sarmiento families were deeply intertwined in medieval Castile.</p>
""",

"jiménez": """
<p>The Jiménez (Jimena) dynasty was the ruling house of the Kingdom of Navarre from the early 10th century, founded by
<strong>Sancho I Garcés</strong> (b. 865) — your 31st great-grandfather. They later extended their rule over Aragon and,
through conquest and marriage, became the most powerful royal dynasty in 11th-century Iberia. <strong>Sancho III el Mayor</strong>
briefly unified most of Christian Iberia under his rule. Your Jiménez ancestors also include the Navarrese and Aragonese
lines that fed into the later Castilian nobility.</p>
""",

"normandy": """
<p>The House of Normandy produced some of the most consequential rulers of medieval Europe, from <strong>William the Conqueror</strong>
to the Anglo-Norman kings of England. Your Norman ancestors appear in the tree through the intermarriage of Norman nobles
with Iberian and French royalty in the 11th–12th centuries. The Norman presence in Iberia was significant — Norman knights
participated in the Reconquista and Norman princesses married into the Castilian and Portuguese royal families.</p>
""",

"provence": """
<p>The County of Provence was a major Mediterranean principality in the 9th–13th centuries, situated in what is now
southeastern France. Your Provence ancestors — <strong>Gersende de Provence</strong> and others — appear at generation
27–35, reflecting the deep medieval roots of your family in the interconnected aristocracy of southern France and the
western Mediterranean. The counts of Provence intermarried with the houses of Barcelona, Toulouse, and Aragon.</p>
""",

"del corral": """
<p>The del Corral family were Iberian nobles whose daughter <strong>Beatriz del Corral</strong> (your 19th great-grandmother,
gen 19) married Mosén Pedro Fernández de Bobadilla, a knight of Castilian descent. Through Beatriz, your ancestry connects
to the Sarmiento, Guzmán, and Asturian noble lines that extend back to the kingdoms of medieval Castile and León.
The del Corral family appear to have been established Castilian minor nobility in the 15th century.</p>
""",

"bobadilla": """
<p>The Bobadilla family produced a remarkable chain of conquistadors who participated in Spain's conquest of the Americas.
<strong>Pedro de Bobadilla</strong> and his son <strong>Francisco de Bobadilla</strong> (your 17th and 16th great-grandfathers)
were among the early settlers of New Spain. Their ancestor <strong>Mosén Pedro Fernández de Bobadilla</strong> was a
Castilian knight whose marriage to Beatriz del Corral links your colonial Mexican ancestry to the medieval Iberian nobility.
The Bobadilla connection is one of the clearest bridges between your Iberian noble lineage and your Mexican heritage.</p>
""",

"mendoza": """
<p>The House of Mendoza was one of the most powerful noble families in late medieval and early modern Castile,
producing the Dukes of Infantado and a string of cardinals, viceroys, and military commanders. Your Mendoza ancestor
<strong>María de Mendoza Arellano</strong> (gen 16) connects through the Velasco branch of your ancestry,
reflecting the tight web of intermarriage among the great Castilian noble houses in the 14th–15th centuries.</p>
""",

"maia": """
<p>The House of Maia (Maiam) was one of the oldest noble families of Portugal, tracing their lordship over the region
between the Douro and Minho rivers from the 10th century. They were among the founding families of the Portuguese
kingdom, consistently loyal to the House of Burgundy that established Portugal's independence in 1143.
Your Maia ancestors appear at generation 29–35, placing them in the 10th–12th centuries in what is now northern Portugal.</p>
""",

"pallars": """
<p>The County of Pallars was a Pyrenean county in what is now Catalonia, divided into Pallars Sobirà (Upper Pallars)
and Pallars Jussà (Lower Pallars). The counts of Pallars maintained a semi-independent existence within the Carolingian
and later Catalan framework, intermarrying with the counts of Barcelona and Urgell. Your Pallars ancestors lived in the
10th–11th centuries, deep in the Pyrenean world that formed the northeastern frontier of Christian Iberia.</p>
""",

"silva": """
<p>The House of Silva was a prominent noble family of Portugal and later Spain, producing numerous magnates, bishops,
and colonial administrators. The Silvas were deeply embedded in the Portuguese and Castilian nobilities of the
12th–15th centuries. Your Silva ancestors appear at generation 25–27, connecting through the network of Galician
and Portuguese noble families that fed into the Castilian nobility.</p>
""",

"sousa": """
<p>The House of Sousa was one of the most ancient noble families of Portugal, tracing descent from the Visigothic and
Suevic nobility of northwestern Iberia. They held lordship over territories near the Sousa river in what is now
the Minho region of Portugal. Your Sousa ancestors appear at generations 28–34, placing them among the earliest
documented Portuguese noble families in your tree.</p>
""",

"coimbra (house)": """<p>See Coimbra entry.</p>""",

"celanova": """
<p>The Celanova connection links your family to the monastery and county of Celanova in Galicia — one of the great
ecclesiastical centers of medieval northwestern Iberia. Your Celanova ancestors were Galician nobles of the 10th–12th
centuries, living during the period when Galicia was the political heartland of the Kingdom of León.</p>
""",

"traba": """
<p>The House of Traba was one of the most powerful Galician noble families of the 11th–12th centuries. The Counts of
Traba served as guardians and regents for the kings of Castile and León, and their power in Galicia was immense.
<strong>Fernando Pérez de Traba</strong> was regent for Alfonso VII of Castile during his minority. Your Traba connection
runs through the Portuguese noble lines in your ancestry.</p>
""",

"bragança": """
<p>The House of Bragança (Braganza) began as Portuguese minor nobility in the 12th century before rising to become
the ruling dynasty of Portugal from 1640 to 1910. Your Bragança ancestors lived in the earlier period, before the
house's dramatic rise — reflecting the network of Galician and Portuguese nobles from which this dynasty eventually emerged.</p>
""",

"foix": """
<p>The County of Foix, situated in the Pyrenean region of southern France (modern Ariège), was a significant feudal
power in the 10th–15th centuries. The counts of Foix were deeply involved in the conflicts between Toulouse,
Aragon, and the French crown, including the Albigensian Crusade. Your Foix ancestor <strong>Estefanía de Foix,
Queen of Navarre</strong> reflects the marriage politics that connected the Pyrenean counties to the Navarrese kingdom.</p>
""",

"anjou": """
<p>The House of Anjou was a major French royal house that produced rulers of England (as the Plantagenets), Naples,
Sicily, and Hungary. Your Anjou ancestors connect through the medieval French nobility that intermarried with Iberian
royal and noble families in the 11th–13th centuries, part of the broad European aristocratic network that connected
courts from England to Jerusalem.</p>
""",
}

# ── CSS shared across all pages ───────────────────────────────────────────────

CSS = """
:root{--bg:#1a1610;--surface:#231f18;--card:#2b2620;--gold:#c8a84b;--gold2:#e8b820;
--parch:#e8dfcc;--muted:#a89b7a;--line:rgba(200,168,75,.15);--red:#c83040;--blue:#2d78d8}
*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--bg);color:var(--parch);font-family:ui-sans-serif,system-ui,sans-serif;
padding:0;min-height:100vh}
a{color:var(--gold);text-decoration:none}a:hover{text-decoration:underline}
/* nav */
.topnav{background:rgba(26,22,16,.95);border-bottom:1px solid var(--line);padding:14px 28px;
display:flex;gap:20px;align-items:center;font-size:.82rem;letter-spacing:.08em;position:sticky;top:0;z-index:99}
.topnav .sep{color:var(--muted)}
/* hero */
.hero{background:linear-gradient(180deg,#231f18 0%,#1a1610 100%);border-bottom:1px solid var(--line);
padding:48px 28px 36px;max-width:900px;margin:0 auto}
.hero-inner{display:flex;gap:36px;align-items:flex-start}
.hero-text{flex:1;min-width:0}
.eyebrow{font-size:.72rem;letter-spacing:.18em;text-transform:uppercase;color:var(--muted);display:block;margin-bottom:10px}
.hero h1{font-size:2.1rem;font-weight:800;color:var(--gold2);letter-spacing:-.01em;margin-bottom:6px;line-height:1.1}
.hero .subtitle{font-size:.92rem;color:var(--muted);margin-bottom:24px}
/* shield */
.shield-wrap{flex-shrink:0;text-align:center;padding-top:4px}
.shield-img{width:130px;height:auto;max-height:160px;object-fit:contain;
filter:drop-shadow(0 2px 12px rgba(0,0,0,.7));border-radius:2px}
.shield-caption{font-size:.6rem;color:var(--muted);margin-top:7px;line-height:1.4;max-width:130px}
@media(max-width:560px){.hero-inner{flex-direction:column-reverse;gap:20px}.shield-wrap{align-self:center}}
.badges{display:flex;flex-wrap:wrap;gap:8px;margin-bottom:0}
.badge{font-size:.7rem;letter-spacing:.1em;text-transform:uppercase;padding:4px 10px;
border-radius:99px;border:1px solid var(--line);color:var(--muted)}
.badge.royal{border-color:#e8b820;color:#e8b820}
.badge.noble{border-color:#c83040;color:#c83040}
.badge.military{border-color:#2d78d8;color:#2d78d8}
/* sections */
.section{max-width:900px;margin:0 auto;padding:36px 28px}
.section h2{font-size:1.1rem;font-weight:700;letter-spacing:.08em;text-transform:uppercase;
color:var(--muted);margin-bottom:20px;border-bottom:1px solid var(--line);padding-bottom:10px}
/* connection card */
.connect-card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:22px 24px}
.connect-label{font-size:.72rem;letter-spacing:.14em;text-transform:uppercase;color:var(--gold);
margin-bottom:4px;display:block}
.connect-rel{font-size:1.05rem;font-weight:700;color:var(--parch);margin-bottom:16px}
/* path chain */
.path-chain{display:flex;flex-direction:column;gap:0}
.path-step{display:flex;align-items:flex-start;gap:12px;padding:6px 0}
.path-dot{width:8px;height:8px;border-radius:50%;background:var(--gold);margin-top:5px;flex-shrink:0}
.path-dot.start{background:var(--gold2);width:10px;height:10px;margin-top:4px}
.path-dot.end{background:#c83040;width:10px;height:10px;margin-top:4px}
.path-line-wrap{display:flex;flex-direction:column;align-items:center;gap:0}
.path-vline{width:1px;height:16px;background:var(--line);margin:0 auto}
.path-info{flex:1}
.path-name{font-size:.88rem;color:var(--parch);font-weight:500}
.path-meta{font-size:.72rem;color:var(--muted);margin-top:2px}
/* history */
.history-body p{font-size:.9rem;line-height:1.7;color:var(--parch);margin-bottom:14px}
.history-body strong{color:var(--parch)}
.history-body em{color:var(--gold)}
/* members table */
.member-table{width:100%;border-collapse:collapse;font-size:.83rem}
.member-table th{text-align:left;font-size:.68rem;letter-spacing:.12em;text-transform:uppercase;
color:var(--muted);padding:8px 10px;border-bottom:1px solid var(--line)}
.member-table td{padding:9px 10px;border-bottom:1px solid rgba(200,168,75,.07);vertical-align:top}
.member-table tr:hover td{background:rgba(200,168,75,.04)}
.m-name{color:var(--parch);font-weight:500}
.m-titles{color:var(--muted);font-size:.78rem;margin-top:2px}
.cat-badge{font-size:.65rem;letter-spacing:.08em;text-transform:uppercase;padding:2px 7px;
border-radius:99px;border:1px solid currentColor;white-space:nowrap}
.cat-royal{color:#e8b820;border-color:#e8b820}
.cat-noble{color:#c83040;border-color:#c83040}
.cat-military{color:#2d78d8;border-color:#2d78d8}
.cat-official{color:#18a870;border-color:#18a870}
.cat-untitled{color:#7a6e5a;border-color:#7a6e5a}
.gen-chip{font-size:.72rem;color:var(--muted);background:rgba(200,168,75,.08);
padding:2px 7px;border-radius:4px;white-space:nowrap}
/* index grid */
.house-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:16px}
.house-card{background:var(--card);border:1px solid var(--line);border-radius:8px;
padding:18px 20px;text-decoration:none;display:block;transition:border-color .2s}
.house-card:hover{border-color:var(--gold);text-decoration:none}
.hc-label{font-size:.68rem;letter-spacing:.12em;text-transform:uppercase;color:var(--gold);
margin-bottom:4px}
.hc-name{font-size:1rem;font-weight:700;color:var(--parch);margin-bottom:6px}
.hc-meta{font-size:.76rem;color:var(--muted)}
/* footer */
footer{text-align:center;padding:28px;font-size:.76rem;color:var(--muted);
border-top:1px solid var(--line);margin-top:40px}
"""

# ── helpers ───────────────────────────────────────────────────────────────────

def slugify(s):
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = re.sub(r"[^a-z0-9]+", "-", s.lower())
    return s.strip("-")

def rel_label(gen):
    if gen == 1: return "parent"
    if gen == 2: return "grandparent"
    if gen == 3: return "great-grandparent"
    return f"{gen-2}th great-grandparent"

def era_label(members):
    births = [n["birth"] for n in members if n.get("birth")]
    if not births: return "dates unknown"
    return f"c. {min(births)}–{max(births)} AD"

def cat_badge(cat):
    cat = (cat or "untitled").lower()
    label = {"royal":"Royalty","noble":"Nobility","military":"Military",
              "official":"Civic","untitled":"Untitled","clergy":"Clergy","indigenous":"Indigenous"}.get(cat, cat.title())
    return f'<span class="cat-badge cat-{cat}">{label}</span>'

def house_type_badge(members):
    cats = collections.Counter(n.get("cat","untitled") for n in members)
    out = []
    if cats.get("royal",0) > 0: out.append('<span class="badge royal">Royal</span>')
    if cats.get("noble",0) > 0: out.append('<span class="badge noble">Noble</span>')
    if cats.get("military",0) > 0: out.append('<span class="badge military">Military</span>')
    return "".join(out) or '<span class="badge">Untitled</span>'

def esc(s):
    return str(s).replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")

# ── load graph ────────────────────────────────────────────────────────────────

with open(TREE_FILE, encoding="utf-8") as f:
    raw = f.read()

m = re.search(r'const GRAPH\s*=\s*(\{.*?\});', raw, re.DOTALL)
graph = json.loads(m.group(1))
nodes, edges = graph["nodes"], graph["edges"]
by_id = {n["id"]: n for n in nodes}

# BFS from Antonio upward through ancestors
parents_of = defaultdict(list)
for e in edges:
    parents_of[e["t"]].append(e["s"])

dist = {0: 0}
prev = {0: None}
queue = deque([0])
while queue:
    cur = queue.popleft()
    for par in parents_of[cur]:
        if par not in dist:
            dist[par] = dist[cur] + 1
            prev[par] = cur
            queue.append(par)

def get_path(nid):
    path = []
    cur = nid
    while cur is not None:
        path.append(cur)
        cur = prev.get(cur)
    return list(reversed(path))

# ── group by house ────────────────────────────────────────────────────────────

house_nodes = defaultdict(list)
for n in nodes:
    h = n.get("house","").strip()
    if h:
        house_nodes[h].append(n)

# Filter to houses with ≥3 members
houses = {h: ns for h, ns in house_nodes.items() if len(ns) >= 3}

# ── load shield image cache ───────────────────────────────────────────────────

SHIELDS_FILE = os.path.join(HERE, "house_shields.json")
SHIELDS = {}
if os.path.exists(SHIELDS_FILE):
    with open(SHIELDS_FILE) as f:
        SHIELDS = json.load(f)

# ── generate individual house page ───────────────────────────────────────────

def make_house_page(house_name, members):
    slug = slugify(house_name)

    # Sort members oldest-first
    members_sorted = sorted(members, key=lambda n: -(n.get("birth") or 0))

    # Find closest reachable member
    reachable = [(dist[n["id"]], n) for n in members if n["id"] in dist]
    if reachable:
        closest_dist, closest = min(reachable, key=lambda x: x[0])
        path_ids = get_path(closest["id"])
    else:
        closest = members_sorted[0]
        closest_dist = closest.get("gen", "?")
        path_ids = []

    rel = rel_label(closest.get("gen", 0))
    era = era_label(members)

    # Shield image
    shield_data = SHIELDS.get(slug)
    if shield_data and isinstance(shield_data, dict):
        src  = shield_data["url"]
        cap  = shield_data.get("caption","").replace("Arms of the House of "+house_name+" — ","").replace("Wikimedia Commons","Wikimedia Commons")
        shield_html = (
            f'<div class="shield-wrap">'
            f'<img class="shield-img" src="{esc(src)}" alt="Arms of the House of {esc(house_name)}" loading="lazy">'
            f'<div class="shield-caption">{esc(cap)}</div>'
            f'</div>'
        )
    else:
        shield_html = ""

    # Connection path HTML (show max 12 steps then skip to end)
    path_html = ""
    if path_ids:
        MAX_SHOWN = 14
        ids_to_show = path_ids
        skipped = 0
        if len(path_ids) > MAX_SHOWN:
            skipped = len(path_ids) - MAX_SHOWN
            ids_to_show = path_ids[:7] + path_ids[-7:]

        for i, nid in enumerate(ids_to_show):
            n = by_id.get(nid, {})
            name = esc(n.get("name","Unknown"))
            birth = n.get("birth")
            gen   = n.get("gen", "?")
            meta  = f"b. {birth}" if birth else ""
            if gen != "?":
                meta += (", " if meta else "") + f"gen {gen}"

            is_start = (nid == 0)
            is_end   = (nid == closest["id"])
            dot_cls  = "start" if is_start else ("end" if is_end else "path-dot")

            path_html += f"""
            <div class="path-step">
              <div style="display:flex;flex-direction:column;align-items:center">
                <div class="{dot_cls}" style="{'width:10px;height:10px;' if is_start or is_end else ''}border-radius:50%;background:{'#e8b820' if is_start else '#c83040' if is_end else 'var(--gold)'};margin-top:5px;flex-shrink:0;width:{'10' if is_start or is_end else '8'}px;height:{'10' if is_start or is_end else '8'}px"></div>
                {'<div class="path-vline"></div>' if i < len(ids_to_show)-1 else ''}
              </div>
              <div class="path-info">
                <div class="path-name">{"⚜ " if is_start else ""}{name}</div>
                <div class="path-meta">{meta}</div>
              </div>
            </div>"""

            if skipped and i == 6:
                path_html += f"""
            <div class="path-step">
              <div style="display:flex;flex-direction:column;align-items:center">
                <div style="width:4px;height:4px;border-radius:50%;background:var(--muted);margin-top:8px;flex-shrink:0"></div>
                <div class="path-vline"></div>
              </div>
              <div class="path-info" style="padding-top:6px">
                <div class="path-meta">· · · {skipped} ancestors · · ·</div>
              </div>
            </div>"""

    # Members table HTML
    table_rows = ""
    for n in members_sorted:
        birth = n.get("birth") or "—"
        death = n.get("death") or "—"
        titles = esc(n.get("titles","") or "")
        gen = n.get("gen","?")
        cat = n.get("cat","untitled")
        table_rows += f"""
          <tr>
            <td><div class="m-name">{esc(n['name'])}</div>
                {'<div class="m-titles">'+titles+'</div>' if titles else ''}</td>
            <td style="white-space:nowrap">{birth}</td>
            <td style="white-space:nowrap">{death}</td>
            <td><span class="gen-chip">gen {gen}</span></td>
            <td>{cat_badge(cat)}</td>
          </tr>"""

    # History
    hist_key = house_name.lower()
    history_html = HISTORY.get(hist_key, "")
    if not history_html:
        # Auto-generate
        oldest = members_sorted[0]
        newest = members_sorted[-1]
        cats = collections.Counter(n.get("cat","untitled") for n in members)
        loc = oldest.get("country","") or ""
        ob = oldest.get("birth","?")
        history_html = f"""<p>The House of <strong>{esc(house_name)}</strong> is represented in your family tree by
        {len(members)} documented ancestors spanning the period {era}.
        {'The oldest known member, ' + esc(oldest['name']) + (' (b. '+str(ob)+')' if ob else '') + ', lived during the ' + ('early medieval' if isinstance(ob,int) and ob < 1000 else 'high medieval' if isinstance(ob,int) and ob < 1200 else 'late medieval') + ' period.' if ob else ''}
        {('Members held royal titles.' if cats.get('royal',0)>1 else 'Members held noble titles.' if cats.get('noble',0)>1 else '')}
        {'Geographic roots in ' + esc(loc) + '.' if loc else ''}</p>"""

    badges_html = house_type_badge(members)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>House of {esc(house_name)} — Villanueva Family Tree</title>
<style>{CSS}</style>
</head>
<body>

<nav class="topnav">
  <a href="../../index.html">Home</a>
  <span class="sep">›</span>
  <a href="index.html">Noble Houses</a>
  <span class="sep">›</span>
  <span style="color:var(--parch)">{esc(house_name)}</span>
</nav>

<div class="hero">
  <div class="hero-inner">
    <div class="hero-text">
      <span class="eyebrow">Noble &amp; Royal House</span>
      <h1>House of {esc(house_name)}</h1>
      <p class="subtitle">{len(members)} ancestors · {era} · {rel_label(closest.get('gen',0))} of Antonio Jasso</p>
      <div class="badges">{badges_html}</div>
    </div>
    {shield_html}
  </div>
</div>

<div class="section">
  <h2>Your Connection</h2>
  <div class="connect-card">
    <span class="connect-label">Nearest ancestor from this house</span>
    <div class="connect-rel">{esc(closest['name'])} &mdash; your {esc(rel)}</div>
    <div class="path-chain">{path_html}</div>
  </div>
</div>

{'<div class="section"><h2>Historical Overview</h2><div class="history-body">' + history_html + '</div></div>' if history_html else ''}

<div class="section">
  <h2>Ancestors from This House ({len(members)})</h2>
  <table class="member-table">
    <thead>
      <tr>
        <th>Name</th>
        <th>Born</th>
        <th>Died</th>
        <th>Generation</th>
        <th>Role</th>
      </tr>
    </thead>
    <tbody>{table_rows}</tbody>
  </table>
</div>

<footer>
  <a href="../../index.html">Villanueva Family Tree</a> &nbsp;·&nbsp;
  <a href="index.html">All Houses</a> &nbsp;·&nbsp;
  <a href="../antonio-jasso-lineage.html">Open Full Tree</a>
</footer>
</body>
</html>"""

    out = os.path.join(OUT_DIR, slug + ".html")
    with open(out, "w", encoding="utf-8") as f:
        f.write(html)
    return slug

# ── generate index page ───────────────────────────────────────────────────────

def make_index(house_slugs):
    # Sort houses: first by royal count desc, then noble count, then total
    def sort_key(item):
        h, ns = item
        cats = collections.Counter(n.get("cat","") for n in ns)
        return (-cats.get("royal",0), -cats.get("noble",0), -len(ns))

    sorted_houses = sorted(houses.items(), key=sort_key)

    cards = ""
    for house_name, members in sorted_houses:
        slug = slugify(house_name)
        if slug not in house_slugs: continue
        cats = collections.Counter(n.get("cat","") for n in members)
        reachable = [(dist[n["id"]], n) for n in members if n["id"] in dist]
        if reachable:
            _, closest = min(reachable, key=lambda x: x[0])
            rel = rel_label(closest.get("gen",0))
        else:
            closest = members[0]; rel = "ancestor"
        era = era_label(members)

        badge = ""
        if cats.get("royal",0) > 0: badge = '<span class="badge royal" style="font-size:.6rem;padding:2px 7px">Royal</span>'
        elif cats.get("noble",0) > 0: badge = '<span class="badge noble" style="font-size:.6rem;padding:2px 7px">Noble</span>'

        cards += f"""
      <a class="house-card" href="{slug}.html">
        <div class="hc-label">{badge} {len(members)} ancestors · {era}</div>
        <div class="hc-name">House of {esc(house_name)}</div>
        <div class="hc-meta">Nearest: {esc(closest['name'][:45])}<br>{rel} of Antonio Jasso</div>
      </a>"""

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Noble &amp; Royal Houses — Villanueva Family Tree</title>
<style>{CSS}
.search-wrap{{margin-bottom:24px}}
#search{{width:100%;background:var(--card);border:1px solid var(--line);border-radius:6px;
padding:10px 14px;color:var(--parch);font-size:.88rem;outline:none}}
#search:focus{{border-color:var(--gold)}}
.house-card.hidden{{display:none}}
</style>
</head>
<body>

<nav class="topnav">
  <a href="../../index.html">Home</a>
  <span class="sep">›</span>
  <span style="color:var(--parch)">Noble Houses</span>
</nav>

<div class="hero">
  <span class="eyebrow">Your Ancestry</span>
  <h1>Noble &amp; Royal Houses</h1>
  <p class="subtitle">{len(sorted_houses)} houses · documented in Antonio Jasso's family tree · each page shows your connection and history</p>
</div>

<div class="section">
  <div class="search-wrap">
    <input id="search" type="text" placeholder="Search houses…" oninput="filterHouses(this.value)">
  </div>
  <div class="house-grid" id="grid">{cards}
  </div>
</div>

<footer>
  <a href="../../index.html">Villanueva Family Tree</a> &nbsp;·&nbsp;
  <a href="../antonio-jasso-lineage.html">Open Full Tree</a>
</footer>

<script>
function filterHouses(q) {{
  q = q.toLowerCase();
  document.querySelectorAll('.house-card').forEach(c => {{
    c.classList.toggle('hidden', q && !c.textContent.toLowerCase().includes(q));
  }});
}}
</script>
</body>
</html>"""

    with open(os.path.join(OUT_DIR, "index.html"), "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Written: houses/index.html")

# ── run ───────────────────────────────────────────────────────────────────────

print(f"Generating pages for {len(houses)} houses…")
slugs = set()
for house_name, members in sorted(houses.items()):
    slug = make_house_page(house_name, members)
    slugs.add(slug)
    print(f"  ✓ {slug}.html  ({len(members)} members)")

make_index(slugs)
print(f"\nDone. {len(slugs)} house pages + index → ancestor_mappings/houses/")
