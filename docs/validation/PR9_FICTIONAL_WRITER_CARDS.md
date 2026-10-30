# PR9 fictional writer cards (NOT evaluation gold)

**Purpose:** Prompts for volunteers to create **actual freehand fictional notes** on paper or with a freehand stylus. Do not represent these typed cards as handwriting or machine-readable clinical gold. Every volunteer should write the fictional meaning in their own words and handwriting, including freehand note layout. The card wording is deliberately not a transcript of the resulting image.

**3 writers × 8 notes:** writer 01 writes hw001-hw008, writer 02 writes hw009-hw016, and writer 03 writes hw017-hw024. Prefer handwriting styles distributed evenly across writers (block-print, cursive, mixed). Photograph or scan each *different* physical note; don't take multiple images of the same underlying note and call them independent samples. Aim for 12 clean and 12 challenging captures, but never artificially degrade fonts and call that handwriting.

**Volunteer instructions:** Use no actual patient names, diagnoses, records, dates of birth, contact info, signatures, or health data. Write the label `SYNTHETIC FICTIONAL NOTE`. Do not draw electronic typed text, trace font screenshots, generate AI strokes or reconstruct notes by Python. If a clinical concept is unclear, ask the study coordinator for an alternative fictional card before writing; do not use actual case material.

**Blinding:** This file is for writers/coordinator only. The two independent transcribers and the separate adjudicator should see only original human-written images and the independent transcription records. They must not see these source cards until all gold is sealed. The final independent gold is based on what is actually visible, not on the typed prompt or whether the writer followed it perfectly.

## Writer prompts

- **hw001:** A fictional clinic note starting metformin 500 mg PO BID; record weight 64 kg.
- **hw002:** Fictional medication list: stop atorvastatin 20 mg PO at night; do not confuse 20 with 200.
- **hw003:** Fictional follow-up: hold atenolol 25 mg PO daily; pulse 52 bpm.
- **hw004:** No medications currently taken; BP 126/78 mmHg; follow up in 2 weeks.
- **hw005:** Fictional order: levothyroxine 25 mcg PO every morning; distinguish 25 mcg from 250 mcg.
- **hw006:** Fictional cough note: benzonatate 100 mg PO TID PRN; temperature 37.2 C.
- **hw007:** Fictional prescription: take gabapentin 300 mg PO at bedtime; previously 100 mg.
- **hw008:** Fictional respiratory note: albuterol 90 mcg inhaled 1 puff as needed; SpO2 96%.
- **hw009:** Fictional note: no aspirin ordered; no acute concerns; no measured vitals.
- **hw010:** Fictional dose: warfarin 2.5 mg PO daily; do not write 25 mg.
- **hw011:** Fictional treatment: amoxicillin 250 mg PO every 8 hours for 6 days.
- **hw012:** Fictional repeated orders: baclofen 5 mg PO in morning; baclofen 10 mg PO at bedtime.
- **hw013:** Fictional change: discontinue duloxetine 60 mg PO daily; note no replacement drug.
- **hw014:** Fictional inhaler entry: budesonide 80 mcg inhaled twice daily, 2 puffs.
- **hw015:** Fictional vital note only: BP 142/90 mmHg, pulse 86 bpm; no medications listed.
- **hw016:** Fictional order: resume calcium carbonate 500 mg chewable daily.
- **hw017:** Fictional hold instruction: continue to hold valsartan 40 mg PO daily; avoid saying continue taking.
- **hw018:** Fictional PRN order: hydroxyzine 10 mg PO every 6 hours PRN itching.
- **hw019:** Fictional note with only weight 72 kg and temperature 36.7 C; explicitly no medication changes.
- **hw020:** Fictional medication: aztreonam 1 g IV every 12 hours; do not confuse 1 g with 1 mg.
- **hw021:** Fictional negative medication mention: previously considered aspirin, but it was never started.
- **hw022:** Fictional treatment change: reduce propranolol from 20 mg to 10 mg PO BID; record pulse 61 bpm.
- **hw023:** Fictional antibiotic: doxycycline 100 mg PO once daily for 7 days; spelling must remain legible.
- **hw024:** Fictional stopped medication: glipizide 5 mg PO daily was stopped last visit; no restart.

### Pre-registered subject coverage

These prompts deliberately mix medication-positive, medication-free negative, dose/unit-decimal, PRN/hold/stop/continue, duplicated name and vital-sign cases. They do not guarantee that the written outputs will retain every target. If a writer omits a detail, the independent adjudicator records what is actually on the image; never backfill it from this card. If a writer's page is unreadable, retain it as a pre-inference unscorable case with the adjudicator's documented reason.

**Evaluation contract:** Freeze all adjudications before first model run. No tuning or cherry-picking of PR8 parser or Qwen mappings on these handwriting samples, and no claim of clinical validity.
