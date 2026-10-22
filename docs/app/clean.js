// What a small model wraps around a rewrite, taken off before anyone reads it.
//
// Measured on the 24 benchmark texts on 22 October 2026: Gemma 3 1B opened 14 of its 24
// rewrites with a line like "Okay, here's a revised version of the text:", and Qwen2.5 0.5B
// once copied the retry instruction into its answer. Left in, those lines are text the
// person did not write, and the facts check counts their words as new facts.

const PREAMBLE = /\b(here|version|rewrit|revised|paraphras|reworded|text)\w*/i;
const ECHO = /previous attempt|negation.{0,40}quantifier|quantifier.{0,40}negation|^\s*TEXT:\s*$/i;
const CODA = /^\s*(\*\*)?(i hope|hope this|let me know|would you like|do you want|feel free|note:|this version|this rewrite|i've|i have)/i;

export function cleanReply(text) {
  let lines = text.replace(/<think>[\s\S]*?<\/think>/g, "").split("\n");
  // an opening line that announces the rewrite and ends in a colon
  while (lines.length && !lines[0].trim()) lines.shift();
  if (lines.length > 1 && /:\s*$/.test(lines[0]) && PREAMBLE.test(lines[0]) && lines[0].length < 200) lines.shift();
  lines = lines.filter((l) => !ECHO.test(l));
  // a closing remark after the rewrite, and the rule or blank lines before it
  for (;;) {
    while (lines.length && !lines[lines.length - 1].trim()) lines.pop();
    const last = lines[lines.length - 1] ?? "";
    if (lines.length > 1 && (CODA.test(last) || /^\s*(-{3,}|\*{3,})\s*$/.test(last))) lines.pop();
    else break;
  }
  let out = lines.join("\n").trim();
  const quoted = out.match(/^["“]([\s\S]*)["”]$/);
  if (quoted && !quoted[1].includes('"') && !/[“”]/.test(quoted[1])) out = quoted[1].trim();
  return out;
}
