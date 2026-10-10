"""
Member Analytics — output audit log (member-analytics task 10.1, Design C7 / R8.1, R8.3).

Every **CSV export**, **PDF-label generate**, and **SES mail send** on the Member
Analytics surface must leave an audit trail: *who* produced *what kind* of output,
*for which tenant / set*, over *how many records*, under *which filter* — and nothing
more. The audit record is **metadata only**; it must never carry member PII (names,
emails, addresses).

Design C7 said to **reuse the platform's existing audit mechanism** rather than invent
a new one. The established pattern is :func:`auth.cognito_utils.log_successful_access`,
which emits a structured JSON line (``ACCESS_LOG:``) to CloudWatch — the same mechanism
the SysAdmin tenant-bypass audit reuses (``auth.tenant_context._log_sysadmin_bypass``).
This module is a thin, typed wrapper around it that:

  1. fixes the C7 record shape
     (``{ actor, timestamp, tenant, set_key, filter_summary, record_count, output_kind }``);
  2. validates ``output_kind`` against the three audited actions; and
  3. **sanitizes** ``filter_summary`` so a caller can never leak PII into the log by
     accident — only the metadata *shape* of a filter is recorded, with any
     PII-looking keys dropped (R8.3).

The ``timestamp`` is produced here (UTC, ISO-8601) so every audited action is stamped
consistently regardless of caller.

Why a shared helper and not an inline log line: the audited analytics outputs are the
**client-side** CSV / PDF generators, which report their action through the lightweight
analytics-audit route (``routes/members_analytics_audit.py``, same spec task). They funnel
through this one helper so the record shape and the PII guarantee are identical across every
output path. (The interactive Members SES *mail* send is NO LONGER a Flask route — it was
retired to the SAM plane per the mail spec, task 4.1 — so its audit now lives on the SAM
plane, not here.)

Reference: .kiro/specs/Members/member-analytics/design.md (C7); requirements R8.1, R8.3.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from auth.cognito_utils import log_successful_access

# The three output actions C7 audits. A caller must name exactly one of these; an
# unknown kind is rejected so the log can never fill with free-form action labels.
VALID_OUTPUT_KINDS = frozenset({"csv_export", "pdf_labels", "ses_mail"})

# The operation label the structured access log is tagged with, so these records are
# greppable as a group (``operation == "member_analytics_output"``).
AUDIT_OPERATION = "member_analytics_output"

# Substrings that mark a filter key as potentially PII-bearing. ``filter_summary`` is
# meant to describe WHICH fields a user filtered on and the SHAPE of the values, never
# the member data itself. Any key whose name hints at direct personal data is dropped
# entirely (R8.3) — defense-in-depth so a careless caller cannot leak PII through the
# audit log. Matching is case-insensitive and substring-based.
_PII_KEY_HINTS = (
    "name",
    "naam",  # name (nl)
    "email",
    "e_mail",
    "mail",
    "address",
    "adres",
    "straat",  # street (nl)
    "postcode",
    "postal",
    "zip",
    "phone",
    "tel",
    "woonplaats",  # city (nl)
    "city",
    "birth",  # birth_date etc. — a raw DOB is PII
    "dob",
    "iban",
    "bsn",  # nl national id
    "ssn",
)


def _looks_like_pii_key(key: str) -> bool:
    """True when a filter key name hints at direct personal data (R8.3)."""
    lowered = key.lower()
    return any(hint in lowered for hint in _PII_KEY_HINTS)


def sanitize_filter_summary(raw: Any) -> dict[str, Any]:
    """Reduce an arbitrary filter object to a PII-free metadata summary.

    The goal (R8.3) is to record *which* fields were filtered and the *shape* of the
    filter, never the member values themselves. The result is safe to persist in an
    audit log:

      - a ``dict`` is kept key-by-key, but
          * any key that looks PII-bearing (:func:`_looks_like_pii_key`) is **dropped**,
            replaced by a redaction count under ``_redacted`` so the fact that a filter
            was applied is still visible without the value;
          * a scalar value (str / number / bool / None) is replaced by a type/length
            descriptor, NOT the value — e.g. ``{"present": true, "type": "str"}`` —
            because even a non-PII-named key could hold a copied-in personal value;
          * a list value is summarized by its length only;
          * a nested dict is summarized by its key count only (not recursed into, to
            avoid deep PII leakage).
      - a non-dict (list / scalar / ``None``) is summarized structurally
        (``{"type": ..., "count": ...}``), never echoed.

    This deliberately records *metadata about the filter*, not the filter's data. A
    caller that wants richer, known-safe metadata can pass an already-shaped dict of
    safe descriptors; it still passes through the PII-key guard.
    """
    if raw is None:
        return {}

    if not isinstance(raw, dict):
        # A bare list / scalar filter → structural summary only.
        if isinstance(raw, (list, tuple, set)):
            return {"type": "list", "count": len(raw)}
        return {"type": type(raw).__name__}

    summary: dict[str, Any] = {}
    redacted = 0

    for key, value in raw.items():
        key_str = str(key)
        if _looks_like_pii_key(key_str):
            redacted += 1
            continue

        if isinstance(value, dict):
            summary[key_str] = {"type": "object", "keys": len(value)}
        elif isinstance(value, (list, tuple, set)):
            summary[key_str] = {"type": "list", "count": len(value)}
        else:
            # Record presence + type, never the raw value — a non-PII-named key may
            # still hold a copied-in personal value.
            summary[key_str] = {
                "present": value is not None and value != "",
                "type": type(value).__name__,
            }

    if redacted:
        summary["_redacted"] = redacted

    return summary


def build_analytics_audit_record(
    *,
    actor: str,
    tenant: str,
    output_kind: str,
    set_key: str | None,
    record_count: int | None,
    filter_summary: Any = None,
) -> dict[str, Any]:
    """Build the C7 audit record (pure — no I/O), with the PII guard applied.

    The returned dict is exactly the C7 shape
    ``{ actor, timestamp, tenant, set_key, filter_summary, record_count, output_kind }``.
    ``timestamp`` is stamped here (UTC, ISO-8601). ``filter_summary`` is run through
    :func:`sanitize_filter_summary` so no PII can enter the record (R8.3).

    Raises:
        ValueError: if ``output_kind`` is not one of :data:`VALID_OUTPUT_KINDS`, or if
            ``tenant`` is falsy (an audit record with no tenant is not tenant-isolated
            and is therefore refused — R8.2 adjacent).
    """
    if output_kind not in VALID_OUTPUT_KINDS:
        raise ValueError(
            f"Unknown analytics output_kind {output_kind!r}; "
            f"expected one of {sorted(VALID_OUTPUT_KINDS)}"
        )
    if not tenant:
        raise ValueError("analytics audit record requires a tenant (no silent default)")

    normalized_count: int | None
    if record_count is None:
        normalized_count = None
    else:
        try:
            normalized_count = max(0, int(record_count))
        except (TypeError, ValueError):
            normalized_count = None

    return {
        "actor": actor,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "tenant": tenant,
        "set_key": set_key,
        "filter_summary": sanitize_filter_summary(filter_summary),
        "record_count": normalized_count,
        "output_kind": output_kind,
    }


def log_analytics_output(
    *,
    actor: str,
    actor_roles: list[str] | None,
    tenant: str,
    output_kind: str,
    set_key: str | None = None,
    record_count: int | None = None,
    filter_summary: Any = None,
) -> dict[str, Any]:
    """Audit one analytics output action (CSV / PDF / mail), metadata only (R8.1/R8.3).

    Builds the C7 record (:func:`build_analytics_audit_record`) and emits it through the
    platform's established structured audit log
    (:func:`auth.cognito_utils.log_successful_access`), tagged
    ``operation="member_analytics_output"`` so the records are greppable as a group.
    The C7 fields ride in the access log's ``details`` payload.

    Returns the record that was logged (handy for tests and for a route to echo back a
    confirmation without re-deriving it). Raises ``ValueError`` on an invalid
    ``output_kind`` / missing tenant (see :func:`build_analytics_audit_record`).
    """
    record = build_analytics_audit_record(
        actor=actor,
        tenant=tenant,
        output_kind=output_kind,
        set_key=set_key,
        record_count=record_count,
        filter_summary=filter_summary,
    )

    log_successful_access(
        user_email=actor,
        user_roles=actor_roles or [],
        operation=AUDIT_OPERATION,
        details=record,
    )

    return record
