#!/usr/bin/env python3
# scripts/create_eval_data.py
"""Write 20 hand-crafted eval notes and their ground-truth labels."""
import json
from pathlib import Path

NOTES_DIR = Path(__file__).parent.parent / "data" / "eval" / "notes"
LABELS_DIR = Path(__file__).parent.parent / "data" / "eval" / "labels"
NOTES_DIR.mkdir(parents=True, exist_ok=True)
LABELS_DIR.mkdir(parents=True, exist_ok=True)

EVAL_DATA = [
  # (filename, note_text, label_dict)
  ("eval_001", """Patient: Alice Morgan
Date of Service: 2024-02-14
Provider: Dr. Samuel Reyes

VITALS: BP 138/88. HR 82 bpm. Temp 98.8F. RR: 16. SpO2 97%. Wt 172 lbs.

MEDICATIONS:
lisinopril 10 mg PO daily
metformin 500 mg PO BID

DISCHARGE INSTRUCTIONS:
Take medications as prescribed. Follow a low-sodium diet.

FOLLOW UP:
Return to clinic in 2 weeks.

RETURN PRECAUTIONS:
Return to ER if BP exceeds 180/110 or chest pain develops.""",
  {
    "vitals": {"blood_pressure": "138/88", "heart_rate": "82", "temperature": "98.8",
               "respiratory_rate": "16", "oxygen_saturation": "97", "weight": "172 lbs"},
    "medications": [
      {"name": "lisinopril", "dose": "10 mg", "route": "PO", "frequency": "daily"},
      {"name": "metformin", "dose": "500 mg", "route": "PO", "frequency": "BID"},
    ],
    "instructions": {
      "discharge_instructions": "Take medications as prescribed. Follow a low-sodium diet.",
      "follow_up": "Return to clinic in 2 weeks.",
      "return_precautions": "Return to ER if BP exceeds 180/110 or chest pain develops.",
    },
    "metadata": {"patient_name": "Alice Morgan", "date_of_service": "2024-02-14", "provider_name": "Dr. Samuel Reyes"},
  }),
  ("eval_002", """Patient: Brian Cho
DOS: 2024-03-05
Attending: Dr. Lisa Pham

vitals: b/p 155/95, hr: 90, temp 99.1, rr 18, o2 sat 96%, wt 198#

meds: atorvastatin 20mg po daily, amlodipine 5 mg oral qd

d/c instructions: low fat diet, exercise 30 min 3x/wk.

f/u: see dr pham in 4 wks.

precautions: call if chest tightness or leg swelling.""",
  {
    "vitals": {"blood_pressure": "155/95", "heart_rate": "90", "temperature": "99.1",
               "respiratory_rate": "18", "oxygen_saturation": "96", "weight": "198 lbs"},
    "medications": [
      {"name": "atorvastatin", "dose": "20 mg", "route": "PO", "frequency": "daily"},
      {"name": "amlodipine", "dose": "5 mg", "route": "PO", "frequency": "daily"},
    ],
    "instructions": {
      "discharge_instructions": "low fat diet, exercise 30 min 3x/wk.",
      "follow_up": "see dr pham in 4 wks.",
      "return_precautions": "call if chest tightness or leg swelling.",
    },
    "metadata": {"patient_name": "Brian Cho", "date_of_service": "2024-03-05", "provider_name": "Dr. Lisa Pham"},
  }),
  ("eval_003", """62-year-old male presenting for hypertension follow-up.

Vital Signs: Blood pressure 148/92 mmHg, heart rate 76 beats/min,
temperature 98.2 degrees F, respirations 14/min, O2 sat 99% on RA, weight 185 lbs.

Current medications include metoprolol 50 mg twice daily by mouth and
lisinopril 20mg orally once daily. Patient denies use of any NSAIDs.

Plan: follow up in 6 weeks. Return to ER if severe headache or vision changes.""",
  {
    "vitals": {"blood_pressure": "148/92", "heart_rate": "76", "temperature": "98.2",
               "respiratory_rate": "14", "oxygen_saturation": "99", "weight": "185 lbs"},
    "medications": [
      {"name": "metoprolol", "dose": "50 mg", "route": "PO", "frequency": "BID"},
      {"name": "lisinopril", "dose": "20 mg", "route": "PO", "frequency": "daily"},
    ],
    "instructions": {
      "follow_up": "follow up in 6 weeks.",
      "return_precautions": "Return to ER if severe headache or vision changes.",
    },
    "metadata": {},
  }),
  ("eval_004", """Patient: Carol Diaz
Date of Service: 2024-04-01
Provider: Dr. James Okafor

V/S: BP 122/78 HR 68 T 97.9 RR 12 SpO2 100% Wt 145 lbs

Rx: omeprazole 40mg PO QHS; sertraline 100mg PO daily

DISCHARGE INSTRUCTIONS: Take omeprazole 30 min before breakfast. Continue sertraline as directed. Avoid caffeine and spicy foods.

FOLLOW UP: Follow up with gastroenterology in 3 weeks.

RETURN PRECAUTIONS: Return if vomiting blood or severe abdominal pain.""",
  {
    "vitals": {"blood_pressure": "122/78", "heart_rate": "68", "temperature": "97.9",
               "respiratory_rate": "12", "oxygen_saturation": "100", "weight": "145 lbs"},
    "medications": [
      {"name": "omeprazole", "dose": "40 mg", "route": "PO", "frequency": "QHS"},
      {"name": "sertraline", "dose": "100 mg", "route": "PO", "frequency": "daily"},
    ],
    "instructions": {
      "discharge_instructions": "Take omeprazole 30 min before breakfast. Continue sertraline as directed. Avoid caffeine and spicy foods.",
      "follow_up": "Follow up with gastroenterology in 3 weeks.",
      "return_precautions": "Return if vomiting blood or severe abdominal pain.",
    },
    "metadata": {"patient_name": "Carol Diaz", "date_of_service": "2024-04-01", "provider_name": "Dr. James Okafor"},
  }),
  ("eval_005", """SHORT PROGRESS NOTE

Patient stable. No acute distress.
BP: 130/80. Pulse 72. Temp 98.4. RR 14. Sat 98% RA.

Meds: albuterol 2.5 mg nebulized PRN, fluticasone 110 mcg inhaled BID.
Patient NOT on oral steroids. Denies use of beta blockers.

Follow patient in 1 month. Call clinic if wheezing worsens.""",
  {
    "vitals": {"blood_pressure": "130/80", "heart_rate": "72", "temperature": "98.4",
               "respiratory_rate": "14", "oxygen_saturation": "98"},
    "medications": [
      {"name": "albuterol", "dose": "2.5 mg", "route": "inhaled", "frequency": "PRN"},
      {"name": "fluticasone", "dose": "110 mcg", "route": "inhaled", "frequency": "BID"},
    ],
    "instructions": {
      "follow_up": "Follow patient in 1 month.",
      "return_precautions": "Call clinic if wheezing worsens.",
    },
    "metadata": {},
  }),
  ("eval_006", """Patient: Edward Park
DOS: 2024-05-12
Provider: Dr. Nina Russo

VITALS
BP 142/88 | HR 88 bpm | Temp 98.6°F | RR 16 | O2 Sat 97% | Wt 210 lbs

MEDICATIONS
- gabapentin 300 mg PO TID
- amoxicillin 875 mg PO BID x 7 days

DISCHARGE INSTRUCTIONS
Take gabapentin with food to minimize nausea. Complete full course of amoxicillin.

FOLLOW UP
Return to neurology in 4 weeks.

RETURN PRECAUTIONS
Return to ED if seizure activity, severe dizziness, or inability to walk.""",
  {
    "vitals": {"blood_pressure": "142/88", "heart_rate": "88", "temperature": "98.6",
               "respiratory_rate": "16", "oxygen_saturation": "97", "weight": "210 lbs"},
    "medications": [
      {"name": "gabapentin", "dose": "300 mg", "route": "PO", "frequency": "TID"},
      {"name": "amoxicillin", "dose": "875 mg", "route": "PO", "frequency": "BID"},
    ],
    "instructions": {
      "discharge_instructions": "Take gabapentin with food to minimize nausea. Complete full course of amoxicillin.",
      "follow_up": "Return to neurology in 4 weeks.",
      "return_precautions": "Return to ED if seizure activity, severe dizziness, or inability to walk.",
    },
    "metadata": {"patient_name": "Edward Park", "date_of_service": "2024-05-12", "provider_name": "Dr. Nina Russo"},
  }),
  ("eval_007", """Follow-Up Visit

Pt: Fiona Wells  Date: 2024-06-18  MD: Dr. Carl Wong

Assessment: Stable chronic hypertension, well-controlled.

VS: BP 128/76. HR 64. Temp 98.2F. RR 13. SpO2 99%. Wt 158 lbs.

Active medications: losartan 50mg PO daily, hydrochlorothiazide 25mg PO daily.

No medication changes today.
RTC in 3 months or sooner if BP > 160/100.""",
  {
    "vitals": {"blood_pressure": "128/76", "heart_rate": "64", "temperature": "98.2",
               "respiratory_rate": "13", "oxygen_saturation": "99", "weight": "158 lbs"},
    "medications": [
      {"name": "losartan", "dose": "50 mg", "route": "PO", "frequency": "daily"},
      {"name": "hydrochlorothiazide", "dose": "25 mg", "route": "PO", "frequency": "daily"},
    ],
    "instructions": {
      "follow_up": "RTC in 3 months or sooner if BP > 160/100.",
    },
    "metadata": {"patient_name": "Fiona Wells", "date_of_service": "2024-06-18", "provider_name": "Dr. Carl Wong"},
  }),
  ("eval_008", """DISCHARGE SUMMARY

Name: George Hill     Admit Date: 2024-07-02     Discharge Date: 2024-07-04
Attending: Dr. Yara Solis

Discharge Vitals: bp 118/74, heart rate 72, temperature 98.4F, resp rate 16, O2 sat 98 percent, wt 195 lbs.

Discharge Medications:
furosemide 40 mg oral once daily
spironolactone 25 mg PO daily
carvedilol 12.5 mg PO BID

Discharge Instructions:
Weigh yourself daily. If weight increases by more than 3 lbs in a day or 5 lbs in a week, call the clinic immediately. Fluid restriction to 1.5L/day.

Follow-Up:
Cardiology follow-up in 1 week.

Return Precautions:
Return to ED for shortness of breath at rest, leg swelling, or weight gain > 3 lbs/day.""",
  {
    "vitals": {"blood_pressure": "118/74", "heart_rate": "72", "temperature": "98.4",
               "respiratory_rate": "16", "oxygen_saturation": "98", "weight": "195 lbs"},
    "medications": [
      {"name": "furosemide", "dose": "40 mg", "route": "PO", "frequency": "daily"},
      {"name": "spironolactone", "dose": "25 mg", "route": "PO", "frequency": "daily"},
      {"name": "carvedilol", "dose": "12.5 mg", "route": "PO", "frequency": "BID"},
    ],
    "instructions": {
      "discharge_instructions": "Weigh yourself daily. If weight increases by more than 3 lbs in a day or 5 lbs in a week, call the clinic immediately. Fluid restriction to 1.5L/day.",
      "follow_up": "Cardiology follow-up in 1 week.",
      "return_precautions": "Return to ED for shortness of breath at rest, leg swelling, or weight gain > 3 lbs/day.",
    },
    "metadata": {"patient_name": "George Hill", "provider_name": "Dr. Yara Solis"},
  }),
  ("eval_009", """PATIENT: Helen Grant
Date of Service: 08/15/2024
CLINICIAN: Dr. Paulo Mendes

Vitals this visit: BP was 165/100, HR = 95, T 99.0 degrees, RR = 20, SpO2 = 95%, weight = 220 lbs.

Patient is on the following:
escitalopram 10 mg po qd
amlodipine 10mg once daily by mouth

Patient denies taking any blood thinners. Not on aspirin.

Instructions given:
Continue medications. Reduce salt intake.

Return to see me in 2 weeks.
Call immediately if BP is above 180 or you feel confused.""",
  {
    "vitals": {"blood_pressure": "165/100", "heart_rate": "95", "temperature": "99.0",
               "respiratory_rate": "20", "oxygen_saturation": "95", "weight": "220 lbs"},
    "medications": [
      {"name": "escitalopram", "dose": "10 mg", "route": "PO", "frequency": "daily"},
      {"name": "amlodipine", "dose": "10 mg", "route": "PO", "frequency": "daily"},
    ],
    "instructions": {
      "discharge_instructions": "Continue medications. Reduce salt intake.",
      "follow_up": "Return to see me in 2 weeks.",
      "return_precautions": "Call immediately if BP is above 180 or you feel confused.",
    },
    "metadata": {"patient_name": "Helen Grant", "date_of_service": "08/15/2024", "provider_name": "Dr. Paulo Mendes"},
  }),
  ("eval_010", """Follow up note - Ian Russo

Seen today for diabetes management. A1c improved.

Vitals today - 126/80 HR 70 Temp 98.0 RR 13 O2 100% weight: 190 pounds

medications: metformin 1000mg po bid, glipizide 5 mg oral once daily

No changes to medication list.
Continue current plan.
RTC in 3 months for repeat labs.
Go to ER immediately if blood sugar < 60 or > 400.""",
  {
    "vitals": {"blood_pressure": "126/80", "heart_rate": "70", "temperature": "98.0",
               "respiratory_rate": "13", "oxygen_saturation": "100", "weight": "190 lbs"},
    "medications": [
      {"name": "metformin", "dose": "1000 mg", "route": "PO", "frequency": "BID"},
      {"name": "glipizide", "dose": "5 mg", "route": "PO", "frequency": "daily"},
    ],
    "instructions": {
      "follow_up": "RTC in 3 months for repeat labs.",
      "return_precautions": "Go to ER immediately if blood sugar < 60 or > 400.",
    },
    "metadata": {},
  }),
  ("eval_011", """Patient: Julia Kim   DOS: 2024-09-03   MD: Dr. Anne Foster

subjective: patient feels well, no complaints.

objective:
BP: 119/76, Pulse: 66, Temperature: 97.8, Resp: 12, O2 Sat: 100%, Wt: 132 lbs

assessment & plan:
Continue pantoprazole 40mg PO daily and cetirizine 10mg PO daily.
Return for annual exam in 12 months.
No urgent concerns at this time.""",
  {
    "vitals": {"blood_pressure": "119/76", "heart_rate": "66", "temperature": "97.8",
               "respiratory_rate": "12", "oxygen_saturation": "100", "weight": "132 lbs"},
    "medications": [
      {"name": "pantoprazole", "dose": "40 mg", "route": "PO", "frequency": "daily"},
      {"name": "cetirizine", "dose": "10 mg", "route": "PO", "frequency": "daily"},
    ],
    "instructions": {
      "follow_up": "Return for annual exam in 12 months.",
    },
    "metadata": {"patient_name": "Julia Kim", "date_of_service": "2024-09-03", "provider_name": "Dr. Anne Foster"},
  }),
  ("eval_012", """EMERGENCY DEPARTMENT DISCHARGE NOTE

Patient: Kevin Nash
Date: 10/20/2024

Discharge VS: blood pressure 135/85 mmHg | heart rate 88 | temp 99.5F | resp 18 | sat 96% | weight not recorded

Rx at Discharge:
ciprofloxacin 500 mg oral BID x 5 days
ibuprofen 400 mg PO TID PRN pain

DISCHARGE INSTRUCTIONS: Take ciprofloxacin with food and water. Complete the full course. Ibuprofen for pain as needed, not to exceed 1200 mg/day. Avoid if stomach upset.

FOLLOW UP: Follow up with your primary care doctor in 3-5 days.

RETURN TO ED IF: fever worsens, unable to keep fluids down, or symptoms not improving in 48 hours.""",
  {
    "vitals": {"blood_pressure": "135/85", "heart_rate": "88", "temperature": "99.5",
               "respiratory_rate": "18", "oxygen_saturation": "96"},
    "medications": [
      {"name": "ciprofloxacin", "dose": "500 mg", "route": "PO", "frequency": "BID"},
      {"name": "ibuprofen", "dose": "400 mg", "route": "PO", "frequency": "TID"},
    ],
    "instructions": {
      "discharge_instructions": "Take ciprofloxacin with food and water. Complete the full course. Ibuprofen for pain as needed, not to exceed 1200 mg/day. Avoid if stomach upset.",
      "follow_up": "Follow up with your primary care doctor in 3-5 days.",
      "return_precautions": "fever worsens, unable to keep fluids down, or symptoms not improving in 48 hours.",
    },
    "metadata": {"patient_name": "Kevin Nash", "date_of_service": "10/20/2024"},
  }),
  ("eval_013", """Name: Laura Chen       Provider: Dr. Raj Kapoor      Visit: 2024-11-01

Quick visit for routine refills.

Vitals: 124/78, 74 bpm, 98.4°F, 14 breaths/min, 99% O2, 155 lb.

Continuing levothyroxine 75 mcg PO daily and simvastatin 40mg by mouth at bedtime.
Patient reports compliance. No new complaints.

Plan: refills provided, labs in 6 months, return PRN.""",
  {
    "vitals": {"blood_pressure": "124/78", "heart_rate": "74", "temperature": "98.4",
               "respiratory_rate": "14", "oxygen_saturation": "99", "weight": "155 lbs"},
    "medications": [
      {"name": "levothyroxine", "dose": "75 mcg", "route": "PO", "frequency": "daily"},
      {"name": "simvastatin", "dose": "40 mg", "route": "PO", "frequency": "QHS"},
    ],
    "instructions": {
      "follow_up": "refills provided, labs in 6 months, return PRN.",
    },
    "metadata": {"patient_name": "Laura Chen", "date_of_service": "2024-11-01", "provider_name": "Dr. Raj Kapoor"},
  }),
  ("eval_014", """Discharge paperwork

Mike Torres
11/15/2024
Discharge attending: Dr. Sasha Bell

Vitals on discharge: bp 145/90, HR 82, T 99.0F, breathing 16x/min, sats 95%, wt 230lbs.

Discharge Medications:
1. metformin 500mg orally twice daily with meals
2. enalapril 5mg once daily PO
3. aspirin 81 mg oral daily

INSTRUCTIONS: Continue metformin with meals. Take enalapril in the morning. Aspirin daily for heart protection. Monitor blood sugars at home.

Follow up with primary care in 2 weeks. Cardiology referral placed.

Call 911 or go to nearest ER for chest pain, trouble breathing, or sudden weakness.""",
  {
    "vitals": {"blood_pressure": "145/90", "heart_rate": "82", "temperature": "99.0",
               "respiratory_rate": "16", "oxygen_saturation": "95", "weight": "230 lbs"},
    "medications": [
      {"name": "metformin", "dose": "500 mg", "route": "PO", "frequency": "BID"},
      {"name": "enalapril", "dose": "5 mg", "route": "PO", "frequency": "daily"},
      {"name": "aspirin", "dose": "81 mg", "route": "PO", "frequency": "daily"},
    ],
    "instructions": {
      "discharge_instructions": "Continue metformin with meals. Take enalapril in the morning. Aspirin daily for heart protection. Monitor blood sugars at home.",
      "follow_up": "Follow up with primary care in 2 weeks. Cardiology referral placed.",
      "return_precautions": "Call 911 or go to nearest ER for chest pain, trouble breathing, or sudden weakness.",
    },
    "metadata": {"patient_name": "Mike Torres", "date_of_service": "11/15/2024", "provider_name": "Dr. Sasha Bell"},
  }),
  ("eval_015", """Patient: Nancy Rivera
Date of visit: December 2, 2024
Treating physician: Dr. Omar Farouk

Vitals: BP 110/68. HR 58. Temp 97.5 F. RR 11. O2 sat 100%. Weight 118 lbs.

On allopurinol 300 mg PO daily and colchicine 0.6 mg PO daily for gout management.
Not taking any OTC pain medications at this time.

Discharge plan:
Stay well hydrated. Avoid high-purine foods (red meat, shellfish, beer).

See Dr. Farouk in 4 weeks.

Come to ER if sudden severe joint pain, fever, or confusion.""",
  {
    "vitals": {"blood_pressure": "110/68", "heart_rate": "58", "temperature": "97.5",
               "respiratory_rate": "11", "oxygen_saturation": "100", "weight": "118 lbs"},
    "medications": [
      {"name": "allopurinol", "dose": "300 mg", "route": "PO", "frequency": "daily"},
      {"name": "colchicine", "dose": "0.6 mg", "route": "PO", "frequency": "daily"},
    ],
    "instructions": {
      "discharge_instructions": "Stay well hydrated. Avoid high-purine foods (red meat, shellfish, beer).",
      "follow_up": "See Dr. Farouk in 4 weeks.",
      "return_precautions": "Come to ER if sudden severe joint pain, fever, or confusion.",
    },
    "metadata": {"patient_name": "Nancy Rivera", "date_of_service": "December 2, 2024", "provider_name": "Dr. Omar Farouk"},
  }),
  ("eval_016", """2024-12-10
Patient: Oscar Bell
Seen by: Dr. Tina Shore

Vitals: 132/82 / 78 / 98.6 / 15 / 97% / 176lbs

MEDS: warfarin 5mg po qd, furosemide 20mg oral daily.
Patient denies missing any doses. INR therapeutic.

DISCHARGE INSTRUCTIONS: Continue warfarin daily. No grapefruit. Avoid alcohol. Soft diet.

FOLLOW UP: INR check and clinic visit in 1 week.

RETURN: Call if bleeding gums, blood in urine, or bruising increases.""",
  {
    "vitals": {"blood_pressure": "132/82", "heart_rate": "78", "temperature": "98.6",
               "respiratory_rate": "15", "oxygen_saturation": "97", "weight": "176 lbs"},
    "medications": [
      {"name": "warfarin", "dose": "5 mg", "route": "PO", "frequency": "daily"},
      {"name": "furosemide", "dose": "20 mg", "route": "PO", "frequency": "daily"},
    ],
    "instructions": {
      "discharge_instructions": "Continue warfarin daily. No grapefruit. Avoid alcohol. Soft diet.",
      "follow_up": "INR check and clinic visit in 1 week.",
      "return_precautions": "Call if bleeding gums, blood in urine, or bruising increases.",
    },
    "metadata": {"patient_name": "Oscar Bell", "date_of_service": "2024-12-10", "provider_name": "Dr. Tina Shore"},
  }),
  ("eval_017", """Patient name: Priya Sharma
Date: January 5, 2025
Physician: Dr. Lin Zhao

Vitals: Bp 120/75 Pulse: 68 Temp: 98.1F RR 13 O2 Sat 100% Wt 142lbs

Plan: add ramipril 5mg daily for microalbuminuria. Continue existing metformin 1000 mg PO BID.

patient to return in 1 month for repeat urine microalbumin.
ER if sudden swelling of face or throat (angioedema).""",
  {
    "vitals": {"blood_pressure": "120/75", "heart_rate": "68", "temperature": "98.1",
               "respiratory_rate": "13", "oxygen_saturation": "100", "weight": "142 lbs"},
    "medications": [
      {"name": "ramipril", "dose": "5 mg", "route": "PO", "frequency": "daily"},
      {"name": "metformin", "dose": "1000 mg", "route": "PO", "frequency": "BID"},
    ],
    "instructions": {
      "follow_up": "patient to return in 1 month for repeat urine microalbumin.",
      "return_precautions": "ER if sudden swelling of face or throat (angioedema).",
    },
    "metadata": {"patient_name": "Priya Sharma", "date_of_service": "January 5, 2025", "provider_name": "Dr. Lin Zhao"},
  }),
  ("eval_018", """CLINIC NOTE — BRIEF

Pt: Quinn Adams     Date: 02/12/2025     Provider: Dr. Sam Patel

V/S: 136/86 / 84 / 99.1 / 18 / 95% / 215 lbs

On doxycycline 100mg oral bid and montelukast 10mg PO qd.
Pt declines prednisone at this time.

Instructions: take doxycycline with full glass of water, avoid lying down for 30 min. Stay out of direct sunlight.

F/U: return in 3 weeks or sooner if rash appears.

Return to ED: if difficulty breathing, throat tightness, or severe skin reaction.""",
  {
    "vitals": {"blood_pressure": "136/86", "heart_rate": "84", "temperature": "99.1",
               "respiratory_rate": "18", "oxygen_saturation": "95", "weight": "215 lbs"},
    "medications": [
      {"name": "doxycycline", "dose": "100 mg", "route": "PO", "frequency": "BID"},
      {"name": "montelukast", "dose": "10 mg", "route": "PO", "frequency": "daily"},
    ],
    "instructions": {
      "discharge_instructions": "take doxycycline with full glass of water, avoid lying down for 30 min. Stay out of direct sunlight.",
      "follow_up": "return in 3 weeks or sooner if rash appears.",
      "return_precautions": "if difficulty breathing, throat tightness, or severe skin reaction.",
    },
    "metadata": {"patient_name": "Quinn Adams", "date_of_service": "02/12/2025", "provider_name": "Dr. Sam Patel"},
  }),
  ("eval_019", """Encounter date 3/1/2025
Patient: Rosa Mendez   Attending: Dr. Felix Grant

Chief complaint: shortness of breath follow-up.

VS 118/72 66 98.0 12 99 158

Medications continued:
- tiotropium 18 mcg inhaled once daily
- budesonide 160 mcg inhaled BID
- albuterol 90 mcg inhaled PRN

No prednisone burst at this time.

Follow up in pulmonary clinic 6 weeks.
Call clinic if rescue inhaler needed more than 2x per week.""",
  {
    "vitals": {"blood_pressure": "118/72", "heart_rate": "66", "temperature": "98.0",
               "respiratory_rate": "12", "oxygen_saturation": "99", "weight": "158 lbs"},
    "medications": [
      {"name": "tiotropium", "dose": "18 mcg", "route": "inhaled", "frequency": "daily"},
      {"name": "budesonide", "dose": "160 mcg", "route": "inhaled", "frequency": "BID"},
      {"name": "albuterol", "dose": "90 mcg", "route": "inhaled", "frequency": "PRN"},
    ],
    "instructions": {
      "follow_up": "Follow up in pulmonary clinic 6 weeks.",
      "return_precautions": "Call clinic if rescue inhaler needed more than 2x per week.",
    },
    "metadata": {"patient_name": "Rosa Mendez", "date_of_service": "3/1/2025", "provider_name": "Dr. Felix Grant"},
  }),
  ("eval_020", """Note created: April 1, 2025
Patient: Sam Young
Provider: Dr. Karen Lim

Vitals: Blood pressure 149/94. Heart rate 92. Temperature 98.9 degrees Fahrenheit. Respiratory rate 20 breaths per minute. Oxygen saturation 94 percent. Weight 250 lbs.

Current medication regimen:
clopidogrel 75 mg by mouth once daily
aspirin 81mg PO daily
atorvastatin 40mg oral at bedtime
metoprolol 100mg by mouth twice daily

Patient reports good compliance. Denies chest pain at rest.

Discharge instructions: Continue all medications. Follow up with cardiologist.

Follow up appointment: see cardiologist in 2 weeks.

Return precautions: Return to ED for chest pain, jaw pain, left arm pain, or sudden severe headache.""",
  {
    "vitals": {"blood_pressure": "149/94", "heart_rate": "92", "temperature": "98.9",
               "respiratory_rate": "20", "oxygen_saturation": "94", "weight": "250 lbs"},
    "medications": [
      {"name": "clopidogrel", "dose": "75 mg", "route": "PO", "frequency": "daily"},
      {"name": "aspirin", "dose": "81 mg", "route": "PO", "frequency": "daily"},
      {"name": "atorvastatin", "dose": "40 mg", "route": "PO", "frequency": "daily"},
      {"name": "metoprolol", "dose": "100 mg", "route": "PO", "frequency": "BID"},
    ],
    "instructions": {
      "discharge_instructions": "Continue all medications. Follow up with cardiologist.",
      "follow_up": "see cardiologist in 2 weeks.",
      "return_precautions": "Return to ED for chest pain, jaw pain, left arm pain, or sudden severe headache.",
    },
    "metadata": {"patient_name": "Sam Young", "date_of_service": "April 1, 2025", "provider_name": "Dr. Karen Lim"},
  }),
]  # end EVAL_DATA

for stem, note_text, label in EVAL_DATA:
    (NOTES_DIR / f"{stem}.txt").write_text(note_text.strip(), encoding="utf-8")
    (LABELS_DIR / f"{stem}.json").write_text(json.dumps(label, indent=2), encoding="utf-8")

print(f"Wrote {len(EVAL_DATA)} eval notes and labels.")
