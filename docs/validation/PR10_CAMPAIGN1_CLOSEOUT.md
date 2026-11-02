# PR #10 campaign 1 closeout

Campaign reporting date: 2026-11-01, America/Chicago (CST, UTC-06:00).
Implementation checkpoint: `29fd7548da4610aee69925467368b0d68b270a5d`.

## Final disposition

**Campaign 1 is stopped at its recorded 30-experiment budget. No candidate qualifies for the untouched holdout. No genuine handwriting-recognition improvement has been established.**

The historical controller-selected configuration was `jpeg_ctx8192__spaces`. The user's final Cursor report states that paired AMR recognition did not improve and the last step changed whitespace only. Increasing context recovered previously failed inference in earlier development measurements; that is a reliability finding, not proof of lower transcription error on the same successfully processed inputs.

The engineering outcome and research outcome are separate:

- Engineering: correctness/provenance hardening, offline contract tests, and repeated native Codex review reached the implementation checkpoint documented below.
- Research: no qualifying accuracy winner; no final-holdout estimate, confidence interval, or clinical-validation claim.
- Operations: the completed campaign stays stopped. A second campaign requires a separately agreed design and budget. Documentation closeout does not authorize new inference, new downloads, cloud OCR, merging, or deployment.
- Repository: PR #10 remains draft, open, and stacked on PR #9. Neither PR is merged by this closeout.

This is a bounded negative/inconclusive optimization outcome, not evidence that GLM-OCR or another approach cannot improve handwriting recognition.

## Evidence and verification boundaries

| Statement | Evidence available for this record | Limitation |
| --- | --- | --- |
| Native Codex found no new major issues on `29fd7548da` | GitHub review receipt linked below, independently read | An automated review is not proof of absence of defects or handwriting accuracy. |
| Offline contract tests passed | GitHub job log: 44 passed in 0.80 seconds | Synthetic/offline software tests, not model accuracy measurements. The job checked out GitHub's PR merge ref `5b7e2c707f8fbd166d8bf2203541f2b0f6e289bc`, combining head `29fd7548da4610aee69925467368b0d68b270a5d` with base `b972d5b229986f52f5ec442688b8812c65a1769a`. |
| Existing local-vision and hosted synthetic workflows passed | GitHub Actions runs linked below | These are software/synthetic gates, not genuine-handwriting validation. |
| Campaign reached 30 recorded experiments and halted at 21:09:31 CST on November 1 | User-supplied Cursor execution report and prior local-status report | Closeout did not independently inspect the Mac processes or private ledger. The reported counter does not prove 30 distinct, valid scientific comparisons under the later corrected contract. |
| Historical winner is whitespace-only relative to its recognition parent and not eligible for holdout | User-supplied final Cursor report | No private raw predictions or full final comparison table were transferred or independently replayed during this documentation update. |
| Campaign files were not rewritten and holdouts remain untouched | User-supplied final Cursor report; this change touches documentation only | This is not an independent audit of all private filesystem access or previous local changes. |

Do not convert reported local observations into independently reproduced measurements. A complete public per-candidate ranking, final 256-crop Rx result table, and final compute/resource totals are not available in the committed evidence examined for this closeout; none are invented here.

## Preserved historical development checkpoints

The following values were already committed in the progress journal. They are snapshots from before campaign completion, not final campaign-wide results or new-code certification.

| Dataset/stage | Unchanged adapter | Context 8192 | Valid interpretation |
| --- | --- | --- | --- |
| AMR 8-document screen | 2/8 successful; scored-case CER 0.649 | 8/8 successful; scored-case CER 0.465 | Coverage recovery. On the two common successes, CER stayed 0.649. |
| AMR 20-document development confirmation snapshot | 3/20 successful; scored-case CER 0.665 | 19/20 successful; scored-case CER 0.487 | Coverage rose from 15% to 95%. On the three common successes, CER stayed 0.665. |
| Rx 64-crop screen | 64/64; CER 0.372 | 64/64; CER 0.372 | The recorded predictions matched; no recognition improvement. |

AMR documents, not pages, are the partition/scoring units; the historical journal called these selections pages. Multi-page documents must remain intact. The different scored-case CER denominators above must never be presented as paired accuracy gains. The journal's critical-token false-positive totals are its historical metric, not a complete medication-association safety assessment. The reported 19 context-8192 false positives in the confirmation snapshot are 19 overall, not 19 newly introduced on shared cases.

The snapshots retain their original measurement provenance. Fixes committed after inference do not retroactively certify earlier checkpoints. No current source, scorer, model, or identity hashes may be fabricated for legacy predictions.

## Partitions and holdout disposition

The preregistered `pr10_partition_manifest.json` and `PR10_ACCURACY_PLAN.md` are unchanged.

- AMR: 24 historical documents including excluded `AMR_041`, 20 development documents, and 18 untouched final-holdout documents. Development and holdout are writer-disjoint from each other, but both overlap historical-pilot writer groups.
- RxHandBD: 3,571 training-development crops, 892 training internal-validation crops, 100 previously observed official-test crops, and 1,015 untouched official-test crops. No writer-disjoint guarantee is established.
- Final holdout: not evaluated for campaign 1 because no eligible accuracy candidate was established. Do not mark this gate as passed or pending automatic execution.
- Internal validation: no completed 892-crop result is established by the evidence inspected here. Do not infer that a subset confirmation is equivalent to internal validation.

Publisher references are not independently adjudicated clinical gold. No human privacy reviewer or independent transcriber is invented. Raw source images, publisher references, predictions, private logs, and private receipts stay local and gitignored.

## Implementation and review record

Implementation sequence reported by Cursor and represented on PR #10:

| Commit | Change |
| --- | --- |
| `6e2559f` | Initial coverage/provenance/empty-output correctness work, subsequently strengthened by review findings. |
| `f66c959` | Run implementation identity and paired Rx-success comparisons. |
| `1732b0a` | Reference hashes and occurrence-level dose recall. |
| `ed74115` | Paired false-positive analysis and frozen AMR page hashes. |
| `e2089ee` | Line wrapping classified as formatting rather than recognition. |
| `3932668` | Blank-page and lost Rx-dose misses. |
| `9e0f603` | Replay saved predictions before accepting cached scores. |
| `29fd754` | Consistent gold normalization and compute-budget stopping. |

The contract test command in the verified job was:

```bash
PYTHONPATH=backend python -m pytest -q \
  backend/tests/test_pr10_partition.py \
  backend/tests/test_pr10_campaign_rules.py
```

Evidence links:

- [Native Codex receipt for `29fd7548da`](https://github.com/KanujVerma/clinical-notes-nlp-assistant/pull/10#issuecomment-6569297213)
- [Offline contract job, 44 tests passed](https://github.com/KanujVerma/clinical-notes-nlp-assistant/actions/runs/41390193423/job/125099663814)
- [Local-vision contract workflow](https://github.com/KanujVerma/clinical-notes-nlp-assistant/actions/runs/41390193295)
- [Hosted synthetic release gate](https://github.com/KanujVerma/clinical-notes-nlp-assistant/actions/runs/41390193383)

These receipts belong to the implementation checkpoint stated above, not automatically to a later documentation commit. Vercel comments/statuses are deployment receipts, not independent code review. Earlier review-thread UI state is not a substitute for checking the referenced fix and exact reviewed head; this closeout does not bulk-resolve historical threads.

## Rules for continuation

1. Preserve the old campaign, source bytes, prediction artifacts, seals, counters, and original plan. Never restart it by resetting its budget or rewriting its identity.
2. Reconcile this remote documentation closeout with any uncommitted local journal rather than force-resetting the local checkout. Preserve local historical records without publishing sensitive text.
3. A subsequent study must have a new campaign ID, explicit architecture, inference/scoring fingerprints, prospective comparisons, and its own approved compute/download budget. It may reuse development data, but cannot call that data newly untouched.
4. Keep the final holdouts sealed until an eligible candidate is frozen under the new study's predeclared rules. Existing evidence is not enough to promote `jpeg_ctx8192__spaces`.
5. Do not treat this closeout as authorization for real-patient use, cloud transmission, fine-tuning, new model downloads, or a merge.

The research record is finalized as **no qualifying recognition gain from campaign 1**, with the above evidence limitations retained explicitly.
