# PR #8: Verified local three-arm synthetic vision benchmark

**Run:** October 30, 2026, Apple M2 Pro / 16 GB unified memory, macOS arm64, Python 3.11.15. The experiment evaluates 24 entirely fictional, generator-authored images (8 clean printed, 8 degraded printed, 8 photographed-effect printed). It includes **no genuine handwriting, human-adjudicated gold, real patient notes or clinical validation**.

## Immutable experiment and evidence

- Source: PR #7 synthetic holdout `prospective_printed_synthetic_holdout_v1` with canonical manifest SHA-256 `c30cfdd3ce457b157d1ee89a7859dfbe137c71e17990e84dcab49a74c6e6c332`.
- Pre-frozen parser/scorer baseline: PR #6 merge `b58a65da2b28917aedd5504c4c8b7e5818f03033` with the separately documented retrospective frozen dependency amendment. The actual 24-case model evaluation used PR #8 code at commit `0dd0888df4f587963d9882f3324a5e4a886922af`; frozen scoring, source images, model prompts and gold labels were not modified.
- Original evidence archive: [PR8_REAL_BENCHMARK_EVIDENCE.zip.base64.txt](evidence/PR8_REAL_BENCHMARK_EVIDENCE.zip.base64.txt). This is an exact lossless ASCII/base64 copy of the 30,742-byte Mac ZIP containing the three original local model reports, paired comparison, completion receipt and independent offline replay.
- **Decoded ZIP SHA-256:** `d073a12c5f9f7b9ff2a3cb406a5d4c06e50c7812f4ddda43e72001007a73a80d`.
- **Original paired comparison SHA-256:** `96ee3dbb3dae1835dccd97b3822d7ab62d627b70968e799e9d9c8f09b0a32ec2`.
- **Completion receipt SHA-256:** `8ebe616f6a8789fad2aa9dab37d17f868bd452a667d118ffcc4528166496014d`.

To reconstruct and verify from the repository root, run:

```bash
python - <<'PY'
from pathlib import Path
import base64, hashlib, zipfile
src = Path('docs/validation/evidence/PR8_REAL_BENCHMARK_EVIDENCE.zip.base64.txt')
payload = base64.b64decode(src.read_text(encoding='ascii').strip(), validate=True)
expected = 'd073a12c5f9f7b9ff2a3cb406a5d4c06e50c7812f4ddda43e72001007a73a80d'
assert hashlib.sha256(payload).hexdigest() == expected
out = Path('artifacts/pr8_real_vision_benchmark_evidence_verified.zip')
out.parent.mkdir(parents=True, exist_ok=True)
out.write_bytes(payload)
with zipfile.ZipFile(out) as archive:
    assert archive.testzip() is None
print('ORIGINAL_EVIDENCE_VERIFIED', expected)
PY
```

All individual arm report hashes matched the preserved completion receipt. Both the saved offline replay and a separate audit of stored predictions against the source annotations reproduced the scores and paired classifications. The hashes and replay establish **internal evidence integrity**, not independently signed attestation that a particular model ran on the Mac.

## Actual 24-image results

Gold support: 23 annotated medication occurrences, 5 annotated vital occurrences, 55 exact critical strings, 2,896 reference characters and 494 reference words. Strict whole-record medication matching requires the annotated name/dose/route/frequency/action to agree, including duplicate occurrences. An incorrect gold-provided attribute counts as one false positive and one false negative. OCR and direct structured outputs are distinct tasks.

| Metric | Tesseract 5.5.2 + parser | GLM-OCR q8_0 + parser | Qwen3-VL 4B direct |
| --- | ---: | ---: | ---: |
| Medication TP / FP / FN | 11 / 3 / 12 | **23 / 0 / 0** | 15 / 8 / 8 |
| Medication precision | 78.57% | **100.00%** | 65.22% |
| Medication recall | 47.83% | **100.00%** | 65.22% |
| Medication strict F1 | 59.46% | **100.00%** | 65.22% |
| Vitals TP / FP / FN | 4 / 0 / 1 | **5 / 0 / 0** | 0 / 7 / 5 |
| Vitals strict F1 | 88.89% | **100.00%** | 0.00% |
| OCR micro CER | 4.2818% (124/2,896) | **0.5870% (17/2,896)** | N/A |
| OCR micro WER | 33.1984% (164/494) | **2.6316% (13/494)** | N/A |
| Critical string presence | 42/55 | **55/55** | N/A |
| p50 per-image latency | 246 ms | 7,092 ms | 17,090 ms |
| p95 per-image latency | 308 ms | 8,554 ms | 28,037 ms |

Exact observed local identities:

- Tesseract `5.5.2`.
- GLM `glm-ocr:q8_0`, model digest `6e5935a916fc8d6878a67c60c2b99648f54e10b4a4af4cbbfb2c308953000e5f`.
- Qwen `qwen3-vl:4b`, model digest `a1b29c246319cdcb1f3842f36d29f198f737c0cf516ba1bcba34b1b974e87980`.

Paired exact-medication-case outcomes (first-only / second-only / tied): GLM vs Tesseract **11 / 0 / 13**, Qwen vs GLM **0 / 8 / 16**, Qwen vs Tesseract **7 / 4 / 13**. GLM had lower character error rate than Tesseract on **24/24 exact paired images**. These are descriptive results from a single tiny synthetic dataset; they are not clinical or handwriting accuracy estimates.

The Linux CI Tesseract-only run on the same frozen cases recorded medication F1 0.64865 and CER 0.04178. Mac Tesseract 5.5.2 differed. Keep each observed executable/runtime result associated with its actual run; do not replace the Mac paired baseline with CI scores.

## Source-correct error audit

An earlier Gemini-written narrative included **incorrect synthetic source values** despite correct aggregate report hashes. The following examples were checked against the actual frozen case definitions and saved predictions, and supersede that prose:

| Frozen case | Correct original source and gold | Recorded error / match |
| --- | --- | --- |
| `h04_baclofen_duplicate` | **5 mg PO QAM** and **10 mg PO QHS** | Tesseract omitted both occurrences; GLM and Qwen each matched both |
| `h12_budesonide_inhaler` | **90 mcg**, inhaled **2 puffs BID**; the annotated frequency is **BID**, SpO2 **97%** | Qwen proposed **90 mg**, a 1,000-fold unit discrepancy, plus frequency `2 puffs BID` rather than gold `BID`; Tesseract omitted medication and SpO2; GLM exact |
| `h15_hydralazine_prn` | **10 mg PO TID PRN**, BP 158/94 | Qwen dropped `PRN` (`TID`), and used vital label `blood pressure` instead of `blood_pressure`; GLM exact |
| `h17_levetiracetam_duplicate` | **250 mg PO BID** plus **500 mg PO at bedtime** | Tesseract omitted route on second occurrence and returned `bedtime` instead of `at bedtime`; GLM and Qwen exact |
| `h19_albuterol_after_running` | **90 mcg**, inhaled **1 puff Q6H PRN** | Qwen dropped `PRN`; Tesseract omitted the medication; GLM exact |
| `h20_valsartan_continue_hold` | **Continue to hold Valsartan 40 mg PO daily**; action `hold` | Tesseract omitted route/frequency; GLM and Qwen exact |
| `h03_duloxetine_stopped` | **Discontinue Duloxetine 30 mg PO daily**; gold action `stop` | Qwen returned `discontinue` rather than `stop`; GLM exact |
| `h14_aspirin_negative` | **No aspirin currently taken**, heart rate 84 bpm; 0 medication occurrences | All arms emitted no medication; Tesseract missed exact `No aspirin` critical string; Qwen used vital label `heart rate` instead of `heart_rate` |
| `h06_weight_not_medication`, `h22_anthropometric_negative` | Fictional weight descriptions, **zero gold vital occurrences** | Qwen returned extra `weight gain` / `weight` vital candidates, counted as false positives under the declared annotation scope |

Other Qwen medication mismatches: `h11` combined route/frequency `POQHS`; `h13` used `Stop taking` vs annotated action `stop`; `h21` omitted `PRN`; `h24` used action `stopped` rather than `stop`. Some failures are vocabulary/schema formatting; the 90 mg versus 90 mcg mismatch is substantively safety relevant. Retrospectively normalizing labels against this frozen holdout would be tuning and would require a new unseen cohort for prospective evaluation. Exact critical-token presence does **not** establish correct negation or medication-status understanding.

## Observed system resources and limitations

| Measurement | GLM-OCR | Qwen3-VL |
| --- | ---: | ---: |
| Peak Ollama-reported loaded-model residency | 1,354,571,447 bytes (~1.35 GB) | 3,719,676,558 bytes (~3.72 GB) |
| Peak Ollama-reported Metal model VRAM | 1,354,571,447 bytes | 3,719,676,558 bytes |
| Mac used system swap before / after | ~5.99 GB / 8.12 GB | ~8.12 GB / 10.13 GB |
| Out-of-process runner peak RSS | **Unmeasured** | **Unmeasured** |

On Apple unified memory, reported Ollama model residency and Metal VRAM can reflect the same allocation and **must not be added**. Swap figures are *whole-system snapshots*, not model-attributable usage or measured peaks. Latencies include the local sequential execution context and cannot be treated as production service-level guarantees.

## Engineering decision and next gate

For an **optional local synthetic workbench**, GLM-OCR followed by the frozen deterministic parser is the best-performing measured OCR proposal path. Retain fast Tesseract as a fallback and human review of consequential fields. Do not select Qwen's direct structured candidates as an unreviewed authoritative source on this evidence, especially given the 90 mg/mcg error. **No production routing, parser, prompt, model source or review-state behavior is changed by PR #8.**

Next: gather *genuine handwritten fictional notes* physically written by humans, obtain two independent verbatim transcriptions and adjudication, verify provenance, and run a newly frozen, separate prospective evaluation of error-prone numeric quantities, actions, negation and PRN. Also replicate with new unseen layouts and another runtime before considering stronger confidence claims. Nothing here establishes handwriting readiness, clinical validation, PHI compliance, treatment suitability or authorization to deploy.
