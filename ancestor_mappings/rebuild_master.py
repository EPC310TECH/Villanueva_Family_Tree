#!/usr/bin/env python3
"""
rebuild_master.py
=================
Rebuild master-lineage.html from scratch using ONLY Geni.com data.

Strategy:
  1. antonio-jasso-lineage.html is the anchor (Antonio = gen 0).
  2. Every other Geni sub-lineage file has its root person looked up in the
     anchor to get the correct gen.  The whole sub-tree is then shifted by
     (base_gen - file_root_gen) so everyone's gen is relative to Antonio.
  3. Nodes are de-duplicated by normalised name + birth year.
  4. Resulting graph is written to a new HTML.

Run from ancestor_mappings/:
    python rebuild_master.py
"""

import json, os, re, sys, unicodedata
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))


# ── helpers ─────────────────────────────────────────────────────────────────

def strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s)
                   if unicodedata.category(c) != "Mn")

def norm(s: str) -> str:
    s = strip_accents(s).lower()
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()

_uid = [0]
PLACEHOLDER_RE = re.compile(
    r"^(n\.?\s*n\.?|no name|\(no name\)|<private>|private|"
    r"fictitious?|mother|father|unknown|desconoc[io]d[ao]|\-)$"
)

def node_key(n: dict) -> str:
    nm = norm(n["name"])
    if PLACEHOLDER_RE.match(nm) or len(nm) < 4:
        _uid[0] += 1
        return f"_uid_{_uid[0]}::{nm}"
    yr = n.get("birth")
    return f"{nm}|{yr}" if yr is not None else f"{nm}|?"

def load_graph(path: str):
    with open(path, encoding="utf-8") as f:
        raw = f.read()
    m = re.search(r'const GRAPH\s*=\s*(\{"nodes".*?\});', raw, re.DOTALL)
    if not m:
        return None
    return json.loads(m.group(1))


# ── classify (needed for nodes from old HTML without cat) ───────────────────

CATS = [
    ("royal",    [r"\brey\b", r"\breina\b", r"\brei\b", r"\brainha\b",
                  r"\bduque\b", r"\bduquesa\b", r"\bduke\b", r"\bduchess\b",
                  r"\binfante\b", r"\bprince\b", r"\bprincess\b",
                  r"\bking\b", r"\bqueen\b", r"\bemperor\b", r"\bempress\b"]),
    ("noble",    [r"\bconde\b", r"\bcondesa\b", r"\bcount\b", r"\bcountess\b",
                  r"\bmarques\b", r"\bvizconde\b", r"\bbaron\b",
                  r"\bsenor de\b", r"\bsenora de\b", r"\blord\b", r"\blady\b",
                  r"^d\. ", r"\bdom\b", r"\bdona\b", r"\bmosen\b"]),
    ("clergy",   [r"\bfray\b", r"\bobispo\b", r"\barzobispo\b",
                  r"\bbishop\b", r"\bcardenal\b", r"\bcardinal\b"]),
    ("military", [r"\bcapitan\b", r"\bcaptain\b", r"\bconquistador",
                  r"\bcomendador\b", r"\badelantado\b", r"\bgeneral\b"]),
    ("official", [r"\balcalde\b", r"\bgobernador\b", r"\boidor\b",
                  r"\bcorregidor\b", r"\bregidor\b"]),
    ("indigenous",[r"\bcacique\b", r"\bindio\b", r"\bindia\b"]),
]

def classify(name: str):
    n = strip_accents(name).lower()
    for key, pats in CATS:
        for p in pats:
            if re.search(p, n):
                return key
    return "untitled"


# ── merge state ──────────────────────────────────────────────────────────────

merged_nodes: dict[str, dict] = {}   # key -> merged node dict
merged_edges: set[tuple]       = set()  # (parent_key, child_key)


def absorb_graph(g: dict, offset: int, source_label: str):
    """Add a graph's nodes/edges into merged state with a gen offset applied."""
    # Compute each node's key ONCE — placeholder nodes increment a counter
    # so calling node_key() twice would generate different keys for the same node.
    node_keys = {n["id"]: node_key(n) for n in g["nodes"]}
    id_to_key = node_keys  # same dict, alias for clarity in the edges loop

    for n in g["nodes"]:
        k = node_keys[n["id"]]
        adj_gen = n["gen"] + offset
        if k not in merged_nodes:
            merged_nodes[k] = {
                "name":    n["name"],
                "gen":     adj_gen,
                "birth":   n.get("birth"),
                "death":   n.get("death"),
                "cat":     n.get("cat") or classify(n["name"]),
                "titles":  n.get("titles", ""),
                "country": n.get("country", ""),
                "mult":    n.get("mult", 1),
                "sources": {source_label},
            }
        else:
            existing = merged_nodes[k]
            existing["mult"] += n.get("mult", 1)
            existing["sources"].add(source_label)
            if existing["birth"] is None and n.get("birth") is not None:
                existing["birth"] = n["birth"]
            if existing["death"] is None and n.get("death") is not None:
                existing["death"] = n["death"]
            # Keep gen from anchor (antonio-jasso) if already present;
            # otherwise take the minimum (closest to Antonio)
            if "antonio" not in existing["sources"]:
                existing["gen"] = min(existing["gen"], adj_gen)

    for e in g["edges"]:
        sk = id_to_key.get(e["s"])
        tk = id_to_key.get(e["t"])
        if sk and tk and sk != tk:
            merged_edges.add((sk, tk))


def find_offset(g: dict, base_name_idx: dict) -> int:
    """
    Find offset = base_gen(root) - file_gen(root).
    First tries the file's root (min-gen node), then falls back to any
    shared node that matches cleanly.
    """
    nodes_by_key = {node_key(n): n for n in g["nodes"]}
    root_n = min(g["nodes"], key=lambda n: n["gen"])
    root_key = node_key(root_n)
    root_file_gen = root_n["gen"]

    # Try root directly
    rname_norm = norm(root_n["name"])
    base_hits = base_name_idx.get(rname_norm, [])
    if base_hits:
        base_gen = base_hits[0]["gen"]
        return base_gen - root_file_gen

    # Fallback: any shared node, prefer the one with lowest base gen (closest to Antonio)
    candidates = []
    for k, fn in nodes_by_key.items():
        fnorm = norm(fn["name"])
        bhits = base_name_idx.get(fnorm, [])
        if bhits:
            candidates.append((bhits[0]["gen"] - fn["gen"], bhits[0]["gen"]))

    if candidates:
        # Sort by base_gen ascending (prefer anchor near Antonio)
        candidates.sort(key=lambda x: x[1])
        return candidates[0][0]

    print(f"  ⚠ Could not find offset for root '{root_n['name']}' — skipping file")
    return None


# ── main ─────────────────────────────────────────────────────────────────────

def main():
    # 1. Load anchor
    anchor_path = os.path.join(HERE, "antonio-jasso-lineage.html")
    anchor_g    = load_graph(anchor_path)
    if not anchor_g:
        sys.exit("Could not load antonio-jasso-lineage.html")

    # Build name index for the anchor
    base_name_idx: dict[str, list] = defaultdict(list)
    for n in anchor_g["nodes"]:
        base_name_idx[norm(n["name"])].append(n)

    # Absorb anchor at offset=0 (it's already at the right gens)
    absorb_graph(anchor_g, offset=0, source_label="antonio")
    print(f"Anchor: {len(anchor_g['nodes']):,} nodes  (antonio-jasso-lineage.html)")

    # 2. Sub-lineage files to merge — all Geni HTML files except anchor/merged/master
    # Stems are computed as f[:-len("-lineage.html")] — e.g. "master-lineage.html" → "master"
    SKIP = {
        "merged",           # merged-lineage.html
        "master",           # master-lineage.html
        "master-geni-only", # our own output (if it exists)
        "antonio-jasso",    # antonio-jasso-lineage.html — absorbed as anchor above
        # ancestors-of-beatriz-del-corral is a dup of beatriz-del-corral
        "ancestors-of-beatriz-del-corral",
        # pedro duplicates (keep pedro-fernandez-de-castro-senor-de-paredes... as the canonical one)
        "pedro",
        "pedro-el-castellano-fernandez-de-castro-senor-de-paredes-de-nava-y-del-infantado-de-leon",
    }

    sub_files = sorted(
        f for f in os.listdir(HERE)
        if f.endswith("-lineage.html") and f[:-len("-lineage.html")] not in SKIP
    )

    for fname in sub_files:
        path = os.path.join(HERE, fname)
        g    = load_graph(path)
        if not g or not g["nodes"]:
            continue
        root = min(g["nodes"], key=lambda n: n["gen"])
        offset = find_offset(g, base_name_idx)
        if offset is None:
            continue
        label = fname.replace("-lineage.html", "")
        absorb_graph(g, offset=offset, source_label=label)
        print(f"  +{len(g['nodes']):>5} nodes  offset={offset:+d}  root: {root['name'][:55]}  ({fname})")

    # 3. BFS from Antonio to reassign all gen numbers by shortest-path distance
    print("\nReassigning gen numbers by BFS from Antonio …")
    # Build adjacency: child_key -> list of parent_keys
    children_of: dict[str, set] = defaultdict(set)
    parents_of:  dict[str, set] = defaultdict(set)
    for (pk, ck) in merged_edges:
        children_of[pk].add(ck)
        parents_of[ck].add(pk)

    # Find Antonio's key
    antonio_key = None
    for k, n in merged_nodes.items():
        if norm(n["name"]) in ("antonio jasso", "antonio jasso villanueva"):
            antonio_key = k
            break
    if antonio_key is None:
        # fallback: node with gen=0
        for k, n in merged_nodes.items():
            if n["gen"] == 0:
                antonio_key = k
                break

    if antonio_key:
        from collections import deque
        bfs_gen: dict[str, int] = {antonio_key: 0}
        queue = deque([antonio_key])
        while queue:
            cur = queue.popleft()
            for par in parents_of.get(cur, set()):
                if par not in bfs_gen:
                    bfs_gen[par] = bfs_gen[cur] + 1
                    queue.append(par)
        assigned = 0
        for k, new_gen in bfs_gen.items():
            if k in merged_nodes and merged_nodes[k]["gen"] != new_gen:
                merged_nodes[k]["gen"] = new_gen
                assigned += 1
        print(f"  BFS reached {len(bfs_gen):,} nodes; updated {assigned:,} gen values")
        unreached = [n["name"] for k, n in merged_nodes.items() if k not in bfs_gen]
        if unreached:
            print(f"  ⚠ {len(unreached)} nodes unreachable from Antonio (kept their existing gen): {unreached[:5]}")
    else:
        print("  ⚠ Antonio node not found; skipping BFS reassignment")

    # 4. Assign sequential integer IDs
    keys  = list(merged_nodes.keys())
    idmap = {k: i for i, k in enumerate(keys)}

    out_nodes = []
    for k in keys:
        n = dict(merged_nodes[k])
        n["id"]      = idmap[k]
        n.pop("sources", None)   # internal bookkeeping, not needed in HTML
        out_nodes.append(n)

    out_edges = [{"s": idmap[pk], "t": idmap[ck]}
                 for (pk, ck) in merged_edges
                 if pk in idmap and ck in idmap]

    # 5. Keep BFS-reachable nodes; drop true isolates (no edges and not on any path to Antonio)
    bfs_ids = set()
    if antonio_key:
        bfs_ids = {idmap[k] for k in bfs_gen if k in idmap}

    connected = set()
    for e in out_edges:
        connected.add(e["s"])
        connected.add(e["t"])

    # Keep node if it: (a) is reachable from Antonio by BFS, OR (b) appears in an edge
    keep_ids = bfs_ids | connected
    out_nodes = [n for n in out_nodes if n["id"] in keep_ids]

    # remap ids
    old_to_new = {n["id"]: i for i, n in enumerate(out_nodes)}
    for n in out_nodes:
        n["id"] = old_to_new[n["id"]]
    out_edges = [{"s": old_to_new[e["s"]], "t": old_to_new[e["t"]]}
                 for e in out_edges
                 if e["s"] in old_to_new and e["t"] in old_to_new]

    print(f"\nFinal graph: {len(out_nodes):,} nodes, {len(out_edges):,} edges")

    # Gen distribution
    gen_counts = defaultdict(int)
    for n in out_nodes:
        gen_counts[n["gen"]] += 1
    max_gen = max(gen_counts)
    print(f"Gen range: 0–{max_gen}")
    for g in range(0, min(max_gen+1, 45)):
        c = gen_counts.get(g, 0)
        if c:
            bar = "█" * min(c, 50)
            print(f"  gen {g:>3}: {c:>4}  {bar}")

    # 6. Render HTML
    template_path = os.path.join(HERE, "template.html")
    d3_path       = os.path.join(HERE, "d3.min.js")
    out_path      = os.path.join(HERE, "master-geni-only.html")

    with open(template_path) as f:
        tpl = f.read()
    with open(d3_path) as f:
        d3  = f.read()

    payload   = json.dumps({"nodes": out_nodes, "edges": out_edges},
                            ensure_ascii=False, separators=(",", ":"))
    n_nodes, n_edges = len(out_nodes), len(out_edges)
    births = [n["birth"] for n in out_nodes if n.get("birth")]
    span   = f"{min(births)}–{max(births)}" if births else ""
    title    = "The Ancestry of Antonio Jasso (Geni.com only)"
    subtitle = f"{n_nodes:,} ancestors · {max_gen} generations · {span}"

    LEGEND = [
        {"key":"royal",      "label":"Royalty",            "color":"#e8b820"},
        {"key":"noble",      "label":"Nobility",           "color":"#c83040"},
        {"key":"clergy",     "label":"Clergy",             "color":"#9040c0"},
        {"key":"military",   "label":"Military / Conquest","color":"#2d78d8"},
        {"key":"official",   "label":"Office / Civic",     "color":"#18a870"},
        {"key":"indigenous", "label":"Indigenous",         "color":"#c86828"},
        {"key":"untitled",   "label":"Untitled",           "color":"#7a6e5a"},
    ]
    legend_js = json.dumps(LEGEND, separators=(",", ":"))
    meta_js   = json.dumps({"title": title, "subtitle": subtitle},
                            separators=(",", ":"))

    def esc(s):
        return s.replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")

    html = (tpl
            .replace("/*__D3__*/",    d3)
            .replace("/*__DATA__*/",  payload)
            .replace("/*__LEGEND__*/",legend_js)
            .replace("/*__META__*/",  meta_js)
            .replace("{{TITLE}}",     esc(title))
            .replace("{{SUBTITLE}}", esc(subtitle)))

    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"\n✓ Written: {out_path}")


if __name__ == "__main__":
    main()
