import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import { test } from "node:test";
import { buildValidation } from "../../scripts/sync-validation.mjs";
import { buildFigures, fmtPpAbs, forestRows, verdictOf, type ValidationData } from "./validation.ts";

const data = JSON.parse(readFileSync(new URL("../data/validation.json", import.meta.url), "utf8")) as ValidationData;
const repoFile = new URL("../../../eval/validation.json", import.meta.url);

test("the data file is exactly what the script builds from eval/validation.json", { skip: !existsSync(repoFile) }, () => {
  const rebuilt = buildValidation(JSON.parse(readFileSync(repoFile, "utf8")));
  assert.deepEqual(JSON.parse(JSON.stringify(rebuilt)), JSON.parse(readFileSync(new URL("../data/validation.json", import.meta.url), "utf8")));
});

test("home figures equal the data file", () => {
  const f = buildFigures(data);
  const single = data.confirm.signals.find((s) => s.signal === "SINGLE_BIDDER")!.adjusted!;
  assert.equal(f.confirm.single, Math.abs(single.effect_pp).toFixed(1).replace(".", ","));
  assert.equal(f.confirm.single, fmtPpAbs(single.effect_pp));
  assert.equal(f.list.positives, String(data.list_test.n_positives));
  assert.equal(f.list.official?.replace(".", ""), String(data.list_test.official_list_size));
  assert.equal(f.list.auc, data.list_test.auc.estimate.toFixed(3).replace(".", ","));
  assert.equal(f.confirm.years, `${data.confirm.years[0]}–${data.confirm.years[1]}`);
  assert.equal(f.confirm.untestableCount, data.confirm.signals.filter((s) => !s.circular && s.status !== "tested").length);
});

test("verdicts follow the interval and the forest plot lists only tested primary signals", () => {
  const rows = forestRows(data);
  assert.ok(rows.length > 0);
  for (const r of rows) {
    assert.ok(r.ci_low_pp <= r.effect_pp && r.effect_pp <= r.ci_high_pp);
    assert.equal(r.verdict, r.ci_high_pp < 0 ? "lower" : r.ci_low_pp > 0 ? "higher" : "none");
  }
  for (const s of data.confirm.signals.filter((s) => s.status !== "tested")) assert.equal(verdictOf(s), "untestable");
});
