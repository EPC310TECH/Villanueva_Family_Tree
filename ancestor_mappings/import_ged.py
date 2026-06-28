#!/usr/bin/env python3
"""
import_ged.py
============
Imports a GEDCOM export into the project's HTML lineage files.

Matching strategy:
  1. Full normalised name
  2. GIVN + _MARNM (how Geni stores the "current" display name)
  3. GIVN + SURN fragments

Name update rules:
  - Skip if new name contains annotation cruft: "(", "8th", "GGM"
  - Skip if new name has repeated words (bad parse like "Bartola Bartola")
  - Skip if the subject's own name would change (Antonio Jasso stays Antonio Jasso)

Usage:
    python3 import_ged.py GEDCOM_FILE.ged [--html FILE.html ...] [--dry-run]
"""
import argparse, json, re, sys, os
from unicodedata import normalize as unorm

JUNK_REGIONS = {"desconcido", "desconocido", "unknown", "n/a", ""}

# ── GEDCOM parser ─────────────────────────────────────────────────────────────

def parse_ged(path):
    with open(path, encoding="utf-8-sig", errors="replace") as fh:
        lines = fh.readlines()

    individuals = {}
    families    = {}
    cur_rec     = None
    cur_type    = None
    cur_tag     = None
    cur_sub     = None

    def new_indi(rid):
        return {"id": rid, "names": [], "givn": "", "marnm": "", "surn": "",
                "birth": {}, "death": {}, "sex": "", "famc": [], "fams": []}

    def new_fam(rid):
        return {"id": rid, "husb": None, "wife": None, "chil": []}

    for raw in lines:
        raw = raw.rstrip("\r\n")
        if not raw.strip():
            continue
        parts = raw.split(" ", 2)
        if len(parts) < 2:
            continue
        try:
            level = int(parts[0])
        except ValueError:
            continue
        tag = parts[1]
        val = parts[2].strip() if len(parts) > 2 else ""

        if level == 0:
            cur_sub = None
            if tag.startswith("@") and val in ("INDI", "FAM"):
                rid = tag
                if val == "INDI":
                    cur_rec = new_indi(rid)
                    cur_type = "INDI"
                    individuals[rid] = cur_rec
                else:
                    cur_rec = new_fam(rid)
                    cur_type = "FAM"
                    families[rid] = cur_rec
            else:
                cur_rec = None; cur_type = None
            continue

        if cur_rec is None:
            continue

        if cur_type == "INDI":
            if level == 1:
                cur_tag = tag; cur_sub = None
                if tag == "NAME":
                    n = re.sub(r"\s+", " ", val.replace("/", " ")).strip()
                    if n:
                        cur_rec["names"].append(n)
                elif tag == "SEX":
                    cur_rec["sex"] = val
                elif tag == "FAMC":
                    cur_rec["famc"].append(val)
                elif tag == "FAMS":
                    cur_rec["fams"].append(val)
            elif level == 2:
                cur_sub = tag
                if tag == "GIVN" and cur_tag == "NAME":
                    if not cur_rec["givn"]:
                        cur_rec["givn"] = val
                elif tag == "SURN" and cur_tag == "NAME":
                    if not cur_rec["surn"]:
                        cur_rec["surn"] = val
                elif tag == "_MARNM" and cur_tag == "NAME":
                    if not cur_rec["marnm"]:
                        cur_rec["marnm"] = val
                elif cur_tag == "BIRT":
                    if tag == "DATE":
                        cur_rec["birth"]["date"] = val
                    elif tag in ("PLAC", "ADDR"):
                        cur_rec["birth"].setdefault("place", val)
                elif cur_tag == "DEAT":
                    if tag == "DATE":
                        cur_rec["death"]["date"] = val
                    elif tag in ("PLAC", "ADDR"):
                        cur_rec["death"].setdefault("place", val)
            elif level == 3:
                if cur_tag == "BIRT":
                    if tag == "STAE":
                        cur_rec["birth"].setdefault("state", val)
                    elif tag == "CTRY":
                        cur_rec["birth"].setdefault("country", val)
                    elif tag == "CITY":
                        cur_rec["birth"].setdefault("city", val)
                elif cur_tag == "DEAT":
                    if tag == "STAE":
                        cur_rec["death"].setdefault("state", val)
                    elif tag == "CTRY":
                        cur_rec["death"].setdefault("country", val)

        elif cur_type == "FAM":
            if level == 1:
                if tag == "HUSB":
                    cur_rec["husb"] = val
                elif tag == "WIFE":
                    cur_rec["wife"] = val
                elif tag == "CHIL":
                    cur_rec["chil"].append(val)

    return individuals, families


# ── name helpers ──────────────────────────────────────────────────────────────

def _ascii(s):
    return unorm("NFKD", s).encode("ascii", "ignore").decode()

def norm(s):
    return re.sub(r"\s+", " ", _ascii(s).lower()).strip()

def name_variants(indi):
    """All candidate name strings for an individual."""
    variants = set()
    for n in indi["names"]:
        if n:
            variants.add(n)
    # GIVN + _MARNM  (Geni's "display name" pattern)
    if indi["givn"] and indi["marnm"]:
        variants.add(f"{indi['givn']} {indi['marnm']}")
    # GIVN + SURN
    if indi["givn"] and indi["surn"]:
        variants.add(f"{indi['givn']} {indi['surn']}")
    return variants

_PARTICLES = {"de", "del", "la", "el", "los", "las", "y", "e", "a", "o",
              "von", "van", "le", "di", "da", "do", "das", "dos", "san", "santa"}

def _has_repeated_content(n):
    words = [w.lower() for w in n.split() if w.lower() not in _PARTICLES]
    return len(words) != len(set(words))

def best_name(indi):
    """Pick the cleanest, most complete name from the GEDCOM individual."""
    candidates = []
    for n in name_variants(indi):
        low = n.lower()
        # skip annotation cruft
        if any(x in low for x in ["(", "8th", "ggm", "el viejo", "alferez", "capitan"]):
            continue
        # skip names with repeated content words (e.g. "Bartola Cipriana Bartola Cipriana")
        if _has_repeated_content(n):
            continue
        candidates.append(n)
    if not candidates:
        return (indi["names"] or [""])[0]
    return max(candidates, key=len)


# ── date helpers ──────────────────────────────────────────────────────────────

def extract_year(date_str):
    if not date_str:
        return None
    m = re.search(r"\b(\d{4})\b", date_str)
    return int(m.group(1)) if m else None

def build_region(bdict):
    if bdict.get("state"):
        return bdict["state"]
    if bdict.get("city"):
        return bdict["city"]
    place = bdict.get("place", "")
    return place.split(",")[0].strip() if place else ""


# ── match + diff ──────────────────────────────────────────────────────────────

def match_and_diff(indi_map, graph_nodes, subject_name="Antonio Jasso"):
    """
    Returns list of (node_id, changes_dict) where changes_dict maps
    field → (old_val, new_val).
    """
    node_by_norm = {}
    for n in graph_nodes:
        k = norm(n.get("name", ""))
        node_by_norm.setdefault(k, []).append(n)

    results = []
    for indi in indi_map.values():
        # find matching node
        node = None
        for v in name_variants(indi):
            k = norm(v)
            if k in node_by_norm:
                node = node_by_norm[k][0]
                break
        if node is None:
            continue

        changes = {}

        # ── name ──
        bn = re.sub(r"\s+", " ", best_name(indi)).strip()
        old_name = node.get("name", "")
        # never rename the subject (Antonio Jasso)
        is_subject = norm(old_name) == norm(subject_name)
        # only update name when it's different AND at least as informative (not shorter)
        if bn and not is_subject and norm(bn) != norm(old_name) and len(bn) >= len(old_name):
            changes["name"] = (old_name, bn)

        # ── birth year ──
        by = extract_year(indi["birth"].get("date", ""))
        if by and node.get("birth") != by:
            changes["birth"] = (node.get("birth"), by)

        # ── death year ──
        dy = extract_year(indi["death"].get("date", ""))
        if dy and node.get("death") != dy:
            changes["death"] = (node.get("death"), dy)

        # ── country ──
        ctry = indi["birth"].get("country", "")
        if ctry and not node.get("country"):
            changes["country"] = ("", ctry)

        # ── region ──
        reg = build_region(indi["birth"])
        if reg and reg.lower() not in JUNK_REGIONS and not node.get("region"):
            changes["region"] = ("", reg)

        if changes:
            results.append((node["id"], changes))

    return results


# ── apply to HTML ─────────────────────────────────────────────────────────────

def apply_to_html(html_path, updates_by_id, dry_run=False):
    with open(html_path, encoding="utf-8") as fh:
        raw = fh.read()
    m = re.search(r"(const GRAPH\s*=\s*)(\{\"nodes\".*?\});", raw, re.DOTALL)
    if not m:
        return 0, {}
    g = json.loads(m.group(2))
    id_map = {n["id"]: n for n in g["nodes"]}

    applied = {}
    for nid, changes in updates_by_id.items():
        # nid is from the reference file; find by name in this file if ids differ
        if nid in id_map:
            n = id_map[nid]
        else:
            continue
        for field, (_, new_val) in changes.items():
            n[field] = new_val
        applied[nid] = changes

    if applied and not dry_run:
        new_json = json.dumps(g, ensure_ascii=False, separators=(",", ":"))
        new_raw  = raw[:m.start(2)] + new_json + raw[m.end(2):]
        with open(html_path, "w", encoding="utf-8") as fh:
            fh.write(new_raw)

    return len(applied), applied


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("ged")
    ap.add_argument("--html", nargs="+",
                    default=["antonio-jasso-lineage.html",
                             "merged-lineage.html",
                             "master-lineage.html"])
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    print(f"\nParsing {a.ged} …")
    indi_map, fam_map = parse_ged(a.ged)
    print(f"  {len(indi_map)} individuals  ·  {len(fam_map)} families")

    # load reference file for matching
    ref = a.html[0]
    if not os.path.exists(ref):
        sys.exit(f"Not found: {ref}")
    with open(ref, encoding="utf-8") as fh:
        raw0 = fh.read()
    m0 = re.search(r"const GRAPH\s*=\s*(\{\"nodes\".*?\});", raw0, re.DOTALL)
    if not m0:
        sys.exit(f"No GRAPH in {ref}")
    g0    = json.loads(m0.group(1))
    nodes = g0["nodes"]

    updates = match_and_diff(indi_map, nodes)
    # convert to dict keyed by node id
    updates_by_id = {nid: ch for nid, ch in updates}

    if not updates_by_id:
        print("\nNo updates needed.")
        return

    tag = "DRY RUN — " if a.dry_run else ""
    print(f"\n{tag}Changes to apply ({len(updates_by_id)} nodes):\n")
    id_to_node = {n["id"]: n for n in nodes}
    for nid, changes in sorted(updates_by_id.items(),
                                key=lambda x: id_to_node.get(x[0], {}).get("gen", 99)):
        nd = id_to_node[nid]
        print(f"  gen {nd.get('gen', '?'):>3}  {nd.get('name', '')}")
        for field, (old, new) in changes.items():
            print(f"         {field}: {old!r}  →  {new!r}")

    if a.dry_run:
        print("\n[dry-run] No files written.")
        return

    print()
    for html_path in a.html:
        if not os.path.exists(html_path):
            print(f"  skip (not found): {html_path}")
            continue
        # re-match against this file (node ids may differ from reference)
        with open(html_path, encoding="utf-8") as fh:
            raw = fh.read()
        m = re.search(r"const GRAPH\s*=\s*(\{\"nodes\".*?\});", raw, re.DOTALL)
        if not m:
            print(f"  skip (no GRAPH): {html_path}")
            continue
        g    = json.loads(m.group(1))
        diff = match_and_diff(indi_map, g["nodes"])
        diff_by_id = {nid: ch for nid, ch in diff}
        n, _ = apply_to_html(html_path, diff_by_id)
        print(f"  {html_path}: {n} node(s) updated")

    print("\nDone.")


if __name__ == "__main__":
    main()
