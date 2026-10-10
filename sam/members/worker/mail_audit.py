"""
The SAM-plane **mail-output audit sink** (R4, pivot-output-actions task 4.3, design §8) — a
metadata-only ``ses_mail`` audit record emitted by the worker after a successful send.

Why a SAM-plane sink and not the Flask ``services.analytics_audit.log_analytics_output``
----------------------------------------------------------------------------------------
The Flask helper (``backend/src/services/analytics_audit.py``) is the canonical
``log_analytics_output`` on the MySQL plane — but it imports ``auth.cognito_utils`` and emits
through the Flask access log, and the SAM/Lambda plane is deliberately Flask-free
(``sam/tests/test_import_boundary_no_flask.py``). So the worker emits the SAME record SHAPE and
honours the SAME PII guarantee here, through a structured CloudWatch log line (``ACCESS_LOG:``,
tagged ``operation="member_analytics_output"``) — the SAM counterpart of the platform's
structured audit log, with no Flask dependency.

Metadata-only (design §8)
-------------------------
The record carries only the SHAPE of the send — actor (the run id, attribution only), tenant,
set, recipient COUNT, output kind, and a UTC timestamp. It NEVER carries a subject, a body,
merge values, or recipient addresses. ``VALID_OUTPUT_KINDS`` / ``AUDIT_OPERATION`` mirror the
Flask helper so records from both planes are greppable as one group.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

__all__ = [
    "AUDIT_OPERATION",
    "VALID_OUTPUT_KINDS",
    "build_mail_audit_record",
    "log_analytics_output",
]

#: The output kinds the mail worker audits. Mirrors the Flask helper's set so both planes
#: classify output actions identically; the worker only ever emits ``ses_mail``.
VALID_OUTPUT_KINDS = frozenset({"csv_export", "pdf_labels", "ses_mail"})

#: The operation label the structured line is tagged with (same as the Flask helper), so the
#: records are greppable as one group across both planes.
AUDIT_OPERATION = "member_analytics_output"


def build_mail_audit_record(
    *,
    actor: str,
    tenant: str,
    output_kind: str,
    set_key: str | None,
    record_count: int | None,
) -> dict[str, Any]:
    """Build the metadata-only audit record (pure — no I/O), rejecting an unknown kind / tenant.

    Returns the C7-shaped record ``{actor, timestamp, tenant, set_key, record_count,
    output_kind}`` with a UTC ISO-8601 ``timestamp`` stamped here. There is NO ``filter_summary``
    and NO member data by construction — the worker only knows ids + counts.

    Raises:
        ValueError: ``output_kind`` is not one of :data:`VALID_OUTPUT_KINDS`, or ``tenant`` is
            falsy (an audit record with no tenant is not tenant-isolated — refused).
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
        "record_count": normalized_count,
        "output_kind": output_kind,
    }


def log_analytics_output(
    *,
    actor: str,
    actor_roles: list[str] | None = None,
    tenant: str,
    output_kind: str,
    set_key: str | None = None,
    record_count: int | None = None,
) -> dict[str, Any]:
    """Audit one mail-output action (metadata only, design §8) — the worker's audit callable.

    Signature-compatible with the Flask ``services.analytics_audit.log_analytics_output`` so the
    worker service depends on the SHAPE, not the plane. Builds the metadata-only record
    (:func:`build_mail_audit_record`) and emits it as a structured CloudWatch log line tagged
    ``operation="member_analytics_output"``. ``actor_roles`` is accepted for signature parity
    (the worker runs unattended — there is no user role) and is not recorded. Returns the record.
    """
    record = build_mail_audit_record(
        actor=actor,
        tenant=tenant,
        output_kind=output_kind,
        set_key=set_key,
        record_count=record_count,
    )
    logger.info(
        "ACCESS_LOG: %s",
        json.dumps(
            {"operation": AUDIT_OPERATION, "details": record},
            default=str,
            sort_keys=True,
        ),
    )
    return record
