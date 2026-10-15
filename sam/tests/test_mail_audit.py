"""
Direct tests for the SAM-plane mail-output audit sink
(:mod:`sam.members.worker.mail_audit`, pivot-output-actions task 4.3, design §8).

Covers two surfaces:

1. :func:`build_mail_audit_record` — the pure, metadata-only C7 record shape
   (``{actor, timestamp, tenant, set_key, record_count, output_kind}``), the kind/tenant
   validation guards, and count normalization. This is the PII guarantee by construction: the
   builder has no parameter that could carry a subject/body/address/merge value.

2. :func:`log_analytics_output` — the emitting callable. Asserts it emits ONE structured
   ``ACCESS_LOG:`` line tagged ``operation="member_analytics_output"`` carrying the C7 record,
   and that ``actor_roles`` drives the top-level ``attended`` flag (True when a role is supplied,
   False for the worker's always-unattended empty-list case) WITHOUT folding roles into the C7
   record — the record shape must stay identical across the Flask and SAM planes.
"""

from __future__ import annotations

import json
import logging

import pytest

from sam.members.worker.mail_audit import (
    AUDIT_OPERATION,
    VALID_OUTPUT_KINDS,
    build_mail_audit_record,
    log_analytics_output,
)

# The C7 record shape, as a set, so an added/removed field is caught (not just a value drift).
_C7_RECORD_KEYS = {
    "actor",
    "timestamp",
    "tenant",
    "set_key",
    "record_count",
    "output_kind",
}


# ── build_mail_audit_record: the pure C7 record ─────────────────────────────────────────


class TestBuildMailAuditRecord:
    def test_build_record_has_exactly_the_c7_shape(self):
        record = build_mail_audit_record(
            actor="run-123",
            tenant="h-dcn",
            output_kind="ses_mail",
            set_key="set-abc",
            record_count=42,
        )
        # Exactly the C7 fields — no filter_summary (worker only knows ids + counts), and
        # crucially no roles/subject/body/address — PII-free by construction.
        assert set(record) == _C7_RECORD_KEYS
        assert record["actor"] == "run-123"
        assert record["tenant"] == "h-dcn"
        assert record["set_key"] == "set-abc"
        assert record["record_count"] == 42
        assert record["output_kind"] == "ses_mail"

    def test_build_record_stamps_utc_iso8601_timestamp(self):
        record = build_mail_audit_record(
            actor="run-1",
            tenant="h-dcn",
            output_kind="ses_mail",
            set_key=None,
            record_count=None,
        )
        # Stamped here, UTC — parseable as an aware ISO-8601 instant.
        from datetime import datetime

        parsed = datetime.fromisoformat(record["timestamp"])
        assert parsed.utcoffset() is not None  # tz-aware (UTC)

    def test_build_record_rejects_unknown_output_kind(self):
        with pytest.raises(ValueError, match="Unknown analytics output_kind"):
            build_mail_audit_record(
                actor="run-1",
                tenant="h-dcn",
                output_kind="smoke_signal",
                set_key=None,
                record_count=1,
            )

    def test_build_record_refuses_falsy_tenant(self):
        # An audit record with no tenant is not tenant-isolated — refused (no silent default).
        with pytest.raises(ValueError, match="requires a tenant"):
            build_mail_audit_record(
                actor="run-1",
                tenant="",
                output_kind="ses_mail",
                set_key=None,
                record_count=1,
            )

    @pytest.mark.parametrize(
        ("raw_count", "expected"),
        [
            (None, None),
            (0, 0),
            (5, 5),
            (-7, 0),  # negative clamps to 0
            ("13", 13),  # numeric string coerces
            ("not-a-number", None),  # junk → None, never raises
            (3.9, 3),  # float truncates via int()
        ],
    )
    def test_build_record_normalizes_record_count(self, raw_count, expected):
        record = build_mail_audit_record(
            actor="run-1",
            tenant="h-dcn",
            output_kind="ses_mail",
            set_key=None,
            record_count=raw_count,
        )
        assert record["record_count"] == expected

    def test_valid_output_kinds_mirror_the_flask_helper_set(self):
        # The SAM sink classifies output actions identically to the Flask helper so records
        # from both planes are greppable as one group.
        assert VALID_OUTPUT_KINDS == frozenset(
            {"csv_export", "pdf_labels", "ses_mail"}
        )


# ── log_analytics_output: the emitting callable ─────────────────────────────────────────


def _access_log_payloads(caplog) -> list[dict]:
    """Parse every structured ``ACCESS_LOG:`` JSON payload emitted during the test."""
    payloads = []
    for rec in caplog.records:
        msg = rec.getMessage()
        if msg.startswith("ACCESS_LOG: "):
            payloads.append(json.loads(msg[len("ACCESS_LOG: ") :]))
    return payloads


class TestLogAnalyticsOutput:
    def test_emits_one_structured_access_log_line_with_the_record(self, caplog):
        with caplog.at_level(logging.INFO, logger="sam.members.worker.mail_audit"):
            returned = log_analytics_output(
                actor="run-123",
                tenant="h-dcn",
                output_kind="ses_mail",
                set_key="set-abc",
                record_count=42,
            )

        payloads = _access_log_payloads(caplog)
        assert len(payloads) == 1
        payload = payloads[0]
        assert payload["operation"] == AUDIT_OPERATION
        # The C7 record rides in details, unchanged in shape, and is what the call returns.
        assert set(payload["details"]) == _C7_RECORD_KEYS
        assert payload["details"] == returned
        assert payload["details"]["output_kind"] == "ses_mail"

    def test_actor_roles_absent_marks_the_line_unattended(self, caplog):
        # The worker's normal case: no roles → attended=False, and roles are NOT in the record.
        with caplog.at_level(logging.INFO, logger="sam.members.worker.mail_audit"):
            log_analytics_output(
                actor="run-1",
                actor_roles=[],
                tenant="h-dcn",
                output_kind="ses_mail",
                set_key=None,
                record_count=0,
            )

        payload = _access_log_payloads(caplog)[0]
        assert payload["attended"] is False
        # Roles never leak into the C7 record — shape parity with the Flask plane is preserved.
        assert "actor_roles" not in payload["details"]
        assert set(payload["details"]) == _C7_RECORD_KEYS

    def test_actor_roles_present_marks_the_line_attended(self, caplog):
        # An attended caller (roles supplied) is distinguishable in the audit log via `attended`,
        # yet the role VALUES are still not recorded in the metadata-only record.
        with caplog.at_level(logging.INFO, logger="sam.members.worker.mail_audit"):
            log_analytics_output(
                actor="user@example.com",
                actor_roles=["members_mail"],
                tenant="h-dcn",
                output_kind="ses_mail",
                set_key="set-abc",
                record_count=5,
            )

        payload = _access_log_payloads(caplog)[0]
        assert payload["attended"] is True
        assert "actor_roles" not in payload["details"]
        # The whole structured line carries no role VALUE either (metadata only).
        assert "members_mail" not in json.dumps(payload)

    def test_actor_roles_defaults_to_unattended_when_omitted(self, caplog):
        # Default (parameter omitted) behaves like the unattended worker case.
        with caplog.at_level(logging.INFO, logger="sam.members.worker.mail_audit"):
            log_analytics_output(
                actor="run-1",
                tenant="h-dcn",
                output_kind="ses_mail",
            )

        assert _access_log_payloads(caplog)[0]["attended"] is False

    def test_invalid_kind_raises_before_emitting(self, caplog):
        with caplog.at_level(logging.INFO, logger="sam.members.worker.mail_audit"):
            with pytest.raises(ValueError, match="Unknown analytics output_kind"):
                log_analytics_output(
                    actor="run-1",
                    tenant="h-dcn",
                    output_kind="smoke_signal",
                )
        # Nothing was logged — the guard fires before the emit.
        assert _access_log_payloads(caplog) == []
