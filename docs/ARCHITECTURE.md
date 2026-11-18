# Architecture

Veedor computes transparent risk indicators over Ecuador's open procurement data and serves them,
with evidence dossiers, through an API and a dashboard. The rules every component follows are in
`docs/CONTRACT.md`.

## Layers and the dependency rule

```
src/veedor/
  core/            settings, paths
  domain/          pure logic, no I/O, no framework imports
    signals/       indicator definitions, parameters, scoring weights
    dossier/       evidence-pack models, templates, grounding verifier, vocabulary
    masking.py     natural-person masking
  use_cases/       application services; query functions depend on ports (Protocols)
  infrastructure/  ocds (flattening), lake (DuckDB over Parquet, marts SQL), registries (SRI,
                   Supercias), db (SQLAlchemy + Alembic), llm (chat-model port), mcp
  agents/          investigator: LangGraph graph that writes and verifies a dossier
  api/ + schemas/  FastAPI routers and Pydantic response models
  cli/             Typer commands (`veedor ...`)
```

`domain` imports nothing from the other layers (no module under `domain/` imports `infrastructure`,
`use_cases` or `api`). `use_cases` depend on `domain` and on ports declared beside them
(`use_cases/queries/ports.py`); `infrastructure` implements the ports; `api` and `cli` call use cases.
Known deviations from that rule (counted on 2026-11-17 with `rg "from veedor.infrastructure"` over
`use_cases/` and `api/v1/`; the rule holds for `domain` and for the query use cases, not everywhere):

- **Use cases that wire concrete infrastructure.** `use_cases/build_dossier.py` (`EvidenceReader`, the LLM
  factory, in `default_service()`; `use_cases/queries/dossier.py` imports it lazily),
  `use_cases/investigate.py` (the investigation store, the tool backends, the evidence reader, the LLM
  factory and the MCP session), `use_cases/similar_processes.py` (`PgVectorStore` and the buyer-name
  helper, imported inside the default factory) and `use_cases/build_vectors.py` (the `VectorRow` type of
  the pgvector adapter). The collaborators are injectable, so tests use fakes, but the default wiring
  lives in the use case instead of a composition root.
- **Ports declared on the wrong side.** `ChatModelPort` and `ToolBackend` are declared under
  `infrastructure/llm/port.py` and `infrastructure/mcp/port.py`, and `use_cases` import them from there.
  A port belongs beside the code that needs it (as in `use_cases/queries/ports.py`), so here the
  dependency points outwards.
- **Routers that skip the use-case layer.** `api/v1/similar.py` imports the database session, the
  pgvector repository and a vectors helper; `api/v1/investigations.py` imports the investigation store;
  `api/v1/ask.py` imports the telemetry span helper. `api/deps.py`, `api/ask_wiring.py` and `api/main.py`
  also import infrastructure, which is their job: they are the composition root of the HTTP process.

None of these is fixed yet. The intended fix is to move the two ports next to the use cases, move the
default wiring into the composition roots (`api/deps.py` and the CLI), and give the three routers a use
case to call.

## Component diagram

```mermaid
flowchart LR
  subgraph Browser
    U[User]
  end
  subgraph web[web: Next.js]
    SSR[Server rendering]
    FORM[Review form]
  end
  subgraph api[api: FastAPI]
    R[Routers /api/v1]
    M[Masking models]
    UC[Use cases]
    DS[DossierService]
  end
  subgraph agent[agents/investigator]
    G[LangGraph]
  end
  L[(Parquet lake + marts<br/>read-only, DuckDB in memory)]
  P[(PostgreSQL<br/>reviews)]
  C[(Dossier cache + traces<br/>writable volume)]
  LLM[[Optional LLM provider]]

  U --> SSR
  U --> FORM
  SSR -->|API_INTERNAL_URL| R
  FORM -->|NEXT_PUBLIC_API_URL| R
  R --> UC --> L
  R --> M
  UC --> DS --> G
  G --> L
  G -.optional.-> LLM
  DS --> C
  UC --> P
```

## Data-flow diagram

```mermaid
flowchart LR
  B[SERCOP OCDS bulk file<br/>jsonl.gz] -->|veedor lake build| LK[lake: processes, tenderers, awards]
  S1[SRI RUC + ghost list] -->|registries download/load| RG[lake: suppliers_sri, ghost_companies]
  S2[Supercias files] -->|registries download/load| RG2[lake: companies_supercias, company_financials]
  LK --> SG[veedor signals build<br/>documented SQL + Isolation Forest]
  RG --> SG
  RG2 --> SG
  SG --> MT[marts: process_signals, process_scores, supplier_profiles]
  LK --> API[FastAPI]
  RG --> API
  RG2 --> API
  MT --> API
  API --> WEB[Next.js dashboard]
  API --> DOS[dossier on demand]
```

## Dossier graph (`agents/investigator`)

Defined in `agents/investigator/graph.py` (LangGraph); security notes in `agents/investigator/README.md`.

```mermaid
flowchart LR
  A[load_evidence] --> B[assess_signals] --> C[write_narrative] --> D{verify_grounding}
  D -->|passed| F[finalize]
  D -->|failed, LLM used, attempts < 2| C
  D -->|failed otherwise| T[fallback_template] --> F
```

`load_evidence` and `assess_signals` are deterministic code. `write_narrative` calls the model only
when a provider is configured; otherwise (or on provider error) the deterministic template is used. The
verifier rejects any number, date, RUC, code or name not present in the evidence pack, and
`finalize` refuses unverified text. Each run appends a trace to `data/traces/`. The module was being
finished when this was written: treat the code as the reference ("see code").

## Key design decisions

| Decision | Reason |
|---|---|
| Parquet + DuckDB for analytics, PostgreSQL only for mutable state | The 2.25 M-process dataset is read-only between monthly rebuilds and scanned column-wise; Parquet files ship as a ~190 MiB bundle and need no server. Reviews are small, concurrent writes that need transactions, so they live in PostgreSQL. |
| One locked-down in-memory DuckDB database per worker process, a cursor per request | `LakeReader` registers views over known files, restricts `allowed_directories`, disables external access and accepts only `SELECT`/`WITH` (`docs/SECURITY.md`); no shared mutable engine to corrupt. |
| Signals as documented SQL, thresholds from the data | Every indicator has a code, fields, threshold rule and caveats (`docs/METHODOLOGY.md`), so a reader can audit why a process scores as it does. The anomaly score is reported separately and never changes the risk score. |
| Deterministic facts first, LLM only for prose | Facts, signals and registry matches are computed by code into an `EvidencePack`; a model may only phrase them. With no provider the system is fully functional (template mode). |
| Grounding verifier as the control | Prompt instructions cannot stop a model from inventing or being steered by text planted in tender descriptions; checking the output against the pack can. Failure falls back to the template; unverified text is never stored or shown. |
| Masking at the API boundary | Internal tables keep real values (needed for joins and signals); response models mask natural persons so no endpoint can forget it. Dossier evidence is masked before the pack is built. |
| Wording as a product rule | "Señal de riesgo", "indicador", "atípico": the system reports indicators, never accusations. |
| Reviews separate from analytics | Human decisions never alter marts or scores, so the indicator pipeline stays reproducible from the raw file. |
