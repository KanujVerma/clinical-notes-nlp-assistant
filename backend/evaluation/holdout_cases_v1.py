"""Pre-authored, unseen fictional PRINTED visual holdout labels.

Created after the frozen PR #6 baseline seal; no model predictions were
inspected for selection, labeling or subsequent parser tuning.
All records are generator-authored, not human-independent annotations.
"""

CASES = [
  {
    "id": "h01_bisoprolol_decimal",
    "type": "printed_clean",
    "lines": [
      "SYNTHETIC DOCUMENT - NOT FOR CLINICAL USE",
      "Start Bisoprolol 2.5 mg PO QAM.",
      "Pulse 58 bpm; repeat pulse tomorrow."
    ],
    "critical_tokens": [
      "2.5 mg",
      "QAM",
      "58 bpm"
    ],
    "expected_medications": [
      {
        "name": "Bisoprolol",
        "dose": "2.5 mg",
        "route": "PO",
        "frequency": "QAM",
        "action": "start"
      }
    ],
    "expected_vitals": [
      {
        "vital_type": "heart_rate",
        "value": "58",
        "unit": "bpm"
      }
    ]
  },
  {
    "id": "h02_cefuroxime_course",
    "type": "printed_clean",
    "lines": [
      "SYNTHETIC DOCUMENT - NOT FOR CLINICAL USE",
      "Take Cefuroxime 500 mg PO BID for 5 more days.",
      "Do not use the 5000 mg label."
    ],
    "critical_tokens": [
      "500 mg",
      "5 more days",
      "5000 mg"
    ],
    "expected_medications": [
      {
        "name": "Cefuroxime",
        "dose": "500 mg",
        "route": "PO",
        "frequency": "BID"
      }
    ],
    "expected_vitals": []
  },
  {
    "id": "h03_duloxetine_stopped",
    "type": "printed_clean",
    "lines": [
      "SYNTHETIC DOCUMENT - NOT FOR CLINICAL USE",
      "Discontinue Duloxetine 30 mg PO daily.",
      "Return for a fictional follow-up in 9 days."
    ],
    "critical_tokens": [
      "Discontinue",
      "30 mg"
    ],
    "expected_medications": [
      {
        "name": "Duloxetine",
        "dose": "30 mg",
        "route": "PO",
        "frequency": "daily",
        "action": "stop"
      }
    ],
    "expected_vitals": []
  },
  {
    "id": "h04_baclofen_duplicate",
    "type": "printed_clean",
    "lines": [
      "SYNTHETIC DOCUMENT - NOT FOR CLINICAL USE",
      "Baclofen 5 mg PO QAM.",
      "Baclofen 10 mg PO QHS.",
      "Dose positions correspond to separate orders."
    ],
    "critical_tokens": [
      "5 mg",
      "10 mg",
      "QHS"
    ],
    "expected_medications": [
      {
        "name": "Baclofen",
        "dose": "5 mg",
        "route": "PO",
        "frequency": "QAM"
      },
      {
        "name": "Baclofen",
        "dose": "10 mg",
        "route": "PO",
        "frequency": "QHS"
      }
    ],
    "expected_vitals": []
  },
  {
    "id": "h05_pravastatin_nightly",
    "type": "printed_clean",
    "lines": [
      "SYNTHETIC DOCUMENT - NOT FOR CLINICAL USE",
      "Pravastatin 10 mg PO nightly.",
      "Blood pressure 134/86 mmHg."
    ],
    "critical_tokens": [
      "10 mg",
      "134/86"
    ],
    "expected_medications": [
      {
        "name": "Pravastatin",
        "dose": "10 mg",
        "route": "PO",
        "frequency": "nightly"
      }
    ],
    "expected_vitals": [
      {
        "vital_type": "blood_pressure",
        "value": "134/86",
        "unit": "mmHg"
      }
    ]
  },
  {
    "id": "h06_weight_not_medication",
    "type": "printed_clean",
    "lines": [
      "SYNTHETIC DOCUMENT - NOT FOR CLINICAL USE",
      "Weight gain 45 g over a month.",
      "Routine follow-up requested for this fictional visit."
    ],
    "critical_tokens": [
      "45 g",
      "follow-up"
    ],
    "expected_medications": [],
    "expected_vitals": []
  },
  {
    "id": "h07_tiotropium_microgram",
    "type": "printed_clean",
    "lines": [
      "SYNTHETIC DOCUMENT - NOT FOR CLINICAL USE",
      "Start Tiotropium 18 mcg inhaled daily.",
      "Do not substitute an 180 mcg strength."
    ],
    "critical_tokens": [
      "18 mcg",
      "180 mcg"
    ],
    "expected_medications": [
      {
        "name": "Tiotropium",
        "dose": "18 mcg",
        "route": "inhaled",
        "frequency": "daily",
        "action": "start"
      }
    ],
    "expected_vitals": []
  },
  {
    "id": "h08_sotalol_hold_order",
    "type": "printed_clean",
    "lines": [
      "SYNTHETIC DOCUMENT - NOT FOR CLINICAL USE",
      "Hold Sotalol 80 mg PO BID.",
      "Telemetry review is due tomorrow."
    ],
    "critical_tokens": [
      "Hold",
      "80 mg"
    ],
    "expected_medications": [
      {
        "name": "Sotalol",
        "dose": "80 mg",
        "route": "PO",
        "frequency": "BID",
        "action": "hold"
      }
    ],
    "expected_vitals": []
  },
  {
    "id": "h09_ursodiol_continue",
    "type": "printed_degraded",
    "lines": [
      "SYNTHETIC DOCUMENT - NOT FOR CLINICAL USE",
      "Continue Ursodiol 300 mg PO BID.",
      "A fictional medication list was reconciled."
    ],
    "critical_tokens": [
      "Continue",
      "300 mg"
    ],
    "expected_medications": [
      {
        "name": "Ursodiol",
        "dose": "300 mg",
        "route": "PO",
        "frequency": "BID",
        "action": "continue"
      }
    ],
    "expected_vitals": []
  },
  {
    "id": "h10_doxycycline_interval",
    "type": "printed_degraded",
    "lines": [
      "SYNTHETIC DOCUMENT - NOT FOR CLINICAL USE",
      "Doxycycline 100 mg PO every 12 hours.",
      "Finish the fictional course as previously planned."
    ],
    "critical_tokens": [
      "100 mg",
      "every 12 hours"
    ],
    "expected_medications": [
      {
        "name": "Doxycycline",
        "dose": "100 mg",
        "route": "PO",
        "frequency": "every 12 hours"
      }
    ],
    "expected_vitals": []
  },
  {
    "id": "h11_temazepam_decimal",
    "type": "printed_degraded",
    "lines": [
      "SYNTHETIC DOCUMENT - NOT FOR CLINICAL USE",
      "Temazepam 7.5 mg PO QHS.",
      "Check that the label does not say 75 mg."
    ],
    "critical_tokens": [
      "7.5 mg",
      "75 mg"
    ],
    "expected_medications": [
      {
        "name": "Temazepam",
        "dose": "7.5 mg",
        "route": "PO",
        "frequency": "QHS"
      }
    ],
    "expected_vitals": []
  },
  {
    "id": "h12_budesonide_inhaler",
    "type": "printed_degraded",
    "lines": [
      "SYNTHETIC DOCUMENT - NOT FOR CLINICAL USE",
      "Budesonide 90 mcg inhaled 2 puffs BID.",
      "SpO2 97% on room air."
    ],
    "critical_tokens": [
      "90 mcg",
      "2 puffs",
      "97%"
    ],
    "expected_medications": [
      {
        "name": "Budesonide",
        "dose": "90 mcg",
        "route": "inhaled",
        "frequency": "BID"
      }
    ],
    "expected_vitals": [
      {
        "vital_type": "oxygen_saturation",
        "value": "97",
        "unit": "%"
      }
    ]
  },
  {
    "id": "h13_montelukast_stop",
    "type": "printed_degraded",
    "lines": [
      "SYNTHETIC DOCUMENT - NOT FOR CLINICAL USE",
      "Stop taking Montelukast 10 mg PO daily.",
      "Allergy clinic follow-up in 7 days."
    ],
    "critical_tokens": [
      "Stop taking",
      "10 mg"
    ],
    "expected_medications": [
      {
        "name": "Montelukast",
        "dose": "10 mg",
        "route": "PO",
        "frequency": "daily",
        "action": "stop"
      }
    ],
    "expected_vitals": []
  },
  {
    "id": "h14_aspirin_negative",
    "type": "printed_degraded",
    "lines": [
      "SYNTHETIC DOCUMENT - NOT FOR CLINICAL USE",
      "No aspirin currently taken.",
      "Heart rate 84 bpm."
    ],
    "critical_tokens": [
      "No aspirin",
      "84 bpm"
    ],
    "expected_medications": [],
    "expected_vitals": [
      {
        "vital_type": "heart_rate",
        "value": "84",
        "unit": "bpm"
      }
    ]
  },
  {
    "id": "h15_hydralazine_prn",
    "type": "printed_degraded",
    "lines": [
      "SYNTHETIC DOCUMENT - NOT FOR CLINICAL USE",
      "Hydralazine 10 mg PO TID PRN systolic pressure above 160.",
      "Blood pressure 158/94 mmHg."
    ],
    "critical_tokens": [
      "10 mg",
      "TID PRN",
      "158/94"
    ],
    "expected_medications": [
      {
        "name": "Hydralazine",
        "dose": "10 mg",
        "route": "PO",
        "frequency": "TID PRN"
      }
    ],
    "expected_vitals": [
      {
        "vital_type": "blood_pressure",
        "value": "158/94",
        "unit": "mmHg"
      }
    ]
  },
  {
    "id": "h16_dabigatran_twice_daily",
    "type": "printed_degraded",
    "lines": [
      "SYNTHETIC DOCUMENT - NOT FOR CLINICAL USE",
      "Dabigatran 150 mg PO BID.",
      "Do not confuse this strength with 15 mg."
    ],
    "critical_tokens": [
      "150 mg",
      "15 mg"
    ],
    "expected_medications": [
      {
        "name": "Dabigatran",
        "dose": "150 mg",
        "route": "PO",
        "frequency": "BID"
      }
    ],
    "expected_vitals": []
  },
  {
    "id": "h17_levetiracetam_duplicate",
    "type": "photographed",
    "lines": [
      "SYNTHETIC DOCUMENT - NOT FOR CLINICAL USE",
      "Levetiracetam 250 mg PO BID.",
      "Levetiracetam 500 mg PO at bedtime.",
      "Keep the orders as separate occurrences."
    ],
    "critical_tokens": [
      "250 mg",
      "500 mg",
      "at bedtime"
    ],
    "expected_medications": [
      {
        "name": "Levetiracetam",
        "dose": "250 mg",
        "route": "PO",
        "frequency": "BID"
      },
      {
        "name": "Levetiracetam",
        "dose": "500 mg",
        "route": "PO",
        "frequency": "at bedtime"
      }
    ],
    "expected_vitals": []
  },
  {
    "id": "h18_aztreonam_intravenous",
    "type": "photographed",
    "lines": [
      "SYNTHETIC DOCUMENT - NOT FOR CLINICAL USE",
      "Aztreonam 1 g IV every 8 hours.",
      "Review the fictional allergy record before administering."
    ],
    "critical_tokens": [
      "1 g",
      "every 8 hours"
    ],
    "expected_medications": [
      {
        "name": "Aztreonam",
        "dose": "1 g",
        "route": "IV",
        "frequency": "every 8 hours"
      }
    ],
    "expected_vitals": []
  },
  {
    "id": "h19_albuterol_after_running",
    "type": "photographed",
    "lines": [
      "SYNTHETIC DOCUMENT - NOT FOR CLINICAL USE",
      "Albuterol 90 mcg inhaled 1 puff Q6H PRN wheezing after running.",
      "Do not exceed the fictional prescription."
    ],
    "critical_tokens": [
      "90 mcg",
      "Q6H PRN",
      "after running"
    ],
    "expected_medications": [
      {
        "name": "Albuterol",
        "dose": "90 mcg",
        "route": "inhaled",
        "frequency": "Q6H PRN"
      }
    ],
    "expected_vitals": []
  },
  {
    "id": "h20_valsartan_continue_hold",
    "type": "photographed",
    "lines": [
      "SYNTHETIC DOCUMENT - NOT FOR CLINICAL USE",
      "Continue to hold Valsartan 40 mg PO daily.",
      "Repeat the fictional chemistry panel at the next appointment."
    ],
    "critical_tokens": [
      "Continue to hold",
      "40 mg"
    ],
    "expected_medications": [
      {
        "name": "Valsartan",
        "dose": "40 mg",
        "route": "PO",
        "frequency": "daily",
        "action": "hold"
      }
    ],
    "expected_vitals": []
  },
  {
    "id": "h21_hydroxyzine_prn",
    "type": "photographed",
    "lines": [
      "SYNTHETIC DOCUMENT - NOT FOR CLINICAL USE",
      "Hydroxyzine 10 mg PO every 8 hours PRN itching at night.",
      "Patient has a fictional symptom diary."
    ],
    "critical_tokens": [
      "10 mg",
      "every 8 hours PRN"
    ],
    "expected_medications": [
      {
        "name": "Hydroxyzine",
        "dose": "10 mg",
        "route": "PO",
        "frequency": "every 8 hours PRN"
      }
    ],
    "expected_vitals": []
  },
  {
    "id": "h22_anthropometric_negative",
    "type": "photographed",
    "lines": [
      "SYNTHETIC DOCUMENT - NOT FOR CLINICAL USE",
      "Weight increased 12 g daily.",
      "A fictional urine sample was collected."
    ],
    "critical_tokens": [
      "12 g",
      "urine sample"
    ],
    "expected_medications": [],
    "expected_vitals": []
  },
  {
    "id": "h23_famotidine_predose_sig",
    "type": "photographed",
    "lines": [
      "SYNTHETIC DOCUMENT - NOT FOR CLINICAL USE",
      "Famotidine PO BID 20 mg.",
      "Avoid switching tablet labels without human review."
    ],
    "critical_tokens": [
      "PO BID",
      "20 mg"
    ],
    "expected_medications": [
      {
        "name": "Famotidine",
        "dose": "20 mg",
        "route": "PO",
        "frequency": "BID"
      }
    ],
    "expected_vitals": []
  },
  {
    "id": "h24_glipizide_poststatus",
    "type": "photographed",
    "lines": [
      "SYNTHETIC DOCUMENT - NOT FOR CLINICAL USE",
      "Glipizide 5 mg PO daily was stopped.",
      "Do not restart without a new clinician-authored order."
    ],
    "critical_tokens": [
      "5 mg",
      "was stopped"
    ],
    "expected_medications": [
      {
        "name": "Glipizide",
        "dose": "5 mg",
        "route": "PO",
        "frequency": "daily",
        "action": "stop"
      }
    ],
    "expected_vitals": []
  }
]
