import json
import os

import pytest

import backend.utils.ai_provider as ai_provider
from backend.utils.ai_provider import AIDisabled, AIError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_VALID_RESPONSE = json.dumps({
    "whatItIs": "A beta-blocker used to manage heart conditions.",
    "commonUse": "Used for hypertension and heart failure management.",
    "plainLanguage": "A medicine that slows the heart rate and reduces blood pressure.",
})

_VALID_RESPONSE_WITH_UNCERTAINTY = json.dumps({
    "whatItIs": "A beta-blocker used to manage heart conditions.",
    "commonUse": "Used for hypertension and heart failure management.",
    "plainLanguage": "A medicine that slows the heart rate and reduces blood pressure.",
    "uncertainty": "Abbreviated input; exact formulation unclear.",
})

_RESPONSE_MISSING_WHAT_IT_IS = json.dumps({
    "commonUse": "Used for hypertension.",
    "plainLanguage": "A blood pressure medicine.",
})


# ---------------------------------------------------------------------------
# is_available()
# ---------------------------------------------------------------------------

def test_is_available_true(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-key")
    assert ai_provider.is_available() is True


def test_is_available_false(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert ai_provider.is_available() is False


def test_is_available_false_for_whitespace_key(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "   ")
    assert ai_provider.is_available() is False


# ---------------------------------------------------------------------------
# explain()
# ---------------------------------------------------------------------------

def test_explain_returns_parsed_dict(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-key")
    monkeypatch.setattr(ai_provider, "_call_anthropic", lambda msgs: _VALID_RESPONSE)

    result = ai_provider.explain("medication", "metoprolol", {"dose": "25 mg"})

    assert isinstance(result, dict)
    assert "whatItIs" in result
    assert "commonUse" in result
    assert "plainLanguage" in result
    assert result["whatItIs"] == "A beta-blocker used to manage heart conditions."


def test_explain_raises_ai_disabled_when_no_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    with pytest.raises(AIDisabled):
        ai_provider.explain("medication", "metoprolol", {})


def test_explain_raises_ai_error_on_malformed_json(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-key")
    monkeypatch.setattr(ai_provider, "_call_anthropic", lambda msgs: "not json")

    with pytest.raises(AIError, match="could not parse JSON"):
        ai_provider.explain("medication", "metoprolol", {})


def test_explain_raises_ai_error_on_missing_required_key(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-key")
    monkeypatch.setattr(
        ai_provider, "_call_anthropic", lambda msgs: _RESPONSE_MISSING_WHAT_IT_IS
    )

    with pytest.raises(AIError, match="missing required keys"):
        ai_provider.explain("abbreviation", "BID", {})


def test_explain_includes_optional_uncertainty(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-key")
    monkeypatch.setattr(
        ai_provider, "_call_anthropic", lambda msgs: _VALID_RESPONSE_WITH_UNCERTAINTY
    )

    result = ai_provider.explain("abbreviation", "PRN", {"qualifier": "as needed"})

    assert "uncertainty" in result
    assert result["uncertainty"] == "Abbreviated input; exact formulation unclear."


def test_explain_raises_ai_error_on_api_failure(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-key")

    def raise_error(msgs):
        raise RuntimeError("connection timeout")

    monkeypatch.setattr(ai_provider, "_call_anthropic", raise_error)
    with pytest.raises(ai_provider.AIError, match="API call failed"):
        ai_provider.explain("medication", "metoprolol", {})
