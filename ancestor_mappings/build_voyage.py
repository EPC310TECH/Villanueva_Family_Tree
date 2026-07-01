#!/usr/bin/env python3
"""
Parse Catálogo de Pasajeros a Indias (8 volumes, 1509-1599)
and generate voyage.html — a ship-manifest page showing
passenger records matched against the Villanueva family tree.
"""

import re, json, os, unicodedata
from collections import defaultdict

# ── Paths ────────────────────────────────────────────────────────────────
TXT_DIR   = "/Users/xx/Downloads/Catalogue of passangers to the indies/txt"
TREE_HTML = "/Users/xx/Geneology/ancestor_mappings/the-tree.html"
OUT_HTML  = "/Users/xx/Geneology/ancestor_mappings/voyage.html"

# Volume label derived from filename — order matters: check most-specific first
VOLUME_KEYS = [
    ("Volumen_V_Tomo_II", "V (T.II)", "1573–1577"),
    ("Volumen_V_Tomo_I",  "V (T.I)",  "1567–1572"),
    ("Volumen_VII",       "VII",       "1586–1599"),
    ("Volumen_VI",        "VI",        "1578–1585"),
    ("Volumen_IV",        "IV",        "1560–1566"),
    ("Volumen_III",       "III",       "1539–1559"),
    ("Volumen_II",        "II",        "1535–1538"),
    ("Volumen_I",         "I",         "1509–1534"),
]

# ── Distinctive family surnames to search ────────────────────────────────
# Keys are lowercased/accent-stripped for matching against norm'd entry text.
# Values: (display-name-of-tree-ancestor, priority 1=high 2=medium)
FAMILY_SURNAMES = {
    "temiño":       ("Baltasar Temiño y Bañuelos", 1),
    "temino":       ("Baltasar Temiño y Bañuelos", 1),
    "bañuelos":     ("Baltasar Temiño y Bañuelos", 1),
    "banuelos":     ("Baltasar Temiño y Bañuelos", 1),
    "zaldivar":     ("Juan de Zaldivar y Oñate", 1),
    "zaldívar":     ("Juan de Zaldivar y Oñate", 1),
    "saldivar":     ("Diego Ruiz Temiño de Bañuelos y Saldivar", 1),
    "bobadilla":    ("Francisco de Bobadilla, Conquistador", 1),
    "bobadila":     ("Francisco de Bobadilla, Conquistador", 1),
    "gamboa":       ("Capitan Juan de Gamboa", 1),
    "miramontes":   ("Fernando de Haro Miramontes, Capitan", 1),
    "oñate":        ("Juan de Zaldivar y Oñate", 1),
    "onate":        ("Juan de Zaldivar y Oñate", 1),
    "recalde":      ("Teresa de Recalde", 1),
    "alcocer":      ("Beatriz Alcocer Bañuelos", 1),
    "villanueva":   ("Alonso de Villanueva (1500)", 2),
    "arellano":     ("Felipe V Conde de Aguilar, Ramírez de Arellano", 2),
    "jimena":       ("Capitan Juan López de Jimena", 2),
    "maldonado":    ("Alonzo Del Castillo Maldonado", 2),
    "marín":        ("Conquistador y Capitán Luis Marín", 2),
    "marin":        ("Conquistador y Capitán Luis Marín", 2),
    "sarmiento":    ("Pedro López de Ayala y Sarmiento", 2),
}

# ── Normalization helpers ────────────────────────────────────────────────
def strip_acc(s):
    return "".join(c for c in unicodedata.normalize("NFD", s)
                   if unicodedata.category(c) != "Mn")

def norm(s):
    return strip_acc(s).lower().strip()

# ── Field-extraction patterns ────────────────────────────────────────────
DEST_PAT = re.compile(
    r"\b(?:"
    r"al?\s+(?:perú|peru|nuevo\s+reino\s+de\s+granada|nuevo\s+m[eé]xico|darien)|"
    r"a(?:\s+la)?\s+(?:nueva\s+españa|nueva\s+galicia|santo\s+domingo|tierra\s+firme|"
    r"florida|cuba|puerto\s+rico|quito|venezuela|cartagena|santa\s+marta|chile|"
    r"filipinas|brasil|yucat[aá]n|campeche|honduras|nicaragua|guatemala|"
    r"panam[aá]|nombre\s+de\s+dios|buenos\s+aires|bogot[aá]|r[ií]o\s+de\s+la\s+plata)"
    r")",
    re.I,
)
DEST_CLEAN = {
    "nueva españa":           "Nueva España (México)",
    "nueva espana":           "Nueva España (México)",
    "perú":                   "Perú",
    "peru":                   "Perú",
    "santo domingo":          "Santo Domingo",
    "tierra firme":           "Tierra Firme",
    "cuba":                   "Cuba",
    "puerto rico":            "Puerto Rico",
    "nueva galicia":          "Nueva Galicia",
    "quito":                  "Quito",
    "venezuela":              "Venezuela",
    "chile":                  "Chile",
    "filipinas":              "Filipinas",
    "brasil":                 "Brasil",
    "florida":                "Florida",
    "yucatan":                "Yucatán",
    "yucatán":                "Yucatán",
    "campeche":               "Campeche",
    "honduras":               "Honduras",
    "nicaragua":              "Nicaragua",
    "guatemala":              "Guatemala",
    "panamá":                 "Panamá",
    "panama":                 "Panamá",
    "nombre de dios":         "Nombre de Dios",
    "buenos aires":           "Buenos Aires",
    "cartagena":              "Cartagena",
    "santa marta":            "Santa Marta",
    "río de la plata":        "Río de la Plata",
    "rio de la plata":        "Río de la Plata",
    "nuevo reino de granada": "Nuevo Reino de Granada",
    "nuevo mexico":           "Nuevo México",
    "nuevo méxico":           "Nuevo México",
    "darien":                 "Darién",
}

DATE_PAT = re.compile(
    r"[—\-–]\s*(\d{1,2})\s+"
    r"(enero|febrero|marzo|abril|mayo|junio|julio|agosto|sept(?:iembre|iembre)|"
    r"oct(?:ubre)?|nov(?:iembre)?|dic(?:iembre)?)\b",
    re.I,
)
MONTH_ES = {
    "enero":1, "febrero":2, "marzo":3, "abril":4, "mayo":5, "junio":6,
    "julio":7, "agosto":8, "septiembre":9, "setiembre":9,
    "octubre":10, "oct":10, "noviembre":11, "nov":11, "diciembre":12, "dic":12,
}

ORIGIN_PAT = re.compile(
    r"\bnatural(?:es)?\s+(?:y\s+vecin(?:o|a|os|as)\s+)?de\s+([^,;.()]+)"
    r"|\bvecin(?:o|a|os|as)\s+(?:y\s+natural(?:es)?\s+)?de\s+([^,;.()]+)",
    re.I,
)
PARENTS_PAT = re.compile(
    r"\bhij(?:o|a)s?\s+de\s+(.+?)(?:\s*[,;]\s*(?:vecin|natural|a\s|al\s|con\s|y\s+sus?\s+hij)|\s*[.—]|\Z)",
    re.I,
)

# ── Parsing ───────────────────────────────────────────────────────────────
YEAR_HDR   = re.compile(r'(?:A[ÑN][OÑ]|Año|año)\s+(\d{4})', re.IGNORECASE)
# Only match standalone year lines 1500–1599 (actual data range)
YEAR_ALONE = re.compile(r'(?:^|\n)\s*(15[0-9]{2})\s*\n', re.M)

EARLY_ENTRY = re.compile(r'(?:^|\n)\s*(\d{1,5})\s*[.·]\s*[—\-–]', re.M)
LATE_ENTRY  = re.compile(r'(?:^|\n)\s*(\d{1,5})\s*[.,]\s+([A-ZÁÉÍÓÚÑÜ])', re.M)

def join_lines(text):
    # Re-join words broken at line ends with hyphen
    text = re.sub(r'([a-záéíóúñü])-\s*\n\s*([a-záéíóúñü])', r'\1\2', text, flags=re.I)
    text = re.sub(r'\n', ' ', text)
    return re.sub(r'\s{2,}', ' ', text).strip()

def extract_destination(text):
    m = DEST_PAT.search(text)
    if not m:
        return ""
    raw = norm(m.group(0))
    for key, clean in DEST_CLEAN.items():
        if key in raw:
            return clean
    return m.group(0).strip().title()

def extract_date(text):
    m = DATE_PAT.search(text)
    if m:
        return int(m.group(1)), MONTH_ES.get(norm(m.group(2))[:3], 0)
    return 0, 0

def extract_origin(text):
    m = ORIGIN_PAT.search(text)
    if m:
        v = (m.group(1) or m.group(2) or "").strip().rstrip(".,;)")
        # truncate at "hijo", "hija", "natural", etc.
        v = re.split(r'\s+(?:hijo|hija|natural|vecino|al\s|a\s+[A-Z])', v, flags=re.I)[0]
        return v.strip().rstrip(".,;) ")
    return ""

def extract_parents(text):
    m = PARENTS_PAT.search(text)
    if m:
        p = m.group(1).strip()
        # limit length
        return p[:120].rstrip(".,;) ")
    return ""

def clean_name(raw, is_late=False):
    """Title-case, strip OCR artifacts, remove leading specials."""
    raw = re.sub(r'-\s*\n\s*', '', raw)  # hyphen line-break
    raw = re.sub(r'\s+', ' ', raw).strip()
    raw = re.sub(r'^[\W_]+', '', raw).strip()  # leading punctuation/symbols
    raw = raw.strip(",.;:—–-·")
    # Fix doubled capital from OCR (e.g. "EFrancisco" → "Francisco")
    raw = re.sub(r'^([A-Z]{2})([a-záéíóúñü])',
                 lambda m: m.group(2).upper() + m.group(1)[1:] + m.group(2)
                 if len(m.group(1)) == 2 else m.group(0), raw)
    if is_late and raw == raw.upper() and len(raw) > 2:
        # ALL-CAPS → Title Case
        raw = raw.title()
    return raw

def build_year_map(text):
    """Return sorted list of (position, year) for year headers in text."""
    ymap = {}
    for m in YEAR_HDR.finditer(text):
        yr = int(m.group(1))
        if 1490 <= yr <= 1620:    # ignore prologue/publication dates
            ymap[m.start()] = yr
    for m in YEAR_ALONE.finditer(text):
        ymap[m.start()] = int(m.group(1))
    return sorted(ymap.items())

def year_at(pos, year_map):
    yr = None
    for p, y in year_map:
        if p <= pos:
            yr = y
        else:
            break
    return yr

def parse_volume(path, vol_label):
    with open(path, encoding="utf-8", errors="replace") as f:
        text = f.read()

    early_c = len(EARLY_ENTRY.findall(text))
    late_c  = len(LATE_ENTRY.findall(text))
    is_late = late_c > early_c

    year_map = build_year_map(text)

    if is_late:
        spans = list(LATE_ENTRY.finditer(text))
    else:
        spans = list(EARLY_ENTRY.finditer(text))

    parsed = []
    for i, m in enumerate(spans):
        num   = int(m.group(1))
        start = m.end() if not is_late else (m.start() + len(m.group(0)) - len(m.group(2)))
        end   = spans[i+1].start() if i+1 < len(spans) else len(text)
        raw   = text[start:end]
        pos   = m.start()

        joined = join_lines(raw)

        # Extract name: text before first field marker
        name_end = len(joined)
        for kw in [", natural ", ", vecino ", ", vecina ", ", vecinos ", " natural de ",
                   " vecino de ", ", hijo ", ", hija ", ", soltero", ", casado",
                   ", clérigo", ", mercader", ", labrador", ", escudero"]:
            idx = joined.lower().find(kw)
            if 0 < idx < name_end:
                name_end = idx
        name = clean_name(joined[:name_end], is_late)
        if not name or len(name) < 3:
            continue

        # Skip index entries: they contain many comma-separated numbers
        ref_count = len(re.findall(r'\d[\.,]\d{3}', joined))
        if ref_count >= 4 or (ref_count >= 2 and ':' in joined[:80]):
            continue

        yr        = year_at(pos, year_map)
        day, mon  = extract_date(joined)
        origin    = extract_origin(joined)
        parents   = extract_parents(joined)
        dest      = extract_destination(joined)

        parsed.append({
            "num":         num,
            "name":        name,
            "origin":      origin,
            "destination": dest,
            "parents":     parents,
            "year":        yr,
            "day":         day,
            "month":       mon,
            "vol":         vol_label,
            "raw":         joined[:320],
        })

    return parsed

def load_all_volumes():
    all_entries = []
    for fname in sorted(os.listdir(TXT_DIR)):
        if not fname.endswith(".txt"):
            continue
        path = os.path.join(TXT_DIR, fname)
        vol_label = "?"
        for key, label, _ in VOLUME_KEYS:
            if key in fname:
                vol_label = label
                break
        print(f"  {fname[-52:]:52s} ({vol_label:7s})", end=" ", flush=True)
        entries = parse_volume(path, vol_label)
        print(f"→ {len(entries):,}")
        all_entries.extend(entries)
    return all_entries

# ── Matching ──────────────────────────────────────────────────────────────
def match_entry(entry):
    """Return list of (surname_key, display_name, priority) matches."""
    text = norm(entry["name"] + " " + entry.get("parents", ""))
    hits = []
    seen = set()
    for sur_key, (display, priority) in FAMILY_SURNAMES.items():
        sur_normed = norm(sur_key)
        if re.search(r'\b' + re.escape(sur_normed) + r'\b', text):
            if display not in seen:
                hits.append((sur_key, display, priority))
                seen.add(display)
    return hits

# ── HTML ──────────────────────────────────────────────────────────────────
MONTH_LONG = ["","enero","febrero","marzo","abril","mayo","junio",
              "julio","agosto","septiembre","octubre","noviembre","diciembre"]

DEST_COLORS = {
    "Nueva España (México)": "#1a5e35",
    "Perú":                  "#6b1f1f",
    "Santo Domingo":         "#1a3a6b",
    "Tierra Firme":          "#5e3e10",
    "Cuba":                  "#1a5e5e",
    "Puerto Rico":           "#4a1a6b",
    "Nueva Galicia":         "#0f4a2a",
    "Quito":                 "#5e4a10",
    "Venezuela":             "#3a1a6b",
    "Chile":                 "#104a6b",
    "Filipinas":             "#6b104a",
    "Brasil":                "#3a5e10",
    "Florida":               "#4a4a10",
    "Yucatán":               "#106b3a",
    "Panamá":                "#5e2a10",
    "Cartagena":             "#2a4a5e",
}

VOL_ORDER = ["I","II","III","IV","V (T.I)","V (T.II)","VI","VII"]

def dest_badge(dest):
    if not dest:
        return ""
    color = DEST_COLORS.get(dest, "#444")
    return f'<span class="dest-badge" style="background:{color}">{dest}</span>'

def fmt_date(e):
    if e["day"] and e["month"] and e["year"]:
        return f"{e['day']} {MONTH_LONG[e['month']]} {e['year']}"
    return str(e["year"]) if e["year"] else "—"

def entry_html(e, priority):
    matches      = e.get("matches", [])
    match_names  = sorted({m[1] for m in matches})
    match_html   = ""
    if match_names:
        items = "".join(f"<li>{n}</li>" for n in match_names[:4])
        match_html = f'<div class="match-tag">↳ <ul>{items}</ul></div>'

    parents_html = f'<p class="parents">hijo/a de {e["parents"]}</p>' if e["parents"] else ""
    origin_html  = f'<span class="field">Origen: {e["origin"]}</span>' if e["origin"] else ""
    raw_safe     = e["raw"][:240].replace("<","&lt;").replace(">","&gt;")
    hl_cls       = " priority-1" if priority == 1 else ""

    return f"""\
<div class="card{hl_cls}" data-dest="{e.get('destination','')}" \
data-vol="{e.get('vol','')}" data-year="{e.get('year',0)}">
  <div class="card-head">
    <span class="entry-num">#{e['num']}</span>
    <span class="vol-tag">Vol. {e['vol']}</span>
    <span class="date-tag">{fmt_date(e)}</span>
    {dest_badge(e['destination'])}
  </div>
  <div class="entry-name">{e['name']}</div>
  {parents_html}
  <div class="entry-meta">{origin_html}</div>
  <details><summary>Texto original</summary><blockquote>{raw_safe}…</blockquote></details>
  {match_html}
</div>"""

def build_html(all_entries, matched_with_priority):
    total   = len(all_entries)
    n_match = len(matched_with_priority)

    # Stats
    dest_counts = defaultdict(int)
    vol_counts  = defaultdict(int)
    yr_min, yr_max = 9999, 0
    for e in all_entries:
        if e.get("destination"):
            dest_counts[e["destination"]] += 1
        vol_counts[e["vol"]] += 1
        if e.get("year"):
            yr_min = min(yr_min, e["year"])
            yr_max = max(yr_max, e["year"])

    top_dests = sorted(dest_counts.items(), key=lambda x: -x[1])[:8]
    dest_stat_html = " ".join(
        f'{dest_badge(d)} <span class="sn">{n:,}</span>'
        for d, n in top_dests
    )

    vol_display_order = [
        ("I",       "1509–1534"), ("II",      "1535–1538"),
        ("III",     "1539–1559"), ("IV",      "1560–1566"),
        ("V (T.I)", "1567–1572"), ("V (T.II)","1573–1577"),
        ("VI",      "1578–1585"), ("VII",     "1586–1599"),
    ]
    vol_table_rows = ""
    for label, years in vol_display_order:
        c   = vol_counts.get(label, 0)
        fmt = "Mayúsculas" if label not in ("I","II","III") else "Título"
        vol_table_rows += f"<tr><td>Vol. {label}</td><td>{years}</td><td>{c:,}</td><td>{fmt}</td></tr>\n"

    # Priority groups
    p1 = [(e, p) for e, p in matched_with_priority if p == 1]
    p2 = [(e, p) for e, p in matched_with_priority if p == 2]

    def cards(pairs):
        return "\n".join(entry_html(e, p) for e, p in pairs)

    p1_html = cards(p1)
    p2_html = cards(p2)

    n_p1  = len(p1)
    n_p2  = len(p2)

    # Surname legend
    sur_legend = ""
    seen_leg = set()
    for key, label, _ in VOLUME_KEYS:
        pass
    for sur_key, (display, prio) in sorted(FAMILY_SURNAMES.items(), key=lambda x: (x[1][1], x[0])):
        if display not in seen_leg:
            seen_leg.add(display)
            badge_cls = "sur-p1" if prio == 1 else "sur-p2"
            sur_legend += f'<span class="sur-item {badge_cls}">{display}</span> '

    return f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Pasajeros a Indias — Villanueva Family Tree</title>
<style>
:root {{
  --bg:     #0e0b07;
  --parch:  #181410;
  --card:   #1d1912;
  --hl:     #1a1506;
  --border: #332c1e;
  --ink:    #e2d8be;
  --muted:  #7a7060;
  --gold:   #c8a245;
  --teal:   #2e7a6a;
  --rust:   #8a3a25;
}}
*{{ box-sizing:border-box; margin:0; padding:0; }}
body{{ background:var(--bg); color:var(--ink); font-family:'Georgia',serif;
      font-size:14px; line-height:1.6; }}

/* NAV */
.nav{{ display:flex; align-items:center; gap:.8rem; padding:.5rem 1.4rem;
      background:#090705; border-bottom:1px solid var(--border); }}
.nav a{{ color:var(--gold); text-decoration:none; font-size:.82rem; }}
.nav a:hover{{ text-decoration:underline; }}
.nav .sep{{ color:var(--muted); }}

/* HERO */
.hero{{ text-align:center; padding:2.5rem 1rem 2rem;
       background:linear-gradient(180deg,#0a0704 0%,var(--parch) 100%);
       border-bottom:2px solid var(--border); position:relative; overflow:hidden; }}
.hero::before{{ content:''; position:absolute; inset:0;
  background:radial-gradient(ellipse 60% 50% at 50% 0%,#c8a24520,transparent);
  pointer-events:none; }}
.ship{{ font-size:3rem; display:block; margin-bottom:.4rem;
        filter:drop-shadow(0 0 16px #c8a24530); }}
h1{{ font-size:1.9rem; color:var(--gold); letter-spacing:.07em;
     text-shadow:0 0 30px #c8a24535; margin-bottom:.3rem; }}
.hero-sub{{ color:var(--muted); font-size:.9rem; font-style:italic; }}
.divider{{ width:50%; max-width:360px; height:1px;
  background:linear-gradient(90deg,transparent,var(--gold),transparent);
  margin:.8rem auto; }}

/* STATS */
.stats{{ display:flex; flex-wrap:wrap; gap:1.2rem; justify-content:center;
        padding:1.2rem 1.5rem; background:var(--parch);
        border-bottom:1px solid var(--border); }}
.stat{{ text-align:center; min-width:90px; }}
.stat .n{{ display:block; font-size:1.6rem; font-weight:bold; color:var(--gold); }}
.stat .l{{ font-size:.7rem; color:var(--muted); text-transform:uppercase; letter-spacing:.06em; }}
.dest-row{{ padding:.8rem 1.5rem; background:var(--card);
           border-bottom:1px solid var(--border);
           display:flex; flex-wrap:wrap; gap:.5rem 1rem; align-items:center;
           font-size:.8rem; }}
.sn{{ color:var(--muted); }}

/* SECTION */
.section{{ max-width:1100px; margin:0 auto; padding:1.8rem 1.2rem; }}
.sec-head{{ display:flex; align-items:baseline; gap:.8rem;
           border-bottom:1px solid var(--border);
           padding-bottom:.5rem; margin-bottom:1rem; }}
.sec-head h2{{ font-size:1.1rem; color:var(--gold); letter-spacing:.04em; }}
.sec-cnt{{ font-size:.75rem; color:var(--muted); }}

/* INTRO */
.intro{{ background:var(--card); border:1px solid var(--border);
        border-left:3px solid var(--gold);
        padding:.9rem 1.1rem; margin-bottom:1.4rem;
        font-size:.86rem; color:var(--muted); line-height:1.7; }}
.intro strong{{ color:var(--ink); }}

/* FILTER BAR */
.filters{{ display:flex; flex-wrap:wrap; gap:.5rem; margin-bottom:1rem; }}
.filters input, .filters select{{
  background:var(--card); border:1px solid var(--border);
  color:var(--ink); padding:.35rem .7rem; border-radius:4px; font-size:.83rem; }}
.filters input{{ width:185px; }}
.filters input:focus, .filters select:focus{{ outline:none; border-color:var(--gold); }}
#cnt-lbl{{ font-size:.78rem; color:var(--muted); align-self:center; }}

/* GRID */
.grid{{ display:grid; grid-template-columns:repeat(auto-fill,minmax(300px,1fr)); gap:.9rem; }}

/* CARD */
.card{{ background:var(--card); border:1px solid var(--border); border-radius:5px;
       padding:.9rem; transition:border-color .15s; }}
.card:hover{{ border-color:var(--muted); }}
.card.priority-1{{ background:var(--hl); border-color:var(--gold);
                  box-shadow:0 0 10px #c8a24518; }}
.card-head{{ display:flex; flex-wrap:wrap; align-items:center; gap:.35rem; margin-bottom:.45rem; }}
.entry-num{{ font-size:.72rem; color:var(--muted); font-style:italic; }}
.vol-tag{{ font-size:.68rem; color:var(--muted); padding:.08rem .4rem;
          border:1px solid var(--border); border-radius:3px; }}
.date-tag{{ font-size:.72rem; color:var(--muted); margin-left:auto; }}
.dest-badge{{ display:inline-block; padding:.12rem .45rem; border-radius:3px;
             font-size:.68rem; font-weight:bold; color:#fff; letter-spacing:.02em; }}
.entry-name{{ font-size:.95rem; font-weight:bold; margin-bottom:.3rem; }}
.parents{{ font-size:.78rem; color:var(--muted); font-style:italic; margin-bottom:.25rem; }}
.entry-meta{{ font-size:.76rem; color:var(--muted); }}
.field{{ color:#6a8070; }}
details{{ margin-top:.5rem; }}
details summary{{ font-size:.72rem; color:var(--muted); cursor:pointer; }}
details summary:hover{{ color:var(--ink); }}
blockquote{{ font-size:.72rem; color:var(--muted); font-family:monospace;
            border-left:2px solid var(--border); padding:.3rem .5rem;
            margin-top:.25rem; white-space:pre-wrap; word-break:break-word; }}
.match-tag{{ margin-top:.45rem; font-size:.74rem; color:#8abaa0;
            border-left:2px solid var(--teal); padding-left:.5rem; }}
.match-tag ul{{ margin:.15rem 0 0 .7rem; }}

/* BADGE */
.sur-item{{ display:inline-block; padding:.15rem .5rem; border-radius:3px;
           font-size:.75rem; margin:.15rem .1rem; }}
.sur-p1{{ background:#1a2e20; border:1px solid #2a5a38; color:#8abaa0; }}
.sur-p2{{ background:#1e1e2a; border:1px solid #3a3a5a; color:#8a8aaa; }}

/* TABLE */
.vol-tbl{{ width:100%; border-collapse:collapse; font-size:.8rem; }}
.vol-tbl th, .vol-tbl td{{ padding:.4rem .7rem; text-align:left;
  border-bottom:1px solid var(--border); }}
.vol-tbl th{{ color:var(--gold); font-size:.72rem; text-transform:uppercase; letter-spacing:.05em; }}
.vol-tbl tr:hover td{{ background:#181410; }}

/* BACK LINKS */
.links{{ display:flex; flex-wrap:wrap; gap:.6rem; }}
.back-link{{ display:inline-flex; align-items:center; gap:.35rem;
            color:var(--gold); text-decoration:none; font-size:.82rem;
            padding:.45rem .9rem; border:1px solid var(--border); border-radius:4px; }}
.back-link:hover{{ border-color:var(--gold); }}

footer{{ text-align:center; padding:1.8rem 1rem;
        color:var(--muted); font-size:.74rem;
        border-top:1px solid var(--border); }}
footer a{{ color:var(--gold); }}

.hidden{{ display:none !important; }}
@media(max-width:560px){{ h1{{ font-size:1.4rem; }} }}
</style>
</head>
<body>
<nav class="nav">
  <a href="../index.html">⌂ Inicio</a><span class="sep">›</span>
  <a href="the-tree.html">Árbol</a><span class="sep">›</span>
  <a href="migration-map.html">Mapa de Migración</a><span class="sep">›</span>
  <span>Pasajeros a Indias</span>
</nav>

<div class="hero">
  <span class="ship">⛵</span>
  <h1>Pasajeros a Indias</h1>
  <p class="hero-sub">Catálogo de Pasajeros a Indias · Archivo General de Indias, Sevilla · Siglos XVI–XVII</p>
  <div class="divider"></div>
  <p style="color:var(--muted);font-size:.83rem">
    Registros oficiales de los que obtuvieron licencia de la Casa de la Contratación<br>
    para pasar a las Américas — 1509 a 1599
  </p>
</div>

<div class="stats">
  <div class="stat"><span class="n">{total:,}</span><span class="l">Registros</span></div>
  <div class="stat"><span class="n">{yr_min}–{yr_max}</span><span class="l">Años</span></div>
  <div class="stat"><span class="n">8</span><span class="l">Volúmenes</span></div>
  <div class="stat"><span class="n" style="color:#8abaa0">{n_match:,}</span><span class="l">Con apellido familiar</span></div>
  <div class="stat"><span class="n" style="color:#c8a245">{n_p1:,}</span><span class="l">Apellido prioritario</span></div>
</div>

<div class="dest-row">
  <span style="color:var(--muted);margin-right:.3rem">Destinos:</span>
  {dest_stat_html}
</div>

<div class="section">
  <div class="intro">
    El <strong>Catálogo de Pasajeros a Indias</strong> contiene los asientos de las personas que
    obtuvieron licencia de la <strong>Casa de la Contratación de Sevilla</strong> para pasar a las
    Indias entre 1509 y 1599. Cada asiento registra el nombre del pasajero, su lugar de origen,
    los nombres de sus padres y el destino en el Nuevo Mundo.<br><br>
    Esta página muestra los registros cuyos nombres o apellidos coinciden con personas documentadas
    en el árbol genealógico <strong>Villanueva–Jasso</strong>. Los registros destacados en dorado
    corresponden a apellidos más distintivos de la familia.
    <br><br>
    Apellidos buscados: {sur_legend}
  </div>

  <div class="sec-head">
    <h2>Registros con Apellidos Prioritarios</h2>
    <span class="sec-cnt">{n_p1:,} registros · Temiño, Bañuelos, Zaldívar, Bobadilla, Oñate, Gamboa&hellip;</span>
  </div>

  <div class="filters">
    <input type="text" id="q1" placeholder="Buscar nombre…" oninput="filter('grid1')">
    <select id="d1" onchange="filter('grid1')">
      <option value="">Todos los destinos</option>
      <option>Nueva España (México)</option><option>Perú</option>
      <option>Santo Domingo</option><option>Tierra Firme</option>
      <option>Cuba</option><option>Puerto Rico</option><option>Nueva Galicia</option>
      <option>Venezuela</option><option>Chile</option><option>Filipinas</option>
    </select>
    <select id="v1" onchange="filter('grid1')">
      <option value="">Todos los volúmenes</option>
      <option>I</option><option>II</option><option>III</option><option>IV</option>
      <option>V (T.I)</option><option>V (T.II)</option><option>VI</option><option>VII</option>
    </select>
    <span id="cnt1" class="cnt-lbl"></span>
  </div>
  <div class="grid" id="grid1">{p1_html}</div>

  <div class="sec-head" style="margin-top:2.5rem">
    <h2>Otros Apellidos Familiares</h2>
    <span class="sec-cnt">{n_p2:,} registros · Villanueva, Arellano, Maldonado, Marín, Sarmiento&hellip;</span>
  </div>
  <div class="filters">
    <input type="text" id="q2" placeholder="Buscar nombre…" oninput="filter('grid2')">
    <select id="d2" onchange="filter('grid2')">
      <option value="">Todos los destinos</option>
      <option>Nueva España (México)</option><option>Perú</option>
      <option>Santo Domingo</option><option>Tierra Firme</option>
      <option>Cuba</option><option>Puerto Rico</option><option>Nueva Galicia</option>
      <option>Venezuela</option><option>Chile</option>
    </select>
    <select id="v2" onchange="filter('grid2')">
      <option value="">Todos los volúmenes</option>
      <option>I</option><option>II</option><option>III</option><option>IV</option>
      <option>V (T.I)</option><option>V (T.II)</option><option>VI</option><option>VII</option>
    </select>
    <span id="cnt2" class="cnt-lbl"></span>
  </div>
  <div class="grid" id="grid2">{p2_html}</div>
</div>

<div class="section" style="padding-top:0">
  <div class="sec-head"><h2>Sobre los Volúmenes</h2></div>
  <table class="vol-tbl">
    <thead><tr><th>Volumen</th><th>Años</th><th>Registros</th><th>Formato del nombre</th></tr></thead>
    <tbody>{vol_table_rows}</tbody>
  </table>
  <p style="margin-top:.6rem;font-size:.75rem;color:var(--muted)">
    Fuente: Ministerio de Cultura de España · Archivo General de Indias, Sevilla
  </p>
</div>

<div class="section" style="padding-top:0;padding-bottom:2.5rem">
  <div class="links">
    <a href="the-tree.html" class="back-link">← Árbol genealógico</a>
    <a href="migration-map.html" class="back-link">↗ Mapa de Migración</a>
    <a href="../index.html" class="back-link">⌂ Inicio</a>
  </div>
</div>

<footer>
  <p>Catálogo de Pasajeros a Indias · Archivo General de Indias, Sevilla</p>
  <p style="margin-top:.25rem">Villanueva Family Tree · <a href="../index.html">epc310tech.github.io/Villanueva_Family_Tree</a></p>
</footer>

<script>
function filter(gridId) {{
  const n = gridId.slice(-1);
  const q = document.getElementById('q'+n).value.toLowerCase();
  const d = document.getElementById('d'+n).value;
  const v = document.getElementById('v'+n).value;
  let shown = 0, total = 0;
  document.querySelectorAll('#'+gridId+' .card').forEach(c => {{
    const name = (c.querySelector('.entry-name')?.textContent||'').toLowerCase();
    const par  = (c.querySelector('.parents')?.textContent||'').toLowerCase();
    const cd   = c.dataset.dest||'';
    const cv   = c.dataset.vol||'';
    const ok   = (!q||(name+par).includes(q)) && (!d||cd===d) && (!v||cv===v);
    c.classList.toggle('hidden',!ok);
    total++; if(ok) shown++;
  }});
  const el = document.getElementById('cnt'+n);
  if(el) el.textContent = shown<total ? `Mostrando ${{shown}} de ${{total}}` : `${{total}} registros`;
}}
filter('grid1'); filter('grid2');
</script>
</body>
</html>"""

# ── Main ──────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("Loading volumes…")
    all_entries = load_all_volumes()
    print(f"\nTotal parsed: {len(all_entries):,}")

    print("Matching family surnames…")
    matched_with_prio = []
    for e in all_entries:
        hits = match_entry(e)
        if hits:
            e["matches"] = hits
            prio = min(h[2] for h in hits)
            matched_with_prio.append((e, prio))

    p1 = sum(1 for _, p in matched_with_prio if p == 1)
    p2 = sum(1 for _, p in matched_with_prio if p == 2)
    print(f"Priority-1 matches: {p1:,}")
    print(f"Priority-2 matches: {p2:,}")

    # Sample priority-1 hits
    print("\nSample priority-1:")
    shown = 0
    for e, p in matched_with_prio:
        if p == 1 and shown < 20:
            hits = [h[0] for h in e["matches"]]
            yr = e.get("year","?")
            print(f"  Vol {e['vol']:7s} {yr}  #{e['num']:4d}  {e['name'][:45]}  [{', '.join(hits[:3])}]")
            shown += 1

    print(f"\nBuilding {OUT_HTML}…")
    html = build_html(all_entries, matched_with_prio)
    with open(OUT_HTML, "w", encoding="utf-8") as f:
        f.write(html)
    size_kb = len(html) // 1024
    print(f"Done! {size_kb:,} KB")
