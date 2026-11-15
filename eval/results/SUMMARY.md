# Evaluation runs

One row per saved run. Rates are shown as passed/scored. Full detail is in the JSON file named in the last column.

The `m3-kb` row is a draft run, kept for the record. Its questions had not been reviewed, the help articles had not been corrected, and the grading has changed since, so it is not comparable with the rows after it. Dates are UTC.

| Date | Tag | Config | Query | Rows | Reviewed | Source retrieved | Chunk relevance | Context sufficient | Grounded | Correct | Relevant | Reading level ok | Median latency (s) | Commit | File | Rules followed | Hand-off correct | Right tool | No PII leak |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 2026-11-14 | m3-kb | A | ann | 22 | 0/22 | 22/22 | 0.50 (n=22) | 22/22 | 22/22 | 16/22 | 22/22 | 22/22 | 2.3 | `04138f9` | 2026-11-14_m3-kb-A-ann.json |
| 2026-11-14 | m3-kb-v2 | A | ann | 22 | 22/22 | 21/21 | 0.53 (n=21) | 21/21 | 21/21 | 19/21 | 22/22 | 20/22 | 2.1 | `1a35afb` | 2026-11-14_m3-kb-v2-A-ann.json |
| 2026-11-14 | m3-kb-v2 | B | ann | 22 | 22/22 | 20/21 | 0.64 (n=21) | 21/21 | 21/21 | 18/21 | 22/22 | 19/22 | 2.1 | `1a35afb` | 2026-11-14_m3-kb-v2-B-ann.json |
| 2026-11-15 | m3-kb-v2 | B | hybrid | 22 | 22/22 | 21/21 | 0.65 (n=21) | 21/21 | 21/21 | 18/21 | 22/22 | 20/22 | 2.1 | `1a35afb` | 2026-11-15_m3-kb-v2-B-hybrid.json |
| 2026-11-15 | m4-full | A | ann | 40 | 40/40 | 22/22 | 0.52 (n=22) | 22/22 | 22/22 | 27/31 | 31/31 | 37/40 | 2.5 | `8624268` | 2026-11-15_m4-full-A-ann.json | 11/11 | 40/40 | 36/37 | 40/40 |
