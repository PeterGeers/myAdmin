"""
Unit tests for EmailVerificationService

Tests all public methods with mocked SES client and DatabaseManager.
Validates: Requirements 1.1, 1.2, 1.3, 2.1–2.5, 3.1–3.4, 5.1–5.5
"""

import os
import sys
from datetime import datetime, timedelta
from unittest.mock import Mock, patch

import pytest
from botocore.exceptions import ClientError

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from services.email_verification_service import (
    RESEND_COOLDOWN_SECONDS,
    EmailVerificationService,
)

# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def mock_db():
    """Create a mocked DatabaseManager."""
    db = Mock()
    db.execute_query = Mock(return_value=[])
    return db


@pytest.fixture
def mock_ses_client():
    """Create a mocked SES client."""
    client = Mock()
    client.verify_email_identity = Mock(return_value={})
    client.get_identity_verification_attributes = Mock(
        return_value={"VerificationAttributes": {}}
    )
    return client


@pytest.fixture
def service(mock_db, mock_ses_client):
    """Create EmailVerificationService with mocked dependencies.

    Injects the fake SES client directly via the `ses_client=` kwarg (task 3.1's
    injectable/lazy seam) rather than patching `boto3` only during construction. The
    old patch-on-construct fixture exited before the test body ran, so the lazy
    `ses_client` property would resolve a fresh real client at first use — breaking
    every fixture-dependent test. Constructor injection keeps the fake wired for the
    whole test and resolves no real client.
    """
    return EmailVerificationService(
        db_manager=mock_db, region="eu-west-1", ses_client=mock_ses_client
    )


# ============================================================================
# _validate_email
# ============================================================================


@pytest.mark.unit
class TestValidateEmail:
    """Test _validate_email method."""

    def test_valid_simple_email(self, service):
        assert service._validate_email("user@example.com") is True

    def test_valid_email_with_dots(self, service):
        assert service._validate_email("first.last@example.com") is True

    def test_valid_email_with_plus(self, service):
        assert service._validate_email("user+tag@example.com") is True

    def test_valid_email_with_subdomain(self, service):
        assert service._validate_email("user@mail.example.co.uk") is True

    def test_invalid_no_at_sign(self, service):
        assert service._validate_email("userexample.com") is False

    def test_invalid_no_domain(self, service):
        assert service._validate_email("user@") is False

    def test_invalid_no_local_part(self, service):
        assert service._validate_email("@example.com") is False

    def test_invalid_no_tld(self, service):
        assert service._validate_email("user@example") is False

    def test_invalid_spaces(self, service):
        assert service._validate_email("user @example.com") is False

    def test_invalid_empty_string(self, service):
        assert service._validate_email("") is False

    def test_invalid_none(self, service):
        assert service._validate_email(None) is False

    def test_invalid_double_at(self, service):
        assert service._validate_email("user@@example.com") is False


# ============================================================================
# initiate_verification
# ============================================================================


@pytest.mark.unit
class TestInitiateVerification:
    """Test initiate_verification method."""

    def test_success_path(self, service, mock_ses_client, mock_db):
        """SES call succeeds → returns success with pending status, stores record."""
        result = service.initiate_verification("tenant1", "user@example.com")

        assert result["success"] is True
        assert result["status"] == "pending"
        assert result["error"] is None
        mock_ses_client.verify_email_identity.assert_called_once_with(
            EmailAddress="user@example.com"
        )
        # Verify DB record stored with pending status
        mock_db.execute_query.assert_called()
        call_args = mock_db.execute_query.call_args
        assert "INSERT INTO email_verifications" in call_args[0][0]
        params = call_args[0][1]
        assert params[0] == "tenant1"
        assert params[1] == "user@example.com"
        assert params[2] == "pending"

    def test_ses_client_error(self, service, mock_ses_client, mock_db):
        """SES ClientError → returns failure, stores failed record."""
        mock_ses_client.verify_email_identity.side_effect = ClientError(
            {"Error": {"Code": "InvalidParameterValue", "Message": "Invalid email"}},
            "VerifyEmailIdentity",
        )

        result = service.initiate_verification("tenant1", "user@example.com")

        assert result["success"] is False
        assert result["status"] == "failed"
        assert "InvalidParameterValue" in result["error"]
        # Verify failed record stored
        mock_db.execute_query.assert_called()
        call_args = mock_db.execute_query.call_args
        params = call_args[0][1]
        assert params[2] == "failed"

    def test_ses_unexpected_error(self, service, mock_ses_client, mock_db):
        """Unexpected exception → returns failure, stores failed record."""
        mock_ses_client.verify_email_identity.side_effect = Exception("Network timeout")

        result = service.initiate_verification("tenant1", "user@example.com")

        assert result["success"] is False
        assert result["status"] == "failed"
        # Raw exception text must not leak to the caller (py/stack-trace-exposure).
        assert "Network timeout" not in result["error"]
        assert result["error"] == "Email verification failed. Please try again later."

    def test_invalid_email_rejected(self, service, mock_ses_client):
        """Invalid email → returns failure without calling SES."""
        result = service.initiate_verification("tenant1", "not-an-email")

        assert result["success"] is False
        assert result["status"] == "failed"
        assert "Invalid email format" in result["error"]
        mock_ses_client.verify_email_identity.assert_not_called()


# ============================================================================
# check_status
# ============================================================================


@pytest.mark.unit
class TestCheckStatus:
    """Test check_status method."""

    def test_ses_success_maps_to_verified(self, service, mock_ses_client, mock_db):
        """SES 'Success' → local status 'verified'."""
        mock_db.execute_query.side_effect = [
            # _get_active_record query
            [
                {
                    "email": "user@example.com",
                    "status": "pending",
                    "last_checked_at": None,
                    "last_resend_at": None,
                    "initiated_at": datetime(2025, 1, 1),
                    "verified_at": None,
                }
            ],
            # _update_verification_status query
            [],
        ]
        mock_ses_client.get_identity_verification_attributes.return_value = {
            "VerificationAttributes": {
                "user@example.com": {"VerificationStatus": "Success"}
            }
        }

        result = service.check_status("tenant1")

        assert result["success"] is True
        assert result["email"] == "user@example.com"
        assert result["status"] == "verified"
        assert result["last_checked"] is not None

    def test_ses_pending_maps_to_pending(self, service, mock_ses_client, mock_db):
        """SES 'Pending' → local status 'pending'."""
        mock_db.execute_query.side_effect = [
            [
                {
                    "email": "user@example.com",
                    "status": "pending",
                    "last_checked_at": None,
                    "last_resend_at": None,
                    "initiated_at": datetime(2025, 1, 1),
                    "verified_at": None,
                }
            ],
            [],
        ]
        mock_ses_client.get_identity_verification_attributes.return_value = {
            "VerificationAttributes": {
                "user@example.com": {"VerificationStatus": "Pending"}
            }
        }

        result = service.check_status("tenant1")

        assert result["success"] is True
        assert result["status"] == "pending"

    def test_ses_failed_maps_to_failed(self, service, mock_ses_client, mock_db):
        """SES 'Failed' → local status 'failed'."""
        mock_db.execute_query.side_effect = [
            [
                {
                    "email": "user@example.com",
                    "status": "pending",
                    "last_checked_at": None,
                    "last_resend_at": None,
                    "initiated_at": datetime(2025, 1, 1),
                    "verified_at": None,
                }
            ],
            [],
        ]
        mock_ses_client.get_identity_verification_attributes.return_value = {
            "VerificationAttributes": {
                "user@example.com": {"VerificationStatus": "Failed"}
            }
        }

        result = service.check_status("tenant1")

        assert result["success"] is True
        assert result["status"] == "failed"

    def test_ses_temporary_failure_maps_to_pending(
        self, service, mock_ses_client, mock_db
    ):
        """SES 'TemporaryFailure' → local status 'pending'."""
        mock_db.execute_query.side_effect = [
            [
                {
                    "email": "user@example.com",
                    "status": "pending",
                    "last_checked_at": None,
                    "last_resend_at": None,
                    "initiated_at": datetime(2025, 1, 1),
                    "verified_at": None,
                }
            ],
            [],
        ]
        mock_ses_client.get_identity_verification_attributes.return_value = {
            "VerificationAttributes": {
                "user@example.com": {"VerificationStatus": "TemporaryFailure"}
            }
        }

        result = service.check_status("tenant1")

        assert result["success"] is True
        assert result["status"] == "pending"

    def test_ses_not_started_maps_to_failed(self, service, mock_ses_client, mock_db):
        """SES 'NotStarted' → local status 'failed'."""
        mock_db.execute_query.side_effect = [
            [
                {
                    "email": "user@example.com",
                    "status": "pending",
                    "last_checked_at": None,
                    "last_resend_at": None,
                    "initiated_at": datetime(2025, 1, 1),
                    "verified_at": None,
                }
            ],
            [],
        ]
        mock_ses_client.get_identity_verification_attributes.return_value = {
            "VerificationAttributes": {
                "user@example.com": {"VerificationStatus": "NotStarted"}
            }
        }

        result = service.check_status("tenant1")

        assert result["success"] is True
        assert result["status"] == "failed"

    def test_no_record_returns_null_status(self, service, mock_db):
        """No active record → returns null email and status."""
        mock_db.execute_query.return_value = []

        result = service.check_status("tenant1")

        assert result["success"] is True
        assert result["email"] is None
        assert result["status"] is None
        assert result["last_checked"] is None

    def test_ses_error_returns_cached_status(self, service, mock_ses_client, mock_db):
        """SES API error → returns cached DB status."""
        last_checked = datetime(2025, 1, 10, 12, 0, 0)
        mock_db.execute_query.return_value = [
            {
                "email": "user@example.com",
                "status": "pending",
                "last_checked_at": last_checked,
                "last_resend_at": None,
                "initiated_at": datetime(2025, 1, 1),
                "verified_at": None,
            }
        ]
        mock_ses_client.get_identity_verification_attributes.side_effect = ClientError(
            {"Error": {"Code": "ServiceUnavailable", "Message": "SES down"}},
            "GetIdentityVerificationAttributes",
        )

        result = service.check_status("tenant1")

        assert result["success"] is True
        assert result["email"] == "user@example.com"
        assert result["status"] == "pending"
        assert result["last_checked"] == "2025-01-10T12:00:00Z"


# ============================================================================
# resend_verification
# ============================================================================


@pytest.mark.unit
class TestResendVerification:
    """Test resend_verification method."""

    def test_success_path(self, service, mock_ses_client, mock_db):
        """Resend succeeds when cooldown has passed."""
        mock_db.execute_query.side_effect = [
            # _get_active_record
            [
                {
                    "email": "user@example.com",
                    "status": "pending",
                    "last_checked_at": None,
                    "last_resend_at": datetime.utcnow() - timedelta(seconds=120),
                    "initiated_at": datetime(2025, 1, 1),
                    "verified_at": None,
                }
            ],
            # update last_resend_at
            [],
        ]

        result = service.resend_verification("tenant1")

        assert result["success"] is True
        assert result["error"] is None
        mock_ses_client.verify_email_identity.assert_called_once_with(
            EmailAddress="user@example.com"
        )

    def test_success_when_no_previous_resend(self, service, mock_ses_client, mock_db):
        """Resend succeeds when last_resend_at is None (first resend)."""
        mock_db.execute_query.side_effect = [
            [
                {
                    "email": "user@example.com",
                    "status": "pending",
                    "last_checked_at": None,
                    "last_resend_at": None,
                    "initiated_at": datetime(2025, 1, 1),
                    "verified_at": None,
                }
            ],
            [],
        ]

        result = service.resend_verification("tenant1")

        assert result["success"] is True
        mock_ses_client.verify_email_identity.assert_called_once()

    def test_rate_limited(self, service, mock_ses_client, mock_db):
        """Resend rejected when within 60s cooldown."""
        mock_db.execute_query.return_value = [
            {
                "email": "user@example.com",
                "status": "pending",
                "last_checked_at": None,
                "last_resend_at": datetime.utcnow() - timedelta(seconds=30),
                "initiated_at": datetime(2025, 1, 1),
                "verified_at": None,
            }
        ]

        result = service.resend_verification("tenant1")

        assert result["success"] is False
        assert "60 seconds" in result["error"]
        mock_ses_client.verify_email_identity.assert_not_called()

    def test_ses_failure(self, service, mock_ses_client, mock_db):
        """SES error during resend → returns error."""
        mock_db.execute_query.return_value = [
            {
                "email": "user@example.com",
                "status": "pending",
                "last_checked_at": None,
                "last_resend_at": None,
                "initiated_at": datetime(2025, 1, 1),
                "verified_at": None,
            }
        ]
        mock_ses_client.verify_email_identity.side_effect = ClientError(
            {"Error": {"Code": "Throttling", "Message": "Rate exceeded"}},
            "VerifyEmailIdentity",
        )

        result = service.resend_verification("tenant1")

        assert result["success"] is False
        assert "Throttling" in result["error"]

    def test_no_record_returns_error(self, service, mock_db):
        """No active record → returns error."""
        mock_db.execute_query.return_value = []

        result = service.resend_verification("tenant1")

        assert result["success"] is False
        assert "No verification record" in result["error"]


# ============================================================================
# update_email
# ============================================================================


@pytest.mark.unit
class TestUpdateEmail:
    """Test update_email method."""

    def test_valid_email_initiates_verification(
        self, service, mock_ses_client, mock_db
    ):
        """Valid new email → marks old as replaced, initiates new verification."""
        mock_db.execute_query.side_effect = [
            # Mark old records as replaced
            [],
            # Store new pending record (from initiate_verification)
            [],
        ]

        result = service.update_email("tenant1", "new@example.com")

        assert result["success"] is True
        assert result["status"] == "pending"
        # Verify old records marked as replaced
        first_call = mock_db.execute_query.call_args_list[0]
        assert "replaced" in first_call[0][0]
        assert first_call[0][1] == ("tenant1",)
        # Verify SES called for new email
        mock_ses_client.verify_email_identity.assert_called_once_with(
            EmailAddress="new@example.com"
        )

    def test_invalid_email_rejected(self, service, mock_ses_client, mock_db):
        """Invalid email → returns error without calling SES or DB."""
        result = service.update_email("tenant1", "not-valid")

        assert result["success"] is False
        assert result["status"] == "failed"
        assert "Invalid email format" in result["error"]
        mock_ses_client.verify_email_identity.assert_not_called()

    def test_state_transition_old_to_replaced(self, service, mock_ses_client, mock_db):
        """Old records with active statuses are marked as 'replaced'."""
        mock_db.execute_query.side_effect = [[], []]

        service.update_email("tenant1", "new@example.com")

        first_call = mock_db.execute_query.call_args_list[0]
        query = first_call[0][0]
        # Verify the UPDATE targets active statuses
        assert "pending" in query
        assert "verified" in query
        assert "failed" in query
        assert "expired" in query
        assert "SET status = 'replaced'" in query


# ============================================================================
# get_verified_sender
# ============================================================================


@pytest.mark.unit
class TestGetVerifiedSender:
    """Test get_verified_sender method."""

    def test_verified_tenant(self, service, mock_db):
        """Verified tenant → returns verified=True with email and company name."""
        mock_db.execute_query.side_effect = [
            # get verified email
            [{"email": "tenant@example.com"}],
            # get company name
            [{"value": '"Acme Corp"}'}],
        ]

        result = service.get_verified_sender("tenant1")

        assert result["verified"] is True
        assert result["email"] == "tenant@example.com"

    def test_no_verified_record(self, service, mock_db):
        """No verified record → returns verified=False."""
        mock_db.execute_query.return_value = []

        result = service.get_verified_sender("tenant1")

        assert result["verified"] is False
        assert result["email"] is None
        assert result["company_name"] is None

    def test_pending_status_not_returned(self, service, mock_db):
        """Only 'verified' status records are returned."""
        # The query filters by status = 'verified', so pending records won't match
        mock_db.execute_query.return_value = []

        result = service.get_verified_sender("tenant1")

        assert result["verified"] is False

    def test_query_filters_by_verified_status(self, service, mock_db):
        """Verify the SQL query filters by status='verified'."""
        mock_db.execute_query.return_value = []

        service.get_verified_sender("tenant1")

        call_args = mock_db.execute_query.call_args
        query = call_args[0][0]
        assert "status = 'verified'" in query

    def test_query_filters_by_administration(self, service, mock_db):
        """Verify tenant isolation — query includes administration filter."""
        mock_db.execute_query.return_value = []

        service.get_verified_sender("tenant1")

        call_args = mock_db.execute_query.call_args
        query = call_args[0][0]
        params = call_args[0][1]
        assert "administration = %s" in query
        assert params == ("tenant1",)


# ============================================================================
# mark_expired
# ============================================================================


@pytest.mark.unit
class TestMarkExpired:
    """Test mark_expired method."""

    def test_updates_status_to_expired(self, service, mock_db):
        """mark_expired updates verified record to expired."""
        service.mark_expired("tenant1", "user@example.com")

        mock_db.execute_query.assert_called_once()
        call_args = mock_db.execute_query.call_args
        query = call_args[0][0]
        params = call_args[0][1]
        assert "SET status = 'expired'" in query
        assert "status = 'verified'" in query
        assert params == ("tenant1", "user@example.com")

    def test_only_targets_verified_records(self, service, mock_db):
        """mark_expired only changes records with status='verified'."""
        service.mark_expired("tenant1", "user@example.com")

        call_args = mock_db.execute_query.call_args
        query = call_args[0][0]
        assert "AND status = 'verified'" in query

    def test_includes_tenant_isolation(self, service, mock_db):
        """mark_expired includes administration filter."""
        service.mark_expired("tenant1", "user@example.com")

        call_args = mock_db.execute_query.call_args
        query = call_args[0][0]
        assert "administration = %s" in query


# ============================================================================
# EXPECTED-BEHAVIOR TESTS — Concern B injectable/lazy SES seam
# (ses-sender-identity-pollution-cleanup, Property 1; reworked from task 1's
#  B-client exploration test now that task 3.1's fix has landed)
#
# Property 1 (Bug Condition B-client, PRIMARY): for any construction NOT explicitly
# production-wired (isBugCondition_B_seam(ctx) — NOT explicitlyProductionWired(ctx)),
# the fixed service resolves NO real boto3 SES client and calls NO real
# `verify_email_identity`. The task-1 exploration assertion (`boto3.client` never
# called at construction) now PASSES against the lazy seam and is KEPT as the
# expected-behavior assertion, extended to cover first use of the seam.
#
# The B-email exploration cases below are left as-is for task 4.x (validation
# tightening) to own — they still assert the FIXED `_validate_email` return values.
#
# Validates: Requirements 2.3 (injectable/lazy seam), 1.3 (B-email, task 4.x owns)
# ============================================================================


@pytest.mark.unit
class TestBugConditionB_UninjectableClient:
    """B-client (PRIMARY) — the fixed seam never resolves a real client off a non-wired path.

    Bug Condition isBugCondition_B_seam(ctx): a construction path NOT explicitly
    production-wired must NOT resolve a real boto3 SES client. Task 3.1 made the SES
    client injectable + lazy (mirroring the SAM `SesBotoSender`): `__init__` stores
    `ses_client` without touching boto3, and the lazy `ses_client` property resolves a
    real `boto3.client("ses", ...)` ONLY when nothing was injected.

    EXPECTED OUTCOME on FIXED code: no real `boto3.client("ses", ...)` is resolved at
    construction (the task-1 exploration assertion now PASSES), and when a fake IS
    injected the seam returns it and never reaches boto3 — closing the identity-burst
    seam.
    """

    def test_init_resolves_no_real_ses_client_without_injection(self):
        """Non-production-wired construction resolves NO real boto3 SES client.

        Spy on `boto3.client` and construct WITHOUT injecting a client. On the fixed
        lazy seam, `__init__` does not touch boto3, so the spy is never called at
        construction — the task-1 exploration test now PASSES against the fix.
        (Accessing `.ses_client` here WOULD resolve the real client — the explicitly
        production-wired path — so we deliberately do not touch it.)
        """
        with patch("services.email_verification_service.boto3.client") as spy_client:
            EmailVerificationService(db_manager=Mock(), region="eu-west-1")

        spy_client.assert_not_called()

    def test_injected_fake_is_used_and_no_real_client_resolved(self, mock_ses_client):
        """An injected fake is returned by the lazy property; boto3 is never reached.

        The off-production default path (tests/scripts/fuzz) injects a fake. The lazy
        `ses_client` property must return that fake and NEVER resolve a real
        `boto3.client("ses", ...)`, even on repeated access.
        """
        with patch("services.email_verification_service.boto3.client") as spy_client:
            svc = EmailVerificationService(
                db_manager=Mock(), region="eu-west-1", ses_client=mock_ses_client
            )
            # First and repeated access both return the injected fake.
            assert svc.ses_client is mock_ses_client
            assert svc.ses_client is mock_ses_client

        spy_client.assert_not_called()

    def test_injected_fake_path_never_calls_real_verify_email_identity(
        self, mock_ses_client
    ):
        """initiate_verification off a non-wired (fake-injected) path calls only the fake.

        No real boto3 SES client is resolved and no real `verify_email_identity` is
        fired — the fuzz-identity burst is unreproducible from a non-production-wired
        construction.
        """
        with patch("services.email_verification_service.boto3.client") as spy_client:
            svc = EmailVerificationService(
                db_manager=Mock(), region="eu-west-1", ses_client=mock_ses_client
            )
            result = svc.initiate_verification("tenant1", "user@example.com")

        assert result["success"] is True
        # The fake received the call; boto3 (the real client) was never resolved.
        mock_ses_client.verify_email_identity.assert_called_once_with(
            EmailAddress="user@example.com"
        )
        spy_client.assert_not_called()


@pytest.mark.unit
class TestBugConditionB_PermissiveValidation:
    """B-email (SECONDARY) — the UNFIXED _validate_email accepts abusive local parts.

    Bug Condition isBugCondition_B_email(email): prototype-pollution keys, exploit
    special characters, no sane domain, or oversized parts are nonetheless accepted by
    the full RFC 5322 local-part regex.

    EXPECTED OUTCOME on UNFIXED code: each assertion FAILS because `_validate_email`
    returns True for these abusive addresses. On fixed code (tightened regex) they return
    False.
    """

    def test_unfixed_validate_email_accepts_prototype_pollution_key(self, service):
        # `__proto__` as the local part — a prototype-pollution key that should never
        # become a permanent SES identity. UNFIXED regex returns True → assertion FAILS.
        assert service._validate_email("__proto__@DA.BeauTy") is False

    def test_unfixed_validate_email_accepts_percent_local_part(self, service):
        # `%4` local part — exploit-ish special chars. UNFIXED regex returns True → FAILS.
        assert service._validate_email("%4@A.PAGe") is False

    def test_unfixed_validate_email_accepts_pipe_exploit_char(self, service):
        # `a|b` local part — pipe is in the RFC 5322 class the UNFIXED regex allows, so it
        # returns True → assertion FAILS, confirming the bug.
        #
        # NOTE: the design's loose example `a|b@x.y` does NOT isolate the pipe bug — its TLD
        # `y` is 1 char and the unfixed regex requires 2+ (`\.[a-zA-Z]{2,}$`), so that input
        # is rejected for an unrelated reason (short TLD), masking the pipe. A valid 2+ char
        # TLD is used here so the case fails ONLY on the pipe exploit char — the genuine
        # isBugCondition_B_email counterexample (confirmed: `a|b@x.yz` also returns True).
        assert service._validate_email("a|b@example.com") is False


# ============================================================================
# PRESERVATION TESTS (ses-sender-identity-pollution-cleanup, task 2)
#
# These capture the UNFIXED baseline behavior that the later fixes (tasks 3.x /
# 4.x) MUST preserve. Observation-first: they encode what the service does TODAY
# for genuine, deliverable senders and for the resend cooldown / DB transitions.
#
# EXPECTED OUTCOME on UNFIXED code: these tests PASS (they are the baseline to
# preserve). After the injectable-seam fix (3.x) and the tightened validation
# (4.x) land, they MUST STILL PASS — genuine senders are never abusive inputs, so
# Property 4 (Preservation) says F(x) == F'(x) for them.
#
# Validates (Preservation): Requirements 3.1 (genuine verify/resolve),
#                           3.5 (resend cooldown + DB status transitions)
# ============================================================================

# Genuine, deliverable sender addresses: plausible local parts, real domains. None of
# these trip isBugCondition_B_email (no prototype key, no exploit char, sane domain,
# not oversized), so the tightened validation (task 4.x) must keep accepting them.
GENUINE_SENDERS = [
    "info@h-dcn.nl",
    "webmaster@h-dcn.nl",
    "accounts.payable@jabaki.nl",
    "jan.jansen@example.com",
    "support+billing@mail.example.co.uk",
    "contact@my-company.org",
]


@pytest.mark.unit
class TestPreservationGenuineSenderVerify:
    """Preservation (req 3.1) — a genuine deliverable sender still verifies + resolves.

    Baseline on UNFIXED code: _validate_email accepts the address, initiate_verification
    calls SES verify_email_identity, a 'pending' record is stored, and get_verified_sender
    resolves a later 'verified' row. The fixes must keep all of this intact for genuine
    senders.
    """

    @pytest.mark.parametrize("email", GENUINE_SENDERS)
    def test_genuine_sender_passes_validation(self, service, email):
        """A genuine deliverable address passes _validate_email today (and must keep passing)."""
        assert service._validate_email(email) is True

    @pytest.mark.parametrize("email", GENUINE_SENDERS)
    def test_genuine_sender_initiate_calls_ses_and_stores_pending(
        self, service, mock_ses_client, mock_db, email
    ):
        """initiate_verification for a genuine address calls SES and stores a pending record."""
        result = service.initiate_verification("tenant1", email)

        assert result["success"] is True
        assert result["status"] == "pending"
        assert result["error"] is None
        mock_ses_client.verify_email_identity.assert_called_once_with(
            EmailAddress=email
        )

        # A pending record is persisted with the tenant + email + status.
        call_args = mock_db.execute_query.call_args
        assert "INSERT INTO email_verifications" in call_args[0][0]
        params = call_args[0][1]
        assert params[0] == "tenant1"
        assert params[1] == email
        assert params[2] == "pending"

    def test_genuine_sender_resolves_via_get_verified_sender(self, service, mock_db):
        """get_verified_sender returns a verified genuine sender with company name."""
        mock_db.execute_query.side_effect = [
            # verified email lookup
            [{"email": "webmaster@h-dcn.nl"}],
            # company name lookup
            [{"value": '"HDCN"'}],
        ]

        result = service.get_verified_sender("tenant1")

        assert result["verified"] is True
        assert result["email"] == "webmaster@h-dcn.nl"
        assert result["company_name"] == "HDCN"

    def test_existing_service_fixture_patches_boto3(self, service, mock_ses_client):
        """The existing `service` fixture (patches boto3 → fake) keeps wiring the fake client.

        Baseline: constructing via the fixture injects the mocked SES client, so no real
        AWS client is used. This must remain true across the fix.
        """
        assert service.ses_client is mock_ses_client


@pytest.mark.unit
class TestPreservationResendCooldownAndTransitions:
    """Preservation (req 3.5) — the 60s resend cooldown + DB status transitions unchanged.

    Baseline on UNFIXED code for VALID addresses:
    - a resend inside the 60s window is rejected (no SES call),
    - a resend after the window (or with no prior resend) proceeds + calls SES,
    - a successful resend writes status='pending' + last_resend_at,
    - update_email marks active records 'replaced' then initiates the new verification.
    """

    def test_resend_rejected_within_cooldown(self, service, mock_ses_client, mock_db):
        """Within the 60s window → rejected, SES not called (baseline to preserve)."""
        mock_db.execute_query.return_value = [
            {
                "email": "info@h-dcn.nl",
                "status": "pending",
                "last_checked_at": None,
                "last_resend_at": datetime.utcnow() - timedelta(seconds=10),
                "initiated_at": datetime(2025, 1, 1),
                "verified_at": None,
            }
        ]

        result = service.resend_verification("tenant1")

        assert result["success"] is False
        assert "60 seconds" in result["error"]
        mock_ses_client.verify_email_identity.assert_not_called()

    def test_resend_at_cooldown_boundary_just_under_is_rejected(
        self, service, mock_ses_client, mock_db
    ):
        """Just under the 60s boundary is still rejected (cooldown constant unchanged)."""
        mock_db.execute_query.return_value = [
            {
                "email": "info@h-dcn.nl",
                "status": "pending",
                "last_checked_at": None,
                "last_resend_at": datetime.utcnow()
                - timedelta(seconds=RESEND_COOLDOWN_SECONDS - 1),
                "initiated_at": datetime(2025, 1, 1),
                "verified_at": None,
            }
        ]

        result = service.resend_verification("tenant1")

        assert result["success"] is False
        mock_ses_client.verify_email_identity.assert_not_called()

    def test_resend_proceeds_after_cooldown_and_sets_pending(
        self, service, mock_ses_client, mock_db
    ):
        """After the window → proceeds, SES called, status set to pending + last_resend_at."""
        mock_db.execute_query.side_effect = [
            # _get_active_record
            [
                {
                    "email": "info@h-dcn.nl",
                    "status": "failed",
                    "last_checked_at": None,
                    "last_resend_at": datetime.utcnow() - timedelta(seconds=120),
                    "initiated_at": datetime(2025, 1, 1),
                    "verified_at": None,
                }
            ],
            # UPDATE last_resend_at + status
            [],
        ]

        result = service.resend_verification("tenant1")

        assert result["success"] is True
        assert result["error"] is None
        mock_ses_client.verify_email_identity.assert_called_once_with(
            EmailAddress="info@h-dcn.nl"
        )
        # The UPDATE transitions status → pending and stamps last_resend_at.
        update_call = mock_db.execute_query.call_args_list[1]
        query = update_call[0][0]
        assert "status = 'pending'" in query
        assert "last_resend_at" in query

    def test_resend_proceeds_when_no_previous_resend(
        self, service, mock_ses_client, mock_db
    ):
        """last_resend_at is None (first resend) → proceeds (baseline)."""
        mock_db.execute_query.side_effect = [
            [
                {
                    "email": "info@h-dcn.nl",
                    "status": "pending",
                    "last_checked_at": None,
                    "last_resend_at": None,
                    "initiated_at": datetime(2025, 1, 1),
                    "verified_at": None,
                }
            ],
            [],
        ]

        result = service.resend_verification("tenant1")

        assert result["success"] is True
        mock_ses_client.verify_email_identity.assert_called_once()

    def test_update_email_marks_replaced_then_initiates(
        self, service, mock_ses_client, mock_db
    ):
        """update_email transitions old active records → 'replaced', then verifies the new one."""
        mock_db.execute_query.side_effect = [
            # UPDATE ... SET status = 'replaced'
            [],
            # INSERT new pending record from initiate_verification
            [],
        ]

        result = service.update_email("tenant1", "new.sender@example.com")

        assert result["success"] is True
        assert result["status"] == "pending"
        replace_call = mock_db.execute_query.call_args_list[0]
        assert "SET status = 'replaced'" in replace_call[0][0]
        mock_ses_client.verify_email_identity.assert_called_once_with(
            EmailAddress="new.sender@example.com"
        )

    def test_check_status_verified_transition_persists(
        self, service, mock_ses_client, mock_db
    ):
        """SES 'Success' → local 'verified' and the DB status transition is written (baseline)."""
        mock_db.execute_query.side_effect = [
            # _get_active_record
            [
                {
                    "email": "info@h-dcn.nl",
                    "status": "pending",
                    "last_checked_at": None,
                    "last_resend_at": None,
                    "initiated_at": datetime(2025, 1, 1),
                    "verified_at": None,
                }
            ],
            # _update_verification_status
            [],
        ]
        mock_ses_client.get_identity_verification_attributes.return_value = {
            "VerificationAttributes": {
                "info@h-dcn.nl": {"VerificationStatus": "Success"}
            }
        }

        result = service.check_status("tenant1")

        assert result["success"] is True
        assert result["status"] == "verified"
        update_call = mock_db.execute_query.call_args_list[1]
        assert "SET status = %s" in update_call[0][0]
        assert update_call[0][1][0] == "verified"
