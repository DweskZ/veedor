# History

Material moved out of the README: the question-answering numbers as first reported, and the summary table of the five independent reviews. Both are historical snapshots. The current question-answering results are in [EVALUATION.md](EVALUATION.md) and `eval/qa.json`; the full review record is [REVIEWS.md](REVIEWS.md). The rest of the detail moved from the README is in [REFERENCE.md](REFERENCE.md).

## Question answering: first two-set measurement (superseded)

`POST /processes/{ocid}/ask` is off by default. Its retrieval-only mode (no model) was measured on 310 unseen processes
(`eval/qa.json`, `docs/EVALUATION.md`) with two question sets, because the first one overstated it (review 5): the
original phrasings share words with the retrieval key phrases (29 of 73 answerable templates were verbatim keys).

| Retrieval only, unseen processes | In-vocabulary phrasing (n = 1,439 answerable) | Unseen phrasing (independent wording, n = 1,439 answerable) |
|---|---|---|
| Recall of the expected facts | 83.7 % (81.8 to 85.5) | **14.2 %** (12.4 to 16.1) |
| Answerable questions answered with no fact | 3.2 % | 75.7 % |
| Abstention on unanswerable questions (n = 930) | 79.7 % (77.2 to 82.4) | 88.0 % (85.9 to 90.0), because it says nothing to most questions |

**Weak categories, stated next to any headline number:** `signals_all` (24 % in-vocabulary, 0 % unseen), `ghost` (42 %, 0 %),
`registry_company` (54 %, 0 %), `history` (50 %, 12 %), `pair_others` (n = 2: 0 %, 0 %) and, with unseen phrasing, also `winner`, `object`, `amounts`,
`procedure` and `registry_sri` (83 to 100 % in-vocabulary, 0 % unseen). The system was **not retuned** to the new set. Model mode (`gpt-5.4-mini`) was measured
on the in-vocabulary phrasings only, over n = 172 questions; it was not rerun on unseen phrasings.

> Superseded: this is the state before the intent-based retrieval. See [EVALUATION.md](EVALUATION.md) for three phrasing sets and the current figures.

## Independent reviews (summary table)

Five independent, adversarial, read-only reviews were run on 2026-11-16, each by a reviewer who started without knowledge of the codebase and was asked to break the project's claims. Full record, including what remains open: [docs/REVIEWS.md](REVIEWS.md).

| Review | When | Result |
|---|---|---|
| 1 | After the first build, every test green | Broke masking (personal data in free text, parties without a RUC) and the text verifier, and found HTTP 500s and open review writes. Held: 40 SQL-injection payloads and 19 file-access attempts had no effect. The model stopped writing prose as a result. |
| 2 | After those fixes | Confirmed the high-severity fixes; a privacy sweep of 1,640 processes (3,280 responses) found 0 leaked names, 0 unmasked natural-person RUCs, 0 valid cédulas. Found over-masking, transient 500s, a weaker review wording filter, and that 35 of 82 fresh evasions passed the word list. |
| 3 | Stage 2: agents, vectors, telemetry | Re-derived the facts of six processes from primary sources (all matched); a hostile fake tool server leaked nothing; budgets held. Broke it: a privacy-scan crash (7 of 80 offline runs, 1 of 15 live) and the API returning 404 for every stored investigation in compose; plus fiscal-year, out-of-range-value and snapshot-labelling defects. |
| 4 | Re-test of the stage 2 fixes | The crash was gone (13 of 13 live and 320 offline investigations completed); 65 attacks on the shared database reader refused; 200 requests at concurrency 8 gave p95 0.64 s. Found the privacy scan narrowed too far (no cédula, no formatted RUC), an unchecked report-number field, and a Contraloría list that silently omitted 3 of 9 reports. |
| 5 | Before publication | Concluded the project was **not fit to publish**. Found natural persons named in the stored quotes (62 passages by 7 simple regular expressions, about 120 by reading, 54 quoting vehicle plates) although the project had claimed about 2 in 110,000; 785 passages of accusation-like third-party text beside risk signals; question-answering evaluation partly measuring the retrieval keys (29 of 73 templates were verbatim keys); 891 identifiers returning 422; per-worker rate limits. Fixes and measurements: [docs/REVIEWS.md](REVIEWS.md). Quotes are now off by default. |

Reviews 3 and 4 tested the agent graph with a scripted fake model; no model behaviour was reviewed adversarially with a real model. **The final round of fixes after review 5 (and those after reviews 2 and 4) was verified by the project's own tests, measurements and a manual reading of samples, not by a further independent review.**
