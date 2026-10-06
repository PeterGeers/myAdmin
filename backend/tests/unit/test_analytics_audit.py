"""
Unit tests for services/analytics_audit.py (member-analytics task 10.1, Design C7).

Covers the metadata-only audit record for CSV export / PDF-label generate / SES mail
send:
  - the record has exactly the C7 shape
    ``{ actor, timestamp, tenant, set_key, filter_summary, record_count, output_kind }``;
  - ``output_kind`` is validated against the three audited actions;
  - a missing tenant is refused (no silent default — R8.2 adjacent);
  - ``record_count`` is normalized (non-negative int, or None);
  - the filter summary is PII-sanitized: PII-looking keys are dropped and scalar
    values are reduced to a presence/type descriptor, never echoed (R8.3);
  - ``log_analytics_output`` emits through the platform's structured access log
    (``log_successful_access``) with the C7 record as details.

Validates: Requirements R8.1, R8.3
"""
from unittest.mock import patch

import pytest

from services.analytics_audit import (
    VALID_OUTPUT_KINDS,
    build_analytics_audit_record,
    log_analytics_output,
    sanitize_filter_summary,
)


class TestBuildAnalyticsAuditRecord:
    """The C7 record shape + validation (pure)."""

    def test_build_record_has_exactly_the_c7_shape(self):
        record = build_analytics_audit_record(
            actor="exporter@example.com",
            tenant="test-tenant",
            output_kind="csv_export",
            set_key="members-per-type",
            record_count=42,
            filter_summary={"membership_type": "gold"},
        )
        assert set(record.keys()) == {
            "actor",
            "timestamp",
            "tenant",
            "set_key",
            "filter_summary",
            "record_count",
            "output_kind",
        }
        assert record["actor"] == "exporter@example.com"
        assert record["tenant"] == "test-tenant"
        assert record["output_kind"] == "csv_export"
        assert record["set_key"] == "members-per-type"
        assert record["record_count"] == 42
        # ISO-8601 UTC timestamp.
        assert record["timestamp"].endswith("+00:00")

    @pytest.mark.parametrize("kind", sorted(VALID_OUTPUT_KINDS))
    def test_build_record_accepts_each_valid_output_kind(self, kind):
        record = build_analytics_audit_record(
            actor="a@example.com",
            tenant="t",
            output_kind=kind,
            set_key=None,
            record_count=0,
        )
        assert record["output_kind"] == kind

    def test_build_record_rejects_unknown_output_kind(self):
        with pytest.raises(ValueError, match="output_kind"):
            build_analytics_audit_record(
                actor="a@example.com",
                tenant="t",
                output_kind="delete_all",
                set_key=None,
                record_count=0,
            )

    def test_build_record_rejects_missing_tenant(self):
        """No silent default for tenant — a record with no tenant is not isolated."""
        with pytest.raises(ValueError, match="tenant"):
            build_analytics_audit_record(
                actor="a@example.com",
                tenant="",
                output_kind="csv_export",
                set_key=None,
                record_count=0,
            )

    def test_build_record_normalizes_record_count(self):
        assert (
            build_analytics_audit_record(
                actor="a@example.com", tenant="t",
                output_kind="csv_export", set_key=None, record_count=-5,
            )["record_count"]
            == 0
        )
        assert (
            build_analytics_audit_record(
                actor="a@example.com", tenant="t",
                output_kind="csv_export", set_key=None, record_count="not-a-number",
            )["record_count"]
            is None
        )
        assert (
            build_analytics_audit_record(
                actor="a@example.com", tenant="t",
                output_kind="csv_export", set_key=None, record_count=None,
            )["record_count"]
            is None
        )


class TestSanitizeFilterSummary:
    """The PII guard on the filter summary (R8.3)."""

    def test_none_summary_is_empty_dict(self):
        assert sanitize_filter_summary(None) == {}

    def test_pii_keys_are_dropped_and_counted(self):
        """A filter naming an email/name/address never records the value."""
        summary = sanitize_filter_summary(
            {
                "email": "alice@example.com",
                "korte_naam": "Alice Example",
                "straat": "Main St 1",
                "membership_type": "gold",
            }
        )
        # No PII key survives.
        assert "email" not in summary
        assert "korte_naam" not in summary
        assert "straat" not in summary
        # The non-PII key survives, but only as a presence/type descriptor.
        assert summary["membership_type"] == {"present": True, "type": "str"}
        # The number of dropped keys is recorded (fact-of-filter without the value).
        assert summary["_redacted"] == 3

    def test_no_pii_value_is_ever_echoed(self):
        """Even a non-PII-named key records presence/type, never the raw value."""
        summary = sanitize_filter_summary({"country": "Netherlands"})
        assert "Netherlands" not in str(summary)
        assert summary["country"] == {"present": True, "type": "str"}

    def test_birth_date_is_treated_as_pii(self):
        """A raw DOB is PII and must be dropped (R8.3)."""
        summary = sanitize_filter_summary({"birth_date": "1980-01-01"})
        assert "birth_date" not in summary
        assert "1980-01-01" not in str(summary)
        assert summary["_redacted"] == 1

    def test_list_and_nested_dict_values_are_summarized_structurally(self):
        summary = sanitize_filter_summary(
            {
                "regions": ["noord", "zuid", "oost"],
                "nested": {"a": 1, "b": 2},
            }
        )
        assert summary["regions"] == {"type": "list", "count": 3}
        assert summary["nested"] == {"type": "object", "keys": 2}

    def test_non_dict_filter_is_summarized_not_echoed(self):
        assert sanitize_filter_summary(["a@example.com", "b@example.com"]) == {
            "type": "list",
            "count": 2,
        }
        assert sanitize_filter_summary("gold") == {"type": "str"}


class TestLogAnalyticsOutput:
    """The I/O path delegates to the platform's structured audit log."""

    def test_log_analytics_output_emits_c7_record_through_access_log(self):
        with patch(
            "services.analytics_audit.log_successful_access"
        ) as mock_access_log:
            record = log_analytics_output(
                actor="exporter@example.com",
                actor_roles=["Members_Export"],
                tenant="test-tenant",
                output_kind="ses_mail",
                set_key="clubblad-paper",
                record_count=128,
                filter_summary={"clubblad": "Papier", "email": "leak@example.com"},
            )

        mock_access_log.assert_called_once()
        _, kwargs = mock_access_log.call_args
        assert kwargs["user_email"] == "exporter@example.com"
        assert kwargs["user_roles"] == ["Members_Export"]
        assert kwargs["operation"] == "member_analytics_output"
        # The details ARE the C7 record, PII-sanitized.
        details = kwargs["details"]
        assert details == record
        assert details["output_kind"] == "ses_mail"
        assert details["record_count"] == 128
        assert details["set_key"] == "clubblad-paper"
        # The PII-named filter key was dropped before logging.
        assert "email" not in details["filter_summary"]
        assert "leak@example.com" not in str(details)
        assert details["filter_summary"]["clubblad"] == {"present": True, "type": "str"}

    def test_log_analytics_output_defaults_roles_to_empty_list(self):
        with patch(
            "services.analytics_audit.log_successful_access"
        ) as mock_access_log:
            log_analytics_output(
                actor="a@example.com",
                actor_roles=None,
                tenant="t",
                output_kind="pdf_labels",
            )
        _, kwargs = mock_access_log.call_args
        assert kwargs["user_roles"] == []
