# Independent reviews

Two adversarial, read-only reviews were run against the code and the running local stack on
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

## Residual limits

- **Name masking in free text is heuristic.** A person who is not a party to the process and is
  mentioned without an honorific can still appear in a description shown by the process detail
  endpoint.
- **The data bundle contains unmasked personal data.** Masking happens at the API boundary. The
  Parquet files must never be published as they are.
- **The forbidden-word list is not a guarantee.** The guarantee for dossier text is structural:
  code writes every sentence from enumerated facts and phrases.
- **The verifier checks presence, not meaning**, for any figure that is not bound to a label.
- **Reviews use one shared token**, and rate limits are per process.
- **891 of 2,251,027 processes (0.04 %)** have identifiers with characters that the strict
  validation rejects; they appear in listings but their detail page cannot be opened.
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
