// What the reflip site is allowed to count, and nothing else.
//
// Every field is a closed list. A value that is not on its list is not stored, not
// truncated, not bucketed: the whole event is refused. That is the mechanism that keeps the
// text a person pastes out of the statistics. A free-form string field, however carefully
// used, would one day carry a sentence; a list of words chosen here cannot.
//
// Deliberately absent, because each is computed from the user's text: its length or word
// count, any hash, the detected language, the detector's verdict or score, whether the tool
// refused and why (a refusal is decided by the length), and how long the work took. Also
// absent, on the advice of the expansion council (docs/council/2026-10-21-espansione.md):
// how an operation ended, because a failure can follow from the text (too long, out of
// memory); what the device could run, and the interface language, because together with the
// rest they describe the person rather than the use of the tool.
//
// The same file is served to the browser as docs/app/stats-schema.js; a test fails if the
// two copies differ by one byte.

export const SCHEMA = Object.freeze({
  v: Object.freeze([1]),
  // what happened
  e: Object.freeze(["page", "model_download", "facts", "detect", "rewrite"]),
  // which page, for "page"; "-" otherwise
  f: Object.freeze(["home", "app", "privacy", "-"]),
  // which model the person picked; "-" when no model is involved
  m: Object.freeze(["qwen2.5-0.5b", "gemma-3-1b", "llama-3.2-1b", "-"]),
});

export const FIELDS = Object.freeze(Object.keys(SCHEMA));
export const MAX_BODY = 256;

// Returns the event as a plain object if every field is present and allowed, else null.
export function validate(event) {
  if (event === null || typeof event !== "object" || Array.isArray(event)) return null;
  const keys = Object.keys(event);
  if (keys.length !== FIELDS.length) return null;
  const out = {};
  for (const k of FIELDS) {
    if (!Object.prototype.hasOwnProperty.call(event, k)) return null;
    if (!SCHEMA[k].includes(event[k])) return null;
    out[k] = event[k];
  }
  return out;
}
