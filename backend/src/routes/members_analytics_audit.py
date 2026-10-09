"""
Member Analytics — client-side output audit route (member-analytics task 10.1, Design C7).

Two of the three audited analytics outputs happen **entirely in the browser**: the CSV
export (``csvExport.ts``) and the PDF address-label generate (jsPDF, ``addressLabelService``).
They never touch the server, so C7 calls for a **small audit signal from the client** —
a lightweight POST that records a metadata-only audit record. (The interactive Members SES
mail send is no longer a Flask route — it was retired to the SAM plane per the mail spec,
task 4.1 — and audits itself on the SAM plane; it does NOT use this route.)

This route is deliberately thin: it validates the ``output_kind`` is a client-side one
(``csv_export`` / ``pdf_labels``), resolves the tenant from the verified auth context
(never from the body — R8.2), and funnels through the shared
:func:`services.analytics_audit.log_analytics_output` helper so the record shape and the
PII guarantee match the server-side path exactly.

Capability gate (R4.12 / Design C7): ``members:export`` — the same capability that gates
every member export surface (CSV / PDF / mail). A caller who may not export cannot write
an export audit record.

Privacy (R8.3): the body carries **metadata only** — ``set_key``, ``record_count``, and
an optional ``filter_summary`` that is sanitized server-side before it is logged. The
route never accepts or logs member rows / PII.

Reference: .kiro/specs/Members/member-analytics/design.md (C7); requirements R8.1, R8.3.
"""

import logging

from flask import Blueprint, jsonify, request
from flask.typing import ResponseReturnValue

from auth.cognito_utils import cognito_required
from auth.tenant_context import get_current_tenant

logger = logging.getLogger(__name__)

members_analytics_audit_bp = Blueprint("members_analytics_audit", __name__)

# Same capability that gates every member export surface (CSV / PDF / mail), per C7.
CAP_MEMBERS_EXPORT = "members:export"

# The client-side output kinds this route accepts. The server-side SES mail send audits
# itself in-process and must NOT be reported through here (so a client can never forge a
# "mail sent" audit record without actually sending).
_CLIENT_OUTPUT_KINDS = frozenset({"csv_export", "pdf_labels"})


@members_analytics_audit_bp.route("/api/members/analytics-audit", methods=["POST"])
@cognito_required(required_permissions=[CAP_MEMBERS_EXPORT])
def record_analytics_output(user_email, user_roles) -> ResponseReturnValue:
    """Record an audit entry for a client-side CSV export or PDF-label generate.

    Authorization: ``members:export`` capability required (R4.12).

    Request body (metadata only — NO member rows / PII)::

        {
            "output_kind": "csv_export" | "pdf_labels",   # required
            "set_key": "members-per-type",                 # optional audit label
            "record_count": 128,                            # optional, >= 0
            "filter_summary": { ... }                       # optional, sanitized server-side
        }

    Returns ``{ "success": true, "audit": <logged record> }`` so the client can confirm
    what was recorded (useful for tests); the ``filter_summary`` in the echoed record is
    the PII-sanitized one.
    """
    try:
        # Tenant ALWAYS from the verified auth context — never a body-supplied tenant
        # (R8.2). No tenant => the record would not be tenant-isolated, so refuse.
        tenant = get_current_tenant(request)
        if not tenant:
            return jsonify({"error": "No tenant context"}), 400

        data = request.get_json(silent=True)
        if not data:
            return jsonify({"error": "No data provided"}), 400

        output_kind = (data.get("output_kind") or "").strip()
        if output_kind not in _CLIENT_OUTPUT_KINDS:
            return jsonify(
                {
                    "error": (
                        "output_kind must be one of "
                        f"{sorted(_CLIENT_OUTPUT_KINDS)}"
                    )
                }
            ), 400

        # Delegate to the shared helper — same record shape + PII guard as the SES
        # mail path. ``filter_summary`` is sanitized inside the helper (R8.3).
        from services.analytics_audit import log_analytics_output

        record = log_analytics_output(
            actor=user_email,
            actor_roles=user_roles,
            tenant=tenant,
            output_kind=output_kind,
            set_key=data.get("set_key"),
            record_count=data.get("record_count"),
            filter_summary=data.get("filter_summary"),
        )

        return jsonify({"success": True, "audit": record})

    except Exception as e:  # noqa: BLE001 — route boundary: never leak a 500 stack
        logger.error("Error recording analytics output audit: %s", e)
        return jsonify({"error": "Failed to record audit", "message": str(e)}), 500
