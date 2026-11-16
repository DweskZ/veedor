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
