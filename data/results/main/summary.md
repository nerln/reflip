# reflip bench

corpus `/Users/eugenionerelli/dev/reflip/data/corpus.jsonl`: 24 watermarked, 23 plain; tokenizer `per record`; ngram_len 5; threshold z<4; LLM `qwen3:4b-instruct-2507-q4_K_M` (T=0.7, seed=0, stride 3, span 1).

z: SynthID mean-g detector, standard deviations above chance (score from stored ids before, from the re-tokenised text after). intact: share of positions whose g-value the detector recomputes unchanged (0 = fully re-randomised). cosine: multilingual-e5-small. edit: share of words not kept verbatim.

| transform | n | err | z before | z after | median | max | <4 | <2 | z_w after | intact | cosine | edit | LLM tok/1k w | s/sample |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| none | 24 | 0 | 17.63 | 17.51 | 18.24 | 25.33 | 0% | 0% | 16.01 | 0.994 | 1.000 | 0.0% | 0 | 0.0 |
| unicode | 24 | 0 | 17.63 | 17.51 | 18.24 | 25.33 | 0% | 0% | 16.01 | 0.994 | 1.000 | 0.0% | 0 | 0.0 |
| rules | 24 | 0 | 17.63 | 15.77 | 16.18 | 24.78 | 0% | 0% | 14.41 | 0.899 | 0.999 | 2.2% | 0 | 0.0 |
| infill | 24 | 0 | 17.63 | 1.53 | 0.99 | 8.25 | 88% | 75% | 1.41 | 0.097 | 0.967 | 40.4% | 13412 | 41.6 |
| hybrid | 24 | 0 | 17.63 | 1.92 | 0.53 | 10.89 | 83% | 71% | 1.73 | 0.105 | 0.968 | 38.7% | 13995 | 40.1 |
| paraphrase | 24 | 0 | 17.63 | 0.59 | 0.48 | 5.11 | 96% | 92% | 0.43 | 0.042 | 0.956 | 72.4% | 5074 | 14.8 |
| infill@2 | 24 | 0 | 17.63 | 1.23 | 0.83 | 10.13 | 92% | 83% | 1.21 | 0.085 | 0.959 | 58.3% | 17910 | 53.1 |
| infill@3 | 24 | 0 | 17.63 | 1.53 | 0.99 | 8.25 | 88% | 75% | 1.41 | 0.097 | 0.967 | 40.4% | 13412 | 41.6 |
| infill@4 | 24 | 0 | 17.63 | 1.54 | 1.07 | 12.61 | 92% | 79% | 1.43 | 0.105 | 0.972 | 28.0% | 9925 | 30.8 |
| control(plain) | 23 | 0 | -0.02 | -0.07 | 0.12 | 1.23 | 100% | 100% | -0.19 | 0.994 | 1.000 | 0.0% | 0 | 0.0 |

No sample errored.
