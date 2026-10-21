# Vendored files

Served from the site itself so the page never loads code from a CDN. Each file is the
published npm file, unchanged.

| file | package | SHA-256 |
| --- | --- | --- |
| `transformers.min.js` | `@huggingface/transformers` 4.3.1 (Apache-2.0, `LICENSE-transformers.js`), `dist/transformers.min.js`, which bundles onnxruntime-web | `8d6716d9086f57c30a4bf367dba61b887593573c770c454465e8019b2703e743` |
| `ort-wasm-simd-threaded.asyncify.mjs` | `onnxruntime-web` 1.31.0-dev.20260914-8d85527a0 (MIT), `dist/` | `0966b6105cd936744498aa60df7a22cbd47af3374dbc64a9ab561c08a71e3611` |
| `ort-wasm-simd-threaded.asyncify.wasm` | the same | `49871f5a4409519797e127440868a6d1923339d9185907f301a5b2a1d90af082` |

onnxruntime-web 1.31.0-dev.20260914 is the version transformers.js 4.3.1 pins. Its package
ships no license file; the project is MIT licensed, Copyright (c) Microsoft Corporation.
