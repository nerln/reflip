// The detectors' arithmetic, a port of features_from_logits and burstiness_from in
// reflip/detect.py. Rows of logits come in one at a time, so the 150,000-wide vocabulary is
// never copied: a 512-token text is two 155 MB tensors already, and that is enough.

const SENTENCE_END = /[.!?…]+["'”’»)\]]*(?=\s|$)/g;

export function sentenceSpans(text) {
  const spans = [];
  let start = 0;
  for (const m of text.matchAll(SENTENCE_END)) {
    const end = m.index + m[0].length;
    if (text.slice(start, end).trim()) spans.push([start, end]);
    start = end;
  }
  if (text.slice(start).trim()) spans.push([start, text.length]);
  return spans;
}

// Standard deviation of the per-sentence mean NLL; null with fewer than two usable sentences.
export function burstinessFrom(nll, starts, text) {
  const spans = sentenceSpans(text);
  if (spans.length < 2) return [null, spans.length];
  const sums = new Array(spans.length).fill(0);
  const counts = new Array(spans.length).fill(0);
  let j = 0;
  for (let i = 0; i < nll.length && i < starts.length; i++) {
    while (j < spans.length - 1 && starts[i] >= spans[j][1]) j++;
    sums[j] += nll[i];
    counts[j] += 1;
  }
  const means = [];
  for (let k = 0; k < spans.length; k++) if (counts[k] >= 3) means.push(sums[k] / counts[k]);
  if (means.length < 2) return [null, spans.length];
  const mu = means.reduce((a, b) => a + b, 0) / means.length;
  return [Math.sqrt(means.reduce((a, m) => a + (m - mu) ** 2, 0) / means.length), spans.length];
}

// Half-precision bits to a number, for logits that arrive as a Uint16Array.
const F16 = new Float32Array(1);
const U32 = new Uint32Array(F16.buffer);
function half(h) {
  const s = (h & 0x8000) << 16;
  const e = (h >> 10) & 0x1f;
  const m = h & 0x3ff;
  if (e === 0) return (s ? -1 : 1) * m * 2 ** -24;
  if (e === 31) return m ? NaN : s ? -Infinity : Infinity;
  U32[0] = s | ((e + 112) << 23) | (m << 13);
  return F16[0];
}

// A row reader over a [1, T, V] logits tensor's flat data, whatever its element type.
export function rows(data, V) {
  const isHalf = data instanceof Uint16Array;
  return (t, out) => {
    const base = t * V;
    for (let i = 0; i < V; i++) out[i] = isHalf ? half(data[base + i]) : data[base + i];
    return out;
  };
}

function logSoftmaxInPlace(x) {
  let max = -Infinity;
  for (let i = 0; i < x.length; i++) if (x[i] > max) max = x[i];
  let sum = 0;
  for (let i = 0; i < x.length; i++) sum += Math.exp(x[i] - max);
  const logZ = max + Math.log(sum);
  for (let i = 0; i < x.length; i++) x[i] -= logZ;
}

// obsRow(t, buf) and perfRow(t, buf) fill buf with the logits that predict token t + 1.
export function featuresFromRows(obsRow, perfRow, V, ids, starts, text) {
  const T = ids.length;
  if (T < 2) throw new Error("a text needs at least two tokens to be scored");
  const n = T - 1;
  const lo = new Float64Array(V);
  const lp = new Float64Array(V);
  let sumNllO = 0, sumNllP = 0, sumXent = 0;
  let llO = 0, meanOO = 0, varOO = 0, meanPO = 0, varPO = 0;
  const perToken = new Float64Array(n);
  for (let t = 0; t < n; t++) {
    obsRow(t, lo);
    perfRow(t, lp);
    logSoftmaxInPlace(lo);
    logSoftmaxInPlace(lp);
    const tgt = ids[t + 1];
    const nllO = -lo[tgt];
    const nllP = -lp[tgt];
    let xent = 0, mOO = 0, sOO = 0, mPO = 0, sPO = 0;
    for (let i = 0; i < V; i++) {
      const a = lo[i];
      const po = Math.exp(a);
      const pp = Math.exp(lp[i]);
      xent -= po * lp[i];
      mOO += po * a;
      sOO += po * a * a;
      mPO += pp * a;
      sPO += pp * a * a;
    }
    sumNllO += nllO;
    sumNllP += nllP;
    sumXent += xent;
    llO -= nllO;
    meanOO += mOO;
    varOO += sOO - mOO * mOO;
    meanPO += mPO;
    varPO += sPO - mPO * mPO;
    perToken[t] = nllO;
  }
  const nllObs = sumNllO / n;
  const nllPerf = sumNllP / n;
  const xent = sumXent / n;
  const [burstiness, sentences] = burstinessFrom(perToken, starts.slice(1), text);
  return {
    tokens: T,
    nll_obs: nllObs,
    nll_perf: nllPerf,
    xent,
    binoculars: xent > 0 ? nllPerf / xent : Infinity,
    fdg_oo: (llO - meanOO) / Math.sqrt(Math.max(varOO, 1e-9)),
    fdg_po: (llO - meanPO) / Math.sqrt(Math.max(varPO, 1e-9)),
    burstiness,
    sentences,
    ppl_obs: Math.exp(Math.min(nllObs, 50)),
  };
}
