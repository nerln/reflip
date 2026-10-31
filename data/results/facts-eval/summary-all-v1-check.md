# Facts check against blind annotators (all, 120 pairs)

| kind | precision (95%) | recall (95%) | tp | fp | fn | annotator kappa |
|---|---|---|---|---|---|---|
| numbers | 0.25 (0.05-0.70) | 0.17 (0.03-0.56) | 1 | 3 | 5 | 0.59 |
| names | 0.15 (0.06-0.32) | 0.80 (0.38-0.96) | 4 | 23 | 1 | 1.00 |
| negation | 0.05 (0.01-0.22) | 1.00 (0.21-1.00) | 1 | 21 | 0 | 1.00 |
| quantifiers | 0.56 (0.42-0.69) | 0.59 (0.44-0.72) | 27 | 21 | 19 | 0.73 |
| any | 0.55 (0.43-0.66) | 0.69 (0.56-0.80) | 36 | 30 | 16 | nan |

Pairs whose meaning changed only outside the four kinds (both annotators agree): 45 of 120 (38%, 29% to 46%).
