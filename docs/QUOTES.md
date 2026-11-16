# Quotes from the process's own text, and provenance of every fact

A visitor on a process page can see (1) where each fact comes from and (2) a few verbatim quotes from the
text the process itself published. This file documents what is quoted, from which fields, how a passage
earns the right to be shown, what was measured and what is still not guaranteed.

Quotes are context, not proof. A quote sits next to a signal because its **meaning is close to the topic
of that signal** (an embedding similarity), not because it shows that the signal is a problem.

## What is quoted, and from where

The SERCOP open data has **no documents and no document links**. A quote therefore never comes from the
tender documents (pliegos, términos de referencia, acts): only from three fields of the published record.

| Kind | OCDS field | Written by | Table column |
|---|---|---|---|
| `enquiry_question` | `tender.enquiries[i].description` | a bidder (`oferente`) | `kind`, `source_field` |
| `enquiry_answer` | `tender.enquiries[i].answer` | the buying entity (`entidad`) | idem |
| `award_text` | `awards[i].description` | the buying entity | idem |

`veedor lake build-texts` (or `veedor lake build --texts`) extracts them in one pass over the bulk file into
`data/texts/process_texts.parquet`: `ocid, kind, seq, date, author_kind, text, source_field, truncated,
author_person`. The table stores **no author name and no RUC**; `author_person` only says that the asker of
an enquiry is a natural person or an unidentified party (see below). It holds unmasked text, so it lives in
`data/texts`, **outside** the `data/lake` folder that compose mounts into the API container (a nested
`/dev/null` mount over the file does not work on this Docker runtime, so the file is kept out of the
mounted folder instead). The data bundle script does not ship it.

Real extraction (2,251,027 releases, one pass, 142.7 s): 3,292,395 rows, 248.3 MB, in 362,515 processes with
at least one text: 1,593,811 questions, 1,346,168 answers, 352,416 award texts. Dropped while extracting
(counted, never silent): 132,461 boilerplate-only questions, 109,459 boilerplate-only answers, 811 award
texts; 118,861 + 292,768 + 24,649 exact duplicates inside one process; 2,345 texts with no letter.
Boilerplate means a bare formula such as «Aclaración», «Convalidación», «Sí», «No aplica», «Ver acta» or a
short pointer to a file that is not in the open data («Se adjunta lo solicitado»). Award texts that only
say the supplier meets the requirements are **kept** (they are the only text some processes have).

Each text is whitespace-collapsed and capped at 2,000 characters (the longest real enquiry has 1,500); a
longer one is cut at a word and flagged `truncated`. A displayed quote is cut at 600 characters at a word
boundary with an ellipsis and also flagged `truncated`.

## Which passages earn a place

For every process with at least one risk **or** context signal and at least one text
(`veedor quotes build`, idempotent, about 4 minutes for all 86,936 such processes):

1. **Eligibility** (`domain/quotes/screen.py`, applied in this order; a passage is never rewritten, a hit
   anywhere drops it whole, so no quote shows a placeholder):
   1. the *asker* of the enquiry is a natural person or an unidentified party: the whole exchange is dropped
      (question and answer), because either can address or sign that person;
   2. `safe_free_text` with the known person names of the process: natural-person and RUC-less winners,
      tenderers, award suppliers, the natural-person *enquiry askers* (read from the bulk file in memory
      only) and a natural-person buyer; honorific plus name runs;
   3. the identifier scan of `domain/investigation/identifiers.py` (natural-person RUC, valid cédula, in
      plain, dotted, dashed, spaced or Unicode-digit form);
   4. stricter personal-data cues: an honorific in any case («ing. juan»), «Señor/Señora» followed by a
      word, a professional title followed by two capitalised words, a closing or signature followed by a
      name, «Estimada María», «yo <nombre>, en mi calidad de», an e-mail address, a telephone number
      (**decision: passages with phones or e-mails are excluded**);
   5. a **name net**: two consecutive capitalised words that are both person-name tokens. The vocabulary is
      built from the data itself: tokens of at least 2 distinct natural-person names of the lake, minus any
      token the texts also use in lower case (`cruz`, `luz`). It is stored as `person_name_tokens.parquet`
      so the API applies the same list at its boundary. Names inside the process's protected names (buyer,
      companies) are ignored;
   6. the unsafe-text screen of the dossier layer (`is_unsafe_text`: accusation and inference wording, links,
      markup, instruction-like text, hidden or look-alike characters) plus an obfuscation pass (digit and
      symbol look-alikes, letters separated by spaces, dots or hyphens).
   A passage that fails is **never stored**; only counts by reason are kept.
2. **Relevance.** Each signal code has one short Spanish topic description (`domain/quotes/topics.py`).
   Eligible passages and the topics of the signals that fired are embedded with the project's local model
   (`minishlab/potion-multilingual-128M`, the same adapter as the vector index). A passage's score is its
   best cosine similarity to those topics; the winning signal is its `related_signal`.
3. **Pairs.** An enquiry is one item. If its question is selected and the entity's answer is eligible, the
   answer is the paired quote (one item, two parts). Items with a pair rank slightly higher (+0.03 in the
   ranking only; the shown similarity is the real one). An answer whose question was withheld is withheld.
4. **Floor.** Items under the floor (0.35) are not shown and counted as `below_floor`. The floor is the
   smallest step of 0.05 at which passages at or above it contain a deadline or price stem at least twice as
   often as all passages (calibration below). It is a ranking aid chosen from a distribution, not a threshold
   of truth.
5. **Selection.** At most 3 items, best first; an item whose primary passage has cosine ≥ 0.92 with one
   already chosen is skipped as a near-duplicate.

Output marts in `data/marts` (already mounted read-only): `process_quotes.parquet` (`ocid, rank, kind, text,
date, author_kind, source_field, related_signal, similarity, truncated, pair_text, pair_kind,
pair_source_field`), `process_quote_stats.parquet` (`ocid, available_total, excluded_personal,
excluded_unsafe, below_floor, n_eligible, n_quotes`) and `person_name_tokens.parquet`.

Commands: `veedor lake build-texts`, `veedor quotes build`, `veedor quotes show <ocid>`,
`veedor quotes evaluate` (writes `eval/quotes.json` and refreshes the block below).

## Measurements

<!-- BEGIN GENERATED: quotes -->
Generated by `veedor quotes evaluate` (seed 42, 2000 bootstrap resamples; intervals are 95 % percentile intervals).

**Build** (`veedor quotes build`, one run over the whole lake):

| Measure | Value |
|---|---|
| Flagged processes with at least one text | 86,936 |
| Texts screened | 716,246 |
| Quotes stored (items) | 68,553 (42,068 with a paired answer) |
| Items skipped as near-duplicates | 1,090 |
| Quotes by rank 1 / 2 / 3 | 36,345 / 19,053 / 13,155 |
| Quotes cut for display (`truncated`) | 13,232 |
| Wall time, embedding time | 252.1 s, 11.1 s (344.9 processes/s, 2841.5 texts/s) |
| Mart sizes | 11.0 MB quotes, 0.83 MB per-process counts |

**Coverage**: share of flagged processes with at least one quote, by signal. A process counts under every signal that fired on it.

| Signal | Flagged | With text | With a quote | Share of flagged |
|---|---|---|---|---|
| `BUYER_CONCENTRATION` | 3,231 | 3,229 | 1,196 | 37.0 % |
| `CONTRACT_VS_COMPANY_SIZE` | 5,957 | 5,957 | 3,136 | 52.6 % |
| `CONTRACT_VS_COMPANY_SIZE_SAME_YEAR` | 614 | 614 | 257 | 41.9 % |
| `GHOST_COMPANY_LISTED_LATER` | 44 | 43 | 23 | 52.3 % |
| `LOW_SAVING` | 4,289 | 4,285 | 1,852 | 43.2 % |
| `NEW_SUPPLIER` | 1,307 | 1,304 | 626 | 47.9 % |
| `RECURRING_COBIDDERS` | 11,417 | 11,415 | 5,751 | 50.4 % |
| `REPEATED_DIRECT_AWARDS` | 3,361 | 3,334 | 438 | 13.0 % |
| `SHORT_TENDER_WINDOW` | 3,092 | 3,088 | 451 | 14.6 % |
| `SINGLE_BIDDER` | 59,268 | 58,628 | 24,444 | 41.2 % |
| `SUPPLIER_NOT_ACTIVE` | 16 | 15 | 2 | 12.5 % |
| **All flagged** | 87,617 | 86,936 | 36,345 | 41.5 % |

**Exclusions** (text rows; an answer whose question was withheld is `question_excluded`):

| Category and reason | Rows |
|---|---|
| personal / asker_person | 88,918 |
| personal / email | 2,437 |
| personal / honorific | 1,017 |
| personal / identifier | 79 |
| personal / name_or_identifier | 5,808 |
| personal / phone | 557 |
| personal / placeholder | 4 |
| personal / probable_person_name | 1,756 |
| personal / question_excluded | 70,103 |
| personal / salutation | 1,697 |
| personal / self_or_address_line | 19 |
| personal / signature | 595 |
| unsafe / obfuscated_wording | 1,527 |
| unsafe / question_excluded | 8,798 |
| unsafe / unsafe_text | 23,350 |
| **personal data (total)** | 172,990 |
| **unsafe wording or markup (total)** | 33,675 |

**Similarity floor** (0.35). Calibration sample: the first 6,000 flagged processes by ocid (23,429 eligible passages; best similarity to a fired signal: median 0.306, p90 0.5). Rule: smallest floor on the 0.05 grid whose stem rate is at least twice the base rate. Base rate of a deadline or price stem among passage-signal pairs: 12.1 %.

| Floor | Passage-signal pairs | Stem rate | Lift over base |
|---|---|---|---|
| 0.1 | 1,221 | 14.3 % | 1.18 |
| 0.15 | 1,097 | 15.1 % | 1.25 |
| 0.2 | 927 | 15.3 % | 1.26 |
| 0.25 | 692 | 17.1 % | 1.41 |
| 0.3 | 469 | 21.3 % | 1.76 |
| 0.35 | 234 | 30.8 % | 2.54 |
| 0.4 | 93 | 53.8 % | 4.44 |
| 0.45 | 37 | 73.0 % | 6.02 |
| 0.5 | 12 | 83.3 % | 6.88 |

**Retrieval check without labels** (processes outside the calibration sample; the selected quote of the signal against one random eligible item of the same process):

| Signal and stems | Processes | Selected quote | Random eligible item | Difference |
|---|---|---|---|---|
| `SHORT_TENDER_WINDOW` (plazo, prórroga, días, fecha, ampli-) | 222 | 38.7 % [32.4, 45.1] | 16.7 % [11.7, 21.6] | +22.1 points [+15.3, +28.8] |
| `LOW_SAVING` (precio, presupuesto, valor, monto, descuento, costo, puja, rebaja) | 1,561 | 51.8 % [49.3, 54.3] | 29.6 % [27.3, 31.9] | +22.2 points [+19.5, +24.8] |

**Privacy sweep over every stored quote** (110,621 passages in 36,345 processes):

| Check | Hits |
|---|---|
| Identifier scan (natural-person RUC, valid cédula) | 0 |
| Name search: two consecutive tokens of any natural-person or RUC-less party, tenderer, supplier or enquiry asker of the same process, either order (67,806 names) | 0 |
| Telephone numbers | 0 |
| E-mail addresses | 1 |
| «Señor/Señora» followed by a name | 0 |
| Passages with a pair of rarer given-name or surname tokens (candidates, mostly places and institutions) | 17 |
<!-- END GENERATED: quotes -->

## Reading 30 quotes myself

I read a random sample of 30 stored quotes (seed 42, across signals) and classified each by whether its
text is about what the topic of its `related_signal` describes. **10 relevant, 13 plausibly relevant,
7 not relevant.** Many «plausibly relevant» are generic award texts («Por cumplir con los requisitos…») or
enquiries about the conditions for presenting an offer, which fit the broad topics of `SINGLE_BIDDER` and
`RECURRING_COBIDDERS` only loosely. The seven that do not fit were about other things (a motor and
reducer asked about under `LOW_SAVING`, the delivery time or the start date of a policy under
`SINGLE_BIDDER`, a payment schedule under `CONTRACT_VS_COMPANY_SIZE`). In this sample no quote contained a
personal name, identifier, telephone number or e-mail address. One earlier version of the build did: «el
personal técnico Señor <apellido> <nombre>» appeared in a sample read before the «señor/señora» cue was added,
which is how the cue and the name net came to exist; the numbers above are for the final build.

Five examples as shown (entity names replaced by a placeholder):

1. `SINGLE_BIDDER`, award text, similarity 0.42: «La oferta cumple con el requerimiento de la Entidad y por
   ser la unica oferta economica mas baja que se ajusta al presupuesto referencial»
2. `SINGLE_BIDDER`, question, similarity 0.57 (relevant): «Para cumplir con los requisitos mínimos solicitados,
   como experiencia específica mínima solicitada, por favor confirmar si los oferentes podemos presentar
   actas de entrega-recepción, facturas, contratos en ejecución y/o contratos terminados […]?» with the
   paired answer: «Estimado oferente, para dar cumplimiento con los requisitos mínimos […] los oferentes si
   podrán presentar actas de entrega/recepción o facturas o contratos terminados […]»
3. `RECURRING_COBIDDERS`, question, similarity 0.60 (relevant): «Estimada entidad, podemos concursar con el
   certificado IATA de nuestros consolidadores?? adicional este item es punto para descalificacion?? o solo
   vale 5 puntos extras?» with the answer: «No es posible presentar el certificado IATA de los consolidadores,
   remítase a la aclaración No. 4 […]»
4. `CONTRACT_VS_COMPANY_SIZE`, question, similarity 0.54 (plausibly relevant): «FAVOR PRESENTAR LA
   CONVALIDACIÓN DE ERRORES DE ACUERDO A LO DESCRITO A DETALLE EN EL OFICIO ADJUNTO. GRACIAS» with the
   answer: «En atención a la Notificación de Convalidación de Errores […], [empresa] presenta la
   documentación requerida […] Se adjuntan los documentos correspondientes al personal mínimo y al equipo
   mínimo […]»
5. `SINGLE_BIDDER`, question, similarity 0.39 (not relevant): «FAVOR CONFIRMAR LA FECHA DE INICIO Y TERMINACIÓN
   DEL PROGRAMA DE SEGUROS» with the answer: «El plazo para la entrega de la póliza es de 10 días contados a
   partir de la adjudicación […]»

## The API

* `GET /api/v1/processes/{ocid}/quotes` returns `{ ocid, items: [{ kind, text, date, author_kind,
  source_field, related_signal, related_signal_label_es, similarity, truncated, pair: {kind, text,
  source_field} | null }], available_total, omitted: { personal_data, unsafe, below_relevance }, note_es }`.
  404 for an unknown process, 200 with empty `items` when there are none, 503 when the mart is not built.
  Every stored passage is screened **again** with the same functions and the process's current names; one
  that fails now is dropped and counted in `omitted`. `available_total` is the number of texts the process
  has; `omitted.below_relevance` counts eligible texts under the floor; texts that were eligible and relevant
  but not among the best three are in none of the three counters.
* `GET /api/v1/processes/{ocid}/provenance` returns the sources (name, publisher, licence, retrieval date,
  URL) and one entry per fact shown on the process page, with the exact field of origin, whether it is
  derived (with the formula in Spanish) and how to check it. `docs/SECURITY.md` lists the controls.
* `GET /api/v1/processes?min_amount=&max_amount=` filters on the awarded amount (inclusive, USD).

## Limits

* Quotes come from the **published record** (questions, answers and award texts), **not from tender
  documents**: the open data has none.
* Relevance is **embedding similarity** to a topic description. It is not a judgement about the process; a
  quote can be about something else.
* Text written by third parties is shown **verbatim and attributed** (`author_kind`, `source_field`); it is
  not Veedor's wording. The screens refuse accusation and inference wording, so a bidder's complaint that
  uses such words is not shown; this removes legitimate text as well (see the exclusion counts).
* Personal data: the screens are heuristics. The sweep above found 0 identifiers, 0 party or asker names,
  0 telephone numbers and no e-mail address (its single «hit» is the inclusive-language token «otr@s» in a
  sentence, not an address). It cannot see a person who is not a party and not an enquiry asker, is written
  without an honorific and has rare given names and surnames. Its weakest check (a pair of capitalised
  words that are both tokens of *any* natural-person name in the lake) lists 17 passages; reading them, two
  name a person (a shareholder in a list of partners and an official in an address block) and the rest are
  places, hospitals and companies named after people. That is an estimate of what remains (about 2 in
  110,000 passages), not a guarantee. Do not describe the quotes as free of personal data.
* The name net has false positives on purpose: a hospital or a street named after a person is dropped
  unless it is one of the process's own buyer or company names.
* The unmasked text table and the raw bulk file are not for publication. The quotes marts contain only
  passages that passed the screens.
* `author_kind` follows the field, not a check of who wrote it: a question field sometimes holds a text written
  by the buying entity or by the very company that is named in it.
* The topic descriptions are one judgement call per signal; the floor was calibrated on two topics only
  (deadlines and prices) because they are the two with an obvious lexical signature.
