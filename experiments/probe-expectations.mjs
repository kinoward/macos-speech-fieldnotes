import assert from "node:assert/strict";

const windowCondition = [/如果.*窗.*雨/u, /\b(if|when|with)\b.*\brain/i];
const sunset = [/晚霞/u, /sunset|twilight|afterglow|evening/i];

export const probes = new Map([
  ["negation", [[/没.{0,2}说.*灯/u, /\b(didn['’]t|did not|never)\b.*\b(light|lamp)/i]]],
  ["condition", [windowCondition]],
  ["noun", [[/天空.*的.*星/u, /\bstar\b/i]]],
  ["independent", [sunset, [/灯/u, /light|lamp/i]]],
  ["mixed-condition", [sunset, windowCondition]],
  ["pronoun-condition", [[/如果.*计划.*比赛/u, /\b(if|when)\b.*(game|match|competition|race)/i]]],
  ["quiet", [windowCondition]],
  ["noise", [windowCondition]],
  ["silence", []],
]);

export function checkProbe(name, sections, firstMs) {
  const expected = probes.get(name);
  assert.equal(sections.length, expected.length, `${name}: final section count`);
  for (const [index, [source, english]] of expected.entries()) {
    assert.ok(source.test(sections[index][0]), `${name}: Mandarin section ${index + 1}`);
    assert.ok(english.test(sections[index][1]), `${name}: English section ${index + 1}`);
  }
  if (name === "silence") assert.deepEqual(firstMs, {}, "digital silence emitted a caption");
}
