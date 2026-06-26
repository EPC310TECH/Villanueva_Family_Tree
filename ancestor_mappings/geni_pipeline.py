#!/usr/bin/env python3
"""
geni_pipeline.py  –  Geni.com ancestor export → directed graph
===============================================================
Converts a Geni.com "Ancestors of X (N generations)" PDF (or .txt) export
into a clean directed graph of people (nodes) and parent→child bonds (edges).

Accepts .pdf (requires pdfplumber) or .txt files; extension is auto-detected.

Pipeline stages
---------------
1. EXTRACT   text lines from PDF pages or plain text file
2. PARSE     depth-first ahnentafel outline → ordered person occurrences
3. SPLIT     name / birth-segment / death-segment per occurrence
4. CLEAN     extract year, country; keep full display name
5. CLASSIFY  derive rank category from honorific keywords in the name
6. LINK      rebuild parent→child edges from DFS traversal order
7. COLLAPSE  dedupe recurring ancestors (pedigree collapse) into single nodes
8. EMIT      assign compact integer ids, output JSON-ready dicts
9. VERIFY    optional integrity checks

Usage
-----
    python geni_pipeline.py INPUT.pdf  [INPUT2.pdf ...]  [options]
    python geni_pipeline.py INPUT.txt  [INPUT2.txt ...]  [options]

Options
    -o, --out PATH      output html (default: <root-name>-lineage.html)
    --json PATH         also write the intermediate graph as JSON
    --merge             merge all inputs into ONE graph (cross-tree collapse)
    --no-dedupe         keep every occurrence as its own node (pure tree)
    --verify            run integrity checks and print a report
    --title "..."       override the page title
    --template PATH     HTML template (default: ./template.html)
    --d3 PATH           d3 min.js to inline (default: ./d3.min.js)
    --outdir PATH       output directory (default: .)

Graph JSON schema
-----------------
    nodes: [{id, name, gen, birth, death, cat, titles, country, mult}, ...]
    edges: [{s: parentId, t: childId}, ...]
"""

import argparse
import json
import os
import re
import sys
import unicodedata

# ═══════════════════════════════════════════════════════════════ § 5 constants

# Category table: (key, label, hex-color, [keyword regexes]).
# Ordered by priority — first match wins.
# Patterns are tested against strip_accents(name).lower() so accents and case
# are irrelevant; word-boundaries \b are used where the word stands alone.
CATEGORIES = [
    ("royal", "Royalty", "#e8b820", [
        r"\brey\b", r"\breina\b", r"\brei\b", r"\brainha\b",
        r"\bemperador\b", r"\bemperatriz\b", r"\bemperor\b", r"\bempress\b",
        r"\bduque\b", r"\bduquesa\b", r"\bduke\b", r"\bduchess\b",
        r"\binfante\b", r"\binfanta\b", r"\bprincipe\b", r"\bprincesa\b",
        r"\bprince\b", r"\bprincess\b", r"\bking\b", r"\bqueen\b",
    ]),
    ("noble", "Nobility", "#c83040", [
        r"\bconde\b", r"\bcondesa\b", r"\bcount\b", r"\bcountess\b",
        r"\bmarques\b", r"\bmarquesa\b", r"\bmarquis\b", r"\bmarquess\b",
        r"\bvizconde\b", r"\bviscount\b", r"\bbaron\b", r"\bbaronesa\b",
        r"\bsenor de\b", r"\bsenora de\b", r"\bsenhor d", r"\bsenhora d",
        r"\bricohombre\b", r"\bmosen\b", r"\blord\b", r"\blady\b",
        r"^d\. ", r"\bdom\b", r"\bdona\b",
    ]),
    ("clergy", "Clergy", "#9040c0", [
        r"\bfray\b", r"\bfr\.\b", r"\bobispo\b", r"\bbispo\b",
        r"\barzobispo\b", r"\barcebispo\b", r"\bpresbitero\b",
        r"\bclerigo\b", r"\babade\b", r"\bdiacono\b", r"\bdeacon\b",
        r"\bbishop\b", r"\bcardenal\b", r"\bcardinal\b",
    ]),
    ("military", "Military / Conquest", "#2d78d8", [
        r"\bcapitan\b", r"\bcaptain\b",
        r"\bconquistador", r"\bmaese de campo\b", r"\bmaestre de campo\b",
        r"\balferez\b", r"\balferes\b", r"\bcomendador\b",
        r"\bgeneral\b", r"\badelantado\b", r"\bsargento\b",
        r"\bteniente\b", r"\bsoldado\b", r"\bcoronel\b",
    ]),
    ("official", "Office / Civic", "#18a870", [
        r"\balcalde\b", r"\balcaide\b", r"\bjurado\b", r"\bregidor\b",
        r"\bgobernador\b", r"\boidor\b", r"\bescribano\b",
        r"\bcorregidor\b", r"\btesorero\b", r"\bcontador\b",
        r"\bencomendero\b", r"\bgovernor\b",
    ]),
    ("indigenous", "Indigenous", "#c86828", [
        r"\bhuachichil\b", r"\bguachichil\b", r"\bindigenous\b",
        r"\bindia\b", r"\bindio\b", r"\bcacique\b", r"\bcacica\b",
        r"\bnahua\b", r"\bmexica\b", r"\bazteca\b", r"\btlaxcalteca\b",
    ]),
]
UNTITLED = ("untitled", "Untitled", "#7a6e5a")

# Names that must never fuse into a shared node (each occurrence gets a unique key).
PLACEHOLDER_RE = re.compile(
    r"^(n\.?\s*n\.?|no name|\(no name\)|<private>|private|"
    r"ficticious|fictitious|mother|father|unknown|desconocido|desconcido|\-)$"
)

# Country normalization: (lowercase hint, display name).
# Last comma-token of the place string is checked first.
COUNTRY_HINTS = [
    ("mexico",        "Mexico"),
    ("méxico",        "Mexico"),
    ("spain",         "Spain"),
    ("españa",        "Spain"),
    ("espana",        "Spain"),
    ("espania",       "Spain"),
    ("portugal",      "Portugal"),
    ("italy",         "Italy"),
    ("italia",        "Italy"),
    ("france",        "France"),
    ("francia",       "France"),
    ("united states", "United States"),
    ("usa",           "United States"),
    ("england",       "England"),
    ("inglaterra",    "England"),
    ("colombia",      "Colombia"),
    ("peru",          "Peru"),
    ("perú",          "Peru"),
    ("chile",         "Chile"),
    ("argentina",     "Argentina"),
]

LINE_RE   = re.compile(r"^\s*(\d+)\.\s+(.*\S)\s*$")   # § 2
VITAL_RE  = re.compile(r"\s[bd]\.\s")                  # § 3
YEAR_RE   = re.compile(r"\b(\d{3,4})\b")               # § 4
HEADER_RE = re.compile(r"^(Ancestors of|Exported from)\b")

# ── region: extract ruled territory from embedded title ───────────────────
REGION_RE = re.compile(
    r"\b(?:rey|reina|rei|rainha|king|queen|emperor|empress|"
    r"duque|duquesa|duke|duchess|grand\s+duke|"
    r"infante|infanta|principe|princesa|prince|princess|"
    r"conde|condesa|count|countess|marques|marquesa|marquis|marquess|"
    r"vizconde|viscount|baron|baronesa|"
    r"se[nñ]or(?:a)?|senhor(?:a)?|lord|lady|"
    r"gobernador|governor|alcalde|alcaide|"
    r"adelantado|comendador|obispo|bispo|arzobispo|archbishop)"
    r"\s+(?:de(?:\s+(?:la|las|los|el|o|a|os|as))?|of|del|da|do)\s+"
    r"([A-ZÁÉÍÓÚÀÈÌÒÙÑÃÕÂÊÎÔÛËÏÜÇ][^,;()\n]{1,60})",
    re.IGNORECASE,
)

# ── house: (regex on strip_accents(name).lower(), display name) ───────────
HOUSE_LOOKUP = [
    # Named dynasties (check before generic surname fallback)
    (r"\bjimenez\b|\bximenez\b|\bximenes\b",       "Jiménez"),
    (r"\btrastamara\b",                             "Trastámara"),
    (r"\bplantagenet\b",                            "Plantagenet"),
    (r"\bcapet(ian)?\b",                            "Capetian"),
    (r"\bhohenstaufen\b",                           "Hohenstaufen"),
    (r"\bhabsburg\b",                               "Habsburg"),
    (r"\bwittelsbach\b",                            "Wittelsbach"),
    (r"\bvalois\b",                                 "Valois"),
    (r"\bborgo[nñ]a\b|\bburgund\w+",               "Burgundy"),
    (r"\bde\s+anjou\b|\bd.anjou\b",                "Anjou"),
    (r"\bde\s+normandie?\b|\bnormandy\b",          "Normandy"),
    (r"\bde\s+champagne\b",                        "Champagne"),
    # Iberian noble houses — keyed on the territorial surname
    (r"\bde\s+lara\b",                             "Lara"),
    (r"\bde\s+haro\b|\bde\s+vizcaya\b",            "Haro"),
    (r"\bde\s+castro\b|\bcastelhano\b",            "Castro"),
    (r"\bde\s+guzman\b",                           "Guzmán"),
    (r"\bde\s+sarmiento\b",                        "Sarmiento"),
    (r"\bde\s+manrique\b",                         "Manrique"),
    (r"\bde\s+villamayor\b",                       "Villamayor"),
    (r"\bde\s+manzanedo\b",                        "Manzanedo"),
    (r"\bde\s+azagra\b",                           "Azagra"),
    (r"\bde\s+cifuentes\b",                        "Cifuentes"),
    (r"\bde\s+brag[aâ]n[cç]a?\b",                 "Bragança"),
    (r"\bde\s+sousa\b",                            "Sousa"),
    (r"\bde\s+maia\b",                             "Maia"),
    (r"\bde\s+tougues\b|\bde\s+toug[uo]es\b",     "Tougues"),
    (r"\bde\s+tolosa\b|\bde\s+toulouse\b",         "Toulouse"),
    (r"\bde\s+corral\b|\bdel\s+corral\b",          "Del Corral"),
    (r"\bde\s+bobadilla\b",                        "Bobadilla"),
    (r"\bde\s+guevara\b",                          "Guevara"),
    (r"\bde\s+mendoza\b",                          "Mendoza"),
    (r"\bde\s+zuniga\b|\bde\s+z[uú][nñ]iga\b",    "Zúñiga"),
    (r"\bde\s+velasco\b",                          "Velasco"),
    (r"\bde\s+padilla\b",                          "Padilla"),
    (r"\bde\s+quinos\b|\bde\s+qui[nñ]ones\b",     "Quiñones"),
    (r"\bde\s+osorio\b",                           "Osorio"),
    (r"\bde\s+pimentel\b",                         "Pimentel"),
    (r"\bde\s+ribera\b",                           "Ribera"),
    (r"\bfern[aá]ndez\s+de\s+castro\b",            "Castro"),
    (r"\bbraganca\b",                              "Bragança"),
]


# ═══════════════════════════════════════════════════════════════ § 4 helpers

def strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s)
                   if unicodedata.category(c) != "Mn")


def norm(s: str) -> str:
    """Normalised form used only for deduplication / matching — never display."""
    s = strip_accents(s).lower()
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def extract_region(name: str) -> str:
    """Extract the ruled or associated territory from an embedded title phrase."""
    m = REGION_RE.search(name)
    if not m:
        return ""
    region = m.group(1).strip(" ,;.()")
    # Truncate at first conjunction to keep it concise
    region = re.split(r"\s+(?:y|e|and|ou|und|&)\s+", region, maxsplit=1)[0]
    region = re.split(r"\s*[,;(]", region)[0]
    return region.strip(" ,;.")


def extract_house(name: str) -> str:
    """Infer the family house or dynasty from the name."""
    n = strip_accents(name).lower()
    for pattern, house in HOUSE_LOOKUP:
        if re.search(pattern, n):
            return house
    # Fallback: first "de/del/da/do Surname" in the original name
    m = re.search(r"\b(?:de[l]?|d[ao])\s+([A-ZÁÉÍÓÚÑ][a-záéíóúñ]{3,})\b", name)
    if m:
        candidate = m.group(1)
        if norm(candidate) not in {"leon", "castilla", "castile", "navarra",
                                   "navarre", "portugal", "aragon", "pamplona",
                                   "galicia", "toledo", "sevilla", "murcia",
                                   "cordoba", "jaen", "badajoz", "caceres",
                                   "burgos", "palencia", "valladolid", "zamora",
                                   "salamanca", "avila", "segovia", "soria",
                                   "guadalajara", "cuenca", "huesca", "zaragoza",
                                   "tarragona", "barcelona", "lerida", "gerona",
                                   "the", "la", "las", "los", "el", "un", "una"}:
            return candidate
    return ""


# ═══════════════════════════════════════════════════════════════ § 1  extract

def extract_lines_pdf(path: str) -> list[str]:
    """Extract text lines from every page of a PDF via pdfplumber."""
    try:
        import pdfplumber
    except ImportError:
        sys.exit("pdfplumber is required for PDF input:  pip install pdfplumber")
    lines = []
    with pdfplumber.open(path) as pdf:
        for pg in pdf.pages:
            lines.extend((pg.extract_text() or "").splitlines())
    return lines


def extract_lines_txt(path: str) -> list[str]:
    """Read a plain-text ancestor file line by line (UTF-8, lenient)."""
    with open(path, encoding="utf-8", errors="replace") as f:
        return f.read().splitlines()


def extract_lines(path: str) -> list[str]:
    """Dispatch to PDF or TXT extractor based on file extension."""
    return extract_lines_pdf(path) if path.lower().endswith(".pdf") \
        else extract_lines_txt(path)


# ═══════════════════════════════════════════════════════════════ § 2  parse

def parse_occurrences(lines: list[str]) -> list[dict]:
    """
    Walk concatenated lines and emit ordered {gen, raw_text} dicts.

    A new occurrence begins on any line matching LINE_RE.
    Any non-matching, non-blank, non-header line is a continuation and is
    appended (space-joined) to the current buffer.
    Order is preserved — the linking step depends on it.
    """
    occurrences: list[dict] = []
    cur: dict | None = None
    for raw in lines:
        if not raw.strip() or HEADER_RE.match(raw):
            continue
        m = LINE_RE.match(raw)
        if m:
            if cur is not None:
                occurrences.append(cur)
            cur = {"gen": int(m.group(1)), "raw_text": m.group(2)}
        elif cur is not None:
            cur["raw_text"] += " " + raw.strip()
    if cur is not None:
        occurrences.append(cur)
    return occurrences


# ═══════════════════════════════════════════════════════════════ § 3  split

def split_vitals(raw: str) -> tuple[str, str, str]:
    """
    Return (name, birth_segment, death_segment); any segment may be empty.

    Strategy: pad with a leading space so raw_text starting with 'b. ' is
    caught, then unpad the matched index before splitting.
    """
    m = VITAL_RE.search(" " + raw)
    if not m:
        return raw.strip(), "", ""

    idx = max(m.start() - 1, 0)           # unpad
    name  = raw[:idx].strip(" ,;")
    vital = raw[idx:].strip()

    birth_seg = death_seg = ""
    dm = re.search(r"\bd\.\s", vital)
    if vital.lstrip().startswith("b."):
        if dm:
            birth_seg = vital[:dm.start()]
            death_seg = vital[dm.start():]
        else:
            birth_seg = vital
    else:
        death_seg = vital

    birth_seg = re.sub(r"^\s*b\.\s*", "", birth_seg).strip(" ,;")
    death_seg = re.sub(r"^\s*d\.\s*", "", death_seg).strip(" ,;")
    return name, birth_seg, death_seg


# ═══════════════════════════════════════════════════════════════ § 4  clean

def parse_year(seg: str) -> int | None:
    """First plausible year in [300, 2025] found in a vital segment.
    'between 1589 and 1620' → 1589; circa/before/after qualifiers are ignored."""
    for m in YEAR_RE.finditer(seg):
        y = int(m.group(1))
        if 300 <= y <= 2025:
            return y
    return None


def parse_country(seg: str) -> str:
    """Check last comma-token first, then full string; return display name."""
    tokens = [t.strip() for t in reversed(seg.split(","))]
    for token in tokens:
        tl = token.lower()
        for hint, country in COUNTRY_HINTS:
            if hint in tl:
                return country
    low = seg.lower()
    for hint, country in COUNTRY_HINTS:
        if hint in low:
            return country
    return ""


def clean_occurrence(occ: dict) -> dict:
    """Stage 3+4 combined: split vitals, extract year, country, region, house."""
    name, b_seg, d_seg = split_vitals(occ["raw_text"])
    name = name or "Unknown"
    return {
        "gen":     occ["gen"],
        "name":    name,
        "birth":   parse_year(b_seg),
        "death":   parse_year(d_seg),
        "country": parse_country(b_seg) or parse_country(d_seg),
        "region":  extract_region(name),
        "house":   extract_house(name),
    }


# ═══════════════════════════════════════════════════════════════ § 5  classify

def _title_phrase(name: str, cat: str) -> str:
    """Best-effort readable title phrase for the detail card."""
    m = re.search(
        r",\s*([^,;]*\b(?:rey|reina|rei|conde|condesa|duque|duquesa|"
        r"senhor|senor|senora|marques|vizconde|baron|capitan|"
        r"conquistador|alcalde|alcaide|alferez|alferes|comendador|"
        r"general|adelantado|jurado|regidor|gobernador|obispo|bispo|"
        r"fray|maese de campo)[^,;]*)",
        name, re.I,
    )
    if m:
        return m.group(1).strip()
    m = re.match(
        r"\s*((?:capit[aá]n(?:\s+general)?|conquistador[a]?|"
        r"comendador|maese de campo|alf[eé]re[zs](?:\s+real)?|"
        r"mos[eé]n|fray|don|do[ñn]a|d\.|capit[aã]o)\b[\w\s]*?)\b",
        name, re.I,
    )
    if m and m.group(1).strip():
        return m.group(1).strip()
    return cat.capitalize()


def classify(name: str) -> tuple[str, str]:
    """Return (category_key, title_phrase) for display."""
    n = strip_accents(name).lower()
    for key, _label, _color, patterns in CATEGORIES:
        for pat in patterns:
            if re.search(pat, n):
                return key, _title_phrase(name, key)
    return UNTITLED[0], ""


# ═══════════════════════════════════════════════════════════════ §§ 6-7  link + collapse

def _node_key(p: dict, dedupe: bool, counter: list[int]) -> str:
    """
    Stable string key used for deduplication.

    Rules (§ 7):
    - Placeholders and very-short names get a unique key every time.
    - With a birth year:  "{norm_name}|{year}"
    - Without a birth year: "{norm_name}|?"   (name-only merge — slightly riskier)
    - --no-dedupe: every occurrence is unique.
    """
    nm = norm(p["name"])
    if not dedupe or PLACEHOLDER_RE.match(nm) or len(nm) < 4:
        counter[0] += 1
        return f"_u{counter[0]}::{nm or 'unknown'}"
    return f"{nm}|{p['birth']}" if p["birth"] is not None else f"{nm}|?"


def build_graph(people: list[dict], dedupe: bool = True,
                src_tag: str = "") -> tuple[dict, set]:
    """
    Stage 6 + 7: link parent→child edges and optionally collapse pedigree.

    The core linking rule (§ 6):
      A person at generation g is a parent of the most-recent person seen at
      generation g-1.  This is maintained by a single `last` dict.

    Returns
    -------
    nodes : dict  key → node-dict  (string keys; ids assigned later)
    edges : set of (parent_key, child_key)
    """
    nodes:   dict[str, dict]  = {}
    edges:   set[tuple]       = set()
    last:    dict[int, str]   = {}    # gen → most-recent node key
    counter: list[int]        = [0]

    for p in people:
        k   = src_tag + _node_key(p, dedupe, counter)
        cat, titles = classify(p["name"])

        if k not in nodes:
            nodes[k] = {
                "id":      k,          # replaced with int later
                "name":    p["name"],
                "gen":     p["gen"],
                "birth":   p["birth"],
                "death":   p["death"],
                "cat":     cat,
                "titles":  titles,
                "country": p["country"],
                "region":  p.get("region", ""),
                "house":   p.get("house", ""),
                "mult":    0,
            }
        node = nodes[k]
        node["mult"] += 1
        node["gen"]   = min(node["gen"], p["gen"])     # closest-to-subject depth
        if node["birth"] is None and p["birth"] is not None:
            node["birth"] = p["birth"]
        if node["death"] is None and p["death"] is not None:
            node["death"] = p["death"]
        if not node["region"] and p.get("region"):
            node["region"] = p["region"]
        if not node["house"] and p.get("house"):
            node["house"] = p["house"]

        g = p["gen"]
        child_key = last.get(g - 1)
        if g > 1 and child_key is not None and child_key != k:
            edges.add((k, child_key))                   # parent → child
        last[g] = k

    return nodes, edges


def assign_int_ids(nodes: dict, edges: set) -> tuple[list, list]:
    """Map string keys to compact sequential integer ids (§ 8)."""
    order  = list(nodes.keys())
    idmap  = {k: i for i, k in enumerate(order)}
    out_nodes = [dict(nodes[k], id=idmap[k]) for k in order]
    out_edges = [{"s": idmap[a], "t": idmap[b]}
                 for a, b in edges if a in idmap and b in idmap]
    return out_nodes, out_edges


def remove_placeholders(nodes: list, edges: list) -> tuple[list, list, int]:
    """
    Remove placeholder nodes (N.N., unknown, etc.) and isolated/floating nodes.

    Two-pass: first strip placeholders + their edges, then strip any nodes that
    became isolated as a result (real people whose only connections were to
    placeholder nodes).

    Operates on int-id lists (after assign_int_ids).
    Returns (clean_nodes, clean_edges, n_removed).
    """
    total_removed = 0
    for _ in range(2):
        has_edge = set()
        for e in edges:
            has_edge.add(e["s"])
            has_edge.add(e["t"])

        placeholder_ids = {
            n["id"] for n in nodes
            if PLACEHOLDER_RE.match(norm(n["name"]))
        }
        isolated_ids = {
            n["id"] for n in nodes
            if n["id"] not in has_edge
        }
        bad = placeholder_ids | isolated_ids
        if not bad:
            break

        total_removed += len(bad)
        nodes = [n for n in nodes if n["id"] not in bad]
        edges = [e for e in edges
                 if e["s"] not in bad and e["t"] not in bad]

    return nodes, edges, total_removed


def resolve_yearless_duplicates(nodes: dict, edges: set) -> int:
    """
    Collapse name|? nodes into their name|YEAR twin when one exists.

    This fixes the case where the same ancestor appears with a birth year in
    one source file and without a birth year in another — producing two keys
    (e.g. 'unisco godins|960' and 'unisco godins|?') that should be one node.

    Operates on the string-keyed node/edge dicts produced by build_graph /
    merge_into_master (i.e. BEFORE assign_int_ids is called).

    Returns the number of nodes collapsed.
    """
    # Group keys by norm-name prefix (everything before the last '|')
    by_name: dict[str, list[str]] = {}
    for k in list(nodes.keys()):
        if k.startswith("_u"):        # unique placeholder keys — skip
            continue
        prefix = k.rsplit("|", 1)[0]
        by_name.setdefault(prefix, []).append(k)

    remap: dict[str, str] = {}       # old_key → canonical_key

    for prefix, keys in by_name.items():
        year_keys = [k for k in keys if not k.endswith("|?")]
        noyr_keys = [k for k in keys if k.endswith("|?")]
        if not (year_keys and noyr_keys):
            continue
        # Pick the year-keyed node with the most information as canonical
        canonical = max(year_keys, key=lambda k: nodes[k]["mult"])
        for nk in noyr_keys:
            remap[nk] = canonical
            ex  = nodes[canonical]
            old = nodes[nk]
            ex["mult"] += old["mult"]
            ex["gen"]   = min(ex["gen"], old["gen"])
            if ex["birth"] is None and old.get("birth") is not None:
                ex["birth"] = old["birth"]
            if ex["death"] is None and old.get("death") is not None:
                ex["death"] = old["death"]
            del nodes[nk]

    if not remap:
        return 0

    # Rewrite edges: replace remapped keys, drop self-loops
    new_edges = {(remap.get(a, a), remap.get(b, b)) for a, b in edges}
    new_edges.discard  # keep as expression — set comprehension already filters
    new_edges = {(a, b) for a, b in new_edges if a != b}
    edges.clear()
    edges.update(new_edges)

    return len(remap)


# ═══════════════════════════════════════════════════════════════ § 9  verify

def verify(nodes: list[dict], edges: list[dict]) -> dict:
    """
    Run the four integrity checks described in § 9.

    1. Root  — exactly the gen-1 person; incoming edges only from gen-2 nodes.
    2. Orientation — edges where parent.gen < child.gen are pedigree-collapse
       artefacts.  For those, confirm birth year ordering: parent.birth ≤ child.birth.
    3. No self-loops; edge set is unique.
    4. Spot-check collapse — top-10 by mult printed.

    Returns a report dict; call print_verify_report() to display it.
    """
    by_id = {n["id"]: n for n in nodes}
    edge_set = {(e["s"], e["t"]) for e in edges}

    report: dict = {}

    # ── check 1: root
    gen1 = [n for n in nodes if n["gen"] == 1]
    report["root_count"] = len(gen1)
    if len(gen1) == 1:
        root = gen1[0]
        report["root_name"] = root["name"]
        bad = [e for e in edges
               if e["t"] == root["id"] and by_id[e["s"]]["gen"] != 2]
        report["root_ok"] = len(bad) == 0
        report["root_bad_parent_edges"] = len(bad)
    else:
        report["root_ok"]   = False
        report["root_name"] = "(multiple or missing)"

    # ── check 2: orientation (parent.gen < child.gen after dedupe)
    inverted = [(e["s"], e["t"]) for e in edges
                if by_id[e["s"]]["gen"] < by_id[e["t"]]["gen"]]
    report["inverted_edge_count"] = len(inverted)

    yr_ok = yr_fail = yr_skip = 0
    for ps, pc in inverted:
        py = by_id[ps]["birth"]
        cy = by_id[pc]["birth"]
        if py is None or cy is None:
            yr_skip += 1
        elif py <= cy:
            yr_ok += 1
        else:
            yr_fail += 1
    report["inverted_year_ok"]   = yr_ok
    report["inverted_year_fail"] = yr_fail
    report["inverted_year_skip"] = yr_skip

    # ── check 3: self-loops + uniqueness
    report["self_loops"]    = sum(1 for e in edges if e["s"] == e["t"])
    report["unique_edges"]  = len(edge_set) == len(edges)

    # ── check 4: top collapsed nodes
    report["top_collapsed"] = [
        {"name": n["name"], "mult": n["mult"], "gen": n["gen"], "birth": n["birth"]}
        for n in sorted(nodes, key=lambda n: n["mult"], reverse=True)[:10]
        if n["mult"] > 1
    ]

    return report


def print_verify_report(report: dict) -> None:
    ok  = lambda b: "✓" if b else "✗"
    print("\n── Verification ────────────────────────────────────────")
    print(f"  {ok(report.get('root_ok'))}  Root: {report.get('root_name', '?')}  "
          f"({report['root_count']} gen-1 node(s))")
    print(f"  {ok(report['self_loops'] == 0)}  Self-loops: {report['self_loops']}")
    print(f"  {ok(report['unique_edges'])}  Edge set unique")

    inv  = report["inverted_edge_count"]
    yok  = report["inverted_year_ok"]
    yfa  = report["inverted_year_fail"]
    ysk  = report["inverted_year_skip"]
    pct  = 100 * yok / (yok + yfa) if (yok + yfa) else 0.0
    print(f"     Inverted-gen edges (pedigree-collapse artefacts): {inv}")
    print(f"       year-consistent {yok}/{yok + yfa}  ({pct:.0f}%)   "
          f"undatable {ysk}")

    cols = report.get("top_collapsed", [])
    if cols:
        print("  Top collapsed nodes (mult > 1):")
        for n in cols:
            print(f"    mult={n['mult']:>3}  gen={n['gen']:>3}  "
                  f"b.{str(n['birth'] or '?'):>4}  {n['name']}")
    print("────────────────────────────────────────────────────────\n")


# ═══════════════════════════════════════════════════════════════ render (HTML)

def present_categories(nodes: list[dict]) -> list[dict]:
    counts: dict[str, int] = {}
    for n in nodes:
        counts[n["cat"]] = counts.get(n["cat"], 0) + 1
    legend = []
    for key, label, color, _ in CATEGORIES:
        if counts.get(key):
            legend.append({"key": key, "label": label, "color": color})
    if counts.get(UNTITLED[0]):
        legend.append({"key": UNTITLED[0], "label": UNTITLED[1],
                        "color": UNTITLED[2]})
    return legend


def make_meta(nodes: list[dict], root_name: str) -> tuple[str, str]:
    births = [n["birth"] for n in nodes if n["birth"] is not None]
    gmax   = max((n["gen"] for n in nodes), default=1)
    span   = f"{min(births)}–{max(births)}" if births else ""
    title  = f"The Ancestry of {root_name}"
    bits   = [f"{len(nodes):,} ancestors", f"{gmax} generations"]
    if span:
        bits.append(span)
    return title, " · ".join(bits)


def render_html(nodes: list, edges: list, title: str, subtitle: str,
                legend: list, template_path: str, d3_path: str,
                out_path: str) -> str:
    with open(template_path) as f:
        tpl = f.read()
    with open(d3_path) as f:
        d3 = f.read()

    def esc(s):
        return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    html = (tpl
            .replace("/*__D3__*/",     d3)
            .replace("/*__DATA__*/",
                     json.dumps({"nodes": nodes, "edges": edges},
                                separators=(",", ":")))
            .replace("/*__LEGEND__*/", json.dumps(legend, separators=(",", ":")))
            .replace("/*__META__*/",
                     json.dumps({"title": title, "subtitle": subtitle},
                                separators=(",", ":")))
            .replace("{{TITLE}}",    esc(title))
            .replace("{{SUBTITLE}}", esc(subtitle)))
    with open(out_path, "w") as f:
        f.write(html)
    return out_path


# ═══════════════════════════════════════════════════════════════ driver

def process(paths: list[str], dedupe: bool = True,
            merge: bool = False) -> list[tuple[str, list, list]]:
    """
    Parse inputs and return list of (root_name, nodes, edges) with integer ids.

    --merge: all occurrences are poured into one keyspace before linking, so
    ancestors shared across files collapse together into single nodes.
    """
    def _one(path: str, src_tag: str = "") -> tuple[str, dict, set]:
        lines      = extract_lines(path)
        people     = [clean_occurrence(o) for o in parse_occurrences(lines)]
        root_name  = people[0]["name"] if people else os.path.basename(path)
        nodes, edges = build_graph(people, dedupe=dedupe, src_tag=src_tag)
        return root_name, nodes, edges

    if merge:
        merged_nodes: dict[str, dict] = {}
        merged_edges: set[tuple]      = set()
        roots: list[str]              = []
        for path in paths:
            root_name, nodes, edges = _one(path)
            roots.append(root_name)
            for k, n in nodes.items():
                if k not in merged_nodes:
                    merged_nodes[k] = n
                else:
                    ex = merged_nodes[k]
                    ex["mult"] += n["mult"]
                    ex["gen"]   = min(ex["gen"], n["gen"])
                    if ex["birth"] is None and n["birth"] is not None:
                        ex["birth"] = n["birth"]
                    if ex["death"] is None and n["death"] is not None:
                        ex["death"] = n["death"]
            merged_edges |= edges
        combined = " + ".join(roots) if roots else "Merged"
        nl, el   = assign_int_ids(merged_nodes, merged_edges)
        return [(combined, nl, el)]

    results = []
    for path in paths:
        root_name, nodes, edges = _one(path)
        nl, el = assign_int_ids(nodes, edges)
        results.append((root_name, nl, el))
    return results


# ═══════════════════════════════════════════════════════════════ CLI

def main() -> None:
    here = os.path.dirname(os.path.abspath(__file__))
    ap = argparse.ArgumentParser(
        description="Geni ancestor PDF/TXT → interactive lineage graph"
    )
    ap.add_argument("inputs",      nargs="+", metavar="INPUT")
    ap.add_argument("-o", "--out", metavar="PATH")
    ap.add_argument("--json",      metavar="PATH")
    ap.add_argument("--merge",     action="store_true")
    ap.add_argument("--no-dedupe", dest="dedupe", action="store_false")
    ap.add_argument("--verify",    action="store_true")
    ap.add_argument("--title")
    ap.add_argument("--template",  default=os.path.join(here, "template.html"))
    ap.add_argument("--d3",        default=os.path.join(here, "d3.min.js"))
    ap.add_argument("--outdir",    default=".")
    args = ap.parse_args()

    os.makedirs(args.outdir, exist_ok=True)
    results = process(args.inputs, dedupe=args.dedupe, merge=args.merge)

    for root_name, nodes, edges in results:
        title, subtitle = make_meta(nodes, root_name)
        if args.title:
            title = args.title
        legend = present_categories(nodes)

        slug = re.sub(r"[^a-z0-9]+", "-",
                      strip_accents(root_name).lower()).strip("-")
        out  = args.out or os.path.join(args.outdir, f"{slug}-lineage.html")

        have_assets = os.path.exists(args.template) and os.path.exists(args.d3)
        if have_assets:
            render_html(nodes, edges, title, subtitle, legend,
                        args.template, args.d3, out)
            print(f"  {root_name}: {len(nodes):,} people, "
                  f"{len(edges):,} bonds  →  {out}")
        else:
            print(f"  {root_name}: {len(nodes):,} people, {len(edges):,} bonds")
            missing = [p for p in (args.template, args.d3)
                       if not os.path.exists(p)]
            for p in missing:
                print(f"    (missing: {p})")

        if args.json:
            with open(args.json, "w") as f:
                json.dump({"nodes": nodes, "edges": edges}, f,
                          ensure_ascii=False, indent=0)
            print(f"     graph json  →  {args.json}")

        if args.verify:
            report = verify(nodes, edges)
            print_verify_report(report)


if __name__ == "__main__":
    main()
