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

## Quotes, provenance and the amount filter

All three are `GET`, unauthenticated, masked like every other response and answer only 200, 404, 422 or 503. Details of the quote pipeline and its measurements are in `docs/QUOTES.md`.

**Quotes are off by default (`VEEDOR_QUOTES_ENABLED=false`): the route is a plain 404, `/ask` attaches no quote, `/meta` reports `quotes_enabled: false`, and the data bundle ships no quotes table unless it is built with `--with-quotes` after the release gate (`scripts/check_quotes_privacy.py`) passes.** The fifth independent review found natural persons named in the stored quotes; the earlier claim ("about 2 in 110,000 passages") is withdrawn. What is claimed now is a measured upper bound from a sample read by hand, in `docs/QUOTES.md`, not that persons never appear.

| Route | Controls | Tests |
|---|---|---|
| `GET /processes/{ocid}/quotes` | Same strict `ocid` pattern. Reads two bound `SELECT ... WHERE ocid = ?` statements (stored quotes and per-process counts), never a table scan, cached per data build. The quotes were screened when the mart was built (`veedor quotes build`) and every stored passage is screened **again** here with the process's current person names: names of natural-person and RUC-less parties and of natural-person enquiry askers, honorifics (any case), natural-person RUCs and valid cédulas in any written form, e-mail addresses, telephone numbers, signatures, salutations, accusation and inference wording (also hidden by look-alike characters, digits or separators), links, markup and instruction-like text. Since review 5 the boundary also runs the **deny-by-default screen** (`domain/quotes/strict.py`: no sign-off or first-person cue, no title followed by a name, no credential or plate or long number, no person-name token in any case, no capitalised word the lexicon `quote_lexicon` does not show to be institutional) and the third-party allegation stems (`domain/quotes/allegation.py`); a mart without `quote_lexicon` is refused with a 503, never served unscreened. A passage that fails is dropped and counted in `omitted`; it is never rewritten, so no quote contains a placeholder. The mart is the only source: the unmasked `process_texts` table is not readable by the API reader and its folder is not mounted. | `tests/api/test_api_quotes.py`, `tests/domain/test_quotes_screen.py`, `tests/test_deployment_data_boundaries.py` |
| `GET /processes/{ocid}/provenance` | Same strict `ocid` pattern. Every value is built from the validated, masked detail models (`ProcessDetail`), the whole payload goes through `MaskedModel` again, and registry facts are looked up only for a company or public-entity winner with a real RUC (never for a natural person or an unidentified party). Signal inputs are shown as numbers, flags and dates only; no string from the evidence (names, RUCs) is copied. A test fails when a field of the detail response has no catalogue entry. | `tests/api/test_api_provenance.py` |
| `GET /processes?min_amount=&max_amount=` | Finite numbers from 0 to 1e12 (`nan`, `inf`, negatives and text are 422), `min_amount` above `max_amount` is 422. Both are bound parameters on `award_total`; a process without an amount matches neither bound. | `tests/api/test_api_provenance.py` (amount filter), `tests/api/test_api_security.py` |

## Residual limits

- Quotes are text written by third parties and shown verbatim, and they are **disabled by default**. The screens are heuristics with a non-zero residual that was measured by reading a sample, not proven (the bound is in `docs/QUOTES.md`). A person named in lower case with a rare name that is neither in the person-name vocabulary nor next to any cue can still pass; so can a person described without a name. The unmasked text table is `data/texts/process_texts.parquet`: never publish or mount it.
- Free-text name masking is heuristic. A person who is not a party of the process and has no honorific can still appear in a description shown by the process detail endpoint.
- The forbidden-wording list is a safety net, not a guarantee. New phrasings will pass until they are added to the vocabulary.
- Reviews use one shared bearer token, not per-user identities. Failed token attempts are not rate limited separately.
- **Rate limits and the ask budget, stated exactly.** The review and dossier limiters are in memory, per worker process, and reset on restart: with `VEEDOR_API_WORKERS` = N a client can make up to N times the configured number of requests, a restart gives a fresh count, and two API replicas count separately. The question route (`/ask`) is the same by default (sliding windows per client IP per worker; a daily budget of `VEEDOR_ASK_DAILY_BUDGET // workers` model calls per worker, so the workers together never exceed it, but a restart resets it and each replica has its own budget). With `VEEDOR_ASK_USAGE_SHARED=true` (set in `docker-compose.yml`) the ask budget and the per-client counters live in PostgreSQL (table `ask_usage`, migration 0003): one atomic `INSERT ... ON CONFLICT DO UPDATE ... WHERE used < limit` per counted request, shared by every worker and replica and kept across restarts; the client is stored as a truncated SHA-256 of its IP and rows are deleted after two days. The shared per-client windows are fixed one-minute and one-hour buckets (a burst at a bucket boundary can reach twice the limit for a moment). If the database is unreachable the in-memory counters apply for that request, so an outage never switches a limit off. A 429 from `/ask` carries `Retry-After` (whole seconds) and CORS exposes the header. Behind a proxy the client IP is the proxy's unless forwarded headers are trusted. Dossier and review limits are not shared.

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

## Question answering (`POST /processes/{ocid}/ask`)

The one route allowed to reach a language model. Everything else in this file still holds: no other route can construct or call a model client (`tests/api/test_ask_boundary.py` checks it twice: no other module of `veedor/api` imports a model adapter, and every other route is called with every model entry point replaced by a spy that stays untouched). The route is **off by default** (`VEEDOR_ASK_ENABLED=false`): disabled, it answers the same 404 as an unknown route, before any validation. Enabled without a key, or with the daily budget spent, it answers by retrieval only (200, `mode: "retrieval"`), never with an error.

| Threat | Control | Residual limit |
|---|---|---|
| Prompt injection in the question | The model never writes text: it returns JSON with `answerable`, `fact_ids` (an enumeration of the candidate ids, enforced by the provider's structured output and validated again with pydantic, strict, no extra keys) and a `reason` from a closed list. The answer is made only of fixed sentences, the dossier renderer's sentences for those ids, and stored quotes. The question travels as a JSON string inside a data block with `<` and `>` escaped. Instruction-like text, links, markup, look-alike alphabets and payload symbols are refused before retrieval with a fixed sentence. | The screen is a heuristic list; a well-disguised instruction can reach the model. It can then only choose real ids of this process (counted as discarded when outside the set), so the worst outcome is a true but irrelevant fact. |
| Exfiltration | The model sees only fact sentences (with every « » span replaced by a marker, because it is data text) and the question: never quotes, never tool results, never another process, never a prompt of ours in the answer. Natural-person facts never enter the pack; a sentence holding an identifier is dropped; the response is masked again at the boundary. | A fact sentence is sent to the provider (a third party) when a model is configured. |
| Judgements and requests about people | Questions asking whether someone did wrong, who is to blame, or for a name, identity number, contact or position get a fixed sentence, whatever the evidence holds. | Wording the lists do not know goes to retrieval, which can only return facts of the process. The lists (`domain/qa/slang.py`) cover formal accusation words, Ecuadorian and Latin American slang and euphemisms (coima, mordida, chanchullo, tongo, negociado, mano negra, amarre, palanca, compadrazgo, trinca, diezmo, testaferro, "a dedo", arreglado, amañado...), English, opinion requests and hidden-instruction wordings; they were extended after a first held-out set exposed misses, so that set's adversarial subset is no longer unseen (docs/EVALUATION.md). A request to compare with similar processes is not a judgement. |
| Cost abuse | Per-IP limits (strict while a model can be called: default 4 per minute and 30 per hour; generous for retrieval-only answers, which cost nothing: 20 per minute and 200 per hour; both keep `Retry-After`), a global daily model budget (default 300 calls; shared in PostgreSQL when `VEEDOR_ASK_USAGE_SHARED` is on, else each worker counts its share so the total never exceeds it, and a restart resets it), one model call per question, an output cap (160 tokens), a request timeout (15 s) and no automatic retry, a 300-character question, a 16 KiB body, an in-memory answer cache keyed by (process, normalised question, data build). A model failure or an invalid reply falls back to retrieval. | Without the shared counters the limits are per worker process and in memory: with `VEEDOR_API_WORKERS` workers the per-IP limit is multiplied by the workers; a restart resets them (see "Residual limits"). Behind a proxy the client IP is the proxy's unless forwarded headers are trusted. |
| The question as data | Never stored or logged in clear: the only record is a log line with a salted hash (the salt is random per process, so hashes cannot be linked across restarts), the length and the outcome. It is never a span attribute or a metric label (`allowlist.py` has no key for it). The answer cache holds the normalised question in memory only. The 422 for a malformed question never repeats it. | Anything between the client and the API (proxy logs, access logs of a gateway) is outside this control. |
| Wrong answers | Retrieval ranks by embedding similarity with a floor measured on a tuning half (docs/EVALUATION.md). The grounding verifier runs on every answer; a failure returns the fixed "no disponible" sentence and is counted. | Similarity is not relevance: the retrieval-only recall and precision are in docs/EVALUATION.md and are not perfect. |

Tests: `tests/qa/` (screening, selection with a scripted model returning valid ids, out-of-set ids, malformed JSON, prose, an injected instruction, judgement questions, budget fallback, cache, the question never in logs), `tests/api/test_api_ask.py` (404 when disabled, retrieval answer, rate limit, budget fallback, masking of a natural-person process, injection payloads in path and body, no question in logs or spans) and `tests/api/test_ask_boundary.py`.

## Name vocabulary (`person_name_tokens.parquet`)

A vocabulary of person-name tokens derived from the names of natural persons in the lake: **single lower-case tokens only** (6,992 rows), each present in the names of at least two distinct natural persons and not an ordinary word (written in lower case in fewer than 20 times as many processes as there are such names). It holds no full name and no link to a process or a RUC. Review 5 showed that the earlier definition ("not used in lower case by the texts") dropped exactly the commonest given names and surnames, because people type them in lower case; the vocabulary is now relative to how many persons carry the name, and it applies in any case (`strict_name_token`). It is used at **build time** of the quotes (`veedor quotes build`) and, where the table is present, at the API boundary. The API treats the table as optional (without it the boundary still applies every other rule, including the lexicon, which needs no vocabulary) and **the public data bundle does not ship it** (`scripts/build_data_bundle.sh`). It stays in `data/marts` for the local stack.

## Quotes: lexicon, release gate, deny list and display

`quote_lexicon.parquet` holds the institutional capitalised words and the ordinary lower-case words that the deny-by-default screen admits (built from the texts, with person-name tokens excluded by construction; no name in it). It is shipped with the quotes (only with `--with-quotes`). `scripts/check_quotes_privacy.py` is the release gate: it fails (exit 1) when any stored passage matches one of the reviewer's seven rules or this project's own rules (`domain/quotes/gate.py`) or when the boundary function would refuse it today with the real protected names from the lake; a missing mart, lexicon or lake is a failure too. `scripts/build_data_bundle.sh --with-quotes` runs it first and refuses to build when it fails; without the flag no quotes table is staged. `tests/test_quotes_release_gate.py` runs it as a test when the real mart is present.

`domain/quotes/deny.py` keeps SHA-256 hashes of passages that a human review found to name a person who is not a party of the process and that no pattern catches without removing legitimate text (a list of shareholders, administrators named in a request, an official in an address block, a trainer named in a letter). It holds hashes only, never a name. A name followed by an official title in capitals ("Nombre Apellido SECRETARIO …") is dropped by pattern. A passage is shown whole when it has at most 800 characters; a longer one is cut at the end of a sentence (else a clause, else a word) and flagged `truncated`; the text screened is the whole passage, so a cut never hides a screened-out remainder.
