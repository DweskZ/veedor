# Deployment

Veedor is three processes plus read-only data: a FastAPI API, a Next.js web app, PostgreSQL
with pgvector (human reviews and the vector index) and about 200 MB of Parquet files that the API
queries with DuckDB. An optional fourth container provides local observability (OpenTelemetry
collector, trace and metrics stores, Grafana; see `docs/OBSERVABILITY.md`). Investigations are
produced on the host with the CLI and only read by the API. The LLM is optional.

## Prerequisites

- Docker with Compose v2 (developed on Colima, 4 CPU / 6 GB). Image builds need network access.
- For rebuilding data: [uv](https://docs.astral.sh/uv/), Python 3.12, and the SERCOP bulk file
  (about 1.1 GB, see `docs/DATA_SOURCES.md`).
- Free host ports 3000 (web), 8000 (API) and 5433 (PostgreSQL), plus, for the observability
  container, 3001 (Grafana), 4318 (OTLP/HTTP), 9090 (Prometheus) and 3200 (Tempo). All bind to
  127.0.0.1.

## Local stack

```bash
docker compose up -d --build --wait     # or: make up
python3 scripts/smoke_test.py           # or: make smoke
```

| Service | URL | Notes |
|---|---|---|
| web | http://localhost:3000 | Next.js standalone, non-root. `API_INTERNAL_URL=http://api:8000/api/v1` for server-side calls; the browser uses `NEXT_PUBLIC_API_URL` baked in at build time. |
| api | http://localhost:8000 (docs at `/docs`) | Non-root, runs `uvicorn`. Healthcheck: `GET /api/v1/health`. |
| migrate | one-shot | `alembic upgrade head` against `db`; `api` starts only after it succeeds. |
| db | localhost:5433 | `pgvector/pgvector:0.8.7-pg16`, volume `veedor_pgdata`. |

Data mounts of the `api` container: `./data/lake` and `./data/marts` are mounted **read-only**.
Generated dossiers and traces go to the named volumes `veedor_dossiers` and `veedor_traces`
(mounted at `/app/data/dossiers` and `/app/data/traces`), so the lake is never writable. The
dossier cache is not invalidated by a data refresh: remove the volume (`docker volume rm
veedor_veedor_dossiers`) after rebuilding the data.

Other commands: `make down`, `make logs`, `docker compose ps`.

### Image sizes (measured, `docker images`)

| Image | Size | Notes |
|---|---|---|
| `veedor-api:local` | 1.21 GB | The virtualenv is 756 MB: pyarrow 155 MB, scipy 118 MB (+31 MB libs), DuckDB 60 MB, scikit-learn 57 MB, plus the LangChain provider SDKs. scikit-learn and scipy are only needed by `veedor signals build` (anomaly score); moving them to an optional dependency group would shrink the runtime image. |
| `veedor-web:local` | 436 MB | `node:26-slim` + standalone output. |

Both images use pinned base tags that exist (`python:3.12-slim`, `node:26-slim`,
`ghcr.io/astral-sh/uv:0.11.16`), install with `uv sync --frozen` / `pnpm install
--frozen-lockfile`, run as a non-root user (uid 10001 / 1001) and contain no `.env`, data or key.

## Environment variables

Full reference: `docs/CONFIGURATION.md`. The ones that matter for deployment:

| Variable | Service | Purpose |
|---|---|---|
| `VEEDOR_DATA_DIR` | api | Data root. Needs `lake/` and `marts/`. |
| `VEEDOR_DATABASE_URL` | api, migrate | PostgreSQL URL. |
| `POSTGRES_PASSWORD` | db, api | Compose only. The default `veedor_dev` is for local development: **change it** anywhere else. |
| `VEEDOR_CORS_ORIGINS` | api | JSON list of the exact public origins of the web app. |
| `VEEDOR_LLM_PROVIDER`, `VEEDOR_LLM_MODEL`, `VEEDOR_LLM_API_KEY` | CLI only | Not passed to any container: the API always serves template-mode dossiers. Used only by `veedor dossier` on the host, empty by default. Without a provider and model the dossiers use deterministic templates. Inject the key through the host's secret store, never into an image or a compose file. |
| `NEXT_PUBLIC_API_URL`, `NEXT_PUBLIC_SITE_URL` | web (build arg) | Public API base URL and site URL, inlined at build time: changing them means rebuilding the web image. |
| `API_INTERNAL_URL` | web (runtime) | API URL for server-side rendering inside the private network. |

Note: Compose reads a project `.env` file for `${...}` interpolation. LLM variables found there are
not forwarded to any container; they only affect `veedor dossier` commands run on the host.

## Rebuilding the data

Run from the repository root with `uv sync` done. Observed timings are from the development
machine for 2,251,027 processes; steps without a timing were not measured.

| # | Command | What it does | Observed time |
|---|---|---|---|
| 1 | `veedor lake build` | Flattens `data/raw/sercop_ocds_full.jsonl.gz` into `processes`, `tenderers`, `awards` Parquet. | about 1 min |
| 2 | `veedor registries download` then `veedor registries load` | Downloads SRI RUC zips, ghost-company list and Supercias files (official hosts only) and loads the registry tables. | not measured (the SRI zips alone are 607 MB on disk) |
| 3 | `veedor signals build` | Computes signals, scores and supplier profiles into `data/marts/`. | about 5 s |
| 4 | `veedor evaluate backtest`, `coverage`, `report` | Optional evaluation harness, see `docs/EVALUATION.md`. | not measured |
| 5 | `veedor dossier batch --top 20` | Optional: pre-generates dossiers for the highest-risk processes. | not measured |

Then rebuild the bundle (`make bundle`) and restart the API.

## Data bundle

`scripts/build_data_bundle.sh` (`make bundle`) packs only the files the API and the dossier
builder read, found in `infrastructure/lake/reader.py` (7 lake tables, 3 marts) and
`infrastructure/lake/evidence_reader.py`. `data/raw/`, `build_summary.json`, dossiers and traces are
excluded. Output: `dist/veedor-data-<date>.tar.gz` plus a manifest (file, bytes, sha256, rows).

**The bundle contains no quotes.** The quotes marts (`process_quotes`, `process_quote_stats`, `quote_lexicon`)
are shipped only with `scripts/build_data_bundle.sh --with-quotes`, which first runs
`scripts/check_quotes_privacy.py` over the mart and refuses to build (exit 1, nothing written) when any
passage matches a gate rule or the deny-by-default screen would refuse it today. Quotes are also disabled by
default at runtime (`VEEDOR_QUOTES_ENABLED=false`); see `docs/QUOTES.md` for why and for the measured residual.
The table below is the default bundle (without quotes).

Measured on this data:

| File | Bytes | Rows |
|---|---|---|
| lake/processes.parquet | 74,650,373 | 2,251,027 |
| lake/awards.parquet | 41,637,580 | 2,243,116 |
| marts/process_scores.parquet | 29,364,765 | 2,251,027 |
| lake/company_financials.parquet | 25,091,766 | 1,662,983 |
| lake/tenderers.parquet | 17,481,668 | 1,462,452 |
| lake/companies_supercias.parquet | 5,900,159 | 348,162 |
| marts/process_signals.parquet | 1,574,398 | 92,596 |
| marts/supplier_profiles.parquet | 2,776,605 | 90,893 |
| lake/suppliers_sri.parquet | 2,187,572 | 90,888 |
| lake/ghost_companies.parquet | 36,389 | 1,113 |
| **Total** | **200,701,275** | |

The tarball is **197,240,830 bytes (about 188 MiB)**: Parquet is already compressed, so gzip saves
under 2 %. Restore with `tar -xzf veedor-data-<date>.tar.gz -C <data dir>` and verify against the
manifest with `shasum -a 256`.

## Hosting path A: one small VM with Docker Compose

Run the same compose project on one Linux VM behind a reverse proxy (Caddy or nginx) that
terminates TLS and forwards `/` to `web:3000` and `/api/` to `api:8000`.

1. Copy the repository and the data bundle to the VM; extract it into `./data`.
2. Build the web image with the public URLs, for example `NEXT_PUBLIC_API_URL=https://example.org/api/v1`
   (a build arg in `docker-compose.yml`), and set `VEEDOR_CORS_ORIGINS` to the public origin.
3. Remove the host port mappings for `db` and `api` (only the proxy is public), set a strong
   `POSTGRES_PASSWORD`, put LLM variables in the shell or a secret file outside the repository.
4. `docker compose up -d --build --wait`, then run `scripts/smoke_test.py` with `API_URL` and `WEB_URL` pointing at the public URLs.

Trade-offs: simplest and cheapest, one machine to patch and back up (the `veedor_pgdata` volume
holds the only mutable state, the reviews); no redundancy; all services share the VM's memory
(DuckDB scans of a 75 MB `processes.parquet` plus the Python and Node runtimes: size by measuring
`docker stats` under load, which has not been done); the in-process rate limiter is correct here
because there is a single API process.

## Hosting path B: managed pieces

- **API**: any container host that runs a Docker image and can attach about 200 MB of data. Two ways
  to supply data: bake the bundle into a derived image (`COPY` the extracted files; simple, rebuild
  per refresh) or mount a persistent disk or object-store sync at start. Whether a given platform
  offers a disk, its size and its price must be checked in that provider's current documentation
  before choosing; none were verified for this document.
- **PostgreSQL**: a managed instance with the `pgvector` extension available only if embeddings are
  used; the reviews table needs plain PostgreSQL. Set `VEEDOR_DATABASE_URL` and run `alembic upgrade head`
  (the `migrate` command) as a release step.
- **Web**: either the same Node image on a container host, or a Node-capable host. The app uses server
  rendering and `API_INTERNAL_URL`, so a purely static host does not fit.

Trade-offs: less to operate and independent scaling, but three bills and three configuration
surfaces, cross-origin traffic between web and API (`VEEDOR_CORS_ORIGINS` must be exact) and more than
one API replica makes the review rate limiter per replica, so put a shared limit at the gateway.

## Pre-publication checklist

- [ ] **Reviews stay disabled unless needed.** They are off by default (`VEEDOR_REVIEWS_ENABLED=false`). Enabling
      them requires the flag and a bearer token (`VEEDOR_REVIEWS_TOKEN`); there are no per-reviewer accounts,
      so treat the token as a shared secret and rotate it.
- [ ] **Rate limiter is per process** and keyed by client IP (the proxy's IP unless forwarded headers are
      trusted). The read routes are limited per client IP by the API (`VEEDOR_READ_RATE_PER_MINUTE` and
      `VEEDOR_READ_SEARCH_RATE_PER_MINUTE`; the code defaults are off, so set them for a public deployment,
      as `deploy/compose.prod.yml` does), in memory, per worker, reset on restart. Add a gateway-level limit
      for anything shared or distributed; `q` scans can still be expensive within the limit.
- [ ] **TLS** terminated at the proxy; HTTP redirected to HTTPS; the API and `db` ports not exposed publicly.
- [ ] **CORS**: `VEEDOR_CORS_ORIGINS` lists only the real public origins; web built with the final `NEXT_PUBLIC_*` values.
- [ ] **Secrets**: non-default `POSTGRES_PASSWORD`; LLM key only in the host's secret mechanism.
- [ ] **Legal wording**: the product reports risk indicators, not accusations. Natural persons are masked
      at the API boundary (name "Persona natural", RUC first 4 digits); free-text process descriptions are
      returned unchanged and may contain names (see `docs/SECURITY.md`).
- [ ] **Data licences**: SERCOP open contracting data is CC BY 3.0 EC (attribute it). The SRI and
      Supercias pages state no licence (`docs/DATA_SOURCES.md`); that is not a statement that reuse is unrestricted. Confirm before redistributing the bundle or the derived tables.
- [ ] `scripts/smoke_test.py` passes against the public URLs (it writes nothing: it checks that an anonymous review write is refused).
- [ ] Backups of the PostgreSQL volume.

## Monthly data refresh

1. Download the new SERCOP bulk file to `data/raw/sercop_ocds_full.jsonl.gz` (see `docs/DATA_SOURCES.md`).
2. `veedor lake build`, `veedor registries download`, `veedor registries load`, `veedor signals build`.
3. Optional: `veedor evaluate ...` and `veedor dossier batch`; review the diff of `data/marts/build_summary.json` and the evaluation report for unexpected shifts.
4. `make bundle`; check the manifest row counts (processes, scores) against the previous bundle.
5. Ship the bundle to the host, extract it, delete the `veedor_dossiers` volume (cached dossiers are
   per process and would be stale), restart `api`, run `scripts/smoke_test.py` (update `EXPECTED_PROCESSES`).
6. Update the retrieval date in `docs/DATA_SOURCES.md`.

## Performance

What the API does per process (`src/veedor/infrastructure/lake/reader.py`):

- **One DuckDB database per process**, locked down once (allowed directories = lake and marts,
  external access off, configuration locked) with a view over each Parquet file. Each call takes
  a `cursor()` from it (DuckDB's Python client is not safe for one connection shared by threads;
  cursors are the documented per-thread pattern) and closes it. Only a single `SELECT`/`WITH`
  statement is accepted, because the database now outlives a request and a stacked statement
  would persist.
- **Rebuilds are picked up without a restart.** The reader compares the modification time and
  size of every table and of `data/marts/build_summary.json` (at most once per second) and builds
  a fresh database when anything changed. `GET /health` returns `data_built_at`, the UTC time of
  `build_summary.json`.
- **`/stats` is cached in memory per process**, keyed by that file signature, so it is
  recomputed once after each rebuild and never served stale.
- **Threads and workers** are settings: `VEEDOR_LAKE_THREADS` (DuckDB threads per process,
  default 2) and `VEEDOR_API_WORKERS` (uvicorn processes, default 2; the container reads it at
  start). Plan for roughly workers x threads <= CPU count. Each worker has its own database,
  cache and in-memory rate limiters, so the effective rate limit is multiplied by the worker
  count (see `docs/SECURITY.md`). The transient `IOException` retry (one retry, then 503
  `data_unavailable`) is unchanged and now also discards the shared database before retrying.

Measure with `scripts/load_test.py` (standard library only):

```
uv run python scripts/load_test.py --requests 600 --concurrency 8
```

Measured on the local compose stack (Colima VM, 4 CPU, 6 GB, lake and marts bind-mounted from
macOS), same mixed route set, one run each:

| Load | Before (new connection per request, 1 worker) | After (reused database, 2 workers x 2 threads) |
|---|---|---|
| 200 req @ 8 | p50 1.00 s, p95 2.25 s, 7.7 req/s | p50 0.22 s, p95 0.87 s, 25.1 req/s |
| 600 req @ 8 | p50 1.04 s, p95 2.26 s, 7.5 req/s | p50 0.24 s, p95 1.31 s, 22.5 req/s |
| 300 req @ 32 | p50 3.83 s, p95 14.35 s, 6.2 req/s, 44 transport errors | p50 0.86 s, p95 7.40 s, 20.8 req/s, no errors |

Still slow, and why:

- `GET /processes?q=...` scans `process_code` and `main_cpc_description` of the 2.25 M-row `processes`
  table on every call (about 0.2 s on the host, 1.4-8 s in the container under load). It needs
  a precomputed search column or index in the marts to improve; it is not changed here.
- Bind-mounted Parquet reads on macOS are slower than on the host: the same code run directly
  on the host served the same 600-request mix at about 46 req/s against 22 req/s in the
  container. That cost is in Docker's file sharing, not in the code; a Linux host with the data
  on a local disk does not pay it.
- At concurrency 32 on 4 CPUs the queue, not the query, dominates the tail.
- The dossier route is rate limited (30 per minute per IP per process), so load runs see some 429.

## Caching

The API answers cacheable `GET` routes with a weak `ETag` and a `Cache-Control` chosen per route class, and answers `If-None-Match` with `304` before running the route (classes, validator and `Vary` are in `docs/SECURITY.md`, "HTTP caching headers"). Inside the process, every aggregate is memoised per data build (`VersionedCache`); each worker fills the aggregate caches in a background thread when it starts, so the first visitor does not pay about 200 ms for `/stats/by-year` and 170 ms for `/stats/by-region`.

There is no Redis or other cache service, deliberately:

- The data changes only when the lake is rebuilt (monthly). The data build signature is the cache key, so an in-process cache is never stale and needs no invalidation protocol.
- One small server runs one worker (two were stopped for lack of memory at the 768 MiB limit, see `deploy/compose.prod.yml`). Its aggregate cache is rebuilt in about 0.4 s in total; there is nothing to share that is worth a network hop and a service to operate and secure.
- The only state that must be shared between workers or restarts (the per-client and daily ask counters) already lives in PostgreSQL (`VEEDOR_ASK_USAGE_SHARED`).
- Caddy runs without plugins; browsers do the per-user caching.

A shared cache becomes worth it when: several API replicas make the per-process warm-up cost or memory matter; the data changes continuously instead of monthly; the rate limiters of the read routes must be shared (they are per process today); or a CDN is put in front, in which case the same headers apply and the CDN should be configured to honour `Vary: Origin`.
