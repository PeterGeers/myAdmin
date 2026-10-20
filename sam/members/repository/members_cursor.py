"""
Members read-path **cursor codec** (spec 02, Task 1.17 / Requirement 25).

The Members table pages with DynamoDB-native **cursor paging**: a query returns a
``LastEvaluatedKey`` dict (the server-side position to resume from), which the SAM read path
hands to the frontend as an OPAQUE wire string the client round-trips back on the next
request. This module is the single place that serializes that key dict to the wire string and
decodes it back to an ``ExclusiveStartKey`` — kept out of the thin route (steering 35) and
reused by the repository + domain so encode and decode can never drift.

Wire format: ``base64url(JSON(key_dict))`` — URL-safe base64 of the compact JSON encoding of
the DynamoDB key mapping. Opaque to the client (it never parses it); the server is the only
thing that reads its contents.

**Tenant isolation (Property 1).** The decoded key is NOT trusted blindly: it carries the
partition key (``tenant_id``), and a client could tamper with it to try to resume a Query in
ANOTHER tenant's partition. :func:`decode_cursor` therefore takes the caller's authoritative
``tenant_id`` (resolved from the verified token, never the body) and REJECTS a cursor whose
partition key is absent or does not match — so a cursor can never carry a read across tenant
partitions. A malformed / corrupt cursor is likewise rejected (a stale or hand-edited string
is a client error, not a silent cross-tenant read).

DynamoDB numbers deserialize as :class:`~decimal.Decimal`; the codec normalizes an integral
Decimal back to ``int`` on decode so the resumed ``ExclusiveStartKey`` matches the shape boto3
produced (the Members table keys are strings today, but the codec stays number-safe so a
numeric key attribute round-trips cleanly).
"""

from __future__ import annotations

import base64
import binascii
import json
from collections.abc import Mapping
from decimal import Decimal
from typing import Any

from sam.members.repository import table_design as td

__all__ = [
    "CursorError",
    "decode_cursor",
    "encode_cursor",
]


class CursorError(ValueError):
    """Raised when a cursor cannot be decoded or fails the tenant-isolation check.

    Either the wire string is not a well-formed ``base64url(JSON(object))``, or the decoded key
    does not carry the caller's tenant partition key (a tampered / stale cursor). The edge maps
    this to a caller-safe 400 — a cursor is client-supplied, so a bad one is a bad request, not
    a server fault, and never a silent cross-tenant read.
    """


def _json_default(value: Any) -> Any:
    """``json.dumps`` fallback: encode a DynamoDB ``Decimal`` as a JSON number.

    DynamoDB (boto3 resource client) returns every number as a :class:`~decimal.Decimal`, which
    the stdlib JSON encoder refuses. An integral Decimal encodes as an ``int`` (no trailing
    ``.0``); a fractional one as a ``float``, so the key round-trips without a spurious decimal
    artefact. Any other unexpected type fails loud (a key attribute is only ever S/N/B).
    """
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    raise TypeError(f"cursor key carries a non-serializable {type(value).__name__}")


def encode_cursor(last_evaluated_key: Mapping[str, Any] | None) -> str | None:
    """Serialize a DynamoDB ``LastEvaluatedKey`` to the opaque wire cursor string.

    Returns ``None`` when there is no ``LastEvaluatedKey`` (the last query exhausted the result
    — the final page), so the caller surfaces "no next page" (Next disabled, R25.5/R25.6). A
    present key is encoded as ``base64url(JSON(key))`` — opaque to the client, which only
    round-trips it back on the next request.
    """
    if not last_evaluated_key:
        return None
    payload = json.dumps(
        dict(last_evaluated_key), default=_json_default, separators=(",", ":")
    ).encode("utf-8")
    return base64.urlsafe_b64encode(payload).decode("ascii")


def _decimalize_integral(value: Any) -> Any:
    """Normalize a decoded JSON number back toward the boto3 key shape.

    JSON decodes a whole number to ``int`` and a fractional one to ``float``. boto3's resource
    client expects numeric key values as ``Decimal`` on a Query ``ExclusiveStartKey``, so a
    numeric value is coerced to ``Decimal`` (via ``str`` to avoid binary-float artefacts).
    Strings (the Members table's actual key type) pass through untouched.
    """
    if isinstance(value, bool):  # bool is an int subclass — never a key number
        return value
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, float):
        return Decimal(str(value))
    return value


def decode_cursor(cursor: str | None, tenant_id: str) -> dict[str, Any] | None:
    """Decode the opaque wire cursor back to a DynamoDB ``ExclusiveStartKey``, tenant-checked.

    Returns ``None`` for an absent/blank cursor (the first page — start from the beginning).
    Otherwise decodes ``base64url(JSON(object))`` and ENFORCES tenant isolation: the decoded
    key MUST carry the partition key (:data:`table_design.PARTITION_KEY_ATTR`) equal to the
    caller's authoritative ``tenant_id``. A missing / mismatched partition key — a tampered or
    stale cursor — raises :class:`CursorError` (mapped to a 400), so a cursor can never resume a
    Query in another tenant's partition (Property 1).

    Args:
        cursor: The opaque wire string the client round-tripped back, or ``None`` for page 1.
        tenant_id: The caller's authoritative tenant (from the verified token, never the body).

    Returns:
        The ``ExclusiveStartKey`` mapping to hand DynamoDB, or ``None`` for the first page.

    Raises:
        CursorError: The cursor is malformed, is not a JSON object, or carries a partition key
            that is absent or does not match ``tenant_id``.
    """
    if not cursor:
        return None
    if not tenant_id:
        # Defensive: a decode is only meaningful against a resolved tenant.
        raise CursorError("a tenant is required to decode a cursor (Property 1)")
    try:
        raw = base64.urlsafe_b64decode(cursor.encode("ascii"))
        decoded = json.loads(raw.decode("utf-8"))
    except (ValueError, binascii.Error, UnicodeDecodeError) as exc:
        raise CursorError("cursor is malformed") from exc

    if not isinstance(decoded, dict):
        raise CursorError("cursor must decode to a key object")

    key_tenant = decoded.get(td.PARTITION_KEY_ATTR)
    if key_tenant != tenant_id:
        # The cursor's partition key must be the caller's own tenant — a tampered cursor that
        # names another tenant (or omits the partition key) can never resume there (Property 1).
        raise CursorError("cursor does not belong to the active tenant")

    return {k: _decimalize_integral(v) for k, v in decoded.items()}
