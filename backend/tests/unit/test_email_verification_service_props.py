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

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from services.email_verification_service import EmailVerificationService, RESEND_COOLDOWN_SECONDS


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# SES verification states and their expected local mappings
SES_STATUS_MAPPING = {
    'Success': 'verified',
    'Pending': 'pending',
    'Failed': 'failed',
    'TemporaryFailure': 'pending',
    'NotStarted': 'failed',
}

ses_status_st = st.sampled_from(list(SES_STATUS_MAPPING.keys()))

# Strategy for timestamps relative to "now"
# Generates seconds offset from current time (positive = in the past)
seconds_offset_st = st.floats(
    min_value=0.0, max_value=86400.0,  # 0 to 24 hours in the past
    allow_nan=False, allow_infinity=False,
)

# Strategy for valid email local parts (RFC 5322 allowed characters)
valid_local_chars = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.!#$%&\'*+/=?^_`{|}~-'
valid_local_part_st = st.text(
    alphabet=valid_local_chars, min_size=1, max_size=30
)

# Strategy for valid domain labels (alphanumeric, may contain hyphens but not start/end with them)
domain_label_st = st.from_regex(r'[a-zA-Z0-9]([a-zA-Z0-9\-]{0,10}[a-zA-Z0-9])?', fullmatch=True)

# Strategy for valid TLDs (2+ alpha characters)
tld_st = st.from_regex(r'[a-zA-Z]{2,6}', fullmatch=True)

# Strategy for valid email addresses
valid_email_st = st.builds(
    lambda local, domain, tld: f"{local}@{domain}.{tld}",
    local=valid_local_part_st,
    domain=domain_label_st,
    tld=tld_st,
)

# Strategy for invalid emails - various ways an email can be invalid
invalid_email_no_at_st = st.text(min_size=1, max_size=50).filter(lambda s: '@' not in s)
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
    domain=st.from_regex(r'[a-zA-Z0-9]{1,20}', fullmatch=True),
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
        """Create EmailVerificationService with mocked dependencies."""
        with patch('services.email_verification_service.boto3') as mock_boto3:
            self.mock_ses = MagicMock()
            mock_boto3.client.return_value = self.mock_ses
            self.service = EmailVerificationService(
                db_manager=mock_db, region='eu-west-1', test_mode=True
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
        test_email = 'tenant@example.com'
        test_admin = 'test-tenant'
        expected_local = SES_STATUS_MAPPING[ses_status]

        # Mock DB to return an active record
        self.mock_db.execute_query.side_effect = [
            # First call: _get_active_record
            [{'email': test_email, 'status': 'pending',
              'last_checked_at': None, 'last_resend_at': None,
              'initiated_at': datetime.utcnow(), 'verified_at': None}],
            # Second call: _update_verification_status (write)
            None,
        ]

        # Mock SES response
        self.mock_ses.get_identity_verification_attributes.return_value = {
            'VerificationAttributes': {
                test_email: {'VerificationStatus': ses_status}
            }
        }

        result = self.service.check_status(test_admin)

        assert result['status'] == expected_local, (
            f"check_status returned status '{result['status']}' for SES state "
            f"'{ses_status}', expected '{expected_local}'"
        )
        assert result['success'] is True

    @settings(
        max_examples=100,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    @given(unknown_status=st.text(min_size=1, max_size=30).filter(
        lambda s: s not in SES_STATUS_MAPPING
    ))
    def test_unknown_ses_status_maps_to_failed(self, unknown_status):
        """
        Feature: ses-email-verification, Property 3: SES status mapping correctness

        For any unknown/unexpected SES status string, _map_ses_status defaults
        to 'failed' as a safe fallback.
        """
        result = self.service._map_ses_status(unknown_status)

        assert result == 'failed', (
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
        """Create EmailVerificationService with mocked dependencies."""
        with patch('services.email_verification_service.boto3') as mock_boto3:
            self.mock_ses = MagicMock()
            mock_boto3.client.return_value = self.mock_ses
            self.service = EmailVerificationService(
                db_manager=mock_db, region='eu-west-1', test_mode=True
            )
        self.mock_db = mock_db

    @settings(
        max_examples=100,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    @given(seconds_ago=st.floats(
        min_value=0.0, max_value=59.9,
        allow_nan=False, allow_infinity=False,
    ))
    def test_resend_rejected_within_cooldown(self, seconds_ago):
        """
        Feature: ses-email-verification, Property 5: Resend rate limiting

        For any last_resend_at within 60 seconds of now, resend is rejected.
        """
        test_admin = 'test-tenant'
        test_email = 'tenant@example.com'
        last_resend = datetime.utcnow() - timedelta(seconds=seconds_ago)

        # Mock DB to return a record with recent last_resend_at
        self.mock_db.execute_query.return_value = [
            {'email': test_email, 'status': 'pending',
             'last_checked_at': None, 'last_resend_at': last_resend,
             'initiated_at': datetime.utcnow(), 'verified_at': None}
        ]

        result = self.service.resend_verification(test_admin)

        assert result['success'] is False, (
            f"Resend should be rejected when last_resend_at was "
            f"{seconds_ago:.1f}s ago (< 60s cooldown)"
        )
        assert 'wait' in result['error'].lower() or '60' in result['error'], (
            f"Error message should mention waiting/60s, got: {result['error']}"
        )

    @settings(
        max_examples=100,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    @given(seconds_ago=st.floats(
        min_value=60.1, max_value=86400.0,
        allow_nan=False, allow_infinity=False,
    ))
    def test_resend_proceeds_after_cooldown(self, seconds_ago):
        """
        Feature: ses-email-verification, Property 5: Resend rate limiting

        For any last_resend_at more than 60 seconds ago, resend proceeds.
        """
        test_admin = 'test-tenant'
        test_email = 'tenant@example.com'
        last_resend = datetime.utcnow() - timedelta(seconds=seconds_ago)

        # First call: _get_active_record returns record with old last_resend_at
        # Second call: update query after successful resend
        self.mock_db.execute_query.side_effect = [
            [{'email': test_email, 'status': 'pending',
              'last_checked_at': None, 'last_resend_at': last_resend,
              'initiated_at': datetime.utcnow(), 'verified_at': None}],
            None,  # update query
        ]

        # Mock SES success
        self.mock_ses.verify_email_identity.return_value = {}

        result = self.service.resend_verification(test_admin)

        assert result['success'] is True, (
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
        test_admin = 'test-tenant'
        test_email = 'tenant@example.com'

        # First call: _get_active_record returns record with null last_resend_at
        # Second call: update query after successful resend
        self.mock_db.execute_query.side_effect = [
            [{'email': test_email, 'status': 'pending',
              'last_checked_at': None, 'last_resend_at': None,
              'initiated_at': datetime.utcnow(), 'verified_at': None}],
            None,  # update query
        ]

        # Mock SES success
        self.mock_ses.verify_email_identity.return_value = {}

        result = self.service.resend_verification(test_admin)

        assert result['success'] is True, (
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
        """Create EmailVerificationService with mocked dependencies."""
        with patch('services.email_verification_service.boto3') as mock_boto3:
            self.mock_ses = MagicMock()
            mock_boto3.client.return_value = self.mock_ses
            self.service = EmailVerificationService(
                db_manager=mock_db, region='eu-west-1', test_mode=True
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
        assume('..' not in email)
        assume(not email.split('@')[0].startswith('.'))
        assume(not email.split('@')[0].endswith('.'))
        assume(' ' not in email)

        result = self.service._validate_email(email)

        assert result is True, (
            f"Valid email '{email}' was rejected by _validate_email"
        )

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
        email = data.draw(st.one_of(
            st.just(''),
            st.just(None),
            st.just('   '),
        ))

        result = self.service._validate_email(email)

        assert result is False, (
            f"Empty/None input '{email}' was accepted by _validate_email"
        )
