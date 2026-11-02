"""Geometry-only audit. It does not read reference text or call a recognizer."""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from PIL import Image, ImageDraw

from evaluation.ocr_c2.segment_v3 import AMENDMENT_PATH, load_amendment, orient_once, segment_v3
from evaluation.public_amr_benchmark import sha


def summarize_layout(layout: dict, source_sha256: str) -> dict:
    owners = Counter(item.get("owner", "unresolved").split(":")[0] for item in layout.get("components") or [])
    return {
        "input_sha256": source_sha256,
        "width": layout["width"],
        "height": layout["height"],
        "orientation": layout.get("orientation"),
        "input_type": layout["input_type"],
        "column_detector_applied": layout["column_detector_applied"],
        "eligible": bool(layout.get("eligible")),
        "blank": bool(layout.get("blank")),
        "fallback": bool(layout.get("fallback")),
        "fallback_reason": layout.get("fallback_reason"),
        "reading_order_status": layout.get("reading_order_status"),
        "component_scale_px": layout.get("component_scale_px"),
        "component_count": len(layout.get("components") or []),
        "owner_counts": dict(sorted(owners.items())),
        "line_count": layout.get("line_count") or 0,
        "block_count": layout.get("block_count"),
        "regions": [
            {
                "id": region["id"],
                "order": region["order"],
                "kind": region["kind"],
                "block": region.get("block"),
                "x0": region["x0"], "y0": region["y0"], "x1": region["x1"], "y1": region["y1"],
                "certified_line": region.get("certified_line"),
                "fallback_reason": region.get("fallback_reason"),
            }
            for region in layout["regions"]
        ],
    }


def write_overlay(image: Image.Image, layout: dict, path: Path) -> None:
    """Private contact image. The caller chooses a directory outside git."""
    canvas = image.copy()
    draw = ImageDraw.Draw(canvas)
    for region in layout["regions"]:
        draw.rectangle((region["x0"], region["y0"], region["x1"] - 1, region["y1"] - 1), outline=(220, 30, 30))
    canvas.thumbnail((800, 800))
    path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(path, format="PNG")


def report_document(pages: list[dict]) -> dict:
    return {
        "pages": len(pages),
        "eligible_pages": sum(1 for page in pages if page["eligible"]),
        "fallback_reasons": [page["fallback_reason"] for page in pages],
    }


def amendment_report(documents: list[dict], word_crops: list[dict]) -> dict:
    amendment = load_amendment()
    eligible = [item["id"] for item in documents if item["pages"] and all(page["eligible"] for page in item["pages"] if not page["blank"]) and any(not page["blank"] for page in item["pages"])]
    return {
        "amendment_id": amendment["amendment_id"],
        "segmenter_id": amendment["segmenter_id"],
        "amendment_sha256": sha(AMENDMENT_PATH.read_bytes()),
        "protocol_sha256": amendment["protocol_sha256"],
        "outcome": amendment["outcome"],
        "gate": {
            "minimum_eligible_documents": 6,
            "eligible_documents": len(eligible),
            "eligible_ids": eligible,
            "passed": len(eligible) >= 6,
        },
        "documents": documents,
        "word_crops": {
            "count": len(word_crops),
            "column_detector_applied": sum(1 for item in word_crops if item["column_detector_applied"]),
            "single_region": sum(1 for item in word_crops if len(item["regions"]) == 1 and item["regions"][0]["kind"] == "word_crop"),
        },
        "line_claims": "none_certified",
        "verification": "structural_fallback_only",
    }


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n")


def main(argv: list[str] | None = None) -> int:
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--sanitized", type=Path, required=True)
    parser.add_argument("--private-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    from evaluation.ocr_c2.holdout import cohort_for
    from evaluation.ocr_c2.protocol import partition
    from evaluation.pr10_autoresearch import AMR_INTAKE, RX_TRAIN_DIR
    selection = json.loads(Path(AMR_INTAKE).read_text())
    by_id = {row["id"]: row for row in selection["all_records"]}
    source_root = Path(selection["source_root"])
    documents = []
    overlay_dir = args.private_dir / "overlays"
    for ident in cohort_for("screen", "amr"):
        pages = []
        for index, page in enumerate(by_id[ident]["pages"]):
            raw = (source_root / page["path"]).read_bytes()
            if sha(raw) != page["sha256"]:
                raise ValueError("OCR_C2_SOURCE_HASH")
            image = Image.open(__import__("io").BytesIO(raw))
            image.load()
            oriented, _orientation = orient_once(image)
            layout = segment_v3(oriented, "page")
            summary = summarize_layout(layout, page["sha256"])
            summary["page_index"] = index
            pages.append(summary)
            write_overlay(oriented, layout, overlay_dir / f"{ident}-p{index}.png")
        documents.append({"id": ident, "pages": pages})
    names = {row["image_name"]: row["original_sha256"] for row in partition()["rxhandbd"]["train"]}
    crops = []
    for name in cohort_for("screen", "rx"):
        raw = (RX_TRAIN_DIR / name).read_bytes()
        if sha(raw) != names[name]:
            raise ValueError("OCR_C2_SOURCE_HASH")
        image = Image.open(__import__("io").BytesIO(raw))
        image.load()
        layout = segment_v3(image, "word_crop")
        crops.append(summarize_layout(layout, names[name]))
    payload = amendment_report(documents, crops)
    _write(args.sanitized, payload)
    _write(args.private_dir / "geometry_report.json", payload)
    print(json.dumps({"eligible": payload["gate"]["eligible_documents"], "word_single": payload["word_crops"]["single_region"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
