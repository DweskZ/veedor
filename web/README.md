# Veedor web

Next.js 16 (App Router, TypeScript, Tailwind 4) dashboard for the Veedor API. Brand and design tokens: `../docs/BRAND.md`.

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

## Notes
- Real mode never shows mock data: when the API fails, pages show an explicit error state.
- Filters on `/procesos` live in the URL (`year`, `method`, `signal`, `min_score`, `q`, `sort`, `page`); `sort=-risk_score` means descending.
