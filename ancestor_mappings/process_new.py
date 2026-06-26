#!/usr/bin/env python3
"""
process_new.py
==============
Scan the directory for source files (PDF / TXT), parse any that have not yet
produced a lineage HTML, then merge everything into one master graph.

Node deduplication uses the same norm-name|birth-year key as the pipeline,
so a person that appears across multiple source files is stored exactly once.

Usage
-----
    python process_new.py [options]

Options
    --dir PATH          directory to scan (default: directory of this script)
    --outdir PATH       where to write HTML files (default: same as --dir)
    --master PATH       path for the combined master HTML
                        (default: <outdir>/master-lineage.html)
    --template PATH     HTML template (default: ./template.html)
    --d3 PATH           d3 min.js (default: ./d3.min.js)
    --force             re-parse source files even if an HTML already exists
"""
import argparse
import glob
import json
import os
import re
import sys
import unicodedata

# ── import pipeline helpers ────────────────────────────────────────────────
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from geni_pipeline import (
    extract_lines, parse_occurrences, clean_occurrence, build_graph,
    assign_int_ids, resolve_yearless_duplicates, remove_placeholders,
    strip_accents, norm, classify, extract_region, extract_house,
    present_categories, make_meta, render_html, PLACEHOLDER_RE,
)

# ── node key (identical to merge_graphs.py) ───────────────────────────────
_uid = [0]

def node_key(n: dict) -> str | None:
    nm = norm(n["name"])
    if PLACEHOLDER_RE.match(nm) or len(nm) < 4:
        return None                 # placeholders are never shared
    yr = n.get("birth")
    return f"{nm}|{yr}" if yr is not None else f"{nm}|?"


def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-",
                  strip_accents(name).lower()).strip("-")


# ── load existing nodes from already-rendered HTML files ──────────────────
def load_existing_keys(html_dir: str) -> set[str]:
    keys: set[str] = set()
    for path in glob.glob(os.path.join(html_dir, "*-lineage.html")):
        try:
            with open(path) as f:
                content = f.read()
            m = re.search(r"const GRAPH\s*=\s*(\{\"nodes\".*?\});",
                          content, re.DOTALL)
            if not m:
                continue
            nodes = json.loads(m.group(1))["nodes"]
            for n in nodes:
                k = node_key(n)
                if k:
                    keys.add(k)
        except Exception:
            pass
    return keys


# ── source file discovery ─────────────────────────────────────────────────
def find_source_files(scan_dir: str) -> list[str]:
    sources = []
    for ext in ("*.pdf", "*.txt"):
        sources.extend(glob.glob(os.path.join(scan_dir, ext)))
    return sorted(sources)


def expected_html(src: str, out_dir: str) -> str:
    """Given a source path, return the expected output HTML path."""
    base = os.path.splitext(os.path.basename(src))[0]
    # normalise the stem the same way the pipeline does for its default output
    s = re.sub(r"[^a-z0-9]+", "-", strip_accents(base).lower()).strip("-")
    # pipeline appends -lineage.html, but the stem already has plenty of words;
    # use a shorter slug derived from the first meaningful token instead
    return os.path.join(out_dir, f"{s}-lineage.html")


# ── parse one source file → individual HTML ───────────────────────────────
def parse_source(src: str, out_path: str,
                 template: str, d3: str) -> tuple[str, list, list]:
    """Parse src, write out_path, return (root_name, nodes, edges)."""
    lines   = extract_lines(src)
    people  = [clean_occurrence(o) for o in parse_occurrences(lines)]
    if not people:
        print(f"    WARNING: no people found in {src}")
        return "", [], []

    root_name = people[0]["name"]
    nodes_d, edges_s = build_graph(people, dedupe=True)
    nodes, edges = assign_int_ids(nodes_d, edges_s)

    if os.path.exists(template) and os.path.exists(d3):
        title, subtitle = make_meta(nodes, root_name)
        legend = present_categories(nodes)
        render_html(nodes, edges, title, subtitle, legend,
                    template, d3, out_path)

    return root_name, nodes, edges


# ── incremental merge ─────────────────────────────────────────────────────
def merge_into_master(
    master_nodes: dict,   # key → node dict
    master_edges: set,    # set of (key_s, key_t)
    nodes: list,          # from a single parsed tree
    edges: list,          # int-id edges
    known_before: set[str],  # keys that existed before this batch
) -> tuple[int, int]:
    """
    Merge nodes/edges into master, skipping nodes whose key already exists.
    Returns (new_nodes_added, new_edges_added).
    """
    id_to_key: dict[int, str | None] = {}
    new_n = new_e = 0

    for n in nodes:
        k = node_key(n)
        id_to_key[n["id"]] = k
        if k is None:
            # placeholder — give it a unique key so it never merges
            _uid[0] += 1
            k = f"_uid_{_uid[0]}::{norm(n['name'])}"
            id_to_key[n["id"]] = k

        if k not in master_nodes:
            master_nodes[k] = dict(n, id=k)
            if k not in known_before:
                new_n += 1
        else:
            ex = master_nodes[k]
            ex["mult"] += n.get("mult", 1)
            ex["gen"]   = min(ex["gen"], n["gen"])
            if ex["birth"] is None and n.get("birth") is not None:
                ex["birth"] = n["birth"]
            if ex["death"] is None and n.get("death") is not None:
                ex["death"] = n["death"]

    for e in edges:
        ks = id_to_key.get(e["s"])
        kt = id_to_key.get(e["t"])
        if ks and kt and ks != kt:
            if (ks, kt) not in master_edges:
                master_edges.add((ks, kt))
                new_e += 1

    return new_n, new_e


# ── main ──────────────────────────────────────────────────────────────────
def main() -> None:
    ap = argparse.ArgumentParser(description="Batch-process new Geni source files")
    ap.add_argument("--dir",      default=HERE)
    ap.add_argument("--outdir",   default=None)
    ap.add_argument("--master",   default=None)
    ap.add_argument("--template", default=os.path.join(HERE, "template.html"))
    ap.add_argument("--d3",       default=os.path.join(HERE, "d3.min.js"))
    ap.add_argument("--force",    action="store_true")
    args = ap.parse_args()

    out_dir = args.outdir or args.dir
    os.makedirs(out_dir, exist_ok=True)
    master_path = args.master or os.path.join(out_dir, "master-lineage.html")

    # ── 1. snapshot of what is already known ─────────────────────────────
    print("Loading existing lineage files …")
    known_before = load_existing_keys(out_dir)
    print(f"  {len(known_before):,} unique ancestor keys already indexed\n")

    # ── 2. discover source files ──────────────────────────────────────────
    sources = find_source_files(args.dir)
    print(f"Found {len(sources)} source file(s) in {args.dir}")

    new_sources, skip_sources = [], []
    for src in sources:
        out = expected_html(src, out_dir)
        if not args.force and os.path.exists(out):
            skip_sources.append(src)
        else:
            new_sources.append(src)

    print(f"  {len(skip_sources)} already processed (skipping)")
    print(f"  {len(new_sources)} new / unprocessed\n")

    if not new_sources:
        print("Nothing new to process.")
        return

    # ── 3. seed master from existing HTMLs ───────────────────────────────
    master_nodes: dict[str, dict] = {}
    master_edges: set[tuple]      = set()

    for path in sorted(glob.glob(os.path.join(out_dir, "*-lineage.html"))):
        if path == master_path:
            continue
        try:
            with open(path) as f:
                content = f.read()
            m = re.search(r"const GRAPH\s*=\s*(\{\"nodes\".*?\});",
                          content, re.DOTALL)
            if not m:
                continue
            data  = json.loads(m.group(1))
            nodes = data["nodes"]
            edges = data["edges"]
            # Re-classify and back-fill region/house for pre-built nodes
            for n in nodes:
                n["cat"], n["titles"] = classify(n["name"])
                if not n.get("region"):
                    n["region"] = extract_region(n["name"])
                if not n.get("house"):
                    n["house"] = extract_house(n["name"])
            merge_into_master(master_nodes, master_edges,
                              nodes, edges, known_before)
        except Exception as exc:
            print(f"  WARNING: could not load {path}: {exc}")

    # ── 4. parse each new source ──────────────────────────────────────────
    print("Processing new source files:")
    for src in new_sources:
        out_path = expected_html(src, out_dir)
        basename = os.path.basename(src)
        try:
            root_name, nodes, edges = parse_source(
                src, out_path, args.template, args.d3)
        except Exception as exc:
            print(f"  ✗  {basename}  ERROR: {exc}")
            continue

        if not nodes:
            print(f"  ✗  {basename}  (empty)")
            continue

        new_n, new_e = merge_into_master(
            master_nodes, master_edges, nodes, edges, known_before)

        status = "NEW" if new_n else "dup"
        print(f"  {'+'if new_n else '·'}  {root_name}")
        print(f"       {len(nodes):>5} people  {new_n:>5} new nodes  "
              f"{new_e:>5} new bonds  →  {os.path.basename(out_path)}")

    # ── 5. resolve name|? / name|YEAR duplicates ─────────────────────────
    collapsed = resolve_yearless_duplicates(master_nodes, master_edges)
    if collapsed:
        print(f"\n  Resolved {collapsed} yearless duplicate(s) "
              f"(same name, one with birth year / one without)")

    # ── 6. emit master ────────────────────────────────────────────────────
    print(f"\nBuilding master graph …")
    # assign fresh integer ids
    order  = list(master_nodes.keys())
    idmap  = {k: i for i, k in enumerate(order)}
    out_nodes = [dict(master_nodes[k], id=idmap[k]) for k in order]
    out_edges = [{"s": idmap[a], "t": idmap[b]}
                 for a, b in master_edges if a in idmap and b in idmap]

    # Remove placeholders and isolated floating nodes
    out_nodes, out_edges, n_removed = remove_placeholders(out_nodes, out_edges)
    if n_removed:
        print(f"  Removed {n_removed} placeholder / isolated node(s)")

    title    = "Master Lineage"
    subtitle = (f"{len(out_nodes):,} ancestors · "
                f"{len(out_edges):,} bonds · all sources combined")
    legend   = present_categories(out_nodes)

    have_assets = (os.path.exists(args.template) and os.path.exists(args.d3))
    if have_assets:
        render_html(out_nodes, out_edges, title, subtitle, legend,
                    args.template, args.d3, master_path)
        print(f"  {len(out_nodes):,} people, {len(out_edges):,} bonds  →  {master_path}")
    else:
        print(f"  {len(out_nodes):,} people, {len(out_edges):,} bonds  "
              f"(template/d3 not found — HTML not written)")


if __name__ == "__main__":
    main()
