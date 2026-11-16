# Contributing

Thanks for looking at Veedor. Read `docs/CONTRACT.md` and `docs/CONTRACT_V2.md` (agents, vector search, observability) first: they are the binding rule set. `docs/REVIEWS.md` lists the defects four independent reviews found; do not reintroduce them.

## Setup

```bash
uv sync                  # Python 3.12 environment
uv run pytest -o addopts=""   # tests
uv run ruff check src tests scripts
uv run ruff format --check src tests
```

`make lint` and `make test` run the same checks. Ruff line length is 110. The dashboard lives in `web/` (`pnpm install`, `pnpm lint`; see `web/README.md`).

Tests use small synthetic fixtures under `tests/fixtures/`. They must not hit the network or need the real data lake. Checks against real data are separate commands and are reported as such.

## The layer rule

- `domain` is pure logic: no I/O, no framework imports, nothing from the other layers.
- `use_cases` depend on `domain` and on ports (Protocols) declared next to them.
- `infrastructure` implements the ports.
- `api` and `cli` only call use cases.

Tests mirror the `src/veedor` layout.

## The two hard rules

1. **No invented data.** No made-up numbers, URLs, legal articles, thresholds, company facts or benchmark results, in code, tests, docs or UI. If a fact is unknown it is `null` and the UI says "no disponible". Any number in a doc must come from a file or a command you ran.
2. **No accusatory wording.** Use "señal de riesgo", "indicador", "atípico". Never "corrupto", "fraude", "irregular", "culpable" or anything that asserts wrongdoing. Natural persons are masked at the API boundary.

Also: code, comments and docs are in English; user-facing text and dossier text are in neutral, professional Spanish. Never commit secrets or `.env` files. Commits follow conventional commits.

## Adding a signal

A signal is a documented rule, not just a query. Include all of these in one change:

1. **Definition.** Add the code, Spanish label, description and threshold rule to `src/veedor/domain/signals/definitions.py`, its parameters to `parameters.py`, and its weight to the scoring module. Decide whether it is a `risk` signal or a zero-weight `context` signal (context signals never change the score). State the exact fields it uses and its scope (which method groups can fire it).
2. **SQL.** Implement it as set-based DuckDB SQL in `src/veedor/infrastructure/lake/marts_builder_sql.py`. Statistical thresholds are computed from the data per method and year, never hard-coded. Each fired row stores `value`, `threshold` and an `evidence_json` with the facts needed to check it against the source record.
3. **Tests.** Add synthetic-fixture tests: it fires when it should, does not fire out of scope, and handles missing fields (a missing field means "not evaluated", not zero).
4. **Methodology entry.** Add a section to `docs/METHODOLOGY.md` with the rule, scope, fields, threshold, data handling and the legitimate explanations that produce false positives.
5. **Dossier text.** Add template wording and make sure the grounding verifier still passes.
6. **Evaluation.** Rebuild the marts and rerun `veedor evaluate backtest`, `coverage` and `report`. Do not edit `docs/EVALUATION.md` by hand; if the result is not better than chance, say so. Never change a rule to improve a metric: the run is appended to `eval/history.json` and tuning after looking at a metric is a source of optimism.
7. **LLM.** The model never writes prose. Anything it influences must be a choice among ids or enumerated options that the renderer turns into text.

## Changing the agents, vector search or telemetry

- **Tools are read-only and allow-listed.** A new tool needs an entry in the specialist's allow-list, a pydantic result model that declares only the fields used, a closed vocabulary for every enumerated value, and a recorded outcome on failure. Arguments are built by code from validated identifiers, never from model output or tool text.
- **Tool results are data.** No string from a tool result goes into a prompt, a tool argument, a path, a URL or SQL. Never declare, store, log or send to a model the name of a natural person returned by a source.
- **New facts** need template wording with an applicability predicate and must pass the "every enumerated phrase renders and verifies" test.
- **Telemetry** accepts only allow-listed attribute keys with a value rule each (`src/veedor/infrastructure/telemetry/allowlist.py`). Never put RUCs, names, prompts, tool results or free text in a span attribute or metric label.
- **Vector search** embeds only text that passed `safe_free_text`; the table stores no text. Report retrieval quality with its caveats, even if poor.
- Tests use scripted fake models and fake tool servers; they must not call a real model or the live MCP server.

## Reporting security issues

Privately, to the maintainer. See `docs/SECURITY.md`.
