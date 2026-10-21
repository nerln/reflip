// A port of reflip/detect_assess.py: a score and the browser's calibration in, an answer or
// a refusal out. Numbers only; app.js turns them into sentences in the reader's language.

const STOP = {
  en: "the and of to is in that it was for with as on are this be by have not but from at which".split(" "),
  it: "il di che per un una non sono del della con gli nel alla anche come più dei delle questo".split(" "),
  es: "el que los las del por una con es para al su se como pero más sus este entre fue".split(" "),
};
const WORD = /[\p{L}\p{M}]+/gu;

export function guessLanguage(text) {
  const votes = { en: 0, it: 0, es: 0 };
  const sets = Object.fromEntries(Object.entries(STOP).map(([k, v]) => [k, new Set(v)]));
  for (const [w] of text.toLowerCase().matchAll(WORD)) {
    for (const k of Object.keys(sets)) if (sets[k].has(w)) votes[k]++;
  }
  const total = votes.en + votes.it + votes.es;
  if (!total) return [null, 0];
  const best = Object.keys(votes).reduce((a, b) => (votes[b] > votes[a] ? b : a));
  return [best, votes[best] / total];
}

export const wordCount = (text) => (text.match(WORD) || []).length;

export function scoreOf(calib, f, bucket) {
  switch (calib.detector) {
    case "binoculars": return -f.binoculars;
    case "fast_detectgpt": return f.fdg_oo;
    case "fast_detectgpt_cross": return f.fdg_po;
    case "perplexity": return -f.nll_obs;
    case "burstiness": return f.burstiness == null ? null : -f.burstiness;
    case "ppl_burstiness": {
      const p = calib.logistic[bucket];
      const burst = f.burstiness != null ? f.burstiness : p.fill_burst;
      return p.w_nll * f.nll_obs + p.w_burst * burst + p.bias;
    }
    default: throw new Error(`unknown detector ${calib.detector}`);
  }
}

export function bucketFor(words, calib) {
  for (const [name, [lo, hi]] of Object.entries(calib.words)) if (lo <= words && words <= hi) return name;
  // Longer than the longest measured texts: the detectors read 512 tokens anyway.
  const longest = Object.entries(calib.words).reduce((a, b) => (b[1][1] > a[1][1] ? b : a));
  return words > longest[1][1] ? longest[0] : null;
}

export function wilson(k, n, z = 1.96) {
  const p = k / n;
  const den = 1 + (z * z) / n;
  const c = (p + (z * z) / (2 * n)) / den;
  const h = (z * Math.sqrt((p * (1 - p)) / n + (z * z) / (4 * n * n))) / den;
  return [Math.max(0, c - h), Math.min(1, c + h)];
}

// The answer before any model runs: refusals that depend only on the text's length and language.
export function precheck(text, calib, lang = null) {
  const words = wordCount(text);
  const [guessed, share] = guessLanguage(text);
  lang = lang || guessed;
  const out = { words, language: lang, language_confidence: share, refused: null, bucket: null };
  const minWords = Math.min(...Object.values(calib.words).map(([lo]) => lo));
  if (words < minWords) out.refused = { why: "too_short", words, min: minWords };
  else if (!["en", "it", "es"].includes(lang)) out.refused = { why: "language" };
  else out.bucket = bucketFor(words, calib);
  return out;
}

export function assess(text, features, calib, lang = null) {
  const out = { ...precheck(text, calib, lang), detector: calib.detector, verdict: null,
    score: null, human_tail: null, cell: null, learners: null };
  if (out.refused || !features) return out;
  const s = scoreOf(calib, features, out.bucket);
  if (s == null) {
    out.refused = { why: "one_sentence" };
    return out;
  }
  const b = calib.buckets[out.bucket];
  const hs = b.human_scores;
  const k = hs.filter((v) => v >= s).length;
  const [lo, hi] = wilson(k, hs.length);
  out.score = s;
  out.human_tail = { count: k, of: hs.length, share: k / hs.length, low: lo, high: hi };
  out.cell = calib.cells[`${out.language}/${out.bucket}`] || {};
  out.learners = (calib.learners || {})[`human_l2/${out.language}/${out.bucket}`] || null;
  if (!out.cell.allowed) {
    out.refused = { why: "cell", reason: out.cell.why || "not measured" };
    return out;
  }
  out.verdict = s > b.threshold ? "machine-like" : "no evidence";
  return out;
}
