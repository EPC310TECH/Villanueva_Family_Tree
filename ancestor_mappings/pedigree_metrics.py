#!/usr/bin/env python3
"""
pedigree_metrics.py
===================
Pedigree-collapse metrics for the cleaned graph JSON emitted by geni_pipeline.py.

Reads the schema you already produce:
    nodes: [{id, name, gen, birth, death, cat, titles, country, mult}, ...]
    edges: [{s: parentId, t: childId}, ...]

Computes BOTH metrics in one pass over the same graph:

  1. IMPLEX  -- structural pedigree collapse. For each generation g it reports
     theoretical slots (2^g), FILLED slots (root->ancestor paths reaching gen g),
     DISTINCT individuals filling them, and collapse = 1 - distinct/filled.
     Slots are counted by dynamic programming over the DAG, NOT by enumerating
     paths -- a deep royalty tree has astronomically many paths but the DP stays
     linear in nodes x depths.

  2. F  -- Wright's coefficient of inbreeding for the subject, computed as the
     kinship coefficient of the subject's two parents via the standard recursion
     (Karigl 1981), memoized. F concentrates the collapse by genetic proximity:
     a duplicated ancestor 4 generations up counts for far more than one 12 up.

Usage
-----
    python pedigree_metrics.py GRAPH.json [--root ID|--root-name "Name"]
                                          [--max-gen N] [--json OUT.json]

Root defaults to the gen==1 person (the subject of the export).
"""
import argparse, json, re, sys
from collections import defaultdict, deque
from functools import lru_cache


# ----------------------------------------------------------------- load graph
def load_graph(path):
    with open(path, encoding="utf-8") as fh:
        raw = fh.read()
    # Accept both plain JSON and the project's rendered HTML files
    if path.endswith(".html"):
        m = re.search(r"const GRAPH\s*=\s*(\{\"nodes\".*?\});", raw, re.DOTALL)
        if not m:
            sys.exit(f"Could not find GRAPH data in {path}")
        g = json.loads(m.group(1))
    else:
        g = json.loads(raw)
    nodes = {n["id"]: n for n in g["nodes"]}
    # child -> list of parent ids   (edge is s=parent -> t=child)
    parents = defaultdict(list)
    children = defaultdict(list)
    for e in g["edges"]:
        s, t = e["s"], e["t"]
        parents[t].append(s)
        children[s].append(t)
    return nodes, dict(parents), dict(children)


def find_root(nodes, children, override=None, override_name=None):
    if override is not None:
        # node ids are integers; argparse gives us a string
        try:
            override = int(override)
        except (TypeError, ValueError):
            pass
        if override not in nodes:
            sys.exit(f"--root {override!r} not found among node ids")
        return override
    if override_name is not None:
        hits = [i for i, n in nodes.items()
                if n.get("name", "").lower() == override_name.lower()]
        if not hits:
            sys.exit(f"--root-name {override_name!r} matched no node")
        if len(hits) > 1:
            sys.exit(f"--root-name {override_name!r} matched {len(hits)} nodes; "
                     f"use --root with one of {hits}")
        return hits[0]
    # default: the gen-1 subject (fall back to the unique node that is never a parent)
    g1 = [i for i, n in nodes.items() if n.get("gen") == 1]
    if len(g1) == 1:
        return g1[0]
    sinks = [i for i in nodes if i not in children]
    if len(sinks) == 1:
        return sinks[0]
    sys.exit("Could not identify a unique root; pass --root ID or --root-name.")


# ------------------------------------------------------------ topological rank
def topo_rank(nodes, parents):
    """Ancestors-first ordering: every parent gets a strictly smaller rank than
    its child. Needed so the kinship recursion always expands the *descendant*."""
    indeg = {i: len(parents.get(i, ())) for i in nodes}          # in = #parents
    children = defaultdict(list)
    for child, ps in parents.items():
        for p in ps:
            children[p].append(child)
    q = deque(i for i, d in indeg.items() if d == 0)             # progenitors
    rank, k = {}, 0
    while q:
        v = q.popleft()
        rank[v] = k; k += 1
        for c in children.get(v, ()):
            indeg[c] -= 1
            if indeg[c] == 0:
                q.append(c)
    if len(rank) != len(nodes):                                 # cycle guard
        missing = [i for i in nodes if i not in rank]
        for i in missing:                                        # park cycles last
            rank[i] = k; k += 1
        print(f"  ! warning: {len(missing)} node(s) in a cycle "
              f"(bad birth-year link?); parked at end: {missing[:5]}",
              file=sys.stderr)
    return rank


# -------------------------------------------------------------------- implex
def implex(root, nodes, parents, max_gen=25):
    """DP over the DAG. ways[node] = Counter{depth: #paths from root at that depth}.
    Process root-first (descendants before ancestors) so a node's path-counts are
    final before we push them up to its parents."""
    # order nodes by ascending generation-from-root via BFS to get a safe push order
    depth_seen = {root: 0}
    order = [root]
    dq = deque([root])
    while dq:
        v = dq.popleft()
        for p in parents.get(v, ()):
            if p not in depth_seen:
                depth_seen[p] = depth_seen[v] + 1
                order.append(p)
                dq.append(p)
    # Process descendants before ancestors so every child's counts are settled
    # before we push up to its parents.  BFS depth from root is the safest
    # ordering: root (depth 0) first, then immediate parents (depth 1), etc.
    # This is immune to cycles that can disrupt topo_rank.
    order = sorted(depth_seen, key=lambda i: depth_seen[i])      # root → ancestors

    ways = defaultdict(lambda: defaultdict(int))
    ways[root][0] = 1
    for v in order:
        for d, w in list(ways[v].items()):
            if d >= max_gen:
                continue
            for p in parents.get(v, ()):
                ways[p][d + 1] += w

    # aggregate by generation (exclude depth 0 = root itself)
    per_gen = {}                       # gen -> (filled_slots, distinct_people)
    total_slots = 0
    distinct_ancestors = set()
    slots_distinct_by_gen = defaultdict(set)
    for node, dd in ways.items():
        if node == root:
            continue
        distinct_ancestors.add(node)
        for d, w in dd.items():
            if d == 0:
                continue
            per_gen.setdefault(d, [0, None])
            per_gen[d][0] += w
            slots_distinct_by_gen[d].add(node)
            total_slots += w
    report = []
    for g in sorted(per_gen):
        filled = per_gen[g][0]
        distinct = len(slots_distinct_by_gen[g])
        collapse = 1 - distinct / filled if filled else 0.0
        report.append({"gen": g, "theoretical": 2 ** g, "filled": filled,
                       "distinct": distinct, "collapse": collapse})
    cumulative = 1 - len(distinct_ancestors) / total_slots if total_slots else 0.0
    return report, {"total_filled_slots": total_slots,
                    "distinct_ancestors": len(distinct_ancestors),
                    "cumulative_collapse": cumulative}


# --------------------------------------------------------- kinship / Wright F
def make_phi(nodes, parents):
    rank = topo_rank(nodes, parents)

    @lru_cache(maxsize=None)
    def phi(a, b):
        if a is None or b is None:
            return 0.0
        # expand the descendant (higher topo rank); keeps recursion well-founded
        if rank[a] < rank[b]:
            a, b = b, a
        ps = parents.get(a, ())
        if a == b:
            p1 = ps[0] if len(ps) >= 1 else None
            p2 = ps[1] if len(ps) >= 2 else None
            return 0.5 * (1.0 + phi(p1, p2))
        if not ps:
            return 0.0
        # average kinship of a's parents with b
        return sum(phi(p, b) for p in ps) / len(ps)

    return phi, rank


def inbreeding_F(root, nodes, parents):
    import sys as _sys
    ps = parents.get(root, [])
    overloaded = {i: len(p) for i, p in parents.items() if len(p) > 2}
    if overloaded:
        print(f"  ! warning: {len(overloaded)} node(s) have >2 parents "
              f"(merge collision in dedupe?); F may be off. e.g. {list(overloaded)[:5]}",
              file=sys.stderr)
    phi, _ = make_phi(nodes, parents)
    if len(ps) < 2:
        return 0.0, ps  # subject with <2 known parents -> F undefined-as-0
    old_limit = _sys.getrecursionlimit()
    _sys.setrecursionlimit(50000)
    try:
        result = phi(ps[0], ps[1]), ps
    except RecursionError:
        print("  ! Wright's F skipped: recursion depth exceeded (graph has cycles).",
              file=sys.stderr)
        result = float("nan"), ps
    finally:
        _sys.setrecursionlimit(old_limit)
    return result


# ------------------------------------------------------------------- reporting
def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("graph", help="cleaned graph JSON from geni_pipeline.py --json")
    ap.add_argument("--root", help="root node id (default: the gen==1 subject)")
    ap.add_argument("--root-name", help="root by exact name instead of id")
    ap.add_argument("--max-gen", type=int, default=25)
    ap.add_argument("--json", dest="out", help="write full metrics as JSON")
    a = ap.parse_args()

    nodes, parents, children = load_graph(a.graph)
    root = find_root(nodes, children, a.root, a.root_name)
    rname = nodes[root].get("name", root)

    rep, summ = implex(root, nodes, parents, a.max_gen)
    F, rps = inbreeding_F(root, nodes, parents)

    print(f"\nSubject: {rname}  (id={root})")
    print(f"Ancestors known: {summ['distinct_ancestors']} distinct individuals "
          f"filling {summ['total_filled_slots']} slots\n")
    print(f"{'gen':>3} {'2^g':>10} {'filled':>8} {'distinct':>9} {'collapse':>9}")
    for r in rep:
        print(f"{r['gen']:>3} {r['theoretical']:>10} {r['filled']:>8} "
              f"{r['distinct']:>9} {r['collapse']:>8.1%}")
    print(f"\nCumulative implex (collapse over filled slots): "
          f"{summ['cumulative_collapse']:.2%}")
    pn = ", ".join(nodes[p].get('name', p) for p in rps) if rps else "(<2 known)"
    import math as _math
    if _math.isnan(F):
        print(f"Wright's F (inbreeding coefficient): n/a (graph cycles prevent computation)   [parents: {pn}]")
    else:
        print(f"Wright's F (inbreeding coefficient): {F:.6f}   [parents: {pn}]")
    if F and not _math.isnan(F):
        # nearest equivalent relationship for intuition
        eq = [("parent-child / full sib", 0.25), ("half sib / uncle-niece", 0.125),
              ("first cousins", 0.0625), ("first cousins once removed", 0.03125),
              ("second cousins", 0.015625)]
        near = min(eq, key=lambda kv: abs(kv[1] - F))
        print(f"  ~ comparable to offspring of {near[0]} (F={near[1]})")

    if a.out:
        with open(a.out, "w") as fh:
            json.dump({"root": root, "root_name": rname, "by_generation": rep,
                       "summary": summ, "inbreeding_F": F}, fh, indent=2)
        print(f"\nwrote {a.out}")


if __name__ == "__main__":
    main()
