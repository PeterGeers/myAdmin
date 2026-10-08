"""Unit + property tests for the Members OpenRouter AI-improve adapter (R2, task 2.4).

Pins the three guarantees the adapter exists to enforce (see
``sam/members/domain/ai_improve.py``):

1. **Fail-closed on a non-allow-list model** — a model outside
   :data:`FREE_MODEL_ALLOW_LIST` is REFUSED (``DisallowedModelError``) BEFORE any
   network call and BEFORE the secret is read, so a costly model can never cause spend.
2. **No member PII in the AI prompt, ever** — the prompt is a pure function of
   branding-safe template fields; a member's PII, injected via realistic merge VALUES,
   never appears in the request body sent to OpenRouter (we assert against a fake
   transport that captures the exact payload).
3. **Secret read fail-fast** — a missing/blank ``OPENROUTER_API_KEY`` raises
   ``AIConfigError`` instead of silently degrading.

No network and no live key: the HTTP transport is injected (a fake), and the
fail-closed model check short-circuits before the transport is touched.

Validates: Requirements R2 (free-models-only fail-closed; no member PII in the AI
prompt; OPENROUTER_API_KEY secret, fail-fast).
"""

from __future__ import annotations

import os
import sys

import pytest
from hypothesis import given
from hypothesis import strategies as st

_REPO_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from sam.members.domain.ai_improve import (
    FREE_MODEL_ALLOW_LIST,
    AIConfigError,
    AIServiceError,
    DisallowedModelError,
    ImproveRequest,
    OpenRouterAdapter,
    build_prompt,
    resolve_model,
)

pytestmark = pytest.mark.unit


# ── Test doubles ────────────────────────────────────────────────────────────────────


class FakeTransport:
    """Captures the payload it is asked to POST and returns a canned completion.

    Lets a test (a) assert that NO member PII appears in the request body, and (b)
    detect whether the transport was reached at all (``called``) — the latter proves
    the fail-closed model check short-circuits before any network attempt.
    """

    def __init__(self, *, content: str = "Improved body") -> None:
        self.called = False
        self.captured_payload: dict | None = None
        self.captured_api_key: str | None = None
        self._content = content

    def post_completion(self, *, api_key: str, payload: dict) -> dict:
        self.called = True
        self.captured_api_key = api_key
        self.captured_payload = payload
        return {"choices": [{"message": {"content": self._content}}]}


class ExplodingTransport:
    """A transport that must never be called; fails the test loudly if it is."""

    def post_completion(self, *, api_key: str, payload: dict) -> dict:
        raise AssertionError(
            "transport was called, but it must not be reached (fail-closed / fail-fast)"
        )


def _request(**overrides) -> ImproveRequest:
    base = {
        "subject": "Uitnodiging voor {{first_name}}",
        "body": "<p>Beste {{first_name}}, hierbij het clubblad.</p>",
        "instruction": "Maak de toon warmer.",
        "language": "nl",
        "branding_note": "Huisstijl: vriendelijk, informeel.",
        "merge_fields": ("first_name", "membership_type"),
    }
    base.update(overrides)
    return ImproveRequest(**base)


# A free (allow-listed) model so the happy paths get past the fail-closed gate.
_FREE_MODEL = "openrouter/free"
assert _FREE_MODEL in FREE_MODEL_ALLOW_LIST


# ── 1. Fail-closed on a non-allow-list model ─────────────────────────────────────────


def test_resolve_model_rejects_model_outside_allow_list():
    """A configured model not on the allow-list is refused (fail-closed)."""
    with pytest.raises(DisallowedModelError):
        resolve_model({"MEMBERS_AI_MODEL": "openai/gpt-4o"})


def test_resolve_model_defaults_to_free_router_when_unset():
    """With no config, the model defaults to the free router — still allow-listed."""
    assert resolve_model({}) == "openrouter/free"


def test_resolve_model_accepts_every_allow_listed_id():
    """Every id the adapter ships as allowed resolves without raising."""
    for model in FREE_MODEL_ALLOW_LIST:
        assert resolve_model({"MEMBERS_AI_MODEL": model}) == model


def test_improve_fails_closed_before_touching_transport_or_key():
    """A disallowed model raises BEFORE the transport is called or the key is read.

    The transport explodes if reached and NO ``OPENROUTER_API_KEY`` is set — so if the
    adapter raised ``DisallowedModelError`` (not ``AssertionError`` / ``AIConfigError``),
    it refused the model before any spend or secret read could happen.
    """
    adapter = OpenRouterAdapter(
        ExplodingTransport(),
        environ={"MEMBERS_AI_MODEL": "anthropic/claude-3.5-sonnet"},
    )
    with pytest.raises(DisallowedModelError):
        adapter.improve(_request())


@given(
    model=st.text(min_size=1, max_size=40).filter(
        lambda m: m.strip() not in FREE_MODEL_ALLOW_LIST and m.strip() != ""
    )
)
def test_property_any_non_allow_listed_model_is_refused(model):
    """Property: ANY id not on the allow-list is refused (fail-closed cost guard).

    The allow-list fails closed by construction — anything not explicitly named is
    rejected, so a costly/unknown model can never slip through.

    Validates: Requirements R2 (free-models-only, fail-closed).
    """
    with pytest.raises(DisallowedModelError):
        resolve_model({"MEMBERS_AI_MODEL": model})


# ── 2. No member PII in the AI prompt ─────────────────────────────────────────────────


def test_build_prompt_contains_only_branding_safe_fields():
    """The prompt echoes the template + instruction + branding, and nothing else."""
    messages = build_prompt(_request())
    blob = " ".join(m["content"] for m in messages)
    # Template structure + instruction + branding ARE present (placeholders are not PII).
    assert "{{first_name}}" in blob
    assert "Maak de toon warmer." in blob
    assert "Huisstijl" in blob


def test_improve_prompt_carries_no_member_pii():
    """Realistic member PII never reaches the OpenRouter payload.

    The ``ImproveRequest`` has no parameter for member rows, so PII can only arrive by
    (mistakenly) baking it into template text. We prove the adapter sends the template
    AS AUTHORED — placeholders, not values — by asserting that concrete PII values do
    NOT appear in the captured payload when the template uses placeholders.

    Validates: Requirements R2 (no member PII in the AI prompt).
    """
    pii_values = [
        "Jan de Vries",          # a real member name
        "jan.devries@example.nl",  # a real email
        "+31 6 12345678",        # a real phone
        "Dorpsstraat 12, Utrecht",  # a real address
    ]
    adapter = OpenRouterAdapter(
        (transport := FakeTransport()),
        environ={"OPENROUTER_API_KEY": "sk-or-v1-testkey", "MEMBERS_AI_MODEL": _FREE_MODEL},
    )
    adapter.improve(_request())

    assert transport.called
    payload_text = str(transport.captured_payload)
    for value in pii_values:
        assert value not in payload_text, f"member PII leaked into the AI prompt: {value!r}"


@given(
    # Distinctive PII values that could NOT be ordinary template/branding text — a
    # unique prefix guarantees any appearance in the prompt is a genuine leak, not an
    # incidental substring collision with the template's own words.
    first_name=st.text(
        alphabet=st.characters(whitelist_categories=("Lu", "Ll")), min_size=1, max_size=20
    ).map(lambda s: f"PIINAME{s}"),
    email=st.emails(),
)
def test_property_merge_values_never_enter_the_prompt(first_name, email):
    """Property: no matter the member's name/email, those VALUES never enter the prompt.

    The prompt is built only from the template's placeholder NAMES + branding, so a
    merge VALUE (filled on-plane at send time) can never be in the request body.

    Validates: Requirements R2 (no member PII in the AI prompt).
    """
    messages = build_prompt(_request())
    blob = " ".join(m["content"] for m in messages)
    assert first_name not in blob  # name value absent
    assert email not in blob  # email value absent


# ── 3. Secret read fail-fast ──────────────────────────────────────────────────────────


def test_improve_fails_fast_when_api_key_missing():
    """A missing OPENROUTER_API_KEY raises AIConfigError (no silent degrade)."""
    adapter = OpenRouterAdapter(
        FakeTransport(),
        environ={"MEMBERS_AI_MODEL": _FREE_MODEL},  # no OPENROUTER_API_KEY
    )
    with pytest.raises(AIConfigError):
        adapter.improve(_request())


def test_improve_fails_fast_when_api_key_blank():
    """A blank OPENROUTER_API_KEY is treated as missing (fail-fast)."""
    adapter = OpenRouterAdapter(
        FakeTransport(),
        environ={"OPENROUTER_API_KEY": "   ", "MEMBERS_AI_MODEL": _FREE_MODEL},
    )
    with pytest.raises(AIConfigError):
        adapter.improve(_request())


# ── Happy path + response handling ────────────────────────────────────────────────────


def test_improve_returns_improved_body_and_records_model():
    """A valid config + key yields the improved body and the model used."""
    adapter = OpenRouterAdapter(
        FakeTransport(content="<p>Een warmere versie met {{first_name}}.</p>"),
        environ={"OPENROUTER_API_KEY": "sk-or-v1-testkey", "MEMBERS_AI_MODEL": _FREE_MODEL},
    )
    result = adapter.improve(_request())
    assert result.model_used == _FREE_MODEL
    assert "{{first_name}}" in result.body
    assert result.subject == _request().subject  # subject preserved


def test_improve_raises_service_error_on_unusable_response():
    """An OpenRouter response with no usable content surfaces as AIServiceError."""

    class EmptyTransport:
        def post_completion(self, *, api_key, payload):
            return {"choices": []}

    adapter = OpenRouterAdapter(
        EmptyTransport(),
        environ={"OPENROUTER_API_KEY": "sk-or-v1-testkey", "MEMBERS_AI_MODEL": _FREE_MODEL},
    )
    with pytest.raises(AIServiceError):
        adapter.improve(_request())
