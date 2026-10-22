// Run the browser's rewriters over the watermarked benchmark texts, in headless Chrome on
// WebGPU, exactly as the page does, and save what they wrote. The watermark score, the
// facts check and the edit ratio are computed afterwards in Python, by
// `python -m reflip.browser_measure`, with the same detector and key as every other row.
//
//   PROFILE=<scratch dir> node web/measure-rewriters.mjs [model ids...]
//
// Writes data/results/browser-rewriters.jsonl, one line per text and model.

import { appendFileSync, existsSync, mkdirSync, readFileSync, statSync } from "node:fs";
import { createServer } from "node:http";
import { homedir } from "node:os";
import { extname, join, normalize } from "node:path";
import { fileURLToPath } from "node:url";

import puppeteer from "puppeteer-core";

const ROOT = fileURLToPath(new URL("../", import.meta.url));
const DOCS = join(ROOT, "docs/");
const OUT = join(ROOT, "data/results/browser-rewriters.jsonl");
const samples = readFileSync(join(ROOT, "data/corpus.jsonl"), "utf8").split("\n").filter(Boolean)
  .map((l) => JSON.parse(l)).filter((r) => r.watermarked).map(({ id, lang, text }) => ({ id, lang, text }));
const models = process.argv.slice(2).length ? process.argv.slice(2) : ["qwen2.5-0.5b", "qwen2.5-1.5b-instruct"];
const done = new Set(existsSync(OUT) ? readFileSync(OUT, "utf8").split("\n").filter(Boolean).map((l) => {
  const r = JSON.parse(l);
  return `${r.model}/${r.id}`;
}) : []);

const TYPES = { ".html": "text/html", ".js": "text/javascript", ".mjs": "text/javascript", ".css": "text/css",
  ".json": "application/json", ".svg": "image/svg+xml", ".wasm": "application/wasm" };
const server = createServer((req, res) => {
  const path = normalize(decodeURIComponent(new URL(req.url, "http://x").pathname)).replace(/^\/+/, "");
  let file = join(DOCS, path);
  if (existsSync(file) && statSync(file).isDirectory()) file = join(file, "index.html");
  if (!file.startsWith(DOCS) || !existsSync(file)) return res.writeHead(404).end();
  res.writeHead(200, { "Content-Type": TYPES[extname(file)] || "application/octet-stream" });
  res.end(readFileSync(file));
});
await new Promise((r) => server.listen(0, "127.0.0.1", r));
const origin = `http://127.0.0.1:${server.address().port}`;

const exe = join(homedir(), ".cache/puppeteer/chrome-headless-shell/mac_arm-152.0.7977.54/chrome-headless-shell-mac-arm64/chrome-headless-shell");
const browser = await puppeteer.launch({
  executablePath: process.env.CHROME_PATH || exe,
  headless: true,
  protocolTimeout: 0,
  args: ["--use-mock-keychain", "--disable-features=MacAppCodeSignClone", `--user-data-dir=${process.env.PROFILE}`,
    "--enable-unsafe-webgpu", "--use-angle=metal", "--enable-gpu"],
});
const page = await browser.newPage();
await page.goto(`${origin}/app/`, { waitUntil: "networkidle0" });
await page.evaluate(() => {
  window.__w = new Worker(new URL("./engine-worker.js", location.href), { type: "module" });
  window.__call = (m) => new Promise((res, rej) => {
    window.__w.onmessage = ({ data }) => {
      if (data.type === "progress") return;
      data.type === "error" ? rej(new Error(data.message)) : res(data);
    };
    window.__w.postMessage(m);
  });
});
const caps = await page.evaluate(() => window.__call({ type: "capabilities" }));
console.error("device", JSON.stringify(caps));
mkdirSync(join(ROOT, "data/results"), { recursive: true });

for (const id of models) {
  const t0 = Date.now();
  await page.evaluate(async (id) => {
    const { REWRITERS } = await import("./models.js");
    await window.__call({ type: "prepare", parts: REWRITERS.find((r) => r.id === id).parts });
  }, id);
  console.error(`${id}: loaded in ${((Date.now() - t0) / 1000).toFixed(0)} s`);
  for (const s of samples) {
    if (done.has(`${id}/${s.id}`)) continue;
    const r = await page.evaluate(async (s, id) => {
      const t = performance.now();
      const out = await window.__call({ type: "rewrite", text: s.text, lang: s.lang, rewriter: id });
      return { seconds: (performance.now() - t) / 1000, text: out.text };
    }, s, id);
    appendFileSync(OUT, JSON.stringify({ model: id, id: s.id, lang: s.lang, seconds: r.seconds, text: r.text }) + "\n");
    console.error(`${id} ${s.id}: ${r.seconds.toFixed(1)} s`);
  }
}
await browser.close();
server.close();
