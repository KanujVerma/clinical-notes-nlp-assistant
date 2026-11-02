"""Development cohorts only. Holdout and internal validation stay sealed."""
from __future__ import annotations

from evaluation.ocr_c2.holdout import HoldoutSealed, cohort_for, refuse_tuning_ids, sealed_ids


def development_ids(stage: str, dataset: str) -> list[str]:
    if stage not in {"screen", "confirm"}:
        raise HoldoutSealed("protected_stage")
    ids = cohort_for(stage, dataset)
    refuse_tuning_ids(ids)
    sealed = sealed_ids()
    if set(ids) & sealed["amr"] or set(ids) & sealed["rx"]:
        raise HoldoutSealed("sealed_id_in_open_stage")
    return ids
