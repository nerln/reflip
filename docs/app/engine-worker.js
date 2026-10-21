// The worker that downloads, checks, loads and runs the models, all on this device.
//
// Messages are listed in web/HOW-IT-WORKS.md. The network is used in one place only,
// `prepare`, to download model files from Hugging Face. `detect` and `rewrite` hold the
// network lock from their first line to their last, and transformers.js is told not to
// fetch anything while they run: a file that is not already on the device is an error,
// not a download.

import { install, whileLocked } from "./guard.js";
import { featuresFromRows, rows } from "./detect.js";
import { diff } from "./facts.js";
import { DETECTOR, REPOS, REWRITERS, SMALL_FILES, WEIGHTS, fileURL } from "./models.js";
import { AutoModelForCausalLM, AutoTokenizer, InterruptableStoppingCriteria, Tensor, env } from "./vendor/transformers.min.js";

install(self);

env.allowLocalModels = false;
env.useBrowserCache = true;
env.backends.onnx.wasm.wasmPaths = {
  mjs: new URL("./vendor/ort-wasm-simd-threaded.asyncify.mjs", import.meta.url).href,
  wasm: new URL("./vendor/ort-wasm-simd-threaded.asyncify.wasm", import.meta.url).href,
};

const MAX_TOKENS = 512;
const CACHE = "transformers-cache";
let device = "webgpu";
const loaded = new Map(); // repo -> model
let tokenizer = null; // the Qwen2.5 tokenizer, shared by the detector pair
const tokenizers = new Map();
let stopper = null;
let cancelled = false;

const post = (msg) => self.postMessage(msg);

async function capabilities() {
  let webgpu = false;
  let f16 = false;
  try {
    const adapter = await navigator.gpu?.requestAdapter();
    webgpu = !!adapter;
    f16 = !!adapter?.features?.has("shader-f16");
  } catch {}
  device = webgpu && f16 ? "webgpu" : "wasm";
  return { webgpu, f16, device };
}

function hex(buf) {
  return [...new Uint8Array(buf)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

// Download one file into the cache transformers.js reads from, checking its SHA-256 first.
async function ensure(repo, file, onBytes) {
  const url = fileURL(repo, file);
  const cache = await caches.open(CACHE);
  if (await cache.match(url)) return 0;
  const res = await fetch(url);
  if (!res.ok) throw new Error(`${repo}/${file}: HTTP ${res.status}`);
  const total = Number(res.headers.get("Content-Length")) || (file === WEIGHTS ? REPOS[repo].size : 0);
  const reader = res.body.getReader();
  const chunks = [];
  let got = 0;
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    chunks.push(value);
    got += value.byteLength;
    onBytes(value.byteLength);
  }
  const body = new Uint8Array(got);
  let at = 0;
  for (const c of chunks) {
    body.set(c, at);
    at += c.byteLength;
  }
  chunks.length = 0;
  if (file === WEIGHTS) {
    const want = REPOS[repo].sha256;
    const have = hex(await crypto.subtle.digest("SHA-256", body));
    if (have !== want) throw new Error(`${repo}/${file}: SHA-256 ${have} is not the pinned ${want}`);
  }
  await cache.put(url, new Response(body, { headers: { "Content-Type": res.headers.get("Content-Type") || "application/octet-stream", "Content-Length": String(got) } }));
  return total;
}

async function prepare(repos) {
  const need = repos.filter((r) => !loaded.has(r));
  const total = need.reduce((s, r) => s + REPOS[r].size, 0);
  let done = 0;
  const onBytes = (n) => {
    done += n;
    post({ type: "progress", phase: "download", done, total });
  };
  for (const repo of need) {
    for (const f of SMALL_FILES) await ensure(repo, f, () => {});
    await ensure(repo, WEIGHTS, onBytes);
  }
  post({ type: "progress", phase: "load", done: 0, total: need.length });
  let k = 0;
  for (const repo of need) {
    const opts = { revision: REPOS[repo].rev, dtype: "q4f16", device };
    loaded.set(repo, await AutoModelForCausalLM.from_pretrained(repo, opts));
    tokenizers.set(repo, await AutoTokenizer.from_pretrained(repo, { revision: REPOS[repo].rev }));
    post({ type: "progress", phase: "load", done: ++k, total: need.length });
  }
  if (repos.includes(DETECTOR.observer)) tokenizer = tokenizers.get(DETECTOR.observer);
}

async function cachedRepos() {
  const cache = await caches.open(CACHE);
  const out = [];
  for (const repo of Object.keys(REPOS)) if (await cache.match(fileURL(repo, WEIGHTS))) out.push(repo);
  return out;
}

async function forget() {
  await caches.delete(CACHE);
  loaded.clear();
  tokenizers.clear();
  tokenizer = null;
}

function int64(ids) {
  return new Tensor("int64", BigInt64Array.from(ids, (x) => BigInt(x)), [1, ids.length]);
}

async function detect(text) {
  env.allowRemoteModels = false;
  try {
    const enc = tokenizer(text, { add_special_tokens: false });
    const ids = Array.from(enc.input_ids.data, Number).slice(0, MAX_TOKENS);
    if (ids.length < 2) throw new Error("the text is too short to score");
    // where each token starts in the text, from the length of everything decoded before it
    const starts = ids.map((_, i) =>
      i === 0 ? 0 : tokenizer.decode(ids.slice(0, i), { skip_special_tokens: false, clean_up_tokenization_spaces: false }).length);
    const feeds = { input_ids: int64(ids), attention_mask: int64(ids.map(() => 1)) };
    const obs = (await loaded.get(DETECTOR.observer)(feeds)).logits;
    const perf = (await loaded.get(DETECTOR.performer)(feeds)).logits;
    const V = obs.dims[2];
    return featuresFromRows(rows(obs.data, V), rows(perf.data, V), V, ids, starts, text);
  } finally {
    env.allowRemoteModels = true;
  }
}

const RULES =
  "Rewrite the following text in your own words, changing the wording throughout (change at least every third word), " +
  "while keeping the meaning, tone, length (within 15%), language, names, numbers, and any markdown structure. " +
  "Keep every line break where it is. Keep every negation (not, never, no) and every quantifier " +
  "(all, most, some, only, at least) exactly as strong as it is. Reply with the rewritten text only.\n\n";
const STRONG =
  "The previous attempt changed a number, a name, a negation or a quantifier. Change the other words, " +
  "and keep every name, number, negation and quantifier exactly.\n\n";

async function ask(rw, block, strong) {
  const repo = rw.repos[0];
  const tok = tokenizers.get(repo);
  const messages = [
    { role: "system", content: "You rewrite text in your own words. Reply with the rewritten text only." },
    { role: "user", content: RULES + (strong ? STRONG : "") + "TEXT:\n" + block },
  ];
  const inputs = tok.apply_chat_template(messages, {
    add_generation_prompt: true, return_dict: true, enable_thinking: rw.thinking ?? undefined,
  });
  stopper = new InterruptableStoppingCriteria();
  const n = inputs.input_ids.dims[1];
  const out = await loaded.get(repo).generate({
    ...inputs, max_new_tokens: Math.min(2048, Math.ceil(n * 1.6) + 64), do_sample: false,
    stopping_criteria: stopper,
  });
  const text = tok.decode(out.slice(null, [n, out.dims[1]])[0], { skip_special_tokens: true });
  return text.replace(/<think>[\s\S]*?<\/think>/g, "").replace(/^TEXT:\s*/, "").trim();
}

async function rewrite(text, lang, rewriterId) {
  env.allowRemoteModels = false;
  cancelled = false;
  try {
    const rw = REWRITERS.find((r) => r.id === rewriterId);
    // paragraphs: blank lines and the text between them, rewritten one at a time
    const parts = text.split(/(\n\s*\n)/);
    const todo = parts.map((p, i) => (i % 2 === 0 && /\p{L}/u.test(p) ? i : -1)).filter((i) => i >= 0);
    let k = 0;
    for (const i of todo) {
      post({ type: "progress", phase: "rewrite", done: k++, total: todo.length });
      let best = null;
      for (let attempt = 0; attempt < 2; attempt++) {
        const out = await ask(rw, parts[i], attempt > 0);
        if (cancelled) throw new DOMException("cancelled", "AbortError");
        const altered = lang ? diff(parts[i], out, lang).altered : 0;
        if (!best || altered < best.altered) best = { out, altered };
        if (!altered) break;
      }
      if (best.out) parts[i] = best.out;
    }
    return parts.join("");
  } finally {
    env.allowRemoteModels = true;
  }
}

self.onmessage = async ({ data: msg }) => {
  try {
    if (msg.type === "capabilities") {
      post({ type: "capabilities", ...(await capabilities()), cached: await cachedRepos() });
    } else if (msg.type === "prepare") {
      await prepare(msg.repos);
      post({ type: "ready", repos: msg.repos });
    } else if (msg.type === "forget") {
      await forget();
      post({ type: "forgotten" });
    } else if (msg.type === "detect") {
      const features = await whileLocked(() => detect(msg.text));
      post({ type: "detected", features });
    } else if (msg.type === "rewrite") {
      const out = await whileLocked(() => rewrite(msg.text, msg.lang, msg.rewriter));
      post({ type: "rewritten", text: out });
    } else if (msg.type === "cancel") {
      cancelled = true;
      stopper?.interrupt();
    }
  } catch (e) {
    post({ type: e?.name === "AbortError" ? "cancelled" : "error", message: String(e?.message || e) });
  }
};
