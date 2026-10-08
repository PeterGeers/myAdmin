"""
Members Lambda edge — HTTP adapter helpers (extracted from ``app`` for cohesion).

Pure handler-layer **adapter** concerns: parsing an API Gateway proxy event into the
pieces the router/edge need, and shaping the platform response/error envelope. Nothing
here authenticates, authorizes, resolves scope, or touches the domain/DynamoDB — those
stay in the :mod:`sam.members.handler.app` facade.

Re-exported from :mod:`sam.members.handler.app`; its public import surface is unchanged
(e.g. ``app._response`` / ``app._json_default`` remain available to the tests). This is a
pure structural split (code-quality M2) with zero behaviour change.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from sam.members.domain.error_codes import FieldError

# ── Request parsing (handler-layer adapter concern) ───────────────────────────────────


@dataclass(frozen=True)
class ParsedRequest:
    """The pieces of an API Gateway proxy event the router + edge need."""

    method: str
    path: str
    headers: Mapping[str, Any]
    query: Mapping[str, Any]
    body: Any


def _parse_request(event: Mapping[str, Any]) -> ParsedRequest:
    """Extract method/path/headers/query/body from an API Gateway proxy event.

    Supports both the REST/HTTP-v1 shape (``httpMethod`` + ``path``) and the HTTP-v2 shape
    (``requestContext.http.method`` + ``rawPath``). JSON bodies are decoded best-effort; a
    non-JSON or empty body is passed through as-is (the domain layer validates content).
    """
    event = event or {}

    method = event.get("httpMethod")
    path = event.get("path")
    request_context = event.get("requestContext") or {}
    http_ctx = request_context.get("http") if isinstance(request_context, Mapping) else None
    if not method and isinstance(http_ctx, Mapping):
        method = http_ctx.get("method")
    if not path:
        path = event.get("rawPath") or (http_ctx.get("path") if isinstance(http_ctx, Mapping) else None)

    headers = event.get("headers") or {}
    query = event.get("queryStringParameters") or {}

    body: Any = event.get("body")
    if isinstance(body, str) and body:
        try:
            body = json.loads(body)
        except (ValueError, TypeError):
            # Leave the raw string; the domain layer decides whether that is acceptable.
            pass

    return ParsedRequest(
        method=method or "",
        path=path or "/",
        headers=headers if isinstance(headers, Mapping) else {},
        query=query if isinstance(query, Mapping) else {},
        body=body,
    )


# ── Accepted (202) result marker — the queued/enqueued send path (R4, task 4.2) ──────


@dataclass(frozen=True)
class AcceptedResult:
    """A domain result the edge must shape as a 202 Accepted (enqueued, not yet done).

    Most routes return a plain value the edge shapes as a 200 (the work is complete). The
    ``deliver`` route (R4) is different: it ENQUEUES the send and returns immediately — the
    actual SES send happens later in the worker — so the honest HTTP status is **202 Accepted**
    ("the request is accepted for processing"), not 200 ("done"). The dispatch wraps the
    service's accepted payload in this marker; :func:`sam.members.handler.app.handler` unwraps
    it and emits a 202 with the SAME ``{success:true, data}`` envelope every other 2xx uses
    (``success`` is True because 202 is in the 2xx range). Keeping it a thin marker (not a new
    response path) means the edge stays uniform — only the status code differs.
    """

    data: Any


# ── Response shaping (handler-layer adapter concern) ──────────────────────────────────


_CORS_HEADERS: dict[str, str] = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Headers": "Content-Type,Authorization",
    "Access-Control-Allow-Methods": "GET,POST,PUT,PATCH,DELETE,OPTIONS",
}


def _json_default(obj: Any) -> Any:
    """`json.dumps` fallback for types the stdlib encoder can't handle.

    DynamoDB returns every number as a :class:`decimal.Decimal` (boto3's resource client),
    which `json.dumps` refuses to serialize (`TypeError: Object of type Decimal is not JSON
    serializable`) — so a member READ whose items carry any numeric attribute would crash
    the response and surface as a 502. Convert a `Decimal` to an `int` when it is integral
    (e.g. a year, a count) else to a `float`, so the JSON body mirrors the source number
    without a spurious ``.0``. Any other unexpected type falls through to a `TypeError`
    (fail loud in tests rather than silently coerce).
    """
    if isinstance(obj, Decimal):
        # Integral Decimals -> int (no trailing .0); fractional -> float.
        return int(obj) if obj == obj.to_integral_value() else float(obj)
    raise TypeError(f"Object of type {obj.__class__.__name__} is not JSON serializable")


def _response(status: int, payload: Mapping[str, Any]) -> dict:
    """Build an API Gateway proxy response with the platform envelope + CORS headers.

    Platform API response & error standard v1.0 (steering `37`): every response carries a
    ``success`` boolean DERIVED from the HTTP status range (2xx → ``true``, else ``false``) so
    the body shape matches the Flask/ZZP plane — success ``{success:true, data}``, error
    ``{success:false, error, code?, ...}`` — while the real HTTP status stays authoritative.
    ``success`` is prepended so it always appears (a caller ``payload`` never needs to set it).

    Every response carries the same CORS headers so a browser client can read it (including the
    401/403 error envelopes below); the body is always well-formed JSON. Uses
    :func:`_json_default` so DynamoDB ``Decimal`` numbers serialize (else a read carrying any
    number 502s — `Decimal is not JSON serializable`).
    """
    body: dict[str, Any] = {"success": 200 <= status < 300}
    body.update(payload)
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json", **_CORS_HEADERS},
        "body": json.dumps(body, default=_json_default),
    }


def _error(
    status: int,
    message: str,
    *,
    code: str | None = None,
    params: Mapping[str, Any] | None = None,
    **extra: Any,
) -> dict:
    """Shape a JSON error envelope ``{success:false, error, code?, params?, ...}``.

    ``code`` is a stable, machine-readable identifier that IS a key in the frontend's existing
    ``errors``/``validation`` i18n namespaces (v1.0, steering `37`); the SPA maps it to localized
    NL/EN copy, with ``message`` (English) as the dev/last-resort fallback. ``params`` carries
    interpolation values for that copy. ``extra`` still carries the structured details the edge
    already returns — ``errors`` (422 per-field) / ``reasons`` (409 transition denials).
    """
    payload: dict[str, Any] = {"error": message}
    if code is not None:
        payload["code"] = code
    if params:
        payload["params"] = dict(params)
    payload.update(extra)
    return _response(status, payload)


def _field_errors_array(errors: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Shape a domain ``{field: FieldError}`` map into the RFC 9457 ``errors`` array (v1.0).

    Each entry is ``{field, code, params?, detail}`` (steering `37`). ``field`` is the dotted
    field key; ``code`` is the machine i18n key the SPA localizes; ``detail`` is the English
    fallback. Tolerant of a legacy bare-string value (wrapped as ``{field, detail}`` with the
    generic ``errors.api.badRequest`` code) so a caller that has not migrated still serializes.
    """
    array: list[dict[str, Any]] = []
    for field_key, value in errors.items():
        if isinstance(value, FieldError):
            array.append(value.as_entry(field_key=str(field_key)))
        else:  # defensive: a not-yet-migrated string reason
            array.append(
                {"field": str(field_key), "code": "errors.api.badRequest", "detail": str(value)}
            )
    return array


def _reasons_array(reasons: Any) -> list[dict[str, Any]]:
    """Shape a :class:`TransitionDenied` ``reasons`` sequence into the RFC 9457 array (v1.0).

    Each entry is ``{code, params?, detail}`` (no ``field`` — a transition denial is not tied to
    one input field). Today the domain emits reasons as plain English strings (config-driven
    guard messages), so each is wrapped under the shared ``errors.transition.denied`` code with
    the string as ``detail``; a :class:`FieldError` reason (future) passes through via
    ``as_entry``. Tolerant of a single string or a non-sequence.
    """
    if isinstance(reasons, (str, bytes)):
        reasons = [reasons]
    array: list[dict[str, Any]] = []
    for reason in reasons or ():
        if isinstance(reason, FieldError):
            array.append(reason.as_entry())
        else:
            array.append({"code": "errors.transition.denied", "detail": str(reason)})
    return array


__all__ = [
    "_CORS_HEADERS",
    "AcceptedResult",
    "ParsedRequest",
    "_error",
    "_field_errors_array",
    "_json_default",
    "_parse_request",
    "_reasons_array",
    "_response",
]
