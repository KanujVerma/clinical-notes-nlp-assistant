from typing import Any


def normalize_output(
    pipeline_version: str,
    vitals: dict[str, Any],
    medications: list[dict[str, Any]],
    instructions: dict[str, Any],
    metadata: dict[str, Any],
) -> dict[str, Any]:
    """Assemble the canonical extraction JSON."""
    return {
        "pipeline_version": pipeline_version,
        "vitals": vitals,
        "medications": medications,
        "instructions": instructions,
        "metadata": metadata,
    }
