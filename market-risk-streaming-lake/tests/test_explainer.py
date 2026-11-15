"""Template explainer, and the optional model client without a network call."""

from __future__ import annotations

import json

import pytest

from risk_lake.errors import RiskLakeError
from risk_lake.explain import TemplateExplainer, breach_payload, build_explainer
from risk_lake.limits import LimitBreach


def _breach() -> LimitBreach:
    return LimitBreach(
        session_date="2026-03-27",
        desk="EQ-DELTA-1",
        book="EQ-DELTA-1-BOOK-A",
        metric="daily_loss",
        metric_label="daily loss",
        value=360000.0,
        limit=200000.0,
        utilization=1.8,
        currency="USD",
    )


def test_template_restates_the_breach_and_is_not_a_decision() -> None:
    text = TemplateExplainer().explain(_breach())
    assert "EQ-DELTA-1 / EQ-DELTA-1-BOOK-A" in text
    assert "daily loss" in text
    assert "360,000.00 USD" in text
    assert "200,000.00 USD" in text
    assert "180.0% of the limit" in text
    assert "does not give a cause" in text
    assert "not the decision" in text


def test_template_stays_selected_when_a_key_is_present(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    explainer = build_explainer("template")
    assert explainer.name == "template"
    assert "not the decision" in explainer.explain(_breach())


def test_openai_explainer_requires_a_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(RiskLakeError, match="OPENAI_API_KEY"):
        build_explainer("openai")


def test_openai_request_contains_only_the_breach_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://example.invalid/v1")
    monkeypatch.setenv("OPENAI_MODEL", "demo-model")
    captured: dict[str, object] = {}

    class _Response:
        def __enter__(self) -> _Response:
            return self

        def __exit__(self, *args: object) -> bool:
            return False

        def read(self) -> bytes:
            body = {"choices": [{"message": {"content": "  A person should review the breach.  "}}]}
            return json.dumps(body).encode("utf-8")

    def fake_urlopen(request, timeout: float = 0):
        captured["url"] = request.full_url
        captured["auth"] = request.get_header("Authorization")
        captured["timeout"] = timeout
        captured["body"] = json.loads(request.data.decode("utf-8"))
        return _Response()

    monkeypatch.setattr("risk_lake.explain.urlopen", fake_urlopen)
    text = build_explainer("openai").explain(_breach())

    assert text == "A person should review the breach."
    assert captured["url"] == "https://example.invalid/v1/chat/completions"
    assert captured["auth"] == "Bearer test-key"
    body = captured["body"]
    assert isinstance(body, dict)
    assert body["model"] == "demo-model"
    assert body["temperature"] == 0
    user = json.loads(body["messages"][1]["content"])
    assert user == breach_payload(_breach())
    assert set(user) == {
        "session_date",
        "desk",
        "book",
        "metric",
        "value",
        "limit",
        "utilization",
        "currency",
    }
