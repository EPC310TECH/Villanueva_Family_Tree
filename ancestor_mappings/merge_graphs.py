#!/usr/bin/env python3
"""
merge_graphs.py
===============
Merge two (or more) lineage HTML files produced by geni_pipeline*.py into
a single interactive graph, collapsing shared ancestors automatically.

Usage
-----
    python merge_graphs.py INPUT1.html INPUT2.html [...] [options]

Options
    -o, --out PATH      output html (default: merged-lineage.html)
    --title "..."       override the page title
    --template PATH     template html (default: ./template.html)
    --d3 PATH           d3 min.js to inline (default: ./d3.min.js)
    --outdir PATH       output directory (default: .)
"""
import argparse, json, os, re, sys, unicodedata
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from geni_pipeline import resolve_yearless_duplicates, classify, extract_region, extract_house, remove_placeholders


# ---------------------------------------------------------------- helpers
def strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s)
                   if unicodedata.category(c) != "Mn")


def norm(s: str) -> str:
    s = strip_accents(s).lower()
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


PLACEHOLDER_RE = re.compile(
    r"^(n\.?\s*n\.?|no name|\(no name\)|<private>|private|"
    r"ficticious|fictitious|mother|father|unknown|desconocido|desconcido|\-)$"
)

_uid_counter = [0]

def node_key(n: dict) -> str:
    nm = norm(n["name"])
    yr = n.get("birth")
    # Placeholders and very short names must never fuse across trees
    if PLACEHOLDER_RE.match(nm) or len(nm) < 4:
        _uid_counter[0] += 1
        return f"_uid_{_uid_counter[0]}::{nm}"
    return f"{nm}|{yr}" if yr is not None else f"{nm}|?"


# ---------------------------------------------------------------- extract
def extract_graph(html_path: str) -> dict:
    """Pull the GRAPH JSON payload out of a rendered lineage HTML."""
    with open(html_path, encoding="utf-8") as f:
        content = f.read()
    m = re.search(r"const GRAPH\s*=\s*(\{\"nodes\".*?\});", content, re.DOTALL)
    if not m:
        sys.exit(f"Could not find GRAPH data in {html_path}")
    return json.loads(m.group(1))


# ---------------------------------------------------------------- merge
def merge_graphs(graphs: list[dict]) -> tuple[list, list]:
    """
    Merge a list of {nodes, edges} dicts.

    Gen alignment: the first graph is the base. Each subsequent graph has its
    gen values shifted so that shared nodes line up with their gen in the base,
    meaning all generations stay relative to the youngest person in the base tree.

    After merging, all gen values are shifted so the youngest person = 0.
    """
    merged_nodes: dict[str, dict] = {}   # key -> node
    merged_edges: set[tuple] = set()     # (key_src, key_tgt)

    for graph_idx, g in enumerate(graphs):
        nodes = g["nodes"]
        edges = g["edges"]

        # Build key -> node map for this graph
        this_nodes: dict[str, dict] = {}
        for n in nodes:
            this_nodes[node_key(n)] = n

        # Compute gen offset: how much to add to this graph's gen values so
        # shared nodes align with their already-merged gen.
        offset = 0
        if graph_idx > 0:
            shared = set(merged_nodes) & set(this_nodes)
            if shared:
                # Anchor on the shared node that is closest to the root in
                # the already-merged tree (lowest gen = most recent).
                anchor = min(shared, key=lambda k: merged_nodes[k]["gen"])
                offset = merged_nodes[anchor]["gen"] - this_nodes[anchor]["gen"]

        # Build int-id -> key map for edge translation
        id_to_key: dict[int, str] = {n["id"]: node_key(n) for n in nodes}

        # Merge nodes
        for n in nodes:
            k = node_key(n)
            adjusted_gen = n["gen"] + offset
            if k not in merged_nodes:
                merged_nodes[k] = {
                    "name":    n["name"],
                    "gen":     adjusted_gen,
                    "birth":   n.get("birth"),
                    "death":   n.get("death"),
                    "cat":     n.get("cat", "untitled"),
                    "titles":  n.get("titles", ""),
                    "country": n.get("country", ""),
                    "region":  n.get("region", ""),
                    "house":   n.get("house", ""),
                    "mult":    n.get("mult", 1),
                }
            else:
                # Shared node: keep gen from the base tree, just accumulate mult
                existing = merged_nodes[k]
                existing["mult"] += n.get("mult", 1)
                if existing["birth"] is None and n.get("birth") is not None:
                    existing["birth"] = n["birth"]
                if existing["death"] is None and n.get("death") is not None:
                    existing["death"] = n["death"]

        # Merge edges
        for e in edges:
            sk = id_to_key.get(e["s"])
            tk = id_to_key.get(e["t"])
            if sk and tk and sk != tk:
                merged_edges.add((sk, tk))

    # Collapse name|? / name|YEAR duplicates
    resolve_yearless_duplicates(merged_nodes, merged_edges)

    # Normalize: youngest person (lowest gen) -> 0
    if merged_nodes:
        min_gen = min(n["gen"] for n in merged_nodes.values())
        if min_gen != 0:
            for n in merged_nodes.values():
                n["gen"] -= min_gen

    # Assign sequential int ids
    order = list(merged_nodes.keys())
    idmap = {k: i for i, k in enumerate(order)}
    out_nodes = []
    for k in order:
        n = dict(merged_nodes[k])
        n["id"] = idmap[k]
        out_nodes.append(n)
    out_edges = [{"s": idmap[a], "t": idmap[b]}
                 for a, b in merged_edges
                 if a in idmap and b in idmap]
    return out_nodes, out_edges


# ---------------------------------------------------------------- render helpers (copied from pipeline)
CATEGORIES = [
    ("royal",      "Royalty",            "#e8b820"),
    ("noble",      "Nobility",           "#c83040"),
    ("clergy",     "Clergy",             "#9040c0"),
    ("military",   "Military / Conquest","#2d78d8"),
    ("official",   "Office / Civic",     "#18a870"),
    ("indigenous", "Indigenous",         "#c86828"),
]
UNTITLED = ("untitled", "Untitled", "#7a6e5a")


def present_categories(nodes):
    counts = {}
    for n in nodes:
        counts[n["cat"]] = counts.get(n["cat"], 0) + 1
    legend = []
    for key, label, color in CATEGORIES:
        if counts.get(key):
            legend.append({"key": key, "label": label, "color": color})
    if counts.get(UNTITLED[0]):
        legend.append({"key": UNTITLED[0], "label": UNTITLED[1], "color": UNTITLED[2]})
    return legend


def make_meta(nodes, title_override, n_edges):
    births = [n["birth"] for n in nodes if n["birth"] is not None]
    gmax = max((n["gen"] for n in nodes), default=1)
    span = ""
    if births:
        lo, hi = min(births), max(births)
        span = f"{lo}–{hi}"
    title = title_override or "Merged Ancestry"
    bits = [f"{len(nodes):,} ancestors", f"{gmax} generations"]
    if span:
        bits.append(span)
    subtitle = " · ".join(bits)
    return title, subtitle


def render_html(nodes, edges, title, subtitle, legend, template, d3path, out):
    with open(template) as f:
        tpl = f.read()
    with open(d3path) as f:
        d3 = f.read()
    payload   = json.dumps({"nodes": nodes, "edges": edges}, separators=(",", ":"))
    legend_js = json.dumps(legend, separators=(",", ":"))
    meta_js   = json.dumps({"title": title, "subtitle": subtitle}, separators=(",", ":"))

    def esc(s):
        return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

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


# ---------------------------------------------------------------- main
def main():
    here = os.path.dirname(os.path.abspath(__file__))
    ap = argparse.ArgumentParser(description="Merge lineage HTML files into one graph")
    ap.add_argument("htmls", nargs="+", metavar="INPUT.html")
    ap.add_argument("-o", "--out")
    ap.add_argument("--title")
    ap.add_argument("--template", default=os.path.join(here, "template.html"))
    ap.add_argument("--d3",       default=os.path.join(here, "d3.min.js"))
    ap.add_argument("--outdir",   default=".")
    args = ap.parse_args()

    os.makedirs(args.outdir, exist_ok=True)

    graphs = []
    roots  = []
    for path in args.htmls:
        g = extract_graph(path)
        # Back-fill region/house/titles for nodes from older HTML files
        for n in g["nodes"]:
            if not n.get("cat") or not n.get("titles"):
                n["cat"], n["titles"] = classify(n["name"])
            if not n.get("region"):
                n["region"] = extract_region(n["name"])
            if not n.get("house"):
                n["house"] = extract_house(n["name"])
        graphs.append(g)
        # first node (gen==1 minimum) is the root person
        root = min(g["nodes"], key=lambda n: n["gen"])
        roots.append(root["name"])
        print(f"  Loaded {path}: {len(g['nodes']):,} nodes, {len(g['edges']):,} edges  (root: {root['name']})")

    nodes, edges = merge_graphs(graphs)

    title = args.title or " + ".join(roots)
    legend = present_categories(nodes)
    title_str, subtitle = make_meta(nodes, title, len(edges))

    # find shared nodes (mult > sum of individual mults would indicate merging,
    # but simpler: mult reflects how many times a node appeared across trees)
    shared = [n for n in nodes if n["mult"] > 1]
    print(f"\n  Shared / collapsed ancestors: {len(shared)}")
    for n in sorted(shared, key=lambda n: n["gen"])[:20]:
        print(f"    gen {n['gen']:>3}  {n['name']}  (b.{n['birth']})")

    nodes, edges, n_removed = remove_placeholders(nodes, edges)
    if n_removed:
        print(f"  Removed {n_removed} placeholder / isolated node(s)")

    out = args.out or os.path.join(args.outdir, "merged-lineage.html")
    render_html(nodes, edges, title_str, subtitle, legend, args.template, args.d3, out)
    print(f"\n  {len(nodes):,} people, {len(edges):,} bonds -> {out}")


if __name__ == "__main__":
    main()
