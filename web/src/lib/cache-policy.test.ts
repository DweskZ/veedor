import assert from "node:assert/strict";
import { test } from "node:test";
import { revalidateSeconds } from "./cache-policy.ts";

test("aggregates and reference data are reused for five minutes", () => {
  for (const p of ["/stats", "/stats/by-region", "/stats/by-year", "/stats/thresholds", "/signals", "/glossary"]) assert.equal(revalidateSeconds(p), 300);
});

test("per-process, supplier and buyer read models are reused for a minute", () => {
  for (const p of ["/processes/ocds-x-1", "/processes/ocds-x-1/context", "/processes/ocds-x-1/threshold", "/suppliers/1790000000001", "/buyers/1760000000001"])
    assert.equal(revalidateSeconds(p), 60);
});

test("lists are reused briefly, whatever the query", () => {
  assert.equal(revalidateSeconds("/processes?page=2&region=MANABI"), 30);
});

test("live, random, gated and out-of-lake reads are never reused", () => {
  for (const p of [
    "/meta",
    "/health",
    "/processes/random",
    "/processes/random?with_signals=true",
    "/buyers/search?q=quito",
    "/processes/ocds-x-1/quotes",
    "/processes/ocds-x-1/reviews",
    "/processes/ocds-x-1/investigation",
    "/processes/ocds-x-1/dossier",
    "/processes/ocds-x-1/similar?k=5",
    "/processes/ocds-x-1/provenance",
    "/processes/ocds-x-1/ask",
  ])
    assert.equal(revalidateSeconds(p), null, p);
});
