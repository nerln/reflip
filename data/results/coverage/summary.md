# reflip bench

corpus `/Users/eugenionerelli/dev/reflip/data/corpus.jsonl`: 24 watermarked, 23 plain; tokenizer `per record`; ngram_len 5; threshold z<4; LLM `qwen3:4b-instruct-2507-q4_K_M` (T=0.7, seed=0, stride 3, span 1, token-aware).

z: SynthID mean-g detector, standard deviations above chance (score from stored ids before, from the re-tokenised text after). intact: share of positions whose g-value the detector recomputes unchanged (0 = fully re-randomised). cosine: multilingual-e5-small. edit: share of words not kept verbatim.

| transform | n | err | z before | z after | median | max | <4 | <2 | z_w after | intact | cosine | edit | LLM tok/1k w | s/sample |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| paraphrase | 24 | 0 | 17.63 | 0.28 | 0.25 | 2.37 | 100% | 96% | 0.17 | 0.026 | 0.955 | 74.1% | 5840 | 16.5 |
| control(plain) | 23 | 0 | -0.02 | -0.07 | 0.12 | 1.23 | 100% | 100% | -0.19 | 0.994 | 1.000 | 0.0% | 0 | 0.0 |

No sample errored.
