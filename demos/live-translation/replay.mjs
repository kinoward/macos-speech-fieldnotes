import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { realpathSync } from "node:fs";
import { setTimeout as delay } from "node:timers/promises";
import { parseArgs } from "node:util";
import WebSocket from "ws";
import { checkProbe, probes } from "../../experiments/probe-expectations.mjs";

const { positionals, values } = parseArgs({
  allowPositionals: true, options: { text: { type: "boolean" }, expect: { type: "string" } },
});
if (positionals.length !== 1 || (values.expect !== undefined && !probes.has(values.expect))) {
  console.error("Usage: node replay.mjs INPUT [--text] [--expect CASE]");
  console.error("Probe names:", [...probes.keys()].join(", "));
  process.exit(2);
}
const file = realpathSync(positionals[0]);
const pcm = execFileSync("ffmpeg", ["-hide_banner", "-loglevel", "error", "-nostdin",
  "-protocol_whitelist", "file,pipe", "-i", file,
  "-map", "0:a:0", "-ar", "16000", "-ac", "1", "-f", "s16le", "-"], { maxBuffer: 32 * 1024 * 1024 });
const origin = `http://127.0.0.1:${process.env.PORT || 8765}`;
const socket = new WebSocket(origin.replace("http:", "ws:") + "/stream", { origin });
const begin = performance.now();
const firstMs = {};
const source = new Map();
const translated = new Map();
let started;
let done = false;
const deadline = setTimeout(() => socket.terminate(), 45_000 + pcm.length / 32);

async function sendAudio() {
  const packetSize = 2880;
  for (let offset = 0; offset < pcm.length; offset += packetSize) {
    await delay(Math.max(0, started + offset / 32 - performance.now()));
    if (socket.readyState !== WebSocket.OPEN) return;
    socket.send(pcm.subarray(offset, offset + packetSize));
  }
  await delay(Math.max(0, started + pcm.length / 32 - performance.now()));
  if (socket.readyState === WebSocket.OPEN) socket.send(JSON.stringify({ type: "stop" }));
}

try {
  await new Promise((resolve, reject) => {
    socket.on("error", reject);
    socket.on("close", () => done ? resolve() : reject(new Error("The session ended before done.")));
    socket.on("message", (bytes) => {
      try {
        const row = JSON.parse(bytes);
        if (row.type === "ready") {
          started = performance.now();
          void sendAudio().catch(reject);
        } else if (row.type === "error") {
          reject(new Error(row.message));
        } else if (row.type === "done") {
          done = true;
          resolve();
        } else if (row.type === "source" || row.type === "translation") {
          const key = row.type + (row.final ? "Final" : "Draft");
          firstMs[key] ??= Math.round(performance.now() - started);
          if (row.final) {
            const finals = row.type === "source" ? source : translated;
            assert(!finals.has(row.segmentId), "duplicate final for a segment");
            finals.set(row.segmentId, row);
          }
        }
      } catch (error) {
        reject(error);
      }
    });
  });
  assert.deepEqual([...source.keys()], [...translated.keys()], "final segments must pair");
  const sections = [];
  for (const [id, row] of source) {
    const match = translated.get(id);
    assert.equal(match.revision, row.revision, "final revisions must match");
    const chinese = row.text.split("\n\n");
    const english = match.text.split("\n\n");
    assert.equal(english.length, chinese.length, "section count must match");
    for (const [index, text] of chinese.entries()) sections.push([text, english[index]]);
  }
  if (values.expect) checkProbe(values.expect, sections, firstMs);
  const report = { audioMs: Math.round(pcm.length / 32), readyMs: Math.round(started - begin),
    firstMs, doneMs: Math.round(performance.now() - started), pairedSegments: source.size };
  if (values.text) {
    report.sections = [...source].map(([id, row]) => [row.text, translated.get(id).text]);
  }
  console.log(JSON.stringify(report, null, 2));
} finally {
  clearTimeout(deadline);
  socket.close();
}
