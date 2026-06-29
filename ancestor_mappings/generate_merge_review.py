#!/usr/bin/env python3
"""
generate_merge_review.py
=========================
Generates private/merge-review.html — an interactive page to review
proposed duplicate-node merges before committing anything.

For each proposed merge pair/group it shows both nodes side-by-side
with their full parent/child context so you can confirm they're the
same person (or mark them as distinct).

Decisions are saved to localStorage. Export button → merge-decisions.json
which apply_merges.py will use to patch the lineage files.

Usage:
    cd ancestor_mappings
    python3 generate_merge_review.py
    open ../private/merge-review.html
"""
import json, os, re, sys
from collections import defaultdict

LINEAGE_HTML = os.path.join(os.path.dirname(__file__), 'antonio-jasso-lineage.html')
OUT_HTML     = os.path.join(os.path.dirname(__file__), '..', 'private', 'merge-review.html')

SKIP_NAMES = {
    'n.n.', 'nn', 'nn nn', 'n n', 'n', '.... ....', '....', 'x x',
    '??? ???', 'unknown', 'unknown unknown', 'n.n. .', 'n.n', 'nn.',
}


def load_graph(path):
    with open(path, encoding='utf-8') as f:
        raw = f.read()
    m = re.search(r'const GRAPH\s*=\s*(\{"nodes".*?\});', raw, re.DOTALL)
    if not m:
        sys.exit(f'No GRAPH in {path}')
    g = json.loads(m.group(1))
    id_map = {n['id']: n for n in g['nodes']}
    parents_of  = defaultdict(list)
    children_of = defaultdict(list)
    for e in g['edges']:
        parents_of[e['t']].append(e['s'])
        children_of[e['s']].append(e['t'])
    return id_map, dict(parents_of), dict(children_of)


def norm(s):
    return re.sub(r'\s+', ' ', s.lower().strip()) if s else ''


def yr(val):
    if not val:
        return None
    m = re.search(r'\b(\d{3,4})\b', str(val))
    return int(m.group(1)) if m else None


def node_detail(nid, id_map, parents_of, children_of):
    n = id_map.get(nid, {})
    parents  = [{'id': pid,
                  'name': id_map[pid].get('name', '?') if pid in id_map else '?',
                  'birth': id_map[pid].get('birth') if pid in id_map else None}
                for pid in parents_of.get(nid, [])]
    children = [{'id': cid,
                  'name': id_map[cid].get('name', '?') if cid in id_map else '?',
                  'birth': id_map[cid].get('birth') if cid in id_map else None}
                for cid in children_of.get(nid, [])]
    return {
        'id':      nid,
        'name':    n.get('name', '?'),
        'gen':     n.get('gen'),
        'birth':   n.get('birth'),
        'death':   n.get('death'),
        'country': n.get('country', ''),
        'region':  n.get('region', ''),
        'source':  'geni' if nid < 3385 else 'geneanet',
        'parents': parents,
        'children': children,
    }


def find_duplicates(id_map, parents_of, children_of):
    """Find groups of nodes that appear to be the same person."""
    name_map = defaultdict(list)
    for nid, n in id_map.items():
        nm = norm(n.get('name', ''))
        if nm and nm not in SKIP_NAMES and len(nm) > 2:
            name_map[nm].append(nid)

    groups = []
    seen_ids = set()

    for nm, ids in sorted(name_map.items()):
        if len(ids) < 2:
            continue

        nodes = [id_map[i] for i in ids]
        gens   = [n.get('gen') for n in nodes]
        births = [yr(n.get('birth')) for n in nodes]

        # Build sub-groups: ids that share (gen, ~birth_year) or are orphan duplicates
        # Strategy: cluster by gen first, then by birth year proximity
        clusters = []
        used = set()
        for i, a in enumerate(ids):
            if a in used:
                continue
            cluster = [a]
            used.add(a)
            for j, b in enumerate(ids):
                if b in used or i == j:
                    continue
                ga, gb = id_map[a].get('gen'), id_map[b].get('gen')
                ba, bb = yr(id_map[a].get('birth')), yr(id_map[b].get('birth'))
                # Same gen, birth within 5yr (or both None)
                if ga == gb:
                    if (ba is None and bb is None) or (ba and bb and abs(ba-bb) <= 5):
                        cluster.append(b)
                        used.add(b)
            if len(cluster) > 1:
                clusters.append(cluster)

        for cluster in clusters:
            # Skip if any id already handled
            if any(i in seen_ids for i in cluster):
                continue
            # Determine why flagged
            cluster_nodes = [id_map[i] for i in cluster]
            bs = [yr(n.get('birth')) for n in cluster_nodes]
            all_orphan = all(
                i not in parents_of and i not in children_of
                for i in cluster
            )
            reason = 'orphan duplicates' if all_orphan else 'same name + gen + birth year'
            groups.append({
                'name':   nm,
                'reason': reason,
                'nodes':  [node_detail(i, id_map, parents_of, children_of)
                           for i in cluster],
            })
            for i in cluster:
                seen_ids.add(i)

    # Catalina Ramírez self-chain: flag separately since gens differ
    cat_ids = [nid for nid, n in id_map.items()
               if norm(n.get('name','')) == 'catalina ramírez dorantez y carranza']
    if len(cat_ids) > 1:
        already = all(i in seen_ids for i in cat_ids)
        if not already:
            groups.append({
                'name':   'catalina ramírez dorantez y carranza',
                'reason': 'self-referencing loop — same person across gen 16/17/18',
                'nodes':  [node_detail(i, id_map, parents_of, children_of)
                           for i in sorted(cat_ids, key=lambda x: id_map[x].get('gen',99))],
            })

    # Sort: non-orphans first (more interesting), then by gen
    def sort_key(g):
        min_gen = min(n['gen'] or 99 for n in g['nodes'])
        is_orphan = g['reason'] == 'orphan duplicates'
        return (is_orphan, min_gen)

    groups.sort(key=sort_key)
    return groups


def generate_html(groups):
    data_json = json.dumps(groups, ensure_ascii=False)
    count = len(groups)

    return f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Merge Review — Antonio Jasso Lineage ({count} groups)</title>
<style>
:root {{
  --bg:#1a1610;--surface:#231f18;--card:#2b2620;--card2:#332d25;
  --or:#c8a84b;--or-dim:#8a7030;--parchment:#e9dec3;--pdim:#a89b7a;
  --blue:#4a90d9;--blue-dim:#2c5580;--gnet:#c8a84b;--gnet-dim:#554830;
  --green:#27ae60;--red:#c0392b;--purple:#8e44ad;--teal:#16a085;
  --line:rgba(200,168,75,.12);--hair:rgba(200,168,75,.22);
  --geni-bg:rgba(41,128,185,.10);--geni-border:rgba(41,128,185,.30);
  --gnet-bg:rgba(200,168,75,.08);--gnet-border:rgba(200,168,75,.28);
}}
*{{box-sizing:border-box;margin:0;padding:0}}
body{{background:var(--bg);color:var(--parchment);
  font-family:ui-sans-serif,system-ui,sans-serif;font-size:13px;
  display:flex;height:100vh;overflow:hidden}}

/* ── Sidebar ──────────────────────────────────────────────── */
#sidebar{{width:270px;flex:none;border-right:1px solid var(--hair);
  overflow-y:auto;background:var(--surface);display:flex;flex-direction:column}}
#sidebar-header{{padding:14px 16px;border-bottom:1px solid var(--hair);flex:none}}
#sidebar-header h1{{font-size:14px;font-weight:700;color:var(--or);letter-spacing:.05em}}
#sidebar-header p{{font-size:11px;color:var(--pdim);margin-top:4px;line-height:1.4}}
#progress-bar-wrap{{padding:10px 16px 0;flex:none}}
#progress-text{{font-size:11px;color:var(--pdim);margin-bottom:5px}}
#progress-bar{{height:4px;background:rgba(200,168,75,.15);border-radius:2px;overflow:hidden}}
#progress-fill{{height:100%;background:var(--green);border-radius:2px;transition:width .3s}}
#node-list{{flex:1;overflow-y:auto;padding:8px 0}}
.node-item{{padding:10px 16px;cursor:pointer;border-bottom:1px solid var(--line);
  transition:background .12s;display:flex;align-items:flex-start;gap:8px}}
.node-item:hover{{background:rgba(200,168,75,.06)}}
.node-item.active{{background:rgba(200,168,75,.12);border-left:2px solid var(--or)}}
.node-item .count-badge{{
  font-size:10px;font-weight:700;color:var(--or-dim);
  background:rgba(200,168,75,.1);border-radius:3px;
  padding:2px 5px;flex:none;margin-top:1px;letter-spacing:.05em}}
.node-item .nm{{font-size:12px;color:var(--parchment);line-height:1.3;flex:1;min-width:0}}
.node-item .nm .sub{{font-size:10px;color:var(--pdim);margin-top:2px}}
.node-item .status-dot{{
  width:8px;height:8px;border-radius:50%;flex:none;margin-top:4px;
  background:var(--or-dim)}}
.node-item.resolved .status-dot{{background:var(--green)}}
.node-item.flagged  .status-dot{{background:var(--purple)}}
.node-item.distinct .status-dot{{background:var(--teal)}}
#export-btn{{
  margin:12px 16px;padding:9px 14px;
  background:rgba(200,168,75,.1);border:1px solid var(--hair);
  color:var(--or);border-radius:4px;cursor:pointer;
  font-size:11px;font-weight:600;letter-spacing:.08em;text-transform:uppercase;
  flex:none;transition:background .15s}}
#export-btn:hover{{background:rgba(200,168,75,.2)}}

/* ── Main panel ────────────────────────────────────────────── */
#main{{flex:1;overflow-y:auto;padding:28px 32px}}
#empty-state{{
  display:flex;flex-direction:column;align-items:center;justify-content:center;
  height:100%;color:var(--pdim);text-align:center;gap:12px}}
#empty-state .icon{{font-size:40px;opacity:.4}}
#detail{{display:none}}

.nav-row{{display:flex;justify-content:space-between;align-items:center;
  margin-bottom:20px;padding-bottom:14px;border-bottom:1px solid var(--line)}}
.nav-row button{{
  background:transparent;border:1px solid var(--hair);color:var(--pdim);
  padding:6px 14px;border-radius:4px;cursor:pointer;font-size:11px;
  letter-spacing:.1em;text-transform:uppercase;transition:border-color .15s,color .15s}}
.nav-row button:hover{{border-color:var(--or);color:var(--or)}}
.nav-row button:disabled{{opacity:.3;cursor:default}}
.nav-row .pos{{font-size:12px;color:var(--pdim)}}

.group-header{{margin-bottom:20px}}
.group-header .eyebrow{{
  font-size:10px;font-weight:700;letter-spacing:.22em;text-transform:uppercase;
  color:var(--or-dim);margin-bottom:8px}}
.group-header h2{{font-size:20px;font-weight:700;color:var(--or);margin-bottom:6px;
  word-break:break-word}}
.reason-tag{{
  display:inline-block;font-size:10px;padding:3px 8px;border-radius:3px;
  background:rgba(200,168,75,.1);border:1px solid var(--gnet-border);
  color:var(--pdim);letter-spacing:.05em;margin-bottom:16px}}

/* Node cards grid */
.node-cards{{display:grid;gap:14px;margin-bottom:24px}}
.node-cards.two{{grid-template-columns:1fr 1fr}}
.node-cards.three{{grid-template-columns:1fr 1fr 1fr}}
@media(max-width:900px){{.node-cards.two,.node-cards.three{{grid-template-columns:1fr}}}}

.node-card{{border-radius:8px;overflow:hidden;border:1px solid}}
.node-card.geni{{background:var(--geni-bg);border-color:var(--geni-border)}}
.node-card.geneanet{{background:var(--gnet-bg);border-color:var(--gnet-border)}}

.nc-header{{
  padding:8px 13px;font-size:10px;font-weight:700;
  letter-spacing:.18em;text-transform:uppercase;
  border-bottom:1px solid rgba(255,255,255,.05);
  display:flex;align-items:center;justify-content:space-between}}
.node-card.geni .nc-header{{color:var(--blue);background:var(--blue-dim)}}
.node-card.geneanet .nc-header{{color:var(--or);background:var(--gnet-dim)}}
.nc-header .nc-id{{font-size:10px;opacity:.7;letter-spacing:.05em}}

.nc-body{{padding:13px}}
.nc-name{{font-size:14px;font-weight:700;color:var(--parchment);margin-bottom:6px;
  word-break:break-word}}
.nc-meta{{font-size:11px;color:var(--pdim);margin-bottom:10px;line-height:1.7}}
.nc-meta span{{display:inline-block;margin-right:12px}}

.nc-section{{margin-top:8px}}
.nc-section-label{{
  font-size:10px;font-weight:700;letter-spacing:.18em;text-transform:uppercase;
  color:var(--or-dim);margin-bottom:5px}}
.rel-list{{display:flex;flex-direction:column;gap:3px}}
.rel-item{{
  font-size:11px;color:var(--pdim);padding:4px 8px;
  background:var(--card2);border-radius:4px;display:flex;gap:6px;align-items:center}}
.rel-item .arrow{{color:var(--or-dim);flex:none}}
.rel-item .rname{{color:var(--parchment)}}
.rel-item .ryr{{color:var(--pdim)}}
.empty-rel{{font-size:11px;color:var(--or-dim);font-style:italic;padding:4px 8px}}

/* Merged result preview */
.merge-preview{{
  border-radius:8px;border:1px solid rgba(39,174,96,.3);
  background:rgba(39,174,96,.06);margin-bottom:20px;overflow:hidden}}
.merge-preview-header{{
  padding:8px 14px;font-size:10px;font-weight:700;letter-spacing:.18em;
  text-transform:uppercase;color:var(--green);
  background:rgba(39,174,96,.12);border-bottom:1px solid rgba(39,174,96,.2);
  display:flex;justify-content:space-between;align-items:center}}
.merge-preview-header .mp-ids{{font-size:10px;opacity:.7;letter-spacing:.05em}}
.merge-preview-body{{padding:13px;display:grid;grid-template-columns:1fr 1fr;gap:14px}}
@media(max-width:800px){{.merge-preview-body{{grid-template-columns:1fr}}}}
.mp-section-label{{
  font-size:10px;font-weight:700;letter-spacing:.18em;text-transform:uppercase;
  color:rgba(39,174,96,.7);margin-bottom:5px}}
.mp-item{{
  font-size:11px;color:var(--pdim);padding:4px 8px;
  background:var(--card2);border-radius:4px;display:flex;gap:6px;align-items:center}}
.mp-item .arrow{{color:rgba(39,174,96,.6);flex:none}}
.mp-item .rname{{color:var(--parchment)}}
.mp-item .tag{{
  font-size:9px;padding:1px 5px;border-radius:2px;
  background:rgba(39,174,96,.15);color:rgba(39,174,96,.8);
  border:1px solid rgba(39,174,96,.25);flex:none}}
.mp-empty{{font-size:11px;color:var(--or-dim);font-style:italic;padding:4px 8px}}

/* Decision bar */
.decision-bar{{
  display:flex;gap:8px;flex-wrap:wrap;margin-bottom:28px;
  padding:16px;background:var(--card);border-radius:8px;border:1px solid var(--line)}}
.decision-bar .label{{
  font-size:10px;font-weight:700;letter-spacing:.15em;text-transform:uppercase;
  color:var(--pdim);width:100%;margin-bottom:4px}}
.dec-btn{{
  padding:9px 16px;border-radius:4px;cursor:pointer;font-size:11px;
  font-weight:700;letter-spacing:.1em;text-transform:uppercase;border:1px solid;
  transition:opacity .15s,transform .1s}}
.dec-btn:hover{{opacity:.85}}
.dec-btn:active{{transform:scale(.97)}}
.dec-btn.btn-merge-first{{background:rgba(39,174,96,.12);border-color:var(--green);color:var(--green)}}
.dec-btn.btn-merge-last {{background:rgba(39,174,96,.12);border-color:var(--green);color:var(--green)}}
.dec-btn.btn-distinct   {{background:rgba(22,160,133,.12);border-color:var(--teal);color:var(--teal)}}
.dec-btn.btn-flag       {{background:rgba(142,68,173,.12);border-color:var(--purple);color:var(--purple)}}
.dec-btn.btn-clear      {{background:rgba(192,57,43,.10);border-color:var(--red);color:var(--red)}}
.dec-btn.selected       {{opacity:1;box-shadow:0 0 0 2px currentColor}}

.current-decision{{
  display:none;padding:10px 14px;border-radius:6px;font-size:12px;
  font-weight:600;margin-bottom:16px;letter-spacing:.05em}}
.current-decision.show{{display:block}}
.current-decision.merge-first,
.current-decision.merge-last {{background:rgba(39,174,96,.15);color:var(--green);border:1px solid var(--green)}}
.current-decision.distinct   {{background:rgba(22,160,133,.12);color:var(--teal);border:1px solid var(--teal)}}
.current-decision.flagged    {{background:rgba(142,68,173,.12);color:var(--purple);border:1px solid var(--purple)}}
</style>
</head>
<body>

<div id="sidebar">
  <div id="sidebar-header">
    <h1>Merge Review</h1>
    <p>Proposed duplicate merges — review each group and decide before any changes are made.</p>
  </div>
  <div id="progress-bar-wrap">
    <div id="progress-text">0 of {count} reviewed</div>
    <div id="progress-bar"><div id="progress-fill" style="width:0%"></div></div>
  </div>
  <div id="node-list"></div>
  <button id="export-btn">Export Decisions ↓</button>
</div>

<div id="main">
  <div id="empty-state">
    <div class="icon">🔍</div>
    <div style="font-size:15px;font-weight:600;color:var(--parchment)">Select a group to review</div>
    <div style="font-size:12px;max-width:320px">Each entry is a set of nodes with the same name that may be the same person imported multiple times. Confirm the merge or mark them as distinct.</div>
  </div>
  <div id="detail"></div>
</div>

<script>
const GROUPS = {data_json};
const STORAGE_KEY = 'merge_decisions_v1';

function loadDecisions() {{
  try {{ return JSON.parse(localStorage.getItem(STORAGE_KEY) || '{{}}'); }}
  catch(e) {{ return {{}}; }}
}}
function saveDecision(key, decision) {{
  const d = loadDecisions();
  if (decision === null) delete d[key];
  else d[key] = decision;
  localStorage.setItem(STORAGE_KEY, JSON.stringify(d));
  updateProgress();
  renderSidebar();
}}
function groupKey(g) {{
  return g.nodes.map(n => n.id).sort().join(',');
}}

let currentIdx = null;

function fmtNode(n) {{
  const parts = [
    n.birth ? `b.${{n.birth}}` : '',
    n.death ? `d.${{n.death}}` : '',
    n.region || '', n.country || '',
  ].filter(Boolean);
  return parts.join(' · ');
}}

function relHtml(list, arrow) {{
  if (!list || !list.length)
    return `<div class="empty-rel">none recorded</div>`;
  return list.map(r => `
    <div class="rel-item">
      <span class="arrow">${{arrow}}</span>
      <span class="rname">${{r.name}}</span>
      ${{r.birth ? `<span class="ryr">b.${{r.birth}}</span>` : ''}}
    </div>`).join('');
}}

function renderSidebar() {{
  const decisions = loadDecisions();
  const list = document.getElementById('node-list');
  list.innerHTML = '';
  GROUPS.forEach((g, i) => {{
    const key = groupKey(g);
    const dec = decisions[key];
    const div = document.createElement('div');
    const cls = dec === 'distinct' ? 'distinct' : dec ? 'resolved' : '';
    div.className = `node-item ${{i===currentIdx?'active':''}} ${{cls}}`;
    const sub = `${{g.nodes.length}} nodes · ${{g.reason}}`;
    div.innerHTML = `
      <span class="count-badge">${{g.nodes.length}}×</span>
      <span class="nm">
        ${{g.name}}
        <div class="sub">${{sub}}</div>
      </span>
      <span class="status-dot"></span>`;
    div.onclick = () => {{ currentIdx = i; render(); }};
    list.appendChild(div);
  }});
}}

function updateProgress() {{
  const decisions = loadDecisions();
  const done = GROUPS.filter(g => decisions[groupKey(g)]).length;
  document.getElementById('progress-text').textContent = `${{done}} of ${{GROUPS.length}} reviewed`;
  document.getElementById('progress-fill').style.width = (done/GROUPS.length*100)+'%';
}}

function render() {{
  if (currentIdx === null) return;
  const g = GROUPS[currentIdx];
  const key = groupKey(g);
  const decisions = loadDecisions();
  const dec = decisions[key];

  document.getElementById('empty-state').style.display = 'none';
  const detail = document.getElementById('detail');
  detail.style.display = 'block';

  const n = g.nodes.length;
  const gridClass = n === 2 ? 'two' : 'three';

  const cards = g.nodes.map(node => {{
    const srcClass = node.source === 'geni' ? 'geni' : 'geneanet';
    const srcLabel = node.source === 'geni' ? 'Geni.com' : 'Geneanet';
    const meta = fmtNode(node);
    return `
      <div class="node-card ${{srcClass}}">
        <div class="nc-header">
          <span>${{srcLabel}}</span>
          <span class="nc-id">id=${{node.id}} · gen ${{node.gen}}</span>
        </div>
        <div class="nc-body">
          <div class="nc-name">${{node.name}}</div>
          <div class="nc-meta">
            ${{meta ? `<span>${{meta}}</span>` : '<span style="color:var(--or-dim)">No dates or location</span>'}}
          </div>
          <div class="nc-section">
            <div class="nc-section-label">Parents</div>
            <div class="rel-list">${{relHtml(node.parents, '↑')}}</div>
          </div>
          <div class="nc-section" style="margin-top:10px">
            <div class="nc-section-label">Children</div>
            <div class="rel-list">${{relHtml(node.children, '↓')}}</div>
          </div>
        </div>
      </div>`;
  }}).join('');

  // ── Merged result preview ──────────────────────────────────────────────
  // Union of parents and children across all nodes in group, deduped by id.
  // Items that appear in ALL nodes are "shared"; items from only some are "added".
  function mergeRelations(field) {{
    const all = g.nodes.flatMap(node => node[field]);
    const byId = {{}};
    for (const r of all) {{
      if (!byId[r.id]) byId[r.id] = {{ ...r, count: 0 }};
      byId[r.id].count++;
    }}
    return Object.values(byId).sort((a, b) => b.count - a.count);
  }}
  const mergedParents  = mergeRelations('parents');
  const mergedChildren = mergeRelations('children');

  function mpItemHtml(r, arrow) {{
    const shared = r.count === n;
    const tag = shared ? '' : `<span class="tag">+added</span>`;
    return `<div class="mp-item">
      <span class="arrow">${{arrow}}</span>
      <span class="rname">${{r.name}}</span>
      ${{r.birth ? `<span style="font-size:10px;color:var(--pdim)">b.${{r.birth}}</span>` : ''}}
      ${{tag}}
    </div>`;
  }}

  const mpParentsHtml = mergedParents.length
    ? mergedParents.map(r => mpItemHtml(r, '↑')).join('')
    : `<div class="mp-empty">none</div>`;
  const mpChildrenHtml = mergedChildren.length
    ? mergedChildren.map(r => mpItemHtml(r, '↓')).join('')
    : `<div class="mp-empty">none</div>`;

  const previewHtml = `
    <div class="merge-preview">
      <div class="merge-preview-header">
        <span>After merge — single node would have:</span>
        <span class="mp-ids">${{mergedParents.length}} parent${{mergedParents.length!==1?'s':''}} · ${{mergedChildren.length}} child${{mergedChildren.length!==1?'ren':''}}</span>
      </div>
      <div class="merge-preview-body">
        <div>
          <div class="mp-section-label">Parents</div>
          <div class="rel-list">${{mpParentsHtml}}</div>
        </div>
        <div>
          <div class="mp-section-label">Children</div>
          <div class="rel-list">${{mpChildrenHtml}}</div>
        </div>
      </div>
    </div>`;

  // Decision labels based on number of nodes
  const keepFirstLabel = n === 2
    ? `Merge → keep id=${{g.nodes[0].id}} (lower)`
    : `Merge → keep id=${{g.nodes[0].id}} (first)`;
  const keepLastLabel = n === 2
    ? `Merge → keep id=${{g.nodes[n-1].id}} (higher)`
    : `Merge → keep id=${{g.nodes[n-1].id}} (last)`;

  const decBanner = {{
    'merge-first': `✓ Merge: keep id=${{g.nodes[0].id}} "${{g.nodes[0].name}}", redirect all edges from the other${{n>2?' nodes':' node'}}`,
    'merge-last':  `✓ Merge: keep id=${{g.nodes[n-1].id}} "${{g.nodes[n-1].name}}", redirect all edges from the other${{n>2?' nodes':' node'}}`,
    'distinct':    '✗ Keep separate — confirmed different people',
    'flag':        '⚑ Flagged for further research',
  }}[dec] || '';
  const decClass = dec || '';

  detail.innerHTML = `
    <div class="nav-row">
      <button id="prev-btn" ${{currentIdx===0?'disabled':''}}>← Prev</button>
      <span class="pos">Group ${{currentIdx+1}} of ${{GROUPS.length}}</span>
      <button id="next-btn" ${{currentIdx===GROUPS.length-1?'disabled':''}}>Next →</button>
    </div>

    <div class="group-header">
      <div class="eyebrow">Possible Duplicate · ${{n}} nodes</div>
      <h2>${{g.name}}</h2>
      <span class="reason-tag">${{g.reason}}</span>
    </div>

    ${{decBanner ? `<div class="current-decision show ${{decClass}}">${{decBanner}}</div>` : ''}}

    <div class="node-cards ${{gridClass}}">${{cards}}</div>

    ${{previewHtml}}

    <div class="decision-bar">
      <div class="label">Decision</div>
      <button class="dec-btn btn-merge-first ${{dec==='merge-first'?'selected':''}}"
        onclick="decide('${{key}}','merge-first')">${{keepFirstLabel}}</button>
      <button class="dec-btn btn-merge-last ${{dec==='merge-last'?'selected':''}}"
        onclick="decide('${{key}}','merge-last')">${{keepLastLabel}}</button>
      <button class="dec-btn btn-distinct ${{dec==='distinct'?'selected':''}}"
        onclick="decide('${{key}}','distinct')">Different people</button>
      <button class="dec-btn btn-flag ${{dec==='flag'?'selected':''}}"
        onclick="decide('${{key}}','flag')">Flag for research</button>
      ${{dec ? `<button class="dec-btn btn-clear" onclick="decide('${{key}}',null)">Clear</button>` : ''}}
    </div>`;

  document.getElementById('prev-btn').onclick = () => {{
    if (currentIdx > 0) {{ currentIdx--; render(); renderSidebar(); }}
  }};
  document.getElementById('next-btn').onclick = () => {{
    if (currentIdx < GROUPS.length-1) {{ currentIdx++; render(); renderSidebar(); }}
  }};

  renderSidebar();
}}

function decide(key, decision) {{
  saveDecision(key, decision);
  render();
}}

document.getElementById('export-btn').onclick = () => {{
  const decisions = loadDecisions();
  const out = GROUPS.map(g => {{
    const key = groupKey(g);
    return {{
      name:      g.name,
      reason:    g.reason,
      node_ids:  g.nodes.map(n => n.id),
      decision:  decisions[key] || null,
    }};
  }});
  const blob = new Blob([JSON.stringify(out, null, 2)], {{type:'application/json'}});
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = 'merge-decisions.json';
  a.click();
}};

document.addEventListener('keydown', e => {{
  if (e.target.tagName === 'INPUT') return;
  if      (e.key === 'ArrowRight' || e.key === 'ArrowDown')  {{
    if (currentIdx === null) currentIdx = 0;
    else if (currentIdx < GROUPS.length-1) currentIdx++;
    render(); renderSidebar();
  }} else if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') {{
    if (currentIdx !== null && currentIdx > 0) currentIdx--;
    render(); renderSidebar();
  }} else if (e.key === '1') {{
    if (currentIdx !== null) decide(groupKey(GROUPS[currentIdx]), 'merge-first');
  }} else if (e.key === '2') {{
    if (currentIdx !== null) decide(groupKey(GROUPS[currentIdx]), 'merge-last');
  }} else if (e.key === 'd') {{
    if (currentIdx !== null) decide(groupKey(GROUPS[currentIdx]), 'distinct');
  }} else if (e.key === 'f') {{
    if (currentIdx !== null) decide(groupKey(GROUPS[currentIdx]), 'flag');
  }}
}});

renderSidebar();
updateProgress();
</script>
</body>
</html>'''


def main():
    print(f'Loading {LINEAGE_HTML} …')
    id_map, parents_of, children_of = load_graph(LINEAGE_HTML)
    groups = find_duplicates(id_map, parents_of, children_of)
    print(f'Found {len(groups)} proposed merge groups')

    html = generate_html(groups)
    os.makedirs(os.path.dirname(OUT_HTML), exist_ok=True)
    with open(OUT_HTML, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f'Written: {OUT_HTML}')
    print(f'Open with: open {OUT_HTML}')
    print()
    print('Keyboard shortcuts:')
    print('  ← / →   navigate groups')
    print('  1        merge, keep first (lower id)')
    print('  2        merge, keep last (higher id)')
    print('  d        different people — keep both')
    print('  f        flag for research')


if __name__ == '__main__':
    main()
