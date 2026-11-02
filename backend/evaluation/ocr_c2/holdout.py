"""Final-holdout ids are readable only by the frozen evaluator."""
from __future__ import annotations

from evaluation.ocr_c2.protocol import partition
from evaluation.pr10_autoresearch import screening_selection, work_items


class HoldoutSealed(RuntimeError):
    pass


def sealed_ids(manifest: dict | None = None) -> dict[str, set[str]]:
    manifest = manifest or partition()
    amr = {row["id"] for row in manifest["amr"]["untouched_holdout"]}
    rx = {
        row["image_name"] for row in manifest["rxhandbd"]["official_test"]
        if row["role"] == "untouched_official_test"
    }
    return {"amr": amr, "rx": rx}


def cohort_for(stage: str, dataset: str, manifest: dict | None = None, freeze: dict | None = None) -> list[str]:
    manifest = manifest or partition()
    sealed = sealed_ids(manifest)
    if stage == "screen":
        selected = screening_selection(manifest)
        ids = selected["amr_ids"] if dataset == "amr" else selected["rx_image_names"]
    elif stage == "confirm":
        ids = work_items(manifest, "confirm", dataset)
    elif stage == "internal_validation":
        if dataset != "rx":
            raise ValueError("OCR_C2_VALIDATION_DATASET")
        ids = [
            row["image_name"] for row in manifest["rxhandbd"]["train"]
            if row["role"] == "internal_validation"
        ]
    elif stage == "holdout":
        if not freeze or freeze.get("state") != "holdout" or not freeze.get("finalist"):
            raise HoldoutSealed("holdout_not_frozen")
        ids = sorted(sealed["amr"] if dataset == "amr" else sealed["rx"])
    else:
        raise ValueError("OCR_C2_STAGE")
    if stage != "holdout" and set(ids) & sealed[dataset if dataset in sealed else "amr"]:
        raise HoldoutSealed("sealed_id_in_open_stage")
    if stage != "holdout" and dataset == "rx" and set(ids) & sealed["rx"]:
        raise HoldoutSealed("sealed_id_in_open_stage")
    return list(ids)


def refuse_tuning_ids(ids: list[str], manifest: dict | None = None) -> None:
    sealed = sealed_ids(manifest)
    if set(ids) & sealed["amr"] or set(ids) & sealed["rx"]:
        raise HoldoutSealed("tuning_requested_holdout")
