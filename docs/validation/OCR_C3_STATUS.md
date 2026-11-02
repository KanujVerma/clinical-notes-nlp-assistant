# OCR campaign 3 status

| Item | State |
| --- | --- |
| Campaign | `ocr-c3-apple-vision-v1` |
| Base | PR #11 `0b6b8f66f5ce3d1fb3c34879ab1fd15672ae4993` |
| Candidate | `V1_apple_vision_accurate_raw`, Vision revision 3 |
| Runtime | macOS 27.0.1 build `26A434`, arm64 |
| Weight digest | unavailable from Vision |
| Inference on development handwriting | not started |
| Synthetic Vision smoke | passed, revision 3, language correction off, one observation, helper 47.1 seconds |
| Compute charged | 47.3 seconds of 7,200 |
| Holdouts | sealed |
| `OCR_C3_ENABLED` | off |

The helper was compiled with `swiftc -O -o <private bin> backend/evaluation/ocr_c3_swift/main.swift`. The smoke used a rendered non-clinical word. Its transcript stays in the private artifact directory and is not published.

Real AMR and Rx recognition is blocked until this implementation head has passed offline CI and native Codex review. No development prediction has been read for this study.
