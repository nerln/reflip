// The models the page offers, pinned by commit, with the SHA-256 of every weights file.
//
// Two kinds of weights file, for two jobs:
// - q4f16 (4-bit weights, 16-bit arithmetic) for the detector, run on the processor. Its
//   calibration (calibration-browser.json) was measured on exactly these files with
//   onnxruntime, and the browser's CPU backend reproduces those scores to three decimals.
// - q4 (4-bit weights, 32-bit arithmetic) for rewriting, run on WebGPU. On Apple's GPUs the
//   16-bit files produced garbage ("Th Th Th") in Chrome 152 and in the app's own browser;
//   the 32-bit files wrote the same text as the processor did, fifty times faster.

export const HUB = "https://huggingface.co";
export const FILES = { q4f16: "onnx/model_q4f16.onnx", q4: "onnx/model_q4.onnx" };
// Gemma keeps its weights in a second file beside the graph; onnxruntime reads that file
// without copying it into WebAssembly memory, which is why a 1.7 GB Llama 3.2 1B in that
// form loaded where a 1.8 GB single-file Qwen2.5 1.5B stopped with std::bad_alloc. Llama
// was measured and left out: on the 24 benchmark texts it wrote up to eight times the
// length of the original and changed 112 facts per 1,000 words.
export const DATA = (dtype) => `${FILES[dtype]}_data`;
// What transformers.js reads besides the weights. Small, and pinned by the commit.
export const SMALL_FILES = ["config.json", "generation_config.json", "tokenizer.json", "tokenizer_config.json"];

export const REPOS = {
  "onnx-community/Qwen2.5-0.5B": {
    rev: "bae5ceaee026f0d0592858b2bd27645a06f19c42",
    weights: { q4f16: { size: 483003582, sha256: "30a39f89fab8f30d0f99aa1e28d3e3be6fca66a3fab915f77584ac52a8361d25" } },
  },
  "onnx-community/Qwen2.5-0.5B-Instruct": {
    rev: "22942cb7d7ba4cc81bb4673549ca4d4614469b5e",
    weights: {
      q4f16: { size: 483003582, sha256: "b11c1dd99efd57e6c6e5bc4443a019931a5fbd5dd500d48644d8225f5ce0b2cb" },
      q4: { size: 786156820, sha256: "09235a3b1c135cd04ef570e5053b5c079e028078a2cc5f76ba6a251e91bf3296" },
    },
  },
  "onnx-community/gemma-3-1b-it-ONNX": {
    rev: "a58439f40017d3b99c7d378ff525e54e0ba08ebf",
    license: "https://ai.google.dev/gemma/terms",
    weights: {
      q4: {
        size: 347363 + 859106816,
        sha256: "69686023e5892376e38fcbcdd0c77af432c55b3bcd03aee6d561bd1f04507da0",
        data: { size: 859106816, sha256: "c2370070be257a98d50e17d81be13e18304c39e7e6d9d1416f8f883681d2a17b" },
      },
    },
  },
};

// A piece of a model on the device: one repository's weights in one form.
export const part = (repo, dtype) => ({ repo, dtype });
export const partKey = ({ repo, dtype }) => `${repo}@${dtype}`;
export const partBytes = ({ repo, dtype }) => REPOS[repo].weights[dtype].size;

export const DETECTOR = {
  id: "qwen2.5-0.5b",
  observer: "onnx-community/Qwen2.5-0.5B",
  performer: "onnx-community/Qwen2.5-0.5B-Instruct",
  parts: [part("onnx-community/Qwen2.5-0.5B", "q4f16"), part("onnx-community/Qwen2.5-0.5B-Instruct", "q4f16")],
};

export const REWRITERS = [
  { id: "qwen2.5-0.5b", label: "Qwen2.5 0.5B Instruct", parts: [part("onnx-community/Qwen2.5-0.5B-Instruct", "q4")] },
  { id: "gemma-3-1b", label: "Gemma 3 1B", parts: [part("onnx-community/gemma-3-1b-it-ONNX", "q4")] },
];

export const fileURL = (repo, file) => `${HUB}/${repo}/resolve/${REPOS[repo].rev}/${file}`;
