#!/usr/bin/env python3
"""
fetch_house_shields.py
======================
Searches wappenwiki.org and Wikimedia Commons for heraldic shield images
for each noble/royal house in the family tree.

Produces: house_shields.json  {slug: {url, caption, source, filename}}

Run from ancestor_mappings/:
    python3 fetch_house_shields.py
"""

import json, os, re, time, unicodedata, urllib.request, urllib.parse, sys

HERE    = os.path.dirname(os.path.abspath(__file__))
TREE    = os.path.join(HERE, "antonio-jasso-lineage.html")
OUT_JSON = os.path.join(HERE, "house_shields.json")

DELAY   = 0.45   # seconds between API calls — be polite

HEADERS = {"User-Agent": "VillanuevaFamilyTree/1.0 (genealogy research; contact: ajassovlsf@gmail.com)"}

# ── wappenwiki.org: specialised heraldry wiki ─────────────────────────────────
WAPPEN_SEARCH = "https://wappenwiki.org/api.php"
# ── Wikimedia Commons ─────────────────────────────────────────────────────────
COMMONS_SEARCH = "https://commons.wikimedia.org/w/api.php"
COMMONS_INFO   = "https://commons.wikimedia.org/w/api.php"

# ── helpers ───────────────────────────────────────────────────────────────────

def slugify(s):
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")

def api_get(base, params, label=""):
    url = base + "?" + urllib.parse.urlencode(params)
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=12) as r:
            return json.loads(r.read())
    except Exception as e:
        print(f"    ⚠ {label}: {e}")
        return {}

def search_wiki(base, query, limit=8):
    data = api_get(base, {
        "action":"query","list":"search",
        "srsearch": query, "srnamespace":"6",
        "srlimit": str(limit), "format":"json"
    }, f"search({query[:30]})")
    return data.get("query",{}).get("search",[])

def get_file_url(base, filename):
    data = api_get(base, {
        "action":"query","titles":f"File:{filename}",
        "prop":"imageinfo","iiprop":"url","format":"json"
    }, f"info({filename[:40]})")
    pages = data.get("query",{}).get("pages",{})
    for p in pages.values():
        ii = p.get("imageinfo",[])
        if ii:
            return ii[0].get("url","")
    return ""

def score(title, house_name, house_slug):
    t   = title.lower()
    s   = 0
    # heraldic keywords
    for kw in ("blason","escudo","wappen","coat_of_arms","coat of arms",
               "armas","arms","shield","stemma","blason"):
        if kw in t: s += 2
    # house name words (ignore short words)
    for word in re.split(r"\W+", house_name.lower()):
        if len(word) > 2 and word in t: s += 4
    if house_slug.replace("-"," ") in t: s += 6
    if house_slug in t.replace(" ","_"): s += 6
    # format
    if t.endswith(".svg"): s += 3
    elif t.endswith(".png"): s += 1
    # penalise overly generic names
    for bad in ("_es.svg","_pt.svg","espana","portugal","castilla_generic"):
        if bad in t: s -= 3
    return s

# ── alternate search terms per house ─────────────────────────────────────────

def queries_for(house_name, house_slug):
    """Return list of search strings to try, best first."""
    slug_sp = house_slug.replace("-"," ")
    name    = house_name
    q = [
        f"escudo casa {slug_sp}",
        f"blason maison {slug_sp}",
        f"coat of arms house {slug_sp}",
        f"wappen {slug_sp}",
        f"armas {slug_sp}",
        f"escudo {slug_sp}",
        f"coat of arms {name}",
        name,
    ]
    return q

# ── load graph and get house list ─────────────────────────────────────────────

with open(TREE, encoding="utf-8") as f:
    raw = f.read()

m = re.search(r'const GRAPH\s*=\s*(\{.*?\});', raw, re.DOTALL)
graph   = json.loads(m.group(1))
nodes   = graph["nodes"]

from collections import defaultdict
house_nodes = defaultdict(list)
for n in nodes:
    h = n.get("house","").strip()
    if h: house_nodes[h].append(n)

houses = {h:ns for h,ns in house_nodes.items() if len(ns)>=3}
# sort by member count descending — biggest/most important first
sorted_houses = sorted(houses.items(), key=lambda x: -len(x[1]))

# ── load existing cache ────────────────────────────────────────────────────────

if os.path.exists(OUT_JSON):
    with open(OUT_JSON) as f:
        cache = json.load(f)
    print(f"Loaded cache: {len(cache)} entries already found")
else:
    cache = {}

def save():
    with open(OUT_JSON,"w") as f:
        json.dump(cache, f, indent=2, ensure_ascii=False)

# ── main search loop ───────────────────────────────────────────────────────────

total   = len(sorted_houses)
found   = 0
skipped = 0

print(f"\nSearching shields for {total} houses …\n")

for i, (house_name, members) in enumerate(sorted_houses):
    slug = slugify(house_name)
    sys.stdout.flush()

    if slug in cache:
        found += 1
        skipped += 1
        print(f"[{i+1}/{total}] {slug}  ← cached ✓")
        continue

    print(f"[{i+1}/{total}] {house_name}  ({len(members)} members)")

    best_url  = ""
    best_file = ""
    best_src  = ""
    best_cap  = ""
    best_scr  = -1

    # Try wappenwiki.org first (heraldry-specific)
    for q in queries_for(house_name, slug)[:4]:
        results = search_wiki(WAPPEN_SEARCH, q)
        time.sleep(DELAY)
        for r in results:
            title = r.get("title","")
            # strip "File:" prefix
            fname = title.replace("File:","").replace("Datei:","")
            ext   = fname.rsplit(".",1)[-1].lower() if "." in fname else ""
            if ext not in ("svg","png","jpg","jpeg"): continue
            sc = score(fname, house_name, slug)
            if sc > best_scr:
                url = get_file_url(WAPPEN_SEARCH, fname)
                time.sleep(DELAY)
                if url:
                    best_scr  = sc
                    best_url  = url
                    best_file = fname
                    best_src  = "wappenwiki"
                    best_cap  = f"Arms of the House of {house_name} — wappenwiki.org"
        if best_scr >= 8:
            break   # good enough, don't over-query

    # Try Wikimedia Commons if wappenwiki gave nothing/poor result
    if best_scr < 6:
        for q in queries_for(house_name, slug)[:5]:
            results = search_wiki(COMMONS_SEARCH, q)
            time.sleep(DELAY)
            for r in results:
                title = r.get("title","")
                fname = title.replace("File:","")
                ext   = fname.rsplit(".",1)[-1].lower() if "." in fname else ""
                if ext not in ("svg","png","jpg","jpeg"): continue
                sc = score(fname, house_name, slug)
                if sc > best_scr:
                    url = get_file_url(COMMONS_INFO, fname)
                    time.sleep(DELAY)
                    if url:
                        best_scr  = sc
                        best_url  = url
                        best_file = fname
                        best_src  = "commons"
                        best_cap  = f"Arms of the House of {house_name} — Wikimedia Commons"
            if best_scr >= 8:
                break

    if best_url and best_scr >= 4:
        print(f"    ✓  score={best_scr}  src={best_src}  {best_file[:60]}")
        cache[slug] = {
            "url":      best_url,
            "filename": best_file,
            "source":   best_src,
            "caption":  best_cap,
            "score":    best_scr,
        }
        found += 1
        save()
    else:
        print(f"    ✗  no confident match found (best score={best_scr})")
        cache[slug] = None   # mark as searched but not found
        save()

save()
print(f"\nDone. {found}/{total} shields found → {OUT_JSON}")
if skipped:
    print(f"({skipped} were already cached from a previous run)")
