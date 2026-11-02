# OCR campaign 2 status

Campaign ID: `ocr-campaign2-native-regions-v1`.

This is a separate study. Campaign 1 remains stopped. Its artifacts were not rewritten.

| Item | State |
| --- | --- |
| Native-screen head | `7ea3a70ea54b9322b86181a9231e6440e44e74b7`, preserved |
| Closeout checkpoint | `c1d9966b7cfd06fe0e626ea828a86e7c13d5c53a`, preserved |
| Amendment | `c2-segmentation-amendment-1`, segmenter `ocr_c2_segments_v3` |
| Amendment outcome | `geometry_still_blocked` after three rejected prototypes |
| Eligible AMR screen documents | 0 of 8 |
| Controller | Stopped. A failed geometry amendment does not open the recognizer |
| Compute charged | 1,225.7 seconds. No new model charge |
| Candidate slots used | 3 of 8 (`N1`, `N3`, `N4`). `G1` and `T1` did not run |
| Model downloads | None |
| Holdout | Sealed. Not read |
| Internal validation | Not opened |
| Product profile | Disabled. `OCR_C2_ENABLED` is off |

The native screen remains a negative result. The later geometry amendment did not establish certified lines, so it is not a recognition result and it does not reopen confirmation or holdout.

The closeout history is `docs/validation/OCR_C2_CAMPAIGN2_CLOSEOUT.md`. The amendment is `docs/validation/OCR_C2_SEGMENTATION_AMENDMENT.md`.
