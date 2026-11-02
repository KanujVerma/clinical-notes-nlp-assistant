# OCR campaign 2 status

Campaign ID: `ocr-campaign2-native-regions-v1`.

This is a separate study. Campaign 1 remains stopped. Its artifacts were not rewritten.

| Item | State |
| --- | --- |
| Native-screen head | `7ea3a70ea54b9322b86181a9231e6440e44e74b7`, preserved |
| Closeout checkpoint | `c1d9966b7cfd06fe0e626ea828a86e7c13d5c53a`, preserved |
| Controller | Stopped after optional-model eligibility |
| Earlier stop, preserved | `no_safety_qualified_native` |
| Current stop reason | `geometry_blocked` |
| Compute charged | 1,225.7 seconds |
| Candidate slots used | 3 of 8 (`N1`, `N3`, `N4`). `N6` was not run |
| Model downloads | None |
| Holdout | Sealed. Not read |
| Internal validation | Not opened |
| Product profile | Disabled. `OCR_C2_ENABLED` is off |
| Outcome | Negative native screen, then the optional phase blocked because N4 line geometry is not usable |

Native screening is complete and negative. The optional recognizer was not evaluated: its code was absent at the measured head, and the later geometry check failed before any download. The campaign did not exhaust an implemented N6 route. Confirmation and every later phase stay closed.

The closeout history is `docs/validation/OCR_C2_CAMPAIGN2_CLOSEOUT.md`. Geometry aggregates are `docs/validation/ocr_c2_screen_geometry.json`. Private outputs stay under the original checkout at `artifacts/handwriting-private/ocr-campaign2-native-regions-v1/`.
