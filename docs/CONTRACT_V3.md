# Veedor — build contract, stage 3 (clarity and interaction)

Binding for this stage. `docs/CONTRACT.md` and `docs/CONTRACT_V2.md` still apply in full:
no invented data, indicators never accusations, natural persons never shown, parameterised SQL
only, no `.env*` edits, no git commands, `rg`/`fd`/`bat`/`sd`/`eza`, no `ruff format` outside
your own files, no `uv add`. Read `docs/REVIEWS.md`: do not reintroduce what four reviews broke.
The visual identity is Ruray's (`docs/BRAND.md`).

The owner's instruction: **the site must be clearer and more interactive.** Clarity outranks
decoration. A visitor who knows nothing about procurement should always know what they are
looking at, what it means, and what it does not mean.

## New API surface (owner: api)

All under `/api/v1`, GET only, masked like every other response, validated at the edge,
bounded, cached in memory keyed by the data build signature where they are full aggregates.

1. `GET /stats/by-region` → one row per province of the BUYING entity:
   `{ items: [{ region, region_label, competitive_processes, with_signal, pct_with_signal,
   single_bidder, pct_single_bidder, mean_score, processes_total, awarded_total }],
   national: { same fields }, basis: "competitive", data_built_at }`.
   `region` is the canonical upper-case key used by the lake (`buyer_region`); `region_label`
   is a display name in proper Spanish (accents, e.g. "Los Ríos", "Santo Domingo de los
   Tsáchilas"), from one mapping in code covering every value present in the data (24
   provinces; null grouped as `"SIN_REGION"` / "Sin provincia registrada"). Percentages are
   over competitive processes; a province with fewer than 500 competitive processes is still
   returned but flagged `small_sample: true`.
2. `GET /stats/by-year` → per year (2015–2026): `processes_total`, `competitive_processes`,
   `pct_single_bidder` for the procedures with stable naming across the period (Subasta
   Inversa Electrónica), `pct_with_signal`, `awarded_total`, share of awarded amount by method
   group (`competitive`, `direct`, `catalogue`). Include `partial_year: true` for the last
   year and `notes` for known caveats (2022 has far fewer published processes; procedure
   names changed around 2025–2026).
3. `GET /processes?region=<KEY>` — new optional filter on the buyer's province, validated
   against the known keys (422 otherwise). Existing filters unchanged.
4. `GET /processes/random?with_signals=true|false&min_score=` → 200 with one process summary
   (same shape as a list item) chosen uniformly among matches whose identifier the API
   accepts and whose winner is a company or public entity; `Cache-Control: no-store`.
5. `GET /buyers/search?q=<text>&limit=` → up to 10 buying entities whose name matches (accent-
   and case-insensitive, prefix and word matches ranked first): `{ items: [{ ruc, name,
   region_label, processes_total }] }`. Minimum 3 characters, maximum 60, wildcards escaped,
   natural-person buyers excluded. Must answer fast (precomputed or cached buyer table).
6. `GET /processes/{ocid}/context` → what the visitor needs to compare this process with
   others like it: for its method and year, the distribution of number of tenderers (counts
   for 1, 2, 3, 4, 5, 6+), the median award/budget ratio and its quartiles, the median tender
   window in days where available, and where this process falls in each (value + percentile).
   Null where the field does not exist for that procedure. No interpretation in the payload.
7. `GET /glossary` → `{ items: [{ term, aliases[], definition_es, source }] }` from one file
   in the repository (owner: web writes the content; api only serves it) — see "Glossary".

Performance: none of these may scan the full lake per request after the first call for a data
build (cache or precompute). The text search route stays as is.

## Web (owner: web)

1. **Plain-language evaluation block** on the home page: no "AUC", no "intervalo". Say what was
   tried, what happened and what it means, in three short sentences; link to the methodology
   page for the figures. Figures stay exact on the methodology page.
2. **Map of Ecuador** (`/mapa`, and a compact version on the home page): provinces coloured by
   the share of competitive processes with at least one signal. Honest framing in the title and
   a one-line note: more signals do not mean more problems; they often reflect fewer suppliers
   in the area. Province of the buying entity, stated. A metric switch (share with a signal /
   share with a single bidder). Hover and focus show the province name, the percentage, the
   number of processes it is based on and the national figure; small samples are marked.
   Click or Enter opens `/procesos?region=<KEY>`. Keyboard navigable; an equivalent sortable
   table below the map for screen readers and mobile. Galápagos shown in an inset, labelled.
   Geometry: province boundaries from a source whose licence allows reuse (verify and state
   it; attribute it on the page), simplified at build time to static SVG paths — no map tile
   service, no external request at runtime, no heavy map library in the browser bundle.
   Brand palette only: a sequential ice-to-ink scale with terracotta reserved for the top
   class; classes shown in a legend with their ranges; readable without colour (pattern or
   label on the top class).
3. **Glossary with inline help**: procurement terms that appear in the UI (oferente, subasta
   inversa electrónica, menor cuantía, cotización, licitación, adjudicación, presupuesto
   referencial, catálogo electrónico, RUC, CPC, entidad contratante, señal de riesgo, señal
   de contexto, puntaje…) are marked with a subtle dotted underline; hover, focus or tap opens
   a small popover with a one- or two-sentence definition in plain Spanish. Definitions must be
   accurate and neutral; where a definition rests on a legal concept, keep it generic and do
   not cite article numbers. One source file; also listed on a `/glosario` page.
4. **Find things fast**: a search box in the header that suggests buying entities as you type
   (debounced, keyboard navigable, announces results to screen readers) and accepts a process
   code; a "Proceso al azar" button on the home page and the explorer.
5. **Explorer**: quick filter chips with plain names and live counts where cheap ("Un solo
   oferente", "Proveedor nuevo", "Compras repetidas", "Más de USD 1 millón"), a province
   filter, active filters shown as removable chips, results that update without a full page
   reload while the URL stays shareable, and a clear empty state that suggests what to relax.
6. **Process page**: for each signal that has comparison data, a small chart showing where
   this process sits among others of the same type and year (for example a row of bars for
   "number of tenderers" with this process's bar marked) with a one-line reading in plain
   words that describes position only ("la mitad de los procesos de este tipo tuvo 3 o más").
   A "Cómo investigaron los agentes" step-through for investigated processes: a timeline of
   the stored tool log that can be played, paused and stepped, showing which specialist asked
   which source and what came back (from structured fields only).
7. **Trends** (`/tendencias`): two or three interactive charts from `/stats/by-year` — share
   of single-bidder reverse auctions per year, how the State buys (method mix by amount) —
   each with a one-sentence reading, the caveats from the API notes shown next to the chart,
   and hover/focus values. Charts drawn in SVG with the brand palette; no chart library heavier
   than a few kilobytes.
8. Every interactive element works with keyboard and touch, has a visible focus style, respects
   `prefers-reduced-motion`, and degrades to readable static content without JavaScript.
   Nothing interactive may hide information that a non-interactive visitor needs.

## Acceptance

- `uv run ruff check src tests scripts`, `uv run pytest -o addopts=""`, web lint + typecheck +
  build, `scripts/smoke_test.py` extended with the new endpoints, all green.
- The new endpoints pass the same injection payload set as the existing ones; no 500s; the
  DuckDB lockdown tests still pass; masking holds on every new response.
- Numbers on the map and charts equal the API values, and the API values are reproducible with
  a DuckDB query over the lake (the orchestrator will spot-check three provinces and two years).
- Screenshots at 1280 and 390 of every new page, looked at before reporting.
