import assert from "node:assert/strict";
import test from "node:test";
import { applyRevision } from "../demos/live-translation/public/revisions.js";

test("a corrected source clears its preview and ignores late translations", () => {
  const cell = () => ({ textContent: "", dataset: {} });
  const row = { source: cell(), translation: cell(), sourceRevision: -1, translationRevision: -1 };
  const send = (type, revision, text, final = false) => applyRevision(row, { type, revision, text, final });
  send("source", 1, "打开灯");
  send("translation", 1, "Turn on the light");
  send("source", 2, "别打开灯");
  assert.equal(row.translation.textContent, "");
  assert.equal(send("translation", 1, "Turn on the light", true), false);
  assert.equal(send("translation", 2, "Leave the light off", true), false);
  send("translation", 2, "Leave the light off");
  send("source", 3, "别打开灯。", true);
  assert.equal(row.translation.textContent, "Leave the light off");
  assert.equal(send("translation", 2, "Old draft"), false);
  send("translation", 3, "Leave the light off.", true);
  assert.equal(send("translation", 3, "Late draft"), false);
  assert.equal(row.translation.textContent, "Leave the light off.");
  assert.equal(row.translation.dataset.final, "true");
});
