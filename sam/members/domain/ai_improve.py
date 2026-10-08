"""Members-owned OpenRouter adapter behind a clean seam (R2, task 2.4).

This is the AI-improve seam for stored mail templates: given a template's
*branding-safe* content (subject + body + optional branding note) and a free-text
instruction, it asks an OpenRouter model to return an improved template. It is
written **module-agnostic** (no member-specific logic, no DynamoDB, no member rows)
so the whole thing can extract to ``sam/shared/templates/`` on a second consumer
(steering 35, rule of three) — do NOT build the shared library now.

Three hard guarantees this module enforces (the reason it exists as its own seam):

1. **Free-models-only, fail-closed on model choice** (R2 cost guard, steering 23
   no-dangerous-fallback). The model id is CONFIG, read from the environment
   (``MEMBERS_AI_MODEL``), defaulting to OpenRouter's zero-price router
   (``openrouter/auto`` is NOT used — the default is a ``:free`` id). The adapter
   REFUSES any model that is not on :data:`FREE_MODEL_ALLOW_LIST`: a costly model
   can never be selected by accident. "Fail closed" means a disallowed model raises
   :class:`DisallowedModelError` *before* any network call — the request never
   leaves the box, so no spend can occur.

2. **No member PII in the prompt, ever** (R2). The ``improve`` contract accepts an
   :class:`ImproveRequest` carrying ONLY a template's subject/body/branding + the
   instruction. There is no parameter through which a caller could pass a member
   row, and :func:`build_prompt` is a pure function of those branding-safe fields —
   so "no PII in the prompt" is a *structural* property, testable without a network.
   Merge happens on-plane at SEND time (template service), never here.

3. **Secret read fail-fast** (steering 23 no-dangerous-fallback, 43 no secrets in
   CI). ``OPENROUTER_API_KEY`` is read from the environment via :func:`require_env`
   with NO default — a missing/blank key raises :class:`AIConfigError` rather than
   silently degrading. The key is wired to the Members Lambda per environment as a
   secret (template.yaml ``OPENROUTER_API_KEY``) and is NEVER committed or placed in
   CI config (OIDC-only deploys, steering 43).

The HTTP transport is injected (:class:`OpenRouterTransport`) so the adapter is unit
-testable with no network and no live key: a fake transport exercises the request we
*would* send (letting a test assert no PII appears in it), and the fail-closed model
check short-circuits before the transport is ever touched.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Protocol

__all__ = [
    "FREE_MODEL_ALLOW_LIST",
    "DEFAULT_FREE_MODEL",
    "AIConfigError",
    "DisallowedModelError",
    "AIServiceError",
    "ImproveRequest",
    "ImproveResult",
    "OpenRouterTransport",
    "RequestsOpenRouterTransport",
    "OpenRouterAdapter",
    "require_env",
    "resolve_model",
]


# ── Config: the free-model allow-list (the cost guard, R2) ────────────────────────
#
# Free / near-zero-cost models ONLY. These are OpenRouter zero-price ids (the ``:free``
# tier) plus the free router. The list is the fail-closed boundary: the adapter will
# send a request ONLY for a model that appears here. Final values churn (free ids come
# and go) and are pinned at build time per design.md §12 — but the SHAPE is fixed: a
# costly model is never on this list, so it can never be selected.
#
# NOTE: this is an explicit allow-list, NOT a "block the expensive ones" deny-list — a
# deny-list fails OPEN (a new costly id nobody listed would slip through). An allow-list
# fails CLOSED: anything not named here is refused.
FREE_MODEL_ALLOW_LIST: frozenset[str] = frozenset(
    {
        # OpenRouter free router — picks a free model automatically.
        "openrouter/free",
        # Explicit zero-price (`:free`) ids. Pinned at build time (design §12); the
        # set only ever holds free-tier ids.
        "meta-llama/llama-3.3-70b-instruct:free",
        "meta-llama/llama-3.1-8b-instruct:free",
        "google/gemini-2.0-flash-exp:free",
        "mistralai/mistral-7b-instruct:free",
        "qwen/qwen-2.5-7b-instruct:free",
    }
)

#: The default model when ``MEMBERS_AI_MODEL`` is unset — the free router (zero price).
DEFAULT_FREE_MODEL = "openrouter/free"

#: The config env var naming the model. Config-selects-strategy (steering 36): the
#: model is config, never hardcoded at the call site.
MODEL_ENV_VAR = "MEMBERS_AI_MODEL"

#: The secret env var carrying the OpenRouter API key. Read fail-fast, NO default
#: (steering 23). Wired to the Members Lambda per env (template.yaml); never in CI.
API_KEY_ENV_VAR = "OPENROUTER_API_KEY"

#: OpenRouter chat-completions endpoint (same contract the Flask plane uses).
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"


# ── Errors ────────────────────────────────────────────────────────────────────────


class AIConfigError(RuntimeError):
    """Required AI config (the API key) is missing/blank.

    Raised instead of substituting a default so a missing secret fails LOUDLY at the
    seam rather than silently degrading (steering 23, no dangerous fallback).
    """


class DisallowedModelError(ValueError):
    """A requested model is not on :data:`FREE_MODEL_ALLOW_LIST` (fail-closed).

    Raised BEFORE any network call, so a costly / unknown model can never cause spend.
    The handler surfaces this as a 4xx with a clear machine code (design §9).
    """


class AIServiceError(RuntimeError):
    """OpenRouter returned an error / an unusable response.

    The caller degrades gracefully (the user keeps the un-improved template, design
    §9) — never a crash, never a silent costly retry.
    """


# ── The improve contract (branding-safe only — no PII can be passed) ────────────────


@dataclass(frozen=True)
class ImproveRequest:
    """The *only* input to :meth:`OpenRouterAdapter.improve`.

    Carries a template's BRANDING-SAFE content plus the instruction — and nothing
    else. There is deliberately NO field for member rows, recipients, or merged
    values: "no member PII in the prompt" (R2) is enforced by the TYPE, not by a
    runtime scrub. Merge-field *names* (e.g. ``"first_name"``) are template metadata,
    not member data, so they are allowed; a merge *value* has no parameter to arrive
    through.

    Fields:
        subject:       the template subject line (may contain ``{{merge_field}}``
                       placeholders — placeholders are template structure, not PII).
        body:          the template body (HTML/text) with placeholders, no real data.
        instruction:   the user's free-text ask ("make it warmer", "shorten it").
        language:      ``"nl"`` | ``"en"`` — which language the template is in.
        branding_note: optional branding/tone guidance (org name, house style) —
                       branding only, never member data.
        merge_fields:  the placeholder NAMES the body uses (metadata, not values).
    """

    subject: str
    body: str
    instruction: str
    language: str = "nl"
    branding_note: str | None = None
    merge_fields: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class ImproveResult:
    """The improved template plus the model that produced it (for audit/telemetry)."""

    subject: str
    body: str
    model_used: str


# ── The transport seam (so the adapter is testable without network / live key) ──────


class OpenRouterTransport(Protocol):
    """The injectable HTTP seam.

    One method: given a fully-formed request body + the API key, POST it to OpenRouter
    and return the parsed JSON. A fake implementation in tests captures the body (to
    assert no PII) and returns a canned response; the real implementation uses
    ``requests``. Keeping transport behind a Protocol is what lets the adapter be a
    pure, network-free unit under test.
    """

    def post_completion(self, *, api_key: str, payload: dict) -> dict:  # pragma: no cover - interface
        ...


class RequestsOpenRouterTransport:
    """The real transport: POSTs to OpenRouter with ``requests`` (shipped in the layer).

    Isolated here so the network + the ``requests`` import live OUTSIDE the adapter's
    decision logic — the adapter decides *whether* and *what* to send (fail-closed
    model check, PII-free prompt); this just moves the bytes.
    """

    def __init__(self, *, timeout: float = 30.0, referer: str | None = None) -> None:
        self._timeout = timeout
        self._referer = referer or os.environ.get("APP_URL", "https://myadmin.app")

    def post_completion(self, *, api_key: str, payload: dict) -> dict:
        # Imported lazily so merely importing the adapter module (e.g. for the
        # fail-closed model check or in a test with a fake transport) does not require
        # `requests` to be importable.
        import requests

        try:
            response = requests.post(
                OPENROUTER_URL,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": self._referer,
                    "X-Title": "myAdmin Members Templates",
                },
                json=payload,
                timeout=self._timeout,
            )
        except requests.exceptions.RequestException as exc:  # network / timeout
            raise AIServiceError(f"OpenRouter request failed: {exc}") from exc

        if response.status_code != 200:
            raise AIServiceError(
                f"OpenRouter returned HTTP {response.status_code}"
            )
        try:
            return response.json()
        except ValueError as exc:  # non-JSON body
            raise AIServiceError("OpenRouter returned a non-JSON response") from exc


# ── Config helpers (fail-fast, no dangerous fallback) ───────────────────────────────


def require_env(name: str, environ: dict | None = None) -> str:
    """Return a required env var's value, or raise :class:`AIConfigError` if missing.

    No default is ever substituted (steering 23, no-dangerous-fallback). Mirrors the
    projection layer's ``services.dynamodb_client.require_env`` discipline so a missing
    secret fails loudly at the seam.

    Args:
        name: the env var name.
        environ: the mapping to read from (defaults to ``os.environ``) — injectable so
            the adapter reads the SAME config source for the key as for the model, and
            tests can drive config without mutating the process env.
    """
    env = os.environ if environ is None else environ
    value = env.get(name)
    if value is None or value.strip() == "":
        raise AIConfigError(
            f"Required AI config env var '{name}' is missing or blank. There is no "
            f"default fallback (steering 23): a missing OpenRouter key / model must "
            f"fail loudly rather than silently degrade or guess."
        )
    return value.strip()


def resolve_model(environ: dict | None = None) -> str:
    """Resolve the configured model and enforce the free-model allow-list (fail-closed).

    The model is read from ``MEMBERS_AI_MODEL`` (config, steering 36), defaulting to
    :data:`DEFAULT_FREE_MODEL`. If the resolved id is not on
    :data:`FREE_MODEL_ALLOW_LIST`, this raises :class:`DisallowedModelError` — the
    adapter never sends a request for a model it did not pre-approve, so a costly model
    can never be selected by accident.

    Args:
        environ: env mapping to read from (defaults to ``os.environ``) — injectable so
            tests can drive a specific config without mutating the process env.

    Returns:
        The validated, allow-listed model id.

    Raises:
        DisallowedModelError: the configured model is not on the allow-list.
    """
    env = os.environ if environ is None else environ
    model = (env.get(MODEL_ENV_VAR) or DEFAULT_FREE_MODEL).strip()
    if model not in FREE_MODEL_ALLOW_LIST:
        raise DisallowedModelError(
            f"Model '{model}' is not on the free-model allow-list and is REFUSED "
            f"(fail-closed cost guard, R2). Allowed: {sorted(FREE_MODEL_ALLOW_LIST)}. "
            f"Set {MODEL_ENV_VAR} to a free-tier id to enable AI-improve."
        )
    return model


# ── Prompt builder (pure, branding-safe — the PII-free structural guarantee) ────────


def build_prompt(req: ImproveRequest) -> list[dict]:
    """Build the OpenRouter ``messages`` array from BRANDING-SAFE fields only.

    A pure function of :class:`ImproveRequest` (which cannot carry member PII). The
    prompt instructs the model to improve the template while PRESERVING its
    ``{{merge_field}}`` placeholders — so merge happens on-plane at send time, never in
    the prompt (R2). Because this takes no member data, "no PII in the prompt" is a
    property testable with a pure function call.
    """
    system = (
        "You improve HTML/text email TEMPLATES for a membership organisation. "
        "Keep every {{merge_field}} placeholder exactly as written — never fill one "
        "in, never invent recipient data. Return only the improved template."
    )
    merge_hint = (
        f"Preserve these placeholders verbatim: "
        f"{', '.join('{{' + m + '}}' for m in req.merge_fields)}."
        if req.merge_fields
        else "Preserve any {{placeholder}} tokens verbatim."
    )
    branding = (
        f"\nBranding / tone guidance: {req.branding_note}" if req.branding_note else ""
    )
    user = (
        f"Language: {req.language}\n"
        f"Instruction: {req.instruction}\n"
        f"{merge_hint}{branding}\n\n"
        f"Current subject:\n{req.subject}\n\n"
        f"Current body:\n{req.body}"
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


# ── The adapter ─────────────────────────────────────────────────────────────────────


class OpenRouterAdapter:
    """Members-owned OpenRouter adapter: ``improve(template, instruction)``.

    Behind a clean seam (module-agnostic, injectable transport). Enforces the three
    guarantees in the module docstring: free-models-only fail-closed, no PII in the
    prompt, secret read fail-fast.
    """

    def __init__(
        self,
        transport: OpenRouterTransport | None = None,
        *,
        environ: dict | None = None,
    ) -> None:
        self._transport = transport or RequestsOpenRouterTransport()
        self._environ = os.environ if environ is None else environ

    def improve(self, request: ImproveRequest) -> ImproveResult:
        """Improve a template with a free, allow-listed model. Fail-closed throughout.

        Order matters for the cost guard: the model is validated (fail-closed) and the
        prompt is built from branding-safe fields BEFORE the key is read and the
        request is sent. A disallowed model therefore raises without ever reading the
        secret or touching the network.

        Raises:
            DisallowedModelError: the configured model is not free/allow-listed.
            AIConfigError: ``OPENROUTER_API_KEY`` is missing/blank.
            AIServiceError: OpenRouter errored or returned an unusable response.
        """
        # 1. Fail-closed model check FIRST — no spend possible past this line if bad.
        model = resolve_model(self._environ)

        # 2. Build the PII-free prompt (pure function of branding-safe fields).
        messages = build_prompt(request)

        # 3. Only now read the secret (fail-fast) and send.
        api_key = require_env(API_KEY_ENV_VAR, self._environ)
        payload = {
            "model": model,
            "messages": messages,
            "temperature": 0.4,
        }
        data = self._transport.post_completion(api_key=api_key, payload=payload)

        improved_body = _extract_content(data)
        # The model returns the improved template body; the subject is kept unless the
        # model is asked to rewrite it. We keep this conservative: return the improved
        # body and preserve the original subject (subject edits are a separate ask).
        return ImproveResult(
            subject=request.subject,
            body=improved_body,
            model_used=model,
        )


def _extract_content(data: dict) -> str:
    """Pull the assistant message text out of an OpenRouter response, or fail cleanly."""
    try:
        choices = data["choices"]
        content = choices[0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise AIServiceError("OpenRouter response had no usable content") from exc
    if not isinstance(content, str) or not content.strip():
        raise AIServiceError("OpenRouter returned empty content")
    return content
