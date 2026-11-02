# OCR campaign 2 status

Campaign ID: `ocr-campaign2-native-regions-v1`.

This is a separate study. Campaign 1 remains stopped. Its artifacts were not rewritten.

| Item | State |
| --- | --- |
| Measured head | `7ea3a70ea54b9322b86181a9231e6440e44e74b7` |
| Controller | Stopped after screening |
| Stop reason | `no_safety_qualified_native` |
| Compute charged | 1,225.7 seconds |
| Candidate slots used | 3 of 8 (`N1`, `N3`, `N4`) |
| Model downloads | None |
| Holdout | Sealed. Not read |
| Internal validation | Not opened |
| Product profile | Disabled. `OCR_C2_ENABLED` is off |
| Outcome | Negative screen. Best paired normalized AMR reduction was 6.5% on `N4`, and every native arm added critical false positives |

The closeout is `docs/validation/OCR_C2_CAMPAIGN2_CLOSEOUT.md`. Private outputs stay under the original checkout at `artifacts/handwriting-private/ocr-campaign2-native-regions-v1/`.
