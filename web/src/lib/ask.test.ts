import assert from "node:assert/strict";
import { test } from "node:test";
import { checkQuestion, examplesFor, normalizeAsk, parseRetryAfter, provenanceKeysFor, questionLength, suggestQuestions, waitPhrase } from "./ask.ts";

test("question length: 3 to 300 characters, one line", () => {
  assert.equal(checkQuestion("¿Qu"), null);
  assert.match(checkQuestion("ab") ?? "", /al menos 3/);
  assert.match(checkQuestion("   a  ") ?? "", /al menos 3/);
  assert.equal(checkQuestion("a".repeat(300)), null);
  assert.match(checkQuestion("a".repeat(301)) ?? "", /300/);
  assert.match(checkQuestion("uno\ndos") ?? "", /una sola línea/);
  assert.equal(questionLength("¿Quién ganó?"), 12);
});

test("normalizeAsk keeps well-formed items, masks natural RUCs and treats text as text", () => {
  const a = normalizeAsk({
    ocid: "ocds-5wno2w-X",
    answerable: true,
    mode: "retrieval",
    reason: "answered",
    sentences: [
      { text: "Hubo 4 oferentes. <b>x</b> 0912345678001", fact_id: "process.tenderers", source_id: "sercop_ocds", source_field: "tender.numberOfTenderers" },
      { text: "", fact_id: "x", source_id: "y", source_field: "z" },
      "no",
    ],
    quotes: [
      { quote_id: "q1", text: "Texto <a href='x'>citado</a>", kind: "enquiry_question", date: "2019-03-12", source_field: "tender.enquiries[0].description", truncated: true },
      { quote_id: "q2", text: "otro", kind: "unknown_kind" },
    ],
    note_es: "Nota.",
  });
  assert.ok(a);
  assert.equal(a.sentences.length, 1);
  assert.equal(a.sentences[0].text, "Hubo 4 oferentes. <b>x</b> 0912*********");
  assert.equal(a.quotes.length, 1);
  assert.equal(a.quotes[0].text, "Texto <a href='x'>citado</a>");
  assert.equal(a.quotes[0].truncated, true);
  assert.equal(normalizeAsk({ ocid: "x" }), null);
  assert.equal(normalizeAsk(null), null);
});

test("Retry-After as seconds or date", () => {
  assert.equal(parseRetryAfter("42"), 42);
  assert.equal(parseRetryAfter(null), null);
  assert.equal(parseRetryAfter("soon"), null);
  const now = Date.UTC(2026, 0, 1, 12, 0, 0);
  assert.equal(parseRetryAfter("Thu, 01 Jan 2026 12:02:00 GMT", now), 120);
  assert.equal(waitPhrase(20), "unos segundos");
  assert.equal(waitPhrase(120), "2 minutos");
  assert.equal(waitPhrase(3600), "1 hora");
});

test("fact ids map to provenance keys; unknown ids fall back to themselves", () => {
  assert.deepEqual(provenanceKeysFor("process.tenderers")[0], "facts.n_tenderers");
  assert.deepEqual(provenanceKeysFor("signal:SINGLE_BIDDER"), ["signal.SINGLE_BIDDER"]);
  assert.deepEqual(provenanceKeysFor("relation.previous"), ["relation.previous"]);
});

test("suggestions come from what the process has (3 to 5)", () => {
  const all = suggestQuestions({ nRiskSignals: 2, hasTenderers: true, hasAmounts: true, hasBuyer: true, hasWinner: true, hasObject: true });
  assert.equal(all.length, 5);
  assert.equal(all[0], "¿Por qué tiene estas señales?");
  const few = suggestQuestions({ nRiskSignals: 0, hasTenderers: false, hasAmounts: true, hasBuyer: true, hasWinner: false, hasObject: false });
  assert.deepEqual(few, ["¿Cuánto se adjudicó y cuál era el presupuesto?", "¿Quién compró?"]);
  assert.equal(examplesFor(few).length, 2);
  assert.equal(new Set(examplesFor(few)).size, 2);
});
