// The streaming SHA-256 against Node's, on lengths around every padding edge and in odd chunks.
import assert from "node:assert/strict";
import { createHash, randomBytes } from "node:crypto";
import { test } from "node:test";

import { Sha256 } from "../../docs/app/sha256.js";

test("matches Node on every length from 0 to 200 bytes", () => {
  for (let n = 0; n <= 200; n++) {
    const data = randomBytes(n);
    assert.equal(new Sha256().update(new Uint8Array(data)).hex(), createHash("sha256").update(data).digest("hex"), `n=${n}`);
  }
});

test("matches Node when the input arrives in uneven pieces", () => {
  const data = new Uint8Array(randomBytes(1_000_003));
  const h = new Sha256();
  for (let i = 0, step = 1; i < data.length; i += step, step = (step * 7 + 3) % 9001 + 1) h.update(data.subarray(i, i + step));
  assert.equal(h.hex(), createHash("sha256").update(data).digest("hex"));
});
