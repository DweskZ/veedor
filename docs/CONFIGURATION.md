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
| `VEEDOR_QUOTES_ENABLED` | `false` | Verbatim quotes from a process's own published text. **Off by default.** Off: `GET /processes/{ocid}/quotes` answers 404 (the same as an unknown route), `POST /processes/{ocid}/ask` attaches no quote and `GET /meta` reports `quotes_enabled: false` (the web hides the block on that flag). On: the mart `process_quotes` and its `quote_lexicon` must be present or the route answers 503. Why it is off and what the screens do and do not guarantee: `docs/QUOTES.md`. In compose: `${VEEDOR_QUOTES_ENABLED:-false}`. |
| `VEEDOR_ASK_ENABLED` | `false` | Switch for `POST /processes/{ocid}/ask` (404 when off). `GET /meta` reports `ask_enabled` and `ask_mode`. |
| `VEEDOR_ASK_DAILY_BUDGET` | `300` | Model calls per UTC day (0 to 1,000,000). **Without `VEEDOR_ASK_USAGE_SHARED`** each worker counts its own share (`budget // VEEDOR_API_WORKERS`, at least 1) in memory: the workers together never exceed the budget, but every restart resets the count, and two API replicas each spend a full budget. **With it** one count in PostgreSQL for every worker and replica, kept across restarts. |
| `VEEDOR_ASK_RATE_PER_MINUTE` / `VEEDOR_ASK_RATE_PER_HOUR` | `4` / `30` | Strict limit per client IP, applied while a model can be called (a model is configured and the daily budget is not 0). It is a cost control. **Without `VEEDOR_ASK_USAGE_SHARED`**: sliding windows in memory, per worker, reset on restart; with `VEEDOR_API_WORKERS` workers a client can make up to workers x the limit. **With it**: fixed one-minute and one-hour buckets per client (stored as a truncated hash of the IP) in PostgreSQL, one count for every worker. A 429 carries `Retry-After` (whole seconds); CORS exposes that header. |
| `VEEDOR_ASK_RETRIEVAL_RATE_PER_MINUTE` / `VEEDOR_ASK_RETRIEVAL_RATE_PER_HOUR` | `20` / `200` | The same limit for retrieval-only answers (no model configured, or `VEEDOR_ASK_DAILY_BUDGET=0`), which cost nothing: a visitor clicking the five suggested questions is not blocked. Same windows, same shared counters (separate buckets), same `Retry-After`. The daily model budget is unchanged. |
| `VEEDOR_ASK_USAGE_SHARED` | `false` (compose: `true`) | Keep the ask budget and the per-client counters in the `ask_usage` table (migration `0003`, atomic `INSERT ... ON CONFLICT DO UPDATE ... WHERE used < limit`). If the database is unreachable the in-memory counters apply for that request, so a database outage never switches a limit off. Rows older than two days are deleted. |
| `VEEDOR_LAKE_THREADS` | `2` | DuckDB threads per API process (1-64). Total CPU use is roughly `VEEDOR_API_WORKERS` x this value. |
| `VEEDOR_API_WORKERS` | `2` | uvicorn worker processes started by `veedor serve` and by the container (1-16). Each worker has its own DuckDB database, `/stats` cache and in-memory rate-limit counters (reviews, dossiers and, unless `VEEDOR_ASK_USAGE_SHARED` is on, `/ask`): the effective in-memory limit is the configured limit times the workers, and a restart resets it. |
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
| Quotes per process / displayed length / similarity floor | 3 / 800 characters / 0.35 | `veedor/use_cases/build_quotes.py` |
| Vocabulary of the quote screen | a capitalised word is institutional only if written capitalised in at least 40 processes of at least 10 buyers and far more often than it appears in natural-person names (ratio 20) | `veedor/domain/quotes/lexicon.py` |
| Process identifier in a path | `ocds-5wno2w-` + 1 to 120 characters of a strict allow-list (letters, digits, `ÑÇÓ`, `. _ - , : + ( ) & º ° ·`, a space, the dashes `– — ‐ ‒ − －`; never a slash, quote, `%` or control character) | `veedor/domain/ocid.py` |
| Stored process text | at most 2,000 characters per text, then cut at a word and flagged `truncated` | `veedor/infrastructure/ocds/texts.py` |

## Common commands

```
veedor lake build-texts    # data/texts/process_texts.parquet (unmasked: never mounted into the API)
veedor quotes build        # data/marts/process_quotes, process_quote_stats, person_name_tokens, quote_lexicon (.parquet)
uv run python scripts/check_quotes_privacy.py   # release gate over the quotes mart (exit 1 on any hit)
scripts/build_data_bundle.sh [--with-quotes]    # quotes are shipped only with the flag, after the gate passes
veedor quotes show <ocid>  # the stored quotes of one process
veedor quotes evaluate     # eval/quotes.json
make db-up         # start PostgreSQL (waits for the healthcheck)
make db-migrate    # alembic upgrade head
make serve         # API on http://127.0.0.1:8000 (docs at /docs)
veedor serve --host 0.0.0.0 --port 8000
```

## Question answering

| Variable | Default | Purpose |
|---|---|---|
| `VEEDOR_ASK_ENABLED` | `false` | Switches `POST /processes/{ocid}/ask` on. Off: 404. |
| `VEEDOR_ASK_DAILY_BUDGET` | `300` | Model calls per UTC day for all workers (each worker counts `budget // workers`). `0` means never call a model. Spent: retrieval-only answers, not errors. |
| `VEEDOR_ASK_RATE_PER_MINUTE` / `VEEDOR_ASK_RATE_PER_HOUR` | `4` / `30` | Strict limit per client IP while a model can be called, per worker process (multiply by `VEEDOR_API_WORKERS`). 429 beyond, with `Retry-After`. |
| `VEEDOR_ASK_RETRIEVAL_RATE_PER_MINUTE` / `VEEDOR_ASK_RETRIEVAL_RATE_PER_HOUR` | `20` / `200` | The generous limit for retrieval-only answers (no model configured, or budget 0), which cost nothing. 429 beyond, with `Retry-After`. |
| `VEEDOR_ASK_MAX_OUTPUT_TOKENS` / `VEEDOR_ASK_TIMEOUT_SECONDS` | `160` / `15` | Hard caps of the one model call per question (no retry). |
| `VEEDOR_LLM_PROVIDER`, `VEEDOR_LLM_MODEL`, `VEEDOR_LLM_API_KEY` | unset | Model mode needs all three. Without them the route answers by retrieval. |

An empty value (what compose passes for `${VAR:-}` when a variable is unset) is read as unset. In compose, `VEEDOR_ASK_ENABLED`, the budget and the three model variables are passed with `${VAR:-}` interpolation; the model variables reach the container only while `VEEDOR_ASK_ENABLED` is set. To switch the route on: `VEEDOR_ASK_ENABLED=true docker compose up -d --no-deps api` (add the model variables to the same shell for model mode). The local embedding model is mounted read-only from `data/models`.

### Cost model

Measured with `gpt-5.4-mini` over 68 model calls (docs/EVALUATION.md): about **991 prompt tokens and 30 completion tokens per call**, one call per question that clears the model floor (questions answered by the screen, the cache or the budget fallback cost nothing). Daily ceiling at the default budget: 300 calls = about 297,000 prompt and 9,000 completion tokens. **Price assumption (not a quoted price; check your provider's list):** USD 1.00 per million prompt tokens and USD 4.00 per million completion tokens gives about USD 0.0010 per call and at most about USD 0.33 per day. Change the budget with `VEEDOR_ASK_DAILY_BUDGET`; the ceiling scales linearly.
