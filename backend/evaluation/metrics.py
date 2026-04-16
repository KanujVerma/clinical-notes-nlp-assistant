from typing import Any


def compute_metrics(tp: int, fp: int, fn: int) -> dict[str, float]:
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) > 0 else 0.0
    return {"precision": round(precision, 4), "recall": round(recall, 4), "f1": round(f1, 4)}


def aggregate_metrics(
    vitals_tpfpfn: tuple,
    meds_tpfpfn: tuple,
    instructions_tpfpfn: tuple,
    metadata_tpfpfn: tuple,
) -> dict[str, Any]:
    categories = {
        "vitals": vitals_tpfpfn,
        "medications": meds_tpfpfn,
        "instructions": instructions_tpfpfn,
        "metadata": metadata_tpfpfn,
    }
    by_category = {cat: compute_metrics(*tpfpfn) for cat, tpfpfn in categories.items()}

    total_tp = sum(t[0] for t in categories.values())
    total_fp = sum(t[1] for t in categories.values())
    total_fn = sum(t[2] for t in categories.values())
    overall = compute_metrics(total_tp, total_fp, total_fn)

    return {"overall": overall, "by_category": by_category}
