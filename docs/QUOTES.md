# Quotes from the process's own text, and provenance of every fact

A visitor on a process page can see (1) where each fact comes from and (2) a few verbatim quotes from the
text the process itself published. This file documents what is quoted, from which fields, how a passage
earns the right to be shown, what was measured and what is still not guaranteed.

Quotes are context, not proof. A quote sits next to a signal because its **meaning is close to the topic
of that signal** (an embedding similarity), not because it shows that the signal is a problem.

## Status: disabled by default

**Quotes are off unless the operator sets `VEEDOR_QUOTES_ENABLED=true`.** With the default (`false`) the route
`GET /processes/{ocid}/quotes` answers 404, `POST /processes/{ocid}/ask` attaches no quote, `GET /meta`
reports `quotes_enabled: false` and the web hides the block. The data bundle does not contain the quotes mart
unless it is built with `--with-quotes`, which first runs the release gate (`scripts/check_quotes_privacy.py`).

Why. The fifth independent review swept all 110,579 stored passages and found natural persons named in them
(legal representatives introducing themselves, sign-offs and signature blocks, titles followed by names,
named technical staff in convalidation requests, insurance advisers with credential numbers, two passages
naming a patient, a partial mobile number, 54 passages quoting vehicle plates). The project had stated "about
2 in 110,000". That estimate came from the project's own screens finding nothing: the pattern-by-pattern
approach had failed twice and was measuring only what it already knew how to look for. The claim is withdrawn.
The screen was then rebuilt the other way round (deny by default, below), and the residual is measured by
reading, not by the screen: **of 150 passages drawn uniformly at random from the final mart, none named or identified a natural person (95 % upper bound 2.0 %; 0 of 300 over the two random rounds, 1.0 %), and none of the 150 most suspicious by heuristics that are not filters did; the bound is from a sample read by one reader, it is not a guarantee, and it leaves room for hundreds of passages.**

A second finding of the same review: 785 passages beside risk signals contained accusation-like third-party
text (rigging, "a dedo", denuncias). Those stems are now refused too (section "Allegation wording").

Nothing here is a guarantee. The numbers are upper bounds from a sample of passages I read myself, with
the sampling and its rounds stated below. Do not describe the quotes as free of personal data.

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
longer one is cut at a word and flagged `truncated`. A displayed passage has at most 800 characters (about 90 % of real questions and answers are shorter, so they are shown whole); a longer one is cut at the last sentence end inside the cap, else at a clause end, else at a word, with no ellipsis in the text, and flagged `truncated`. The flag is per part: `truncated` for the main passage and `pair.truncated` for the paired answer (a cut answer no longer marks its question as cut). The whole passage is screened before it is cut, so a cut never hides a remainder that failed a screen.

## Which passages earn a place

For every process with at least one risk **or** context signal and at least one text
(`veedor quotes build`, idempotent, about 4 minutes for all 86,936 such processes):

1. **Eligibility** (`domain/quotes/screen.py`, applied in this order; a passage is never rewritten, a hit
   anywhere drops it whole, so no quote shows a placeholder):
   1. the *asker* of the enquiry is a natural person or an unidentified party: the whole exchange is dropped
      (question and answer), because either can address or sign that person;
   2. a hash on the explicit deny list (`domain/quotes/deny.py`);
   3. `safe_free_text` with the known person names of the process: natural-person and RUC-less winners,
      tenderers, award suppliers, the natural-person *enquiry askers* (read from the bulk file in memory
      only) and a natural-person buyer; honorific plus name runs;
   4. the identifier scan of `domain/investigation/identifiers.py` (natural-person RUC, valid cédula, in
      plain, dotted, dashed, spaced or Unicode-digit form);
   5. the earlier pattern cues: an honorific in any case («ing. juan»), «Señor/Señora» followed by a word, a
      professional title followed by two capitalised words, a closing or signature followed by a name,
      «Estimada María», «yo <nombre>, en mi calidad de», an e-mail address, a telephone number;
   6. the earlier **name net**: two consecutive capitalised words that are both person-name tokens;
   7. **unsafe wording**: the dossier layer's `is_unsafe_text` (accusation and inference wording, links,
      markup, instruction-like text, hidden or look-alike characters), an obfuscation pass (digit and symbol
      look-alikes, letters separated by spaces, dots or hyphens) and the third-party **allegation stems** of
      `domain/quotes/allegation.py` (section "Allegation wording");
   8. the **deny-by-default screen** (`domain/quotes/strict.py`, rules D1 to D13 below).
   A passage that fails is **never stored**; only counts by reason are kept. Stages 3 to 6 are patterns and
   failed twice against reviewers; stage 8 is the one that carries the privacy claim, because it does not
   look for what is wrong, it admits only what it can show to be institutional.

   **Deny by default (stage 8).** After the names of the process's own companies and public entities
   (buyer, tenderers, suppliers, winners, taken from the lake and blanked out as whole strings, ignoring case
   and accents) are set aside, a passage is eligible only if **every one** of these holds:

   | Rule | A passage is refused when it contains |
   |---|---|
   | D1 `sign_off` | a sign-off or signature cue, anywhere: *atte, att, atentamente, atentos, cordialmente, cordial saludo, saludo(s), rúbrica, firma(s)/firmado/firmar…, suscrito/a, suscribe, suscribimos*, or «f.» |
   | D2 `self_identification` | *yo,*, *el/la suscrito/a*, *quien suscribe*, *en mi calidad/condición/representación*, *representado/a (legalmente) por*, *representante(s) legal(es)*, *administrador/a del contrato*, *delegado/a*, *apoderado/a*, *gerente general*, *mi nombre*, *me llamo*, *soy el/la*, *con c.i./c.c./cédula*, *portador/a*, *identificado/a con* |
   | D3 `health_reference` | *paciente(s)*, *historia(s) clínica(s)* |
   | D4 `plate` | an Ecuadorian plate shape: three capitals and 3 or 4 digits (`PBA-1234`, `PBA 123`), two capitals, 3 digits and a capital (motorbikes), or `abc-1234` in lower case with a hyphen. **No exemption**: `USD 1500` and `ISO 9001` match and are refused |
   | D5 `credential_id` | *licencia, registro, matrícula, certificado/a, certificación, cédula, pasaporte, placa, credencial, Senescyt, acreditación, colegiatura, carnet, votación* followed, in the same sentence and within 40 characters, by an identifier (5 or more characters with a digit) |
   | D6 `contact` | `@`, *arroba*, a mail provider, *www*, `http(s):`, `.com .ec .net .org .gob .edu` |
   | D7 `long_number` | a run of 7 or more digits (single separators allowed) or a partial mobile `09dd…` / `+593…`; **exempt**: dates, year-codes such as `2023-0145`, a 13-digit RUC whose third digit is 6 or 9 and that ends in `001` (company or public entity), and an amount (after a currency or quantity word, or formatted `1.250.000,00`). A number that starts with 0 or 593 is never an amount |
   | D8 `title_name` | a title or its abbreviation (*ing, ingeniero/a, dr, dra, doctor/a, lic, lcdo/a, abg, abogado/a, econ, economista, arq, arquitecto/a, bqf, qf, mgs, msc, mba, phd, cpa, sr, sra, srta, señor/a/ita, tnlgo, crnl, prof, don, doña, coronel, capitán, sargento…*) followed by **any capitalised word** or by any word that is not ordinary vocabulary, with or without space or period; glued forms such as `sr.PÉREZ`; in an all-capitals passage *sr/sra/srta/señor/señora/don/doña* followed by any word |
   | D9 `name_token` | **any token of the person-name vocabulary, in any case** (`person_name_tokens`: tokens of at least 3 letters contained in at least 2 distinct natural-person names of the lake and written in lower case in fewer than 20 x (number of such names) processes, so that ordinary words that are also surnames stay words) |
   | D10 `unknown_capitalised` | in a mixed-case passage, a capitalised or ALL-CAPS word of 2 or more letters that is **not in the institutional lexicon** (below), except a sentence-opening word that is an ordinary lower-case word. A run of two or more unknown capitalised words is the special case; a single unknown surname is refused too |
   | D11 `caps_unknown_word` | in a passage written (mostly, 60 % or more) in capitals, where capitalisation carries no signal, a word of 2 or more letters that is neither institutional vocabulary nor an ordinary word: every word must be known |
   | D12 `unknown_lowercase_pair` | two consecutive lower-case words of 4 or more letters that are in neither list of the lexicon: a rare given name and surname typed in lower case ("nombre apellido") looks like this, and so does a rare technical bigram (it costs about 0.4 % of the passages). One unknown word alone is allowed: it is a typo or a term |
   | D13 entity names | (not a refusal) the process's own entity and company names are blanked before D1 to D11. Their shortened forms are **not** set aside: a name written in short form is refused like any other capitalised word |

   In addition, **the rules of the release gate are part of the screen** (`domain/quotes/gate.py`: the reviewer's seven
   rules, reconstructed from the sweep scripts, and the project's own; reasons `gate_*`), so a mart built by this
   function cannot fail the gate, which then checks the mart independently (section "Release gate").
   Another two cues were added by reading: `cédula de <word>` (a person's identity card) and a labelled
   `Nombre:` / `Apellidos:` field (reason `labelled_name`).

   **The lexicon** (`domain/quotes/lexicon.py`, stored in the mart `quote_lexicon`; no hand-written list) is
   built from the 3,292,395 texts of the lake. *Capitalised*: folded tokens written with a capital, or in
   capitals, in the middle of a sentence of a mixed-case passage in at least 40 distinct processes of at least
   10 distinct buyers (one official signing hundreds of processes of one entity is not vocabulary; "Municipal"
   is written by hundreds), and used at least 20 times more (in processes) than the number of distinct
   natural-person names containing them. This is where the province and canton names, the legal and
   procurement terms (*Pliegos, Reglamento, Contratación, SERCOP, SRI, IVA*) and the institutional vocabulary
   come from. *Lowercase*: the same rule for ordinary lower-case words. The current lexicon has 7,836 capitalised and 20,024 ordinary tokens (the person-name vocabulary: 6,992 tokens).
   Both lists exclude person-name tokens by construction, so they hold no name and are shipped with the quotes.
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
5. **Selection.** At most 3 items, best first; a passage appears **at most once per process** (as an item or as a pair: an item that repeats a shown passage, ignoring case and spacing, is skipped and the next one takes its place; an answer that repeats its question word for word is shown once); an item whose primary passage has cosine ≥ 0.92 with one
   already chosen is skipped as a near-duplicate.

Output marts in `data/marts` (already mounted read-only): `process_quotes.parquet` (`ocid, rank, kind, text,
date, author_kind, source_field, related_signal, similarity, truncated, pair_text, pair_kind,
pair_source_field`), `process_quote_stats.parquet` (`ocid, available_total, excluded_personal,
excluded_unsafe, below_floor, n_eligible, n_quotes`), `person_name_tokens.parquet` (tokens of person names; not shipped) and
`quote_lexicon.parquet` (`token, form`: institutional capitalised words and ordinary lower-case words; no names; shipped with the quotes).

Commands: `veedor lake build-texts`, `veedor quotes build`, `veedor quotes show <ocid>`,
`veedor quotes evaluate` (writes `eval/quotes.json` and refreshes the block below; `eval/quotes_before_review5.json` keeps the numbers of the build before review 5 for the before/after columns), `scripts/check_quotes_privacy.py` (release gate).

## Measurements

<!-- BEGIN GENERATED: quotes -->
Generated by `veedor quotes evaluate` (seed 42, 2000 bootstrap resamples; intervals are 95 % percentile intervals).

**Build** (`veedor quotes build`, one run over the whole lake):

| Measure | Value |
|---|---|
| Flagged processes with at least one text | 86,936 |
| Texts screened | 716,246 |
| Quotes stored (items) | 54,489 (27,079 with a paired answer) |
| Items skipped as near-duplicates | 583 |
| Quotes by rank 1 / 2 / 3 | 30,752 / 14,299 / 9,438 |
| Quotes cut for display (`truncated`) | 1,261 |
| Wall time, embedding time | 509.5 s, 5.8 s (170.6 processes/s, 1405.8 texts/s) |
| Mart sizes | 7.0 MB quotes, 0.83 MB per-process counts |

**Coverage**: share of flagged processes with at least one quote, by signal. A process counts under every signal that fired on it.

| Signal | Flagged | With text | With a quote | Share of flagged | Share before review 5 |
|---|---|---|---|---|---|
| `BUYER_CONCENTRATION` | 3,231 | 3,229 | 1,004 | 31.1 % | 37.0 % |
| `CONTRACT_VS_COMPANY_SIZE` | 5,957 | 5,957 | 2,628 | 44.1 % | 52.6 % |
| `CONTRACT_VS_COMPANY_SIZE_SAME_YEAR` | 614 | 614 | 208 | 33.9 % | 41.9 % |
| `GHOST_COMPANY_LISTED_LATER` | 44 | 43 | 18 | 40.9 % | 52.3 % |
| `LOW_SAVING` | 4,289 | 4,285 | 1,600 | 37.3 % | 43.2 % |
| `NEW_SUPPLIER` | 1,307 | 1,304 | 536 | 41.0 % | 47.9 % |
| `RECURRING_COBIDDERS` | 11,417 | 11,415 | 4,898 | 42.9 % | 50.4 % |
| `REPEATED_DIRECT_AWARDS` | 3,361 | 3,334 | 379 | 11.3 % | 13.0 % |
| `SHORT_TENDER_WINDOW` | 3,092 | 3,088 | 366 | 11.8 % | 14.6 % |
| `SINGLE_BIDDER` | 59,268 | 58,628 | 20,659 | 34.9 % | 41.2 % |
| `SUPPLIER_NOT_ACTIVE` | 16 | 15 | 2 | 12.5 % | 12.5 % |
| **All flagged** | 87,617 | 86,936 | 30,752 | 35.1 % | 41.5 % |

**Exclusions** (text rows; an answer whose question was withheld is `question_excluded`):

| Category and reason | Rows |
|---|---|
| personal / asker_person | 88,918 |
| personal / denied_passage | 4 |
| personal / email | 1,705 |
| personal / gate_r1_title_then_name | 1,105 |
| personal / gate_r2_role_then_name | 13 |
| personal / gate_r3_honorific_then_capitalised | 2 |
| personal / gate_r4_sign_off_or_first_person | 579 |
| personal / gate_r7_identity_document_word | 49 |
| personal / honorific | 929 |
| personal / identifier | 66 |
| personal / name_before_title | 21 |
| personal / name_or_identifier | 5,289 |
| personal / phone | 519 |
| personal / placeholder | 4 |
| personal / probable_person_name | 4,686 |
| personal / question_excluded | 118,335 |
| personal / salutation | 1,542 |
| personal / self_or_address_line | 14 |
| personal / signature | 484 |
| personal / strict_caps_unknown_word | 11,693 |
| personal / strict_contact | 251 |
| personal / strict_credential_id | 821 |
| personal / strict_health_reference | 1,990 |
| personal / strict_labelled_name | 34 |
| personal / strict_long_number | 7,724 |
| personal / strict_name_token | 17,795 |
| personal / strict_plate | 6,526 |
| personal / strict_self_identification | 3,640 |
| personal / strict_sign_off | 18,117 |
| personal / strict_title_name | 2,161 |
| personal / strict_unknown_capitalised | 30,563 |
| personal / strict_unknown_lowercase_pair | 2,058 |
| unsafe / allegation_wording | 7,958 |
| unsafe / obfuscated_wording | 1,394 |
| unsafe / question_excluded | 12,693 |
| unsafe / unsafe_text | 17,951 |
| **personal data (total)** | 327,637 |
| **unsafe wording or markup (total)** | 39,996 |

**Similarity floor** (0.35). Calibration sample: the first 6,000 flagged processes by ocid (15,475 eligible passages; best similarity to a fired signal: median 0.3, p90 0.499). Rule: smallest floor on the 0.05 grid whose stem rate is at least twice the base rate. Base rate of a deadline or price stem among passage-signal pairs: 10.8 %.

| Floor | Passage-signal pairs | Stem rate | Lift over base |
|---|---|---|---|
| 0.1 | 789 | 12.6 % | 1.16 |
| 0.15 | 725 | 13.4 % | 1.23 |
| 0.2 | 623 | 14.8 % | 1.36 |
| 0.25 | 475 | 17.7 % | 1.63 |
| 0.3 | 334 | 21.9 % | 2.01 |
| 0.35 | 163 | 34.4 % | 3.17 |
| 0.4 | 70 | 57.1 % | 5.27 |
| 0.45 | 31 | 71.0 % | 6.54 |
| 0.5 | 11 | 81.8 % | 7.54 |

**Retrieval check without labels** (processes outside the calibration sample; the selected quote of the signal against one random eligible item of the same process):

| Signal and stems | Processes | Selected quote | Random eligible item | Difference |
|---|---|---|---|---|
| `SHORT_TENDER_WINDOW` (plazo, prórroga, días, fecha, ampli-) | 188 | 35.1 % [28.2, 41.5] | 17.0 % [11.7, 22.3] | +18.1 points [+12.2, +23.9] |
| `LOW_SAVING` (precio, presupuesto, valor, monto, descuento, costo, puja, rebaja) | 1,348 | 52.1 % [49.5, 54.9] | 31.5 % [29.0, 34.1] | +20.6 points [+17.9, +23.2] |

**Privacy sweep over every stored quote** (81,568 passages in 30,752 processes):

| Check | Hits |
|---|---|
| Identifier scan (natural-person RUC, valid cédula) | 0 |
| Name search: two consecutive tokens of any natural-person or RUC-less party, tenderer, supplier or enquiry asker of the same process, either order (56,448 names) | 0 |
| Telephone numbers | 0 |
| E-mail addresses | 0 |
| «Señor/Señora» followed by a name | 0 |
| Passages with a pair of rarer given-name or surname tokens (candidates, mostly places and institutions) | 0 |
| Passages the deny-by-default boundary function refuses today (same function as the API) | 0 |

**Release-gate rules** (`scripts/check_quotes_privacy.py`; the first seven are the reviewer's regular expressions, the rest are this project's; every one must be 0):

| Rule | Hits |
|---|---|
| `r1_title_then_name` | 0 |
| `r2_role_then_name` | 0 |
| `r3_honorific_then_capitalised` | 0 |
| `r4_sign_off_or_first_person` | 0 |
| `r5_vehicle_plate` | 0 |
| `r6_telephone` | 0 |
| `r7_identity_document_word` | 0 |
| `o1_glued_honorific` | 0 |
| `o2_partial_mobile` | 0 |
| `o3_email` | 0 |
| `o4_identifier` | 0 |
| `o5_natural_ruc` | 0 |
| `o6_long_number` | 0 |
| `o7_health` | 0 |
| `o8_lowercase_plate` | 0 |
| `o9_accusation_stem` | 0 |
<!-- END GENERATED: quotes -->

## Reading 30 quotes myself (earlier build, superseded)

*This section describes the build before review 5. Its conclusion about personal data was wrong: a random sample of 30
passages cannot see a rate of about 1 in 1,000, and the reviewer found persons in that build. It is kept because the
relevance reading (which topics the quotes fit) is still the only judgement of that kind; the privacy reading of the
current build is in the next section.*

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

## Measured residual of personal data (how it was measured, every round)

**Method.** I read passages myself and counted those that name or identify a natural person (a name, a signature, an
identifier, a plate, a mobile number, a patient). Unit: a unique passage of the mart (about 71,700 unique passages:
quotes and paired answers). Two samples per round: **150 chosen uniformly at random**, and **150 chosen as the most
suspicious by heuristics that are not filters of the screen** (the most capitalised words in mid-sentence, a short last
line, the fragments `sr`, `ing`, `dr`, `lic`, `abg`, `econ`, `arq` as words, the most words that are rare in the
corpus: 38 / 38 / 37 / 37). The upper bound is the one-sided 95 % Clopper-Pearson bound (the rule of three, 3/n, when
nothing is found). Limits of this measurement, stated plainly: a single reader (me, not blind to the rules); the first
230 to 340 characters of each passage were printed, so the tail of long passages was **not read**; the suspicious
sample is a stress test, not an estimate of a rate (its ranking is deterministic, so a second round re-reads mostly the
same passages); a bound from a sample is not a guarantee about the other 71,000.

| Round | Mart | Random sample (seed) | Persons found | 95 % upper bound | Suspicious sample | Persons found | What I did |
|---|---|---|---|---|---|---|---|
| 0a (preview) | earlier rules: strict screen without the redefined vocabulary | 60 of 100 (seed 11) | 0 | not used | the 25 most capitalised and the 25 rarest | 1 passage naming two persons **in lower case** (an accusation that also insulted) | the old vocabulary excluded the commonest names (typed in lower case); redefined (`build_name_vocabulary`), applied in any case |
| 0b (preview) | rebuilt with the new vocabulary | not read | - | - | 150 | 0 | the release gate, run for the first time, found 528 passages by its broader rules (glued honorifics, titles in all-caps text): the gate rules were merged into the screen |
| 1 | `quotes build` 4 | 150 (seed 4101) | **0** | **2.0 %** | 150 | **0** | the gate then found 2 stored passages that fail once cut for display: a cut passage is now screened as shown; 7 allegation stems and `unknown_lowercase_pair` were added by reading |
| 2 (final mart) | final | 150 (seed 5202) | **0** | **2.0 %** | 150 | **0** | none needed |
| both random rounds pooled | | 300 | **0** | **1.0 %** | | | |

Round 2 was read on the mart of build 5; the two later builds only added allegation stems (`direccionar`,
`direccionaría`, substring forms of `denunci`, `a la medida`, `beneficiar a`) and removed passages, so they cannot add a
person; the gate and the independent searches below were rerun on the final mart. For the allegation reading I read 100
passages beside `SINGLE_BIDDER` or `RECURRING_COBIDDERS` in an earlier mart (seed 777) and 100 in the build-5 mart
(seed 6303): none read as an allegation; mildly hostile wording appeared in the random samples ("conflicto de
intereses", "viola la ley", "empresas beneficiadas") and became stems. **I did not state that persons never appear and the measurement does not support it**: with 0 of 300
random passages the rate could still be up to 1.0 % (about 700 passages) with 95 % confidence. Counts of
what the final screen removed are in the exclusions table of the generated block.

Coverage cost (generated block): quotes 54,489 against 68,541 before; processes with a quote 30,752 against 36,345
(35.1 % against 41.5 % of flagged processes). By signal the share falls by 0 to 8 points (the largest drops:
`CONTRACT_VS_COMPANY_SIZE` 52.6 to 44.1 %, `RECURRING_COBIDDERS` 50.4 to 42.9 %, `SINGLE_BIDDER` 41.2 to 34.9 %).
The similarity floor stays at 0.35: on the new eligible set the lift is 2.01 at 0.30 and 3.17 at 0.35, so 0.35 is
the conservative end of the rule, not recalibrated.

## Release gate

`scripts/check_quotes_privacy.py [--marts DIR] [--lake DIR]` exits 1 when anything in the mart should have been
removed, and prints only rule names, counts and short hashes (never a passage or a name). It checks every stored
passage (the quote and its paired answer) against:

* **the reviewer's seven rules** (reconstructed from the sweep scripts of review 5, so they may differ in detail
  from the reviewer's own): `r1` a title followed by a capitalised name; `r2` a role word (represented, signed,
  designated, manager, director, administrator, delegate...) followed by a capitalised name; `r3` an honorific followed
  by a capitalised word; `r4` a sign-off or first-person cue; `r5` a vehicle plate; `r6` a telephone number; `r7` an
  identity-document word followed by an identifier;
* **the project's own rules**: `o1` glued honorific (`sr.PÉREZ`), `o2` partial mobile number, `o3` e-mail address,
  `o4` identifier scan (natural-person RUC, valid cédula), `o5` natural-person RUC, `o6` run of 10 or more digits,
  `o7` health reference, `o8` lower-case plate, `o9` accusation stem;
* **the boundary function** (`check_passage` with the quote lexicon, the person-name vocabulary when present and the
  real protected names of each process from the lake): any passage it refuses today is a failure, so a mart built with
  older rules cannot ship.

A missing mart, a missing lexicon or a missing lake is a failure (fail closed). `scripts/build_data_bundle.sh
--with-quotes` runs it first and does not build when it fails; without the flag no quotes table is staged.
`tests/test_quotes_release_gate.py` runs it as a test when the real mart is present, and tests the refusal.
This closes the part of review finding 7 that concerned content: the earlier bundle gate matched file names and
hashes, never what was inside a data table.

## Allegation wording (review 5, finding 2)

A quote appears next to a risk signal, so a bidder's accusation ("el proceso está direccionado", "a dedo",
"sucios juegos") reads as if Veedor agreed with it. The unsafe screen of the dossier layer refuses Veedor's own
accusation vocabulary; the reviewer found 785 passages in 672 processes of third-party hostile text that it
missed. `domain/quotes/allegation.py` adds one pattern per stem (accent-, case- and look-alike-insensitive, on
`canonical` text) and a passage containing any of them is never eligible (`unsafe / allegation_wording`; also
applied to the QA screen through `has_accusation_wording`).

The reviewer's stems (24 patterns; documents with at least one hit, over the 3,292,395 texts of the lake and
over the 110,579 stored passages of the earlier mart):

| Stem | Texts | Earlier mart |
|---|---|---|
| `direccion` + `ar/an/aron/a` (whole word), `ado/ada/amiento/ando` (rigging; also inside "redireccionar") | 14,990 (whole-word form) | 411 |
| `denunci` | 4,057 | 71 |
| `favorec` | 3,474 | 140 |
| `perjudic` | 2,208 | 69 |
| `ilegal` | 1,983 | 0 |
| `corrup` | 1,290 | 0 |
| `arregl(ado|ada|ados|adas|o)` as a whole word | 1,023 | 31 |
| `irregular` | 806 | 0 |
| `trampa` | 579 | 0 |
| `fraud` | 535 | 0 |
| `colus` | 416 | 1 |
| `a la medida` | 406 | 16 |
| `beneficiar a` | 311 | 18 |
| `amarrad` | 267 | 7 |
| `sobrepreci` | 185 | 0 |
| `coima` | 139 | 0 |
| `soborn` | 113 | 0 |
| `a dedo` | 62 | 0 |
| `aman(ado|ada|ar|ando|o|os|an)` (amañar) | 45 | 0 |
| `con nombre y apellido` | 38 | 2 |
| `sucios juegos`, `no se engañen`, `la cía que todos sabemos` | 1, 2, 2 | 1, 1, 1 |
| `ganador(es) (ya) definido/elegido/escogido` | 0 | 0 |

"dirección" (an address, a department, 34,155 texts) is not touched: only the verb family is matched, so
`dirección`, `direcciones` and `direccional` (a turn signal) pass and `direccionar`, `direccionado`, `direccionamiento`,
`direccionando` and `redireccionar` are refused. (A first version matched the family only as a whole word and
let 8 passages with "direccionar el proceso" through; an independent substring search of the mart found them, which is
why the search is part of the verification below. "Redireccionar" is the entity's boilerplate "no redireccionar a los
proveedores a los términos de referencia": about 400 passages are lost to it on purpose.) Tests pin both sides (`tests/domain/test_quotes_strict.py`).

Stems added after reading (a sample of 30 passages that were kept near the boundary and 100 passages beside
`SINGLE_BIDDER` or `RECURRING_COBIDDERS`): `discriminat` (2,718 texts; 72 in the earlier mart), `arbitrari` (1,857; 46),
`sospech` (483; 1), `nepotismo|favoritismo|tráfico de influencias` (138; 2), `ladron|estafa` (122; 0),
`falta de transparencia|sin transparencia|no hay transparencia` (94; 3) and `abusiv|abuso de` (67; 0).
All stems together touch 33,951 of 3,292,395 texts (1.03 %) and 845 of the earlier 110,579 stored passages (0.76 %).
The screen is deliberately blunt: `a la medida` also drops "la medida solicitada", `arreglo` drops "arreglo de un
vehículo", `denunci` drops a quotation of the law. A hit anywhere drops the whole passage.

Reading the boundary. **30 dropped** passages (random among those the stems refused in the earlier mart, seed 5):
all 30 contained the stem; I classified 18 as complaints or allegations (specifications said to be "direccionadas"
to a brand, "está amarrado", "favorecen a una casa comercial"), 4 as quotations of the law or of the evaluation
rules ("principio de no direccionamiento"), 6 as harmless uses (a vehicle repair, "a la medida solicitada",
an award text "resultó favorecida en la puja") and 2 as unclear. In the final mart a search for the reviewer's stems, written independently of `allegation.py` as plain substring regular expressions, finds 0 true hits (1 false hit: "sería la medida" matches "a la medida" across an accent) against 1,362 passages in 1,140 processes in the earlier mart; and in 100 passages beside `SINGLE_BIDDER` or `RECURRING_COBIDDERS` read in the final mart, 0 read as an allegation.

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
* Personal data: **the screens are heuristics and the residual is not zero.** Review 5 found natural persons named in
  the earlier mart (see "Status"). The earlier statement "about 2 in 110,000 passages" is withdrawn. For the current
  mart the claim is only the measured bound in "Measured residual of personal data" below, from samples I read, with
  every round stated; it is an upper bound for the sampled population, not a guarantee, and it says nothing about a
  person who is described without a name or whose name is written in lower case, is rare and is not in the vocabulary.
  Do not describe the quotes as free of personal data.
* The name net has false positives on purpose: a hospital or a street named after a person is dropped
  unless it is one of the process's own buyer or company names.
* The unmasked text table and the raw bulk file are not for publication. The quotes marts contain only
  passages that passed the screens.
* `author_kind` follows the field, not a check of who wrote it: a question field sometimes holds a text written
  by the buying entity or by the very company that is named in it.
* The topic descriptions are one judgement call per signal; the floor was calibrated on two topics only
  (deadlines and prices) because they are the two with an obvious lexical signature.

## Changes after the first review of the stored quotes

* Repeated passages: the first build showed the same passage twice in 78 processes (an answer paired with two questions, an answer equal to its question); the build now guarantees at most one appearance per process: 0 repeats after the rebuild.
* Truncation: a question was shown as cut (`[…]`) because the item-level flag was set by a cut *answer*; the flag is now per part and shown passages end at a sentence or clause.
* Ten-digit numbers starting with 0 (5 stored passages) are part numbers, a page number and invoice numbers, not telephones: the phone screen requires 0 followed by a digit 2 to 9 and 7 or 8 more digits (`09…` mobiles and `02…` to `07…` landlines), and `0174120140`, `0000000091` and `00004240-0000004419` do not have that shape. Tests pin both sides.
* Four passages that name a person who is not a party (a list of shareholders, administrators named in a request, an official in an address block, a trainer named in a letter) are in `domain/quotes/deny.py` by hash; a name followed by an official title in capitals is a pattern (`name_before_title`). Two broader patterns (role noun plus name, list of owners) were tried and removed: they matched 289 and 82 stored passages, almost all ordinary requirements.
* `person_name_tokens.parquet` is not shipped in the data bundle (docs/SECURITY.md).

## Changes after review 5

* **Disabled by default** (`VEEDOR_QUOTES_ENABLED=false`): 404, no quotes in `/ask`, `quotes_enabled: false` in `/meta`, no quotes table in the data bundle without `--with-quotes`.
* **Deny by default** (`domain/quotes/strict.py`) and an institutional **lexicon** built from the texts, replacing the claim that patterns find what matters. The earlier screens stay in front of it.
* **Person-name vocabulary redefined** (`build_name_vocabulary`) and applied in any case: the earlier one excluded the commonest names.
* **Release gate** (`scripts/check_quotes_privacy.py`) with the reviewer's seven rules and the project's own, wired into the bundle script and into the test suite.
* **Allegation stems** (`domain/quotes/allegation.py`), also applied to the QA screen.
* The numbers "about 2 in 110,000", "0 identifiers" and "natural persons never appear" were removed from `docs/QUOTES.md`, `docs/SECURITY.md` and `README.md`: they described what the old screens could see, not what the mart contained.
