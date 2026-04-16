import json
from datetime import datetime, timezone
from typing import Any


def build_report(
    pipeline_version: str,
    overall: dict,
    by_category: dict,
    per_note: list[dict],
) -> dict[str, Any]:
    return {
        "run_at": datetime.now(timezone.utc).isoformat(),
        "pipeline_version": pipeline_version,
        "overall": overall,
        "by_category": by_category,
        "per_note": per_note,
    }


def print_summary(report: dict) -> None:
    ov = report["overall"]
    print("\n" + "=" * 60)
    print(f"  Clinical NLP Evaluation — pipeline v{report['pipeline_version']}")
    print("=" * 60)
    print(f"  {'Category':<20} {'Precision':>10} {'Recall':>10} {'F1':>10}")
    print("  " + "-" * 54)
    for cat, m in report["by_category"].items():
        print(f"  {cat:<20} {m['precision']:>10.3f} {m['recall']:>10.3f} {m['f1']:>10.3f}")
    print("  " + "-" * 54)
    print(f"  {'OVERALL':<20} {ov['precision']:>10.3f} {ov['recall']:>10.3f} {ov['f1']:>10.3f}")
    print("=" * 60)
    print(f"  Notes evaluated: {len(report['per_note'])}")
    print()
