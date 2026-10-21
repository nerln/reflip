// The models the page offers, pinned by commit, with the SHA-256 of every weights file.
//
// The detector is fixed: its calibration (calibration-browser.json) was measured on exactly
// these two files, and any other file would make every number on the page untrue. The
// rewriters are a choice; the facts check runs on whatever they write.

export const HUB = "https://huggingface.co";
export const WEIGHTS = "onnx/model_q4f16.onnx";
// What transformers.js reads besides the weights. Small, and pinned by the commit.
export const SMALL_FILES = ["config.json", "generation_config.json", "tokenizer.json", "tokenizer_config.json"];

export const REPOS = {
  "onnx-community/Qwen2.5-0.5B": {
    rev: "bae5ceaee026f0d0592858b2bd27645a06f19c42",
    size: 483003582,
    sha256: "30a39f89fab8f30d0f99aa1e28d3e3be6fca66a3fab915f77584ac52a8361d25",
  },
  "onnx-community/Qwen2.5-0.5B-Instruct": {
    rev: "22942cb7d7ba4cc81bb4673549ca4d4614469b5e",
    size: 483003582,
    sha256: "b11c1dd99efd57e6c6e5bc4443a019931a5fbd5dd500d48644d8225f5ce0b2cb",
  },
  "onnx-community/Qwen2.5-1.5B-Instruct": {
    rev: "d54957e3af1be04546436e874a60fe386041b244",
    size: 1221878940,
    sha256: "19dec9f63488016185ba997d5e4492b5ac5b4f7ef1abb45243a91de958838dcd",
  },
  "onnx-community/Qwen3-1.7B-ONNX": {
    rev: "3231b522c6e703b2f9b3cd8ea27426a1289a02f2",
    size: 1426069098,
    sha256: "fb85b44defdf43ace50c7a4937127e889b9f8a0483eb87a6c4151a815c5da3b5",
  },
};

export const DETECTOR = {
  id: "qwen2.5-0.5b",
  observer: "onnx-community/Qwen2.5-0.5B",
  performer: "onnx-community/Qwen2.5-0.5B-Instruct",
};

// `repos` is what has to be on the device for this rewriter; the first one writes.
export const REWRITERS = [
  { id: "qwen2.5-0.5b", repos: ["onnx-community/Qwen2.5-0.5B-Instruct"], label: "Qwen2.5 0.5B Instruct" },
  { id: "qwen2.5-1.5b-instruct", repos: ["onnx-community/Qwen2.5-1.5B-Instruct"], label: "Qwen2.5 1.5B Instruct" },
  { id: "qwen3-1.7b", repos: ["onnx-community/Qwen3-1.7B-ONNX"], label: "Qwen3 1.7B", thinking: false },
];

export const fileURL = (repo, file) => `${HUB}/${repo}/resolve/${REPOS[repo].rev}/${file}`;
export const repoBytes = (repo) => REPOS[repo].size;
