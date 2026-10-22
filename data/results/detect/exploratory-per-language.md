# Exploratory, decided after seeing the results: one threshold per language and length

Not used by the tool. The protocol fixed one threshold per length for the three languages together;
this asks what a threshold per language would have done, on the same split. Thresholds rest on 100
calibration humans per cell instead of 300, so they are noisier.

## binoculars on qwen2.5-1.5b

| cell | machine caught | humans flagged | upper bound | rule |
|---|---|---|---|---|
| en short | 17% of 24 | 7 of 300 | 4.3% | still refused: AUROC lower bound 0.76, under 0.85 |
| en medium | 50% of 24 | 8 of 300 | 4.8% | still refused: the threshold flagged 8 of 300 human texts, so the false-positive rate could be as high as 4.8%, over 2% |
| en long | 67% of 24 | 5 of 300 | 3.5% | still refused: the threshold flagged 5 of 300 human texts, so the false-positive rate could be as high as 3.5%, over 2% |
| it short | 8% of 24 | 1 of 300 | 1.6% | still refused: AUROC lower bound 0.73, under 0.85 |
| it medium | 64% of 28 | 10 of 300 | 5.6% | still refused: the threshold flagged 10 of 300 human texts, so the false-positive rate could be as high as 5.6%, over 2% |
| it long | 85% of 20 | 2 of 220 | 2.8% | still refused: the threshold flagged 2 of 220 human texts, so the false-positive rate could be as high as 2.8%, over 2% |
| es short | 50% of 24 | 8 of 300 | 4.8% | still refused: AUROC lower bound 0.80, under 0.85 |
| es medium | 68% of 25 | 5 of 300 | 3.5% | still refused: the threshold flagged 5 of 300 human texts, so the false-positive rate could be as high as 3.5%, over 2% |
| es long | 92% of 24 | 2 of 300 | 2.1% | still refused: the threshold flagged 2 of 300 human texts, so the false-positive rate could be as high as 2.1%, over 2% |

0 of 9 cells would pass the rule.

## binoculars on qwen2.5-0.5b-q4f16

| cell | machine caught | humans flagged | upper bound | rule |
|---|---|---|---|---|
| en short | 17% of 24 | 4 of 300 | 3.0% | still refused: AUROC lower bound 0.63, under 0.85 |
| en medium | 38% of 24 | 8 of 300 | 4.8% | still refused: AUROC lower bound 0.80, under 0.85 |
| en long | 38% of 24 | 3 of 300 | 2.6% | still refused: the threshold catches 38% of machine texts, under half |
| it short | 25% of 24 | 12 of 300 | 6.4% | still refused: AUROC lower bound 0.76, under 0.85 |
| it medium | 29% of 28 | 0 of 300 | 1.0% | still refused: the threshold catches 29% of machine texts, under half |
| it long | 80% of 20 | 3 of 220 | 3.5% | still refused: the threshold flagged 3 of 220 human texts, so the false-positive rate could be as high as 3.5%, over 2% |
| es short | 33% of 24 | 6 of 300 | 3.9% | still refused: AUROC lower bound 0.77, under 0.85 |
| es medium | 52% of 25 | 8 of 300 | 4.8% | still refused: the threshold flagged 8 of 300 human texts, so the false-positive rate could be as high as 4.8%, over 2% |
| es long | 79% of 24 | 3 of 300 | 2.6% | still refused: the threshold flagged 3 of 300 human texts, so the false-positive rate could be as high as 2.6%, over 2% |

0 of 9 cells would pass the rule.

