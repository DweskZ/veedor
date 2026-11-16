# Veedor web

Next.js 16 (App Router, TypeScript, Tailwind 4) dashboard for the Veedor API. Veedor is a Ruray product: brand, tokens, risk scale and illustration method are in `../docs/BRAND.md`.

## Run

```bash
pnpm install
pnpm dev            # http://localhost:3000, expects the API at http://localhost:8000/api/v1
pnpm lint
pnpm build && pnpm start
```

The API allows CORS only from `http://localhost:3000`, so serve the web on that port.

## Environment variables

| Variable | Default | When | Purpose |
|---|---|---|---|
| `NEXT_PUBLIC_API_URL` | `http://localhost:8000/api/v1` | build time (inlined) | API base URL used by the browser (review form) and by the server unless overridden |
| `API_INTERNAL_URL` | unset | runtime, server only | API URL for server-side calls, e.g. `http://api:8000/api/v1` inside a container network |
| `NEXT_PUBLIC_SITE_URL` | `http://localhost:3000` | build time | Base URL for Open Graph metadata |
| `NEXT_PUBLIC_USE_MOCKS` | unset | build time | `1` serves clearly labelled SAMPLE data and shows a "Datos de ejemplo" banner. Never set in production |

`NEXT_PUBLIC_*` values are baked into the bundle: change them, rebuild.

## Docker

```bash
docker build -t veedor-web --build-arg NEXT_PUBLIC_API_URL=http://localhost:8000/api/v1 .
docker run --rm -p 3000:3000 -e API_INTERNAL_URL=http://host.docker.internal:8000/api/v1 \
  --add-host host.docker.internal:host-gateway veedor-web
```

The image uses Next.js `output: "standalone"` (multi-stage, non-root, `node server.js`).

## Design system

- **One theme**: "ice and terracotta" (ice `#E3EEFF`, ink `#1A1F36`, terracotta `#D9480F`). There is no dark mode and no theme toggle. Tokens and every component class live in `src/app/globals.css`; no gradients, no monospace.
- **Fonts**: Plus Jakarta Sans, self-hosted. The four woff2 files (500, 600, 700, 800) are in `public/fonts/` and loaded with `next/font/local` in `src/app/layout.tsx`; the CSP keeps `font-src 'self'`. `assets/jakarta-*.ttf` are decompressed copies used only by the Open Graph image (satori does not read woff2).
- **Illustrations**: five isometric line-art models in `public/art/` (`hero`, `datos`, `investigacion`, `verificacion`, `vacio`), WebP at 960 and 480 px, rendered by `src/components/Art.tsx` with explicit size, `alt` text and lazy loading. They were generated with the Codex CLI using two Ruray maquetas as style references; prompts and sources are in `art-src/` (git-ignored) and the method and prompt text are in `../docs/BRAND.md`. To add one: write `art-src/prompt-<name>.txt`, run `art-src/run.sh <name>`, look at the result, crop to the same lower 1254 x 874 band, convert with `magick ... -resize 960x` and `480x` to `public/art/<name>-{960,480}.webp`, and add the name and its `alt` to `Art.tsx`. If a transparent PNG comes back on flat magenta, key it with `ffmpeg -i in.png -vf "colorkey=0xFF00FF:0.30:0.10,format=rgba" out.png` and check alpha.
- **Icons and share image**: `src/app/icon.svg`, `src/app/apple-icon.tsx` and `src/app/opengraph-image.tsx` are generated in code.
- **Risk scale**: five steps from ice-deep to ink, terracotta only for the top band, with a level name and a four-bar glyph so it never relies on colour (`src/components/ui.tsx`, `src/lib/risk.ts`). Contrast ratios are in `../docs/BRAND.md`.
- **Responsive**: tables become cards under 880 px; the agent diagram becomes a numbered list under 1100 px; the sticky in-page index appears from 1100 px on process pages.
- **Plain-language copy for each signal** (what was observed, why it can matter, how it can be normal) is in `src/lib/signal-copy.ts`.

## Map geometry (`/mapa` and the home page)

- Source: **geoBoundaries gbOpen, Ecuador ADM1 (24 provinces)**, `https://github.com/wmgeolab/geoBoundaries/tree/main/releaseData/gbOpen/ECU/ADM1` (file `geoBoundaries-ECU-ADM1.geojson`, boundary year 2011, metadata `boundaryLicense`: **CC0 1.0, public domain dedication**). Retrieved 2026-11-16. Natural Earth admin-1 (public domain) was the alternative; geoBoundaries was chosen because it already has the 24 current provinces including Santa Elena and Santo Domingo de los Tsachilas. No INEC/IGM file was used.
- The raw file lives in `geo-src/` (git-ignored). `node scripts/build-map.mjs` projects it (equirectangular, 1 degree = 100 units), simplifies it (Douglas-Peucker, about 1 km), draws Galapagos in an inset at 55 % scale and writes `src/data/ecuador-provinces.json` (SVG path strings and label anchors, about 27 KB, committed). It maps geometry names to the API keys explicitly and **fails unless all 24 provinces match once each**.
- The attribution is printed under the table on `/mapa`. No map library and no tile or other external request at runtime.
- Colour classes are quintiles of the 24 provinces (five groups with the same number of provinces), recomputed in the browser for the selected metric; the legend shows the observed range of each group. The top group is terracotta with ink stripes.

## Glossary

`src/data/glossary.json` (`{ items: [{ term, aliases, definition_es, source }] }`) is the single source: the web reads it at build time (`<Term t="...">` popovers, `/glosario`) and the API serves it at `/glossary`. Keep exactly those four fields.

## New pages and components (stage 3)

`/mapa`, `/tendencias`, `/glosario`; `HeaderSearch` (combobox over `/buyers/search`), `RandomProcessButton` (`/processes/random`), `ExplorerShell` (URL-synced filters with router transitions), `ContextCharts` (`/processes/{ocid}/context`), `AgentStepThrough` (stored tool log). Browser-side API calls are in `src/lib/client-api.ts`; with `NEXT_PUBLIC_USE_MOCKS=1` every new endpoint has a fictional sample.

## Notes
- Real mode never shows mock data: when the API fails, pages show an explicit error state.
- Filters on `/procesos` live in the URL (`year`, `method`, `signal`, `min_score`, `q`, `sort`, `page`); `sort=-risk_score` means descending.
