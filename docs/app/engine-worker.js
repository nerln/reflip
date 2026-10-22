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
import { cleanReply } from "./clean.js";
import { DATA, DETECTOR, FILES, REPOS, REWRITERS, SMALL_FILES, fileURL, partBytes, partKey } from "./models.js";
import { Sha256 } from "./sha256.js";
import { AutoModelForCausalLM, AutoTokenizer, InterruptableStoppingCriteria, Tensor, env } from "./vendor/transformers.min.js";

install(self);

env.allowLocalModels = false;
// Model files live in the Origin Private File System, not the Cache Storage: browsers refuse
// a cache entry of a few hundred megabytes (measured: 150 MB stored, 300 MB refused), and a
// weights file is 483 MB. transformers.js reads them through the custom cache below.
env.useBrowserCache = false;
env.useWasmCache = false;
env.useCustomCache = true;
env.backends.onnx.wasm.wasmPaths = {
  mjs: new URL("./vendor/ort-wasm-simd-threaded.asyncify.mjs", import.meta.url).href,
  wasm: new URL("./vendor/ort-wasm-simd-threaded.asyncify.wasm", import.meta.url).href,
};

const DIR = "reflip-models";
const nameOf = (url) => url.replace(/^https:\/\/huggingface\.co\//, "").replace(/[^A-Za-z0-9._-]/g, "_");

async function modelsDir(create = true) {
  const root = await navigator.storage.getDirectory();
  return root.getDirectoryHandle(DIR, { create });
}

async function stored(url) {
  try {
    const dir = await modelsDir(false);
    await dir.getFileHandle(nameOf(url) + ".ok");
    return await (await dir.getFileHandle(nameOf(url))).getFile();
  } catch {
    return null;
  }
}

// Write a stream to a file, hashing it on the way; the ".ok" marker is written last, so a
// download cut short is never mistaken for a file.
async function store(url, stream, onBytes = () => {}) {
  const dir = await modelsDir();
  const name = nameOf(url);
  try { await dir.removeEntry(name + ".ok"); } catch {}
  const handle = await (await dir.getFileHandle(name, { create: true })).createSyncAccessHandle();
  const hash = new Sha256();
  try {
    handle.truncate(0);
    let at = 0;
    const reader = stream.getReader();
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      handle.write(value, { at });
      at += value.byteLength;
      hash.update(value);
      onBytes(value.byteLength);
    }
    handle.flush();
  } finally {
    handle.close();
  }
  return { hex: hash.hex(), ok: async () => (await dir.getFileHandle(name + ".ok", { create: true })) };
}

env.customCache = {
  async match(request) {
    const url = typeof request === "string" ? request : request.url;
    const file = await stored(url);
    return file ? new Response(file, { headers: { "Content-Length": String(file.size) } }) : undefined;
  },
  async put(request, response) {
    // only files transformers.js fetched itself while preparing, never during work
    const url = typeof request === "string" ? request : request.url;
    const saved = await store(url, response.body);
    await saved.ok();
  },
};

const MAX_TOKENS = 512;
// The detector runs on the processor. On WebGPU the same 4-bit files gave other scores
// (Binoculars 1.245 against 0.995 on one text, perplexity a nat and a half higher), which
// would have put every text on the wrong side of thresholds measured with onnxruntime on a
// CPU; in the browser's own CPU backend the scores match those to three decimals. Rewriting
// runs on WebGPU with the 32-bit-arithmetic files (see models.js), and needs it: on the
// processor one paragraph took 215 seconds.
let gpu = null;
const loaded = new Map(); // "repo@dtype" -> model
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
  gpu = webgpu && f16 ? "webgpu" : null;
  return { webgpu, f16, device: gpu || "wasm" };
}

// Download one file to the device. A weights file whose SHA-256 is not the pinned one is
// deleted before anything can load it.
async function ensure(repo, file, pin, onBytes) {
  const url = fileURL(repo, file);
  if (await stored(url)) {
    if (pin) onBytes(pin.size);
    return;
  }
  const res = await fetch(url);
  if (!res.ok) throw new Error(`${repo}/${file}: HTTP ${res.status}`);
  const saved = await store(url, res.body, pin ? onBytes : () => {});
  if (pin && saved.hex !== pin.sha256) {
    try { await (await modelsDir()).removeEntry(nameOf(url)); } catch {}
    throw new Error(`${repo}/${file}: SHA-256 ${saved.hex} is not the pinned ${pin.sha256}`);
  }
  await saved.ok();
}

// parts: [{repo, dtype}]. q4f16 parts load on the processor, q4 parts on the GPU.
async function prepare(parts) {
  const need = parts.filter((p) => !loaded.has(partKey(p)));
  const total = need.reduce((s, p) => s + partBytes(p), 0);
  let done = 0;
  const onBytes = (n) => {
    done += n;
    post({ type: "progress", phase: "download", done, total });
  };
  for (const { repo, dtype } of need) {
    for (const f of SMALL_FILES) await ensure(repo, f, null, () => {});
    const w = REPOS[repo].weights[dtype];
    await ensure(repo, FILES[dtype], { size: w.size - (w.data?.size || 0), sha256: w.sha256 }, onBytes);
    if (w.data) await ensure(repo, DATA(dtype), w.data, onBytes);
  }
  post({ type: "progress", phase: "load", done: 0, total: need.length });
  let k = 0;
  for (const p of need) {
    const device = p.dtype === "q4f16" ? "wasm" : gpu;
    if (!device) throw new Error("rewriting needs WebGPU");
    const opts = { revision: REPOS[p.repo].rev, dtype: p.dtype, device,
      use_external_data_format: !!REPOS[p.repo].weights[p.dtype].data };
    loaded.set(partKey(p), await AutoModelForCausalLM.from_pretrained(p.repo, opts));
    if (!tokenizers.has(p.repo)) tokenizers.set(p.repo, await AutoTokenizer.from_pretrained(p.repo, { revision: REPOS[p.repo].rev }));
    post({ type: "progress", phase: "load", done: ++k, total: need.length });
  }
  if (tokenizers.has(DETECTOR.observer)) tokenizer = tokenizers.get(DETECTOR.observer);
}

// Which parts are already on the device, as "repo@dtype".
async function storedParts() {
  const out = [];
  for (const [repo, r] of Object.entries(REPOS)) {
    for (const [dtype, w] of Object.entries(r.weights)) {
      if (await stored(fileURL(repo, FILES[dtype])) && (!w.data || await stored(fileURL(repo, DATA(dtype))))) out.push(`${repo}@${dtype}`);
    }
  }
  return out;
}

async function forget() {
  try { await (await navigator.storage.getDirectory()).removeEntry(DIR, { recursive: true }); } catch {}
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
    const obs = (await loaded.get(`${DETECTOR.observer}@q4f16`)(feeds)).logits;
    const perf = (await loaded.get(`${DETECTOR.performer}@q4f16`)(feeds)).logits;
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
  const repo = rw.parts[0].repo;
  const tok = tokenizers.get(repo);
  const messages = [
    { role: "system", content: "You rewrite text in your own words. Reply with the rewritten text only, with no introduction and no comment." },
    { role: "user", content: RULES + (strong ? STRONG : "") + "TEXT:\n" + block },
  ];
  const inputs = tok.apply_chat_template(messages, {
    add_generation_prompt: true, return_dict: true, enable_thinking: rw.thinking ?? undefined,
  });
  stopper = new InterruptableStoppingCriteria();
  const n = inputs.input_ids.dims[1];
  const out = await loaded.get(partKey(rw.parts[0])).generate({
    ...inputs, max_new_tokens: Math.min(2048, Math.ceil(n * 1.6) + 64), do_sample: false,
    stopping_criteria: stopper,
  });
  const text = tok.decode(out.slice(null, [n, out.dims[1]])[0], { skip_special_tokens: true });
  return cleanReply(text);
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
      post({ type: "capabilities", ...(await capabilities()), cached: await storedParts() });
    } else if (msg.type === "prepare") {
      await prepare(msg.parts);
      post({ type: "ready" });
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
