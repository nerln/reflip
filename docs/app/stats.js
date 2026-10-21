// What the page counts, built only from the allowlist, sent only when the network lock is off.
//
// An event is four fields: the schema version, what happened, which page, which model. Each
// value comes from a closed list in stats-schema.js, the same file the counter enforces, so a
// sentence, a length or a score has nowhere to go: validate() returns null for anything that
// is not on a list and count() throws. No cookie, no identifier, no storage.

import { validate } from "./stats-schema.js";
import { isLocked, onUnlock } from "./guard.js";

export const ENDPOINT = "https://reflip-stats.nerln.workers.dev/e";

const queue = [];
const sent = [];

// A browser that sends Global Privacy Control or Do Not Track gets nothing counted at all.
export const optedOut = () =>
  navigator.globalPrivacyControl === true || navigator.doNotTrack === "1" || window.doNotTrack === "1";

export function event(e, f = "-", m = "-") {
  const ev = validate({ v: 1, e, f, m });
  if (!ev) throw new Error(`not an allowed statistics event: ${JSON.stringify({ e, f, m })}`);
  return ev;
}

export function count(e, f = "-", m = "-") {
  const ev = event(e, f, m);
  if (optedOut()) return;
  queue.push(ev);
  flush();
}

export function flush() {
  if (isLocked()) return;
  while (queue.length) {
    const body = JSON.stringify(queue.shift());
    sent.push(body);
    // text/plain keeps this a simple request: no preflight, no cookies, no referrer
    fetch(ENDPOINT, {
      method: "POST",
      body,
      headers: { "Content-Type": "text/plain" },
      credentials: "omit",
      referrerPolicy: "no-referrer",
      keepalive: true,
    }).catch(() => {});
  }
}

onUnlock(flush);

// Every body this page has sent, for the "what this page sends" panel and for the tests.
export const sentBodies = () => [...sent];
