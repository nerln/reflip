// The page: language, tabs, the three tools, and the panel that shows what was sent.
//
// The text a person pastes goes to two places only: the facts check in this file, and the
// worker on this device. While the worker has it, the page holds the network lock too, so
// neither side can open a connection until the answer is back.

import { install, isLocked, whileLocked } from "./guard.js";
import { diff } from "./facts.js";
import { assess, precheck } from "./assess.js";
import { DETECTOR, REWRITERS, partBytes, partKey } from "./models.js";
import { ENDPOINT, count, optedOut, sentBodies } from "./stats.js";
import { LANGS, bytes, fill, num, pct, pickLanguage, strings } from "./i18n.js";

install(window);

const $ = (id) => document.getElementById(id);
let ui = pickLanguage();
let T = strings(ui);
let calib = null;
let caps = null;
let cached = new Set();
let busy = false;
const worker = new Worker(new URL("./engine-worker.js", import.meta.url), { type: "module" });

// ------------------------------------------------------------------ language and tabs

function applyLanguage() {
  T = strings(ui);
  document.documentElement.lang = ui;
  $("ui-lang").value = ui;
  for (const el of document.querySelectorAll("[data-t]")) el.textContent = T[el.dataset.t] ?? el.textContent;
  for (const el of document.querySelectorAll("[data-ph]")) el.placeholder = T[el.dataset.ph] ?? "";
  renderDetectControls();
  renderRewriteControls();
  renderSent();
}

$("ui-lang").addEventListener("change", (e) => {
  ui = LANGS.includes(e.target.value) ? e.target.value : "en";
  try { localStorage.setItem("reflip.ui", ui); } catch {}
  applyLanguage();
});

for (const tab of document.querySelectorAll('[role="tab"]')) {
  tab.addEventListener("click", () => {
    for (const t of document.querySelectorAll('[role="tab"]')) {
      const on = t === tab;
      t.setAttribute("aria-selected", String(on));
      $(t.getAttribute("aria-controls")).hidden = !on;
    }
  });
}

// ------------------------------------------------------------------ facts

const factLang = (text) => {
  const p = precheck(text, { words: { any: [0, 1e9] } });
  return ["en", "it", "es"].includes(p.language) ? p.language : null;
};

function renderFacts(target, d) {
  const box = $(target);
  box.replaceChildren();
  const p = (cls, text) => {
    const el = document.createElement("p");
    if (cls) el.className = cls;
    el.textContent = text;
    box.append(el);
  };
  if (!d) {
    p("bad", T.facts_lang);
    return;
  }
  if (!d.altered) p("head good", T.facts_none);
  else p("head bad", fill(T.facts_some, { n: d.altered, p: num(d.per_1000_words, ui, 1) }));
  const both = (label, part, f = (x) => x) => {
    const bits = [];
    if (part.missing.length) bits.push(`${T.gone}: ${part.missing.map(f).join(", ")}`);
    if (part.added.length) bits.push(`${T.added}: ${part.added.map(f).join(", ")}`);
    if (bits.length) p("", `${label}. ${bits.join("; ")}.`);
  };
  both(T.numbers, d.numbers, (x) => num(Number(x), ui, 6));
  both(T.names, d.names);
  if (d.negations.before !== d.negations.after) {
    p("", `${T.negations}. ${fill(T.neg_line, { a: d.negations.before, b: d.negations.after })}.`);
  }
  both(T.quantifiers, d.quantifiers, (q) => T.q[q] || q);
  p("small", T.facts_limit);
}

$("compare").addEventListener("click", () => {
  const a = $("text").value.normalize("NFC");
  const b = $("after").value.normalize("NFC");
  if (!a.trim() || !b.trim()) return;
  const lang = factLang(a);
  renderFacts("facts-out", lang ? diff(a, b, lang) : null);
  count("facts");
});

// ------------------------------------------------------------------ worker plumbing

let pending = null;
worker.onmessage = ({ data }) => {
  if (data.type === "progress") return pending?.progress?.(data);
  if (data.type === "capabilities") return pending?.resolve(data);
  const p = pending;
  pending = null;
  if (!p) return;
  if (data.type === "error") p.reject(new Error(data.message));
  else if (data.type === "cancelled") p.reject(Object.assign(new Error("cancelled"), { cancelled: true }));
  else p.resolve(data);
};

function call(msg, progress) {
  return new Promise((resolve, reject) => {
    pending = { resolve, reject, progress };
    worker.postMessage(msg);
  });
}

function setBusy(on) {
  busy = on;
  $("lockline").hidden = !isLocked();
  renderDetectControls();
  renderRewriteControls();
}

// Download (network on), then process (network locked on both sides).
async function run({ parts, status, msg, cancelBtn }) {
  setBusy(true);
  try {
    // the worker skips what it already holds in memory; the network is open only here
    const missing = parts.filter((p) => !cached.has(partKey(p)));
    await call({ type: "prepare", parts }, (d) => {
      $(status).textContent = d.phase === "download"
        ? fill(T.downloading, { done: bytes(d.done, ui), total: bytes(d.total, ui) })
        : fill(T.loading, { done: d.done, total: d.total });
    });
    if (missing.length) count("model_download", "-", msg.model);
    missing.forEach((p) => cached.add(partKey(p)));
    renderStored();
    $(status).textContent = T.working;
    $(cancelBtn).hidden = false;
    return await whileLocked(async () => {
      $("lockline").hidden = false;
      try {
        return await call(msg.body, (d) => {
          if (d.phase === "rewrite") $(status).textContent = fill(T.rewriting, { i: d.done + 1, n: d.total });
        });
      } finally {
        $("lockline").hidden = true;
      }
    });
  } finally {
    $(cancelBtn).hidden = true;
    setBusy(false);
    renderSent();
  }
}

// ------------------------------------------------------------------ detect

const detectorBytes = () => DETECTOR.parts.reduce((s, p) => s + partBytes(p), 0);
const detectorReady = () => DETECTOR.parts.every((p) => cached.has(partKey(p)));

function renderDetectControls() {
  $("detect-intro").textContent = fill(T.detect_intro, { size: bytes(detectorBytes(), ui) });
  const btn = $("detect");
  const unavailable = !calib ? T.detect_no_calib : "";
  $("detect-unavailable").hidden = !unavailable;
  $("detect-unavailable").textContent = unavailable;
  btn.textContent = detectorReady() ? T.check : fill(T.download_detector, { size: bytes(detectorBytes(), ui) });
  btn.disabled = busy || !!unavailable || !caps;
}

function renderAnswer(a) {
  const box = $("detect-out");
  box.replaceChildren();
  const p = (cls, text) => {
    const el = document.createElement("p");
    if (cls) el.className = cls;
    el.textContent = text;
    box.append(el);
  };
  const L = T.lang_names[a.language] || a.language;
  if (a.human_tail) {
    const t = a.human_tail;
    p("", fill(T.tail, { of: t.of, k: t.count, share: pct(t.share, ui), lo: pct(t.low, ui), hi: pct(t.high, ui) }));
  }
  if (a.verdict === "machine-like") p("head bad", fill(T.verdict_machine, { up: pct(a.cell.fpr_upper, ui), lang: L }));
  else if (a.verdict === "no evidence") p("head", T.verdict_none);
  const r = a.refused;
  if (r?.why === "too_short") p("head", fill(T.refuse_short, { w: r.words, min: r.min }));
  else if (r?.why === "language") p("head", T.refuse_lang);
  else if (r?.why === "one_sentence") p("head", T.refuse_one);
  else if (r?.why === "cell") {
    const c = a.cell || {};
    p("head", c.auroc_low == null ? fill(T.refuse_cell_none, { lang: L })
      : fill(T.refuse_cell, { lang: L, auc: num(c.auroc, ui), lo: num(c.auroc_low, ui), tpr: pct(c.tpr, ui), up: pct(c.fpr_upper, ui) }));
  }
  if (a.human_tail) {
    const l2 = a.learners;
    p("", l2 ? fill(T.learners, { lang: L, k: l2.fp, n: l2.n, share: pct(l2.fpr, ui), up: pct(l2.fpr_upper, ui) })
      : fill(T.learners_none, { lang: L }));
  }
  p("small", T.vendor);
}

$("detect").addEventListener("click", async () => {
  const text = $("text").value.normalize("NFC");
  if (!text.trim() || !calib) return;
  const pre = precheck(text, calib);
  if (pre.refused) {
    renderAnswer({ ...pre, human_tail: null });
    return;
  }
  try {
    const res = await run({ parts: DETECTOR.parts, status: "detect-status",
      cancelBtn: "detect-cancel", msg: { model: DETECTOR.id, body: { type: "detect", text } } });
    renderAnswer(assess(text, res.features, calib));
    $("detect-status").textContent = "";
    count("detect", "-", DETECTOR.id);
  } catch (e) {
    $("detect-status").textContent = e.cancelled ? T.cancelled : fill(T.error, { m: e.message });
  }
});

// ------------------------------------------------------------------ rewrite

function rewriterBytes(rw) {
  return rw.parts.filter((p) => !cached.has(partKey(p))).reduce((s, p) => s + partBytes(p), 0);
}

function renderRewriteControls() {
  const sel = $("rewriter");
  const keep = sel.value;
  sel.replaceChildren(...REWRITERS.map((rw) => {
    const o = document.createElement("option");
    o.value = rw.id;
    o.textContent = `${rw.label} (${bytes(rw.parts.reduce((s, p) => s + partBytes(p), 0), ui)})`;
    return o;
  }));
  if (keep) sel.value = keep;
  const rw = REWRITERS.find((r) => r.id === sel.value) || REWRITERS[0];
  const extra = rewriterBytes(rw);
  $("rewrite").textContent = extra ? fill(T.download_rewriter, { size: bytes(extra, ui) }) : T.rewrite;
  const unavailable = caps && !caps.webgpu || caps && !caps.f16 ? T.no_gpu : "";
  $("rewrite-unavailable").hidden = !unavailable;
  $("rewrite-unavailable").textContent = unavailable;
  $("rewrite").disabled = busy || !!unavailable || !caps;
}
$("rewriter").addEventListener("change", renderRewriteControls);

$("rewrite").addEventListener("click", async () => {
  const text = $("text").value.normalize("NFC");
  if (!text.trim()) return;
  const rw = REWRITERS.find((r) => r.id === $("rewriter").value);
  const lang = factLang(text);
  try {
    const res = await run({ parts: rw.parts, status: "rewrite-status", cancelBtn: "rewrite-cancel",
      msg: { model: rw.id, body: { type: "rewrite", text, lang, rewriter: rw.id } } });
    $("rewrite-result").hidden = false;
    $("rewritten").value = res.text;
    renderFacts("rewrite-facts", lang ? diff(text, res.text, lang) : null);
    $("rewrite-status").textContent = "";
    count("rewrite", "-", rw.id);
  } catch (e) {
    $("rewrite-status").textContent = e.cancelled ? T.cancelled : fill(T.error, { m: e.message });
  }
});

for (const id of ["detect-cancel", "rewrite-cancel"]) $(id).addEventListener("click", () => worker.postMessage({ type: "cancel" }));

$("copy").addEventListener("click", async () => {
  try {
    await navigator.clipboard.writeText($("rewritten").value);
    $("copy").textContent = T.copied;
    setTimeout(() => ($("copy").textContent = T.copy), 1500);
  } catch {}
});

// ------------------------------------------------------------------ stored models, sent panel

function renderStored() {
  const names = [...cached].map((k) => k.replace("onnx-community/", "").replace("@", " "));
  $("stored").textContent = names.length ? fill(T.stored, { list: names.join(", ") }) : "";
  $("forget").hidden = !names.length || busy;
}

$("forget").addEventListener("click", async () => {
  await call({ type: "forget" });
  cached = new Set();
  renderStored();
  renderDetectControls();
  renderRewriteControls();
  $("stored").textContent = T.forgotten;
});

function renderSent() {
  const box = $("sent-body");
  box.replaceChildren();
  const p = document.createElement("p");
  if (optedOut()) {
    p.textContent = T.sent_gpc;
    box.append(p);
    return;
  }
  const bodies = sentBodies();
  p.textContent = bodies.length ? fill(T.sent_intro, { host: new URL(ENDPOINT).host }) : T.sent_none;
  box.append(p);
  for (const b of bodies) {
    const c = document.createElement("code");
    c.textContent = b;
    const line = document.createElement("div");
    line.append(c);
    box.append(line);
  }
}
$("sent").addEventListener("toggle", renderSent);

// ------------------------------------------------------------------ start

applyLanguage();
count("page", "app");
renderSent();

(async () => {
  try {
    calib = await (await fetch("calibration-browser.json", { cache: "no-cache" })).json();
  } catch {
    calib = null;
  }
  caps = await call({ type: "capabilities" });
  cached = new Set(caps.cached || []);
  renderStored();
  renderDetectControls();
  renderRewriteControls();
})();
