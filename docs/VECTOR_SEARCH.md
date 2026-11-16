# Vector search ("similar processes")

Finds processes that bought something similar to a given process. It is a search aid, not a risk
indicator: similarity never feeds the risk score and says nothing about wrongdoing.

## What is embedded, and why

For every non-catalogue process (catalogue purchases are out of scope) the text is
`"<CPC description>. <description>"`, where the description has passed `safe_free_text`
(`veedor.domain.masking`). The CPC description gives the purchase category; the description gives the
object. Text is truncated to 1,000 characters.

## Privacy

- The description is embedded only after `safe_free_text`. It is withheld (and only the CPC description is
  embedded) when the winner is a masked party (natural person or unidentified party) or when masking finds
  any personal item (names of the process's parties, cédulas, natural-person RUCs, honorific + name).
- The table `process_vectors` has **no text column**: it stores the vector, a SHA-256 of the embedded text,
  the model name and non-sensitive metadata (year, buyer RUC, method, award total, main CPC). The raw
  description is never stored.
- Residual limit (same as the rest of the project): a person who is not a party and is named without an
  honorific can slip through the heuristic. Vectors are not reversible to text in practice, but they are
  derived from it.
- API responses are masked like every other response (`MaskedModel`): a natural-person buyer is shown as
  "Persona natural".

## Model

`minishlab/potion-multilingual-128M` through `fastembed` 0.9.1: multilingual, **256 dimensions**, licence
**MIT**, 0.512 GB (values read from `TextEmbedding.list_supported_models()`). It is a static-embedding
model: no transformer forward pass. The cache is `data/models/fastembed`; no network is needed after the
first download, and none at query time (a query uses the stored vector of the process).

Why not `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` (384 d, Apache-2.0, ONNX int8)?
On a 5,000-description sample (description only, exact search inside the pool, 1,000 queries) both reached
the same CPC 5-digit agreement@10 (0.168 vs 0.170; random 0.015), but MiniLM ran at about 60-80 texts/s on
this machine (measured while the machine was also busy with other work, so treat as a lower bound)
against tens of thousands for the static model. At that speed the full ~386k texts would have taken
well over the 25-minute budget. This comparison was a one-off scratch measurement, not part of the
repository's evaluation.

## Index

HNSW, `vector_cosine_ops` (`m=16, ef_construction=64`), `hnsw.ef_search=100` at query time. Reasons
(pgvector docs): HNSW has a better speed/recall trade-off than IVFFlat and needs no training step, so the
table is filled incrementally and re-built idempotently while the index stays valid (IVFFlat must be built
after the data and tuned per row count). Cost: slower inserts and more memory (insertion into the index is
the bottleneck of the build, not the embedding). Cosine distance (`<=>`) is consistent with the
L2-normalised vectors (it ranks like inner product) and stays correct if a model is not normalised;
similarity = 1 - distance. With `same_buyer`, filtering happens after the ANN scan, so
`hnsw.iterative_scan = strict_order` is enabled for those queries.

## Commands

```
uv run alembic upgrade head
uv run veedor vectors build [--limit N] [--batch-size 64]   # idempotent, resumable
uv run veedor vectors status
uv run veedor vectors evaluate [--sample 1000]              # writes eval/vector_search.json
```

`build` skips rows whose text hash and model are unchanged, embeds each distinct text once and maps it back
to every process that shares it, and commits per chunk (an interrupted run resumes where it stopped).

API: `GET /api/v1/processes/{ocid}/similar?k=10&same_buyer=false` (k 1-50; 404 unknown or not indexed;
503 `vectors_unavailable`). Python: `veedor.use_cases.similar_processes.find_similar(ocid, k, same_buyer)`.

## Coverage actually built

Full build, not a subset. Measured on 2026-11-16 on a 10-core laptop that was also running the compose
stack (db, api, web, observability) and other work; timings are indicative.

| Item | Value |
|---|---|
| In-scope records read (non-catalogue with any text) | 366,070 |
| Indexed rows | 365,864 (all of them with a safe text) |
| Not indexed: no safe text (withheld description and no CPC description) | 206 |
| Embedded as CPC + description | 188,440 + 1,678 |
| Embedded as CPC only because the description was withheld | 168,180 + 3,318 (46.9 %) |
| Embedded as description only (no CPC in the data) | 4,244 + 4 |
| Distinct texts embedded in the main run | 193,824 for 360,864 records |
| Throughput | embedding 42,705 distinct texts/s; end to end 1,377 rows/s (wall 262 s, the rest is HNSW insertion and PostgreSQL) |

The first figure in each "+" pair is the main run, the second a preceding `--limit 5000` sample run (5,000
records: 2.4 s wall); a third run skipped all 365,864 rows as unchanged (idempotency). Projection from the
5,000-record sample: ~3 minutes for the whole set; the real run took 4 min 25 s.

Almost half of the indexed processes are represented by their CPC description alone, because their winner
is a masked party (natural person) or masking found personal data. Their nearest neighbours are therefore
mostly same-category processes, and the full-index agreement below is inflated by them.

## Evaluation

The proxy label is the CPC 5-digit prefix. It is not relevance: similar purchases can carry different CPC
codes and the embedded text contains the CPC description, so the full-index number is optimistic (the pool
experiment below quantifies that). The exact-CPC baseline shares the prefix by construction (ceiling 1.0).
Identical descriptions (re-tendered objects) inflate agreement; the "removed" row excludes them.

<!-- BEGIN GENERATED: evaluation -->
Generated by `veedor vectors evaluate` on 2026-11-16 (seed 42, 2000 bootstrap resamples; values are mean [95 % interval]).

Index: 365,864 rows, model `minishlab/potion-multilingual-128M` (256 dimensions).

**Full index** (1,000 random query processes, top-10 from pgvector):

| Measure | Value |
|---|---|
| CPC 5-digit agreement@10, embedding neighbours | 81.3 % [79.2, 83.4] |
| Same, random-neighbour baseline | 1.7 % [1.4, 2.1] |
| Same, exact-CPC baseline (ceiling by construction) | 100.0 % [100.0, 100.0] |
| Embedding neighbours with the identical 9-digit CPC | 73.9 % [71.5, 76.2] |
| Queries with fewer than 10 other processes of the same 9-digit CPC | 70 of 1,000 |

**CPC-text leakage** (pool of 20,000 processes with a safe description, 1,000 queries, exact search inside the pool):

| Variant | Embedding includes CPC text | Description only |
|---|---|---|
| All neighbours | 63.3 % [61.0, 65.8] | 29.8 % [27.7, 31.8] |
| Identical-description neighbours removed | 63.3 % [61.0, 65.7] | 29.6 % [27.6, 31.6] |

Pool baselines: random neighbours 2.4 % [2.0, 2.8]; exact-CPC 100.0 % [100.0, 100.0].

**Latency** of `find_similar` over 200 queries: p50 14.1 ms, p95 20.3 ms, max 33.9 ms.
<!-- END GENERATED: evaluation -->

## Limits

- Similarity of descriptions, not of legal or economic substance. Static embeddings ignore word order.
- Processes with a withheld description are represented by their CPC description only, so they are close
  to every other process of the same category.
- Processes without any safe text, and catalogue purchases, are not indexed.
- Changing the model or dimension needs a new migration and a full rebuild.
