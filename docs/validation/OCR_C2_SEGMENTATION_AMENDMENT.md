# Segmentation amendment 1

Amendment ID: `c2-segmentation-amendment-1`. Segmenter ID: `ocr_c2_segments_v3`.

This amendment does not replace `ocr_c2_segments_v2` or edit `docs/validation/ocr_c2_protocol_manifest.json`. The original manifest hash is `b90255108d9b351d1e2a441b0112a7ea58c3e783794b1f3290199681ac41abfd`. Partition, reference normalization, the 10% recognition target, critical-error rules, and the 60-second latency target are unchanged.

The amendment configuration is `docs/validation/ocr_c2_segmentation_amendment.json`. Private geometry output is under the existing campaign directory in `amendment-1/`. It uses the same cumulative ledger. No model call was added.

## Reproduction

A synthetic page with six short left-aligned lines, wide right margins, and clear gaps was run through the frozen v2 column detector. The result is `geometry=page`, `reading_order_uncertain=true`, `line_segmentation_unavailable=true`, and one region. The same page under v3 yields six certified lines. A centered word on a wide page stays one page fallback when the input type is `page`, and stays one word crop, with the column detector skipped, when the input type is `word_crop`.

The v2 failure is a quiet vertical run in the central band. Short lines leave that band empty, so a margin is reported as a gutter. v3 requires text on both sides of a gap, on at least three lines, with overlapping stacks on each side.

## Prototypes

Geometry search stopped at three CPU-only prototypes. None was chosen. No OCR output was used.

1. Rejected. A component slightly taller than the estimated scale, with a character-like width, rejected every development page as a cross-line stroke.
2. Rejected. Sparse fields were separated and the height cutoff was raised. All eight pages still fell back, from aligned word gaps, marks between lines, and tall components that only grazed a second line. The local mask also had to treat a tile with no paper as ink; a 75th-percentile background erased solid strokes inside a dark tile.
3. Rejected. Gutters now need three coherent lines on both sides, a mark between two lines goes to the nearer line unless the distances tie, and a tall component counts as cross-line only when it overlaps two lines by a substantial fraction of the scale. Zero of eight development pages became eligible.

## Development geometry

The gate required at least six of the eight fixed AMR screen documents to be covered by certified lines, with at least two lines on each nonblank page. The result is 0 of 8. No page produced a certified line crop. The line claims below are fallback reasons, not human adjudication and not recognition accuracy.

| Document | Pixels | Fallback | Scale (px) |
| --- | --- | --- | ---: |
| AMR_035 | 2012×3124 | cross_line_stroke | 20 |
| AMR_039 | 2175×3000 | cross_line_stroke | 32 |
| AMR_042 | 1653×2339 | ambiguous_layout | 33 |
| AMR_046 | 1653×2339 | unassigned_component | 23 |
| AMR_051 | 963×1280 | cross_line_stroke | 14 |
| AMR_053 | 4953×6945 | cross_line_stroke | 64 |
| AMR_057 | 1987×3000 | cross_line_stroke | 34 |
| AMR_061 | 823×1080 | unassigned_component | 11 |

All 64 development Rx crops stayed one `word_crop`. The column detector was not applied to them. That is the required input-type split, not evidence of a page gutter.

Per-page hashes, owner counts, and the fallback rectangle are in `docs/validation/ocr_c2_amendment1_geometry.json`. Private contact images are in `amendment-1/overlays/`. They are not certified line overlays. No reference text was read for this audit.

## Outcome

`geometry_still_blocked`. The optional recognizer was not implemented for measurement, and no weights were downloaded. G1, G1-runtime, and T1 did not run. Historical `B8192` predictions were not rerun. The ledger remains 1,225.7 charged seconds.
