# reflip in the browser: how it is put together

The published files live in `docs/app/` and are served at https://nerln.github.io/reflip/app/.
This file is the contract between their parts. It is not published (it sits outside `docs/`).

## The promise, and where the code keeps it

Everything a person pastes is processed on their device. The site counts a few aggregate
events, and **never** the text, its length, a hash, the detected language, a verdict, a score,
a refusal reason or a duration: all of those are derived from the text. Following the
expansion council, it does not count how an operation ended, what the device can run or the
interface language either. This is enforced in code, in four places, each with a test:

1. **The allowlist.** `docs/app/stats-schema.js` (a byte-identical copy of
   `stats/src/schema.js`) lists every value each event field may take. `stats.js` builds an
   event only from those values and throws on anything else. The server refuses the same way.
2. **The network lock.** `guard.js` wraps `fetch`, `XMLHttpRequest`, `navigator.sendBeacon`,
   `WebSocket`, `EventSource` and image loads, in the page and inside the worker. While a text
   is being processed, any of them throws `NetworkLockedError`. Statistics are queued and only
   sent after the lock is released.
3. **The CSP.** A `<meta http-equiv="Content-Security-Policy">` on every page, with
   `connect-src 'self' https://huggingface.co https://*.hf.co https://reflip-stats.nerln.workers.dev`
   and nothing else. Model files come from Hugging Face; the counter is the worker. Scripts,
   styles, WebAssembly and workers come from the site itself (`'self'`), never a CDN.
   Its limit, stated plainly: a policy in a `<meta>` tag covers the page, not a worker loaded
   from its own URL, which takes its policy from its own response headers, and GitHub Pages
   sends none. Inside the worker, the network lock is the wall, and the test exercises it.
4. **The tests.** `web/test/privacy.test.mjs` runs the page in headless Chrome with every
   request recorded and the worker replaced by a hostile fake that tries to send the text out
   by fetch, sendBeacon, an image and a WebSocket while it "processes". It fails if any of
   those is not refused, if any request leaves the page while the text is being processed, or
   if any statistics payload has a key or value off the allowlist, four characters in a row of
   the pasted text, or a number other than the schema version. Switching the lock off makes
   it fail (checked).

## Files

| file | what it does |
| --- | --- |
| `docs/app/index.html` | the page: one column, mobile first, en/it/es |
| `docs/app/app.css` | styles; no monospace font in the interface (only inside `<code>`) |
| `docs/app/app.js` | the page's logic: language, tabs, results, statistics |
| `docs/app/i18n.js` | every sentence the page shows, in English, Italian and Spanish |
| `docs/app/facts.js` | the facts check, a port of `reflip/facts.py`; `facts-lexicon.js` is generated from `reflip/facts_lexicon.json` |
| `docs/app/models.js` | the models, pinned by commit, with the SHA-256 of each weights file |
| `docs/app/engine-worker.js` | a module Web Worker: downloads and checks models, scores, rewrites |
| `docs/app/detect.js` | the detectors' arithmetic, a port of `reflip/detect.py` `features_from_logits` |
| `docs/app/assess.js` | a port of `reflip/detect_assess.py`: calibration to an answer or a refusal |
| `docs/app/guard.js` | the network lock, imported by the page and by the worker |
| `docs/app/stats.js` | builds, queues and sends allowlisted events |
| `docs/app/stats-schema.js` | the allowlist, identical to `stats/src/schema.js` |
| `docs/app/calibration-browser.json` | the browser detector's calibration, fitted on the 4-bit ONNX files |
| `docs/app/vendor/` | transformers.js and onnxruntime-web, pinned and self-hosted |

## Worker messages

The page posts and the worker answers. The text crosses this boundary only inside
`detect` and `rewrite`, and never comes back except as the rewritten text.

| page to worker | worker to page |
| --- | --- |
| `{type: "capabilities"}` | `{type: "capabilities", webgpu, f16, device, cached}` |
| `{type: "prepare", repos}` | `{type: "progress", phase: "download" or "load", done, total}` repeatedly, then `{type: "ready"}` or `{type: "error", message}` |
| `{type: "detect", text}` | `{type: "detected", features}`; the page turns them into an answer with `assess.js` |
| `{type: "rewrite", text, lang, rewriter}` | `{type: "progress", phase: "rewrite", done, total}`, then `{type: "rewritten", text}` |
| `{type: "cancel"}` | `{type: "cancelled"}` in place of the answer |
| `{type: "forget"}` | `{type: "forgotten"}` after the model cache is deleted |

`prepare` is the only message during which the worker may use the network: it downloads each
weights file, checks its SHA-256 against `models.js`, and puts it in the Cache Storage under
the URL transformers.js looks for. `detect` and `rewrite` run under the lock from the first
line to the last, with `env.allowRemoteModels` off.

## Models offered

| id | role | files | size |
| --- | --- | --- | --- |
| `qwen2.5-0.5b` | detector pair: observer `onnx-community/Qwen2.5-0.5B`, performer `onnx-community/Qwen2.5-0.5B-Instruct`, both `onnx/model_q4f16.onnx` | 2 x 483 MB | 966 MB |
| `qwen2.5-0.5b` | also the smallest rewriter (the performer above, no extra download) | | 0 |
| `qwen2.5-1.5b-instruct` | rewriter, `onnx-community/Qwen2.5-1.5B-Instruct` `q4f16` | | 1.22 GB |
| `qwen3-1.7b` | rewriter, `onnx-community/Qwen3-1.7B-ONNX` `q4f16`, thinking off | | 1.43 GB |

The detector is fixed: its calibration was measured on these exact files, and swapping it
would make every number on the page untrue. Rewriting has not been through the benchmark in
the browser; every rewrite is followed by the facts check.

## Statistics events

`{v: 1, e, f, m}`, every field from the allowlist:

- `page` when a page loads (`f`: `home`, `app` or `privacy`);
- `model_download` when a model finishes downloading (`m`: which);
- `facts`, `detect` and `rewrite` when a tool is used (`m`: which model, `-` for facts).

Nothing else. A browser that sends Global Privacy Control or Do Not Track sends nothing.
