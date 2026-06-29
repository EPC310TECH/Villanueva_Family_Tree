#!/usr/bin/env python3
"""
generate_conflict_report.py
============================
Generates private/source-conflicts.html — a local-only interactive
investigation page for the 19 ancestor nodes that still have >2 parents
after fix_graph_data.py removed bad-direction edges.

Decisions are saved to localStorage and can be exported as a JSON file
that apply_conflict_resolutions.py uses to patch the HTML lineage files.

Usage:
    cd ancestor_mappings
    python3 generate_conflict_report.py
    open ../private/source-conflicts.html
"""
import json, os, re, sys

LINEAGE_HTML = os.path.join(os.path.dirname(__file__), 'antonio-jasso-lineage.html')
OUT_HTML     = os.path.join(os.path.dirname(__file__), '..', 'private', 'source-conflicts.html')

# IDs below this threshold are from the original Geni.com export;
# IDs at or above are from the Geneanet import (import_ged_full.py).
GENI_THRESHOLD = 3385


def load_graph(path):
    with open(path, encoding='utf-8') as f:
        raw = f.read()
    m = re.search(r'const GRAPH\s*=\s*(\{\"nodes\".*?\});', raw, re.DOTALL)
    if not m:
        sys.exit(f'No GRAPH in {path}')
    g = json.loads(m.group(1))
    id_map = {n['id']: n for n in g['nodes']}
    parents_of  = {}
    children_of = {}
    for e in g['edges']:
        parents_of.setdefault(e['t'], []).append(e['s'])
        children_of.setdefault(e['s'], []).append(e['t'])
    return id_map, parents_of, children_of


def node_summary(n):
    if not n:
        return {}
    return {
        'id':      n['id'],
        'name':    n.get('name', ''),
        'gen':     n.get('gen', ''),
        'birth':   n.get('birth'),
        'death':   n.get('death'),
        'country': n.get('country', ''),
        'region':  n.get('region', ''),
        'source':  'geni' if n['id'] < GENI_THRESHOLD else 'geneanet',
    }


def build_conflict_data(id_map, parents_of, children_of):
    conflicts = []
    for nid, ps in parents_of.items():
        if len(ps) <= 2:
            continue
        node = id_map.get(nid, {})

        # Gather parent details including each parent's own parents
        parent_details = []
        for pid in ps:
            p = id_map.get(pid, {})
            gps = [node_summary(id_map.get(gp)) for gp in parents_of.get(pid, [])]
            parent_details.append({
                **node_summary(p),
                'grandparents': gps,
            })

        # Children (downstream connections)
        kids = [node_summary(id_map.get(c)) for c in children_of.get(nid, [])]

        # Group parents by source
        geni_ids = [p for p in ps if p < GENI_THRESHOLD]
        gnet_ids = [p for p in ps if p >= GENI_THRESHOLD]

        # If all parents are from same source, split by index pairs
        if not gnet_ids:
            label_a, label_b = 'Geni.com (path 1)', 'Geni.com (path 2)'
            group_a = geni_ids[:len(geni_ids)//2]
            group_b = geni_ids[len(geni_ids)//2:]
        elif not geni_ids:
            label_a, label_b = 'Geneanet (path 1)', 'Geneanet (path 2)'
            group_a = gnet_ids[:len(gnet_ids)//2]
            group_b = gnet_ids[len(gnet_ids)//2:]
        else:
            label_a, label_b = 'Geni.com', 'Geneanet'
            group_a = geni_ids
            group_b = gnet_ids

        conflicts.append({
            'node':      node_summary(node),
            'parents':   parent_details,
            'group_a':   group_a,
            'group_b':   group_b,
            'label_a':   label_a,
            'label_b':   label_b,
            'children':  kids,
        })

    conflicts.sort(key=lambda x: x['node'].get('gen', 99))
    return conflicts


def generate_html(conflicts):
    data_json = json.dumps(conflicts, ensure_ascii=False)
    count = len(conflicts)

    return f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Source Conflicts — Antonio Jasso Lineage ({count} nodes)</title>
<style>
:root {{
  --bg:#1a1610;--surface:#231f18;--card:#2b2620;--card2:#332d25;
  --or:#c8a84b;--or-dim:#8a7030;--parchment:#e9dec3;--pdim:#a89b7a;
  --blue:#4a90d9;--blue-dim:#2c5580;--gold-dim:#554830;
  --geni-bg:rgba(41,128,185,.12);--geni-border:rgba(41,128,185,.35);
  --gnet-bg:rgba(200,168,75,.10);--gnet-border:rgba(200,168,75,.35);
  --line:rgba(200,168,75,.12);--hair:rgba(200,168,75,.22);
  --green:#27ae60;--red:#c0392b;--purple:#8e44ad;
}}
*{{box-sizing:border-box;margin:0;padding:0}}
body{{background:var(--bg);color:var(--parchment);
  font-family:ui-sans-serif,system-ui,sans-serif;font-size:13px;
  display:flex;height:100vh;overflow:hidden}}

/* Sidebar */
#sidebar{{width:260px;flex:none;border-right:1px solid var(--hair);
  overflow-y:auto;background:var(--surface);display:flex;flex-direction:column}}
#sidebar-header{{padding:14px 16px;border-bottom:1px solid var(--hair);flex:none}}
#sidebar-header h1{{font-size:14px;font-weight:700;color:var(--or);letter-spacing:.05em}}
#sidebar-header p{{font-size:11px;color:var(--pdim);margin-top:4px;line-height:1.4}}
#progress-bar-wrap{{padding:10px 16px 0;flex:none}}
#progress-text{{font-size:11px;color:var(--pdim);margin-bottom:5px}}
#progress-bar{{height:4px;background:var(--gold-dim);border-radius:2px;overflow:hidden}}
#progress-fill{{height:100%;background:var(--green);border-radius:2px;transition:width .3s}}
#node-list{{flex:1;overflow-y:auto;padding:8px 0}}
.node-item{{padding:10px 16px;cursor:pointer;border-bottom:1px solid var(--line);
  transition:background .12s;display:flex;align-items:center;gap:8px}}
.node-item:hover{{background:rgba(200,168,75,.06)}}
.node-item.active{{background:rgba(200,168,75,.12);border-left:2px solid var(--or)}}
.node-item .gen-badge{{
  font-size:10px;font-weight:700;color:var(--or-dim);
  background:rgba(200,168,75,.1);border-radius:3px;
  padding:2px 5px;flex:none;letter-spacing:.05em}}
.node-item .nm{{font-size:12px;color:var(--parchment);line-height:1.3;flex:1;min-width:0}}
.node-item .nm .yr{{font-size:10px;color:var(--pdim)}}
.node-item .status-dot{{
  width:8px;height:8px;border-radius:50%;flex:none;
  background:var(--or-dim)}}
.node-item.resolved .status-dot{{background:var(--green)}}
.node-item.flagged .status-dot{{background:var(--purple)}}
#export-btn{{
  margin:12px 16px;padding:9px 14px;
  background:rgba(200,168,75,.1);border:1px solid var(--hair);
  color:var(--or);border-radius:4px;cursor:pointer;
  font-size:11px;font-weight:600;letter-spacing:.08em;text-transform:uppercase;
  flex:none;transition:background .15s}}
#export-btn:hover{{background:rgba(200,168,75,.2)}}

/* Main panel */
#main{{flex:1;overflow-y:auto;padding:28px 32px}}
#empty-state{{
  display:flex;flex-direction:column;align-items:center;justify-content:center;
  height:100%;color:var(--pdim);text-align:center;gap:12px}}
#empty-state .icon{{font-size:40px;opacity:.4}}
#detail{{display:none}}

/* Node header */
.node-header{{margin-bottom:24px}}
.node-header .eyebrow{{
  font-size:10px;font-weight:700;letter-spacing:.22em;text-transform:uppercase;
  color:var(--or-dim);margin-bottom:8px}}
.node-header h2{{font-size:22px;font-weight:700;color:var(--or);margin-bottom:6px}}
.node-header .meta{{font-size:12px;color:var(--pdim);display:flex;gap:16px;flex-wrap:wrap}}
.node-header .meta span{{display:flex;align-items:center;gap:4px}}

/* Children strip */
.children-strip{{
  display:flex;flex-wrap:wrap;gap:6px;margin-bottom:20px;padding:10px 14px;
  background:rgba(200,168,75,.04);border:1px solid var(--line);border-radius:6px}}
.children-strip .label{{
  font-size:10px;font-weight:700;letter-spacing:.15em;text-transform:uppercase;
  color:var(--or-dim);margin-right:4px;align-self:center}}
.child-pill{{
  font-size:11px;padding:3px 8px;border-radius:3px;
  background:var(--card);border:1px solid var(--line);color:var(--pdim)}}

/* Parent groups */
.groups{{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:24px}}
@media(max-width:900px){{.groups{{grid-template-columns:1fr}}}}
.group{{border-radius:8px;overflow:hidden;border:1px solid}}
.group.geni{{background:var(--geni-bg);border-color:var(--geni-border)}}
.group.gnet{{background:var(--gnet-bg);border-color:var(--gnet-border)}}
.group-header{{
  padding:10px 14px;font-size:10px;font-weight:700;
  letter-spacing:.18em;text-transform:uppercase;
  border-bottom:1px solid rgba(255,255,255,.05)}}
.group.geni .group-header{{color:var(--blue);background:var(--blue-dim)}}
.group.gnet .group-header{{color:var(--or);background:var(--gold-dim)}}
.parent-cards{{padding:12px;display:flex;flex-direction:column;gap:8px}}
.parent-card{{
  background:var(--card2);border-radius:6px;padding:10px 12px}}
.parent-card .p-name{{font-size:13px;font-weight:600;color:var(--parchment);margin-bottom:3px}}
.parent-card .p-meta{{font-size:11px;color:var(--pdim);margin-bottom:6px}}
.grandparents{{
  font-size:11px;color:var(--pdim);
  border-top:1px solid var(--line);margin-top:6px;padding-top:6px;
  display:flex;flex-direction:column;gap:2px}}
.gp-row{{display:flex;align-items:center;gap:6px}}
.gp-row::before{{content:"↑";color:var(--or-dim);flex:none}}

/* Decision buttons */
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
.dec-btn.btn-a{{background:var(--blue-dim);border-color:var(--blue);color:var(--blue)}}
.dec-btn.btn-b{{background:var(--gold-dim);border-color:var(--or);color:var(--or)}}
.dec-btn.btn-both{{background:rgba(39,174,96,.15);border-color:var(--green);color:var(--green)}}
.dec-btn.btn-flag{{background:rgba(142,68,173,.15);border-color:var(--purple);color:var(--purple)}}
.dec-btn.btn-clear{{background:rgba(192,57,43,.12);border-color:var(--red);color:var(--red)}}
.dec-btn.selected{{opacity:1;box-shadow:0 0 0 2px currentColor}}

/* Current decision banner */
.current-decision{{
  display:none;padding:10px 14px;border-radius:6px;font-size:12px;
  font-weight:600;margin-bottom:16px;letter-spacing:.05em}}
.current-decision.show{{display:block}}
.current-decision.keep-a{{background:var(--blue-dim);color:var(--blue);border:1px solid var(--geni-border)}}
.current-decision.keep-b{{background:var(--gold-dim);color:var(--or);border:1px solid var(--gnet-border)}}
.current-decision.keep-both{{background:rgba(39,174,96,.15);color:var(--green);border:1px solid var(--green)}}
.current-decision.flagged{{background:rgba(142,68,173,.15);color:var(--purple);border:1px solid var(--purple)}}

/* Nav arrows */
.nav-row{{display:flex;justify-content:space-between;align-items:center;
  margin-bottom:20px;padding-bottom:14px;border-bottom:1px solid var(--line)}}
.nav-row button{{
  background:transparent;border:1px solid var(--hair);color:var(--pdim);
  padding:6px 14px;border-radius:4px;cursor:pointer;font-size:11px;
  letter-spacing:.1em;text-transform:uppercase;transition:border-color .15s,color .15s}}
.nav-row button:hover{{border-color:var(--or);color:var(--or)}}
.nav-row button:disabled{{opacity:.3;cursor:default}}
.nav-row .pos{{font-size:12px;color:var(--pdim)}}
</style>
</head>
<body>

<div id="sidebar">
  <div id="sidebar-header">
    <h1>Source Conflicts</h1>
    <p>Ancestors with &gt;2 parents from conflicting genealogy sources. Click to investigate.</p>
  </div>
  <div id="progress-bar-wrap">
    <div id="progress-text">0 of {count} resolved</div>
    <div id="progress-bar"><div id="progress-fill" style="width:0%"></div></div>
  </div>
  <div id="node-list"></div>
  <button id="export-btn">Export Decisions ↓</button>
</div>

<div id="main">
  <div id="empty-state">
    <div class="icon">⚖️</div>
    <div style="font-size:15px;font-weight:600;color:var(--parchment)">Select a node to investigate</div>
    <div style="font-size:12px;max-width:300px">Each node has parents assigned by two different sources. Decide which set is correct — or mark it for further research.</div>
  </div>
  <div id="detail"></div>
</div>

<script>
const CONFLICTS = {data_json};
const STORAGE_KEY = 'conflict_decisions_v1';

function loadDecisions() {{
  try {{ return JSON.parse(localStorage.getItem(STORAGE_KEY) || '{{}}'); }}
  catch(e) {{ return {{}}; }}
}}
function saveDecision(id, decision) {{
  const d = loadDecisions();
  d[id] = decision;
  localStorage.setItem(STORAGE_KEY, JSON.stringify(d));
  updateProgress();
  renderSidebar();
}}

let currentIdx = null;

function fmt(n) {{
  if (!n) return '';
  const yr = n.birth ? ` b.${{n.birth}}` : '';
  const loc = [n.region, n.country].filter(Boolean).join(', ');
  return (n.name || '?') + yr + (loc ? ` · ${{loc}}` : '');
}}

function sourceClass(id) {{
  return id < {GENI_THRESHOLD} ? 'geni' : 'gnet';
}}

function renderSidebar() {{
  const decisions = loadDecisions();
  const list = document.getElementById('node-list');
  list.innerHTML = '';
  CONFLICTS.forEach((c, i) => {{
    const nid = c.node.id;
    const dec = decisions[nid];
    const div = document.createElement('div');
    div.className = 'node-item' + (i===currentIdx?' active':'') +
      (dec && dec!=='flag' ? ' resolved' : dec==='flag' ? ' flagged' : '');
    const yr = c.node.birth ? ` b.${{c.node.birth}}` : '';
    div.innerHTML = `
      <span class="gen-badge">G${{c.node.gen}}</span>
      <span class="nm">
        ${{c.node.name || '?'}}
        <span class="yr">${{yr}}</span>
      </span>
      <span class="status-dot"></span>`;
    div.onclick = () => {{ currentIdx = i; render(); }};
    list.appendChild(div);
  }});
}}

function updateProgress() {{
  const decisions = loadDecisions();
  const done = CONFLICTS.filter(c => decisions[c.node.id]).length;
  document.getElementById('progress-text').textContent = `${{done}} of ${{CONFLICTS.length}} resolved`;
  document.getElementById('progress-fill').style.width = (done/CONFLICTS.length*100)+'%';
}}

function render() {{
  if (currentIdx === null) return;
  const c = CONFLICTS[currentIdx];
  const decisions = loadDecisions();
  const dec = decisions[c.node.id];

  document.getElementById('empty-state').style.display = 'none';
  const detail = document.getElementById('detail');
  detail.style.display = 'block';

  const metaParts = [
    c.node.birth ? `b. ${{c.node.birth}}` : '',
    c.node.death ? `d. ${{c.node.death}}` : '',
    c.node.region || '',
    c.node.country || '',
  ].filter(Boolean);

  // Build parent groups
  const groupIds = [c.group_a, c.group_b];
  const groupLabels = [c.label_a, c.label_b];
  const groupClasses = [
    c.label_a.toLowerCase().includes('geni') ? 'geni' : 'gnet',
    c.label_b.toLowerCase().includes('geneanet') ? 'gnet' : 'geni',
  ];

  function parentCardHtml(pid) {{
    const p = c.parents.find(p => p.id === pid);
    if (!p) return '';
    const meta = [
      p.birth ? `b.${{p.birth}}` : '',
      p.death ? `d.${{p.death}}` : '',
      p.region || '', p.country || '',
    ].filter(Boolean).join(' · ');
    const gps = (p.grandparents||[]).map(gp =>
      `<div class="gp-row">${{gp.name||'?'}}${{gp.birth?' b.'+gp.birth:''}}</div>`
    ).join('');
    return `<div class="parent-card">
      <div class="p-name">${{p.name||'?'}}</div>
      <div class="p-meta">id=${{p.id}} · gen ${{p.gen}}${{meta?' · '+meta:''}}</div>
      ${{gps ? `<div class="grandparents">${{gps}}</div>` : ''}}
    </div>`;
  }}

  function groupHtml(ids, label, cls) {{
    const cards = ids.map(parentCardHtml).join('');
    return `<div class="group ${{cls}}">
      <div class="group-header">${{label}}</div>
      <div class="parent-cards">${{cards}}</div>
    </div>`;
  }}

  const children = (c.children||[]).map(ch =>
    `<span class="child-pill">${{ch.name||'?'}} (gen ${{ch.gen}})</span>`
  ).join('');

  // Decision banner
  const decLabel = {{
    'keep-a': `✓ Keeping ${{c.label_a}} parents`,
    'keep-b': `✓ Keeping ${{c.label_b}} parents`,
    'keep-both': '✓ Keeping both parent sets (genuine pedigree collapse)',
    'flag': '⚑ Flagged for further research',
  }}[dec] || '';
  const decClass = dec || '';

  detail.innerHTML = `
    <div class="nav-row">
      <button id="prev-btn" ${{currentIdx===0?'disabled':''}}>← Prev</button>
      <span class="pos">Node ${{currentIdx+1}} of ${{CONFLICTS.length}} · id=${{c.node.id}}</span>
      <button id="next-btn" ${{currentIdx===CONFLICTS.length-1?'disabled':''}}>Next →</button>
    </div>

    <div class="node-header">
      <div class="eyebrow">Generation ${{c.node.gen}} · Source Conflict</div>
      <h2>${{c.node.name || '?'}}</h2>
      <div class="meta">
        ${{metaParts.map(s=>`<span>${{s}}</span>`).join('')}}
        <span>id=${{c.node.id}}</span>
      </div>
    </div>

    ${{children ? `<div class="children-strip">
      <span class="label">Child in tree:</span>${{children}}
    </div>` : ''}}

    ${{decLabel ? `<div class="current-decision show ${{decClass}}">${{decLabel}}</div>` : ''}}

    <div class="groups">
      ${{groupHtml(groupIds[0], groupLabels[0], groupClasses[0])}}
      ${{groupHtml(groupIds[1], groupLabels[1], groupClasses[1])}}
    </div>

    <div class="decision-bar">
      <div class="label">Resolution</div>
      <button class="dec-btn btn-a ${{dec==='keep-a'?'selected':''}}"
        onclick="decide(${{c.node.id}},'keep-a')">Keep ${{c.label_a}}</button>
      <button class="dec-btn btn-b ${{dec==='keep-b'?'selected':''}}"
        onclick="decide(${{c.node.id}},'keep-b')">Keep ${{c.label_b}}</button>
      <button class="dec-btn btn-both ${{dec==='keep-both'?'selected':''}}"
        onclick="decide(${{c.node.id}},'keep-both')">Both (collapse)</button>
      <button class="dec-btn btn-flag ${{dec==='flag'?'selected':''}}"
        onclick="decide(${{c.node.id}},'flag')">Flag for research</button>
      ${{dec ? `<button class="dec-btn btn-clear"
        onclick="decide(${{c.node.id}},null)">Clear</button>` : ''}}
    </div>`;

  document.getElementById('prev-btn').onclick = () => {{
    if (currentIdx > 0) {{ currentIdx--; render(); renderSidebar(); }}
  }};
  document.getElementById('next-btn').onclick = () => {{
    if (currentIdx < CONFLICTS.length-1) {{ currentIdx++; render(); renderSidebar(); }}
  }};

  renderSidebar();
}}

function decide(nodeId, decision) {{
  if (decision === null) {{
    const d = loadDecisions();
    delete d[nodeId];
    localStorage.setItem(STORAGE_KEY, JSON.stringify(d));
  }} else {{
    saveDecision(nodeId, decision);
  }}
  render();
}}

document.getElementById('export-btn').onclick = () => {{
  const decisions = loadDecisions();
  const out = CONFLICTS.map(c => ({{
    id: c.node.id,
    name: c.node.name,
    gen: c.node.gen,
    label_a: c.label_a,
    label_b: c.label_b,
    group_a: c.group_a,
    group_b: c.group_b,
    decision: decisions[c.node.id] || null,
  }}));
  const blob = new Blob([JSON.stringify(out, null, 2)], {{type:'application/json'}});
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = 'conflict-resolutions.json';
  a.click();
}};

// Keyboard navigation
document.addEventListener('keydown', e => {{
  if (e.key === 'ArrowRight' || e.key === 'ArrowDown') {{
    if (currentIdx === null) currentIdx = 0;
    else if (currentIdx < CONFLICTS.length-1) currentIdx++;
    render(); renderSidebar();
  }} else if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') {{
    if (currentIdx !== null && currentIdx > 0) currentIdx--;
    render(); renderSidebar();
  }} else if (e.key === '1') {{
    if (currentIdx!==null) decide(CONFLICTS[currentIdx].node.id,'keep-a');
  }} else if (e.key === '2') {{
    if (currentIdx!==null) decide(CONFLICTS[currentIdx].node.id,'keep-b');
  }} else if (e.key === '3') {{
    if (currentIdx!==null) decide(CONFLICTS[currentIdx].node.id,'keep-both');
  }} else if (e.key === 'f') {{
    if (currentIdx!==null) decide(CONFLICTS[currentIdx].node.id,'flag');
  }}
}});

// Init
renderSidebar();
updateProgress();
</script>
</body>
</html>'''


def main():
    print(f'Loading {LINEAGE_HTML} …')
    id_map, parents_of, children_of = load_graph(LINEAGE_HTML)
    conflicts = build_conflict_data(id_map, parents_of, children_of)
    print(f'Found {len(conflicts)} source-conflict nodes')

    html = generate_html(conflicts)

    os.makedirs(os.path.dirname(OUT_HTML), exist_ok=True)
    with open(OUT_HTML, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f'Written: {OUT_HTML}')
    print(f'Open with: open {OUT_HTML}')
    print()
    print('Keyboard shortcuts in the browser:')
    print('  ← / → (or ↑/↓)  navigate nodes')
    print('  1  keep source A  |  2  keep source B  |  3  keep both  |  f  flag')
    print('  Export Decisions button → conflict-resolutions.json')


if __name__ == '__main__':
    main()
