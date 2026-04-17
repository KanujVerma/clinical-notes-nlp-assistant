"""
Medication extraction.
Strategy: structured line parser on medications sections -> medSpaCy prose fallback.
Prototype vocabulary -- not a production drug-normalization system.
"""
import re
import json
import os
from typing import Any

_VOCAB_PATH = os.path.join(os.path.dirname(__file__), "patterns", "medications.json")

# -- Dose -----------------------------------------------------------------------
_DOSE_RE = re.compile(
    r"(\d+(?:\.\d+)?\s*"
    r"(?:mg|mcg|g|ml|units?|meq|puffs?|tablets?|tabs?|capsules?|cap|patch|spray|drops))",
    re.IGNORECASE,
)

# -- Route ----------------------------------------------------------------------
_ROUTE_RE = re.compile(
    r"\b(PO|IV|IM|SQ|subq|subcutaneous|inhaled|inhalation|topical|sublingual|SL|PR|"
    r"transdermal|intranasal|ophthalmic|otic|rectal|oral)\b",
    re.IGNORECASE,
)

# -- Frequency ------------------------------------------------------------------
_FREQ_RE = re.compile(
    r"\b(once\s+daily|twice\s+daily|"
    r"every\s+\d+\s+hours?|"
    r"once\s+weekly|twice\s+weekly|"
    r"BID|TID|QID|QHS|QAM|QPM|QD|"
    r"daily|q\.?d\.?|"
    r"q\d+h|"
    r"PRN|as\s+needed|"
    r"at\s+bedtime|bedtime|"
    r"weekly|monthly)\b",
    re.IGNORECASE,
)

# -- Reject patterns (guard 3) --------------------------------------------------
_REJECT_DATE = re.compile(
    r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\b|\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4}",
    re.IGNORECASE,
)
_REJECT_ICD = re.compile(r"\b[A-Z]\d{2,3}\.?\d*\b")
_REJECT_PROSE = re.compile(
    r"^(return\s+to|follow[\s\-]?up|avoid|drink|if\s+you|go\s+to|call|seek|"
    r"use\s+the|take\s+all|continue\s+medications?|no\s+(home\s+)?meds?|"
    r"see\s+med|nkda|allergies?)",
    re.IGNORECASE,
)

_nlp = None


def _get_nlp():
    global _nlp
    if _nlp is not None:
        return _nlp
    import sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
    from config import Config
    import medspacy
    from medspacy.target_matcher import TargetRule
    try:
        nlp = medspacy.load(Config.SPACY_MODEL, disable=["parser"])
    except OSError:
        if Config.SPACY_MODEL == "en_core_web_sm":
            raise
        import warnings
        warnings.warn(f"Model {Config.SPACY_MODEL!r} not found, falling back to en_core_web_sm")
        nlp = medspacy.load("en_core_web_sm", disable=["parser"])
    with open(_VOCAB_PATH) as f:
        vocab: list[str] = json.load(f)
    target_matcher = nlp.get_pipe("medspacy_target_matcher")
    rules = [TargetRule(name, "MEDICATION") for name in vocab]
    target_matcher.add(rules)
    _nlp = nlp
    return _nlp


def _is_rejected(line: str) -> bool:
    """Return True if this line should not be treated as a medication entry."""
    stripped = line.strip()
    if not stripped:
        return True
    # Guard 1: no dose/route/freq token at all
    has_dose = bool(_DOSE_RE.search(stripped))
    has_route = bool(_ROUTE_RE.search(stripped))
    has_freq = bool(_FREQ_RE.search(stripped))
    if not has_dose and not has_route and not has_freq:
        return True
    # Guard 2: entirely uppercase AND no dose/sig structure
    if stripped == stripped.upper() and not has_dose and not has_route and not has_freq:
        return True
    # Guard 3: matches non-medication reject patterns
    if _REJECT_DATE.search(stripped):
        return True
    if _REJECT_ICD.search(stripped):
        return True
    if _REJECT_PROSE.match(stripped):
        return True
    return False


def _parse_line(line: str, char_offset: int) -> "dict[str, Any] | None":
    """
    Parse a single medication line into a med dict.
    Returns None if the line is rejected or cannot be parsed.
    """
    # Strip leading bullets, numbers, hyphens, whitespace
    clean = re.sub(r"^[\s\-\u2022*\d.)\]]+", "", line).strip()
    if _is_rejected(clean):
        return None

    dm = _DOSE_RE.search(clean)
    rm = _ROUTE_RE.search(clean)
    fm = _FREQ_RE.search(clean)

    # Extract name: words before the first dose/route/freq token
    first_token_pos = min(
        (m.start() for m in [dm, rm, fm] if m),
        default=len(clean),
    )
    name_raw = clean[:first_token_pos].strip()
    # Remove trailing punctuation from name
    name = re.sub(r"[\s,;:]+$", "", name_raw).strip()
    if not name:
        return None

    # Build frequency (just the core dosing interval, no appendages)
    freq = fm.group(1) if fm else ""

    # Duration: "for N days/weeks/months" anywhere after frequency (or after dose if no freq)
    search_start = fm.end() if fm else (dm.end() if dm else 0)
    duration = ""
    duration_match = re.search(
        r"\bfor\s+(?:\d+\s+)?(?:more\s+)?\d*\s*(?:days?|weeks?|months?)\b",
        clean[search_start:],
        re.IGNORECASE,
    )
    if duration_match:
        duration = duration_match.group().strip()

    # PRN + qualifier: collect "PRN" and whatever reason phrase follows (up to 4 words)
    qualifier = ""
    prn_match = re.search(r"\bPRN\b", clean[search_start:], re.IGNORECASE)
    if prn_match:
        prn_pos = search_start + prn_match.start()
        after_prn = clean[prn_pos + len("PRN"):].strip()
        # Grab up to 4 words as the qualifier reason (stop at punctuation)
        reason_match = re.match(r"((?:\w+\s*){0,4})", after_prn)
        reason = reason_match.group(1).strip() if reason_match else ""
        qualifier = f"PRN {reason}".strip() if reason else "PRN"
        # Remove PRN from freq if it was included there
        freq = re.sub(r"\s*PRN\b.*", "", freq, flags=re.IGNORECASE).strip()

    # "as needed" with optional reason (when no explicit PRN token)
    if not qualifier:
        as_needed_match = re.search(
            r"\bas\s+needed(?:\s+for\s+([\w\s]{1,30}?))?(?:[,.]|$)",
            clean[search_start:],
            re.IGNORECASE,
        )
        if as_needed_match:
            reason = (as_needed_match.group(1) or "").strip()
            qualifier = f"as needed for {reason}".rstrip(" for").strip() if reason else "as needed"
            freq = re.sub(r"\s*as\s+needed\b.*", "", freq, flags=re.IGNORECASE).strip()

    # Route inference: if name contains "inhaler" and no explicit route found, infer "inhaled"
    route = rm.group(1) if rm else ""
    if not route and re.search(r"\binhaler\b", name, re.IGNORECASE):
        route = "inhaled"

    return {
        "name": name.lower(),
        "dose": dm.group(1).strip() if dm else "",
        "route": route,
        "frequency": freq,
        "duration": duration,
        "qualifier": qualifier,
        "span": [char_offset, char_offset + len(line)],
        "source": "section",
        "confidence": 0.85,
    }


def _parse_section_lines(section_text: str, section_start: int) -> "list[dict[str, Any]]":
    """Parse a medications section line-by-line."""
    results = []
    offset = section_start
    for line in section_text.splitlines():
        med = _parse_line(line, offset)
        if med:
            results.append(med)
        offset += len(line) + 1  # +1 for newline
    return results


def _find_sentence_bounds(text: str, char_pos: int) -> "tuple[int, int]":
    """Return (start, end) of the sentence containing char_pos."""
    start = char_pos
    while start > 0 and text[start - 1] not in ".\n!?":
        start -= 1
    end = char_pos
    while end < len(text) and text[end] not in ".\n!?":
        end += 1
    if end < len(text):
        end += 1  # include terminator
    return start, end


def _scan_sentence(text: str, entity_start: int) -> "dict[str, str]":
    """Scan only within the sentence containing entity_start for dose/route/freq.
    Searching starts at entity_start to avoid binding sig from earlier in the sentence.
    """
    s_start, s_end = _find_sentence_bounds(text, entity_start)
    snippet = text[s_start:s_end]
    local_pos = entity_start - s_start
    result: dict[str, str] = {}
    dm = _DOSE_RE.search(snippet, local_pos)
    if dm:
        result["dose"] = dm.group(1).strip()
    rm = _ROUTE_RE.search(snippet, local_pos)
    if rm:
        result["route"] = rm.group(1)
    fm = _FREQ_RE.search(snippet, local_pos)
    if fm:
        result["frequency"] = fm.group(1)
    return result


# Action verbs that introduce a medication order in prose (A/P, Plan, HPI)
_PROSE_VERB_RE = re.compile(
    r"(?i)^\s*(?:continue|start|resume|add|prescribe|may\s+use|use|initiate|begin)\s+"
)


def _split_prose_sentences(text: str) -> "list[tuple[str, int, int]]":
    """Return (sentence_text, start, end) for each sentence in text."""
    pattern = re.compile(r"(?<=[.!?])\s+|\n+")
    sentences = []
    last = 0
    for m in pattern.finditer(text):
        s = text[last:m.start()].strip()
        if s:
            sentences.append((s, last, m.start()))
        last = m.end()
    remaining = text[last:].strip()
    if remaining:
        sentences.append((remaining, last, len(text)))
    return sentences


def _parse_prose_sections(
    sections: "list[dict[str, Any]]",
    prose_cats: "set[str]",
) -> "list[dict[str, Any]]":
    """Parse action-verb medication sentences from non-medication prose sections."""
    results: list[dict[str, Any]] = []
    for sec in sections:
        if sec["category"] not in prose_cats:
            continue
        text_start = sec["end"] - len(sec["text"])
        for sent, s_start, _ in _split_prose_sentences(sec["text"]):
            vm = _PROSE_VERB_RE.match(sent)
            if not vm:
                continue
            remainder = sent[vm.end():]
            med = _parse_line(remainder, text_start + s_start)
            if med:
                results.append(med)
    return results


def extract_medications(text: str, sections: "list[dict[str, Any]] | None" = None) -> "list[dict[str, Any]]":
    """
    Extract medications from text.
    1. Structured line parser on any medications section (source: "section").
    2. medSpaCy on full text for prose fallback (source: "medspacy").
    3. De-duplicate by name; section results take precedence.
    """
    from extractors.sections import detect_sections
    if sections is None:
        sections = detect_sections(text)

    # Step 1: structured line parser on medications sections
    section_results: list[dict[str, Any]] = []
    for sec in sections:
        if sec["category"] == "medications":
            header_end = sec["start"] + len(sec["header"]) + 1  # +1 for colon/newline
            section_results.extend(_parse_section_lines(sec["text"], header_end))

    # Step 2: action-verb prose parser on plan / hpi / assessment_plan sections
    # Sentence-local by construction — each sentence is parsed independently.
    prose_section_results = _parse_prose_sections(
        sections, {"plan", "hpi", "assessment_plan"}
    )

    # Merge steps 1 & 2, preferring step 1 (structured) on name collision
    known_names: set[str] = {m["name"].lower() for m in section_results}
    for med in prose_section_results:
        n = med["name"].lower()
        if not any(sn == n or sn.startswith(n + " ") or n.startswith(sn + " ")
                   for sn in known_names):
            section_results.append(med)
            known_names.add(n)

    # Step 3: medSpaCy prose fallback — sentence-local window scan only
    nlp = _get_nlp()
    doc = nlp(text)
    spacy_results: list[dict[str, Any]] = []
    for ent in doc.ents:
        if ent.label_ != "MEDICATION":
            continue
        if ent._.is_negated:
            continue
        name = ent.text.lower()
        # Skip if already found by steps 1 or 2
        if any(sn == name or sn.startswith(name + " ") or name.startswith(sn + " ")
               for sn in known_names):
            continue
        # Sentence-local scan — never crosses a sentence boundary
        extra = _scan_sentence(text, ent.start_char)
        # Skip entities where no sig could be found AND no dose/route/freq anywhere nearby
        # (prevents pure-name noise, but keeps entities with freq like "as needed")
        if not extra and not _FREQ_RE.search(text[max(0, ent.start_char - 80):ent.end_char + 80]):
            continue
        spacy_results.append({
            "name": name,
            "dose": extra.get("dose", ""),
            "route": extra.get("route", ""),
            "frequency": extra.get("frequency", ""),
            "duration": "",
            "qualifier": "",
            "span": [ent.start_char, ent.end_char],
            "source": "medspacy",
            "confidence": 0.9,
        })

    return section_results + spacy_results
