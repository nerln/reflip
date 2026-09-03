# reflip bench

corpus `data/corpus.jsonl`: 2 watermarked, 2 plain; tokenizer `per record`; ngram_len 5; threshold z<4; LLM `qwen3:4b-instruct-2507-q4_K_M` (T=0.7, seed=0, stride 3, span 1).

z: SynthID mean-g detector, standard deviations above chance (score from stored ids before, from the re-tokenised text after). intact: share of positions whose g-value the detector recomputes unchanged (0 = fully re-randomised). cosine: multilingual-e5-small. edit: share of words not kept verbatim.

| transform | n | err | z before | z after | median | max | <4 | <2 | z_w after | intact | cosine | edit | LLM tok/1k w | s/sample |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| none | 2 | 0 | 13.29 | 13.29 | 13.29 | 18.01 | 0% | 0% | 12.04 | 1.000 | 1.000 | 0.0% | 0 | 0.0 |
| rules | 2 | 0 | 13.29 | 12.18 | 12.18 | 16.31 | 0% | 0% | 11.10 | 0.901 | 0.999 | 2.2% | 0 | 0.0 |
| control(plain) | 2 | 0 | -0.91 | -0.91 | -0.91 | -0.19 | 100% | 100% | -1.34 | 1.000 | 1.000 | 0.0% | 0 | 0.0 |

No sample errored.
