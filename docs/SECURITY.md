# API security

## Threat model

Veedor's API is a read-mostly service over public procurement data. It is meant to run behind a
trusted frontend, today without user accounts. Threats considered:

- Injection through request parameters (SQL in DuckDB and PostgreSQL, wildcard abuse, path traversal).
- Disclosure of natural persons (names and full RUCs) and of server internals (stack traces, SQL).
- Reading files outside the data directory through the query engine.
- Abuse of the only write endpoint (`POST /processes/{ocid}/reviews`): flooding, oversized bodies, stored script content.
- Cross-origin use from untrusted sites.

## What is defended, and how

| Concern | Control | Tests |
|---|---|---|
| SQL injection | All values are bound parameters (DuckDB `?`, SQLAlchemy ORM). The only variable SQL text is the sort column and direction, taken from a closed mapping to constant fragments; `LIMIT`/`OFFSET` are bound. | `tests/api/test_api_security.py`, `tests/use_cases/queries/test_queries_read_side.py` |
| Input validation | Path `ocid` must match `^ocds-5wno2w-[A-Za-z0-9._\-]{1,120}$`; `ruc` and `buyer_ruc` `^\d{13}$`; `year` 2000-2100; `signal` must be a catalogue code; `method` limited to a safe character set (it is not checked against the list of existing methods); `q` up to 80 characters; `sort` pattern plus whitelist; pagination bounded (page >= 1, page_size <= 100). Invalid input returns 422. | same |
| LIKE wildcards | `q` is escaped (`%`, `_`, and the escape character) and bound; a literal `%` matches nothing. | `test_wildcard_abuse_in_q_matches_nothing` |
| File and network access from DuckDB | Each worker process holds one in-memory database containing only views over the known Parquet files; every request takes its own cursor and may run exactly one `SELECT` statement, so nothing a request does persists for the next one. `allowed_directories` is restricted to the lake and marts directories, `enable_external_access=false` and `lock_configuration=true` are set, and only `SELECT`/`WITH` statements are accepted. | `test_reader_blocks_files_outside_the_lake` |
| Natural persons | Masking is applied in the response models (`MaskedModel`), so every serialised response is masked, including nested winners, tenderers, awards, top suppliers, signal evidence and dossiers. Names become "Persona natural"; RUCs keep four digits. | `tests/domain/test_masking.py`, `tests/api/test_api_masking.py` |
| Error leakage | One error model `{"error": {"code", "message"}}`. Unexpected exceptions return a generic 500; details go to the server log only. | `test_unexpected_errors_do_not_leak_details` |
| Stored content | Review `note` (max 2000 chars) and `reviewer` (max 120) are stored as plain text and returned as JSON strings; the frontend must render them as text, never as HTML. `status` is an enum. | `tests/api/test_api_reviews.py` |
| Browser hardening | CORS limited to `VEEDOR_CORS_ORIGINS`; `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, `Cache-Control: no-store` and a restrictive `Content-Security-Policy` on API responses (the interactive docs pages are exempt from the last two). | `test_security_headers_present`, `test_cors_only_allows_configured_origin` |
| Resource abuse | Request bodies above 16 KiB are rejected with 413. `POST` reviews are limited to 30 per minute per client IP. | `test_oversized_body_is_rejected`, `test_review_post_is_rate_limited` |

## Independent review (phase 3): findings and status

An independent review broke the masking claim above and found API defects. Status of each item:

| Finding | Status |
|---|---|
| HIGH: natural persons leaked through free text (a name and RUC or cédula inside `description`). | Fixed. `mask_free_text` (`domain/masking.py`) masks natural-person RUCs, check-digit-valid cédulas (and any 10 digits after "CC", "C.I.", "CÉDULA", "RUC/PASAPORTE"...), the known names of the process's natural-person parties (case, accent and word-order tolerant) and honorific-plus-name runs. A description is withheld (`description: null`, `description_withheld: true`) when a party is masked or masking finds anything. Applied to descriptions, CPC text, dossier text and review notes. |
| HIGH: parties with no RUC were never masked. | Fixed. Without a usable RUC the name is masked ("Persona natural o sin identificar") unless it carries an allow-listed legal-entity marker (S.A., CIA. LTDA., EP, CONSORCIO, FUNDACIÓN, UNIVERSIDAD, GAD, MINISTERIO, HOSPITAL ...). Default is to mask. |
| MEDIUM: `/suppliers/{ruc}` was an oracle for natural persons. | Fixed. Natural-person RUCs return the same 404 as an unknown RUC. |
| `q` could find a process by a person's name through the description. | Fixed. Search covers only ocid, process code, buyer name and CPC description. |
| HIGH: dossier endpoint returned 500. | Fixed on the API side: any builder exception is a controlled 503 `dossier_unavailable`, logged server-side. The root cause is owned by the dossier code. |
| MEDIUM: anonymous callers could trigger paid LLM calls and unbounded cache writes. | Fixed. The API always builds template-mode dossiers; LLM dossiers come only from the CLI. API-built dossiers stop being kept once 5000 files exist. |
| MEDIUM: reviews were open to anyone, accepted NUL bytes and wrongdoing wording. | Fixed. Disabled by default; writing needs `VEEDOR_REVIEWS_ENABLED=true` and a bearer token; the process must exist; control characters are stripped; notes and reviewer pass the forbidden-wording check (422) and `mask_free_text`. `GET /meta` exposes `reviews_enabled`. |
| MEDIUM: huge `page` values caused 500s (INT64 overflow). | Fixed. `page` and `page * page_size` are bounded; 422. |
| MEDIUM: PostgreSQL published on all interfaces with a default password. | Fixed. db, api and web ports are bound to `127.0.0.1`. |
| LOW: `\d` accepted Unicode digits; redirect built from the Host header; docs loaded unpinned CDN assets; CI had default token permissions. | Fixed. `[0-9]`; redirects disabled; `/docs` pins swagger-ui-dist 5.17.14 with SRI (ReDoc removed) and can be switched off with `VEEDOR_DOCS_ENABLED`; CI has `permissions: contents: read`. |
| Test data in the reviews table. | Removed. |

## Second independent review (phase 4)

The second review swept 1,640 processes and found 0 personal-data leaks, confirming the phase 3 fixes (free-text masking, parties without a RUC, supplier oracle, reviews switched off by default, bounded pages, loopback ports). It found the items below; all are fixed and tested.

| Finding | Fix |
|---|---|
| Over-masking: the honorific rule garbled entity names in dossiers ("HOSPITAL DR. GUSTAVO DOMINGUEZ Z."). | `mask_free_text` takes `protected_names` (the process's buyer, company and public-entity names) and never rewrites text inside them; the dossier path passes them and shows the same names as the process detail. |
| Transient DuckDB `IOException` ("Permission denied") during bursts surfaced as 500. | The reader retries once after a short backoff, then answers 503 `data_unavailable`. |
| Review wording filter was weaker than the dossier verifier (Cyrillic, fullwidth, combining, leet variants, "robaron"). | Uses the dossier's `canonical` form and `FORBIDDEN_PATTERN`, plus a digit/symbol look-alike pass and a small list of verb forms the dossier vocabulary lacks (to be moved there). Notes and reviewer are also masked with the process's known person names. |
| Authorization scheme parsing was loose; the rate limiter ran before authentication. | Only `Bearer <token>` is accepted (scheme case-insensitive, exactly one space). Authentication runs first, so anonymous clients cannot exhaust the rate-limit bucket. |
| Natural-person buyers: `/buyers/{ruc}` returned a profile; `q` and `sort=buyer_name` used raw names. | 404 like an unknown buyer; the `buyer_ruc` filter returns nothing; `q` skips natural-person buyer names and name sorting treats them as unknown. |
| Natural-person winners exposed a behavioural profile in `winner`. | Natural persons and unidentified parties return only `ruc`, `name` (masked) and `kind`. |
| Dossier endpoint had no rate limit and wrote an investigator trace per uncached build. | 30 requests per minute per IP (in memory, per process); the API builds with `write_traces=False`. |

## Stage 3 read endpoints (aggregates, random process, buyer search, context, glossary)

All are `GET`, unauthenticated, masked like every other response, and answer only 200, 404, 422 or 503.

| Route | Controls | Tests |
|---|---|---|
| `GET /processes?region=` | Closed enumeration of the 24 province keys plus `SIN_REGION`; anything else is 422. The key is mapped to the exact raw `buyer_region` strings found in the lake (read once per data build) and bound as parameters; no text of the request reaches SQL. | `test_api_new_endpoints_security.py`, `test_api_stats_aggregates.py` |
| `GET /processes/random` | `with_signals` is a boolean, `min_score` a number 0-100 (422 otherwise). Candidates are only processes whose identifier matches the path pattern, whose winner has a 13-digit RUC with third digit 9 or 6 and whose buyer is not a natural person; so natural-person and RUC-less winners are never returned. Uniform choice from bounded in-memory pools of random samples (`secrets`), at most 32 pools of 1,000 rows, keyed by the data build. A warm call does no database work; a combination with no match is not rescanned for 30 s. `Cache-Control: no-store`. | `test_api_random_search_context.py` |
| `GET /buyers/search` | `q` is trimmed, 3-60 characters, no control, format, surrogate or private-use characters (422). Matching is done in Python over an in-memory table (one row per buyer RUC): `%`, `_` and `\` are ordinary punctuation, no SQL `LIKE` is built from user text. Natural-person buyers (RUC third digit 0-5) and RUCs the API would reject are not in the table. `limit` 1-10. | same |
| `GET /processes/{ocid}/context` | Same strict `ocid` pattern. Returns counts, quartiles and percentiles of the process's own method and year only; it carries no name, no RUC and no free text. Groups are computed once per method-year and cached with a size bound. | same |
| `GET /stats/by-region`, `/stats/by-year` | No parameters. One aggregate query each, cached per data build. Natural-person buyers appear only as counts inside a province total. | `test_api_stats_aggregates.py` |
| `GET /glossary` | Serves one repository file (`VEEDOR_GLOSSARY_PATH`, mounted read-only in compose). The file is treated as untrusted: at most 512 KiB and 400 entries, strict types and lengths (term 100, alias 100 x 20, definition 1500, source 300), no control characters, unique terms, unknown keys dropped. Any violation, or a missing file, is a 503 `glossary_unavailable` with a generic message (the path is never echoed). | `test_api_glossary.py` |

Every statement these routes send to DuckDB is a single `SELECT` (`test_every_new_query_is_exactly_one_select`); the lockdown of the shared database is unchanged. Rate limiting is not applied: the routes are cheap after warm-up (see "Measured cost" below) and the aggregates are memoised.

### Measured cost

Real lake (2.25 M processes), two uvicorn workers with two DuckDB threads each, local container. Cold = first call of a worker after a data build; warm = later calls.

| Route | Cold | Warm |
|---|---|---|
| `/stats/by-region` | 0.20-0.25 s | 2 ms |
| `/stats/by-year` | 0.15 s | 2 ms |
| `/processes/random` (any / with signals) | 0.03-0.17 s (one sample scan per filter combination) | 1-5 ms |
| `/buyers/search` | 0.07 s (builds the buyer table once) | 5 ms |
| `/processes/{ocid}/context` | 0.03 s per new method-year group | 12 ms |
| `/processes?region=MANABI` / `SIN_REGION` | not cached (a join per request) | 72 ms / 180 ms |

200 requests at concurrency 8 over a mix of the new routes: 183 requests per second, p50 7 ms, p95 126 ms, no errors. 1,000 requests at concurrency 8 over only random and search: 590 requests per second, p95 19 ms, no errors.

## Residual limits

- Free-text name masking is heuristic. A person who is not a party of the process and has no honorific can still appear in a description shown by the process detail endpoint.
- The forbidden-wording list is a safety net, not a guarantee. New phrasings will pass until they are added to the vocabulary.
- Reviews use one shared bearer token, not per-user identities. Failed token attempts are not rate limited separately.
- All rate limits (reviews, dossier) are in memory and per process; a multi-instance deployment needs a shared limiter. With `VEEDOR_API_WORKERS` > 1 each worker counts separately, so the effective limit is the configured limit multiplied by the number of workers.

## Not covered yet

- **User authentication.** Reads are anonymous. Writing reviews needs one shared bearer token, not per-user identities; `reviewer` is a free-text label, not an identity. Do not expose the API to the internet before adding real authentication.
- **Free-text masking is heuristic.** A person's name is masked only when it is a known party of the process or follows an honorific; a name that is neither can still appear in a process description returned by the detail endpoint or in a review note. Dossiers do not quote free-text descriptions at all, so this does not apply to dossier text.
- **The data bundle contains unmasked personal data.** `data/` (lake, marts, registries, dossier cache) holds real names, RUCs and cédulas. Masking exists only at the API boundary: never publish or share the data directory or the Parquet files as-is.
- **Shared rate limiting.** The limiter is in memory and per process: each worker or replica counts separately and a restart resets it. Behind a proxy the client IP is the proxy's unless forwarded headers are trusted. A real deployment needs a shared limiter (for example at the gateway or in Redis).
- TLS termination, secrets management and database credentials rotation (the compose password is a local-development default).
- Rate limiting of read endpoints; `q` searches over the full lake can be expensive. The stage-3 routes are cached or in-memory (see above) and are not rate limited.
- `GET /processes/random` samples a bounded pool, so within one pool lifetime at most 1,000 distinct processes are served per filter combination; every matching process has the same probability per call and pools are redrawn independently when exhausted.

## Reporting an issue

Report vulnerabilities privately to the repository maintainers (use the repository's private security advisory channel, or contact the maintainer directly). Do not open a public issue with exploit details. Include the endpoint, the request, and the observed response.
