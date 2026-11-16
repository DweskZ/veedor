# Veedor — build contract, stage 2 (investigation agents, vector search, observability)

Binding for everyone working on this stage. `docs/CONTRACT.md` still applies in full (no
invented data, wording rules, masking of natural persons, English code / Spanish UI copy, no
`.env*` edits, no git commands, `rg`/`fd`/`bat`/`sd`/`eza`). Read `docs/REVIEWS.md` first: it
lists the defects two independent reviews found in stage 1. Do not reintroduce them.

Each owner edits only their paths. Do not run `ruff format` outside your own files. Do not run
`uv add` (dependencies are installed: `mcp`, `langgraph`, `langchain*`, `fastembed`, `pgvector`,
`sqlalchemy`, `psycopg`, `opentelemetry-*`). Use current library docs, not memory.

## What stage 2 adds

1. A **multi-agent investigation**: a supervisor and four specialists that gather additional
   evidence about a flagged process through read-only tools, including live lookups through the
   EcuDataMCP server.
2. **Vector search** over what each process bought (PostgreSQL + pgvector), exposed as "similar
   processes" and used by one specialist.
3. **Observability**: OpenTelemetry traces and metrics for API requests and every agent step,
   with a dashboard in the local compose stack.

## Verified facts about EcuDataMCP (checked by running it on 2026-11-16)

- Launch: `uvx ecuador-mcp --transport stdio` (server v0.15.0, 85 tools). First launch downloads
  the package; some tools download a dataset on first use (the Supercías directory took ~12 s).
- Tools take a `format` argument: `"json"` returns a structured result. Always use it.
- `get_compania_info(ruc)` worked live and returned, for a company: name, RUC, expediente, legal
  status, company type, **incorporation date**, address, phone, legal representative, subscribed
  capital, CIIU, last year with a filed balance.
- `get_sri_ruc_info(ruc)` **failed** with HTTP 500 from the SRI's own service. Upstream failures
  are normal: every tool call must have a timeout, at most one retry, and a recorded outcome.
- Other tools seen (verify their real JSON output before relying on a field):
  `get_financials(expediente_or_ruc, anio|desde|hasta)`, `search_companias`, `search_contratos`,
  `get_contrato_info(ocid)`, `get_resumen_compras(comprador, year)`,
  `get_contraloria_informe(informe_id)` with ids from `list_catalogo(fuente="contraloria")`.
- The MCP python client exposes `tool.input_schema` (not `inputSchema`).

## Agent design (owner: investigation)

Pattern: **supervisor + specialists**, built with LangGraph. The stage-1 design principles stay:
facts are gathered and computed by code; a language model never writes prose about facts and
never produces free-form tool arguments.

```
load_evidence → supervisor ─┬→ company_agent      (Supercías: incorporation, capital, status, financials)
                            ├→ tax_registry_agent (SRI registry facts; live lookup optional)
                            ├→ history_agent      (buyer–supplier history, similar purchases via vectors)
                            └→ audit_agent        (Contraloría reports about the buyer)
              ← each specialist returns typed findings + a tool log →
supervisor (may dispatch again within budget) → assemble_evidence → plan (constrained) → render → verify → finalize
```

- **Supervisor**: decides which specialists to run and in what order, given the fired signals
  and what is already known. Its output is a list of specialist names from an enumeration, with
  a one-phrase reason chosen from an enumeration. Deterministic policy when no model is
  configured (rule table: which signals call for which specialist). Budget: at most 6 specialist
  dispatches per investigation, no specialist more than twice.
- **Specialists**: each has ONE objective, an allow-list of tools, and a step budget (max 4 tool
  calls). A specialist chooses its next action from an enumeration of (tool, target) pairs where
  the target is a reference into the evidence pack (`winner`, `buyer`, `process`) — never a
  free string. Code resolves the reference to the real argument (RUC, ocid, buyer name), calls
  the tool, validates the result against a pydantic model, and converts it into typed facts.
  With no model configured, each specialist runs a fixed default sequence.
- **Tool results are untrusted data.** They are parsed by code into typed fields. No string from
  a tool result is ever placed in a prompt as an instruction, used as a tool argument, a path, a
  URL or SQL. Free-text fields from tools are either dropped or stored as attributed quotations
  that never reach the model.
- **Tools are read-only.** Allow-list only; unknown tool names are rejected; arguments are built
  by code from validated identifiers (RUC regex, ocid regex).
- **Natural persons.** Registry lookups run only for companies and public entities (RUC third
  digit 9 or 6). Names of legal representatives, shareholders or any natural person returned by
  a tool are never stored in the evidence pack, never shown, never sent to the model. A derived
  fact such as "the legal representative also represents another bidder in this process" may be
  computed by code and stored as a boolean plus a count, without the name.
- **Failure is a first-class outcome.** Every tool call is logged: tool, target reference,
  started/ended, outcome (`ok` | `timeout` | `upstream_error` | `invalid_result` | `skipped`),
  attempt count. A failed lookup yields the fact "no disponible (la fuente no respondió)"; it
  never yields an invented value and never aborts the investigation.
- **New facts flow into the same renderer and verifier** as stage 1. New fact templates are
  added to the catalogue with applicability predicates; the "every enumerated phrase renders and
  verifies" test must cover them.
- The dossier gains an "Investigación realizada" section listing which specialists ran, which
  sources were consulted, and which lookups failed — rendered by code from the tool log.
- **HTTP API**: still never calls a language model and never starts live lookups for anonymous
  requests. Investigations are produced by the CLI (`veedor investigate run <ocid>`,
  `veedor investigate batch --top N`) and stored; the API serves stored investigations
  (`GET /api/v1/processes/{ocid}/investigation`, 404 when none exists).

## Vector search (owner: vectors)

- Text embedded per process: CPC description plus the process description **after**
  `safe_free_text` masking (never embed or store raw personal data). Catalogue purchases are out
  of scope. Local multilingual embedding model through `fastembed` (verify the exact model name
  and dimension from the library; no API key, no network at query time after the model is cached).
- Storage: PostgreSQL table with a pgvector column and an HNSW or IVFFlat index (choose and
  justify from the pgvector docs), created by an Alembic migration. Keyed by `ocid`; stores the
  model name and a content hash so re-runs are idempotent.
- `veedor vectors build [--limit N]` and `veedor vectors status`.
- Interface used by others (exact path and signature):
  `veedor.use_cases.similar_processes.find_similar(ocid: str, k: int = 10, same_buyer: bool = False) -> list[SimilarProcess]`
  where `SimilarProcess` has `ocid, similarity, year, buyer_ruc, buyer_name, method, award_total,
  main_cpc`. Raises `VectorsUnavailable` when the index or database is missing.
- API: `GET /api/v1/processes/{ocid}/similar?k=&same_buyer=` (masked like every other response;
  503 when vectors are unavailable).
- **Measured quality, not asserted**: an evaluation command reports retrieval quality using CPC
  codes as a proxy label — for a random sample of ≥ 1,000 query processes, the share of the top-10
  neighbours that share the query's CPC 5-digit prefix, compared with a random-neighbour baseline
  and with an exact-CPC-match baseline, with a bootstrap confidence interval. Results written to
  `eval/vector_search.json` and a generated section in the docs. Report it even if it is poor.

## Observability (owner: telemetry)

- Module `veedor.infrastructure.telemetry` exposing (exact names):
  `setup_telemetry(service_name: str) -> None` (no-op when `VEEDOR_OTEL_ENDPOINT` is unset),
  `span(name: str, **attributes)` context manager, `record_llm_usage(model, prompt_tokens,
  completion_tokens)`, `record_tool_call(tool, outcome, duration_ms)`,
  `record_grounding(passed: bool, mode: str)`.
  All are safe no-ops without a configured endpoint so tests and the CLI work offline.
- Never put personal data, RUCs of natural persons, prompts, tool results or free text in span
  attributes or metric labels. Allowed: ocid, specialist name, tool name, outcome, counts,
  durations, model name, token counts, final mode.
- FastAPI instrumentation for request traces and RED metrics.
- Compose: one observability service, bound to 127.0.0.1, with an OTLP endpoint, a trace store,
  a metrics store and Grafana with a provisioned dashboard (verify that the image and tag exist).
  Dashboard panels: request rate / errors / latency by route; investigations by final mode;
  specialist runs and tool-call outcomes by tool; tool latency p50/p95; tokens per investigation;
  grounding pass rate.
- **Proven, not assumed**: a script generates traffic (API requests and a batch of
  investigations) and then queries the trace and metrics stores' HTTP APIs to assert that the
  expected spans and series exist, printing counts.

## Acceptance checks (the orchestrator will run these personally)

1. `uv run ruff check src tests scripts` clean; `uv run pytest -o addopts=""` all pass.
2. `veedor investigate batch --top 20` with **live** EcuDataMCP: every investigation completes
   (no exception); the tool log shows real `ok` outcomes for company lookups and honest failure
   outcomes where a source is down; every dossier passes verification. Summary written to
   `eval/investigations_run.json` (counts only; no names or RUCs).
3. Fault injection: with the MCP server unavailable, with a tool that times out, and with a tool
   returning malformed or hostile content, investigations still complete, facts say "no
   disponible", nothing injected appears anywhere.
4. Privacy: across the 20 real investigations, no natural person's name (including legal
   representatives returned by the registry) and no natural-person RUC appears in any stored
   investigation, dossier, trace, span attribute or log line.
5. `veedor vectors build` over the real data; `find_similar` returns results in well under a
   second; `eval/vector_search.json` exists with the three numbers and their intervals.
6. The telemetry verification script passes against the running stack.
7. `docker compose up -d --build --wait` brings everything up healthy; `scripts/smoke_test.py`
   passes (extended with: similar-processes endpoint, stored-investigation endpoint).
8. An independent adversarial review is run **before** anything is reported as working.

## Reporting back

Files created; exact commands with real output; what is partial or unverified; any deviation
from this contract and why. If a criterion cannot be met, say so — do not weaken the check.
