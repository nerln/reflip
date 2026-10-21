// node --test stats/test
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { fileURLToPath } from "node:url";

import { handle } from "../src/index.js";
import { SCHEMA, validate } from "../src/schema.js";

const GOOD = { v: 1, e: "detect", f: "-", m: "qwen2.5-0.5b" };

function fakeDB() {
  const rows = new Map();
  return {
    rows,
    prepare(sql) {
      return {
        bind(...args) {
          return {
            async run() {
              assert.match(sql, /INSERT INTO counts/);
              const key = args.join("|");
              rows.set(key, (rows.get(key) || 0) + 1);
            },
          };
        },
      };
    },
  };
}

function req(body, { origin = "https://nerln.github.io", method = "POST", path = "/e" } = {}) {
  return new Request(`https://reflip-stats.example${path}`, {
    method,
    headers: { Origin: origin, "Content-Type": "text/plain" },
    body: method === "POST" ? (typeof body === "string" ? body : JSON.stringify(body)) : undefined,
  });
}

test("an allowed event adds one to its tally", async () => {
  const env = { DB: fakeDB() };
  assert.equal((await handle(req(GOOD), env, "2026-10-21")).status, 204);
  assert.equal((await handle(req(GOOD), env, "2026-10-21")).status, 204);
  assert.deepEqual([...env.DB.rows.entries()], [["2026-10-21|detect|-|qwen2.5-0.5b", 2]]);
});

test("any value off its list refuses the whole event", async () => {
  const env = { DB: fakeDB() };
  for (const [k, bad] of [["e", "paste"], ["m", "gpt"], ["f", "machine-like"], ["v", 2], ["e", 412]]) {
    const r = await handle(req({ ...GOOD, [k]: bad }), env);
    assert.equal(r.status, 400, `${k}=${bad}`);
  }
  assert.equal(env.DB.rows.size, 0);
});

test("text in any field, an extra field or a missing one is refused", async () => {
  const env = { DB: fakeDB() };
  const sentence = "Il gatto dorme sul divano da tre ore.";
  for (const ev of [
    { ...GOOD, f: sentence },
    { ...GOOD, text: sentence },
    { ...GOOD, len: 37 },
    { ...GOOD, o: "completed" },
    { ...GOOD, u: "it" },
    (({ m, ...rest }) => rest)(GOOD),
  ]) {
    assert.equal((await handle(req(ev), env)).status, 400);
  }
  assert.equal(env.DB.rows.size, 0);
});

test("other origins, methods, paths and big bodies are not counted", async () => {
  const env = { DB: fakeDB() };
  assert.equal((await handle(req(GOOD, { origin: "https://evil.example" }), env)).status, 403);
  assert.equal((await handle(req(GOOD, { method: "GET" }), env)).status, 404);
  assert.equal((await handle(req(GOOD, { path: "/x" }), env)).status, 404);
  assert.equal((await handle(req("x".repeat(300)), env)).status, 413);
  assert.equal((await handle(req("{not json"), env)).status, 400);
  assert.equal(env.DB.rows.size, 0);
});

test("validate never returns a field the schema does not name", () => {
  assert.deepEqual(Object.keys(validate(GOOD)).sort(), Object.keys(SCHEMA).sort());
  assert.equal(validate(null), null);
  assert.equal(validate([GOOD]), null);
  assert.equal(validate("detect"), null);
});

test("the browser's copy of the schema is the same file", () => {
  const here = fileURLToPath(new URL("../src/schema.js", import.meta.url));
  const site = fileURLToPath(new URL("../../docs/app/stats-schema.js", import.meta.url));
  assert.equal(readFileSync(site, "utf8"), readFileSync(here, "utf8"));
});
