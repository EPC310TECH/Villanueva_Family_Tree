# Geni → Interactive Lineage Graph

Turn a Geni.com **"Ancestors of X (20 generations)"** PDF export into a single
self-contained, interactive HTML graph — no manual cleaning, no Cytoscape pass.
The cleaning, parent→child linking, category coloring, and node sizing you used
to do by hand all happen automatically.

## Quick start

```bash
pip install pdfplumber          # one-time (the only dependency)
python geni_pipeline.py "Ancestors of Someone.pdf"
# -> someone-lineage.html
```

Open the resulting `.html` in any browser. Everything (d3, data, styling) is
inlined into that one file — nothing to host, nothing to upload.

Two finished examples are in `examples/`:
- `antonio-jasso-lineage.html` — 197 people, Spanish-colonial Mexican line
- `afonso-godinez-lineage.html` — 566 people, Iberian royalty (León / Asturias / Navarra)

## Options

```
python geni_pipeline.py INPUT.pdf [MORE.pdf ...] [options]

  -o, --out PATH     output html (default: <root-name>-lineage.html)
  --outdir DIR       directory for auto-named outputs (default: .)
  --json PATH        also write the cleaned graph as JSON (reusable)
  --merge            fuse all input PDFs into ONE graph; shared ancestors
                     (same name + birth year) collapse across trees
  --title "..."      override the page title
  --no-dedupe        keep every occurrence as its own node (pure tree, no diamonds)
  --template PATH    viewer template (default: ./template.html)
  --d3 PATH          d3 build to inline (default: ./d3.min.js)
```

## How it works (7 stages)

1. **Extract** — pull text from the PDF with `pdfplumber`.
2. **Parse** — the export is a depth-first ahnentafel outline. The leading
   number on each line *is* the generation depth (1 = the subject, 20 = the
   deepest ancestor). Wrapped lines are stitched back onto their person.
3. **Clean** — split each entry into name / birth / death; pull years (handling
   `circa`, `before`, `between … and …`), and a best-guess country.
4. **Classify** — a rank category is derived from honorific keywords embedded in
   the name (see below). This replaces the manual coloring step.
5. **Link** — a person's parent is simply *the most recent person one generation
   shallower*. That single rule rebuilds every parent→child edge correctly,
   even across deep depth-first returns.
6. **Collapse** — recurring ancestors (pedigree collapse) are merged into one
   node, creating the diamonds. A node's **size** is driven by how many times it
   recurs, so your most pedigree-collapsed progenitors surface automatically.
7. **Render** — nodes, edges, legend, and metadata are injected into the viewer
   template → one standalone `.html`.

## Auto-classification

Categories are matched in priority order; the first keyword hit wins. Matching is
accent- and case-insensitive, so `León`, `leon`, `LEÓN` all match.

| Category   | Color   | Example keywords (ES / PT / EN)                                   |
|------------|---------|------------------------------------------------------------------|
| royalty    | gold    | rey, reina, rei, rainha, emperador, duque, infante, prince…      |
| nobility   | crimson | conde, marqués, vizconde, barón, señor de, senhor da, D., dom…   |
| clergy     | purple  | fray, obispo, bispo, arzobispo, presbítero, diácono…             |
| military   | blue    | capitán, conquistador, maese de campo, alférez, comendador…      |
| office      | teal    | alcalde, alcaide, jurado, regidor, gobernador, escribano…        |
| indigenous | amber   | huachichil, india, indio, cacique, nahua, mexica…                |
| untitled   | sable   | everyone else                                                    |

The legend in the viewer only shows the categories actually present in a file,
with live counts. To tune the rules, edit the `CATEGORIES` list at the top of
`geni_pipeline.py` — add a keyword or a whole new category and re-run.

## Deduplication (pedigree collapse)

Two occurrences merge into one node **only when the normalized name *and* birth
year match**. This is deliberately conservative:

- Year-less placeholders (`N N`, `(No Name)`, `<private>`, `Ficticious`) are
  always kept distinct, never fused into one mega-node.
- Two same-named people with different birth years stay separate.
- `--no-dedupe` disables merging entirely if you want the raw tree.

A merged node records how many lines it sits on; the viewer shows this as
"appears N×" on hover and "N separate lines" in the detail card.

## The viewer

- **Layout** toggles between *by generation* (clean layers) and *by year* (true
  chronology — the better view once heavy collapse pulls shared ancestors to
  different depths).
- **Click any person** to gild their full ancestor + descendant line and dim the
  rest; the card shows titles, place, generation, collapse count, and
  ancestor/descendant tallies.
- **Search** jumps to and frames any name. **Reset** re-fits the whole tree.

## A note on data quality

Edge direction is always locally correct (parent = one generation up). When the
"by generation" view shows a long edge crossing several rows, that's a
genuinely pedigree-collapsed ancestor sitting at multiple depths at once — not an
error. The only true orientation oddities trace back to Geni's own fuzzy `circa`
dates, not the parser. The "by year" view reflects the real chronology.
