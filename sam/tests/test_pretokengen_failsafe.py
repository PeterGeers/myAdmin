"""
S4 D2 / T12 (amended, Option A) — unit tests for the PreTokenGen handler's
fail-safe + fail-fast wiring, reading the S3 DynamoDB projection (NOT MySQL).

Two DISTINCT behaviours, opposite policies (see the handler docstring):

- **Fail-safe (R2.3)** — a RUNTIME resolution failure at issuance (DynamoDB query
  blip, malformed item, resolver/codec error) must NOT stamp a partial/garbage
  claim: the claim is OMITTED on BOTH token generations (all-or-nothing), the
  failure is logged by user identity + exception TYPE only (never secrets / config
  / item contents), and a VALID event is returned so login is not broken.
- **Fail-fast (R2.5)** — a genuine MISCONFIGURATION (missing/blank projection
  table/region env → :class:`services.dynamodb_client.DynamoDBConfigError`) must
  surface LOUDLY: it propagates out of the handler and is never swallowed into a
  per-request omit.

DynamoDB is faked; the shared resolver/codec are the real logic (not re-implemented).
"""

import logging
import os
import sys

import pytest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from sam.pretokengen import handler as handler_mod
from sam.pretokengen.projection_governance_reader import ProjectionGovernanceReader

_BACKEND_SRC = os.path.join(_REPO_ROOT, "backend", "src")
if _BACKEND_SRC not in sys.path:
    sys.path.insert(0, _BACKEND_SRC)

from auth.entitlement_claim_codec import CLAIM_NAME
from services.dynamodb_client import DynamoDBConfigError


# ---------------------------------------------------------------------------
# Fakes / helpers
# ---------------------------------------------------------------------------

# Sensitive values that must NEVER appear in a log record (R2.3 — no secrets,
# config values, or item contents leaked through the fail-safe path).
_DB_PASSWORD = "sup3r-s3cret-pw"
_DB_HOST = "governance-db.internal"
_ITEM_SECRET_ROLE = "Finance_CRUD_SECRET_ROW_VALUE"


def make_v2_event(email="admin@example.com", tenants="ExampleTenant"):
    user_attributes = {"email": email, "sub": "sub-123"}
    if tenants is not None:
        user_attributes["custom:tenants"] = tenants
    return {
        "version": "2",
        "triggerSource": "TokenGeneration_HostedAuth",
        "userPoolId": "eu-west-1_xyrlzfqbl",
        "request": {
            "userAttributes": user_attributes,
            "groupConfiguration": {"groupsToOverride": ["Administrators"]},
        },
        "response": {
            "claimsAndScopeOverrideDetails": {
                "idTokenGeneration": {},
                "accessTokenGeneration": {},
            }
        },
    }


def _claims(result, generation):
    gen = result["response"]["claimsAndScopeOverrideDetails"][generation]
    return gen.get("claimsToAddOrOverride", {})


class RaisingTable:
    """A projection table whose ``query`` raises, to simulate a runtime failure."""

    def __init__(self, exc):
        self._exc = exc

    def query(self, KeyConditionExpression=None):
        raise self._exc


def _install_reader(monkeypatch, table):
    reader = ProjectionGovernanceReader(table=table)
    monkeypatch.setattr(handler_mod, "_build_reader", lambda: reader)
    return reader


# ---------------------------------------------------------------------------
# Fail-safe (R2.3) — runtime resolution failure at issuance
# ---------------------------------------------------------------------------


class TestFailSafeRuntimeError:
    def test_query_error_omits_claim_on_both_generations(self, monkeypatch, caplog):
        _install_reader(monkeypatch, RaisingTable(RuntimeError("DynamoDB unreachable")))
        event = make_v2_event("admin@example.com")

        with caplog.at_level(logging.INFO):
            result = handler_mod.handler(event, context=None)

        # Claim OMITTED on BOTH generations (fail-closed for entitlement).
        assert CLAIM_NAME not in _claims(result, "idTokenGeneration")
        assert CLAIM_NAME not in _claims(result, "accessTokenGeneration")
        # A valid event is still returned (login not broken).
        assert result is event
        assert result["version"] == "2"

    def test_query_error_logs_identity_and_exception_type_only(
        self, monkeypatch, caplog
    ):
        _install_reader(monkeypatch, RaisingTable(RuntimeError("boom")))
        with caplog.at_level(logging.INFO):
            handler_mod.handler(make_v2_event("audit@example.com"), context=None)

        # Exactly one fail-safe log record, carrying the user identity + the
        # exception TYPE (not the message/payload).
        omit_records = [
            r for r in caplog.records if "omitting entitlement claim" in r.getMessage()
        ]
        assert len(omit_records) == 1
        msg = omit_records[0].getMessage()
        assert "audit@example.com" in msg
        assert "RuntimeError" in msg
        # The exception PAYLOAD ("boom") must not be logged.
        assert "boom" not in msg

    def test_malformed_item_is_all_or_nothing_zero_claims(self, monkeypatch, caplog):
        """A malformed projection item mid-flow leaves ZERO claims (all-or-nothing).

        The query returns a non-dict "item"; the reader's ``item.get(...)`` trips
        on it and raises, proving the claim value is computed FULLY before any
        stamping — a half-written claim is impossible, so BOTH generations stay
        empty.
        """

        class BadItemTable:
            def query(self, KeyConditionExpression=None):
                # A malformed item (not a dict) — reader's item.get() will raise.
                return {"Items": ["not-a-dict-item"]}

        _install_reader(monkeypatch, BadItemTable())

        with caplog.at_level(logging.INFO):
            result = handler_mod.handler(make_v2_event(tenants="TenantA"), context=None)

        assert CLAIM_NAME not in _claims(result, "idTokenGeneration")
        assert CLAIM_NAME not in _claims(result, "accessTokenGeneration")

    def test_no_secret_or_item_value_appears_in_logs(self, monkeypatch, caplog):
        """caplog must never contain a secret/host or item contents (R2.3)."""
        # The exception message itself embeds sensitive-looking data to prove the
        # handler does not log the exception payload.
        secret_exc = RuntimeError(
            f"connect failed host={_DB_HOST} password={_DB_PASSWORD} "
            f"row={_ITEM_SECRET_ROLE}"
        )
        _install_reader(monkeypatch, RaisingTable(secret_exc))

        with caplog.at_level(logging.INFO):
            handler_mod.handler(make_v2_event(), context=None)

        all_logs = "\n".join(r.getMessage() for r in caplog.records)
        assert _DB_PASSWORD not in all_logs
        assert _DB_HOST not in all_logs
        assert _ITEM_SECRET_ROLE not in all_logs


# ---------------------------------------------------------------------------
# Fail-fast (R2.5) — genuine misconfiguration
# ---------------------------------------------------------------------------


class TestFailFastConfig:
    def test_missing_projection_config_raises_and_is_not_swallowed(
        self, monkeypatch, caplog
    ):
        """Missing projection env → DynamoDBConfigError propagates (not an omit).

        We DON'T patch ``_build_reader`` — the real reader is built, and its
        ``.table`` resolves fail-fast on first use because the required env vars
        are unset. The config error must propagate, never become a fail-safe omit.
        """
        monkeypatch.setattr(handler_mod, "_reader_cache", None)
        for var in ("GOVERNANCE_PROJECTION_TABLE", "AWS_REGION"):
            monkeypatch.delenv(var, raising=False)

        with caplog.at_level(logging.INFO):
            with pytest.raises(DynamoDBConfigError):
                handler_mod.handler(make_v2_event(), context=None)

        # It must NOT have been swallowed into a fail-safe omit log.
        omit_records = [
            r for r in caplog.records if "omitting entitlement claim" in r.getMessage()
        ]
        assert omit_records == []

    def test_config_error_from_table_is_not_swallowed_by_failsafe(
        self, monkeypatch, caplog
    ):
        """A DynamoDBConfigError surfacing during use propagates (belt-and-braces).

        The fail-safe ``except`` re-raises the config-error types rather than
        turning them into an omit. Simulate a table whose query raises
        DynamoDBConfigError and assert it is NOT swallowed.
        """
        _install_reader(monkeypatch, RaisingTable(DynamoDBConfigError("bad config")))

        with caplog.at_level(logging.INFO):
            with pytest.raises(DynamoDBConfigError):
                handler_mod.handler(make_v2_event(), context=None)

        omit_records = [
            r for r in caplog.records if "omitting entitlement claim" in r.getMessage()
        ]
        assert omit_records == []
