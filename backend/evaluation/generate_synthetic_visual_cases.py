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

from PIL import Image, ImageDraw, ImageFont


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
            {"name": "Warfarin", "dose": "2.5 mg", "route": "PO", "frequency": "daily"},
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
            {"name": "aspirin", "dose": "81 mg", "route": "", "frequency": ""},
        ],
        "expected_vitals": [],
    },
]


def make_printed_image(lines: list[str], degraded: bool) -> Image.Image:
    width, height = 1200, 290
    img = Image.new("RGB", (width, height), (250, 250, 250))
    draw = ImageDraw.Draw(img)
    font = ImageFont.load_default()
    for index, line in enumerate(lines):
        draw.text((40, 30 + index * 50), line, fill=(10, 10, 10), font=font)
    # Make the bundled Pillow default font legible on a model input.
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


def generate(output_dir: Path) -> Path:
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    image_dir = output_dir / "images"
    image_dir.mkdir(exist_ok=True)
    cases = []
    for fixture in CASES:
        case_id = fixture["id"]
        image_path = image_dir / f"{case_id}.png"
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
        "dataset_id": "synthetic_printed_visual_ocr_development_v1",
        "synthetic_only": True,
        "annotation_status": "synthetic_generator_ground_truth",
        "cases": cases,
        "limitations": [
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
    args = parser.parse_args()
    print(generate(args.output))


if __name__ == "__main__":
    main()
