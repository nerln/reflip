// node --test web/test/clean.test.mjs: what is taken off a model's reply, and what is not.
import assert from "node:assert/strict";
import { test } from "node:test";

import { cleanReply } from "../../docs/app/clean.js";

test("an announced rewrite loses its announcement", () => {
  assert.equal(cleanReply("Okay, here’s a revised version of the text, keeping the meaning:\n\nThe trial ran for 18 months."),
    "The trial ran for 18 months.");
  assert.equal(cleanReply("Here is the rewritten version:\nThe trial ran for 18 months."), "The trial ran for 18 months.");
});

test("a copied instruction and a closing remark are dropped", () => {
  const reply = "The trial ran for 18 months.\nThe previous attempt altered a number, a name, a negation or a quantifier.\n\n---\nI hope this helps!";
  assert.equal(cleanReply(reply), "The trial ran for 18 months.");
});

test("a whole reply in quotes loses the quotes", () => {
  assert.equal(cleanReply("“The trial ran for 18 months.”"), "The trial ran for 18 months.");
});

test("ordinary text is left alone, colons and quotes included", () => {
  const text = "Three findings stood out:\n\n1. The effect held.\n2. It was \"small\" but real.";
  assert.equal(cleanReply(text), text);
  assert.equal(cleanReply("Here the river bends: the town sits on the inside."), "Here the river bends: the town sits on the inside.");
});
