"""Screen entry. It refuses to load a case until the reviewed head matches."""
from __future__ import annotations


def run_screen(checkpoint: dict, head: str, load_case) -> dict:
    from evaluation.ocr_c3.controller import require_reviewed
    require_reviewed(checkpoint, head)
    return load_case()


def confirmation_fits(remaining_seconds: float, seconds_per_page: float, pages: int, margin: float = 1.25) -> bool:
    if pages <= 0 or seconds_per_page < 0:
        return False
    return remaining_seconds >= seconds_per_page * pages * margin
