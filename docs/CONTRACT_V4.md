# Veedor — build contract, stage 5 (question answering, evaluator, enquiries specialist)

Binding for this stage. `docs/CONTRACT.md`, `docs/CONTRACT_V2.md` and `docs/CONTRACT_V3.md` still
apply in full (no invented data, indicators never accusations, natural persons never stored,
shown, traced or sent to a model, parameterised SQL only, no `.env*` reads or edits, no git
commands, `rg`/`fd`/`bat`/`sd`/`eza`, no `ruff format` outside your own files, no `uv add`).
Read `docs/REVIEWS.md` and `docs/QUOTES.md` first.

## One deliberate change to an earlier rule

Until now the HTTP API never called a language model. This stage adds ONE route that may:
`POST /api/v1/processes/{ocid}/ask`. Every other route keeps the old rule, and a test must
assert that no other route can reach the model client. The route is **off by default**
(`VEEDOR_ASK_ENABLED=false`) and works without any model (retrieval-only mode) when enabled
without a key.

## 1. Question answering over one process (owner: agents)

Purpose: a visitor asks a question in plain Spanish about one process and gets an answer made
only of stored evidence, each sentence linked to its source.

Design — the stage-1 principle is kept: **the model never writes prose.**

```
question → screen → retrieve (embeddings, no model) → select (model picks ids, or top-k without model)
        → render (code writes every sentence from fact templates) → verify (grounding) → answer
```

- **Evidence pack**: the process's facts already rendered by code (process facts, fired
  signals with their inputs, comparison context, registry facts about a company or public
  entity winner, stored investigation facts) each with a stable `fact_id` and its provenance
  entry; plus the stored quotes for the process (`quote_id`).
- **Screen**: length 3–300 characters, control characters rejected, one question per call. The
  question is untrusted text: it is never used as SQL, a path, a URL, a tool argument, or a
  template. It is never stored or logged in clear (store a salted hash, its length and the
  outcome) and never put in a span attribute.
- **Retrieve**: embed the question with the project's local model; rank fact sentences and
  quotes by cosine similarity; keep a bounded candidate set.
- **Select**: with a model configured, the model receives the question and the candidate
  facts (code-rendered sentences only) and returns a JSON object constrained by schema:
  `{ "answerable": bool, "fact_ids": [enumerated], "reason": one of an enumeration }`.
  Quotes are third-party text and are **never sent to the model**; relevant quotes are
  attached by similarity alone. Without a model, selection is top-k above a measured floor.
- **Render**: the answer is the selected facts' sentences in a fixed order, followed by the
  attached quotes as attributed quotations. If nothing clears the floor or the model says not
  answerable: a fixed sentence saying the stored evidence does not answer that, and what kinds
  of question it can answer. Questions asking for a judgement ("¿hubo corrupción?", "¿es
  culpable?") always get the fixed sentence that Veedor describes records and does not judge.
- **Verify**: the existing grounding verifier runs on the rendered answer; a failure returns
  the fixed "no disponible" answer and is counted.
- **Abuse and cost controls**: per-IP rate limit and a global daily request budget (both
  configurable, conservative defaults), a hard token cap per call, a timeout, at most one
  model call per question, an in-memory cache keyed by (ocid, normalised question hash, data
  build). When the budget is spent the route answers in retrieval-only mode, not with an error.
- **Response**: `{ ocid, answerable, mode: "model" | "retrieval", sentences: [{ text, fact_id,
  source_id, source_field }], quotes: [{ quote_id, text, kind, date, source_field }],
  note_es }`. Masked like every response.
- CLI: `veedor ask <ocid> "<question>"`.
- Telemetry: spans and counters for mode, answerable, grounding result, tokens. No question text.

## 2. Evaluator (owner: agents)

Measured, not asserted. `veedor evaluate qa [--with-model] [--n N]` writes `eval/qa.json`
(numbers only) and a generated section in `docs/EVALUATION.md`.

- **Answerable set**, generated from the data, not hand-written per process: question
  templates in several phrasings per fact type ("¿cuántos oferentes hubo?", "¿quién compró?",
  "¿cuánto se adjudicó?", "¿por qué tiene esta señal?" …) applied to a random sample of
  processes, with the expected `fact_id`s known by construction.
- **Unanswerable set**: questions whose answer is not in the pack (facts absent for that
  procedure, things the data does not contain) — expected outcome: abstain.
- **Adversarial set**: prompt-injection attempts, requests to name or judge people, requests
  for an accusation, requests to reveal instructions, markup and link payloads, mixed-language
  and Unicode evasions — expected: abstain or answer only from enumerated facts; success of an
  attack is any output text not produced by a template, any natural-person datum, any
  accusation vocabulary.
- **Metrics**: recall and precision of selected facts on the answerable set; abstention rate
  on the unanswerable set; attack success count; grounding pass rate; latency; tokens per
  question when a model is used. Bootstrap confidence intervals. Retrieval-only and model
  modes reported side by side. Report the numbers even when they are poor.
- A small fixed subset runs in the test suite and in CI in retrieval-only mode with thresholds
  taken from the measured run (a regression gate, not a quality claim).

## 3. Enquiries specialist (owner: agents)

A fifth specialist, `enquiries_agent`, objective: describe how the question-and-answer stage
of the process went. Tools: read-only access to the process's stored texts. Facts are computed
by code only — number of questions, how many were answered, days between question and answer,
how many questions arrived in the last days before the deadline when that date exists, and how
many fall into each topic (deadlines, specifications, price, requirements) by embedding
similarity to fixed topic descriptions. No free text reaches a model or the dossier; the
dossier may show counts and dates. New fact templates join the catalogue with applicability
predicates and the "every enumerated phrase renders and verifies" test. The supervisor's rule
table dispatches it when the relevant signals fire and texts exist.

## 4. Web (owner: web, after the API exists)

On the process page, a "Pregunta sobre este proceso" box: a few suggested questions as chips,
a text field, the answer rendered as sentences each with its source marker, attached quotes in
the quotation style, the mode stated ("respondido con un modelo" / "respondido por búsqueda"),
and a fixed line that the answer uses only this process's stored evidence. Hidden when the
route is disabled. Answer text rendered as text only. Keyboard and screen-reader friendly.

## Acceptance (the orchestrator will run these personally)

1. `uv run ruff check src tests scripts` clean; `uv run pytest -o addopts=""` all pass.
2. The route is 404 when disabled; with it enabled and no key it answers in retrieval mode.
3. `veedor evaluate qa` in both modes over real data; `eval/qa.json` exists; attack success
   count reported (target 0) with every successful attack listed by category.
4. A privacy sweep: across the evaluation run, no natural-person name or identifier in any
   answer, log line, trace or stored record; no question text stored in clear.
5. Twenty real investigations rerun with the fifth specialist complete without exception.
6. Smoke test extended and passing; compose passes the model key from the environment to the
   API service only when ask is enabled, and nothing secret is written to any file or image.
