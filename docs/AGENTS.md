# Multi-agent investigation

A supervisor and five specialists gather extra evidence about a flagged process through read-only
tools, then the evidence flows through the same renderer and grounding verifier as the stage-1
dossier. Investigations are produced by the CLI and stored; the HTTP API only serves stored ones.

```bash
veedor investigate run <ocid> [--no-llm] [--offline] [--print]
veedor investigate batch --top 20 [--no-llm] [--offline] [--max-model-calls 60] [--summary-out PATH] [--force]
#   default summary file: eval/investigations_run.json; a smaller run never replaces a larger recorded one
#   unless --summary-out or --force is given
veedor investigate show <ocid>
GET /api/v1/processes/{ocid}/investigation        # stored record, masked; 404 when none; never runs anything
```

## Graph

```mermaid
flowchart TD
    A[load_evidence] --> S{supervisor}
    S -->|dispatch| C[company_agent<br/>Superintendencia de Compañías]
    S -->|dispatch| T[tax_registry_agent<br/>SRI public record]
    S -->|dispatch| H[history_agent<br/>buyer-supplier history, vector search]
    S -->|dispatch| U[audit_agent<br/>Contraloría reports]
    S -->|dispatch| Q[enquiries_agent<br/>question-and-answer stage]
    Q --> S
    C --> S
    T --> S
    H --> S
    U --> S
    S -->|queue empty, no retry due| E[assemble_evidence]
    E --> G[assess_signals]
    G --> P[write_narrative: plan]
    P --> V[verify_grounding]
    V -->|passed| F[finalize]
    V -->|failed, attempts left| P
    V -->|failed| K[fallback_template]
    K --> F
```

Each specialist is itself a LangGraph subgraph: `choose` (order the enumerated actions) then `act`
(run one action, loop). Without a model, `choose` returns the fixed default sequence.

## Agents

| Agent | Objective | Tools (allow-list) | Budget | On failure |
|---|---|---|---|---|
| Supervisor | Decide which specialists run, in what order, with a reason from an enumeration. | none | 6 dispatches per investigation, a specialist at most twice | Invalid model choice: one retry, then the deterministic table. |
| `company` | Facts of the company winner: incorporation date and days to the process date, subscribed capital and the award/capital multiple, legal status, last balance year, latest fiscal year with financial statements (employees, equity, assets). | `get_compania_info`, `get_financials` (EcuDataMCP) | 4 calls | Fact becomes "no disponible (la fuente no respondió)"; the source says so in the section "Investigación realizada". |
| `tax_registry` | Live SRI public record: status, taxpayer class, size category, activity start, whether it agrees with the downloaded table. | `get_sri_ruc_info` with `include_establecimientos=false` | 4 calls | Same. |
| `history` | Other awards between this buyer and supplier at any date (count, amount) and same-buyer similar purchases within ±180 days among the 50 nearest neighbours of the vector index. | `pair_awards` (lake), `similar_processes` (`find_similar` + lake dates) | 4 calls | Vector index missing: `upstream_error`/`skipped` with a closed reason; the rest still runs. |
| `enquiries` | How the question-and-answer stage went: questions registered, with text, with an answer text, days between question and answer, questions in the 3 days before the offer deadline (when the process publishes it), questions per topic (deadlines, specifications, price, requirements) by embedding similarity to fixed descriptions. | `process_texts` (local, read-only, over `data/texts`) | 1 call | Fact becomes "no disponible". |
| `audit` | Contraloría approved-report rows whose audited entity equals the buyer by a normalised-name comparison. | `list_catalogo(fuente="contraloria")`, `get_contraloria_informe` | 4 calls (catalogue + 3 files) | "No se pudo establecer" when matching is unreliable or coverage is partial; never a weak match. |

### Dispatch policy (no model)

Signal-driven specialists first, in the order of the table in `domain/investigation/policies.py`
(for example `NEW_SUPPLIER` → company, tax_registry; `BUYER_CONCENTRATION` → history, audit;
`SHORT_TENDER_WINDOW` → audit), then the remaining applicable specialists in the order company,
history, audit, tax_registry. These weights are judgement calls, like the score weights. A specialist
whose call ended in a timeout is dispatched once more (reason `retry_after_transient_failure`), only
for the failed action, within budget. Registry specialists are applicable only when the winner is a
company or public entity (RUC third digit 9 or 6) and the RUC is not masked.

### Model-driven variant

With a model configured, the supervisor and each specialist with at least two actions make one
call (plus one retry on an invalid reply). The reply is a JSON object validated against closed
enumerations (`{"dispatch": [{"specialist", "reason"}]}`, `{"actions": [ids]}`); names, reasons,
action ids and budgets are checked in code. Prompts contain only signal codes, specialist names,
action ids and counters: never an entity name, RUC or any tool text. A hard cap on model calls is
shared by the whole batch (`--max-model-calls`); beyond it every decision falls back to the policy.

## What the model can and cannot influence

Can: the order and subset of specialists (within the enumerations and budgets), the order and
subset of a specialist's actions, and, as in stage 1, the plan of the dossier (which facts, order,
one connective, one note). Cannot: write any sentence, pass any argument to a tool, name a target
that is not `winner`, `buyer` or `process`, add a tool, exceed a budget, hide the section
"Investigación realizada" (the plan cannot name it) or any failure listed in it, touch the
limitations section, see a string that came from a tool.

## Threat model for tool results

Tool results are untrusted data (a registry, a PDF-derived CSV and an upstream web page are all
writable by third parties).

1. **Allow-list**: `ToolRunner` refuses any tool not in the specialist's list (logged as `skipped`,
   reason `tool_not_allowed`); it is the only code path that calls a backend.
2. **Arguments are built by code** from the pack (`targets.py`), after strict patterns (RUC,
   ocid). The one value that originates in a result is a Contraloría file id: it must match
   `^[0-9]{1,6}$` and come from a catalogue entry whose label starts with "Informes aprobados".
3. **Typed parsing**: every result is validated by a pydantic model that declares only the fields
   used, ignores all others (a legal representative's name, address and phone are never declared,
   so they are dropped at validation), caps string lengths and sizes, and checks that the returned
   RUC equals the requested one. A failure is `invalid_result`.
4. **Closed vocabularies**: legal status, SRI status, taxpayer class, size category and report type
   are mapped to enumerations; anything else becomes `other`. Numbers and dates are parsed, not copied.
5. **Free text**: the only free string kept is a Contraloría report title, screened (personal-data
   masking, forbidden-wording and instruction screens), capped, shown as an attributed quotation in a
   fact the model catalogue replaces with `«[cita de la fuente omitida]»`. Report entity names are
   used only for comparison in code.
6. **Natural persons**: no registry lookup for them; names of legal representatives are never
   declared, stored, shown, logged or sent to a model; derived facts hold counts and flags only. The
   store refuses to write a record containing a natural-person RUC or a cédula (the record is stored
   as `withheld`). The scan (`domain/investigation/identifiers.py`) walks every value and every key,
   normalises NFKC, Unicode digits and zero-width characters, accepts single separators between
   digits, and skips only the keys in `NON_IDENTIFIER_KEYS` (numeric counters and offsets). Company
   and public-entity RUCs are allowed. Contraloría report numbers must match `REPORT_ID_PATTERN`
   (office code, sequence, year), otherwise they render as "número de informe no disponible".
7. **Logs and telemetry** hold ocid, specialist, tool, outcome, counts and durations only; MCP server
   logs are sent to `/dev/null`; error texts are read only to choose a closed reason and are dropped.
8. The grounding verifier still checks every sentence; new facts have bindings for their labelled
   figures (capital, equity, assets, employees, accumulated amount, days, multiples).

## The Contraloría objective, and its limit

`get_contraloria_informe` returns at most 200 rows per file and flags `truncated: true`; the
catalogue lists 8 approved-report files for 2022-2024. Matching is exact on a canonical key (accents,
case, punctuation, filler words, "GAD / Gobierno Autónomo Descentralizado / Municipio" variants
collapsed; no prefix or containment) and a key shared by two buyers in the data is ambiguous and
never matches. The audit specialist reads 3 files (budget), so it can confirm "at least N reports"
but cannot rule any out: the usual statement is "no se pudo establecer", with the rows examined.

## Stored record

`data/investigations/<ocid>.json`: specialists run (reason, who decided, outcomes, fact ids added),
the tool log (tool, target reference, start/end, duration, outcome, attempts, closed reason), the
facts added, the final dossier and model usage (calls, tokens, rejected choices). No identifiers of
targets are stored.

## Rules added after the independent review

- **Privacy guard.** The store refuses a record only when a *string value* holds a natural person's RUC
  as a whole token (a `.`/`,` next to the digits makes it a number, not an identifier). A genuine hit
  does not crash: the record is stored with `withheld = "personal_data_guard"`, no dossier and no
  fact list; the CLI exits cleanly. Floats are rounded where they are produced (amounts to cents,
  grounding-report values to 4 decimals).
- **File names.** `data/investigations/<sha256(ocid)>.json` (the ocid stays inside the record), so
  every real identifier works; the CLI only rejects an empty, over-long or control-character id.
  The dossier cache keeps readable names for safe ids and hashes the rest.
- **Fiscal year.** Financial figures come from the latest fiscal year strictly before the process
  year, and the sentence says which year; if none exists it says so.
- **Plausibility** (`domain/investigation/bounds.py`): dates 1900-01-01 to the day of the query,
  amounts up to USD 1e12, 1 to 1,000,000 employees; anything else renders as "no disponible (valor
  fuera de rango en la fuente)" and the tool call gets the reason `out_of_range`. A zero is missing
  data and is never rendered as a reported figure (also the stage-1 revenue lines).
- **Snapshots.** Legal status and subscribed capital are labelled "a la fecha de la consulta" and
  "no es necesariamente el vigente al momento del proceso"; the award/capital multiple says it uses
  today's capital; a multiple under 0,01 is written "menos de 0,01 veces".
- **Contraloría.** Approval date and audited period are read (both header spellings) and each report
  says whether the period includes the process date; reports are grouped as includes / does not
  include / period not available.
- **Similar purchases.** Similarity floor 0,75 (the lower quartile, 0,745, of 1.175 same-buyer top-50
  similarities measured on the 25 highest-risk processes; median 0,81; a judgement call). The fact
  reports how many neighbours passed it and says "descripción del objeto" only if the query and every
  counted neighbour were embedded from description text, otherwise "clasificación del objeto".
- **Lookups** report consulted files (`calls`) and retries separately.
- **Dispatch.** A repeat dispatch of a specialist is honoured only when its previous run ended in a
  timeout; otherwise it is ignored.
- Node names are registered with the telemetry vocabulary from the graph's own node list.

## Known limits

- Live data come from an unofficial MCP server over public sources; schemas can change. The SRI tool
  fails with HTTP 500 unless establishments are excluded (we exclude them); other SRI outages are
  recorded as failures.
- The first `get_compania_info` call loads a ~230k-row directory (about 25 s).
- "Legal representative also represents another bidder" was not built: it needs one registry call
  per tenderer, beyond the 4-call budget.
- The legal status and capital come from a snapshot directory; status is not the status at award time.
- Similar-purchase counts depend on the vector index and are bounded by the 50 neighbours examined.
- No model behaviour was reviewed adversarially with a real model beyond one batch of 10.

## Enquiries specialist

`enquiries_agent` runs **only in the CLI investigation flow**: its tool reads `data/texts/process_texts.parquet`, which is unmasked and is not mounted in the API container. The tool returns numbers only (counts, dates, topic counts); no text reaches the pack, the dossier, a model or the stored record, which keeps derived counts and dates (`InvestigationRecord.facts`). It applies when the process registered at least one question (`processes.n_enquiries`). The supervisor table dispatches it for `SHORT_TENDER_WINDOW`, `SINGLE_BIDDER` and `RECURRING_COBIDDERS`, and last in the baseline order. "Answered" counts only answers with published text (bare formulas such as "Aclaración" are not stored), so it is a lower bound; the sentence says so. The topic floor (0.40) and the late window (3 days) are in `domain/investigation/enquiry_topics.py`: judgement calls, the floor chosen from the similarity distribution of real questions (calibration below). New fact templates (`investigation.enquiries.*`) have applicability predicates, bindings for their day counts, provenance, and are covered by the "every enumerated phrase renders and verifies" test.

## Question answering flow

```mermaid
flowchart TD
    Q[question] --> V{screen: 3-300 chars, one question, no control characters}
    V -->|invalid| R422[422, never echoed]
    V --> I{intent}
    I -->|judgement, person, instruction, payload| F[fixed sentence]
    I -->|answerable| P[evidence pack: dossier sentences + stored investigation + stored quotes, only when VEEDOR_QUOTES_ENABLED]
    P --> E[embed question; score intents: nearest prototype fused with a weighted lexicon; quotes by cosine]
    E --> M{model configured and budget left?}
    M -->|no| T[facts of the winning intent, if it has facts here, clears the floor and beats oos]
    M -->|yes| S[one structured call: ids from the candidate set]
    S -->|invalid, failure, timeout| T
    S -->|valid| C[ids in catalogue order]
    T --> C
    C --> N[render: dossier sentences + attributed quotes]
    N --> G{grounding verifier}
    G -->|pass| A[answer]
    G -->|fail| U[fixed unavailable sentence, counted]
```

**Retrieval without a model** (`domain/qa/intents.py`, `domain/qa/ranking.py`). The question is not compared with the wording of
the fact keys; it is scored against 33 *intents* (kinds of question: winner, amounts, tenderers, history, signals, ... and `oos`, what the stored evidence
never answers). Per intent: the embedding similarity to the nearest of several differently worded prototype questions (plus the old key phrases) and a
noisy lexical score of accent-folded stems (`ganó`, `ganador`, `adjudicatario`; `quien~ganó` allows words in between; a question of two content words
counts its terms 1.5 times), mixed convexly (`lexical_weight`). The decision is made over all intents: if `oos`, or an intent whose facts this process lacks
(no investigation stored, no company winner), scores within a margin of the best intent that has facts, nothing is stated. The facts of the winning
intent are stated, as a group where the answer is a group (every fired signal for "which signals", both relation facts for the history; a named signal
is matched by the distinctive words of its label). A second intent within `second_gap` is added when `k` is 2. The eight numbers are in
`Thresholds` (`domain/qa/selection.py`) and are chosen by `veedor evaluate qa` on the tuning half of the processes with the original and
the development phrasings; the held-out phrasings (`evaluation/qa/heldout.py`) are never used for tuning. With a model, the same scores rank the 12 candidates
it is shown. `AskService(retrieval="legacy")` keeps the earlier key-phrase retrieval only so the evaluation can measure against it. The model never
writes prose either way: the answer is the facts' dossier sentences. The first question after a start pays for embedding the prototypes (about 1 to 3 s with
the local model, once per process); after that retrieval takes about a millisecond.

What each control does, and what stays open, is in `docs/SECURITY.md` ("Question answering"): the model only picks ids (prompt injection can at most select true facts of this process), it never sees quotes or text from the data (exfiltration of third-party text), and rate limits, a daily budget, a token cap and a timeout bound the cost. Residual limits: the screen is heuristic; limits are per worker; the retrieval is only as good as its prototypes, lexicon and a static word-vector embedding (see docs/EVALUATION.md for measured recall by phrasing set and what stays weak); behaviour of a real model against a hostile question was measured on a small set, not reviewed adversarially by a third party.

### Topic floor calibration (measured)

A random sample of 20,000 real questions (seed 42) was embedded and each assigned to its closest topic. The proxy label is a lexical stem family per topic (deadlines: plazo, prórroga, fecha, días, ampli-, cronograma; specifications: especific-, característic-, marca, modelo, ficha, medida, norma, cantidad; price: precio, presupuesto, valor, costo, pago, anticipo, reajuste; requirements: requisito, experiencia, certific-, document-, formulario, descalific-, personal técnico). Rule: the smallest floor on a 0.05 grid at which, for every topic, the stem rate among the questions assigned to it is at least twice the base rate of that stem family over all questions. Base rates: 14.0 %, 29.2 %, 13.0 %, 34.1 %. At 0.40 the stem rates are 59.6 %, 61.4 %, 90.1 % and 84.8 % (4,101 of 20,000 questions get a topic); at 0.35 specifications reach 55.3 %, under twice its base, so the floor is 0.40. It is a ranking aid chosen from a distribution, not a finding about any question.
