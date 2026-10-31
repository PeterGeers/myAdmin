"""
Property-based tests for EmailVerificationService.

Uses Hypothesis to verify correctness properties from the design document.
Feature: ses-email-verification, Properties 3, 5, 9

Requirements: 2.2, 2.3, 2.4, 3.4, 5.5
Reference: .kiro/specs/ses-email-verification/design.md
"""

import os
import sys
import pytest
from hypothesis import given, strategies as st, settings, HealthCheck, assume
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from services.email_verification_service import (
    EmailVerificationService,
    RESEND_COOLDOWN_SECONDS,
)


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# SES verification states and their expected local mappings
SES_STATUS_MAPPING = {
    "Success": "verified",
    "Pending": "pending",
    "Failed": "failed",
    "TemporaryFailure": "pending",
    "NotStarted": "failed",
}

ses_status_st = st.sampled_from(list(SES_STATUS_MAPPING.keys()))

# Strategy for timestamps relative to "now"
# Generates seconds offset from current time (positive = in the past)
seconds_offset_st = st.floats(
    min_value=0.0,
    max_value=86400.0,  # 0 to 24 hours in the past
    allow_nan=False,
    allow_infinity=False,
)

# Strategy for valid email local parts.
#
# RECONCILED with the hardened `_validate_email` (task 4.1): the validator NARROWS the
# accepted local-part class below the full RFC 5322 set to a deliverable-safe class —
# letters / digits plus the common non-exploit separators (dot / plus / underscore /
# hyphen), alphanumeric-anchored at both ends, no consecutive dots, local part <= 64.
# The old generator drew the full RFC class (`!#$%&'*+/=?^_`{|}~`) and the "valid"
# property asserted those validate True — a direct CONTRADICTION of the hardened
# behavior. We constrain the generator to exactly the accepted class so a generated
# "valid" address is one the hardened validator genuinely accepts.
valid_local_chars = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._+-"
_local_anchor_chars = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
# Alphanumeric-anchored head + body of safe chars + alphanumeric tail; capped so the
# whole local part stays <= 64 and contains no consecutive dots.
# Prototype-pollution keys the hardened validator rejects as a substring (case-insensitive).
# The generator uses alnum + `._+-`, and `__proto__` / `constructor` / `prototype` are all
# drawable from that alphabet, so an unfiltered "genuine" draw can accidentally embed one
# (e.g. `0__PROTO__0`) — which the validator correctly rejects. Exclude them here so a
# generated "valid"/"genuine" address is one the hardened validator genuinely accepts.
_PROTO_KEYS = ("__proto__", "constructor", "prototype")


def _has_proto_key(local: str) -> bool:
    low = local.lower()
    return any(k in low for k in _PROTO_KEYS)


valid_local_part_st = st.builds(
    lambda h, b, t: f"{h}{b}{t}",
    st.text(alphabet=_local_anchor_chars, min_size=1, max_size=1),
    st.text(alphabet=valid_local_chars, min_size=0, max_size=28),
    st.text(alphabet=_local_anchor_chars, min_size=1, max_size=1),
).filter(lambda s: ".." not in s and len(s) <= 30 and not _has_proto_key(s))

# Strategy for valid domain labels (alphanumeric, may contain hyphens but not start/end with them)
domain_label_st = st.from_regex(
    r"[a-zA-Z0-9]([a-zA-Z0-9\-]{0,10}[a-zA-Z0-9])?", fullmatch=True
)

# Strategy for valid TLDs (2+ alpha characters)
tld_st = st.from_regex(r"[a-zA-Z]{2,6}", fullmatch=True)

# Strategy for valid email addresses — a deliverable sender the hardened validator accepts.
valid_email_st = st.builds(
    lambda local, domain, tld: f"{local}@{domain}.{tld}",
    local=valid_local_part_st,
    domain=domain_label_st,
    tld=tld_st,
)

# Strategy for invalid emails - various ways an email can be invalid
invalid_email_no_at_st = st.text(min_size=1, max_size=50).filter(lambda s: "@" not in s)
invalid_email_multiple_at_st = st.builds(
    lambda a, b, c: f"{a}@{b}@{c}",
    a=st.text(min_size=1, max_size=10),
    b=st.text(min_size=1, max_size=10),
    c=st.text(min_size=1, max_size=10),
)
invalid_email_empty_local_st = st.builds(
    lambda domain, tld: f"@{domain}.{tld}",
    domain=domain_label_st,
    tld=tld_st,
)
invalid_email_no_dot_domain_st = st.builds(
    lambda local, domain: f"{local}@{domain}",
    local=valid_local_part_st,
    domain=st.from_regex(r"[a-zA-Z0-9]{1,20}", fullmatch=True),
)
invalid_email_with_space_st = st.builds(
    lambda local, domain, tld: f"{local} @{domain}.{tld}",
    local=valid_local_part_st,
    domain=domain_label_st,
    tld=tld_st,
)


# ---------------------------------------------------------------------------
# Property 3: SES status mapping correctness
# Feature: ses-email-verification, Property 3: SES status mapping correctness
# Validates: Requirements 2.2, 2.3, 2.4
# ---------------------------------------------------------------------------


class TestSesStatusMappingCorrectness:
    """
    Property 3: SES status mapping correctness

    For any SES verification state (Success, Pending, Failed), the check_status
    method SHALL map it to the corresponding local status (verified, pending, failed)
    and persist the mapping to the database.

    Feature: ses-email-verification, Property 3: SES status mapping correctness
    **Validates: Requirements 2.2, 2.3, 2.4**
    """

    @pytest.fixture(autouse=True)
    def setup_service(self, mock_db):
        """Create EmailVerificationService with an INJECTED fake SES client.

        After the task-3 lazy/injectable seam, the SES client is resolved lazily on
        first use. Patching ``boto3`` only at construction (the old pattern) exits the
        ``with`` before the test body runs, so the lazy property later resolves a REAL
        boto3 SES client and hits live AWS. Inject the fake via the ``ses_client`` kwarg
        instead — it is returned by the lazy property and no real client is ever built.
        """
        self.mock_ses = MagicMock()
        self.mock_ses.verify_email_identity.return_value = {}
        self.service = EmailVerificationService(
            db_manager=mock_db, region="eu-west-1", ses_client=self.mock_ses
        )
        self.mock_db = mock_db

    @settings(
        max_examples=100,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    @given(ses_status=ses_status_st)
    def test_ses_status_maps_to_correct_local_status(self, ses_status):
        """
        Feature: ses-email-verification, Property 3: SES status mapping correctness

        For any SES state, _map_ses_status returns the correct local status.
        """
        expected_local = SES_STATUS_MAPPING[ses_status]
        result = self.service._map_ses_status(ses_status)

        assert result == expected_local, (
            f"SES status '{ses_status}' mapped to '{result}', "
            f"expected '{expected_local}'"
        )

    @settings(
        max_examples=100,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    @given(ses_status=ses_status_st)
    def test_check_status_persists_mapped_status_to_db(self, ses_status):
        """
        Feature: ses-email-verification, Property 3: SES status mapping correctness

        For any SES state returned by GetIdentityVerificationAttributes,
        check_status persists the correctly mapped local status to the database.
        """
        test_email = "tenant@example.com"
        test_admin = "test-tenant"
        expected_local = SES_STATUS_MAPPING[ses_status]

        # Mock DB to return an active record
        self.mock_db.execute_query.side_effect = [
            # First call: _get_active_record
            [
                {
                    "email": test_email,
                    "status": "pending",
                    "last_checked_at": None,
                    "last_resend_at": None,
                    "initiated_at": datetime.utcnow(),
                    "verified_at": None,
                }
            ],
            # Second call: _update_verification_status (write)
            None,
        ]

        # Mock SES response
        self.mock_ses.get_identity_verification_attributes.return_value = {
            "VerificationAttributes": {test_email: {"VerificationStatus": ses_status}}
        }

        result = self.service.check_status(test_admin)

        assert result["status"] == expected_local, (
            f"check_status returned status '{result['status']}' for SES state "
            f"'{ses_status}', expected '{expected_local}'"
        )
        assert result["success"] is True

    @settings(
        max_examples=100,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    @given(
        unknown_status=st.text(min_size=1, max_size=30).filter(
            lambda s: s not in SES_STATUS_MAPPING
        )
    )
    def test_unknown_ses_status_maps_to_failed(self, unknown_status):
        """
        Feature: ses-email-verification, Property 3: SES status mapping correctness

        For any unknown/unexpected SES status string, _map_ses_status defaults
        to 'failed' as a safe fallback.
        """
        result = self.service._map_ses_status(unknown_status)

        assert result == "failed", (
            f"Unknown SES status '{unknown_status}' mapped to '{result}', "
            f"expected 'failed'"
        )


# ---------------------------------------------------------------------------
# Property 5: Resend rate limiting
# Feature: ses-email-verification, Property 5: Resend rate limiting
# Validates: Requirements 3.4
# ---------------------------------------------------------------------------


class TestResendRateLimiting:
    """
    Property 5: Resend rate limiting

    For any tenant, if last_resend_at is within 60 seconds of the current time,
    a resend request SHALL be rejected with an error. If last_resend_at is more
    than 60 seconds ago (or null), the resend SHALL proceed.

    Feature: ses-email-verification, Property 5: Resend rate limiting
    **Validates: Requirements 3.4**
    """

    @pytest.fixture(autouse=True)
    def setup_service(self, mock_db):
        """Create EmailVerificationService with an INJECTED fake SES client.

        See ``TestSesStatusMappingCorrectness.setup_service`` — the fake must be
        injected via the ``ses_client`` kwarg so the lazy seam never resolves a real
        boto3 client once the construction-time ``with patch(...)`` would have exited.
        """
        self.mock_ses = MagicMock()
        self.mock_ses.verify_email_identity.return_value = {}
        self.service = EmailVerificationService(
            db_manager=mock_db, region="eu-west-1", ses_client=self.mock_ses
        )
        self.mock_db = mock_db

    @settings(
        max_examples=100,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    @given(
        seconds_ago=st.floats(
            min_value=0.0,
            max_value=59.9,
            allow_nan=False,
            allow_infinity=False,
        )
    )
    def test_resend_rejected_within_cooldown(self, seconds_ago):
        """
        Feature: ses-email-verification, Property 5: Resend rate limiting

        For any last_resend_at within 60 seconds of now, resend is rejected.
        """
        test_admin = "test-tenant"
        test_email = "tenant@example.com"
        last_resend = datetime.utcnow() - timedelta(seconds=seconds_ago)

        # Mock DB to return a record with recent last_resend_at
        self.mock_db.execute_query.return_value = [
            {
                "email": test_email,
                "status": "pending",
                "last_checked_at": None,
                "last_resend_at": last_resend,
                "initiated_at": datetime.utcnow(),
                "verified_at": None,
            }
        ]

        result = self.service.resend_verification(test_admin)

        assert result["success"] is False, (
            f"Resend should be rejected when last_resend_at was "
            f"{seconds_ago:.1f}s ago (< 60s cooldown)"
        )
        assert "wait" in result["error"].lower() or "60" in result["error"], (
            f"Error message should mention waiting/60s, got: {result['error']}"
        )

    @settings(
        max_examples=100,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    @given(
        seconds_ago=st.floats(
            min_value=60.1,
            max_value=86400.0,
            allow_nan=False,
            allow_infinity=False,
        )
    )
    def test_resend_proceeds_after_cooldown(self, seconds_ago):
        """
        Feature: ses-email-verification, Property 5: Resend rate limiting

        For any last_resend_at more than 60 seconds ago, resend proceeds.
        """
        test_admin = "test-tenant"
        test_email = "tenant@example.com"
        last_resend = datetime.utcnow() - timedelta(seconds=seconds_ago)

        # First call: _get_active_record returns record with old last_resend_at
        # Second call: update query after successful resend
        self.mock_db.execute_query.side_effect = [
            [
                {
                    "email": test_email,
                    "status": "pending",
                    "last_checked_at": None,
                    "last_resend_at": last_resend,
                    "initiated_at": datetime.utcnow(),
                    "verified_at": None,
                }
            ],
            None,  # update query
        ]

        # Mock SES success
        self.mock_ses.verify_email_identity.return_value = {}

        result = self.service.resend_verification(test_admin)

        assert result["success"] is True, (
            f"Resend should proceed when last_resend_at was "
            f"{seconds_ago:.1f}s ago (> 60s cooldown), got error: {result.get('error')}"
        )

    @settings(
        max_examples=100,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    @given(dummy=st.integers(min_value=0, max_value=1000))
    def test_resend_proceeds_when_last_resend_is_null(self, dummy):
        """
        Feature: ses-email-verification, Property 5: Resend rate limiting

        When last_resend_at is null (never resent before), resend always proceeds.
        """
        test_admin = "test-tenant"
        test_email = "tenant@example.com"

        # First call: _get_active_record returns record with null last_resend_at
        # Second call: update query after successful resend
        self.mock_db.execute_query.side_effect = [
            [
                {
                    "email": test_email,
                    "status": "pending",
                    "last_checked_at": None,
                    "last_resend_at": None,
                    "initiated_at": datetime.utcnow(),
                    "verified_at": None,
                }
            ],
            None,  # update query
        ]

        # Mock SES success
        self.mock_ses.verify_email_identity.return_value = {}

        result = self.service.resend_verification(test_admin)

        assert result["success"] is True, (
            f"Resend should proceed when last_resend_at is None, "
            f"got error: {result.get('error')}"
        )


# ---------------------------------------------------------------------------
# Property 9: Email validation
# Feature: ses-email-verification, Property 9: Email validation
# Validates: Requirements 5.5
# ---------------------------------------------------------------------------


class TestEmailValidation:
    """
    Property 9: Email validation

    For any string that is a well-formed email address (contains exactly one @,
    has non-empty local and domain parts, domain contains a dot), validation
    SHALL pass. For any string that does not meet these criteria, validation
    SHALL fail and the update SHALL be rejected.

    Feature: ses-email-verification, Property 9: Email validation
    **Validates: Requirements 5.5**
    """

    @pytest.fixture(autouse=True)
    def setup_service(self, mock_db):
        """Create EmailVerificationService with an INJECTED fake SES client.

        See ``TestSesStatusMappingCorrectness.setup_service`` — inject the fake via the
        ``ses_client`` kwarg so the lazy seam never resolves a real boto3 client.
        """
        self.mock_ses = MagicMock()
        self.mock_ses.verify_email_identity.return_value = {}
        self.service = EmailVerificationService(
            db_manager=mock_db, region="eu-west-1", ses_client=self.mock_ses
        )
        self.mock_db = mock_db

    @settings(
        max_examples=100,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    @given(email=valid_email_st)
    def test_valid_emails_pass_validation(self, email):
        """
        Feature: ses-email-verification, Property 9: Email validation

        For any well-formed email (one @, non-empty local, domain with dot),
        _validate_email returns True.
        """
        # Filter out edge cases that the regex won't accept
        # (e.g., local parts starting/ending with dots, consecutive dots)
        assume(".." not in email)
        assume(not email.split("@")[0].startswith("."))
        assume(not email.split("@")[0].endswith("."))
        assume(" " not in email)

        result = self.service._validate_email(email)

        assert result is True, f"Valid email '{email}' was rejected by _validate_email"

    @settings(
        max_examples=100,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    @given(email=invalid_email_no_at_st)
    def test_emails_without_at_sign_fail(self, email):
        """
        Feature: ses-email-verification, Property 9: Email validation

        For any string without an @ sign, _validate_email returns False.
        """
        result = self.service._validate_email(email)

        assert result is False, (
            f"String without @ '{email}' was accepted by _validate_email"
        )

    @settings(
        max_examples=100,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    @given(email=invalid_email_multiple_at_st)
    def test_emails_with_multiple_at_signs_fail(self, email):
        """
        Feature: ses-email-verification, Property 9: Email validation

        For any string with multiple @ signs, _validate_email returns False.
        """
        result = self.service._validate_email(email)

        assert result is False, (
            f"String with multiple @ '{email}' was accepted by _validate_email"
        )

    @settings(
        max_examples=100,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    @given(email=invalid_email_empty_local_st)
    def test_emails_with_empty_local_part_fail(self, email):
        """
        Feature: ses-email-verification, Property 9: Email validation

        For any string with empty local part (starts with @), _validate_email
        returns False.
        """
        result = self.service._validate_email(email)

        assert result is False, (
            f"Email with empty local part '{email}' was accepted by _validate_email"
        )

    @settings(
        max_examples=100,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    @given(email=invalid_email_no_dot_domain_st)
    def test_emails_without_dot_in_domain_fail(self, email):
        """
        Feature: ses-email-verification, Property 9: Email validation

        For any email where the domain part has no dot, _validate_email
        returns False.
        """
        result = self.service._validate_email(email)

        assert result is False, (
            f"Email without dot in domain '{email}' was accepted by _validate_email"
        )

    @settings(
        max_examples=100,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    @given(email=invalid_email_with_space_st)
    def test_emails_with_spaces_fail(self, email):
        """
        Feature: ses-email-verification, Property 9: Email validation

        For any email containing spaces, _validate_email returns False.
        """
        result = self.service._validate_email(email)

        assert result is False, (
            f"Email with space '{email}' was accepted by _validate_email"
        )

    @settings(
        max_examples=100,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    @given(data=st.data())
    def test_empty_and_none_inputs_fail(self, data):
        """
        Feature: ses-email-verification, Property 9: Email validation

        Empty strings, None, and non-string inputs always fail validation.
        """
        email = data.draw(
            st.one_of(
                st.just(""),
                st.just(None),
                st.just("   "),
            )
        )

        result = self.service._validate_email(email)

        assert result is False, (
            f"Empty/None input '{email}' was accepted by _validate_email"
        )

    # -----------------------------------------------------------------------
    # Property 2 (Bug Condition B-email) — abusive addresses rejected.
    #
    # These encode the hardened behavior from task 4.1: addresses where
    # isBugCondition_B_email holds (prototype-pollution keys, exploit special
    # characters, no sane dotted domain, or oversized local/domain) MUST now
    # return False so SES verify_email_identity is never called for them. These
    # are the inputs the OLD broad RFC generator wrongly accepted as "valid".
    #
    # **Validates: Requirements 2.4**
    # -----------------------------------------------------------------------

    @pytest.mark.parametrize(
        "email",
        [
            # Prototype-pollution keys anywhere in the local part.
            "__proto__@DA.BeauTy",
            "constructor@example.com",
            "prototype@example.com",
            "a__proto__b@example.com",
            # Exploit / unsafe special characters (| ^ # { } = ! ~ % & ' * / ? $).
            "a|b@example.com",
            "%4@A.PAGe",
            "a^b@example.com",
            "a#b@example.com",
            "a{b}@example.com",
            "a=b@example.com",
            "a!b@example.com",
            "a~b@example.com",
            "a&b@example.com",
            "a'b@example.com",
            "a*b@example.com",
            "a/b@example.com",
            "a?b@example.com",
            "a$b@example.com",
            # No sane dotted domain / no alpha TLD.
            "user@localhost",
            "user@example",
            "user@example.1",
            # Consecutive dots / non-alnum anchors in the local part.
            "a..b@example.com",
            ".user@example.com",
            "user.@example.com",
        ],
    )
    def test_abusive_addresses_rejected(self, email):
        """Property 2: an abusive address is rejected before any SES call.

        _validate_email returns False (never raises), so initiate_verification
        short-circuits and SES verify_email_identity is never reached for it.
        """
        assert self.service._validate_email(email) is False, (
            f"Abusive address '{email}' was wrongly accepted by _validate_email"
        )
        # No SES call happens on the app path for a rejected address.
        self.mock_ses.reset_mock()
        result = self.service.initiate_verification("tenant1", email)
        assert result["success"] is False
        assert result["status"] == "failed"
        self.mock_ses.verify_email_identity.assert_not_called()

    @pytest.mark.parametrize(
        "email",
        [
            # Oversized local part (> 64) — RFC 5321 cap.
            "a" * 65 + "@example.com",
            # Oversized overall (> 254).
            "user@" + ("a" * 250) + ".com",
            # Oversized single domain label (> 63).
            "user@" + ("a" * 64) + ".com",
        ],
    )
    def test_oversized_addresses_rejected(self, email):
        """Property 2: oversized local/domain parts are rejected before any SES call."""
        assert self.service._validate_email(email) is False, (
            f"Oversized address (len local/domain) was wrongly accepted: '{email[:40]}...'"
        )


# ---------------------------------------------------------------------------
# PRESERVATION PROPERTY (ses-sender-identity-pollution-cleanup, task 2)
#
# Property 4 (Preservation): a GENERATED genuine/deliverable address still passes
# _validate_email (True) and reaches the SES verify call. The generator is
# constrained to the genuine/deliverable subspace — safe local-part characters,
# a sane dotted domain, and conservative length caps — i.e. the inputs that do
# NOT satisfy isBugCondition_B_email. These must keep validating + reaching verify
# BOTH before the fix (baseline) AND after the tightened validation (task 4.x)
# and the injectable seam (task 3.x) land, since genuine senders are never abusive.
#
# EXPECTED OUTCOME on UNFIXED code: PASSES (this is the baseline to preserve).
#
# **Validates: Requirements 3.1, 3.5**
# ---------------------------------------------------------------------------

# A conservative "genuine deliverable" local part: letters/digits plus the common,
# non-exploit separators (dot / plus / underscore / hyphen). Deliberately EXCLUDES the
# exploit special characters (| ^ # { } = ! ~ % etc.) and the prototype-pollution keys
# that the task-4 tightening will reject, so a generated address here is always a
# genuine sender the fix must preserve.
genuine_local_chars = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"


def _genuine_local_part():
    """Draw a plausible local part: an alnum-anchored body with safe inner separators."""
    body = st.text(alphabet=genuine_local_chars + ".+_-", min_size=0, max_size=28)
    head = st.text(alphabet=genuine_local_chars, min_size=1, max_size=1)
    tail = st.text(alphabet=genuine_local_chars, min_size=1, max_size=1)
    return st.builds(lambda h, b, t: f"{h}{b}{t}", head, body, tail).filter(
        lambda s: (
            ".." not in s and "@" not in s and len(s) <= 30 and not _has_proto_key(s)
        )
    )


genuine_label_st = st.from_regex(r"[a-z0-9]([a-z0-9\-]{0,10}[a-z0-9])?", fullmatch=True)
genuine_tld_st = st.from_regex(r"[a-z]{2,6}", fullmatch=True)

genuine_email_st = st.builds(
    lambda local, domain, tld: f"{local}@{domain}.{tld}",
    local=_genuine_local_part(),
    domain=genuine_label_st,
    tld=genuine_tld_st,
)


class TestPreservationGenuineSenderProperty:
    """Property 4 (Preservation) — generated genuine senders validate + reach the SES verify.

    For ANY generated genuine/deliverable address (safe chars, sane domain, within length
    caps), _validate_email returns True AND initiate_verification calls SES
    verify_email_identity and stores a pending record. This is the baseline the tightened
    validation (task 4.x) must preserve: it narrows the accepted set to reject abusive
    inputs WITHOUT dropping genuine senders.

    **Validates: Requirements 3.1, 3.5**
    """

    @pytest.fixture(autouse=True)
    def setup_service(self, mock_db):
        # Inject the fake via the ses_client kwarg. The old construction-time
        # `with patch(...boto3)` exited before the test body, letting the lazy seam
        # resolve a REAL boto3 client and hit live AWS on generated addresses.
        self.mock_ses = MagicMock()
        self.mock_ses.verify_email_identity.return_value = {}
        self.service = EmailVerificationService(
            db_manager=mock_db, region="eu-west-1", ses_client=self.mock_ses
        )
        self.mock_db = mock_db

    @settings(
        max_examples=200,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    @given(email=genuine_email_st)
    def test_genuine_address_passes_validation(self, email):
        """A generated genuine/deliverable address passes _validate_email (baseline True)."""
        assert self.service._validate_email(email) is True, (
            f"Genuine deliverable address '{email}' was rejected by _validate_email"
        )

    @settings(
        max_examples=200,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    @given(email=genuine_email_st)
    def test_genuine_address_reaches_ses_verify(self, email):
        """initiate_verification for a generated genuine address calls SES + stores pending."""
        self.mock_db.reset_mock()
        self.mock_ses.reset_mock()
        self.mock_ses.verify_email_identity.return_value = {}

        result = self.service.initiate_verification("tenant1", email)

        assert result["success"] is True
        assert result["status"] == "pending"
        assert result["error"] is None
        self.mock_ses.verify_email_identity.assert_called_once_with(EmailAddress=email)
        # a pending record is stored for the genuine sender
        call_args = self.mock_db.execute_query.call_args
        assert "INSERT INTO email_verifications" in call_args[0][0]
        assert call_args[0][1][2] == "pending"


# ---------------------------------------------------------------------------
# EXPECTED-BEHAVIOR PROPERTY — Concern B injectable/lazy SES seam
# (ses-sender-identity-pollution-cleanup, Property 1; paired with task 3.1)
#
# Property 1 (Bug Condition B-client, PRIMARY): for ANY non-production-wired
# construction (isBugCondition_B_seam(ctx) — NOT explicitlyProductionWired(ctx)),
# the fixed EmailVerificationService resolves NO real boto3 SES client before any
# SES call. We generate the non-wired construction space — arbitrary regions, with
# an injected fake client (the off-production default) — and assert `boto3.client`
# is NEVER reached, neither at construction nor on first use of the lazy seam, and
# that any SES call lands on the injected fake instead of a real client.
#
# EXPECTED OUTCOME on FIXED code: PASSES (the injectable/lazy seam closes the
# identity-burst hole from every non-production-wired path).
#
# **Validates: Requirements 2.3, 3.1**
# ---------------------------------------------------------------------------

# Plausible AWS region strings a script/test/REPL/fuzz harness might pass. The region
# is irrelevant to the seam — no non-production-wired construction may resolve a real
# client regardless of it.
region_st = st.sampled_from(
    ["eu-west-1", "eu-central-1", "us-east-1", "us-west-2", "ap-southeast-2"]
)


class TestNonProductionWiredConstructionResolvesNoRealClient:
    """Property 1 — a non-production-wired construction never resolves a real SES client.

    For any generated non-production-wired construction (arbitrary region, fake injected),
    `boto3.client` is never called — at construction OR before/at the first SES call — and
    SES calls land on the injected fake. This is the fixed seam from task 3.1 (injectable +
    lazy, mirroring the SAM `SesBotoSender`).

    **Validates: Requirements 2.3, 3.1**
    """

    @settings(
        max_examples=100,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    @given(region=region_st)
    def test_injected_construction_never_resolves_real_client(self, region, mock_db):
        """Construct with an injected fake over an arbitrary region → boto3.client untouched."""
        with patch("services.email_verification_service.boto3.client") as spy_client:
            fake_ses = MagicMock()
            fake_ses.verify_email_identity.return_value = {}
            svc = EmailVerificationService(
                db_manager=mock_db, region=region, ses_client=fake_ses
            )
            # Lazy property returns the injected fake, never a real client.
            assert svc.ses_client is fake_ses

        spy_client.assert_not_called()

    @settings(
        max_examples=100,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    @given(region=region_st)
    def test_no_real_client_resolved_before_any_ses_call(self, region, mock_db):
        """initiate_verification off a non-wired path calls the fake; boto3.client is never reached."""
        with patch("services.email_verification_service.boto3.client") as spy_client:
            fake_ses = MagicMock()
            fake_ses.verify_email_identity.return_value = {}
            svc = EmailVerificationService(
                db_manager=mock_db, region=region, ses_client=fake_ses
            )
            result = svc.initiate_verification("tenant1", "user@example.com")

        assert result["success"] is True
        fake_ses.verify_email_identity.assert_called_once_with(
            EmailAddress="user@example.com"
        )
        # No real boto3 SES client was ever resolved on this non-production-wired path.
        spy_client.assert_not_called()
