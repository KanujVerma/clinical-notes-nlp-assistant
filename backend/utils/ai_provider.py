import json
import logging
import os

logger = logging.getLogger(__name__)

MODEL = "claude-haiku-4-5-20251001"
MAX_TOKENS = 256
TEMPERATURE = 0

SYSTEM_PROMPT = """
You are a clinical terminology reference tool for a trained clinical reviewer auditing an NLP pipeline's output. Given a single medication name or clinical abbreviation and optional structured sig context, produce a short, neutral, informational explanation.

STRICT RULES:
1. Never give diagnostic advice or suggest a diagnosis.
2. Never give treatment recommendations or dosing advice.
3. Never address a patient ("you should…", "your…") — tone is reviewer-facing third person.
4. Never speculate beyond the provided inputs. If the input is ambiguous or sparse, set uncertainty and keep fields brief.
5. Never discuss contraindications, adverse effects, or interactions in detail — one sentence max, only if broadly informational.
6. Output valid JSON only, matching exactly {"whatItIs": "...", "commonUse": "...", "plainLanguage": "...", "uncertainty": "..."} where uncertainty is optional. No prose before or after.

Field limits: whatItIs ≤ 25 words, commonUse ≤ 20 words, plainLanguage ≤ 40 words, uncertainty ≤ 20 words.
"""

REQUIRED_KEYS = {"whatItIs", "commonUse", "plainLanguage"}


class AIDisabled(Exception):
    """Raised when ANTHROPIC_API_KEY is not set in the environment."""


class AIError(Exception):
    """Raised when the API call fails or returns invalid JSON/schema."""


def is_available() -> bool:
    """Return True if ANTHROPIC_API_KEY is set to a non-empty value."""
    return bool(os.environ.get("ANTHROPIC_API_KEY", "").strip())


def _call_anthropic(messages: list) -> str:
    """Make the actual HTTP call to Anthropic and return the response text."""
    import anthropic  # lazy import — keeps tests from requiring the package

    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    client = anthropic.Anthropic(api_key=api_key)
    response = client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        system=SYSTEM_PROMPT,
        messages=messages,
    )
    return response.content[0].text


def explain(kind: str, value: str, context: dict) -> dict:
    """
    Call Anthropic Haiku to produce an explanation for a clinical term.

    Parameters
    ----------
    kind    : 'medication' | 'abbreviation'
    value   : the term string
    context : dict of optional sig fields

    Returns the parsed JSON dict on success.
    Raises AIDisabled if ANTHROPIC_API_KEY is not set.
    Raises AIError if the API call fails or the response is malformed.
    """
    if not is_available():
        raise AIDisabled("ANTHROPIC_API_KEY is not set")

    messages = [
        {
            "role": "user",
            "content": json.dumps({"kind": kind, "value": value, "context": context or {}}),
        }
    ]

    try:
        raw = _call_anthropic(messages)
    except Exception as exc:
        logger.exception("Anthropic API call failed for kind=%s value=%s", kind, value)
        raise AIError(f"API call failed: {exc}") from exc

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        logger.error("JSON parse failed. Raw response: %r", raw)
        raise AIError(f"Invalid model response: could not parse JSON — {exc}") from exc

    missing = REQUIRED_KEYS - parsed.keys()
    if missing:
        logger.error("Schema validation failed. Missing keys: %s. Raw: %r", missing, raw)
        raise AIError(f"Invalid model response: missing required keys {missing}")

    return parsed
