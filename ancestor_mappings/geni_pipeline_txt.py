#!/usr/bin/env python3
"""
geni_pipeline_txt.py
====================
Turn Geni.com "Ancestors of X (N generations)" plain-text exports into a
self-contained, interactive web graph -- no PDF or pdfplumber required.

This is a drop-in alternative to geni_pipeline.py that reads .txt files
instead of PDFs.  Everything downstream (parse → clean → classify → link
→ collapse → render) is identical.

Pipeline stages
---------------
1. EXTRACT   read the .txt file line by line
2. PARSE     the indented ahnentafel outline -> ordered list of person occurrences
3. CLEAN     split name / birth / death; pull years, places, country
4. CLASSIFY  derive a rank category from honorific keywords in the name
5. LINK      rebuild parent->child edges from the depth-first structure
6. COLLAPSE  dedupe recurring ancestors (pedigree collapse) into single nodes
7. RENDER    inject nodes+edges+legend into the HTML template -> one .html file

Usage
-----
    python geni_pipeline_txt.py INPUT.txt [INPUT2.txt ...] [options]

Options
    -o, --out PATH      output html (default: <root-name>-lineage.html)
    --json PATH         also write the intermediate cleaned graph as JSON
    --merge             merge all input files into ONE graph (cross-tree collapse)
    --title "..."       override the page title
    --no-dedupe         keep every occurrence as its own node (pure tree)
    --template PATH     template html (default: ./template.html)
    --d3 PATH           d3 min.js to inline (default: ./node_modules/d3/dist/d3.min.js)

The cleaned graph JSON is reusable on its own; the schema matches the viewer:
    nodes: {id, name, gen, birth, death, cat, titles, country, mult}
    edges: {s: parentId, t: childId}
"""
import argparse, json, os, re, sys, unicodedata

# ---------------------------------------------------------------- categories
CATEGORIES = [
    ("royal", "Royalty", "#d8af43", [
        r"\brey\b", r"\breina\b", r"\brei\b", r"\brainha\b",
        r"\bemperador\b", r"\bemperatriz\b", r"\bemperor\b", r"\bempress\b",
        r"\bduque\b", r"\bduquesa\b", r"\bduke\b", r"\bduchess\b",
        r"\binfante\b", r"\binfanta\b", r"\bprincipe\b", r"\bprincesa\b",
        r"\bprince\b", r"\bprincess\b", r"\bking\b", r"\bqueen\b",
    ]),
    ("noble", "Nobility", "#bc4257", [
        r"\bconde\b", r"\bcondesa\b", r"\bcount\b", r"\bcountess\b",
        r"\bmarques\b", r"\bmarquesa\b", r"\bmarquis\b", r"\bmarquess\b",
        r"\bvizconde\b", r"\bviscount\b", r"\bbaron\b", r"\bbaronesa\b",
        r"\bsenor de\b", r"\bsenora de\b", r"\bsenhor d", r"\bsenhora d",
        r"\bricohombre\b", r"\bmosen\b", r"\blord\b", r"\blady\b",
        r"^d\. ", r"\bdom\b", r"\bdona\b",
    ]),
    ("clergy", "Clergy", "#9460ab", [
        r"\bfray\b", r"\bfr\.", r"\bobispo\b", r"\bbispo\b",
        r"\barzobispo\b", r"\barcebispo\b", r"\bpresbitero\b",
        r"\bclerigo\b", r"\babade\b", r"\bdiacono\b", r"\bdeacon\b",
        r"\bbishop\b", r"\bcardenal\b",
    ]),
    ("military", "Military / Conquest", "#4d83c4", [
        r"\bcapitan\b", r"\bcaptain\b",
        r"\bconquistador", r"\bmaese de campo\b", r"\bmaestre de campo\b",
        r"\balferez\b", r"\balferes\b", r"\bcomendador\b",
        r"\bgeneral\b", r"\badelantado\b", r"\bsargento\b",
        r"\bteniente\b", r"\bsoldado\b", r"\bcoronel\b",
    ]),
    ("official", "Office / Civic", "#4f9d8c", [
        r"\balcalde\b", r"\balcaide\b", r"\bjurado\b", r"\bregidor\b",
        r"\bgobernador\b", r"\boidor\b", r"\bescribano\b",
        r"\bcorregidor\b", r"\btesorero\b", r"\bcontador\b",
        r"\bencomendero\b", r"\bgovernor\b",
    ]),
    ("indigenous", "Indigenous", "#cf8a3c", [
        r"\bhuachichil\b", r"\bguachichil\b", r"\bindigenous\b",
        r"\bindia\b", r"\bindio\b", r"\bcacique\b", r"\bcacica\b",
        r"\bnahua\b", r"\bmexica\b", r"\bazteca\b", r"\btlaxcalteca\b",
    ]),
]
UNTITLED = ("untitled", "Untitled", "#7d7461")

PLACEHOLDER = re.compile(
    r"^(n\.?\s*n\.?|no name|\(no name\)|<private>|private|"
    r"ficticious|fictitious|mother|father|unknown|desconocido|desconcido|\-)$"
)

COUNTRY_HINTS = [
    ("mexico", "Mexico"), ("méxico", "Mexico"),
    ("spain", "Spain"), ("españa", "Spain"), ("espana", "Spain"), ("espania", "Spain"),
    ("portugal", "Portugal"),
    ("italy", "Italy"), ("italia", "Italy"),
    ("france", "France"), ("francia", "France"),
    ("united states", "United States"), ("usa", "United States"),
    ("england", "England"), ("inglaterra", "England"),
]

LINE_RE = re.compile(r"^\s*(\d+)\.\s+(.*\S)\s*$")
VITAL_RE = re.compile(r"\s[bd]\.\s")
YEAR_RE = re.compile(r"\b(\d{3,4})\b")


def strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s)
                   if unicodedata.category(c) != "Mn")


def norm(s: str) -> str:
    s = strip_accents(s).lower()
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def classify(name: str) -> tuple:
    n = strip_accents(name).lower()
    for key, label, color, pats in CATEGORIES:
        for p in pats:
            if re.search(p, n):
                return key, _title_phrase(name, key)
    return UNTITLED[0], ""


def _title_phrase(name: str, cat: str) -> str:
    m = re.search(r",\s*([^,;]*\b(?:rey|reina|rei|conde|condesa|duque|duquesa|"
                  r"senhor|senor|senora|marques|vizconde|baron|capitan|"
                  r"conquistador|alcalde|alcaide|alferez|alferes|comendador|"
                  r"general|adelantado|jurado|regidor|gobernador|obispo|bispo|"
                  r"fray|maese de campo)[^,;]*)", name, re.I)
    if m:
        return m.group(1).strip()
    m = re.match(r"\s*((?:capit[aá]n(?:\s+general)?|conquistador[a]?|"
                 r"comendador|maese de campo|alf[eé]re[zs](?:\s+real)?|"
                 r"mos[eé]n|fray|don|do[ñn]a|d\.|capit[aã]o)\b[\w\s]*?)\b",
                 name, re.I)
    if m and m.group(1).strip():
        return m.group(1).strip()
    return cat.capitalize()


def parse_year(seg: str):
    for m in YEAR_RE.finditer(seg):
        y = int(m.group(1))
        if 300 <= y <= 2025:
            return y
    return None


def parse_country(seg: str):
    low = seg.lower()
    for token in [t.strip() for t in reversed(seg.split(","))]:
        for hint, name in COUNTRY_HINTS:
            if hint in token.lower():
                return name
    for hint, name in COUNTRY_HINTS:
        if hint in low:
            return name
    return ""


def split_vitals(rest: str):
    """Return (name, birth_seg, death_seg). Segments may be ''."""
    m = VITAL_RE.search(" " + rest)
    if not m:
        return rest.strip(), "", ""
    idx = m.start()
    idx -= 1
    if idx < 0:
        idx = 0
    name = rest[:idx].strip(" ,;")
    vital = rest[idx:].strip()
    birth_seg, death_seg = "", ""
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


# ---------------------------------------------------------------- stage 1 (txt)
def extract_lines(txt_path: str):
    """Read a plain-text ancestor file and return its lines."""
    with open(txt_path, encoding="utf-8", errors="replace") as f:
        return f.read().splitlines()


# ---------------------------------------------------------------- stage 2
def parse_people(lines):
    """Walk the outline; yield dicts {gen, name, birth_seg, death_seg}."""
    people = []
    cur = None
    for raw in lines:
        if not raw.strip():
            continue
        if raw.startswith("Ancestors of") or raw.startswith("Exported from"):
            continue
        m = LINE_RE.match(raw)
        if m:
            if cur:
                people.append(cur)
            gen = int(m.group(1))
            cur = {"gen": gen, "rest": m.group(2)}
        elif cur:
            cur["rest"] += " " + raw.strip()
    if cur:
        people.append(cur)

    cleaned = []
    for p in people:
        name, b_seg, d_seg = split_vitals(p["rest"])
        if not name:
            name = "Unknown"
        cleaned.append({
            "gen": p["gen"], "name": name,
            "birth": parse_year(b_seg), "death": parse_year(d_seg),
            "country": parse_country(b_seg) or parse_country(d_seg),
        })
    return cleaned


# ---------------------------------------------------------------- stages 4-6
def build_graph(people, dedupe=True, src_tag=""):
    nodes = {}
    edges = set()
    last = {}
    uniq = [0]

    def key_for(p):
        nm = norm(p["name"])
        if (not dedupe) or PLACEHOLDER.match(nm) or len(nm) < 4:
            uniq[0] += 1
            return f"_{src_tag}{uniq[0]}::{nm or 'unknown'}"
        if p["birth"] is not None:
            return f"{src_tag}{nm}|{p['birth']}"
        return f"{src_tag}{nm}|?"

    for p in people:
        k = key_for(p)
        cat, titles = classify(p["name"])
        if k not in nodes:
            nodes[k] = {
                "id": k, "name": p["name"], "gen": p["gen"],
                "birth": p["birth"], "death": p["death"],
                "cat": cat, "titles": titles, "country": p["country"], "mult": 0,
            }
        node = nodes[k]
        node["mult"] += 1
        node["gen"] = min(node["gen"], p["gen"])
        if node["birth"] is None and p["birth"] is not None:
            node["birth"] = p["birth"]
        if node["death"] is None and p["death"] is not None:
            node["death"] = p["death"]

        g = p["gen"]
        if g > 1 and (g - 1) in last and last[g - 1] is not None:
            child_key = last[g - 1]
            if child_key != k:
                edges.add((k, child_key))
        last[g] = k
    return nodes, edges


def assign_int_ids(nodes, edges):
    order = list(nodes.keys())
    idmap = {k: i for i, k in enumerate(order)}
    out_nodes = []
    for k in order:
        n = dict(nodes[k]); n["id"] = idmap[k]
        out_nodes.append(n)
    out_edges = [{"s": idmap[a], "t": idmap[b]} for a, b in edges
                 if a in idmap and b in idmap]
    return out_nodes, out_edges


# ---------------------------------------------------------------- render
def present_categories(nodes):
    counts = {}
    for n in nodes:
        counts[n["cat"]] = counts.get(n["cat"], 0) + 1
    legend = []
    for key, label, color, _ in CATEGORIES:
        if counts.get(key):
            legend.append({"key": key, "label": label, "color": color})
    if counts.get(UNTITLED[0]):
        legend.append({"key": UNTITLED[0], "label": UNTITLED[1], "color": UNTITLED[2]})
    return legend


def make_meta(nodes, root_name, n_edges):
    births = [n["birth"] for n in nodes if n["birth"] is not None]
    gmax = max((n["gen"] for n in nodes), default=1)
    span = ""
    if births:
        lo, hi = min(births), max(births)
        span = f"{lo}–{hi}"
    title = f"The Ancestry of {root_name}"
    bits = [f"{len(nodes):,} ancestors", f"{gmax} generations"]
    if span:
        bits.append(span)
    subtitle = " · ".join(bits)
    return title, subtitle, span


def render_html(nodes, edges, title, subtitle, legend, template, d3path, out):
    with open(template) as f:
        tpl = f.read()
    with open(d3path) as f:
        d3 = f.read()
    payload = json.dumps({"nodes": nodes, "edges": edges}, separators=(",", ":"))
    legend_js = json.dumps(legend, separators=(",", ":"))
    meta_js = json.dumps({"title": title, "subtitle": subtitle},
                         separators=(",", ":"))

    def esc(s):
        return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))

    html = (tpl
            .replace("/*__D3__*/", d3)
            .replace("/*__DATA__*/", payload)
            .replace("/*__LEGEND__*/", legend_js)
            .replace("/*__META__*/", meta_js)
            .replace("{{TITLE}}", esc(title))
            .replace("{{SUBTITLE}}", esc(subtitle)))
    with open(out, "w") as f:
        f.write(html)
    return out


# ---------------------------------------------------------------- driver
def process(txt_paths, dedupe=True, merge=False):
    """Return list of (root_name, nodes, edges)."""
    results = []
    if merge:
        all_people = []
        roots = []
        for p in txt_paths:
            people = parse_people(extract_lines(p))
            if people:
                roots.append(people[0]["name"])
            all_people.append(("", people))
        merged = []
        for _, ppl in all_people:
            merged.extend(ppl)
        nodes, edges = build_graph(merged, dedupe=dedupe, src_tag="")
        root_name = " + ".join(roots) if roots else "Merged"
        results.append((root_name, nodes, edges))
    else:
        for p in txt_paths:
            people = parse_people(extract_lines(p))
            root_name = people[0]["name"] if people else os.path.basename(p)
            nodes, edges = build_graph(people, dedupe=dedupe, src_tag="")
            results.append((root_name, nodes, edges))
    return results


def main():
    ap = argparse.ArgumentParser(description="Geni ancestor TXT -> interactive graph")
    ap.add_argument("txts", nargs="+", metavar="INPUT.txt")
    ap.add_argument("-o", "--out")
    ap.add_argument("--json")
    ap.add_argument("--merge", action="store_true")
    ap.add_argument("--title")
    ap.add_argument("--no-dedupe", dest="dedupe", action="store_false")
    here = os.path.dirname(os.path.abspath(__file__))
    ap.add_argument("--template", default=os.path.join(here, "template.html"))
    ap.add_argument("--d3", default=os.path.join(here, "d3.min.js"))
    ap.add_argument("--outdir", default=".")
    args = ap.parse_args()

    os.makedirs(args.outdir, exist_ok=True)
    results = process(args.txts, dedupe=args.dedupe, merge=args.merge)

    for root_name, nodes_d, edges_s in results:
        nodes, edges = assign_int_ids(nodes_d, edges_s)
        title, subtitle, span = make_meta(nodes, root_name, len(edges))
        if args.title:
            title = args.title
        legend = present_categories(nodes)

        slug = re.sub(r"[^a-z0-9]+", "-", strip_accents(root_name).lower()).strip("-")
        out = args.out or os.path.join(args.outdir, f"{slug}-lineage.html")
        render_html(nodes, edges, title, subtitle, legend,
                    args.template, args.d3, out)
        print(f"  {root_name}: {len(nodes):,} people, {len(edges):,} bonds -> {out}")
        if args.json:
            with open(args.json, "w") as f:
                json.dump({"nodes": nodes, "edges": edges}, f,
                          ensure_ascii=False, indent=0)
            print(f"     graph json -> {args.json}")


if __name__ == "__main__":
    main()
