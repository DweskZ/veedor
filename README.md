# Veedor

An open procurement risk radar for Ecuador: it reads the open data of public procurement (SERCOP, OCDS), computes rule-based risk indicators, and lets you explore them, with LLM agents that gather evidence and a question box that answers only from stored facts. *Un producto de ruray.*

![licence: MIT](https://img.shields.io/badge/licence-MIT-green) ![python 3.12](https://img.shields.io/badge/python-3.12-blue) ![CI: GitHub Actions](https://img.shields.io/badge/CI-GitHub%20Actions-lightgrey)

Live demo: not deployed yet

| Home | A process dossier |
|---|---|
| ![Veedor home: risk indicators across 2.25 million processes](docs/img/home.png) | ![Dossier of one process: fired indicators with value, threshold and source field](docs/img/process.png) |

In Ecuador a *veedor* is a citizen overseer: someone who watches a public process and reports what the records show.

## What it does

- Reads **2,251,027 procurement processes** (2015 to 2026) from SERCOP's open contracting data into a Parquet lake queried with DuckDB (`data/marts/build_summary.json`, `eval/coverage.json`).
- Applies **10 documented risk indicators and 2 zero-weight context indicators** to every process; 87,217 (3.9 %) fire at least one (`eval/coverage.json`).
- Writes a **dossier per process**: for each fired indicator, the value, the threshold and the source field, next to the typical value for the same method and year.
- Runs a **supervisor and five specialist agents** (LangGraph) that add registry, history, audit and question-and-answer facts for a flagged process through read-only tools, including the author's own MCP server, EcuDataMCP. The fifth runs only when the process has stored texts.
- Serves a **Next.js dashboard** with similar-process search (365,864 processes in a pgvector index) and a question box that answers only from stored facts (off by default).

One real dossier, with names withheld (a 2018 works contract; full text in [REFERENCE.md](docs/REFERENCE.md#a-real-example)):

| Indicator fired | Observed | Threshold |
|---|---|---|
| `SINGLE_BIDDER` | 1 bidder | 1 |
| `SHORT_TENDER_WINDOW` | 3.52 days | 4.04 days (5th percentile, same method and year) |
| `BUYER_CONCENTRATION` | 0.31 | 0.3 |
| `CONTRACT_VS_COMPANY_SIZE` | 4.58 times the supplier's previous-year revenue | 3 times |

The dossier also states that about half of the processes of that method and year have a single bidder (51.9 %), so a reader can discount the indicator.

## What it deliberately does not do

- **It does not accuse.** A fired indicator means a field is atypical under a stated rule. Veedor does not detect corruption and never says that anything improper happened.
- **It shows no natural persons.** They are masked at the API; quotes from process text are off by default.
- **Its score did not predict the one external list it was tested against.** On the SRI list of shell companies (9 winning companies against 19,837 others) the ROC-AUC is 0.447 (95 % interval 0.303 to 0.598); 0.5 is chance (`docs/EVALUATION.md`). The indicators are descriptive transparency measures, not validated predictors.

## Engineering highlights

1. **Constrained generation.** In LLM mode the model never writes prose: it receives a catalogue of fact ids and returns a plan (ids in order, one connective from a closed set). Code renders every sentence from templates, and a grounding verifier checks each number, date, RUC and name against the evidence pack, falling back to the template after two failures. Real-model run: 6 of 20 plans still fell back (`eval/llm_grounding_runs.json`). Code: `src/veedor/domain/dossier/`; see [AGENTS.md](docs/AGENTS.md).
2. **Evaluation that corrected itself.** Question answering was first measured on phrasings written with the retrieval keys (84.1 % recall). An independent review wrote its own wording: 14.2 %. The retrieval was rebuilt around intents and re-measured on three disjoint phrasing sets, one of them held out and evaluated once. <!-- qa-figures: copied from eval/qa.json and docs/EVALUATION.md -->Recall now: original 97.2 %, development 89.5 % (tuned on, optimistic), held-out 89.1 % (87.5 to 90.7); the earlier retrieval scored 40.7 % on the held-out set. Abstention on held-out unanswerable questions did not improve (83.9 %); attack successes 0 in all sets.<!-- /qa-figures --> Code: `src/veedor/evaluation/`, [EVALUATION.md](docs/EVALUATION.md).
3. **Privacy as a release gate.** Third-party text passes a deny-by-default screen, and a script fails the data bundle build when any stored passage matches the reviewer's or the project's rules. Quotes stay off unless built `--with-quotes`. Measured residual: of 150 passages read from the final mart, none named a person (95 % upper bound 2.0 %; 0 of 300 over two rounds, 1.0 %). That is a sample read by one reader, not a guarantee (`docs/QUOTES.md`). Code: `src/veedor/domain/quotes/`, `scripts/check_quotes_privacy.py`.
4. **Adversarial reviews.** Five independent, read-only reviews, each started without knowledge of the code, run on a suite that was fully green. They broke masking, the text verifier, the investigation API in compose and the first quote screen (persons in stored quotes), and the fixes are recorded. The last one concluded the project was not fit to publish until they were fixed. See [REVIEWS.md](docs/REVIEWS.md).

## Stack

| Skill | Where it lives |
|---|---|
| Python 3.12, uv, ruff, pytest | `pyproject.toml`, `tests/` |
| FastAPI, Pydantic | `src/veedor/api/`, `src/veedor/schemas/` (masking in response models) |
| SQLAlchemy + Alembic | `src/veedor/infrastructure/db/`, `alembic/versions/` |
| PostgreSQL + pgvector (HNSW) | `docker-compose.yml`, `alembic/versions/0002_create_process_vectors.py`, `src/veedor/infrastructure/vectors/` |
| DuckDB + Parquet | `src/veedor/infrastructure/lake/` (set-based SQL indicators) |
| scikit-learn (Isolation Forest) | `src/veedor/infrastructure/lake/marts_builder_anomaly.py` (reported separately, not in the score) |
| Local embeddings (fastembed) | `src/veedor/infrastructure/vectors/`, [VECTOR_SEARCH.md](docs/VECTOR_SEARCH.md) |
| LangGraph multi-agent supervisor | `src/veedor/agents/investigation/`, [AGENTS.md](docs/AGENTS.md) |
| MCP client | `src/veedor/infrastructure/mcp/` |
| RAG with grounding | `src/veedor/domain/dossier/`, `src/veedor/domain/qa/` |
| LLM evaluation | `src/veedor/evaluation/`, `eval/`, [EVALUATION.md](docs/EVALUATION.md) |
| Prompt-injection defences | `src/veedor/domain/investigation/`, `tests/agents/test_investigator_injection.py` |
| OpenTelemetry + Grafana | `src/veedor/infrastructure/telemetry/`, `ops/observability/`, [OBSERVABILITY.md](docs/OBSERVABILITY.md) |
| Next.js 16, TypeScript, Tailwind CSS | `web/` |
| Playwright + axe accessibility tests | `web/e2e/` (run locally with `pnpm test:e2e`; not in CI) |
| Docker Compose | `docker-compose.yml`, `deploy/` |
| GitHub Actions CI | `.github/workflows/ci.yml` (ruff, migrations, pytest), `deploy.yml` (manual deploy) |
| Terraform (AWS EC2, IAM OIDC, SSM) | `infra/terraform/`, [DEPLOYMENT_AWS.md](docs/DEPLOYMENT_AWS.md) (written, not verified on a live account) |
| Caddy | `deploy/Caddyfile` |

## Architecture

```mermaid
flowchart LR
  OCDS[SERCOP OCDS bulk file] -->|lake build| LK[(Parquet lake)]
  REG[SRI and Supercias files] -->|registries| LK
  LK -->|signals build| MT[(DuckDB marts: signals, scores)]
  LK -->|vectors build| PG[(PostgreSQL + pgvector)]
  MT --> API[FastAPI, masking]
  PG --> API
  API --> WEB[Next.js dashboard]
  API --> ASK[ask route: stored facts only]
  CLI[CLI investigate] --> SUP[LangGraph supervisor]
  SUP --> SPEC[five specialists]
  SPEC -->|read-only| MCP[EcuDataMCP]
  SPEC --> VER[renderer + grounding verifier]
  VER --> INV[(stored investigations)]
  INV --> API
```

- `domain/`: indicators, scoring, dossier templates, grounding verifier, masking. Imports nothing from the other layers.
- `use_cases/`: application services; they depend on `domain` and on ports (`use_cases/queries/ports.py`).
- `infrastructure/`: implements the ports (lake, registries, db, llm, mcp, vectors, telemetry).
- `agents/`: the LangGraph dossier graph and the investigation supervisor and specialists.
- `api/` and `schemas/`: FastAPI routers and Pydantic response models; `cli/`: Typer commands. Both only call use cases.
- The HTTP API serves stored records and never starts an investigation; the only route that can call an LLM is the question box (`POST /processes/{ocid}/ask`), where the model only selects stored fact ids. One known deviation from the layer rule is in [ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Run it locally

Needs Docker with Compose v2, [uv](https://docs.astral.sh/uv/) and Python 3.12. **The data lake is not in the repository**: the API needs `data/lake/` and `data/marts/`. Build them (below) or restore a bundle (`make bundle`, [DEPLOYMENT.md](docs/DEPLOYMENT.md)); a bundle holds unmasked personal data, so do not publish it.

```bash
uv sync
uv run veedor lake build                # needs data/raw/sercop_ocds_full.jsonl.gz, about 1 min
uv run veedor registries download && uv run veedor registries load
uv run veedor signals build             # about 5 s
docker compose up -d --build --wait     # or: make up; web :3000, api :8000
uv run python scripts/smoke_test.py     # or: make smoke
```

Vector index and investigations (`make db-up`, then `uv run alembic upgrade head`): `uv run veedor vectors build`, `uv run veedor investigate run <ocid> --no-llm`. Ports are bound to `127.0.0.1`. Full commands, `make` targets and configuration: [REFERENCE.md](docs/REFERENCE.md), [CONFIGURATION.md](docs/CONFIGURATION.md).

## Results and limits

| Measure | Value | Source |
|---|---|---|
| Processes analysed | 2,251,027 | `eval/coverage.json` |
| Processes with at least one risk indicator | 87,217 (3.9 %) | `eval/coverage.json` |
| Score vs SRI shell-company list, ROC-AUC | 0.447 (0.303 to 0.598) | `eval/backtest.json`, [EVALUATION.md](docs/EVALUATION.md) |
| Question answering recall, held-out phrasings | 89.1 % (87.5 to 90.7) | `eval/qa.json` |
| Similar-process agreement, description only, 20,000 pool | 29.8 % vs 2.4 % random | `eval/vector_search.json` |
| Investigations, no model / model-assisted | 20 / 10, no errors | `eval/investigations_run.json` |

Limits, in plain words: the score is not validated against any outcome. The label set is 9 companies and measures tax behaviour, not procurement. Registry facts are snapshots of today. Emergency procurement is absent from the open data. Name masking in free text is heuristic, and there is no user authentication, so do not expose the API to the internet. The model-assisted investigation run predates the last fixes, and no model behaviour was reviewed adversarially with a real model. More: [REFERENCE.md](docs/REFERENCE.md#known-limitations).

## Documentation

- **Method and evidence:** [METHODOLOGY.md](docs/METHODOLOGY.md), [EVALUATION.md](docs/EVALUATION.md), [DATA_SOURCES.md](docs/DATA_SOURCES.md), [VECTOR_SEARCH.md](docs/VECTOR_SEARCH.md).
- **Design:** [ARCHITECTURE.md](docs/ARCHITECTURE.md), [AGENTS.md](docs/AGENTS.md), [OBSERVABILITY.md](docs/OBSERVABILITY.md), [BRAND.md](docs/BRAND.md).
- **Safety and review:** [SECURITY.md](docs/SECURITY.md), [QUOTES.md](docs/QUOTES.md), [REVIEWS.md](docs/REVIEWS.md).
- **Operations:** [CONFIGURATION.md](docs/CONFIGURATION.md), [DEPLOYMENT.md](docs/DEPLOYMENT.md), [DEPLOYMENT_AWS.md](docs/DEPLOYMENT_AWS.md).
- **Build contracts:** [CONTRACT.md](docs/CONTRACT.md), [V2](docs/CONTRACT_V2.md), [V3](docs/CONTRACT_V3.md), [V4](docs/CONTRACT_V4.md).
- **Moved from this README:** [REFERENCE.md](docs/REFERENCE.md) (example dossier, key numbers, agents, performance, full commands, roadmap), [HISTORY.md](docs/HISTORY.md) (first question-answering measurement, review summary table).

## Resumen en español

Veedor es un radar abierto de riesgo en la contratación pública del Ecuador. Lee los datos abiertos del SERCOP (OCDS): 2.251.027 procesos entre 2015 y 2026. Calcula indicadores de riesgo con reglas documentadas y muestra, para cada proceso, el valor, el umbral y el campo de origen. Un conjunto de agentes con modelos de lenguaje reúne evidencia adicional de fuentes públicas, y una caja de preguntas responde solo con hechos almacenados. Veedor no acusa ni detecta corrupción: un indicador solo señala que un dato es atípico según una regla. No muestra personas naturales. Su puntaje no logró predecir la única lista externa con la que se probó (AUC 0,447; el azar es 0,5), y eso se dice sin rodeos. Funciona en local con Docker Compose y aún no está desplegado. Los datos no están en el repositorio; la guía para construirlos está en este archivo y en `docs/DEPLOYMENT.md`.

## Data sources and licences

All data is public and was retrieved on 2026-11-16 ([DATA_SOURCES.md](docs/DATA_SOURCES.md)). SERCOP open contracting data (via the Open Contracting Data Registry): CC BY 3.0 EC. SRI registry and "empresas fantasmas" list, and Superintendencia de Compañías directory and financials: licence not stated. "Not stated" is not a statement that reuse is unrestricted; confirm terms before redistributing data or derived tables.

Veedor muestra indicadores de riesgo calculados sobre datos públicos. No constituyen acusaciones ni determinan responsabilidades. (Veedor shows risk indicators computed on public data. They are not accusations and do not determine responsibility.)

## Licence and contact

Code: MIT, see [LICENSE](LICENSE). Contributions: [CONTRIBUTING.md](CONTRIBUTING.md).

Luis Figueroa ([github.com/DweskZ](https://github.com/DweskZ)), creator of EcuDataMCP.
