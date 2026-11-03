# Clinical NLP UI v2

The workbench stays a synthetic review and evaluation tool. This pass changes how the same results are shown.

- Review compares one source note with the extracted fields. Pasted text stays text. A page image appears only when the note has one. Field names and review actions use everyday words. Scores and review rules are unchanged.
- Validation Lab reports the 20-note evaluation in words: matched, extra, and missed. F1 stays a number from the API. It is not colored and it is not described as clinical accuracy. The 24-image test stays on its own page.
- Test evidence leads with the recorded 24-image comparison, then the separate three-case Tesseract examples. Counts come from the published evidence payload.

Routes are unchanged: `/`, `/queue`, `/history`, `/metrics`, `/validation-lab`, `/showcase`.
