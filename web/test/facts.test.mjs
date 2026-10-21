// node --test web/test/facts.test.mjs: the browser's facts diff against the shared cases.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

import { diff } from "../../docs/app/facts.js";

const cases = JSON.parse(readFileSync(new URL("../../tests/fixtures/facts-cases.json", import.meta.url), "utf8"));

for (const c of cases) {
  test(c.name, () => {
    const d = diff(c.a, c.b, c.lang);
    assert.equal(d.altered, c.altered, JSON.stringify(d));
    for (const part of ["numbers", "names", "quantifiers", "negations"]) {
      if (part in c) assert.deepEqual(d[part], c[part], part);
    }
  });
}

test("the same text changes nothing", () => {
  assert.equal(diff(cases[1].a, cases[1].a, "en").altered, 0);
});
