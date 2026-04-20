export interface MedicationExplanation {
  name: string;        // display name (proper case)
  description: string; // ≤12 words, plain language
  commonUse: string;   // ≤10 words
  drugClass: string;   // 1–3 words
}

export const MEDICATION_EXPLANATIONS: Record<string, MedicationExplanation> = {
  metformin: {
    name: "Metformin",
    description: "Lowers blood glucose by reducing liver glucose output",
    commonUse: "Type 2 diabetes management",
    drugClass: "Biguanide",
  },
  lisinopril: {
    name: "Lisinopril",
    description: "Relaxes blood vessels by blocking ACE enzyme",
    commonUse: "High blood pressure, heart failure",
    drugClass: "ACE inhibitor",
  },
  atorvastatin: {
    name: "Atorvastatin",
    description: "Reduces LDL cholesterol by inhibiting liver enzyme",
    commonUse: "High cholesterol, heart disease prevention",
    drugClass: "Statin",
  },
  amlodipine: {
    name: "Amlodipine",
    description: "Relaxes blood vessel walls by blocking calcium channels",
    commonUse: "High blood pressure, chest pain",
    drugClass: "Calcium channel blocker",
  },
  metoprolol: {
    name: "Metoprolol",
    description: "Slows heart rate by blocking beta-adrenergic receptors",
    commonUse: "High blood pressure, heart failure, arrhythmia",
    drugClass: "Beta blocker",
  },
  omeprazole: {
    name: "Omeprazole",
    description: "Reduces stomach acid by blocking the proton pump",
    commonUse: "Acid reflux, GERD, peptic ulcer",
    drugClass: "Proton pump inhibitor",
  },
  albuterol: {
    name: "Albuterol",
    description: "Opens airways by relaxing bronchial smooth muscle",
    commonUse: "Asthma, COPD bronchospasm relief",
    drugClass: "Bronchodilator",
  },
  amoxicillin: {
    name: "Amoxicillin",
    description: "Kills bacteria by blocking cell wall synthesis",
    commonUse: "Bacterial infections (ear, respiratory, UTI)",
    drugClass: "Penicillin antibiotic",
  },
  sertraline: {
    name: "Sertraline",
    description: "Increases serotonin availability in the brain",
    commonUse: "Depression, anxiety, OCD, PTSD",
    drugClass: "SSRI",
  },
  gabapentin: {
    name: "Gabapentin",
    description: "Reduces nerve signal transmission in the brain",
    commonUse: "Neuropathic pain, seizures",
    drugClass: "Anticonvulsant",
  },
  levothyroxine: {
    name: "Levothyroxine",
    description: "Replaces or supplements thyroid hormone",
    commonUse: "Hypothyroidism",
    drugClass: "Thyroid hormone",
  },
  furosemide: {
    name: "Furosemide",
    description: "Removes excess fluid via the kidneys",
    commonUse: "Heart failure, edema, high blood pressure",
    drugClass: "Loop diuretic",
  },
  warfarin: {
    name: "Warfarin",
    description: "Prevents blood clots by inhibiting clotting factors",
    commonUse: "Atrial fibrillation, DVT, pulmonary embolism",
    drugClass: "Anticoagulant",
  },
  aspirin: {
    name: "Aspirin",
    description: "Reduces pain, inflammation, and platelet aggregation",
    commonUse: "Pain relief, fever, heart attack prevention",
    drugClass: "Salicylate / Antiplatelet",
  },
  ibuprofen: {
    name: "Ibuprofen",
    description: "Reduces pain and inflammation by blocking prostaglandins",
    commonUse: "Pain, fever, inflammation",
    drugClass: "NSAID",
  },
  acetaminophen: {
    name: "Acetaminophen",
    description: "Reduces pain and fever via central nervous system",
    commonUse: "Pain relief, fever reduction",
    drugClass: "Analgesic",
  },
  prednisone: {
    name: "Prednisone",
    description: "Suppresses immune response and reduces inflammation",
    commonUse: "Inflammation, autoimmune conditions, allergies",
    drugClass: "Corticosteroid",
  },
  hydrochlorothiazide: {
    name: "Hydrochlorothiazide",
    description: "Removes excess sodium and water via the kidneys",
    commonUse: "High blood pressure, edema",
    drugClass: "Thiazide diuretic",
  },
  carvedilol: {
    name: "Carvedilol",
    description: "Blocks beta and alpha receptors to reduce cardiac workload",
    commonUse: "Heart failure, high blood pressure",
    drugClass: "Beta blocker",
  },
  spironolactone: {
    name: "Spironolactone",
    description: "Blocks aldosterone to reduce fluid retention",
    commonUse: "Heart failure, edema, high blood pressure",
    drugClass: "Potassium-sparing diuretic",
  },
};
