# PR #10 progress journal

## Final status: campaign 1 stopped, no qualifying accuracy candidate

Reporting date: November 1, 2026, America/Chicago. See [campaign 1 closeout](PR10_CAMPAIGN1_CLOSEOUT.md) for evidence, limitations, code-review links, and continuation rules.

The user's final Cursor report records 30 completed experiments and normal budget termination at 21:09:31 CST. The recorded winner was `jpeg_ctx8192__spaces`; it did not demonstrate paired AMR recognition improvement, and the final change was whitespace-only. No candidate qualifies for the untouched holdout. Do not restart this campaign. No final-holdout evaluation was performed for it.

Implementation checkpoint `29fd7548da4610aee69925467368b0d68b270a5d` received a native Codex receipt reporting no major issues. The associated offline contract CI job recorded 44 passing tests; these are software tests, not OCR accuracy evidence. The implementation review does not retroactively validate legacy experiment predictions.

The terminal campaign state and winner assessment above are attributed to the user-supplied Cursor report. This documentation update did not independently replay private raw artifacts or inspect Mac processes. The committed trend file is a historical subset, not a complete 30-experiment ledger. No missing final metrics have been invented.

The section below is preserved from the earlier committed checkpoint. Its present-tense statements, three-experiment count, and next actions are historical and superseded by this final status. They are not instructions to resume inference. Original snapshots remain available in Git history at `29fd754`.

---

## Historical checkpoint text, preserved

Aggregates only. No transcriptions. CER is micro-averaged on cases that returned a transcription. A failed case is a coverage miss. It is not a zero-error success, and it is not mixed into the paired comparison.

Model: `glm-ocr:q8_0`, digest `6e5935a916fc8d6878a67c60c2b99648f54e10b4a4af4cbbfb2c308953000e5f`. Ollama 0.40.12.

Development and holdout writer groups are disjoint from each other. Both overlap the historical 24-document cohort. The holdout is not being read.

## Screen, 8 AMR pages and 64 Rx crops

| | Coverage | CER on scored cases | Shared-success CER | Critical tokens | False positives | p95 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| JPEG baseline | 2/8 | 0.649 on 1,808 characters | 0.649 | 7/7 | 1 | 8.7 s |
| JPEG, context 8192 | 8/8 | 0.465 on 6,699 characters | 0.649 | 7/7 on the shared pages; 23/27 on all scored pages | 1 on the shared pages; 8 overall | 24.8 s |

Rx screen: both arms scored 64/64. CER 0.372 and the predictions matched. Critical tokens in that crop set: 0.

PNG and contrast, at the default context, stayed at 2/8 and were discarded.

`jpeg_ctx8192` is a provisional screen keep because coverage rose and the two shared successes did not change CER, critical hits, or false positives. The lower 0.465 figure is the full scored population, not a paired gain.

## Confirmation so far, 20 AMR development pages

| | Coverage | CER on scored cases | Shared-success CER | Critical tokens | False positives | p95 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| JPEG baseline | 3/20 | 0.665 on 3,576 characters | 0.665 | 7/8 | 1 | 9.0 s |
| JPEG, context 8192 | 19/20 | 0.487 on 12,164 characters | 0.665 | 7/8 on the shared pages; 37/51 on all scored pages | 1 on the shared pages; 19 overall | 28.0 s |

`AMR_043` still failed at context 8192. The Rx confirmation set is still running. This candidate is not confirmed yet.

## Completed candidate experiments

3. PNG discarded, contrast discarded, context-8192 kept on the screen only.

## Next

Finish the 256-crop Rx confirmation for the baseline, then the same crops for context 8192. If that keep holds, the next single change is a prompt that forbids inventing illegible doses and units. The 19 new false positives are why that hypothesis is first.
