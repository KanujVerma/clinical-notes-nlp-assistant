"""Generate reproducible printed synthetic OCR images with exact gold labels.

The images are generated from text, never from real patient information.
These are PRINTED examples, not handwritten examples. They are not a held-out
clinical dataset. To measure an actual installed model, next run:
  python backend/evaluation/vision_benchmark.py --manifest data/vision_gold/manifest.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import random

from PIL import Image, ImageDraw, ImageFilter, ImageFont


CASES = [
    {
        "id": "synthetic_print_clean",
        "type": "printed_clean",
        "lines": [
            "SYNTHETIC DOCUMENT - NOT FOR CLINICAL USE",
            "Prescription: Metformin 500 mg PO BID.",
            "Lisinopril 10 mg PO daily.",
            "Blood pressure 120/80 mmHg.",
        ],
        "critical_tokens": ["500 mg", "10 mg", "120/80"],
        "expected_medications": [
            {"name": "Metformin", "dose": "500 mg", "route": "PO", "frequency": "BID"},
            {"name": "Lisinopril", "dose": "10 mg", "route": "PO", "frequency": "daily"},
        ],
        "expected_vitals": [
            {"vital_type": "blood_pressure", "value": "120/80", "unit": "mmHg"},
        ],
    },
    {
        "id": "synthetic_print_decimal",
        "type": "printed_decimal",
        "lines": [
            "SYNTHETIC DOCUMENT - NOT FOR CLINICAL USE",
            "Hold Warfarin 2.5 mg PO daily.",
            "Do not substitute 25 mg.",
            "Return if symptoms worsen.",
        ],
        "critical_tokens": ["2.5 mg", "25 mg", "Hold", "Do not"],
        "expected_medications": [
            {"name": "Warfarin", "dose": "2.5 mg", "route": "PO", "frequency": "daily", "action": "hold"},
        ],
        "expected_vitals": [],
    },
    {
        "id": "synthetic_print_noisy",
        "type": "printed_degraded",
        "lines": [
            "SYNTHETIC DOCUMENT - NOT FOR CLINICAL USE",
            "Amoxicillin 500 mg PO TID for 10 days.",
            "Do not continue aspirin 81 mg.",
            "Follow up in 2 weeks.",
        ],
        "critical_tokens": ["500 mg", "10 days", "Do not", "81 mg"],
        "expected_medications": [
            {"name": "Amoxicillin", "dose": "500 mg", "route": "PO", "frequency": "TID"},
            {"name": "aspirin", "dose": "81 mg", "route": "", "frequency": "", "action": "stop"},
        ],
        "expected_vitals": [],
    },
]

EXPANDED_CASES = [
    # --- 10 Clean Printed Cases ---
    {
        "id": "clean_01_routine_hypertension",
        "type": "printed_clean",
        "lines": [
            "SYNTHETIC DOCUMENT - NOT FOR CLINICAL USE",
            "Prescription: Lisinopril 10 mg PO daily.",
            "Hydrochlorothiazide 25 mg PO daily.",
            "Blood pressure 128/82 mmHg. Heart rate 72 bpm.",
        ],
        "critical_tokens": ["10 mg", "25 mg", "128/82", "72 bpm"],
        "expected_medications": [
            {"name": "Lisinopril", "dose": "10 mg", "route": "PO", "frequency": "daily"},
            {"name": "Hydrochlorothiazide", "dose": "25 mg", "route": "PO", "frequency": "daily"},
        ],
        "expected_vitals": [
            {"vital_type": "blood_pressure", "value": "128/82", "unit": "mmHg"},
            {"vital_type": "heart_rate", "value": "72", "unit": "bpm"},
        ],
    },
    {
        "id": "clean_02_decimal_warfarin",
        "type": "printed_clean",
        "lines": [
            "SYNTHETIC DOCUMENT - NOT FOR CLINICAL USE",
            "Hold Warfarin 2.5 mg PO daily.",
            "Do not dispense Warfarin 25 mg.",
            "INR check scheduled in 3 days.",
        ],
        "critical_tokens": ["2.5 mg", "25 mg", "Hold", "Do not"],
        "expected_medications": [
            {"name": "Warfarin", "dose": "2.5 mg", "route": "PO", "frequency": "daily", "action": "hold"},
        ],
        "expected_vitals": [],
    },
    {
        "id": "clean_03_duplicate_prednisone_taper",
        "type": "printed_clean",
        "lines": [
            "SYNTHETIC DOCUMENT - NOT FOR CLINICAL USE",
            "Prednisone 20 mg PO QAM.",
            "Prednisone 10 mg PO QPM with dinner.",
            "Taper by 5 mg weekly.",
        ],
        "critical_tokens": ["20 mg", "10 mg", "QAM", "QPM"],
        "expected_medications": [
            {"name": "Prednisone", "dose": "20 mg", "route": "PO", "frequency": "QAM"},
            {"name": "Prednisone", "dose": "10 mg", "route": "PO", "frequency": "QPM"},
        ],
        "expected_vitals": [],
    },
    {
        "id": "clean_04_microgram_levothyroxine",
        "type": "printed_clean",
        "lines": [
            "SYNTHETIC DOCUMENT - NOT FOR CLINICAL USE",
            "Levothyroxine 75 mcg PO every morning before breakfast.",
            "Do not confuse 75 mcg with 75 mg.",
            "TSH follow-up in 6 weeks.",
        ],
        "critical_tokens": ["75 mcg", "75 mg", "before breakfast"],
        "expected_medications": [
            {"name": "Levothyroxine", "dose": "75 mcg", "route": "PO", "frequency": "every morning"},
        ],
        "expected_vitals": [],
    },
    {
        "id": "clean_05_decimal_haloperidol",
        "type": "printed_clean",
        "lines": [
            "SYNTHETIC DOCUMENT - NOT FOR CLINICAL USE",
            "Administer Haloperidol 0.5 mg PO BID PRN agitation.",
            "Maximum daily dose 2 mg. Do not exceed 5 mg.",
            "Monitor QT interval on ECG.",
        ],
        "critical_tokens": ["0.5 mg", "5 mg", "BID PRN", "2 mg"],
        "expected_medications": [
            {"name": "Haloperidol", "dose": "0.5 mg", "route": "PO", "frequency": "BID PRN"},
        ],
        "expected_vitals": [],
    },
    {
        "id": "clean_06_continue_discontinue_diabetes",
        "type": "printed_clean",
        "lines": [
            "SYNTHETIC DOCUMENT - NOT FOR CLINICAL USE",
            "Continue Metformin 500 mg PO BID.",
            "Discontinue Glipizide 5 mg PO daily.",
            "Fasting blood glucose 118 mg/dL.",
        ],
        "critical_tokens": ["Continue", "Discontinue", "500 mg", "5 mg"],
        "expected_medications": [
            {"name": "Metformin", "dose": "500 mg", "route": "PO", "frequency": "BID", "action": "continue"},
            {"name": "Glipizide", "dose": "5 mg", "route": "PO", "frequency": "daily", "action": "stop"},
        ],
        "expected_vitals": [
            {"vital_type": "blood_glucose", "value": "118", "unit": "mg/dL"},
        ],
    },
    {
        "id": "clean_07_multiple_vitals_panel",
        "type": "printed_clean",
        "lines": [
            "SYNTHETIC DOCUMENT - NOT FOR CLINICAL USE",
            "Vitals: BP 118/76 mmHg, HR 68 bpm, RR 16 bpm.",
            "SpO2 98% on room air, Temp 98.4 F.",
            "Patient resting comfortably in triage.",
        ],
        "critical_tokens": ["118/76", "68 bpm", "16 bpm", "98%", "98.4 F"],
        "expected_medications": [],
        "expected_vitals": [
            {"vital_type": "blood_pressure", "value": "118/76", "unit": "mmHg"},
            {"vital_type": "heart_rate", "value": "68", "unit": "bpm"},
            {"vital_type": "respiratory_rate", "value": "16", "unit": "bpm"},
            {"vital_type": "oxygen_saturation", "value": "98", "unit": "%"},
            {"vital_type": "temperature", "value": "98.4", "unit": "F"},
        ],
    },
    {
        "id": "clean_08_hold_start_cardiac",
        "type": "printed_clean",
        "lines": [
            "SYNTHETIC DOCUMENT - NOT FOR CLINICAL USE",
            "Hold Metoprolol Tartrate 25 mg PO BID today.",
            "Start Amlodipine 5 mg PO daily tomorrow morning.",
            "Call clinic if systolic BP drops below 100.",
        ],
        "critical_tokens": ["Hold", "Start", "25 mg", "5 mg"],
        "expected_medications": [
            {"name": "Metoprolol Tartrate", "dose": "25 mg", "route": "PO", "frequency": "BID", "action": "hold"},
            {"name": "Amlodipine", "dose": "5 mg", "route": "PO", "frequency": "daily", "action": "start"},
        ],
        "expected_vitals": [],
    },
    {
        "id": "clean_09_duplicate_insulin",
        "type": "printed_clean",
        "lines": [
            "SYNTHETIC DOCUMENT - NOT FOR CLINICAL USE",
            "Insulin glargine 20 units SubQ at bedtime.",
            "Insulin lispro 4 units SubQ with meals TID.",
            "Check fingerstick BG before each meal.",
        ],
        "critical_tokens": ["20 units", "4 units", "SubQ", "TID"],
        "expected_medications": [
            {"name": "Insulin glargine", "dose": "20 units", "route": "SubQ", "frequency": "at bedtime"},
            {"name": "Insulin lispro", "dose": "4 units", "route": "SubQ", "frequency": "TID"},
        ],
        "expected_vitals": [],
    },
    {
        "id": "clean_10_stat_antibiotic_iv",
        "type": "printed_clean",
        "lines": [
            "SYNTHETIC DOCUMENT - NOT FOR CLINICAL USE",
            "Ceftriaxone 1 g IV daily for 7 days.",
            "Azithromycin 500 mg PO daily for 3 days.",
            "SpO2 95% on 2L nasal cannula.",
        ],
        "critical_tokens": ["1 g", "IV", "500 mg", "95%"],
        "expected_medications": [
            {"name": "Ceftriaxone", "dose": "1 g", "route": "IV", "frequency": "daily"},
            {"name": "Azithromycin", "dose": "500 mg", "route": "PO", "frequency": "daily"},
        ],
        "expected_vitals": [
            {"vital_type": "oxygen_saturation", "value": "95", "unit": "%"},
        ],
    },

    # --- 10 Degraded Scan Cases ---
    {
        "id": "degraded_01_amoxicillin_aspirin",
        "type": "printed_degraded",
        "lines": [
            "SYNTHETIC DOCUMENT - NOT FOR CLINICAL USE",
            "Amoxicillin 500 mg PO TID for 10 days.",
            "Do not continue Aspirin 81 mg.",
            "Follow up in 2 weeks.",
        ],
        "critical_tokens": ["500 mg", "10 days", "Do not", "81 mg"],
        "expected_medications": [
            {"name": "Amoxicillin", "dose": "500 mg", "route": "PO", "frequency": "TID"},
            {"name": "Aspirin", "dose": "81 mg", "route": "", "frequency": "", "action": "stop"},
        ],
        "expected_vitals": [],
    },
    {
        "id": "degraded_02_decimal_digoxin",
        "type": "printed_degraded",
        "lines": [
            "SYNTHETIC DOCUMENT - NOT FOR CLINICAL USE",
            "Digoxin 0.125 mg PO daily.",
            "Caution: do not dispense 0.25 mg.",
            "Heart rate 64 bpm.",
        ],
        "critical_tokens": ["0.125 mg", "0.25 mg", "64 bpm"],
        "expected_medications": [
            {"name": "Digoxin", "dose": "0.125 mg", "route": "PO", "frequency": "daily"},
        ],
        "expected_vitals": [
            {"vital_type": "heart_rate", "value": "64", "unit": "bpm"},
        ],
    },
    {
        "id": "degraded_03_duplicate_lorazepam",
        "type": "printed_degraded",
        "lines": [
            "SYNTHETIC DOCUMENT - NOT FOR CLINICAL USE",
            "Lorazepam 0.5 mg PO nightly at bedtime.",
            "Lorazepam 1 mg PO every 6 hours PRN severe anxiety.",
            "Hold if excessively sedated.",
        ],
        "critical_tokens": ["0.5 mg", "1 mg", "nightly", "PRN", "Hold"],
        "expected_medications": [
            {"name": "Lorazepam", "dose": "0.5 mg", "route": "PO", "frequency": "nightly"},
            {"name": "Lorazepam", "dose": "1 mg", "route": "PO", "frequency": "every 6 hours PRN"},
        ],
        "expected_vitals": [],
    },
    {
        "id": "degraded_04_microgram_fentanyl",
        "type": "printed_degraded",
        "lines": [
            "SYNTHETIC DOCUMENT - NOT FOR CLINICAL USE",
            "Fentanyl 25 mcg/hr transdermal patch every 72 hours.",
            "Do not order 25 mg.",
            "Pain score 4/10.",
        ],
        "critical_tokens": ["25 mcg/hr", "25 mg", "every 72 hours"],
        "expected_medications": [
            {"name": "Fentanyl", "dose": "25 mcg/hr", "route": "transdermal", "frequency": "every 72 hours"},
        ],
        "expected_vitals": [],
    },
    {
        "id": "degraded_05_decimal_clonazepam",
        "type": "printed_degraded",
        "lines": [
            "SYNTHETIC DOCUMENT - NOT FOR CLINICAL USE",
            "Clonazepam 0.25 mg PO BID for panic attacks.",
            "Confirm dose is not 2.5 mg before dispensing.",
            "Patient counseled on driving precautions.",
        ],
        "critical_tokens": ["0.25 mg", "2.5 mg", "BID"],
        "expected_medications": [
            {"name": "Clonazepam", "dose": "0.25 mg", "route": "PO", "frequency": "BID"},
        ],
        "expected_vitals": [],
    },
    {
        "id": "degraded_06_continue_hold_statin",
        "type": "printed_degraded",
        "lines": [
            "SYNTHETIC DOCUMENT - NOT FOR CLINICAL USE",
            "Continue Atorvastatin 40 mg PO QHS.",
            "Hold Clopidogrel 75 mg PO daily for 5 days prior to surgery.",
            "Platelet count stable.",
        ],
        "critical_tokens": ["Continue", "Hold", "40 mg", "75 mg"],
        "expected_medications": [
            {"name": "Atorvastatin", "dose": "40 mg", "route": "PO", "frequency": "QHS", "action": "continue"},
            {"name": "Clopidogrel", "dose": "75 mg", "route": "PO", "frequency": "daily", "action": "hold"},
        ],
        "expected_vitals": [],
    },
    {
        "id": "degraded_07_vitals_hypertensive_crisis",
        "type": "printed_degraded",
        "lines": [
            "SYNTHETIC DOCUMENT - NOT FOR CLINICAL USE",
            "Blood pressure 186/112 mmHg. Pulse 104 bpm.",
            "Administer Labetalol 20 mg IV push STAT.",
            "Recheck blood pressure every 15 minutes.",
        ],
        "critical_tokens": ["186/112", "104 bpm", "20 mg", "IV"],
        "expected_medications": [
            {"name": "Labetalol", "dose": "20 mg", "route": "IV", "frequency": "STAT"},
        ],
        "expected_vitals": [
            {"vital_type": "blood_pressure", "value": "186/112", "unit": "mmHg"},
            {"vital_type": "heart_rate", "value": "104", "unit": "bpm"},
        ],
    },
    {
        "id": "degraded_08_discontinue_start_ace_arb",
        "type": "printed_degraded",
        "lines": [
            "SYNTHETIC DOCUMENT - NOT FOR CLINICAL USE",
            "Discontinue Enalapril 10 mg PO daily due to cough.",
            "Start Losartan 50 mg PO daily.",
            "Repeat serum creatinine in 2 weeks.",
        ],
        "critical_tokens": ["Discontinue", "Start", "10 mg", "50 mg"],
        "expected_medications": [
            {"name": "Enalapril", "dose": "10 mg", "route": "PO", "frequency": "daily", "action": "stop"},
            {"name": "Losartan", "dose": "50 mg", "route": "PO", "frequency": "daily", "action": "start"},
        ],
        "expected_vitals": [],
    },
    {
        "id": "degraded_09_duplicate_diltiazem",
        "type": "printed_degraded",
        "lines": [
            "SYNTHETIC DOCUMENT - NOT FOR CLINICAL USE",
            "Diltiazem CD 180 mg PO daily.",
            "Diltiazem 30 mg PO TID PRN breakthrough palpitations.",
            "Blood pressure 130/84 mmHg.",
        ],
        "critical_tokens": ["180 mg", "30 mg", "daily", "TID PRN"],
        "expected_medications": [
            {"name": "Diltiazem CD", "dose": "180 mg", "route": "PO", "frequency": "daily"},
            {"name": "Diltiazem", "dose": "30 mg", "route": "PO", "frequency": "TID PRN"},
        ],
        "expected_vitals": [
            {"vital_type": "blood_pressure", "value": "130/84", "unit": "mmHg"},
        ],
    },
    {
        "id": "degraded_10_steroid_burst",
        "type": "printed_degraded",
        "lines": [
            "SYNTHETIC DOCUMENT - NOT FOR CLINICAL USE",
            "Dexamethasone 0.75 mg PO BID for 3 days.",
            "Do not prescribe 7.5 mg.",
            "Temperature 99.1 F.",
        ],
        "critical_tokens": ["0.75 mg", "7.5 mg", "99.1 F"],
        "expected_medications": [
            {"name": "Dexamethasone", "dose": "0.75 mg", "route": "PO", "frequency": "BID"},
        ],
        "expected_vitals": [
            {"vital_type": "temperature", "value": "99.1", "unit": "F"},
        ],
    },

    # --- 10 Photographed-Style Document Cases ---
    {
        "id": "photo_01_discharge_summary",
        "type": "photographed",
        "lines": [
            "SYNTHETIC DOCUMENT - NOT FOR CLINICAL USE",
            "Discharge Meds: Pantoprazole 40 mg PO daily.",
            "Metoprolol Succinate 50 mg PO daily.",
            "Blood pressure 122/78 mmHg. Heart rate 66 bpm.",
        ],
        "critical_tokens": ["40 mg", "50 mg", "122/78", "66 bpm"],
        "expected_medications": [
            {"name": "Pantoprazole", "dose": "40 mg", "route": "PO", "frequency": "daily"},
            {"name": "Metoprolol Succinate", "dose": "50 mg", "route": "PO", "frequency": "daily"},
        ],
        "expected_vitals": [
            {"vital_type": "blood_pressure", "value": "122/78", "unit": "mmHg"},
            {"vital_type": "heart_rate", "value": "66", "unit": "bpm"},
        ],
    },
    {
        "id": "photo_02_decimal_levothyroxine_dose",
        "type": "photographed",
        "lines": [
            "SYNTHETIC DOCUMENT - NOT FOR CLINICAL USE",
            "Levothyroxine 0.05 mg PO daily on empty stomach.",
            "Verify label says 0.05 mg, never 0.5 mg.",
            "Repeat thyroid panel in 8 weeks.",
        ],
        "critical_tokens": ["0.05 mg", "0.5 mg", "empty stomach"],
        "expected_medications": [
            {"name": "Levothyroxine", "dose": "0.05 mg", "route": "PO", "frequency": "daily"},
        ],
        "expected_vitals": [],
    },
    {
        "id": "photo_03_duplicate_morphine",
        "type": "photographed",
        "lines": [
            "SYNTHETIC DOCUMENT - NOT FOR CLINICAL USE",
            "Morphine ER 30 mg PO every 12 hours.",
            "Morphine 15 mg PO every 4 hours PRN breakthrough pain.",
            "Respiratory rate 14 bpm.",
        ],
        "critical_tokens": ["30 mg", "15 mg", "every 12 hours", "PRN", "14 bpm"],
        "expected_medications": [
            {"name": "Morphine ER", "dose": "30 mg", "route": "PO", "frequency": "every 12 hours"},
            {"name": "Morphine", "dose": "15 mg", "route": "PO", "frequency": "every 4 hours PRN"},
        ],
        "expected_vitals": [
            {"vital_type": "respiratory_rate", "value": "14", "unit": "bpm"},
        ],
    },
    {
        "id": "photo_04_microgram_nitrostat",
        "type": "photographed",
        "lines": [
            "SYNTHETIC DOCUMENT - NOT FOR CLINICAL USE",
            "Nitroglycerin 400 mcg SL every 5 minutes PRN chest pain up to 3 doses.",
            "Do not use with PDE5 inhibitors.",
            "BP 110/70 mmHg before administration.",
        ],
        "critical_tokens": ["400 mcg", "SL", "up to 3 doses", "110/70"],
        "expected_medications": [
            {"name": "Nitroglycerin", "dose": "400 mcg", "route": "SL", "frequency": "every 5 minutes PRN"},
        ],
        "expected_vitals": [
            {"vital_type": "blood_pressure", "value": "110/70", "unit": "mmHg"},
        ],
    },
    {
        "id": "photo_05_decimal_alprazolam",
        "type": "photographed",
        "lines": [
            "SYNTHETIC DOCUMENT - NOT FOR CLINICAL USE",
            "Alprazolam 0.25 mg PO TID PRN anxiety.",
            "Warning: high risk if taken at 2.5 mg.",
            "Follow up in 1 month.",
        ],
        "critical_tokens": ["0.25 mg", "2.5 mg", "TID PRN"],
        "expected_medications": [
            {"name": "Alprazolam", "dose": "0.25 mg", "route": "PO", "frequency": "TID PRN"},
        ],
        "expected_vitals": [],
    },
    {
        "id": "photo_06_continue_discontinue_anticoagulation",
        "type": "photographed",
        "lines": [
            "SYNTHETIC DOCUMENT - NOT FOR CLINICAL USE",
            "Continue Apixaban 5 mg PO BID.",
            "Discontinue Aspirin 325 mg PO daily.",
            "Hemoglobin 13.8 g/dL.",
        ],
        "critical_tokens": ["Continue", "Discontinue", "5 mg", "325 mg"],
        "expected_medications": [
            {"name": "Apixaban", "dose": "5 mg", "route": "PO", "frequency": "BID", "action": "continue"},
            {"name": "Aspirin", "dose": "325 mg", "route": "PO", "frequency": "daily", "action": "stop"},
        ],
        "expected_vitals": [],
    },
    {
        "id": "photo_07_complete_icu_vitals",
        "type": "photographed",
        "lines": [
            "SYNTHETIC DOCUMENT - NOT FOR CLINICAL USE",
            "ICU Flowsheet: BP 142/88 mmHg, HR 88 bpm.",
            "RR 20 bpm, SpO2 96%, Temp 100.8 F.",
            "Acetaminophen 650 mg PO Q6H PRN fever.",
        ],
        "critical_tokens": ["142/88", "88 bpm", "20 bpm", "96%", "100.8 F", "650 mg"],
        "expected_medications": [
            {"name": "Acetaminophen", "dose": "650 mg", "route": "PO", "frequency": "Q6H PRN"},
        ],
        "expected_vitals": [
            {"vital_type": "blood_pressure", "value": "142/88", "unit": "mmHg"},
            {"vital_type": "heart_rate", "value": "88", "unit": "bpm"},
            {"vital_type": "respiratory_rate", "value": "20", "unit": "bpm"},
            {"vital_type": "oxygen_saturation", "value": "96", "unit": "%"},
            {"vital_type": "temperature", "value": "100.8", "unit": "F"},
        ],
    },
    {
        "id": "photo_08_hold_start_nephrology",
        "type": "photographed",
        "lines": [
            "SYNTHETIC DOCUMENT - NOT FOR CLINICAL USE",
            "Hold Spironolactone 25 mg PO daily due to hyperkalemia.",
            "Start Sodium polystyrene sulfonate 15 g PO daily.",
            "Recheck potassium tomorrow.",
        ],
        "critical_tokens": ["Hold", "Start", "25 mg", "15 g"],
        "expected_medications": [
            {"name": "Spironolactone", "dose": "25 mg", "route": "PO", "frequency": "daily", "action": "hold"},
            {"name": "Sodium polystyrene sulfonate", "dose": "15 g", "route": "PO", "frequency": "daily", "action": "start"},
        ],
        "expected_vitals": [],
    },
    {
        "id": "photo_09_duplicate_gabapentin",
        "type": "photographed",
        "lines": [
            "SYNTHETIC DOCUMENT - NOT FOR CLINICAL USE",
            "Gabapentin 300 mg PO TID.",
            "Gabapentin 600 mg PO QHS.",
            "Avoid alcohol while taking this medication.",
        ],
        "critical_tokens": ["300 mg", "TID", "600 mg", "QHS"],
        "expected_medications": [
            {"name": "Gabapentin", "dose": "300 mg", "route": "PO", "frequency": "TID"},
            {"name": "Gabapentin", "dose": "600 mg", "route": "PO", "frequency": "QHS"},
        ],
        "expected_vitals": [],
    },
    {
        "id": "photo_10_inhaler_combination",
        "type": "photographed",
        "lines": [
            "SYNTHETIC DOCUMENT - NOT FOR CLINICAL USE",
            "Fluticasone/Salmeterol 250/50 mcg inhaled 1 puff BID.",
            "Albuterol 90 mcg inhaled 2 puffs every 4 hours PRN wheezing.",
            "SpO2 94% on room air.",
        ],
        "critical_tokens": ["250/50 mcg", "1 puff", "90 mcg", "2 puffs", "94%"],
        "expected_medications": [
            {"name": "Fluticasone/Salmeterol", "dose": "250/50 mcg", "route": "inhaled", "frequency": "BID"},
            {"name": "Albuterol", "dose": "90 mcg", "route": "inhaled", "frequency": "every 4 hours PRN"},
        ],
        "expected_vitals": [
            {"vital_type": "oxygen_saturation", "value": "94", "unit": "%"},
        ],
    },
]


def make_printed_image(lines: list[str], degraded: bool) -> Image.Image:
    """Legacy generator for original 3-case benchmark."""
    width, height = 1200, 290
    img = Image.new("RGB", (width, height), (250, 250, 250))
    draw = ImageDraw.Draw(img)
    font = ImageFont.load_default()
    for index, line in enumerate(lines):
        draw.text((40, 30 + index * 50), line, fill=(10, 10, 10), font=font)
    img = img.resize((width * 2, height * 2), resample=Image.Resampling.NEAREST)
    if degraded:
        rng = random.Random(8122026)
        draw = ImageDraw.Draw(img)
        for _ in range(420):
            x = rng.randrange(img.width)
            y = rng.randrange(img.height)
            draw.point((x, y), fill=(205, 205, 205))
        img = img.rotate(1.5, expand=True, fillcolor=(250, 250, 250))
    return img


def make_image_for_case(lines: list[str], source_type: str, case_id: str) -> Image.Image:
    """Multi-style renderer supporting printed_clean, printed_degraded, and photographed."""
    line_height = 45
    margin_top = 35
    margin_left = 40
    base_height = max(290, margin_top + len(lines) * line_height + 35)
    base_width = 1100

    paper = Image.new("RGB", (base_width, base_height), (252, 252, 250))
    draw = ImageDraw.Draw(paper)
    font = ImageFont.load_default()
    for idx, line in enumerate(lines):
        draw.text((margin_left, margin_top + idx * line_height), line, fill=(20, 20, 20), font=font)

    paper = paper.resize((base_width * 2, base_height * 2), resample=Image.Resampling.NEAREST)
    rng = random.Random(int(hashlib.sha256(case_id.encode("utf-8")).hexdigest()[:8], 16))

    if source_type in ("printed_clean", "printed_decimal"):
        return paper

    if source_type == "printed_degraded":
        p_draw = ImageDraw.Draw(paper)
        for _ in range(500):
            x = rng.randrange(paper.width)
            y = rng.randrange(paper.height)
            shade = rng.randint(180, 230)
            p_draw.point((x, y), fill=(shade, shade, shade))
        paper = paper.filter(ImageFilter.GaussianBlur(radius=0.5))
        angle = rng.choice([-1.2, 1.2, -0.8, 1.5])
        return paper.rotate(angle, expand=True, fillcolor=(250, 250, 250))

    if source_type == "photographed":
        desk_w = paper.width + 120
        desk_h = paper.height + 120
        desk = Image.new("RGB", (desk_w, desk_h), (55, 48, 42))
        overlay = Image.new("RGBA", paper.size, (0, 0, 0, 0))
        o_draw = ImageDraw.Draw(overlay)
        for y in range(paper.height):
            alpha = int(30 * (y / paper.height))
            o_draw.line([(0, y), (paper.width, y)], fill=(20, 15, 10, alpha))
        paper_rgba = paper.convert("RGBA")
        paper_lit = Image.alpha_composite(paper_rgba, overlay).convert("RGB")
        angle = rng.choice([-1.5, 1.5, -1.0, 1.2])
        rot = paper_lit.rotate(angle, expand=True, fillcolor=(55, 48, 42))
        desk.paste(rot, (60, 60))
        return desk

    return paper


def generate(output_dir: Path, expanded: bool = False) -> Path:
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    image_dir = output_dir / "images"
    image_dir.mkdir(exist_ok=True)
    cases_source = EXPANDED_CASES if expanded else CASES
    cases = []
    for fixture in cases_source:
        case_id = fixture["id"]
        image_path = image_dir / f"{case_id}.png"
        if expanded:
            image = make_image_for_case(fixture["lines"], fixture["type"], case_id)
        else:
            image = make_printed_image(fixture["lines"], fixture["type"] == "printed_degraded")
        image.save(image_path, format="PNG", optimize=False)
        original = image_path.read_bytes()
        reference_text = "\n".join(fixture["lines"])
        cases.append({
            "id": case_id,
            "image": f"images/{case_id}.png",
            "sha256": hashlib.sha256(original).hexdigest(),
            "reference_text": reference_text,
            "critical_tokens": fixture["critical_tokens"],
            "expected_medications": fixture["expected_medications"],
            "expected_vitals": fixture["expected_vitals"],
            "source_type": fixture["type"],
        })
    manifest = {
        "dataset_id": (
            "synthetic_printed_visual_ocr_development_v2_expanded"
            if expanded else
            "synthetic_printed_visual_ocr_development_v1"
        ),
        "synthetic_only": True,
        "annotation_status": "synthetic_generator_ground_truth",
        "cases": cases,
        "limitations": [
            "Printed, degraded scans, and photographed docs; no handwriting",
            "Handwriting is NOT RUN: requires independent human-written clinical samples",
            "Generated from the label text; not an independent clinical holdout",
            "Not clinical validation",
        ] if expanded else [
            "Printed and artificially degraded only; no handwriting",
            "Generated from the label text; not an independent holdout",
            "Not clinical validation",
        ],
    }
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8",
    )
    return manifest_path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", type=Path, default=Path("data/vision_gold"),
    )
    parser.add_argument(
        "--expanded", action="store_true", help="Generate the full 30-case representative benchmark dataset",
    )
    args = parser.parse_args()
    print(generate(args.output, expanded=args.expanded))


if __name__ == "__main__":
    main()
