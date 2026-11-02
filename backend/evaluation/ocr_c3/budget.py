"""Append-only Vision and fresh-control ledger. The cap is 7,200 seconds."""
from __future__ import annotations

import json
from pathlib import Path

from evaluation.ocr_c3.protocol import load_protocol


class BudgetExhausted(RuntimeError):
    pass


class Ledger:
    def __init__(self, path: Path, cap_seconds: float | None = None):
        self.path = path
        self.cap_seconds = cap_seconds if cap_seconds is not None else load_protocol()["budgets"]["total_seconds"]
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.write_text("")

    def rows(self) -> list[dict]:
        if not self.path.exists():
            return []
        return [json.loads(line) for line in self.path.read_text().splitlines() if line.strip()]

    def charged(self) -> float:
        begins = {}
        finished = {}
        crashed = {}
        for row in self.rows():
            if row["event"] == "begin":
                begins[row["request_id"]] = row
            elif row["event"] == "finish":
                finished[row["request_id"]] = row
            elif row["event"] == "crash_charge":
                crashed[row["request_id"]] = row
        total = 0.0
        for request_id, began in begins.items():
            if request_id in finished:
                total += float(finished[request_id]["charged_seconds"])
            elif request_id in crashed:
                total += float(crashed[request_id]["charged_seconds"])
            else:
                total += float(began["deadline_seconds"])
        return total

    def remaining(self) -> float:
        return self.cap_seconds - self.charged()

    def _append(self, row: dict) -> None:
        with self.path.open("a") as handle:
            handle.write(json.dumps(row) + "\n")

    def begin(self, request_id: str, deadline_seconds: float) -> float:
        if any(row.get("request_id") == request_id for row in self.rows()):
            raise ValueError("OCR_C3_DUPLICATE_REQUEST")
        allowed = min(float(deadline_seconds), self.remaining())
        if allowed <= 0:
            raise BudgetExhausted("compute_budget_exhausted")
        self._append({
            "request_id": request_id,
            "event": "begin",
            "deadline_seconds": allowed,
            "charged_seconds": 0,
        })
        return allowed

    def finish(self, request_id: str, elapsed_seconds: float) -> None:
        self._open(request_id)
        self._append({
            "request_id": request_id,
            "event": "finish",
            "charged_seconds": max(0.0, float(elapsed_seconds)),
        })

    def recover_crashes(self) -> None:
        finished = {row["request_id"] for row in self.rows() if row["event"] == "finish"}
        recovered = {row["request_id"] for row in self.rows() if row["event"] == "crash_charge"}
        for row in self.rows():
            if row["event"] == "begin" and row["request_id"] not in finished and row["request_id"] not in recovered:
                self._append({
                    "request_id": row["request_id"],
                    "event": "crash_charge",
                    "charged_seconds": row["deadline_seconds"],
                })

    def _open(self, request_id: str) -> dict:
        found = [row for row in self.rows() if row["request_id"] == request_id and row["event"] == "begin"]
        if len(found) != 1:
            raise ValueError("OCR_C3_UNKNOWN_REQUEST")
        return found[0]
