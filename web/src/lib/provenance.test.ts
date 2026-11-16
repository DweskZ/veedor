import assert from "node:assert/strict";
import { test } from "node:test";
import { maskNaturalRuc, normalizeProvenance, normalizeQuotes, pickQuotes } from "./provenance.ts";

test("natural-person RUCs (third digit 0-5) are masked, company RUCs are not", () => {
  assert.equal(maskNaturalRuc("RUC 0602345678001 y 0991234567001"), "RUC 0602********* y 0991234567001");
  assert.equal(maskNaturalRuc("1768086750001"), "1768086750001"); // third digit 6: public entity
});

test("provenance values are masked and malformed rows dropped", () => {
  const p = normalizeProvenance({
    ocid: "ocds-x-1",
    sources: [{ id: "s", name: "Fuente", url: "javascript:alert(1)" }, { name: "sin id" }],
    facts: [{ key: "winner", label_es: "Ganó", value: "1302345678001", source_id: "s" }, { label_es: "sin clave" }],
  });
  assert.equal(p?.sources.length, 1);
  assert.equal(p?.sources[0].url, null);
  assert.equal(p?.facts.length, 1);
  assert.equal(p?.facts[0].value, "1302*********");
});

test("quotes: at most three, an answer shown as a pair is not repeated, text stays text", () => {
  const q = normalizeQuotes({
    ocid: "ocds-x-1",
    items: [
      { kind: "enquiry_question", text: "¿Pregunta? <b>x</b> 1302345678001", pair: { kind: "enquiry_answer", text: "Respuesta", source_field: "a" } },
      { kind: "enquiry_answer", text: "Respuesta" },
      { kind: "award_text", text: "Uno" },
      { kind: "award_text", text: "Dos" },
      { kind: "award_text", text: "Tres" },
    ],
  });
  const shown = pickQuotes(q!);
  assert.equal(shown.length, 3);
  assert.equal(shown[1].text, "Uno");
  assert.equal(shown[0].text, "¿Pregunta? <b>x</b> 1302*********");
});
