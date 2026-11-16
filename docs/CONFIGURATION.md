# Configuration

Settings are read from environment variables prefixed `VEEDOR_` (and from a local `.env`, see
`.env.example`). Every setting has a safe default for local development. Source of truth:
`src/veedor/core/settings.py`.

| Variable | Default | Purpose |
|---|---|---|
| `VEEDOR_DATA_DIR` | `<repo>/data` | Root of the data directory. `raw/`, `lake/` (Parquet tables) and `marts/` (signals, scores, supplier profiles) live under it. The API only reads `lake/` and `marts/`. |
| `VEEDOR_DATABASE_URL` | `postgresql+psycopg://veedor:veedor_dev@localhost:5433/veedor` | PostgreSQL (SQLAlchemy URL) for human reviews, dossier cache and embeddings. If unreachable, only the review endpoints answer 503. |
| `VEEDOR_LLM_PROVIDER` | unset | Optional chat-model provider (`openai`, `anthropic`, `groq`). Unset means dossiers use deterministic templates. |
| `VEEDOR_LLM_MODEL` | unset | Model name for the provider above. |
| `VEEDOR_LLM_API_KEY` | unset | API key for the provider. Never commit it. |
| `VEEDOR_REVIEWS_ENABLED` | `false` | Master switch for human reviews. Off: `POST .../reviews` answers 403 `reviews_disabled` and `GET` returns an empty list. |
| `VEEDOR_REVIEWS_TOKEN` | unset | Bearer token required by `POST .../reviews` (constant-time comparison). Unset means posting stays disabled even when the flag is on. Keep it secret; never commit it. |
| `VEEDOR_LAKE_THREADS` | `2` | DuckDB threads per API process (1-64). Total CPU use is roughly `VEEDOR_API_WORKERS` x this value. |
| `VEEDOR_API_WORKERS` | `2` | uvicorn worker processes started by `veedor serve` and by the container (1-16). Each worker has its own DuckDB database, `/stats` cache and rate-limit counters. |
| `VEEDOR_DOCS_ENABLED` | `true` | Serves `/docs` (Swagger UI with pinned, integrity-checked assets) and `/openapi.json`. Set `false` in any shared deployment. |
| `VEEDOR_GLOSSARY_PATH` | `<repo>/web/src/data/glossary.json` | JSON file served by `GET /glossary` (written by the web team; the API only reads it). In compose it is `/app/web/src/data/glossary.json` with `./web/src/data` mounted read-only. A missing or invalid file makes the route answer 503 `glossary_unavailable`. |
| `VEEDOR_CORS_ORIGINS` | `["http://localhost:3000"]` | Allowed browser origins, as a JSON list. No other origin receives CORS headers. |

## Docker Compose

| Variable | Default | Purpose |
|---|---|---|
| `POSTGRES_PASSWORD` | `veedor_dev` | Password of the `veedor` database user (local development default). The `api` service builds its `VEEDOR_DATABASE_URL` from it. |

All three published ports (`db` 5433, `api` 8000, `web` 3000) are bound to `127.0.0.1`. The lake and marts are mounted read-only into `api`; only dossiers and traces are writable.

## Fixed limits (code constants, not settings)

| Limit | Value | Where |
|---|---|---|
| Page size | 1-100, default 25 | `veedor/api/deps.py` |
| Pagination depth | `(page - 1) * page_size` at most 1,000,000 | `veedor/api/deps.py` |
| Dossier cache written from the API | at most 5000 files; beyond that dossiers are served but not kept | `veedor/use_cases/queries/dossier.py` |
| `GET /buyers/search` | `q` 3-60 characters after trimming, `limit` 1-10, up to 10 results | `veedor/api/v1/buyers.py` |
| `GET /processes/random` pools | at most 32 pools of 1,000 sampled rows; an empty combination is retried after 30 s | `veedor/use_cases/queries/random_process.py` |
| Process-context cache | at most 256 method-year groups and 6,000,000 stored values | `veedor/use_cases/queries/process_context.py` |
| Glossary file | at most 512 KiB, 400 entries, term 100 / definition 1500 / source 300 characters | `veedor/infrastructure/glossary.py` |
| Request body | 16 KiB | `veedor/api/security.py` |
| `POST .../reviews` rate | 30 per minute per client IP, per process | `veedor/api/security.py` |
| Review note / reviewer length | 2000 / 120 characters | `veedor/schemas/reviews.py` |
| Database connect timeout | 3 s | `veedor/infrastructure/db/session.py` |
| `GET /processes?min_amount=&max_amount=` | finite numbers from 0 to 1e12; minimum above maximum is 422 | `veedor/api/params.py` |
| Quotes per process / displayed length / similarity floor | 3 / 600 characters / 0.35 | `veedor/use_cases/build_quotes.py` |
| Stored process text | at most 2,000 characters per text, then cut at a word and flagged `truncated` | `veedor/infrastructure/ocds/texts.py` |

## Common commands

```
veedor lake build-texts    # data/texts/process_texts.parquet (unmasked: never mounted into the API)
veedor quotes build        # data/marts/process_quotes.parquet, process_quote_stats.parquet, person_name_tokens.parquet
veedor quotes show <ocid>  # the stored quotes of one process
veedor quotes evaluate     # eval/quotes.json
make db-up         # start PostgreSQL (waits for the healthcheck)
make db-migrate    # alembic upgrade head
make serve         # API on http://127.0.0.1:8000 (docs at /docs)
veedor serve --host 0.0.0.0 --port 8000
```
