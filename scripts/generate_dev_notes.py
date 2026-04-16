#!/usr/bin/env python3
# scripts/generate_dev_notes.py
"""
Generate 50 synthetic clinical notes for dev/demo use.
All data is entirely synthetic — no real patient information.
"""
import os, random
from pathlib import Path

random.seed(42)

OUT_DIR = Path(__file__).parent.parent / "data" / "dev" / "notes"
OUT_DIR.mkdir(parents=True, exist_ok=True)

NAMES = ["John Smith", "Maria Garcia", "James Lee", "Sarah Johnson", "Robert Brown",
         "Emily Davis", "Michael Wilson", "Jennifer Taylor", "William Anderson", "Lisa Martinez"]
PROVIDERS = ["Dr. Alice Chen", "Dr. Robert Evans", "Dr. Priya Patel", "Dr. Mark Torres"]
MEDS = [
    ("lisinopril", ["5 mg", "10 mg", "20 mg"], "PO", "daily"),
    ("metformin", ["500 mg", "1000 mg"], "PO", "BID"),
    ("atorvastatin", ["10 mg", "20 mg", "40 mg"], "PO", "daily"),
    ("albuterol", ["2.5 mg", "90 mcg"], "inhaled", "PRN"),
    ("omeprazole", ["20 mg", "40 mg"], "PO", "QHS"),
    ("amoxicillin", ["500 mg", "875 mg"], "PO", "TID"),
    ("amlodipine", ["5 mg", "10 mg"], "PO", "daily"),
    ("metoprolol", ["25 mg", "50 mg"], "PO", "BID"),
    ("sertraline", ["50 mg", "100 mg"], "PO", "daily"),
    ("gabapentin", ["300 mg", "600 mg"], "PO", "TID"),
]
NOTE_TYPES = ["discharge", "followup", "progress"]
HEADER_STYLES = {
    "discharge_instructions": ["DISCHARGE INSTRUCTIONS:", "Discharge Instructions:", "DISCHARGE INSTRUCTIONS", "D/C Instructions:"],
    "follow_up": ["FOLLOW UP:", "Follow-Up:", "FOLLOW-UP:", "Follow Up Instructions:"],
    "return_precautions": ["RETURN PRECAUTIONS:", "Return Precautions:", "PRECAUTIONS:"],
}
FOLLOW_UPS = [
    "Follow up with PCP in {days} weeks.",
    "Return to clinic in {days} days.",
    "See Dr. {provider_last} in {days} weeks for re-evaluation.",
]
RETURN_PREC = [
    "Return to ED if fever > 101.5F, chest pain, or shortness of breath.",
    "Call the clinic if symptoms worsen or if you develop new symptoms.",
    "Go to the ER immediately if you experience severe chest pain or difficulty breathing.",
]
DISCHARGE_INSTRS = [
    "Take all medications as prescribed. Rest and avoid strenuous activity for {days} days.",
    "Follow a low-sodium diet. Take medications with food. Avoid alcohol.",
    "Continue current medications. Monitor blood pressure daily. Record readings.",
]


def random_bp():
    systolic = random.randint(110, 160)
    diastolic = random.randint(65, 95)
    return f"{systolic}/{diastolic}"


def random_vitals(style="labeled"):
    bp = random_bp()
    hr = random.randint(58, 105)
    temp = round(random.uniform(97.4, 99.2), 1)
    rr = random.randint(12, 20)
    spo2 = random.randint(94, 100)
    wt = random.randint(120, 240)
    if style == "labeled":
        return (f"BP: {bp}. HR: {hr} bpm. Temp: {temp}F. RR: {rr}. "
                f"SpO2: {spo2}%. Wt: {wt} lbs.")
    elif style == "abbreviated":
        return f"BP {bp} HR {hr} T {temp} RR {rr} O2 {spo2}% Wt {wt}#"
    else:
        return (f"Blood pressure {bp} mmHg, heart rate {hr} beats/min, "
                f"temperature {temp} degrees F, respirations {rr}/min, "
                f"oxygen saturation {spo2}% on room air, weight {wt} lbs.")


def random_meds(count=None):
    n = count or random.randint(1, 4)
    chosen = random.sample(MEDS, min(n, len(MEDS)))
    lines = []
    for name, doses, route, freq in chosen:
        dose = random.choice(doses)
        lines.append(f"- {name} {dose} {route} {freq}")
    return "\n".join(lines)


def random_negation():
    if random.random() < 0.3:
        neg_med = random.choice(MEDS)[0]
        return f"\nPatient denies use of {neg_med}. Not currently taking {neg_med}.\n"
    return ""


def make_note(i: int) -> str:
    note_type = random.choice(NOTE_TYPES)
    name = random.choice(NAMES)
    provider = random.choice(PROVIDERS)
    provider_last = provider.split()[-1]
    days = random.randint(1, 4) * 7
    vitals_style = random.choice(["labeled", "abbreviated", "prose"])
    dis_hdr = random.choice(HEADER_STYLES["discharge_instructions"])
    fu_hdr = random.choice(HEADER_STYLES["follow_up"])
    rp_hdr = random.choice(HEADER_STYLES["return_precautions"])

    header = f"Patient: {name}\nDate of Service: 2024-{random.randint(1,12):02d}-{random.randint(1,28):02d}\nProvider: {provider}\n\n"
    vitals_section = f"Vitals:\n{random_vitals(vitals_style)}\n\n"
    meds_section = f"Medications:\n{random_meds()}{random_negation()}\n"

    if note_type == "discharge":
        body = (
            f"{dis_hdr}\n"
            f"{random.choice(DISCHARGE_INSTRS).format(days=days // 7)}\n\n"
            f"{fu_hdr}\n"
            f"{random.choice(FOLLOW_UPS).format(days=days // 7, provider_last=provider_last)}\n\n"
            f"{rp_hdr}\n"
            f"{random.choice(RETURN_PREC)}\n"
        )
    elif note_type == "followup":
        body = (
            f"Patient presents for follow-up. Doing well overall.\n\n"
            f"{fu_hdr}\n"
            f"{random.choice(FOLLOW_UPS).format(days=days // 7, provider_last=provider_last)}\n\n"
            f"{rp_hdr}\n"
            f"{random.choice(RETURN_PREC)}\n"
        )
    else:
        body = (
            f"Brief progress note. Patient stable.\n\n"
            f"Plan: Continue current management. {random.choice(FOLLOW_UPS).format(days=days // 7, provider_last=provider_last)}\n"
        )

    return header + vitals_section + meds_section + "\n" + body


if __name__ == "__main__":
    for i in range(1, 51):
        note = make_note(i)
        path = OUT_DIR / f"dev_{i:03d}.txt"
        path.write_text(note, encoding="utf-8")
    print(f"Generated 50 notes in {OUT_DIR}")
