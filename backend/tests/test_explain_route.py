import sys
import os
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app import create_app


@pytest.fixture
def app():
    return create_app({"TESTING": True, "DATABASE_URL": "sqlite:///:memory:"})


@pytest.fixture
def client(app):
    return app.test_client()


SESSION_HEADERS = {"X-Session-ID": "test-session-abc"}

FAKE_EXPLANATION = {
    "whatItIs": "A common medication",
    "commonUse": "Used for pain relief",
    "plainLanguage": "This is a pain reliever used by patients",
}


class _FakeAIProvider:
    """Minimal stub replacing the ai_provider module."""

    def __init__(self, explain_result=None, explain_exc=None, available=True):
        self._explain_result = explain_result
        self._explain_exc = explain_exc
        self._available = available

    def explain(self, kind, value, context):
        if self._explain_exc is not None:
            raise self._explain_exc
        return self._explain_result

    def is_available(self):
        return self._available

    # Re-expose exceptions so route code can catch them via the module reference
    @property
    def AIDisabled(self):
        from utils.ai_provider import AIDisabled
        return AIDisabled

    @property
    def AIError(self):
        from utils.ai_provider import AIError
        return AIError


def _patch_ai(monkeypatch, explain_result=None, explain_exc=None, available=True):
    fake = _FakeAIProvider(explain_result=explain_result, explain_exc=explain_exc, available=available)
    monkeypatch.setattr("routes.explain.ai_provider", fake)
    return fake


def _patch_rate_limit(monkeypatch, allowed=True, retry_after=0):
    monkeypatch.setattr(
        "routes.explain.check_rate_limit",
        lambda session_id, **kwargs: (allowed, retry_after),
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_missing_session_returns_400(client):
    resp = client.post("/api/explain", json={"kind": "medication", "value": "Aspirin"})
    assert resp.status_code == 400
    data = resp.get_json()
    assert data["code"] == "MISSING_SESSION_ID"


def test_bad_kind_returns_400(client, monkeypatch):
    _patch_rate_limit(monkeypatch)
    _patch_ai(monkeypatch, explain_result=FAKE_EXPLANATION)
    resp = client.post(
        "/api/explain",
        json={"kind": "invalid", "value": "Aspirin"},
        headers=SESSION_HEADERS,
    )
    assert resp.status_code == 400
    data = resp.get_json()
    assert data["code"] == "INVALID_INPUT"


def test_missing_kind_returns_400(client, monkeypatch):
    _patch_rate_limit(monkeypatch)
    _patch_ai(monkeypatch, explain_result=FAKE_EXPLANATION)
    resp = client.post(
        "/api/explain",
        json={"value": "Aspirin"},
        headers=SESSION_HEADERS,
    )
    assert resp.status_code == 400
    data = resp.get_json()
    assert data["code"] == "INVALID_INPUT"


def test_value_too_long_returns_400(client, monkeypatch):
    _patch_rate_limit(monkeypatch)
    _patch_ai(monkeypatch, explain_result=FAKE_EXPLANATION)
    long_value = "A" * 81
    resp = client.post(
        "/api/explain",
        json={"kind": "medication", "value": long_value},
        headers=SESSION_HEADERS,
    )
    assert resp.status_code == 400
    data = resp.get_json()
    assert data["code"] == "INVALID_INPUT"


def test_value_with_newline_returns_400(client, monkeypatch):
    _patch_rate_limit(monkeypatch)
    _patch_ai(monkeypatch, explain_result=FAKE_EXPLANATION)
    resp = client.post(
        "/api/explain",
        json={"kind": "medication", "value": "Aspirin\nInjection"},
        headers=SESSION_HEADERS,
    )
    assert resp.status_code == 400
    data = resp.get_json()
    assert data["code"] == "INVALID_INPUT"


def test_context_not_dict_returns_400(client, monkeypatch):
    _patch_rate_limit(monkeypatch)
    _patch_ai(monkeypatch, explain_result=FAKE_EXPLANATION)
    resp = client.post(
        "/api/explain",
        json={"kind": "medication", "value": "metformin", "context": "not-a-dict"},
        headers={"X-Session-ID": "sess-ctx-type-test"},
    )
    assert resp.status_code == 400
    data = resp.get_json()
    assert data["code"] == "INVALID_INPUT"


def test_context_too_many_keys_returns_400(client, monkeypatch):
    _patch_rate_limit(monkeypatch)
    _patch_ai(monkeypatch, explain_result=FAKE_EXPLANATION)
    too_many = {f"key{i}": "val" for i in range(7)}
    resp = client.post(
        "/api/explain",
        json={"kind": "medication", "value": "metformin", "context": too_many},
        headers=SESSION_HEADERS,
    )
    assert resp.status_code == 400
    data = resp.get_json()
    assert data["code"] == "INVALID_INPUT"


def test_rate_limited_returns_429(client, monkeypatch):
    _patch_rate_limit(monkeypatch, allowed=False, retry_after=60)
    _patch_ai(monkeypatch, explain_result=FAKE_EXPLANATION)
    resp = client.post(
        "/api/explain",
        json={"kind": "medication", "value": "Aspirin"},
        headers=SESSION_HEADERS,
    )
    assert resp.status_code == 429
    data = resp.get_json()
    assert data["code"] == "RATE_LIMITED"
    assert data["retry_after"] == 60


def test_ai_disabled_returns_503(client, monkeypatch):
    from utils.ai_provider import AIDisabled

    _patch_rate_limit(monkeypatch)
    _patch_ai(monkeypatch, explain_exc=AIDisabled("not configured"))
    resp = client.post(
        "/api/explain",
        json={"kind": "medication", "value": "Aspirin"},
        headers=SESSION_HEADERS,
    )
    assert resp.status_code == 503
    data = resp.get_json()
    assert data["code"] == "AI_DISABLED"


def test_ai_error_returns_502(client, monkeypatch):
    from utils.ai_provider import AIError

    _patch_rate_limit(monkeypatch)
    _patch_ai(monkeypatch, explain_exc=AIError("service down"))
    resp = client.post(
        "/api/explain",
        json={"kind": "medication", "value": "Aspirin"},
        headers=SESSION_HEADERS,
    )
    assert resp.status_code == 502
    data = resp.get_json()
    assert data["code"] == "AI_ERROR"


def test_happy_path_returns_200(client, monkeypatch):
    _patch_rate_limit(monkeypatch)
    _patch_ai(monkeypatch, explain_result=FAKE_EXPLANATION)
    resp = client.post(
        "/api/explain",
        json={"kind": "medication", "value": "Aspirin", "context": {"dose": "500mg"}},
        headers=SESSION_HEADERS,
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert "explanation" in data
    assert data["explanation"] == FAKE_EXPLANATION
    assert data["modelUsed"] == "claude-haiku-4-5-20251001"


def test_status_available_true(client, monkeypatch):
    _patch_ai(monkeypatch, available=True)
    resp = client.get("/api/explain/status")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data == {"available": True}


def test_status_available_false(client, monkeypatch):
    _patch_ai(monkeypatch, available=False)
    resp = client.get("/api/explain/status")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data == {"available": False}
