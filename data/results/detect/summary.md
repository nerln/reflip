# Detection benchmark

Chosen by the pre-registered rule: **binoculars** on **qwen2.5-1.5b**, mean test AUROC over the six medium and long cells 0.965. Every number below comes from the test half; the protocol is docs/detect/PREREG.md.


## binoculars on qwen2.5-1.5b, cell by cell

| cell | AUROC (95%) | machine caught | humans flagged | upper bound | verdict |
|---|---|---|---|---|---|
| en short | 0.83 (0.76-0.89) | 12% of 24 | 2 of 300 | 2.1% | refused: AUROC lower bound 0.76, under 0.85 |
| en medium | 0.92 (0.86-0.97) | 46% of 24 | 7 of 300 | 4.3% | refused: the threshold catches 46% of machine texts, under half |
| en long | 0.97 (0.95-0.99) | 50% of 24 | 0 of 300 | 1.0% | given |
| it short | 0.82 (0.73-0.91) | 8% of 24 | 4 of 300 | 3.0% | refused: AUROC lower bound 0.73, under 0.85 |
| it medium | 0.94 (0.91-0.97) | 64% of 28 | 10 of 300 | 5.6% | refused: the threshold flagged 10 of 300 human texts, so the false-positive rate could be as high as 5.6%, over 2% |
| it long | 0.99 (0.98-1.00) | 85% of 20 | 2 of 220 | 2.8% | refused: the threshold flagged 2 of 220 human texts, so the false-positive rate could be as high as 2.8%, over 2% |
| es short | 0.88 (0.80-0.94) | 46% of 24 | 6 of 300 | 3.9% | refused: AUROC lower bound 0.80, under 0.85 |
| es medium | 0.98 (0.97-0.99) | 84% of 25 | 11 of 300 | 6.0% | refused: the threshold flagged 11 of 300 human texts, so the false-positive rate could be as high as 6.0%, over 2% |
| es long | 0.98 (0.95-1.00) | 92% of 24 | 2 of 300 | 2.1% | refused: the threshold flagged 2 of 300 human texts, so the false-positive rate could be as high as 2.1%, over 2% |


## binoculars on qwen2.5-1.5b: rewritten text, second-language writers, generators, genres

| reflip-rewritten machine text | AUROC against humans | caught at the threshold |
|---|---|---|
| medium (24 texts) | 0.56 | 25% |
| long (21 texts) | 0.71 | 19% |

| second-language writers | texts | flagged as machine | upper bound |
|---|---|---|---|
| human_l2/en/long | 15 | 0 (0.0%) | 18.1% |
| human_l2/en/medium | 135 | 0 (0.0%) | 2.2% |
| human_l2/es/long | 13 | 0 (0.0%) | 20.6% |
| human_l2/es/medium | 130 | 3 (2.3%) | 5.9% |
| human_l2/es/short | 7 | 0 (0.0%) | 34.8% |
| human_l2_corrected/en/medium | 150 | 0 (0.0%) | 2.0% |
| human_l2_corrected/es/long | 11 | 0 (0.0%) | 23.8% |
| human_l2_corrected/es/medium | 132 | 7 (5.3%) | 9.7% |
| human_l2_corrected/es/short | 7 | 0 (0.0%) | 34.8% |

| generator | bucket | AUROC |
|---|---|---|
| qwen3 | short | 0.85 (0.77-0.92) |
| gemma3 | short | 0.90 (0.85-0.94) |
| claude | short | 0.75 (0.65-0.84) |
| qwen3 | medium | 0.99 (0.97-1.00) |
| gemma3 | medium | 0.93 (0.86-0.98) |
| claude | medium | 0.92 (0.89-0.95) |
| qwen3 | long | 0.99 (0.98-1.00) |
| gemma3 | long | 0.99 (0.97-1.00) |
| claude | long | 0.95 (0.91-0.99) |

| human genre | bucket | AUROC |
|---|---|---|
| wiki | short | 0.85 (0.79-0.90) |
| news | short | 0.83 (0.76-0.89) |
| wiki | medium | 0.93 (0.88-0.97) |
| news | medium | 0.97 (0.94-0.98) |
| wiki | long | 0.98 (0.96-0.99) |
| news | long | 0.99 (0.97-1.00) |


## In the browser: binoculars on qwen2.5-0.5b-q4f16 (4-bit), cell by cell

| cell | AUROC (95%) | machine caught | humans flagged | upper bound | verdict |
|---|---|---|---|---|---|
| en short | 0.73 (0.63-0.84) | 17% of 24 | 4 of 300 | 3.0% | refused: AUROC lower bound 0.63, under 0.85 |
| en medium | 0.88 (0.81-0.94) | 17% of 24 | 0 of 300 | 1.0% | refused: AUROC lower bound 0.81, under 0.85 |
| en long | 0.94 (0.90-0.98) | 38% of 24 | 3 of 300 | 2.6% | refused: the threshold catches 38% of machine texts, under half |
| it short | 0.85 (0.77-0.92) | 8% of 24 | 7 of 300 | 4.3% | refused: AUROC lower bound 0.77, under 0.85 |
| it medium | 0.93 (0.87-0.97) | 50% of 28 | 3 of 300 | 2.6% | refused: the threshold flagged 3 of 300 human texts, so the false-positive rate could be as high as 2.6%, over 2% |
| it long | 0.99 (0.99-1.00) | 80% of 20 | 3 of 220 | 3.5% | refused: the threshold flagged 3 of 220 human texts, so the false-positive rate could be as high as 3.5%, over 2% |
| es short | 0.85 (0.77-0.92) | 33% of 24 | 6 of 300 | 3.9% | refused: AUROC lower bound 0.77, under 0.85 |
| es medium | 0.96 (0.93-0.98) | 52% of 25 | 8 of 300 | 4.8% | refused: the threshold flagged 8 of 300 human texts, so the false-positive rate could be as high as 4.8%, over 2% |
| es long | 0.98 (0.95-1.00) | 79% of 24 | 3 of 300 | 2.6% | refused: the threshold flagged 3 of 300 human texts, so the false-positive rate could be as high as 2.6%, over 2% |


| reflip-rewritten machine text | AUROC against humans | caught at the threshold |
|---|---|---|
| medium (24 texts) | 0.54 | 17% |
| long (21 texts) | 0.60 | 10% |

| second-language writers | texts | flagged as machine | upper bound |
|---|---|---|---|
| human_l2/en/long | 15 | 0 (0.0%) | 18.1% |
| human_l2/en/medium | 135 | 0 (0.0%) | 2.2% |
| human_l2/es/long | 13 | 0 (0.0%) | 20.6% |
| human_l2/es/medium | 130 | 0 (0.0%) | 2.3% |
| human_l2/es/short | 7 | 0 (0.0%) | 34.8% |
| human_l2_corrected/en/medium | 150 | 0 (0.0%) | 2.0% |
| human_l2_corrected/es/long | 11 | 0 (0.0%) | 23.8% |
| human_l2_corrected/es/medium | 132 | 2 (1.5%) | 4.7% |
| human_l2_corrected/es/short | 7 | 0 (0.0%) | 34.8% |

| generator | bucket | AUROC |
|---|---|---|
| qwen3 | short | 0.83 (0.73-0.91) |
| gemma3 | short | 0.84 (0.74-0.93) |
| claude | short | 0.71 (0.63-0.79) |
| qwen3 | medium | 0.98 (0.96-0.99) |
| gemma3 | medium | 0.85 (0.76-0.93) |
| claude | medium | 0.88 (0.82-0.92) |
| qwen3 | long | 1.00 (0.99-1.00) |
| gemma3 | long | 0.98 (0.96-0.99) |
| claude | long | 0.88 (0.80-0.95) |

| human genre | bucket | AUROC |
|---|---|---|
| wiki | short | 0.82 (0.73-0.89) |
| news | short | 0.78 (0.70-0.86) |
| wiki | medium | 0.91 (0.85-0.95) |
| news | medium | 0.90 (0.85-0.95) |
| wiki | long | 0.96 (0.92-0.99) |
| news | long | 0.96 (0.93-0.98) |


## qwen2.5-0.5b: test AUROC of every detector, with 95% interval

| detector | en short | en medium | en long | it short | it medium | it long | es short | es medium | es long | mean medium+long |
|---|---|---|---|---|---|---|---|---|---|---|
| binoculars | 0.79 (0.71-0.87) | 0.85 (0.77-0.92) | 0.94 (0.88-0.98) | 0.84 (0.74-0.92) | 0.92 (0.85-0.98) | 1.00 (0.99-1.00) | 0.88 (0.80-0.94) | 0.97 (0.94-0.99) | 0.98 (0.94-1.00) | 0.942 |
| fast_detectgpt | 0.73 (0.62-0.82) | 0.79 (0.69-0.87) | 0.92 (0.85-0.97) | 0.78 (0.68-0.87) | 0.89 (0.79-0.96) | 0.98 (0.95-1.00) | 0.81 (0.72-0.90) | 0.95 (0.91-0.98) | 0.96 (0.91-1.00) | 0.913 |
| fast_detectgpt_cross | 0.72 (0.60-0.82) | 0.81 (0.72-0.90) | 0.94 (0.90-0.98) | 0.77 (0.66-0.87) | 0.86 (0.76-0.95) | 0.98 (0.95-1.00) | 0.75 (0.63-0.85) | 0.92 (0.87-0.96) | 0.94 (0.87-0.99) | 0.909 |
| perplexity | 0.52 (0.43-0.61) | 0.63 (0.52-0.74) | 0.79 (0.71-0.87) | 0.63 (0.53-0.73) | 0.78 (0.69-0.86) | 0.89 (0.81-0.95) | 0.65 (0.55-0.76) | 0.78 (0.72-0.85) | 0.90 (0.84-0.95) | 0.795 |
| burstiness | 0.67 (0.57-0.77) | 0.69 (0.59-0.79) | 0.84 (0.77-0.91) | 0.50 (0.40-0.61) | 0.59 (0.49-0.70) | 0.76 (0.65-0.86) | 0.44 (0.34-0.55) | 0.71 (0.60-0.81) | 0.87 (0.77-0.94) | 0.742 |
| ppl_burstiness | 0.58 (0.48-0.67) | 0.70 (0.59-0.80) | 0.85 (0.78-0.92) | 0.62 (0.52-0.72) | 0.74 (0.65-0.83) | 0.92 (0.85-0.97) | 0.63 (0.52-0.74) | 0.79 (0.70-0.88) | 0.94 (0.89-0.97) | 0.824 |


## qwen2.5-1.5b: test AUROC of every detector, with 95% interval

| detector | en short | en medium | en long | it short | it medium | it long | es short | es medium | es long | mean medium+long |
|---|---|---|---|---|---|---|---|---|---|---|
| binoculars | 0.83 (0.76-0.89) | 0.92 (0.86-0.97) | 0.97 (0.95-0.99) | 0.82 (0.73-0.91) | 0.94 (0.91-0.97) | 0.99 (0.98-1.00) | 0.88 (0.80-0.94) | 0.98 (0.97-0.99) | 0.98 (0.95-1.00) | 0.965 |
| fast_detectgpt | 0.77 (0.69-0.85) | 0.86 (0.78-0.92) | 0.95 (0.91-0.98) | 0.77 (0.66-0.88) | 0.94 (0.89-0.98) | 0.97 (0.91-1.00) | 0.83 (0.73-0.91) | 0.97 (0.94-0.99) | 0.96 (0.91-0.99) | 0.939 |
| fast_detectgpt_cross | 0.74 (0.63-0.83) | 0.83 (0.74-0.91) | 0.97 (0.94-0.99) | 0.78 (0.67-0.87) | 0.91 (0.83-0.97) | 0.98 (0.96-1.00) | 0.77 (0.67-0.86) | 0.94 (0.90-0.97) | 0.96 (0.91-0.99) | 0.931 |
| perplexity | 0.51 (0.42-0.60) | 0.65 (0.54-0.76) | 0.81 (0.73-0.89) | 0.56 (0.45-0.67) | 0.81 (0.73-0.89) | 0.92 (0.86-0.96) | 0.63 (0.52-0.74) | 0.80 (0.73-0.86) | 0.93 (0.87-0.97) | 0.820 |
| burstiness | 0.68 (0.59-0.77) | 0.70 (0.59-0.81) | 0.83 (0.76-0.90) | 0.43 (0.33-0.54) | 0.57 (0.46-0.67) | 0.69 (0.56-0.81) | 0.45 (0.33-0.57) | 0.70 (0.58-0.81) | 0.84 (0.75-0.92) | 0.723 |
| ppl_burstiness | 0.57 (0.47-0.67) | 0.71 (0.60-0.81) | 0.86 (0.79-0.92) | 0.54 (0.43-0.64) | 0.77 (0.68-0.86) | 0.92 (0.87-0.97) | 0.61 (0.49-0.71) | 0.80 (0.72-0.88) | 0.95 (0.90-0.98) | 0.835 |


## qwen2.5-0.5b-q4f16: test AUROC of every detector, with 95% interval

| detector | en short | en medium | en long | it short | it medium | it long | es short | es medium | es long | mean medium+long |
|---|---|---|---|---|---|---|---|---|---|---|
| binoculars | 0.73 (0.63-0.84) | 0.88 (0.81-0.94) | 0.94 (0.90-0.98) | 0.85 (0.77-0.92) | 0.93 (0.87-0.97) | 0.99 (0.99-1.00) | 0.85 (0.77-0.92) | 0.96 (0.93-0.98) | 0.98 (0.95-1.00) | 0.947 |
| fast_detectgpt | 0.69 (0.57-0.80) | 0.79 (0.71-0.86) | 0.93 (0.86-0.97) | 0.78 (0.68-0.86) | 0.90 (0.82-0.96) | 0.99 (0.97-1.00) | 0.79 (0.69-0.88) | 0.94 (0.90-0.97) | 0.96 (0.90-1.00) | 0.918 |
| fast_detectgpt_cross | 0.57 (0.45-0.69) | 0.71 (0.60-0.81) | 0.84 (0.75-0.92) | 0.75 (0.65-0.84) | 0.89 (0.80-0.95) | 0.99 (0.97-1.00) | 0.72 (0.61-0.81) | 0.91 (0.85-0.95) | 0.93 (0.84-0.98) | 0.876 |
| perplexity | 0.48 (0.39-0.59) | 0.61 (0.51-0.72) | 0.78 (0.70-0.85) | 0.62 (0.51-0.72) | 0.79 (0.70-0.87) | 0.88 (0.80-0.95) | 0.65 (0.55-0.76) | 0.79 (0.72-0.85) | 0.89 (0.82-0.95) | 0.790 |
| burstiness | 0.65 (0.54-0.76) | 0.67 (0.56-0.78) | 0.84 (0.77-0.90) | 0.47 (0.37-0.57) | 0.57 (0.47-0.67) | 0.70 (0.58-0.82) | 0.42 (0.31-0.53) | 0.72 (0.61-0.82) | 0.84 (0.73-0.92) | 0.726 |
| ppl_burstiness | 0.53 (0.43-0.64) | 0.68 (0.57-0.79) | 0.86 (0.79-0.92) | 0.60 (0.50-0.69) | 0.72 (0.61-0.81) | 0.90 (0.81-0.96) | 0.62 (0.51-0.73) | 0.79 (0.70-0.88) | 0.90 (0.83-0.96) | 0.809 |
