# PR #10 autoresearch program

Local GLM-OCR only (`glm-ocr:q8_0`). One model worker. Gold is used to score a finished prediction, never to choose one. Do not read the 18 AMR holdout documents or the 1,015 untouched Rx test labels while selecting candidates.

## Screening set

Frozen from `pr10_partition_manifest.json` before any candidate:

- 8 AMR development documents, the lowest id in each development writer group.
- 64 Rx development crops, the first 64 hash-ranked development names.

## Keep rule

Replace the incumbent only when AMR development CER falls, critical-token recall does not fall, numeric/unit false positives do not rise, coverage does not fall, and Rx word CER does not materially worsen.

## Budget

30 real candidate experiments, stopping at 40 configurations or 6 hours of local model compute. A baseline is not a candidate. Stop earlier after 20 valid experiments if every major family has been tried and ten consecutive experiments fail to beat the incumbent.

## Reporting

Every finished run appends one aggregate row to `docs/validation/pr10_run_trend.tsv` and prints a `PR10_TREND` line. The hourly check only reports. It must not start or resume inference. `backend/evaluation/pr10_campaign.py` is the detached keep/discard loop. It resumes from case files, stops at 30 candidate experiments, 40 configurations, or 6 hours of measured inference, and restarts itself after a crash.

## Current error finding

The installed adapter leaves Ollama's context at its default. Full-page development images consume about 4,000 prompt tokens, so generation is cut off after a few dozen tokens and the adapter records `INFERENCE_ERROR`. Image-format changes do not fix that. Context length is the first coverage hypothesis.
