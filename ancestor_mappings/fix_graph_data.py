#!/usr/bin/env python3
"""
fix_graph_data.py
=================
One-time cleanup of bad edges and duplicate nodes across the three public
lineage HTML files.

Problems fixed
--------------
1. REVERSED edges: parent_gen <= child_gen  (s=parent, t=child)
   - same-gen edges  (parent_gen == child_gen): 293 in antonio-jasso-lineage
   - reversed edges  (parent_gen  < child_gen): 413 in antonio-jasso-lineage
   Both break the topological sort in pedigree_metrics.py, causing the
   "608 nodes in a cycle" warning and inflate the >2-parents count.

2. DUPLICATE node: "Maria Bartola Sipriana De La Torre" is the same person
   as "Blasa Bartola Cipriana de la Torre y de Aro" (gen 9 in all files).
   Merge the new Geneanet node into the original Geni.com node.

Usage
-----
    cd ancestor_mappings
    python3 fix_graph_data.py [--dry-run]
"""
import argparse, json, os, re, sys

HTML_FILES = [
    'antonio-jasso-lineage.html',
    'merged-lineage.html',
    'master-lineage.html',
]

# Duplicate pair: (keep_name_fragment, drop_name_fragment)
BARTOLA_KEEP = 'blasa bartola'
BARTOLA_DROP = 'maria bartola sipriana'


def load_graph(path):
    with open(path, encoding='utf-8') as f:
        raw = f.read()
    m = re.search(r'(const GRAPH\s*=\s*)(\{\"nodes\".*?\});', raw, re.DOTALL)
    if not m:
        sys.exit(f'No GRAPH in {path}')
    return json.loads(m.group(2)), raw, m


def save_graph(path, raw, match, g):
    new_json = json.dumps(g, ensure_ascii=False, separators=(',', ':'))
    new_raw = raw[:match.start(2)] + new_json + raw[match.end(2):]
    with open(path, 'w', encoding='utf-8') as f:
        f.write(new_raw)


def fix_file(path, dry_run=False):
    g, raw, match = load_graph(path)
    id_map = {n['id']: n for n in g['nodes']}
    name = os.path.basename(path)

    # ── 1. Merge Bartola duplicate ────────────────────────────────────────────
    keep_node = next((n for n in g['nodes']
                      if BARTOLA_KEEP in n['name'].lower()), None)
    drop_node = next((n for n in g['nodes']
                      if BARTOLA_DROP in n['name'].lower()), None)

    bartola_merged = 0
    if keep_node and drop_node:
        keep_id = keep_node['id']
        drop_id = drop_node['id']

        # Enrich keep_node with any data from drop_node that's missing
        for field in ('birth', 'death', 'country', 'region'):
            if not keep_node.get(field) and drop_node.get(field):
                keep_node[field] = drop_node[field]

        # Rewrite all edges: drop_id → keep_id, deduplicate
        new_edges, seen = [], set()
        for e in g['edges']:
            s = keep_id if e['s'] == drop_id else e['s']
            t = keep_id if e['t'] == drop_id else e['t']
            key = (s, t)
            if s != t and key not in seen:
                seen.add(key)
                new_edges.append({'s': s, 't': t})
        g['edges'] = new_edges

        # Remove drop node
        g['nodes'] = [n for n in g['nodes'] if n['id'] != drop_id]
        id_map = {n['id']: n for n in g['nodes']}
        bartola_merged = 1

    # ── 2. Remove bad-direction edges ────────────────────────────────────────
    # Rule: edge s→t is valid only if parent_gen > child_gen
    # (parent must be at a higher generation number = further back in time)
    good_edges, bad_edges = [], []
    for e in g['edges']:
        s, t = e['s'], e['t']
        sg = id_map.get(s, {}).get('gen', -1)
        tg = id_map.get(t, {}).get('gen', -1)
        if sg == -1 or tg == -1:
            good_edges.append(e)      # unknown gen: keep and don't flag
            continue
        if sg > tg:
            good_edges.append(e)      # correct direction
        else:
            bad_edges.append(e)       # same-gen or reversed

    removed_edges = len(bad_edges)
    g['edges'] = good_edges

    # ── 3. Report ─────────────────────────────────────────────────────────────
    # Count remaining >2-parent nodes
    parents_of = {}
    for e in g['edges']:
        parents_of.setdefault(e['t'], []).append(e['s'])
    over2 = {nid: ps for nid, ps in parents_of.items() if len(ps) > 2}

    print(f'\n{name}:')
    if bartola_merged:
        print(f'  Merged "Maria Bartola Sipriana" → "Blasa Bartola Cipriana"')
    print(f'  Removed {removed_edges} bad-direction edges '
          f'(same-gen: {sum(1 for e in bad_edges if id_map.get(e["s"],{}).get("gen",-1)==id_map.get(e["t"],{}).get("gen",-1))}, '
          f'reversed: {sum(1 for e in bad_edges if id_map.get(e["s"],{}).get("gen",-1)<id_map.get(e["t"],{}).get("gen",-1))})')
    print(f'  Nodes with >2 parents remaining: {len(over2)}')
    if over2:
        for nid, ps in sorted(over2.items(), key=lambda x: -len(x[1]))[:8]:
            node = id_map.get(nid, {})
            print(f'    id={nid:>5} gen={node.get("gen","?"):>3}  '
                  f'{node.get("name","?")[:50]}  ({len(ps)} parents)')
    print(f'  Final: {len(g["nodes"])} nodes, {len(g["edges"])} edges')

    if not dry_run:
        save_graph(path, raw, match, g)

    return removed_edges, bartola_merged, len(over2)


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--dry-run', action='store_true')
    a = ap.parse_args()

    tag = '[DRY RUN] ' if a.dry_run else ''
    print(f'{tag}Fixing graph data across {len(HTML_FILES)} files …')

    for fname in HTML_FILES:
        path = os.path.join(here, fname)
        if not os.path.exists(path):
            print(f'  skip (not found): {fname}')
            continue
        fix_file(path, dry_run=a.dry_run)

    if a.dry_run:
        print('\n[dry-run] No files written.')
    else:
        print('\nDone. Run pedigree_metrics.py again to verify warnings are gone.')


if __name__ == '__main__':
    main()
