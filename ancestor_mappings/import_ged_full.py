#!/usr/bin/env python3
"""
import_ged_full.py
==================
Full two-branch import from a Geneanet GEDCOM.

  Paternal branch (David Villanueva Jasso side)
    → adds new ancestors + updates existing nodes in the three public HTML files
  Maternal branch (Maria Margaret Elbertse side)
    → generates private/maternal-lineage.html (NEVER pushed to GitHub)

Matching strategy (multi-pass):
  1. Exact normalised-name match (same as import_ged.py)
  2. Family-position match: if G is a parent of an already-matched C,
     look for an HTML parent of C's node with the same first given name

Usage:
    cd ancestor_mappings
    python3 import_ged_full.py /path/to/file.ged [--dry-run]
"""

import argparse, json, os, re, sys
from collections import deque

sys.path.insert(0, os.path.dirname(__file__))
from import_ged import (parse_ged, best_name, name_variants, norm,
                        extract_year, build_region, JUNK_REGIONS)

# ── Family graph helpers ──────────────────────────────────────────────────────

def build_family_maps(fams):
    parents_of  = {}   # indi_id -> [parent_ged_ids]
    children_of = {}   # indi_id -> [child_ged_ids]
    for fam in fams.values():
        parents = [p for p in [fam['husb'], fam['wife']] if p]
        for child in fam['chil']:
            parents_of.setdefault(child, []).extend(parents)
            for p in parents:
                children_of.setdefault(p, []).append(child)
    return parents_of, children_of


def bfs_ancestors(start_id, start_gen, parents_of):
    """Return {indi_id: gen} for all ancestors reachable from start_id."""
    visited = {}
    q = deque([(start_id, start_gen)])
    while q:
        iid, g = q.popleft()
        if iid in visited:
            continue
        visited[iid] = g
        for p in parents_of.get(iid, []):
            q.append((p, g + 1))
    return visited


# ── Name helpers ──────────────────────────────────────────────────────────────

_PARTICLES = {"de", "del", "la", "el", "los", "las", "y", "e", "a", "o",
              "von", "van", "le", "di", "da", "do", "das", "dos", "san",
              "santa", "r"}


def first_word(name_str):
    words = norm(name_str).split()
    return words[0] if words else ""


# ── Matching passes ───────────────────────────────────────────────────────────

def exact_match(branch, indis, html_nodes):
    """Pass 1: normalised-name exact match.  Returns {ged_id: html_node_id}."""
    node_by_norm = {}
    for n in html_nodes:
        k = norm(n.get('name', ''))
        node_by_norm.setdefault(k, []).append(n)

    matched = {}
    for ged_id in branch:
        indi = indis[ged_id]
        for v in name_variants(indi):
            k = norm(v)
            if k in node_by_norm:
                matched[ged_id] = node_by_norm[k][0]['id']
                break
    return matched


def family_position_match(branch, ged_to_html, children_of_ged,
                           html_parents_of, html_id_map, indis,
                           max_passes=15):
    """
    Pass 2: iteratively match unmatched GEDCOM ancestors by family position.

    If G is a parent of a matched C, look at HTML parents of C's html node.
    Match G to the HTML parent whose first given-name word equals G's.
    """
    ged_to_html = dict(ged_to_html)
    used_html = set(ged_to_html.values())

    for _ in range(max_passes):
        new_found = 0
        for ged_id in list(branch):
            if ged_id in ged_to_html:
                continue
            indi = indis[ged_id]
            g_fw = first_word(best_name(indi))

            for child_ged in children_of_ged.get(ged_id, []):
                if child_ged not in ged_to_html:
                    continue
                child_html = ged_to_html[child_ged]

                for parent_html_id in html_parents_of.get(child_html, []):
                    if parent_html_id in used_html:
                        continue
                    p_node = html_id_map.get(parent_html_id, {})
                    p_fw = first_word(p_node.get('name', ''))
                    if p_fw == g_fw:
                        ged_to_html[ged_id] = parent_html_id
                        used_html.add(parent_html_id)
                        new_found += 1
                        break
                if ged_id in ged_to_html:
                    break

        if new_found == 0:
            break

    return ged_to_html


# ── HTML graph I/O ────────────────────────────────────────────────────────────

def load_graph(html_path):
    with open(html_path, encoding='utf-8') as f:
        raw = f.read()
    m = re.search(r'(const GRAPH\s*=\s*)(\{\"nodes\".*?\});', raw, re.DOTALL)
    if not m:
        return None, raw, None
    g = json.loads(m.group(2))
    return g, raw, m


def save_graph(html_path, raw, match, g):
    new_json = json.dumps(g, ensure_ascii=False, separators=(',', ':'))
    new_raw = raw[:match.start(2)] + new_json + raw[match.end(2):]
    with open(html_path, 'w', encoding='utf-8') as f:
        f.write(new_raw)


# ── Node factory ──────────────────────────────────────────────────────────────

def make_node(html_id, indi, gen):
    name = best_name(indi)
    by   = extract_year(indi['birth'].get('date', ''))
    dy   = extract_year(indi['death'].get('date', ''))
    ctry = indi['birth'].get('country', '')
    reg  = build_region(indi['birth'])
    if reg and reg.lower() in JUNK_REGIONS:
        reg = ''
    return {
        'id': html_id, 'name': name, 'gen': gen,
        'birth': by, 'death': dy,
        'cat': 'untitled', 'titles': '', 'house': '',
        'country': ctry, 'region': reg, 'mult': 1,
    }


# ── Paternal: update one HTML file ───────────────────────────────────────────

def update_html_file(html_path, paternal_branch, indis, parents_of,
                     children_of_ged, verbose=True):
    """
    Load html_path, match paternal branch, add new nodes + edges, save.
    Returns (nodes_added, edges_added).
    """
    g, raw, m = load_graph(html_path)
    if g is None:
        print(f'  skip (no GRAPH): {html_path}')
        return 0, 0

    html_nodes   = g['nodes']
    html_id_map  = {n['id']: n for n in html_nodes}

    # HTML edge direction: s=parent → t=child
    html_parents_of = {}  # child html_id -> [parent html_ids]
    existing_edges  = set()
    for e in g['edges']:
        html_parents_of.setdefault(e['t'], []).append(e['s'])
        existing_edges.add((e['s'], e['t']))

    # Match
    ged_to_html = exact_match(paternal_branch, indis, html_nodes)
    ged_to_html = family_position_match(
        paternal_branch, ged_to_html, children_of_ged,
        html_parents_of, html_id_map, indis
    )

    # Update existing matched nodes (dates / country / region only)
    for ged_id, html_id in ged_to_html.items():
        indi = indis[ged_id]
        node = html_id_map.get(html_id)
        if node is None:
            continue
        by = extract_year(indi['birth'].get('date', ''))
        if by and node.get('birth') is None:
            node['birth'] = by
        dy = extract_year(indi['death'].get('date', ''))
        if dy and node.get('death') is None:
            node['death'] = dy
        ctry = indi['birth'].get('country', '')
        if ctry and not node.get('country'):
            node['country'] = ctry
        reg = build_region(indi['birth'])
        if reg and reg.lower() not in JUNK_REGIONS and not node.get('region'):
            node['region'] = reg

    # Add new nodes
    max_id = max(n['id'] for n in html_nodes)
    new_id = max_id + 1
    for ged_id, gen in sorted(paternal_branch.items(), key=lambda x: x[1]):
        if ged_id in ged_to_html:
            continue
        indi = indis[ged_id]
        new_node = make_node(new_id, indi, gen)
        g['nodes'].append(new_node)
        html_id_map[new_id] = new_node
        ged_to_html[ged_id] = new_id
        new_id += 1

    nodes_added = new_id - (max_id + 1)

    # Add edges
    edges_added = 0
    for ged_id in paternal_branch:
        if ged_id not in ged_to_html:
            continue
        child_html = ged_to_html[ged_id]
        for parent_ged in parents_of.get(ged_id, []):
            if parent_ged not in ged_to_html:
                continue
            parent_html = ged_to_html[parent_ged]
            edge = (parent_html, child_html)
            if edge not in existing_edges:
                g['edges'].append({'s': parent_html, 't': child_html})
                existing_edges.add(edge)
                edges_added += 1

    save_graph(html_path, raw, m, g)
    if verbose:
        name = os.path.basename(html_path)
        matched = len(ged_to_html) - nodes_added
        print(f'  {name}: matched={matched}  +{nodes_added} nodes  +{edges_added} edges')

    return nodes_added, edges_added


# ── Maternal: build standalone GRAPH ─────────────────────────────────────────

def build_maternal_graph(maternal_branch, indis, antonio_ged, mother_ged, parents_of):
    """
    Build GRAPH JSON for the private maternal lineage HTML.
    antonio_ged → id=0 (gen 0)
    mother_ged  → id=1 (gen 1)
    All other ancestors get sequential IDs starting at 2.
    """
    ged_to_mat = {antonio_ged: 0, mother_ged: 1}
    next_id = 2

    # BFS from mother upward to assign IDs in breadth order
    q = deque([mother_ged])
    visited = {antonio_ged, mother_ged}
    bfs_order = []
    while q:
        gid = q.popleft()
        for parent in parents_of.get(gid, []):
            if parent not in visited and parent in maternal_branch:
                visited.add(parent)
                bfs_order.append(parent)
                q.append(parent)

    for gid in bfs_order:
        ged_to_mat[gid] = next_id
        next_id += 1

    # Build nodes
    nodes = []

    # Antonio — fixed reference node (gen 0)
    nodes.append({
        'id': 0, 'name': 'Antonio Jasso', 'gen': 0,
        'birth': 1988, 'death': None,
        'cat': 'untitled', 'titles': '', 'house': '',
        'country': 'United States', 'region': 'Orange', 'mult': 1,
    })

    # Maria Margaret Elbertse (gen 1)
    mm = indis[mother_ged]
    mm_by   = extract_year(mm['birth'].get('date', ''))
    mm_ctry = mm['birth'].get('country', '')
    mm_reg  = build_region(mm['birth'])
    if mm_reg and mm_reg.lower() in JUNK_REGIONS:
        mm_reg = ''
    nodes.append({
        'id': 1, 'name': best_name(mm), 'gen': 1,
        'birth': mm_by, 'death': extract_year(mm['death'].get('date', '')),
        'cat': 'untitled', 'titles': '', 'house': '',
        'country': mm_ctry, 'region': mm_reg, 'mult': 1,
    })

    # All other maternal ancestors
    for gid in bfs_order:
        indi = indis[gid]
        gen  = maternal_branch[gid]   # from BFS (mother=1, her parents=2, …)
        nodes.append(make_node(ged_to_mat[gid], indi, gen))

    # Build edges
    edges = [{'s': 1, 't': 0}]  # Maria Margaret → Antonio (manual, GEDCOM has no this link)
    seen_edges = {(1, 0)}

    for gid in [mother_ged] + bfs_order:
        child_mat = ged_to_mat[gid]
        for parent_ged in parents_of.get(gid, []):
            if parent_ged not in ged_to_mat:
                continue
            parent_mat = ged_to_mat[parent_ged]
            e = (parent_mat, child_mat)
            if e not in seen_edges:
                edges.append({'s': parent_mat, 't': child_mat})
                seen_edges.add(e)

    return {'nodes': nodes, 'edges': edges}


# ── HTML generation from template ────────────────────────────────────────────

def generate_html(template_path, graph, title, subtitle):
    with open(template_path, encoding='utf-8') as f:
        tmpl = f.read()
    graph_json = json.dumps(graph, ensure_ascii=False, separators=(',', ':'))
    html = tmpl.replace('{{TITLE}}', title)
    html = html.replace('{{SUBTITLE}}', subtitle)
    html = html.replace('/*__DATA__*/', graph_json)
    return html


# ── Main ─────────────────────────────────────────────────────────────────────

ANTONIO_GED = '@I1@'
DAVID_GED   = '@I2@'
MM_GED      = '@I3@'

PUBLIC_HTML = [
    'antonio-jasso-lineage.html',
    'merged-lineage.html',
    'master-lineage.html',
]


def main():
    here = os.path.dirname(os.path.abspath(__file__))

    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('ged', help='Path to Geneanet GEDCOM file')
    ap.add_argument('--dir', default=here,
                    help='Directory containing the public HTML files')
    ap.add_argument('--private', default=os.path.join(here, '..', 'private'),
                    help='Directory for private maternal HTML output')
    ap.add_argument('--dry-run', action='store_true',
                    help='Show what would change without writing files')
    a = ap.parse_args()

    private_dir = os.path.abspath(a.private)

    print(f'\nParsing {a.ged} …')
    indis, fams = parse_ged(a.ged)
    print(f'  {len(indis)} individuals  ·  {len(fams)} families')

    parents_of, children_of = build_family_maps(fams)

    # Branch classification
    paternal = bfs_ancestors(DAVID_GED, 1, parents_of)
    paternal[ANTONIO_GED] = 0

    maternal = bfs_ancestors(MM_GED, 1, parents_of)
    maternal[ANTONIO_GED] = 0

    print(f'  Paternal branch: {len(paternal)} people')
    print(f'  Maternal branch: {len(maternal)} people')

    # ── Paternal: update public HTML files ───────────────────────────────────
    print('\n── Paternal import (public files) ──')

    if a.dry_run:
        # Quick preview against the first file only
        ref = os.path.join(a.dir, PUBLIC_HTML[0])
        g_ref, _, _ = load_graph(ref)
        if g_ref:
            html_id_map = {n['id']: n for n in g_ref['nodes']}
            html_parents_of = {}
            for e in g_ref['edges']:
                html_parents_of.setdefault(e['t'], []).append(e['s'])
            gtoh = exact_match(paternal, indis, g_ref['nodes'])
            gtoh = family_position_match(paternal, gtoh, children_of,
                                         html_parents_of, html_id_map, indis)
            unmatched = [(gid, gen) for gid, gen in paternal.items()
                         if gid not in gtoh]
            print(f'  Matched: {len(gtoh)}  Unmatched (would add): {len(unmatched)}')
            print('  New nodes preview (first 25):')
            for gid, gen in sorted(unmatched, key=lambda x: x[1])[:25]:
                indi = indis[gid]
                n = best_name(indi)
                by = extract_year(indi['birth'].get('date', ''))
                print(f'    gen {gen:>2}  {n}  b.{by}')
    else:
        for fname in PUBLIC_HTML:
            html_path = os.path.join(a.dir, fname)
            if not os.path.exists(html_path):
                print(f'  skip (not found): {fname}')
                continue
            update_html_file(html_path, paternal, indis, parents_of, children_of)

    # ── Maternal: generate private HTML ──────────────────────────────────────
    print('\n── Maternal import (private only) ──')

    mat_graph = build_maternal_graph(
        maternal, indis, ANTONIO_GED, MM_GED, parents_of
    )
    n_mat = len(mat_graph['nodes'])
    e_mat = len(mat_graph['edges'])
    print(f'  Maternal graph: {n_mat} nodes, {e_mat} edges')

    template_path = os.path.join(here, 'template.html')
    out_path = os.path.join(private_dir, 'maternal-lineage.html')

    if not a.dry_run:
        os.makedirs(private_dir, exist_ok=True)
        html_out = generate_html(
            template_path,
            mat_graph,
            'Maria Margaret Elbertse — Maternal Lineage',
            'Private maternal lineage of Antonio Jasso · '
            'Elbertse / DeBruyn family (Utrecht, Netherlands)'
        )
        with open(out_path, 'w', encoding='utf-8') as f:
            f.write(html_out)
        print(f'  Written: {out_path}')
        print('  (This file is in private/ — git-ignored, never pushed)')
    else:
        print(f'  [dry-run] Would write: {out_path}')

    print('\nDone.')


if __name__ == '__main__':
    main()
