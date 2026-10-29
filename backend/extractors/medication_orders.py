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
    r"\b(?:every\s+\d+\s+(?:minutes?|hours?|days?|weeks?)|every\s+morning|"
    r"every\s+evening|once\s+daily|twice\s+daily|once\s+weekly|"
    r"twice\s+weekly|at\s+bedtime|bedtime|nightly|at\s+night|"
    r"q\.?\s*\d+\s*h|q\.?\s*d\.?|"
    r"bid|tid|qid|qhs|qam|qpm|stat|daily|weekly|monthly|"
    r"as\s+needed|prn)\b",
    re.IGNORECASE,
)
_DURATION = re.compile(
    r"\bfor\s+\d+\s+(?:more\s+)?(?:days?|weeks?|months?)\b",
    re.IGNORECASE,
)
_BULLET = re.compile(r"^\s*(?:[-*\u2022]\s*|\d{1,3}[.)]\s*)")
_LABEL = re.compile(
    r"^(?:prescription|discharge\s+med(?:s|ications?)|"
    r"home\s+med(?:s|ications?)|current\s+med(?:s|ications?)|"
    r"medications?|meds|rx)\s*:\s*"
    r"|^discharge\s+meds?\s+(?=[A-Za-z])", re.IGNORECASE,
)
_ACTION = re.compile(
    r"^(?P<verb>continue\s+to\s+(?:hold|withhold)|do\s+not\s+continue|discontinue|withhold|"
    r"continue|restart|initiate|administer|prescribe|"
    r"resume|start|begin|hold|stop|cease|give|take|use|"
    r"apply|inject|inhale)\s+", re.IGNORECASE,
)
_ACTIONS = {
    "continue to hold": "hold",
    "continue to withhold": "hold",
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
    r"^(?:no|not|never|denies?|denied|without|formerly|previously|"
    r"historical|history\s+of|stopped\s+taking|is\s+not\s+taking|"
    r"patient|blood|fasting|serum|hemoglobin|hematocrit|"
    r"platelet|glucose|systolic|diastolic|temperature|temp|"
    r"heart|pulse|respiratory|maximum|minimum|daily\s+dose|"
    r"dose|caution|warning|verify|confirm|do\s+not|avoid|"
    r"repeat|follow|return|monitor|recheck|check|taper|"
    r"pain\s+score|risk)\b", re.IGNORECASE,
)
_NAME = re.compile(r"[A-Za-z][A-Za-z0-9/-]*(?:\s+[A-Za-z][A-Za-z0-9/-]*){0,4}\Z")
_NESTED_ACTION = re.compile(
    r"^(?:to\s+)?(?:continue|hold|withhold|start|stop|discontinue|"
    r"resume|restart|initiate|begin|prescribe|cease)\b", re.IGNORECASE,
)


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
    # More than one drug-strength dose on a single clause is ambiguous.
    # "250/50 mcg inhaled 1 puff" is an exception: the second amount is
    # administration quantity, not a second drug. Only accept it when the
    # intervening text is an explicit route (no other drug/conjunction).
    doses = list(_DOSE.finditer(body))
    if not doses:
        return None
    dose = doses[0]
    for previous, extra in zip(doses, doses[1:]):
        middle = body[previous.end():extra.start()]
        administration_unit = re.search(
            r"\b(?:puffs?|tablets?|tabs?|capsules?|caps?|sprays?|drops?|patch(?:es)?)\b",
            extra.group("dose"), re.IGNORECASE,
        )
        if not administration_unit or re.sub(_ROUTE, "", middle).strip():
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
    # The route and the schedule can appear BEFORE the strength:
    # "Metformin PO BID 500 mg". Strip only explicit trailing tokens,
    # preserving the original text coordinate and medication-name start.
    # Reject ambiguous conflicts rather than choosing a guessed sig.
    pre_route = None
    pre_freq = None
    for _ in range(2):
        trailing = name_piece.rstrip()
        suffixes = []
        for kind, pattern in (("route", _ROUTE), ("frequency", _FREQUENCY)):
            suffixes.extend(
                (match.start(), kind, match)
                for match in pattern.finditer(trailing)
                if match.end() == len(trailing)
            )
        if not suffixes:
            break
        _, kind, match = max(suffixes, key=lambda item: item[0])
        if kind == "route":
            if pre_route is not None:
                return None
            pre_route = match.group()
        else:
            if pre_freq is not None:
                return None
            pre_freq = match.group()
        name_piece = trailing[:match.start()]
    stripped = name_piece.strip()
    if (not stripped or _NON_ORDER.match(stripped)
            or _NESTED_ACTION.match(stripped)
            or _ROUTE.search(stripped)
            or _FREQUENCY.search(stripped)
            or not _NAME.fullmatch(stripped)):
        return None

    after_dose = body[dose.end():]
    route_match = _ROUTE.search(after_dose)
    freq_match = _FREQUENCY.search(after_dose)
    if (pre_route and route_match
            and pre_route.casefold() != route_match.group().casefold()):
        return None
    if (pre_freq and freq_match
            and pre_freq.casefold() != freq_match.group().casefold()):
        return None
    if not (action or pre_route or pre_freq or route_match or freq_match or action_match):
        return None

    # Do not attach a dose to an unrelated later order in the same line.
    # Inline conjunctions with a second medication are handled separately
    # by the existing entity matcher.
    if re.search(r"\b(?:and|or)\b", stripped, re.IGNORECASE):
        return None

    frequency = freq_match.group().strip() if freq_match else (pre_freq or "")
    prn = re.search(r"\bPRN\b", after_dose, re.IGNORECASE)
    as_needed = re.search(r"\bas\s+needed\b", after_dose, re.IGNORECASE)
    if prn and "prn" not in frequency.casefold():
        frequency = (frequency + " PRN").strip()
    elif as_needed and "as needed" not in frequency.casefold():
        frequency = (frequency + " as needed").strip()

    # The PRN indication is reviewer-visible information, not just a word
    # following a dosing frequency. Preserve only explicitly stated words.
    qualifier = ""
    qualifier_end = 0
    if prn:
        reason = re.match(
            r"\s+([A-Za-z][A-Za-z0-9/-]*(?:\s+[A-Za-z][A-Za-z0-9/-]*){0,3})",
            after_dose[prn.end():],
        )
        # Reason formatting may include repeated spaces or tabs. Work from
        # match offsets in the untouched source, not a .find() of the
        # normalized string, or the end coordinate truncates evidence.
        words = list(re.finditer(r"[A-Za-z][A-Za-z0-9/-]*", reason.group(1))) if reason else []
        stop_at = next(
            (idx for idx, token in enumerate(words)
             if token.group().casefold() in (
                 "up", "if", "when", "unless", "until", "before", "after"
             )),
            len(words),
        )
        words = words[:stop_at]
        if words:
            qualifier = "PRN " + " ".join(token.group() for token in words)
            qualifier_end = prn.end() + reason.start(1) + words[-1].end()
        else:
            qualifier = "PRN"
            qualifier_end = prn.end()
    elif as_needed:
        reason = re.match(
            r"\s+for\s+([A-Za-z][A-Za-z0-9/-]*(?:\s+[A-Za-z][A-Za-z0-9/-]*){0,3})",
            after_dose[as_needed.end():],
        )
        if reason:
            qualifier = "as needed for " + reason.group(1)
            qualifier_end = as_needed.end() + reason.end()
        else:
            qualifier = "as needed"
            qualifier_end = as_needed.end()

    duration = _DURATION.search(after_dose)
    sig_end = max(item.end() for item in doses)
    for hit in (route_match, freq_match, prn, as_needed, duration):
        if hit:
            sig_end = max(sig_end, dose.end() + hit.end())
    if qualifier_end:
        sig_end = max(sig_end, dose.end() + qualifier_end)

    # Exact source span covers drug identity and supported sig fields, never
    # a whole page or an unrelated following sentence.
    relative_name = name_piece.find(stripped)
    start = offset + cursor + name_start + relative_name
    end = offset + cursor + sig_end
    return {
        "name": stripped.casefold(),
        "dose": dose.group("dose").strip(),
        "route": (route_match.group().strip() if route_match else
                  pre_route.strip() if pre_route else ""),
        "frequency": frequency,
        "duration": duration.group().strip() if duration else "",
        "qualifier": qualifier,
        "action": action,
        "span": [start, end],
        "source": "explicit_order",
        "confidence": 0.85,
    }


# Split on clear sentence/semicolon boundaries, never the decimal in 0.5.
# An ambiguous multiple-dose clause deliberately falls through to medSpaCy.
_CLAUSE_BREAK = re.compile(r";\s*|(?<!\d)[.!?](?!\d)\s+")


def parse_order_lines(text: str) -> list[dict[str, Any]]:
    """Extract independent, anchored source clauses including repeated drugs."""
    if not text:
        return []
    entries: list[dict[str, Any]] = []
    for line in re.finditer(r"[^\r\n]+", text):
        value = line.group()
        start = 0
        for boundary in _CLAUSE_BREAK.finditer(value):
            candidate = parse_order_line(value[start:boundary.start()], line.start() + start)
            if candidate is not None:
                entries.append(candidate)
            start = boundary.end()
        candidate = parse_order_line(value[start:], line.start() + start)
        if candidate is not None:
            entries.append(candidate)
    return entries
