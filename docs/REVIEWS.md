# Independent reviews

Five adversarial, read-only reviews were run against the code and the running local stack on
2026-11-16. Each reviewer started without knowledge of the codebase, was told the project's
claims, and was asked to break them. Reviewers could run tests, call the API, and query the
data, but could not modify the repository.

This file records what they found. Personal names and identifiers that appeared in the
reviewers' reproductions are deliberately not repeated here.

## Review 1 — after the first complete build

Every automated test was passing when this review started.

### Claims that held

- **SQL injection.** Forty payloads across all nine query parameters and the path parameters
  (quotes, `UNION`, stacked statements, `LIKE` wildcards, NUL bytes, 100k-character values,
  encoded variants, huge integers). No behavioural change and no leak. Sort columns come from a
  closed mapping; no SQL is built from request-derived values.
- **DuckDB lockdown (API reader).** Nineteen attempts to read files or URLs outside the lake
  and marts folders, to write files, or to re-enable external access were refused.
- **Secrets.** None found in source, tests, docs, CI, scripts, or images.
- **Indicator arithmetic.** The fired signals of three processes were re-derived by hand from
  the lake tables and matched the evidence shown.

### Claims that were broken

| Id | Severity | Finding |
|---|---|---|
| H1 | High | Natural persons' names, RUCs and 10-digit cédulas appeared inside free-text process descriptions returned by the API, quoted in dossiers and rendered by the web. 205 processes had the winner's own name in the description. |
| H2 | High | Parties with no RUC were never masked. 33,127 processes had a winner name and no RUC; a person's full name was shown as winner, tenderer and award supplier. |
| H3 | High | The dossier endpoint returned HTTP 500 for roughly 3,900 processes whose buyer or place names contain a forbidden word (for example an anti-crime unit) or a number written as a word. |
| H4 | High | The grounding verifier accepted accusatory or false prose that contained no numbers or capitalised names: synonyms outside the word list, Unicode evasions (zero-width characters, homoglyphs, fullwidth letters), unsupported causal claims, wrong dates, numbers attached to the wrong noun. |
| H5 | High | Hostile source text could be quoted verbatim inside a dossier. No such text exists in the real data, but the path was open. |
| M1 | Medium | Review writes were unauthenticated, accepted for non-existent processes, stored and displayed without masking or wording checks. |
| M2 | Medium | A NUL byte in a review note caused HTTP 500. |
| M3 | Medium | An unbounded `page` value caused HTTP 500 (integer overflow). |
| M4 | Medium | The supplier endpoint, called with a natural person's RUC, revealed registry status and totals for that person. A registry listing dated after the award still added its full weight to the score. |
| M5 | Medium | PostgreSQL was published on all interfaces with a default password. |
| M6 | Medium | The evidence reader's DuckDB connection was not locked down like the API reader's. |
| M7 | Medium | The dossier endpoint was unauthenticated, wrote one file per request, and ran in a container that held an LLM API key; with one more variable set, anonymous requests could have triggered paid model calls. |

Low-severity items: path patterns accepting Unicode digits, a redirect built from the `Host`
header, documentation assets loaded from a CDN without integrity hashes, no security headers on
the web app, unknown web routes returning 200, and CI actions without a `permissions` block.

### What changed in response

- Masking was extended to free text (descriptions are withheld when they contain personal
  identifiers), to 10-digit cédulas, and to parties without a RUC (masked unless the name
  carries a legal-entity marker). Supplier pages for natural persons return 404.
- **The language model no longer writes prose.** It returns a plan: which facts to include, in
  what order, and at most one connective and one reviewer note per section, all chosen from
  enumerated lists. Code renders every sentence. The verifier remains as a second net.
- The HTTP API never calls a language model, and no model credential is passed to any
  container. Model-assisted dossiers are produced only from the command line.
- Reviews are disabled by default; enabling them requires a flag and a bearer token.
- All services bind to `127.0.0.1`. Inputs are bounded and validated; control characters are
  stripped.
- A registry listing dated after the process is shown as context and carries no weight.

## Review 2 — after the fixes

A different reviewer re-tested every item above, tried to bypass each fix, and looked for
regressions.

### Confirmed fixed

H1, H2, H3, H5 (for the listed vocabulary), M2, M3, M4 (suppliers), M5, M6, and the model part
of M7.

Privacy sweep: 1,640 processes (natural-person winners, winners without RUC, descriptions
containing identity-number patterns or honorifics, natural-person tenderers, and a random
sample), detail and dossier for each — 3,280 responses. Result: **0** leaked names (two or more
consecutive name tokens), **0** unmasked natural-person RUCs, **0** valid cédulas. Twenty web
pages were fetched and their page source checked: 0 leaks.

Dossier robustness: 522 further processes, including long names, quotes, non-ASCII characters
and forbidden or number words in names — every dossier was returned and passed verification.

Context signals: for all 2,251,027 processes, `n_signals` equals the number of risk signals and
`risk_score` equals the capped sum of their weights; context rows contribute nothing.

Plan-based generation: unknown identifiers, non-string types, extra fields, Unicode
identifiers, a second connective, unknown sections and invalid reviewer notes were all rejected
and ended in the deterministic template.

### Still open at the time of review 2

| Severity | Finding |
|---|---|
| Medium | Over-masking: the honorific rule was applied to buyer and company names, so a hospital named after a doctor was rendered with a placeholder in 6.1 % of sampled dossiers. |
| Medium | A burst of transient DuckDB "cannot open file" errors (7.7 % of requests during about one minute) surfaced as HTTP 500; retries succeeded and the cause was not reproduced. |
| Medium | With reviews enabled, the wording filter used a weaker normalisation than the dossier verifier, and a person's name without an honorific could be stored. |
| Medium | The text verifier is a word list: 35 of 82 fresh evasions passed it (hyphenation, digit substitution, spacing, uncommon synonyms). After the change to plan-based generation this list is a safety net, not the control. |
| Low | One natural-person buyer was still retrievable; natural-person winners exposed aggregate figures; a connective phrase always failed verification; a deeply nested model reply raised an uncaught error; reviewer notes were not conditional on the evidence; the dossier cache was not versioned; dossier requests were not rate limited; some web paths returned a soft 404. |

These items were addressed after review 2. That last round was verified by the project's own
tests and sweeps, not by a third independent review — treat it accordingly.

## Review 3 — stage 2 (investigation agents, vector search, observability)

Run before anything in stage 2 was reported as working. The reviewer ran its own live
investigations against the real EcuDataMCP server, re-derived facts from primary sources,
attacked the tool path with a hostile fake server, and tried to push the agents past their
budgets. The team's own check at that point was a batch of 20 live investigations, all
successful.

### What held

- **Facts.** Every investigation fact of six processes was re-derived from the registry tools
  and the lake: incorporation dates and day counts, subscribed capital and its ratio to the
  award, prior and total awards between buyer and supplier, and the similar-purchase counts and
  amounts. All matched.
- **Privacy.** Legal-representative names, street names and phone numbers returned by the
  registry for 14 companies were searched for in 35 stored investigations, traces, CLI output at
  default and debug level, 60 API responses, 15 web pages, trace spans and metric labels: 0 hits.
- **Tool-result injection.** A fake server placed instruction text, URLs, markup and a fake
  representative name in every string field of every tool, with a scripted model that obeyed.
  Nothing reached a stored record, a dossier, a model prompt or a tool argument. Records for a
  different RUC than requested were rejected.
- **Agent control.** Unknown specialist names, repeated dispatches, a 100,000-item list and
  malformed replies never pushed a run past 6 dispatches, 2 per specialist or 4 tool calls per
  specialist; the deterministic policy took over each time. No HTTP route can start an
  investigation.
- **Vector search.** The published retrieval figures were reproduced within noise.

### What was broken

| Severity | Finding |
|---|---|
| High | One of the reviewer's 15 live investigations ended in a traceback, and 7 of 80 in an offline sample: the privacy scan matched digits inside floating-point artefacts and aborted the run. The team's batch of 20 had not hit it. |
| High | The API in the compose stack returned 404 for every stored investigation: the folder was not mounted into the container, and the smoke test did not cover the endpoint. |
| Medium | Process identifiers with unusual characters produced a traceback in the CLI. |
| Medium | Financial figures from the fiscal year of the process itself were shown as if known at award time. |
| Medium | The approval date and audited period of Contraloría reports were dropped, so a report could sit under a process it did not cover without saying so. |
| Medium | Absurd values from a source (for example a seven-digit employee count or a date in 2099) were rendered as facts. |
| Medium | Legal status and subscribed capital are current snapshots but read as the status at award time. |
| Medium | The telemetry attribute allow-list accepted out-of-range numbers and hyphen-joined names. |
| Low | No similarity floor for "similar purchases"; ratios rounding to zero; retries and files conflated; a specialist could be dispatched twice without cause. |

It also traced a latency problem to the API opening a new database connection and recreating
its views on every request.

### What changed in response

The privacy scan inspects only string values and a genuine hit stores a withheld record instead
of aborting; stored files are named by a hash of the identifier so every real process can be
investigated; financial figures come from the latest fiscal year strictly before the process;
out-of-range values render as "no disponible"; snapshot facts say so; Contraloría matches carry
their dates and are grouped by whether the audited period includes the process; similar
purchases require a minimum similarity; telemetry validates each attribute against its own
type, range or vocabulary; the API reuses one locked-down database per worker.

## Review 4 — re-test of the stage 2 fixes

A different reviewer re-tested the fixes, concentrating on the riskiest change: the API now
shares one database per worker process instead of opening one per request.

### Confirmed

- **The crash is gone.** 13 of 13 live investigations and 320 offline ones completed; none
  aborted and none were withheld.
- **Shared database.** 65 attacks through the reader (file and URL reads, `COPY`, `ATTACH`,
  `INSTALL`, `SET`/`PRAGMA`, stacked statements, temporary views, tables and macros, `EXPORT`,
  `CALL`) were refused or harmless; nothing persisted between requests; 340 payloads over HTTP
  produced no 500. Sixteen threads making 150 calls each showed no cross-request mix-up, and a
  replaced data file was picked up.
- **Stored investigations are served** by the compose stack, and no HTTP route can start one.
- **Fact logic.** Financial figures come from the latest fiscal year strictly before the
  process (checked on six processes against the source), zeros render as unavailable, snapshot
  facts say so, and Contraloría dates and period grouping matched the source rows.
- **Privacy.** 300 natural-person and RUC-less processes across four endpoints: no identifiers
  and no names. Legal-representative names fetched live for 32 companies appear in none of the
  36 stored records.
- **Load.** 200 requests at concurrency 8: p95 0.64 s, no errors.

### Still open at the time of review 4

| Severity | Finding |
|---|---|
| Medium | The stored-record privacy scan had been narrowed too far while fixing the crash: it caught a plain natural-person RUC but no cédula and no RUC written with dots, dashes or spaces, nor identifiers held as integers or dictionary keys. |
| Medium | The Contraloría report-number field was rendered as received and accepted an identity number in a test. |
| Medium | One buyer had nine matching reports and the dossier listed six without saying so; two of the omitted ones covered the process date. |
| Low | The same neighbour could show a different buyer-name spelling across identical requests; a CLI command still printed a traceback for an empty identifier; a stored record was not checked against the identifier it was requested under; a singular/plural mismatch. |

These were fixed afterwards: the scan now normalises digits and separators, inspects values and
keys, validates cédulas with the checksum, and was run in both directions (21 attack forms
caught; 400 real offline investigations with no false alarm); report numbers must match the
shape derived from real values; the list states "se muestran N de M" and orders covering
reports first. **This last round was verified by the project's own tests and runs, not by a
fifth independent review.**

## Review 5 — adversarial review before publication

A fifth reviewer, who again started without knowledge of the codebase, swept the stored quotes, the
question-answering evaluation, the identifier validation, the deployment path and the web build, and
concluded that **the project was not fit to publish**. As in the earlier reviews, personal names and
identifiers from the reviewer's reproductions are not repeated here: evidence is given as counts and
categories. Findings 4, 5, 6, 8a, the deployment parts of 7 and 9, and finding 10 were assigned to the web
and deployment work; this section records the backend part (findings 1, 2, 3, 7 content check, 8b, 9 and the
`Retry-After` item).

### Finding 1 (critical): natural persons named in the stored quotes

**Evidence.** All 110,579 stored passages were swept. Seven simple regular expressions found 62 passages
naming a person; reading found roughly 120 passages in about 110 processes. Categories: legal representatives
introducing themselves ("Yo, <three or four names>, en mi calidad de..."); sign-offs and signature blocks
("Atte. <name>"); titles spelled out and followed by a name (engineer, doctor, chemist-pharmacist);
"representada legalmente por <name>" in award texts; "sr.<SURNAME>" with no space; named technical staff in
convalidation requests (CVs, certificates, voting-certificate numbers); insurance advisers with credential
numbers (about 25 passages); two passages naming a patient; "copia de la cédula de <name>"; one partial mobile
number; 54 passages quoting vehicle plates. The project had claimed "about 2 in 110,000"; that claim is
withdrawn: it came from the same screens finding nothing, i.e. from measuring what they already knew how to find.

**What changed.** The approach, not another pattern (patterns had failed twice):
1. **Deny by default** (`domain/quotes/strict.py`, rules D1 to D13 in `docs/QUOTES.md`): a passage is eligible only if it holds no sign-off, first-person identification, title followed by a word, credential, plate,
   long number, health reference or person-name token (in any case), every capitalised word is institutional
   vocabulary built from the data (`quote_lexicon`: 7,836 capitalised and 20,024 ordinary words, no hand-written list and no
   person-name token), and an all-capitals passage contains only known words. Entity names of the process are set aside.
   The vocabulary of person-name tokens was redefined: the earlier one dropped every token ever typed in lower case
   more than 2 % of the time, which removed the commonest given names and surnames, because people type them in lower case.
2. The **release gate** (`scripts/check_quotes_privacy.py`, `domain/quotes/gate.py`): the reviewer's seven rules (reconstructed from
   the sweep scripts) plus nine of the project's own, and the boundary function re-run with the real protected names. The bundle
   script runs it first with `--with-quotes` and refuses to build when it fails; without the flag no quotes table is shipped.
   An optional test runs it over the real mart. The gate rules are also part of the screen, so a mart built by this code cannot fail it.
3. **Off by default** (`VEEDOR_QUOTES_ENABLED=false`): the route is a 404, `/ask` attaches no quote, `/meta` says
   `quotes_enabled: false`, compose passes `${VEEDOR_QUOTES_ENABLED:-false}`.
4. The API boundary applies the same function with the same lexicon; a mart without the lexicon is refused (503).

**Measured after the rebuild.** Gate on the final mart: all seven reviewer rules 0, all own rules 0, boundary refusals 0 (81,568 passages in 54,489 stored quotes); the same seven rules (my reconstruction, broader than the reviewer's 62-hit regular expressions) matched **9,994 passages of the earlier mart**. Quotes stored 54,489 (27,079 paired) against 68,541 (42,038); processes with a quote 30,752 against 36,345, i.e. 35.1 % of flagged processes against 41.5 %. By signal the share of flagged processes with a quote moved: `SINGLE_BIDDER` 41.2 to 34.9 %, `RECURRING_COBIDDERS` 50.4 to 42.9 %, `CONTRACT_VS_COMPANY_SIZE` 52.6 to 44.1 %, `LOW_SAVING` 43.2 to 37.3 %, `BUYER_CONCENTRATION` 37.0 to 31.1 %, `NEW_SUPPLIER` 47.9 to 41.0 %, `SHORT_TENDER_WINDOW` 14.6 to 11.8 %, `REPEATED_DIRECT_AWARDS` 13.0 to 11.3 % (full table in `docs/QUOTES.md`). Reading, rounds and bounds in `docs/QUOTES.md`: round 1 (seed 4101) and round 2 (seed 5202) each read 150 random passages and 150 suspicious ones and found **0 persons** (95 % upper bound 2.0 % per round; 1.0 % pooled over 300). The earlier preview rounds did find things: a passage naming two persons in lower case (the vocabulary was redefined), 528 passages the gate's broader rules caught (merged into the screen), and 2 passages that fail only once cut for display (now screened as shown).

**Remains open.** The bound is from samples read by one reader who knew the rules, of the first 230 to 340 characters of each passage; it is an upper bound, not a guarantee (0 of 300 random passages still allows up to 1.0 %, about 700 passages). A person named in lower case with a rare name that is in no vocabulary and next to no cue, or described without a name, can pass. The reviewer's own 62 regular expressions were not available, only their sweep scripts. Quotes stay off by default; turning them on is the operator's decision.

### Finding 2 (high): accusation-like third-party text beside risk signals

**Evidence.** 785 passages in 672 processes contained accusation or hostile wording that the unsafe screen missed:
"direccionamiento" in the sense of rigging (about 500), "denunci...", "a dedo", "sucios juegos", "corrup...", "no se
engañen", "la cía que todos sabemos", "favorec...", "amañ...", "colus...", "arreglado", "fraud...", "ilegal",
"irregular", "sobrepreci...", "coima", "soborn...", "trampa", "amarrad...", "a la medida", "con nombre y apellido",
"ganador ya definido", "beneficiar a", "perjudic...".

**What changed.** `domain/quotes/allegation.py`: one accent-, case- and look-alike-insensitive pattern per stem, applied to
the quotes screen and to the QA screen. "dirección" (address, department) is untouched: only the verb family is matched, as a whole word, and
tests pin both sides. Seven stems were added after reading a boundary sample (discriminatorio, arbitrario, sospechoso, nepotismo,
ladrón, "falta de transparencia", abusivo). Counts per stem over all 3,292,395 texts and over the earlier mart are in `docs/QUOTES.md`
(33,951 texts, 1.03 %, contain at least one stem; 845 of the earlier 110,579 stored passages).

**Measured.** The reviewer's stems, searched independently of the new module (plain substring regular expressions, `amañ` at a word start, "direccional" excluded), find **1,362 passages in 1,140 processes in the earlier mart and 0 true hits in the final one** (the one hit, "sería la medida", is a false match across an accent). The first version of the `direccion` stem matched whole words only and let 8 passages with "direccionar el proceso" through; the independent search found them, the stem was widened and the mart rebuilt. In 100 passages beside `SINGLE_BIDDER` or `RECURRING_COBIDDERS` (and in 150 random passages) none read as an allegation after the fix; a sample of 30 dropped passages: 18 complaints or allegations, 4 quotations of the law, 6 harmless uses, 2 unclear. The screen is blunt on purpose and also drops harmless text (about 400 passages with the boilerplate "no redireccionar").

### Finding 3 (medium): leakage in the question-answering evaluation

**Evidence.** 29 of 73 answerable templates were verbatim retrieval key phrases (`FACT_KEYS_ES`) and 50 of 73 contained or were
contained in one; the split was by process, not by phrasing.

**What changed.** A second, independently worded set (at least 5 new phrasings per fact type and per unanswerable group; colloquial
Ecuadorian Spanish, no accents, misspellings, indirect wording) with a test that none equals, contains or is contained in a key phrase and that the content-word
overlap with the nearest key stays under 0.5; thresholds tuned on one set of phrasings and processes, reported on unseen phrasings and unseen
processes; the system was not retuned and the keys were not changed. The retrieval keys were in the author's context when the phrasings were written:
independence is enforced by the test, not by blindness.

**Measured (retrieval only, 310 unseen processes).** Recall of the expected facts: **83.7 %** (81.8 to 85.5) with the original phrasings, **14.2 %** (12.4 to 16.1) with unseen phrasings.
Answerable questions answered with no fact: 3.2 % and 75.7 %. Abstention on unanswerable questions: 79.7 % and 88.0 %. Weak categories: `signals_all`
(24 % / 0 %), `ghost` (42 % / 0 %), `registry_company` (54 % / 0 %), `history` (50 % / 12 %), `pair_others` (n = 2), and with unseen phrasing also `winner`, `object`, `amounts`, `procedure`,
`registry_sri` (0 %). Model mode was not rerun (cost); its numbers are marked as measured on the in-vocabulary set with n = 172.
**Remains open:** the similarity floor (0.575) was chosen on in-vocabulary phrasings and is probably too high for colloquial wording; a fair
fix needs a new tuning set of phrasings (it was not done here, so as not to tune on the report set); the model was not tested on unseen phrasings.

### Finding 7 (backend part): the bundle gate matched only names and hashes

**Evidence.** The release gate refused files by path and by hash of the unmasked texts; it did not look at the content of a data table.
**What changed.** For the quotes table the gate now checks content (finding 1, item 2); the default bundle contains no quotes table at all.
**Remains open.** The deployment-side release gate (name, hash and path checks of the whole bundle) is in the deploy work; the orchestrator completes this line.

### Finding 8b: 891 processes returned 422

**Evidence.** 891 of 2,251,027 identifiers contain characters the path pattern rejected (spaces, en dashes, commas, `Ñ`, slashes, quotes...).
**What changed.** The pattern is still a strict allow-list (`domain/ocid.py`), widened to spaces, the dashes `– — ‐ ‒ − －`, commas, colons, parentheses, `+`, `&`, `º`, `°`, `·`, `Ñ`, `Ç`, `Ó`; control characters, format characters (soft hyphen,
zero-width, bidi override), slashes, backslashes, quotes, `%`, `? # ; * ~ | ! < > { } $`, look-alike letters and digits stay refused (an injection set is in `tests/domain/test_ocid.py`).
**Measured.** Against the running API: **806 of the 891 earlier 422s now return the process (200, same ocid)**; 85 do not (54 answer 404, the slash splits the path into a route that does not exist; 31 answer 422, they hold quotes, `*`, `|`, `;`, `~`, `!` or an invisible character). List endpoints (`/processes`, similar processes) carry `detail_available: false` for those 85 so a client does not link to them.

### Finding 9 (backend part): rate limits and the ask budget are per worker, in memory

**What changed.** The documents now say exactly what is per worker and what resets on restart (`docs/SECURITY.md`, `docs/CONFIGURATION.md`). The ask daily budget
and the per-client counters can live in PostgreSQL (`VEEDOR_ASK_USAGE_SHARED`, table `ask_usage`, migration 0003, one atomic `INSERT ... ON CONFLICT DO UPDATE ... WHERE used < limit`;
the client is stored as a truncated hash; on a database error the in-memory counters apply). Compose sets it. Verified: 16 threads on the real PostgreSQL count exactly 5 of 40 for a limit of 5.
`/ask` 429 responses carry `Retry-After` and CORS exposes it. **Remains open:** review and dossier limiters are still per worker and in memory; the shared per-client windows are fixed buckets; behind a proxy
the client IP is the proxy's unless forwarded headers are trusted.

### Findings addressed in web and deployment

| Finding | Status |
|---|---|
| 4, 5, 6, 8a, the deployment parts of 7 and 9, and 10 | addressed in web/deploy. Placeholder: the orchestrator completes this row with the web and deploy changes. |

## Residual limits

- **Name masking in free text is heuristic.** A person who is not a party to the process and is
  mentioned without an honorific can still appear in a description shown by the process detail
  endpoint.
- **The data bundle contains unmasked personal data.** Masking happens at the API boundary. The
  Parquet files must never be published as they are.
- **The forbidden-word list is not a guarantee.** The guarantee for dossier text is structural:
  code writes every sentence from enumerated facts and phrases.
- **The verifier checks presence, not meaning**, for any figure that is not bound to a label.
- **Reviews use one shared token**, and the review and dossier rate limits are per worker process and in memory (the `/ask` budget and limits are shared in PostgreSQL when `VEEDOR_ASK_USAGE_SHARED` is on).
- **85 of 2,251,027 processes** have identifiers with a slash, a quote, `*`, `|`, `;`, `~`, `!` or an
  invisible character; the validation still rejects them (806 of the 891 earlier rejections now open).
  They appear in listings with `detail_available: false` and their page cannot be opened.
- **Quotes are disabled by default** because their privacy screens have a measured, non-zero residual
  (`docs/QUOTES.md`); the sample-based bound is not a guarantee.
- **No model behaviour was reviewed adversarially with a real model.** Reviewers used a scripted
  fake model through the real agent graph.
- **Investigation facts are snapshots of today's registries.** Legal status and subscribed
  capital are the values at query time; the text says so, but they are not the values at award.
- **The audit specialist reads part of the catalogue.** It can show that at least N Contraloría
  reports mention the buyer; it cannot show that there are no others. Matching is by exact
  normalised entity name; near-identical entity names were not exercised by a reviewer.
- **Model-assisted investigation numbers predate the last fixes.** The recorded run with a real
  model (10 processes) was not repeated after the review-3 and review-4 fixes.
- **Vector similarity is not relevance.** Almost half of the index is embedded from the CPC
  classification alone; agreement drops from 63 % to 30 % when the classification text is
  removed from the embedding.
