import re
from typing import Any

_CATEGORIES = ["discharge_instructions", "follow_up", "return_precautions"]

_FALLBACK_TRIGGERS: dict[str, list[re.Pattern]] = {
    "follow_up": [
        re.compile(r"(?i)\bfollow[\s\-]?up\b"),
        re.compile(r"(?i)\bsee\s+(dr\.?|your\s+doctor|pcp)\b"),
        re.compile(r"(?i)\breturn\s+to\s+(clinic|office|pcp)\b"),
    ],
    "return_precautions": [
        re.compile(r"(?i)\breturn\s+to\s+(er|emergency|hospital)\b"),
        re.compile(r"(?i)\bcall\s+(if|when|the)\b"),
        re.compile(r"(?i)\bif\s+(you\s+)?(develop|experience|notice|have)\b"),
        re.compile(r"(?i)\bseek\s+(medical|immediate|emergency)\b"),
    ],
    "discharge_instructions": [
        re.compile(r"(?i)\btake\s+your\s+(medication|medicine)\b"),
        re.compile(r"(?i)\brest\s+for\b"),
        re.compile(r"(?i)\bavoid\s+(activity|lifting|exercise)\b"),
        re.compile(r"(?i)\bdo\s+not\b"),
    ],
}


def _sentence_split(text: str) -> list[tuple[str, int, int]]:
    sentences = []
    pattern = re.compile(r"(?<=[.!?])\s+")
    last = 0
    for m in pattern.finditer(text):
        sent = text[last:m.start()].strip()
        if sent:
            sentences.append((sent, last, m.start()))
        last = m.end()
    remaining = text[last:].strip()
    if remaining:
        sentences.append((remaining, last, len(text)))
    return sentences


def extract_instructions(
    text: str,
    sections: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}

    # Primary: section-scoped
    for section in sections:
        cat = section["category"]
        if cat in _CATEGORIES and cat not in result:
            result[cat] = {
                "value": section["text"],
                "span": [section["start"], section["end"]],
                "source": "section",
                "confidence": 0.9,
            }

    # Fallback: sentence/keyword (fills only missing categories)
    missing = [c for c in _CATEGORIES if c not in result]
    if not missing:
        return result

    for sent, start, end in _sentence_split(text):
        for cat in list(missing):
            for trigger in _FALLBACK_TRIGGERS[cat]:
                if trigger.search(sent):
                    result[cat] = {
                        "value": sent,
                        "span": [start, end],
                        "source": "fallback",
                        "confidence": 0.6,
                    }
                    missing.remove(cat)
                    break
        if not missing:
            break

    return result
