// What a rewrite changed in the facts of a text: numbers, names, negations, quantifiers.
//
// A line-by-line port of reflip/facts.py, reading the same lexicon. Both versions run the
// cases in tests/fixtures/facts-cases.json, so they cannot drift apart unnoticed. No model,
// no network: it works the moment the page has loaded.

import LEXICON from "./facts-lexicon.js";

const WORD = /[0-9]+(?:[.,'  ][0-9]{3})*(?:[.,][0-9]+)?%?|\p{L}+(?:['’-]\p{L}+)*/gu;
const SENTENCE_END = /[.!?…]+["'”»)\]]*\s+|\n/g;
const OPENERS = new Set(" \t\r\n\"'“‘«([-–—*#>•");
const NEGATIVE_CONTRACTION = /n['’]t\b/gi;

const isDigit = (t) => t[0] >= "0" && t[0] <= "9";
const isUpper = (c) => c !== c.toLowerCase() && c === c.toUpperCase();

function stripSet(s, set) {
  let a = 0;
  let b = s.length;
  while (a < b && set.has(s[a])) a++;
  while (b > a && set.has(s[b - 1])) b--;
  return s.slice(a, b);
}

// Words and numbers, each with whether it opens a sentence or a line.
export function tokens(text) {
  const starts = [0];
  for (const m of text.matchAll(SENTENCE_END)) starts.push(m.index + m[0].length);
  const out = [];
  let k = 0;
  for (const m of text.matchAll(WORD)) {
    while (k + 1 < starts.length && starts[k + 1] <= m.index) k++;
    out.push([m[0], stripSet(text.slice(starts[k], m.index), OPENERS) === ""]);
  }
  return out;
}

export function digitValue(tok, lang) {
  let t = tok.replace(/%$/, "").replaceAll(" ", "").replaceAll(" ", "").replaceAll("'", "");
  if (lang === "en") t = t.replaceAll(",", "");
  else if (t.includes(",") || /\.\d{3}(?!\d)/.test(t)) t = t.replaceAll(".", "").replace(",", ".");
  const v = Number(t);
  return Number.isFinite(v) && t !== "" ? v : null;
}

const IT = LEXICON.numbers.it;
const IT_PARTS = [...Object.keys(IT.morphemes), ...IT.hundred, ...IT.thousand_one, ...IT.thousand_many,
  ...Object.keys(IT.scales)].sort((x, y) => y.length - x.length);

// Italian writes a number as one word: trecentoquarantacinque, duemila, ventitré.
export function italianWord(w) {
  if (IT.alone_excluded.includes(w) || w in IT.scales || IT.thousand_many.includes(w)) return null;
  let total = 0;
  let current = 0;
  let i = 0;
  while (i < w.length) {
    const p = IT_PARTS.find((q) => w.startsWith(q, i));
    if (p === undefined) return null;
    i += p.length;
    if (p in IT.morphemes) current += IT.morphemes[p];
    else if (IT.hundred.includes(p)) current = (current || 1) * 100;
    else if (IT.thousand_one.includes(p)) { total += 1000; current = 0; }
    else if (IT.thousand_many.includes(p)) { total += (current || 1) * 1000; current = 0; }
    else { total += (current || 1) * IT.scales[p]; current = 0; }
  }
  return w ? total + current : null;
}

// "two hundred and five", "treinta y tres": and/y only after a hundred, a scale or a ten.
function joins(prev, nxt, lex, lang) {
  if (lang === "en") return (lex.hundred.includes(prev) || prev in lex.scales) && nxt in lex.units;
  const ten = lex.units[prev] || 0;
  const unit = lex.units[nxt] || 0;
  return ten >= 30 && ten % 10 === 0 && unit > 0 && unit < 10;
}

// The value of each run of number words.
export function wordNumbers(words, lang) {
  const lex = LEXICON.numbers[lang];
  const scales = lex.scales;
  const out = [];
  const n = words.length;
  let i = 0;
  while (i < n) {
    if (lang === "it") {
      let v = italianWord(words[i]);
      if (v === null && lex.one.includes(words[i]) && i + 1 < n && words[i + 1] in scales) v = 1;
      if (v === null) { i++; continue; }
      let j = i + 1;
      let total = 0;
      let current = v;
      while (j < n) {
        if (words[j] in scales) { total += (current || 1) * scales[words[j]]; current = 0; j++; }
        else if (total && lex.joiners.includes(words[j]) && j + 1 < n && italianWord(words[j + 1]) !== null) {
          current += italianWord(words[j + 1]);
          j += 2;
        } else break;
      }
      out.push(total + current);
      i = j;
      continue;
    }
    // English and Spanish write a number as a run of words
    let j = i;
    let total = 0;
    let current = 0;
    let seen = false;
    while (j < n) {
      const x = words[j];
      const nxt = j + 1 < n ? words[j + 1] : "";
      if (x in lex.units) current += lex.units[x];
      else if (lang === "es" && x in lex.hundreds) current += lex.hundreds[x];
      else if (lang === "en" && lex.hundred.includes(x) && seen) current = (current || 1) * 100;
      else if (x in scales && (seen || (lex.alone_scales || []).includes(x))) {
        total += (current || 1) * scales[x];
        current = 0;
      } else if (!seen && lex.one.includes(x) && (nxt in scales || (lang === "en" && lex.hundred.includes(nxt)))) {
        current += 1;
      } else if (seen && lex.joiners.includes(x) && joins(words[j - 1], nxt, lex, lang)) {
        j++;
        continue;
      } else break;
      seen = true;
      j++;
    }
    if (seen) { out.push(total + current); i = j; } else i++;
  }
  return out;
}

class Bag extends Map {
  add(k, by = 1) { this.set(k, (this.get(k) || 0) + by); }
  minus(other) {
    const out = new Bag();
    for (const [k, v] of this) if (v - (other.get(k) || 0) > 0) out.set(k, v - (other.get(k) || 0));
    return out;
  }
  elements() { return [...this].flatMap(([k, v]) => Array(v).fill(k)); }
  total() { let s = 0; for (const v of this.values()) s += v; return s; }
}

export function facts(text, lang) {
  const f = { numbers: new Bag(), names: new Bag(), lowered: new Set(), negations: 0, quantifiers: new Bag(), words: 0 };
  const toks = tokens(text);
  const words = toks.map(([t]) => t.toLowerCase());
  f.words = toks.filter(([t]) => !isDigit(t)).length;
  const scales = LEXICON.numbers[lang].scales;
  toks.forEach(([t], k) => {
    if (!isDigit(t)) return;
    const v = digitValue(t, lang);
    // "3 million" is the number three million, as "three million" is
    if (v !== null) f.numbers.add(v * (scales[words[k + 1]] || 1));
  });
  const split = words.filter((w) => !isDigit(w)).flatMap((w) => w.split("-"));
  for (const v of wordNumbers(split, lang)) f.numbers.add(v);
  for (const [t, opening] of toks) {
    f.lowered.add(t.toLowerCase());
    if (isUpper(t[0]) && t.length > 1 && !opening) f.names.add(t);
  }
  const neg = new Set(LEXICON.negations[lang]);
  f.negations = split.filter((w) => neg.has(w)).length;
  if (lang === "en") f.negations += (text.match(NEGATIVE_CONTRACTION) || []).length;
  let lowered = " " + split.join(" ") + " ";
  const qs = Object.entries(LEXICON.quantifiers[lang])
    .sort((x, y) => y[0].length - x[0].length || (x[0] < y[0] ? -1 : x[0] > y[0] ? 1 : 0));
  for (const [phrase, cls] of qs) {
    const k = lowered.split(" " + phrase + " ").length - 1;
    if (k) {
      f.quantifiers.add(cls, k);
      lowered = lowered.replaceAll(" " + phrase + " ", " | ");
    }
  }
  return f;
}

const fmt = (v) => (Number.isInteger(v) ? String(v) : String(parseFloat(v.toPrecision(6))));
const sorted = (xs) => [...xs].sort((x, y) => (x < y ? -1 : x > y ? 1 : 0));

// What changed between two texts, and how many facts that is per thousand words.
export function diff(original, rewritten, lang) {
  const a = facts(original, lang);
  const b = facts(rewritten, lang);
  const missingNum = a.numbers.minus(b.numbers);
  const addedNum = b.numbers.minus(a.numbers);
  // a name is kept if the word appears anywhere in the other text, in any case: moved to the
  // start of a sentence, or written in capitals, it is the same name
  const missingNames = new Bag([...a.names.minus(b.names)].filter(([k]) => !b.lowered.has(k.toLowerCase())));
  const addedNames = new Bag([...b.names.minus(a.names)].filter(([k]) => !a.lowered.has(k.toLowerCase())));
  const missingQ = a.quantifiers.minus(b.quantifiers);
  const addedQ = b.quantifiers.minus(a.quantifiers);
  const altered = missingNum.total() + addedNum.total() + missingNames.total() + addedNames.total()
    + Math.abs(a.negations - b.negations) + missingQ.total() + addedQ.total();
  return {
    lang,
    words: a.words,
    altered,
    per_1000_words: a.words ? Math.round((10000 * altered) / a.words) / 10 : 0,
    numbers: { missing: sorted(missingNum.elements().map(fmt)), added: sorted(addedNum.elements().map(fmt)) },
    names: { missing: sorted(missingNames.elements()), added: sorted(addedNames.elements()) },
    negations: { before: a.negations, after: b.negations },
    quantifiers: { missing: sorted(missingQ.elements()), added: sorted(addedQ.elements()) },
  };
}
