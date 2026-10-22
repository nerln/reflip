# reflip bench

corpus `data/corpus.jsonl`: 24 watermarked, 23 plain; tokenizer `per record`; ngram_len 5; threshold z<4; LLM `qwen3:4b-instruct-2507-q4_K_M` (T=0.7, seed=0, stride 3, span 1).

z: SynthID mean-g detector, standard deviations above chance (score from stored ids before, from the re-tokenised text after). intact: share of positions whose g-value the detector recomputes unchanged (0 = fully re-randomised). cosine: multilingual-e5-small. edit: share of words not kept verbatim.

| transform | n | err | z before | z after | median | max | <4 | <2 | z_w after | intact | cosine | edit | LLM tok/1k w | s/sample |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| rules | 24 | 0 | 17.63 | 15.77 | 16.18 | 24.78 | 0% | 0% | 14.41 | 0.899 | 0.999 | 2.2% | 0 | 0.0 |
| infill | 24 | 0 | 17.63 | 1.25 | 0.99 | 7.75 | 92% | 83% | 1.24 | 0.074 | 0.967 | 39.4% | 12534 | 31.1 |
| hybrid | 24 | 0 | 17.63 | 1.47 | 1.22 | 8.99 | 88% | 71% | 1.45 | 0.080 | 0.968 | 41.8% | 12430 | 30.0 |
| paraphrase | 24 | 0 | 17.63 | 0.52 | 0.49 | 5.59 | 92% | 88% | 0.42 | 0.053 | 0.960 | 66.6% | 14478 | 27.5 |
| infill@2 | 24 | 0 | 17.63 | 0.81 | 0.43 | 6.10 | 92% | 83% | 0.89 | 0.065 | 0.959 | 61.6% | 17343 | 43.7 |
| infill@4 | 24 | 0 | 17.63 | 1.32 | 0.76 | 13.45 | 92% | 83% | 1.31 | 0.107 | 0.974 | 28.1% | 9140 | 22.1 |
| control(plain) | 23 | 0 | -0.02 | -0.07 | 0.12 | 1.23 | 100% | 100% | -0.19 | 0.994 | 1.000 | 0.0% | 0 | 0.0 |

No sample errored.
