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
| `NEXT_PUBLIC_ALLOW_INDEXING` | `0` | build time | `1` or `true` lets search engines in (`robots.txt` allows static pages and lists `sitemap.xml`). Default: nothing is indexed (`Disallow: /`, empty sitemap, `noindex` meta). Process, supplier and entity pages are never in the sitemap and are disallowed in `robots.txt` even when indexing is on |
| `NEXT_PUBLIC_USE_MOCKS` | unset | build time | `1` serves clearly labelled SAMPLE data and shows a "Datos de ejemplo" banner. Never set in production |

`NEXT_PUBLIC_*` values are baked into the bundle: change them, rebuild.

## Feature flags from the API

`GET /api/v1/meta` returns `ask_enabled` and `quotes_enabled`. A missing flag counts as `false`.

- `ask_enabled`: the "Pregunta sobre este proceso" section, with its disclosure before the submit button.
- `quotes_enabled`: the "Citas de la fuente" section, its item in the section bar and the quotes inside answers. The quotes request is only made when the flag is true; a 404 or any failure hides the section silently. Quotes are never linked to a risk signal.
- Contact for reports: the quotes note says "si ves un dato personal, avísanos por el contacto del pie de página". The only contact the site has is the Ruray Instagram profile shown in the footer. **The owner must supply a dedicated contact (e-mail address or issue tracker URL) before `quotes_enabled` is turned on**; replace the footer line in `src/components/Footer.tsx`.

## Content Security Policy

The policy is built per request in `src/proxy.ts` with a nonce, as described in `node_modules/next/dist/docs/01-app/02-guides/content-security-policy.md`: `script-src 'self' 'nonce-…' 'strict-dynamic'` (plus `'unsafe-eval'` in development only). Next.js puts the nonce on its own scripts; `src/app/layout.tsx` reads the `x-nonce` request header and puts it on its one inline script. Reading the header makes every page render per request (the previously static `/agentes`, `/glosario` and the 404 page are now dynamic); the site already rendered without streaming, so output order is unchanged.

`style-src` still has `'unsafe-inline'`. The pages use many `style="…"` attributes (React `style` props) and a nonce does not cover style attributes, so removing it would break layout. The only way to drop it is to move every inline style into CSS classes; that is not done. Static assets, icons, `robots.txt` and `sitemap.xml` are excluded from the proxy matcher and carry no CSP (they are not documents).

## Docker

```bash
docker build -t veedor-web --build-arg NEXT_PUBLIC_API_URL=http://localhost:8000/api/v1 .
# optional: --build-arg NEXT_PUBLIC_ALLOW_INDEXING=1 (default 0)
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
