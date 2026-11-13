"""Submission body parsing + resolved-view shaping.
Part of public_app (task 8).
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Mapping
from typing import Any

from sam.members.handler._http import (
    _field_errors_array,  # SEC-2 (task 4.2): shapes the deliberate validation 422 per-field array
)

logger = logging.getLogger(__name__)

#: Raw-storage-shape keys that MUST NEVER appear in a public response (steering 39 / SEC-1). The
#: resolved-view contract keeps the physical two-map/dotted-key layout (``fields`` vs ``overrides``
#: vs ``fixed_overrides``, dotted ``{group}.{key}``) INSIDE the repository; a public response
#: carries only the RESOLVED view. The authority (``get_public_field_config``) already builds that
#: resolved view by constructing an explicit, named key set — it never copies the raw item — so
#: nothing raw can ride along by construction. This set names the exact keys the access guard
#: (``scripts/check_sam_service_access.py``) also forbids, so the two enforcement points agree.
_RAW_SHAPE_KEYS = frozenset({"field_overlay", "overrides", "fixed_overrides"})


def _assert_fail_closed_public_schema(schema: Any) -> Any:
    """SEC-1 defense-in-depth: assert the resolved public schema leaks NO raw/physical shape.

    The applicant schema is an ALLOWLIST authored upstream in
    :meth:`MembershipService.get_public_field_config`: a field is exposed ONLY when the tenant
    explicitly marked it ``application_visible`` (default ``False`` → an unknown / newly-added
    field defaults HIDDEN, fail-closed), and each exposed field is projected into an EXPLICIT,
    named key set (``key``/``type``/``label``/``functional_group``/``order``/``required``/
    ``show_when``/``options``/``format``) — never a copy of the raw item, so no secret VALUE and no
    physical-layout key can ride along. A secret can therefore surface at most as a boolean
    existence flag, never its value.

    This guard is the LAST trust boundary (the public edge) re-checking that invariant rather than
    blindly trusting the upstream view: if a future change to the authority ever regressed to
    leaking a raw-shape key (``field_overlay`` / ``overrides`` / ``fixed_overrides``) or a dotted
    ``{group}.{key}`` key — at the schema top level OR inside any field — this FAILS CLOSED by
    raising, so the regression surfaces as a bodied 500 server-side instead of silently
    over-exposing tenant data on an unauthenticated endpoint. It mirrors the committed access guard
    (``scripts/check_sam_service_access.py``) and the boundary test, moving the same rule to
    runtime on the one surface with no authentication in front of it.

    Returns ``schema`` unchanged on success (so it is a transparent pass-through at the call site).
    """
    if isinstance(schema, Mapping):
        _reject_raw_shape_keys(schema.keys())
        for field in schema.get("fields") or ():
            if isinstance(field, Mapping):
                _reject_raw_shape_keys(field.keys())
    return schema


def _reject_raw_shape_keys(keys: Any) -> None:
    """Raise if any key is a forbidden raw-shape key or a dotted ``{group}.{key}`` key (SEC-1)."""
    for key in keys:
        if not isinstance(key, str):
            continue
        if key in _RAW_SHAPE_KEYS or "." in key:
            # A raw-shape / dotted physical key reached the public boundary — fail closed. The
            # message is server-log-only (the edge maps the raised error to a neutral bodied 500,
            # never echoing the offending key to the unauthenticated caller).
            raise ValueError(
                f"public schema carried a forbidden raw-shape key {key!r} (SEC-1 / steering 39)"
            )


# ── Submit-request sourcing (task 4.1) — the NON-TRUSTED values the submit write needs ──
#
# The POST submit carries three non-field inputs the write needs beside the resolved tenant and
# the applicant ``body``. NONE of them confers tenant or identity (steering 39: the tenant comes
# ONLY from the verified marker, never the request body); they are read from the request in a
# non-trusted way and the authoritative service owns their meaning:
#
#   * ``session_key`` — a per-submission idempotency/de-dup value (R3a). The FIRST submit of a
#     session CREATES; a same-key resend (a correction, a double-click) UPDATES that same record.
#     A client that supplies one gets resend-coalescing; one that supplies none gets a fresh,
#     server-minted uuid4 (so every submit lands, never silently coalesced to another's record).
#   * ``locale`` — the applicant's preferred locale; the service owns normalization + fallback.
#   * ``consent`` — the applicant's affirmative acceptance of the tenant's versioned notice; the
#     service REQUIRES it (a submit without it is a hard reject) and stamps a server-authoritative
#     consent record (version/timestamp/locale resolved server-side, never client-trusted).

#: The body keys the submit reads its session value / locale from. Accept both the camelCase the
#: SPA form posts and the snake_case the domain uses, so the edge is tolerant of either client.
_SESSION_KEY_BODY_KEYS = ("session_key", "sessionKey", "session_id", "sessionId")
_LOCALE_BODY_KEYS = ("locale", "lang")


def _submission_session_key(body: Mapping[str, Any]) -> str:
    """The per-submission de-dup ``session_key`` for ``create_application`` (R3a), NON-TRUSTED.

    Read from the request body (one of :data:`_SESSION_KEY_BODY_KEYS`) so a resend within one
    fill-in session coalesces onto the SAME record; a server-minted ``uuid4`` is used when the
    client sends none (a fresh session), so a submission is NEVER silently lost or coalesced onto
    an unrelated record. The value is a de-dup token ONLY — it carries no tenant and no identity
    (the tenant is the verified, marker-resolved one; the ``member_id`` is server-minted), so
    trusting it for de-dup grants a caller no cross-tenant or cross-record reach.
    """
    if isinstance(body, Mapping):
        for key in _SESSION_KEY_BODY_KEYS:
            value = body.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return uuid.uuid4().hex


def _submission_locale(body: Mapping[str, Any]) -> str | None:
    """The applicant's requested locale off the body, or ``None`` (the service owns fallback)."""
    if isinstance(body, Mapping):
        for key in _LOCALE_BODY_KEYS:
            value = body.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return None


def _submission_consent(body: Mapping[str, Any]) -> Mapping[str, Any] | None:
    """The applicant's consent object off the body, or ``None`` (the service REQUIRES/validates it).

    Passed through verbatim for the service to gate on (affirmative consent is mandatory — a
    submit without it is rejected) and to stamp server-authoritatively; the edge neither trusts
    nor interprets its contents.
    """
    if isinstance(body, Mapping):
        consent = body.get("consent")
        if isinstance(consent, Mapping):
            return consent
    return None


def _public_field_key(engine_key: Any) -> str:
    """Map an engine error key to the BARE key the published form names its control by.

    The engine keys errors by physical identity (``personal.last_name``, ``membership.membership_type``,
    ``overlay.region``); the public field config emits the bare ``key`` (``last_name`` ...) and the
    form's controls carry that name. Steering 39: no dotted ``{group}.{key}`` crosses the public
    boundary. The bare key IS the last dotted segment (the group / ``overlay`` prefix is the
    physical placement), so this is derived from the key alone: no extra read, no boto3. A key
    with no dot (``consent``) is returned unchanged. For an unrecognised shape the last segment is
    still used, so a message is never dropped.
    """
    key = str(engine_key)
    return key.rsplit(".", 1)[-1] or key


def _public_field_errors_array(errors: Mapping[str, Any]) -> list[dict[str, Any]]:
    """The shared per-field ``errors`` array with ``field`` rewritten to the bare public key.

    Entry shape is unchanged (``{field, code, detail, params?}``). When two engine keys collapse
    to the same bare key, the FIRST entry wins (no duplicates).
    """
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for entry in _field_errors_array(errors):
        bare = _public_field_key(entry.get("field"))
        if bare in seen:
            continue
        seen.add(bare)
        out.append({**entry, "field": bare})
    return out
