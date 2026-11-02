# PR #10 historical campaign audit

Read-only classification of the finished 30-candidate campaign. No predictions were rewritten, fingerprinted, or rerun. The untouched AMR and Rx holdouts were not opened.

## Provenance

All 66 saved screen and confirm runs are `legacy_unverified`. None carry `pr10_run_identity_v4`. They cannot be reused or promoted by the current loader. Case files still contain the original model name `glm-ocr:q8_0`, a model digest, a prompt hash, and per-case metrics. Those fields are historical records, not a current implementation fingerprint.

The campaign remains stopped at `experiment_budget`. The saved best name is still `jpeg_ctx8192__spaces`.

## Paired reread of the saved metrics

`jpeg_ctx8192` against the default-context baseline is a coverage change. Confirm AMR paired successes stay 3 pages, both at CER 0.6649888143176734 on 3576 characters. The unpaired confirm CER of 0.487 is 19 scored pages against 3, not a paired accuracy gain.

`jpeg_ctx8192__spaces` against `jpeg_ctx8192`:

| Split | Shared successes | Paired CER | Paired characters | All-scored CER | Coverage |
| --- | ---: | ---: | ---: | ---: | ---: |
| Confirm AMR | 19 | 0.4870108516935219 → 0.4868464320947057 | 12164 | same as paired | 19/20 → 19/20 |
| Confirm Rx | 256 | 0.39018952062430323 → 0.3896321070234114 | 1794 | same as paired | 256/256 → 256/256 |

Word error rate does not change on either confirm split. After collapsing repeated spaces, every shared confirm prediction matches: 17 of 19 AMR pages were already identical and the other 2 differ only by spaces; 255 of 256 Rx crops were already identical and the other 1 differs only by spaces.

## Conclusion

`jpeg_ctx8192__spaces` is a whitespace-normalization result on top of a coverage result. It is not a recognition improvement, and it is not eligible for the untouched holdout. The campaign's saved `best.json` reason predates this contract and is not a promotion under the current rules.
