#!/usr/bin/env python3
"""
normalize_data.py
=================
Normalize all rendered lineage HTML files:

  Names
  -----
  • ALL-CAPS tokens → Title Case   (JACINTO → Jacinto, AQUITANIA → Aquitania)
  • Mid-name particles lowercase   (De → de, Van → van, Del → del, Of → of …)
  • Roman numerals stay uppercase  (I, II, III …)
  • Special tokens preserved       (D., Dª, Sir, NN …)
  • Comma-separated title clause   translated to English (, rey de → , King of)

  Titles field
  ------------
  • Category labels kept as-is     (Noble, Royal, Clergy …)
  • Spanish / Portuguese / French  → English
      rey → King      reina consorte → Queen Consort
      conde → Count   condesa → Countess    duque → Duke
      señor → Lord    señora → Lady         senhor → Lord (Port.)
      barón → Baron   infante → Infante     marqués → Marquess …
  • Kingdom names normalised       (Castilla → Castile, Aragón → Aragon …)
  • Ordinals translated            (1er. → 1st, 2º → 2nd …)

  Spanish naming style
  --------------------
  Existing 'y' connectors between surnames are preserved and normalised to
  lowercase. No automatic 'y' is injected (genealogical context required).
"""
import json, re, os

HERE = os.path.dirname(os.path.abspath(__file__))

# ── helpers ──────────────────────────────────────────────────────────────────

def esc(s):
    return str(s).replace('&','&amp;').replace('<','&lt;').replace('>','&gt;')

# ── Name capitalisation ───────────────────────────────────────────────────────

# These words should be lowercase when they appear mid-name (not the first token)
PARTICLES = frozenset({
    # Spanish / Portuguese
    'de','del','da','das','do','dos','di','e',
    # Spanish articles / prepositions
    'el',
    # French
    'du','des',
    # Germanic
    'van','von','af','zu',
    # English
    'of',
    # Romance articles (as name particles)
    'la','le','les','lo','los','las',
    # Surname connectors — preserve but normalise to lower
    'y',
})

# Standalone tokens that must never be changed
KEEP_TOKENS = frozenset({
    'D.','Dª','Sir','Dame','SJ','St.','NN','Ntra.','Don','Doña','Sr.','Sra.',
})

ORDINAL_RE = re.compile(r'^\d+(st|nd|rd|th|[º°ª]|er\.?|a\.?)$', re.I)

ROMAN_SET = frozenset({
    'I','II','III','IV','V','VI','VII','VIII','IX','X',
    'XI','XII','XIII','XIV','XV','XVI','XVII','XVIII','XIX','XX',
    'XXI','XXII','XXIII','XXIV','XXV',
})
ROMAN_PAT = re.compile(r'^M{0,4}(CM|CD|D?C{0,3})(XC|XL|L?X{0,3})(IX|IV|V?I{0,3})$')

def _fix_token(tok: str, is_first: bool) -> str:
    if tok in KEEP_TOKENS:
        return tok
    if ORDINAL_RE.match(tok):
        return tok
    # NN / NNN / NNNN "unknown" placeholders — keep as-is
    if re.match(r'^N{2,}$', tok):
        return tok

    # Strip wrapping punctuation for analysis
    prefix = ''
    suffix = ''
    bare = tok
    for ch in ('(', '"', "'", '«'):
        if bare.startswith(ch):
            prefix += ch; bare = bare[1:]
    for ch in (')', '"', "'", '»', ','):
        if bare.endswith(ch):
            suffix = ch + suffix; bare = bare[:-1]

    if not bare:
        return tok

    # Roman numeral — keep uppercase
    if bare.upper() in ROMAN_SET and ROMAN_PAT.match(bare.upper()):
        return prefix + bare.upper() + suffix

    # Particle mid-name — lowercase
    if not is_first and bare.lower() in PARTICLES:
        return prefix + bare.lower() + suffix

    # ALL-CAPS token (2+ pure-alpha chars, not abbreviations like "N.N.") → title case
    if bare.isupper() and len(bare) >= 2 and bare.isalpha():
        return prefix + bare.capitalize() + suffix

    return tok


def fix_name(name: str) -> str:
    """Fix capitalisation in a person's full name string."""
    if not name:
        return name

    # Split on FIRST comma only — everything after is title/descriptor
    ci = name.find(',')
    if ci >= 0:
        name_part, rest = name[:ci], name[ci + 1:].strip()
    else:
        name_part, rest = name, None

    tokens = name_part.split()
    fixed = ' '.join(_fix_token(t, i == 0) for i, t in enumerate(tokens))

    if rest is not None:
        fixed += ', ' + translate_title(rest)

    return fixed


# ── Title translation ─────────────────────────────────────────────────────────

# Substitutions applied in order (most specific / multi-word FIRST)
# All patterns matched case-insensitively
TITLE_SUBS = [
    # ── Multi-word compound titles ──────────────────────────────────────────
    (r'\breina\s+consorte\b',           'Queen Consort'),
    (r'\breina\s+consort\b',            'Queen Consort'),
    (r'\bcondesa\s+consorte\b',         'Countess Consort'),
    (r'\bconde\s+consorte\b',           'Count Consort'),
    (r'\bduquesa\s+consorte\b',         'Duchess Consort'),
    (r'\bduque\s+consorte\b',           'Duke Consort'),
    (r'\bmaese\s+de\s+campo\b',         'Field Marshal'),
    (r'\badelantado\s+mayor\b',         'Governor-General'),
    (r'\balcalde\s+mayor\b',            'Chief Magistrate'),
    (r'\balguacil\s+mayor\b',           'Chief Constable'),
    (r'\bmayordomo\s+del\s+rey\b',      'Royal Steward'),
    (r'\bmayordomo\s+mayor\b',          'Lord Steward'),
    (r'\bcapitán\s+general\b',          'Captain General'),
    (r'\bcapitan\s+general\b',          'Captain General'),

    # ── 'y' / 'e' connector + article contractions → 'and' ─────────────────
    # Must come before the simple \bde\b → 'of' substitution
    (r'\s+y\s+del\s+',                  ' and '),
    (r'\s+y\s+de\s+la\s+',             ' and '),
    (r'\s+y\s+de\s+los\s+',            ' and '),
    (r'\s+y\s+de\s+las\s+',            ' and '),
    (r'\s+y\s+de\s+',                  ' and '),
    (r'\s+y\s+',                        ' and '),
    (r'\s+e\s+do\s+',                   ' and '),
    (r'\s+e\s+da\s+',                   ' and '),
    (r'\s+e\s+',                        ' and '),

    # ── Article contractions → 'of' ─────────────────────────────────────────
    (r'\bde\s+la\b',                    'of'),
    (r'\bde\s+los\b',                   'of'),
    (r'\bde\s+las\b',                   'of'),
    (r'\bdel\b',                        'of'),
    (r'\bda\b',                         'of'),
    (r'\bdo\b',                         'of'),
    (r'\bdas\b',                        'of'),
    (r'\bdos\b',                        'of'),
    (r'\bdu\b',                         'of'),

    # ── Royal titles ─────────────────────────────────────────────────────────
    (r'\brey\b',                        'King'),
    (r'\breina\b',                      'Queen'),
    (r'\brei\b',                        'King'),       # Portuguese
    (r'\brainha\b',                     'Queen'),      # Portuguese

    # ── Nobility ─────────────────────────────────────────────────────────────
    (r'\bcondesa\b',                    'Countess'),
    (r'\bconde\b',                      'Count'),
    (r'\bduquesa\b',                    'Duchess'),
    (r'\bduque\b',                      'Duke'),
    (r'\bvizcondesa\b',                 'Viscountess'),
    (r'\bvizconde\b',                   'Viscount'),
    (r'\bmarquesa\b',                   'Marchioness'),
    (r'\bmarqués\b',                    'Marquess'),
    (r'\bmarques\b',                    'Marquess'),
    (r'\bbaronesa\b',                   'Baroness'),
    (r'\bbarón\b',                      'Baron'),
    (r'\bbaron\b',                      'Baron'),
    (r'\binfanta\b',                    'Infanta'),
    (r'\binfante\b',                    'Infante'),
    (r'\bseñora\b',                     'Lady'),
    (r'\bseñor\b',                      'Lord'),
    (r'\bsenhora\b',                    'Lady'),       # Portuguese
    (r'\bsenhor\b',                     'Lord'),       # Portuguese
    (r'\bprincesa\b',                   'Princess'),
    (r'\bpríncipe\b',                   'Prince'),
    (r'\bprincipe\b',                   'Prince'),

    # ── French ───────────────────────────────────────────────────────────────
    (r'\bcomtesse\b',                   'Countess'),
    (r'\bcomtessa\b',                   'Countess'),   # Catalan
    (r'\bcomte\b',                      'Count'),
    (r'\bseigneur\b',                   'Lord'),
    (r'\bvicomtesse\b',                 'Viscountess'),
    (r'\bvicomte\b',                    'Viscount'),
    (r'\bduchesse\b',                   'Duchess'),
    (r'\bduc\b',                        'Duke'),
    (r'\bprincess\b',                   'Princess'),   # already English but mixed

    # ── German / Dutch ───────────────────────────────────────────────────────
    (r'\bherzog\b',                     'Duke'),
    (r'\bherzogin\b',                   'Duchess'),
    (r'\bmarkgraf\b',                   'Margrave'),
    (r'\blandgraf\b',                   'Landgrave'),
    (r'\bpfalzgraf\b',                  'Count Palatine'),
    (r'\bgräfin\b',                     'Countess'),
    (r'\bgraf\b',                       'Count'),
    (r'\bgravin\b',                     'Countess'),   # Dutch
    (r'\bgraaf\b',                      'Count'),      # Dutch
    (r'\bvon\b',                        'of'),         # German preposition in titles

    # ── Church ───────────────────────────────────────────────────────────────
    (r'\barzobispo\b',                  'Archbishop'),
    (r'\bobispo\b',                     'Bishop'),
    (r'\babadesa\b',                    'Abbess'),
    (r'\babad\b',                       'Abbot'),

    # ── Civic / military ─────────────────────────────────────────────────────
    (r'\bgobernador\b',                 'Governor'),
    (r'\badelantado\b',                 'Governor'),
    (r'\balcaide\b',                    'Castellan'),
    (r'\balcalde\b',                    'Mayor'),
    (r'\bcapitán\b',                    'Captain'),
    (r'\bcapitan\b',                    'Captain'),
    (r'\balférez\b',                    'Ensign'),
    (r'\balferez\b',                    'Ensign'),
    (r'\bmaestro\b',                    'Master'),

    # ── Simple preposition ───────────────────────────────────────────────────
    (r'\bde\b',                         'of'),

    # ── Ordinals ─────────────────────────────────────────────────────────────
    (r'\b1er?\.\s*',                    '1st '),
    (r'\b1[oº°]\b',                     '1st'),
    (r'\b2[oº°]\b',                     '2nd'),
    (r'\b3[oº°]\b',                     '3rd'),
    (r'\b(\d+)[oº°]\b',                r'\1th'),
    (r'\b2\.º\b',                       '2nd'),
    (r'\b3\.º\b',                       '3rd'),
    (r'\b(\d+)\.º\b',                  r'\1th'),

    # ── English title capitalisation fixes ───────────────────────────────────
    (r'\bOf\b',                         'of'),
    (r'\bThe\b(?!\s+[A-Z])',            'the'),
]

# Kingdom / territory name translations (applied after title word substitution)
PLACE_SUBS = [
    (r'\bCastilla\b',       'Castile'),
    (r'\bCastela\b',        'Castile'),    # Portuguese
    (r'\bAragón\b',         'Aragon'),
    (r'\bNavarra\b',        'Navarre'),
    (r'\bNavara\b',         'Navarre'),
    (r'\bAstúrias\b',       'Asturias'),   # Portuguese variant
    (r'\bLusitânia\b',      'Lusitania'),
    (r'\bAndalucía\b',      'Andalusia'),
    (r'\bAndalucia\b',      'Andalusia'),
    (r'\bGalicia\b',        'Galicia'),    # same in English
    (r'\bBurgonha\b',       'Burgundy'),   # Portuguese
    (r'\bBorgoña\b',        'Burgundy'),   # Spanish
    (r'\bBourgogne\b',      'Burgundy'),   # French
]

# Labels that must be left exactly as-is
KEEP_LABELS = frozenset({
    'Noble','Royal','Clergy','Military','Official','Indigenous',
    'Conquistador','Conquistador de la Nueva Galicia','Conquistador de Nueva España',
    'Mosen','Mosén','mosen','Jurado','Maese de Campo',
    'Don','Doña','Dona','D.','D',
    'o Alferes','o Conquistador',
    'Capitan','Capitán',   # kept if standalone without rank attached
})


def translate_title(title: str) -> str:
    """Translate a title phrase from Spanish/Portuguese/French to English."""
    if not title:
        return title
    t = title.strip()
    if t in KEEP_LABELS:
        return t

    for pat, repl in TITLE_SUBS:
        t = re.sub(pat, repl, t, flags=re.IGNORECASE)

    for pat, repl in PLACE_SUBS:
        t = re.sub(pat, repl, t)

    # Collapse double spaces
    t = re.sub(r' {2,}', ' ', t).strip()

    # Capitalise first character if lower, but not if it's a bare preposition phrase
    _LOWER_STARTERS = frozenset({'of', 'and', 'the', 'in', 'at', 'to', 'by', 'from', 'o', 'a', 'el', 'la', 'os', 'as'})
    if t and t[0].islower() and t.split()[0].lower() not in _LOWER_STARTERS:
        t = t[0].upper() + t[1:]

    return t


# ── HTML processing ───────────────────────────────────────────────────────────

def process_html(path: str) -> tuple[int, int]:
    """Normalise one HTML file in-place. Returns (name_changes, title_changes)."""
    with open(path, encoding='utf-8') as f:
        content = f.read()

    m = re.search(r'const GRAPH\s*=\s*(\{"nodes".*?\});', content, re.DOTALL)
    if not m:
        return 0, 0

    graph = json.loads(m.group(1))
    name_chg = title_chg = 0

    for node in graph['nodes']:
        # Name
        old_n = node.get('name', '')
        new_n = fix_name(old_n)
        if new_n != old_n:
            node['name'] = new_n
            name_chg += 1

        # Titles field
        old_t = node.get('titles', '')
        if old_t:
            new_t = translate_title(old_t)
            if new_t != old_t:
                node['titles'] = new_t
                title_chg += 1

    payload   = json.dumps({'nodes': graph['nodes'], 'edges': graph['edges']},
                           separators=(',', ':'))

    m2 = re.search(r'const LEGEND\s*=\s*(\[.*?\]);', content, re.DOTALL)
    legend_js = m2.group(1) if m2 else '[]'
    m3 = re.search(r'const META\s*=\s*(\{.*?\});', content, re.DOTALL)
    meta_js   = m3.group(1) if m3 else '{"title":"","subtitle":""}'
    meta      = json.loads(meta_js)

    tmpl = os.path.join(HERE, 'template.html')
    d3p  = os.path.join(HERE, 'd3.min.js')
    with open(tmpl) as f: tpl = f.read()
    with open(d3p)  as f: d3  = f.read()

    out = (tpl
           .replace('/*__D3__*/', d3)
           .replace('/*__DATA__*/', payload)
           .replace('/*__LEGEND__*/', legend_js)
           .replace('/*__META__*/', meta_js)
           .replace('{{TITLE}}',    esc(meta.get('title', '')))
           .replace('{{SUBTITLE}}', esc(meta.get('subtitle', ''))))

    with open(path, 'w', encoding='utf-8') as f:
        f.write(out)

    return name_chg, title_chg


# ── Preview / dry-run helper ──────────────────────────────────────────────────

def preview(path: str, limit: int = 40):
    """Print before/after samples without writing."""
    with open(path, encoding='utf-8') as f:
        content = f.read()
    m = re.search(r'const GRAPH\s*=\s*(\{"nodes".*?\});', content, re.DOTALL)
    if not m:
        return
    nodes = json.loads(m.group(1))['nodes']
    shown = 0
    for node in nodes:
        old_n = node.get('name', '')
        new_n = fix_name(old_n)
        old_t = node.get('titles', '')
        new_t = translate_title(old_t) if old_t else old_t
        if new_n != old_n or new_t != old_t:
            if shown >= limit:
                print(f'  … ({shown} shown, more changes exist)')
                break
            if new_n != old_n:
                print(f'  NAME   before: {old_n}')
                print(f'         after:  {new_n}')
            if new_t != old_t:
                print(f'  TITLE  before: {old_t}')
                print(f'         after:  {new_t}')
            print()
            shown += 1


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    import sys
    dry = '--dry-run' in sys.argv or '-n' in sys.argv
    target = next((a for a in sys.argv[1:] if a.endswith('.html')), None)

    if dry:
        path = target or os.path.join(HERE, 'master-lineage.html')
        print(f'DRY RUN — previewing changes in {os.path.basename(path)}\n')
        preview(path, limit=60)
        return

    htmls = (
        [target] if target
        else sorted(
            os.path.join(HERE, h)
            for h in os.listdir(HERE)
            if h.endswith('-lineage.html')
        )
    )

    print(f'Normalizing {len(htmls)} HTML file(s)…\n')
    total_n = total_t = 0
    for path in htmls:
        nn, nt = process_html(path)
        total_n += nn
        total_t += nt
        label = os.path.basename(path)
        print(f'  {nn:>4} name  {nt:>4} title  {label}')

    print(f'\n  ✓  {total_n} name fixes, {total_t} title translations across {len(htmls)} file(s).')


if __name__ == '__main__':
    main()
