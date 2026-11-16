"""Plain-English breach explanations.

The default explainer fills a fixed template. It does not call a model and
does not need a key. ``OpenAICompatibleExplainer`` is used only when the
caller selects it and ``OPENAI_API_KEY`` is set. The numbers that decide a
breach are computed before either explainer runs.
"""

from __future__ import annotations

import json
import os
from typing import Protocol
from urllib.request import Request, urlopen

from risk_lake.errors import RiskLakeError
from risk_lake.limits import LimitBreach

_SYSTEM_PROMPT = (
    "You explain one market-risk limit breach in two or three plain sentences "
    "for a risk manager. Use only the JSON figures in the user message. "
    "Do not invent a market cause, a desk action, or a number that is not there. "
    "Say that a person reviews the breach. You are not the decision."
)

_PAYLOAD_FIELDS = (
    "session_date",
    "desk",
    "book",
    "metric",
    "value",
    "limit",
    "utilization",
    "currency",
)


class Explainer(Protocol):
    """Turn one breach into a short paragraph."""

    name: str

    def explain(self, breach: LimitBreach) -> str:
        """Return the paragraph."""


class TemplateExplainer:
    """Deterministic wording over the breach fields."""

    name = "template"

    def explain(self, breach: LimitBreach) -> str:
        return (
            f"{breach.desk} / {breach.book} is over its {breach.metric_label} limit "
            f"on {breach.session_date}. "
            f"The figure is {breach.value:,.2f} {breach.currency} and the limit is "
            f"{breach.limit:,.2f} {breach.currency}, "
            f"which is {breach.utilization * 100:.1f}% of the limit. "
            "The template only restates those inputs. It does not give a cause. "
            "A person reviews this breach before any action. This text is not the decision."
        )


class OpenAICompatibleExplainer:
    """Optional chat-completions client. Off unless the caller selects it.

    The request body contains the breach fields and the system prompt. It does
    not send the lake, the position file, or any other payload.
    """

    name = "openai"

    def __init__(self, *, api_key: str, base_url: str, model: str, timeout: float = 30.0) -> None:
        if not api_key.strip():
            raise RiskLakeError("The OpenAI explainer needs OPENAI_API_KEY.")
        self._api_key = api_key.strip()
        self._url = base_url.rstrip("/") + "/chat/completions"
        self._model = model
        self._timeout = timeout

    def explain(self, breach: LimitBreach) -> str:
        body = {
            "model": self._model,
            "temperature": 0,
            "max_tokens": 200,
            "messages": [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps(breach_payload(breach), sort_keys=True)},
            ],
        }
        request = Request(
            self._url,
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=self._timeout) as response:
                raw = response.read()
        except RiskLakeError:
            raise
        except Exception as exc:
            raise RiskLakeError("the explanation model request failed") from exc
        return _completion_text(raw)


def build_explainer(name: str) -> Explainer:
    """Return the template, or the model client when ``name`` is ``openai``.

    A key in the environment does not select the model. The demo stays on
    the template unless the caller passes ``openai``.
    """
    if name == "template":
        return TemplateExplainer()
    if name == "openai":
        api_key = os.environ.get("OPENAI_API_KEY", "")
        if not api_key.strip():
            raise RiskLakeError(
                "The OpenAI explainer needs OPENAI_API_KEY. "
                "The default template explainer does not."
            )
        base_url = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
        model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
        return OpenAICompatibleExplainer(api_key=api_key, base_url=base_url, model=model)
    raise RiskLakeError("explainer must be template or openai")


def breach_payload(breach: LimitBreach) -> dict[str, object]:
    """The only fields an external explainer is given."""
    payload: dict[str, object] = {
        "session_date": breach.session_date,
        "desk": breach.desk,
        "book": breach.book,
        "metric": breach.metric_label,
        "value": round(breach.value, 2),
        "limit": round(breach.limit, 2),
        "utilization": round(breach.utilization, 6),
        "currency": breach.currency,
    }
    if tuple(payload) != _PAYLOAD_FIELDS:
        raise RiskLakeError("breach payload fields drifted")
    return payload


def _completion_text(raw: bytes) -> str:
    try:
        body = json.loads(raw.decode("utf-8"))
        text = body["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise RiskLakeError("the explanation model returned an unexpected body") from exc
    if not isinstance(text, str) or not text.strip():
        raise RiskLakeError("the explanation model returned an empty explanation")
    return text.strip()
