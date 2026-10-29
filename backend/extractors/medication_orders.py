"""Conservative line-anchored medication-order extraction.

Only explicit dose-and-sig orders or directed medication actions are handled
here. This is a candidate generator, not a prescribing or clinical-validity
engine. It never infers a dose, route, action, or patient intent.
"""
from __future__ import annotations

import re
from typing import Any

# Keep digits, slashes and their original units intact. In particular,
# 0.05 is never interchangeable with 0.5, and mcg/hr is not mcg or mg.
_DOSE = re.compile(
    r"(?<![\w.])(?P<dose>\d+(?:\.\d+)?(?:/\d+(?:\.\d+)?)?\s*"
    r"(?:mcg(?:/hr)?|mg(?:/kg)?|mEq|units?|mL|g|puffs?|"
    r"tablets?|tabs?|capsules?|caps?|patch(?:es)?|sprays?|drops?))\b",
    re.IGNORECASE,
)
_ROUTE = re.compile(
    r"\b(?:subcutaneous|subq|sq|intravenous|iv|intramuscular|im|"
    r"transdermal|inhalation|inhaled|oral|po|sublingual|sl|"
    r"topical|intranasal|ophthalmic|otic|rectal|pr)\b", re.IGNORECASE,
)
_FREQUENCY = re.compile(
    r"\b(?:every\s+\d+\s+(?:hours?|days?|weeks?)|every\s+morning|"
    r"every\s+evening|once\s+daily|twice\s+daily|once\s+weekly|"
    r"twice\s+weekly|at\s+bedtime|nightly|at\s+night|"
    r"q\.?\s*\d+\s*h|q\.?\s*d\.?|"
    r"bid|tid|qid|qhs|qam|qpm|stat|daily|weekly|monthly|"
    r"as\s+needed|prn)\b",
    re.IGNORECASE,
)
_DURATION = re.compile(r"\bfor\s+\d+\s+(?:days?|weeks?|months?)\b", re.IGNORECASE)
_BULLET = re.compile(r"^\s*(?:[-*\u2022]\s*|\d{1,3}[.)]\s*)")
_LABEL = re.compile(
    r"^(?:prescription|discharge\s+med(?:s|ications?)|"
    r"home\s+med(?:s|ications?)|current\s+med(?:s|ications?)|"
    r"medications?|meds|rx)\s*:\s*", re.IGNORECASE,
)
_ACTION = re.compile(
    r"^(?P<verb>do\s+not\s+continue|discontinue|withhold|"
    r"continue|restart|initiate|administer|prescribe|"
    r"resume|start|begin|hold|stop|cease|give|take|use|"
    r"apply|inject|inhale)\s+", re.IGNORECASE,
)
_ACTIONS = {
    "do not continue": "stop",
    "discontinue": "stop",
    "stop": "stop",
    "cease": "stop",
    "hold": "hold",
    "withhold": "hold",
    "continue": "continue",
    "resume": "continue",
    "restart": "continue",
    "start": "start",
    "initiate": "start",
    "begin": "start",
}
# These introduce laboratory values, safety cautions, or narrative, not a
# patient-specific medication order. A dose token alone is never sufficient.
_NON_ORDER = re.compile(
    r"^(?:patient|blood|fasting|serum|hemoglobin|hematocrit|"
    r"platelet|glucose|systolic|diastolic|temperature|temp|"
    r"heart|pulse|respiratory|maximum|minimum|daily\s+dose|"
    r"dose|caution|warning|verify|confirm|do\s+not|avoid|"
    r"repeat|follow|return|monitor|recheck|check|taper|"
    r"pain\s+score|risk)\b", re.IGNORECASE,
)
_NAME = re.compile(r"[A-Za-z][A-Za-z0-9/-]*(?:\s+[A-Za-z][A-Za-z0-9/-]*){0,4}\Z")


def parse_order_line(line: str, offset: int = 0) -> dict[str, Any] | None:
    """Parse one explicitly structured order, preserving original text offsets.

    The anchor and short drug-name limit deliberately reject arbitrary prose.
    Other prose remains available to the existing medSpaCy fallback.
    """
    if not line or len(line) > 2000:
        return None
    cursor = 0
    whitespace = re.match(r"\s*", line)
    cursor += whitespace.end()
    bullet = _BULLET.match(line[cursor:])
    if bullet:
        cursor += bullet.end()
    label = _LABEL.match(line[cursor:])
    if label:
        cursor += label.end()

    body = line[cursor:]
    dose = _DOSE.search(body)
    if dose is None:
        return None

    before_dose = body[:dose.start()]
    action_match = _ACTION.match(before_dose)
    action = ""
    name_start = 0
    if action_match:
        action = _ACTIONS.get(
            " ".join(action_match.group("verb").casefold().split()), ""
        )
        name_start = action_match.end()

    name_piece = before_dose[name_start:]
    stripped = name_piece.strip()
    if not stripped or _NON_ORDER.match(stripped) or not _NAME.fullmatch(stripped):
        return None

    after_dose = body[dose.end():]
    route_match = _ROUTE.search(after_dose)
    freq_match = _FREQUENCY.search(after_dose)
    if not (action or route_match or freq_match or action_match):
        return None

    # Do not attach a dose to an unrelated later order in the same line.
    # Inline conjunctions with a second medication are handled separately
    # by the existing entity matcher.
    if re.search(r"\b(?:and|or)\b", stripped, re.IGNORECASE):
        return None

    frequency = freq_match.group().strip() if freq_match else ""
    prn = re.search(r"\bPRN\b", after_dose, re.IGNORECASE)
    as_needed = re.search(r"\bas\s+needed\b", after_dose, re.IGNORECASE)
    if prn and "prn" not in frequency.casefold():
        frequency = (frequency + " PRN").strip()
    elif as_needed and "as needed" not in frequency.casefold():
        frequency = (frequency + " as needed").strip()

    duration = _DURATION.search(after_dose)
    sig_end = dose.end()
    for hit in (route_match, freq_match, prn, as_needed, duration):
        if hit:
            sig_end = max(sig_end, dose.end() + hit.end())

    # Exact source span covers drug identity and supported sig fields, never
    # a whole page or an unrelated following sentence.
    relative_name = name_piece.find(stripped)
    start = offset + cursor + name_start + relative_name
    end = offset + cursor + sig_end
    return {
        "name": stripped.casefold(),
        "dose": dose.group("dose").strip(),
        "route": route_match.group().strip() if route_match else "",
        "frequency": frequency,
        "duration": duration.group().strip() if duration else "",
        "qualifier": "",
        "action": action,
        "span": [start, end],
        "source": "explicit_order",
        "confidence": 0.85,
    }


def parse_order_lines(text: str) -> list[dict[str, Any]]:
    """Extract independently occurring medication orders, including repeats."""
    if not text:
        return []
    entries: list[dict[str, Any]] = []
    for m in re.finditer(r"[^\r\n]+", text):
        candidate = parse_order_line(m.group(), m.start())
        if candidate is not None:
            entries.append(candidate)
    return entries
