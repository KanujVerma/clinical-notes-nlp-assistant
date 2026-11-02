# OCR campaign 3 results

Terminal outcome: `screen_negative`.

The measurement ran on reviewed head `09ad20377433dbff7901f29d58de02f1288008a3` after offline CI passed and native Codex review reported no findings. Confirmation did not start. Holdouts stayed sealed. No screen process is still running.

## Baseline

Saved campaign-2 `B8192` cases were not reused. `accept_saved_control` rejected all 8 AMR and 64 Rx screen cases as `baseline_code_drift`. The stored identity differs in `control_sha256`, `inference_sha256`, and `experiment_fingerprint`. The model digest matches the installed `glm-ocr:q8_0` digest `6e5935a916fc8d6878a67c60c2b99648f54e10b4a4af4cbbfb2c308953000e5f`. The saved page files also have no `source_sha256` and no region `crop_sha256`, so prepared-byte identity was not proved from those files.

A fresh `B8192` control was run on the same `infer_image` JPEGs as Vision and charged to this campaign. Its predictions were replayed before scoring. SHA-256 of those fresh predictions matches the historical prediction text for 8/8 AMR documents and 64/64 Rx crops. The historical files were still not the comparator.

## Screen

Eight development AMR documents and 64 development Rx crops. One page each. Vision is `V1_apple_vision_accurate_raw`, revision 3, language correction off.

| Set | Scored | Strict CER | Strict WER | Normalized CER | Normalized WER | Critical hits | False positives |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| AMR Vision | 8/8 | 0.612778 | 0.851336 | 0.526095 | 0.858304 | 16/33 | 1 |
| AMR B8192 | 8/8 | 0.464995 | 0.534262 | 0.355109 | 0.563298 | 29/33 | 13 |
| Rx Vision | 40/64 | 0.457364 | 0.886364 | 0.457364 | 0.954545 | 0/0 | 0 |
| Rx B8192 | 64/64 | 0.313953 | 0.750000 | 0.313953 | 0.863636 | 0/0 | 0 |

Rx rates are paired on the 40 crops both arms scored. Twenty-four Vision crops returned an empty transcription and are coverage misses, not zero-CER successes.

The 10% AMR gate required normalized CER at or below 0.319599. Vision's paired normalized CER is 0.526095, a relative change of -48.15% against the fresh baseline. Strict CER, strict WER, and normalized WER worsened on both datasets. AMR critical hits fell from 29 to 16. AMR critical false positives fell from 13 to 1, which does not offset the missed hits.

## Latency and compute

Vision screen pages were separate helper processes. The framework was already warm from the synthetic smoke, so these times are not a cold model load. Vision page p95 was 0.473 seconds and the slowest page was 0.644 seconds. The sum was 16.214 seconds. The product target is 60 seconds. The screen p95 is under that target and was not used to ignore the accuracy failure.

Fresh GLM page p95 was 21.584 seconds, the slowest page was 25.838 seconds, and the sum was 250.921 seconds. Campaign-2 historical `B8192` page times, from that earlier ledger and not this session, sum to 265.358 seconds with p95 22.923 seconds.

Charged campaign-3 model time is 314.385 seconds of 7,200. Remaining: 6,885.615 seconds. That includes the earlier 47.251 second synthetic smoke, the fresh control, and the Vision screen.
