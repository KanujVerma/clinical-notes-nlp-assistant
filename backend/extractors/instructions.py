import re
from typing import Any

_CATEGORIES = ["discharge_instructions", "follow_up", "return_precautions"]

_FALLBACK_TRIGGERS: dict[str, list[re.Pattern]] = {
    "follow_up": [
        re.compile(r"(?i)\bfollow[\s\-]?up\s+with\b"),
        re.compile(r"(?i)\bfollow[\s\-]?up\b"),
        re.compile(r"(?i)\bsee\s+your\b"),
        re.compile(r"(?i)\breturn\s+to\s+(clinic|office|your\s+doctor|primary\s+care|pcp)\b"),
        re.compile(r"(?i)\bschedule\s+an?\s+appointment\b"),
        re.compile(r"(?i)\bcall\s+your\s+doctor\b"),
    ],
    "return_precautions": [
        re.compile(r"(?i)\breturn\s+to\s+(the\s+)?(er|emergency|hospital)\b"),
        re.compile(r"(?i)\bgo\s+to\s+(the\s+)?(er|emergency)\b"),
        re.compile(r"(?i)\bseek\s+(medical|emergency|immediate)\b"),
        re.compile(r"(?i)\bcall\s+(911|if\b)"),
        re.compile(r"(?i)\bif\s+(you\s+)?(develop|experience|notice|have|feel)\b"),
        re.compile(r"(?i)\bworsening\b"),
        re.compile(r"(?i)\bseek\s+care\b"),
    ],
    "discharge_instructions": [
        re.compile(r"(?i)\btake\s+(your|all)\b"),
        re.compile(r"(?i)\bdrink\s+plenty\b"),
        re.compile(r"(?i)\brest\b"),
        re.compile(r"(?i)\bavoid\b"),
        re.compile(r"(?i)\bdo\s+not\b"),
        re.compile(r"(?i)\buse\s+your\b"),
        re.compile(r"(?i)\bcontinue\s+your\b"),
        re.compile(r"(?i)\bapply\b"),
    ],
}

_HEADER_RE = re.compile(r"(?i)^[ \t]*[A-Za-z\s/]+[ \t]*:[ \t]*$", re.MULTILINE)


def _split_sentences(text: str) -> list[tuple[str, int, int]]:
    sentences = []
    pattern = re.compile(r"(?<=[.!?;])\s+|\n+")
    last = 0
    for m in pattern.finditer(text):
        raw = text[last:m.start()]
        sent = re.sub(r"^[\s\-\u2022*\d.)\]]+", "", raw).strip()
        if sent:
            sentences.append((sent, last, m.start()))
        last = m.end()
    remaining = re.sub(r"^[\s\-\u2022*\d.)\]]+", "", text[last:]).strip()
    if remaining:
        sentences.append((remaining, last, len(text)))
    return sentences


def _classify_sentence(sent: str) -> "str | None":
    for cat in _CATEGORIES:
        for trigger in _FALLBACK_TRIGGERS[cat]:
            if trigger.search(sent):
                return cat
    return None


def _sub_classify_text(text: str, text_start: int, existing: dict[str, Any]) -> dict[str, Any]:
    found: dict[str, Any] = {}
    sentences = _split_sentences(text)
    i = 0
    while i < len(sentences):
        sent, s_start, s_end = sentences[i]
        cat = _classify_sentence(sent)
        if cat and cat not in existing and cat not in found:
            parts = [sent]
            j = i + 1
            while j < i + 3 and j < len(sentences):
                next_sent, _, _ = sentences[j]
                if _classify_sentence(next_sent) is not None:
                    break
                if _HEADER_RE.match(next_sent):
                    break
                parts.append(next_sent)
                j += 1
            value = " ".join(parts)
            abs_start = text_start + s_start
            last_included = sentences[j - 1] if j > i + 1 else sentences[i]
            abs_end = text_start + last_included[2]
            found[cat] = {
                "value": value,
                "span": [abs_start, abs_end],
                "source": "fallback",
                "confidence": 0.6,
            }
        i += 1
    return found


def extract_instructions(
    text: str,
    sections: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}

    # Primary: dedicated instruction sections
    for section in sections:
        cat = section["category"]
        if cat in _CATEGORIES and cat not in result:
            result[cat] = {
                "value": section["text"],
                "span": [section["start"], section["end"]],
                "source": "section",
                "confidence": 0.9,
            }

    # Secondary: sub-classify Plan and HPI sections
    for section in sections:
        if section["category"] in ("plan", "hpi") and len(result) < len(_CATEGORIES):
            text_start = section["end"] - len(section["text"])
            new = _sub_classify_text(section["text"], text_start, result)
            for cat, val in new.items():
                if cat not in result:
                    result[cat] = val

    # Fallback: sentence/keyword on full text (fills only missing categories)
    missing = [c for c in _CATEGORIES if c not in result]
    if not missing:
        return result

    found = _sub_classify_text(text, 0, result)
    for cat, val in found.items():
        if cat not in result:
            result[cat] = val

    return result
