"""One page of campaign-2 recognition. Transport is injected; nothing here calls Ollama."""
from __future__ import annotations

import io

from PIL import Image

from evaluation.ocr_c2.budget import BudgetExhausted, Ledger
from evaluation.ocr_c2.native import interpret_native_response, resolved_spec
from evaluation.ocr_c2.protocol import load_protocol
from evaluation.ocr_c2.segment import orient_page, segment_page
from evaluation.public_amr_benchmark import infer_image, sha


def _crop_bytes(image: Image.Image, region: dict) -> bytes:
    crop = image.crop((region["x0"], region["y0"], region["x1"], region["y1"]))
    buffer = io.BytesIO()
    crop.save(buffer, format="PNG")
    return infer_image(buffer.getvalue())


def run_page(
    image: Image.Image,
    candidate: str,
    transport,
    ledger: Ledger,
    request_prefix: str,
    expected_digest: str | None = None,
    parent: str | None = None,
) -> dict:
    spec = resolved_spec(candidate, parent)
    geometry = spec.get("geometry") or "page"
    oriented = orient_page(image)
    layout = segment_page(oriented, geometry if geometry in {"page", "bands", "lines"} else "page")
    budgets = load_protocol()["budgets"]
    page_remaining = budgets["per_page_seconds"]
    regions = []
    transcripts = []
    incomplete = False
    for region in layout["regions"]:
        prepared = _crop_bytes(oriented, region)
        deadline = min(budgets["per_call_seconds"], page_remaining, ledger.remaining())
        request_id = f"{request_prefix}-{region['order']}"
        try:
            allowed = ledger.begin(request_id, deadline)
        except BudgetExhausted:
            return {
                "status": "budget_blocked",
                "completed": False,
                "layout": layout,
                "regions": regions,
                "prediction": "\n".join(transcripts),
            }
        response = transport(prepared, candidate, allowed)
        ledger.finish(request_id, float(response.get("elapsed_seconds") or 0))
        page_remaining -= float(response.get("elapsed_seconds") or 0)
        interpreted = interpret_native_response(
            response, load_protocol()["model"]["tag"], expected_digest,
        )
        regions.append({
            "order": region["order"],
            "source": region,
            "crop_sha256": sha(prepared),
            "status": interpreted["status"],
            "raw_response": response.get("response"),
            "transcription": interpreted["transcription"],
        })
        transcripts.append(interpreted["transcription"] or "")
        if region.get("has_ink", True) and not interpreted["scored"]:
            incomplete = True
        if page_remaining <= 0 and region["order"] != layout["regions"][-1]["order"]:
            incomplete = True
            break
    status = "incomplete" if incomplete else "scored"
    return {
        "status": status,
        "completed": status == "scored",
        "layout": layout,
        "regions": regions,
        "prediction": "\n".join(transcripts),
    }
