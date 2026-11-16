# Investigator agent

Builds a dossier draft for one process (`ocid`). A human reviewer is expected to read it before any use.

## What the model can and cannot influence (constrained generation)

The model does not write text about facts. It receives a **catalogue** of facts (`id`, section and the
exact sentence the renderer will write) and returns a **plan**:

- the order of fact ids inside each section, and which context facts to include (selection, ordering,
  emphasis);
- the order of signal codes in the summary;
- at most one connective per section from a closed set (`domain/dossier/plan.py: CONNECTIVES`);
- at most one reviewer note from a closed set of neutral framings (`REVIEWER_NOTES`).

`render_plan` writes every sentence from the same templates as template mode. A plan with an unknown id,
an unknown section, more than one connective, a free-text key or free text where an id belongs is
rejected (`PlanError` / schema validation) and counts as a failed attempt; after two failed attempts the
template is used.

What the model **cannot** do: write or rephrase any sentence, add, change or compute a figure, name an
entity, add a judgement, drop a risk signal (signals can only be reordered), touch the limitations
section, or add a source. It can hide context facts (for example, the comparative statistics) and choose
emphasis, so it can change what a reviewer reads first. That is the whole of its influence. This trades
expressiveness for safety: the prose is less fluent than free generation, and the plan is no better than
the model's judgement about relevance.

The rendered text still goes through the grounding verifier (defence in depth; it should always pass).

## Threat model

Untrusted input: process descriptions, enquiry text, supplier and buyer names, registry activity text and
every string inside signal evidence. Third parties write them, so an attacker can plant instructions in a
tender description ("ignora las instrucciones anteriores...").

Defences, in order of importance:

1. **Output verification (the real defence).** Whatever the model returns goes through
   `domain/dossier/grounding.verify`: every number, date, RUC, code and capitalised name must exist in the
   evidence pack, forbidden wording is rejected, and free text may only appear as a verbatim `« »` quote of
   the data. After two failed attempts the deterministic template is used. Unverified text is never stored
   (`finalize` raises `GroundingError`).
2. **Least privilege.** The LLM node has no tools and no access to the lake, files, network or settings.
   All data gathering (`load_evidence`, `assess_signals`) is deterministic code that runs before the model.
   The model turns a facts JSON into prose. Its output is parsed as data and never executed or used as a
   query, path, URL or tool argument.
3. **Prompt construction.** Fixed system prompt (`prompts/`). Untrusted strings travel only inside a JSON
   document between `<datos_no_confiables>` tags, with control characters removed and lengths capped;
   `<` and `>` are escaped so a value cannot forge the closing delimiter. The prompt states that the block
   is data, not instructions.
4. **Structured output.** The reply must be a JSON object that validates against `schema.LLMNarrative`
   (fixed keys, `extra="forbid"`). The limitations section is always written by code. A reply with a link or
   a verbatim run of the system prompt is rejected, not repaired. Sources are attached by code.
5. **Bounded execution.** At most 2 LLM attempts, request timeout and output-token cap in
   `infrastructure/llm`, graph recursion limit, and any provider error degrades to the template.
6. **Observability.** Every run appends a `Trace` to `data/traces/investigator.jsonl`
   (`veedor dossier traces --summary`).

Known limits: the verifier checks membership, not meaning (two pack values swapped in a sentence pass), and
only capitalised names are detected. Natural persons are masked before the pack is built.

## What the verifier covers and what it does not

Checked in every text (summary and sections): numbers, percentages, dates, RUCs, process and CPC codes,
Spanish number words (dos to cien), capitalised names, forbidden wording, and `« »` quotes (verbatim excerpts
of the data, or a grounded value such as a date).

**Figure binding.** When a figure directly follows a known label phrase (only fillers such as `de`, `fue`,
`USD`, `:` or `(` in between), it must be that label's value. Labels and values are built from the pack in
`domain/dossier/bindings.py`: presupuesto referencial, monto adjudicado, ingresos (del año del proceso, más
recientes, reportados), por un total de (history), relación monto/presupuesto, proporción de procesos con un
solo oferente, mediana de la relación, número de oferentes, mediana de oferentes, fecha de adjudicación / de
firma / inicio y cierre de ofertas / inicio de actividades / fecha de suspensión, primera y última
adjudicación previa. A label whose pack value is null rejects any figure after it. The longest matching
label wins.

**Still uncovered**
- A figure that does not directly follow a known label (for example `... equivale a 5 veces ...`) is checked
  by membership only: any pack number passes, even a wrong one.
- Labels outside the list above are unbound; a swap between two unlabelled figures passes.
- Only capitalised names are detected; an invented name written in lowercase passes.
- Meaning is not checked: the verifier cannot tell that a true figure is used in a misleading sentence, or
  that a claim ("el proveedor no existe") follows from the data.
- Number words above veinte except the tens and `cien` are not read; `un/uno/una` are never checked.
- Text inside a verbatim quote is data and is not checked beyond the unsafe-text screen (forbidden wording,
  links, instruction-like phrases).

## Phase 4 hardening notes

- The verifier works on NFKC-normalised text with hidden characters stripped and Cyrillic/Greek look-alikes
  folded to Latin; hidden, look-alike, fullwidth and markup characters are rejected outright.
- Forbidden wording is a stem list (accusation vocabulary and synonyms) plus an inference/intensifier list
  ("por lo tanto", "con creces"...). Entity and place names that equal a pack value verbatim are verified
  spans: they bypass the forbidden-word and number-word checks for that exact span only, and the role they
  fill (supplier vs entity) is checked. The surrounding prose is still checked.
- Counts followed by a noun (`2023 oferentes`) must be a pack value for that noun; dates after a verb
  (`Se adjudicó el`) must be that field's date; a value after `Proveedor adjudicado:` must be a pack name.
- Membership-only acceptance for a bare figure remains in the verifier for figures that follow no label or
  noun. It no longer matters for LLM output, which is rendered from templates and never free prose.
- If even the template fails verification the dossier is a facts table (`mode="template_minimal"`) with
  the reason recorded; the pipeline never raises for an existing process.

## The guarantee, stated precisely

The guarantee is **structural**, not lexical:

1. The model selects from enumerated facts (`id`s in the catalogue built from the evidence pack) and from
   closed sets of connectives and reviewer notes. Each phrase has an applicability predicate
   (`domain/dossier/plan.py`); a plan that uses a phrase that does not apply to the pack is invalid.
2. Code writes every sentence, from the same templates in template mode and LLM mode.
3. The free-text process description is **not loaded, not quoted and not offered to the model**. "Qué se
   contrató" uses the CPC classification and structured fields, plus a fixed pointer to the source
   record.
4. Plan parsing is bounded (reply size, nesting depth); any parse failure is an invalid plan (retry, then
   template). The template is verified too; if it cannot be, the dossier is a facts table
   (`template_minimal`) and, last, constant text.

The word list, the Unicode normalisation (NFKC, hidden characters, look-alike letters) and the figure
bindings are a **secondary net** behind that. Its known gaps: leetspeak or hyphenated spellings of
forbidden words ("fr4ude", "frau-de"), uncommon synonyms outside the stem list, and wrongdoing implied
without any listed word. None of these can reach a dossier through the model, because it writes no words;
they matter only for source strings that are still quoted, below.

## Source strings that are still quoted, and why each is acceptable

| String | Where | Why it is acceptable |
|---|---|---|
| CPC classification text | "Qué se contrató" | Official catalogue label, not free text typed per process; passes `safe_free_text` and the unsafe-text screen, otherwise it is replaced by an "omitido" notice. |
| SRI qualification text, resolution, challenge state | ghost-list statement, evidence | Attributed quotation of an official registry ("calificación asignada por el SRI en la resolución n.º …"), shown verbatim and screened; the sentence says when the listing postdates the process. |
| Registered economic activity and CIIU code | "Proveedor adjudicado" | Official SRI registry fields; passed through `safe_free_text`; not shown for natural persons. |
| Method, status and other short evidence strings from signals | signal "datos de respaldo" | Controlled vocabulary emitted by the signals builder; screened, length-capped, personal data masked by `mask_payload`. |
| Entity, place, supplier and signal-label names | everywhere | Verified spans equal to pack values (role-checked); natural persons and suppliers without RUC are never named. |

Everything else a reader sees is template text.

## Caching

`domain/dossier/version.py: RENDERER_VERSION` is stored in every dossier. A cached dossier with another
version (or none) is ignored and rebuilt. Bump it whenever templates, wording, masking or the verifier
change what an existing dossier would say.
