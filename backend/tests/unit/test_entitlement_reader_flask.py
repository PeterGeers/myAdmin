"""
S4 T15 — unit tests for the optional, additive Flask-plane entitlement reader.

Covers :mod:`auth.entitlement_reader`
(:func:`resolve_capabilities` / :func:`has_capability`), which prefers the
resolved entitlement stamped into the verified token (``custom:entitlements``)
and falls back to the MySQL path (``role_cache`` → module gate → the shared T1
resolver) when the token does not carry a usable answer.

The R5.3 guarantee under test: the token-path and DB-path answers are IDENTICAL
for the same MySQL state, because both carry the SAME T1 resolution rule (one
rule, two carriers). We do not reimplement the rule here — the DB-path oracle is
the resolver itself / the real Flask composition (as in T2).

Reference: .kiro/specs/multi-tenant/s4-token-entitlement-projection/
  design.md "Reader helpers (Flask plane)"; R5.3, R4.1.
"""

import os
import sys

import pytest

sys.path.append(os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from auth import role_cache
from auth.entitlement_claim_codec import CLAIM_NAME, encode_entitlements
from auth.entitlement_reader import (
    has_capability,
    resolve_capabilities,
    resolve_capabilities_from_db,
)
from auth.entitlement_resolver import resolve_entitlement
from services.module_registry import MODULE_REGISTRY


@pytest.fixture(autouse=True)
def _clear_role_cache():
    """Ensure the module-level role cache never leaks between tests."""
    role_cache._role_cache.clear()
    yield
    role_cache._role_cache.clear()


def _wire_db(mock_db, roles_by_tenant, active_by_tenant):
    """Answer BOTH the role_cache and has_module queries from seeded state.

    Mirrors the T2 oracle wiring so the DB fallback path runs the REAL query/cache
    code (no reimplementation), honouring the testing-standards mock_db rule.
    """

    def _execute_query(query, params=None, fetch=True, commit=False):
        params = params or ()
        q = " ".join(query.split())
        if "FROM user_tenant_roles" in q:
            _email, tenant = params
            return [{"role": r} for r in roles_by_tenant.get(tenant, [])]
        if "FROM tenant_modules" in q:
            tenant, module_name = params
            active = active_by_tenant.get(tenant, [])
            return [{"is_active": 1}] if module_name in active else []
        raise AssertionError(f"Unexpected query: {q!r}")

    mock_db.execute_query.side_effect = _execute_query
    return mock_db


def _token_claims(entitlement_map, *, email="user@example.com"):
    """Build a verified-claims dict carrying an encoded custom:entitlements claim."""
    return {"email": email, CLAIM_NAME: encode_entitlements(entitlement_map)}


# ---------------------------------------------------------------------------
# 1. Token claim present + tenant present -> token caps, NO DB read.
# ---------------------------------------------------------------------------

class TestTokenFastPath:
    def test_token_present_tenant_present_uses_token_no_db(self, mock_db):
        claims = _token_claims(
            {"ExampleTenant": ["finance_read", "finance_create"]}
        )

        caps = resolve_capabilities(claims, "ExampleTenant", mock_db)

        assert caps == {"finance_read", "finance_create"}
        # The whole point of the fast path: no MySQL touched.
        mock_db.execute_query.assert_not_called()

    def test_token_present_empty_caps_is_authoritative_no_db(self, mock_db):
        # An explicit empty list for a listed tenant is an authoritative "no caps",
        # NOT an absence — so it must still avoid the DB.
        claims = _token_claims({"ExampleTenant": []})

        caps = resolve_capabilities(claims, "ExampleTenant", mock_db)

        assert caps == set()
        mock_db.execute_query.assert_not_called()

    def test_has_capability_token_path_no_db(self, mock_db):
        claims = _token_claims({"ExampleTenant": ["finance_read"]})

        assert has_capability(claims, "ExampleTenant", "finance_read", mock_db) is True
        assert (
            has_capability(claims, "ExampleTenant", "finance_delete", mock_db) is False
        )
        mock_db.execute_query.assert_not_called()


# ---------------------------------------------------------------------------
# 2. Claim absent -> falls back to role_cache/resolver, SAME caps as resolver.
# ---------------------------------------------------------------------------

class TestClaimAbsentFallsBack:
    def test_claim_absent_falls_back_and_matches_resolver(self, mock_db):
        roles_by_tenant = {"ExampleTenant": ["Finance_CRUD"]}
        active_by_tenant = {"ExampleTenant": ["FIN"]}
        _wire_db(mock_db, roles_by_tenant, active_by_tenant)

        # No entitlement claim in the verified token.
        claims = {"email": "user@example.com"}

        caps = resolve_capabilities(claims, "ExampleTenant", mock_db)

        # Oracle: the shared T1 resolver over the same seeded state.
        expected = set(
            resolve_entitlement(
                user_roles_by_tenant=roles_by_tenant,
                active_modules_by_tenant=active_by_tenant,
                module_registry=MODULE_REGISTRY,
            )["ExampleTenant"]
        )
        assert caps == expected
        # Non-vacuous: it really granted write access via the DB path.
        assert "finance_create" in caps
        # It actually consulted MySQL (role read + module gate).
        assert mock_db.execute_query.called

    def test_claim_absent_no_email_fails_closed(self, mock_db):
        # No claim AND no email -> cannot query; fail-closed (no caps), no DB read.
        caps = resolve_capabilities({}, "ExampleTenant", mock_db)
        assert caps == set()
        mock_db.execute_query.assert_not_called()


# ---------------------------------------------------------------------------
# 3. Overflow / fallback_required claim -> falls back to DB.
# ---------------------------------------------------------------------------

class TestOverflowAndUnknownVersionFallBack:
    def test_overflow_claim_falls_back_to_db(self, mock_db):
        roles_by_tenant = {"ExampleTenant": ["Finance_Read"]}
        active_by_tenant = {"ExampleTenant": ["FIN"]}
        _wire_db(mock_db, roles_by_tenant, active_by_tenant)

        # Force an overflow signal by encoding with a tiny budget.
        big_map = {"ExampleTenant": ["finance_read", "finance_create"]}
        overflow_value = encode_entitlements(big_map, budget=1)
        claims = {"email": "user@example.com", CLAIM_NAME: overflow_value}

        caps = resolve_capabilities(claims, "ExampleTenant", mock_db)

        expected = set(
            resolve_entitlement(
                user_roles_by_tenant=roles_by_tenant,
                active_modules_by_tenant=active_by_tenant,
                module_registry=MODULE_REGISTRY,
            )["ExampleTenant"]
        )
        assert caps == expected
        assert mock_db.execute_query.called  # overflow -> consulted MySQL

    def test_unknown_version_claim_falls_back_to_db(self, mock_db):
        roles_by_tenant = {"ExampleTenant": ["Finance_Read"]}
        active_by_tenant = {"ExampleTenant": ["FIN"]}
        _wire_db(mock_db, roles_by_tenant, active_by_tenant)

        # A claim from an unrecognised future version -> decoder requires fallback.
        claims = {
            "email": "user@example.com",
            CLAIM_NAME: '{"v":999,"t":{"ExampleTenant":["should_be_ignored"]}}',
        }

        caps = resolve_capabilities(claims, "ExampleTenant", mock_db)

        expected = set(
            resolve_entitlement(
                user_roles_by_tenant=roles_by_tenant,
                active_modules_by_tenant=active_by_tenant,
                module_registry=MODULE_REGISTRY,
            )["ExampleTenant"]
        )
        assert "should_be_ignored" not in caps
        assert caps == expected
        assert "finance_read" in caps  # non-vacuous
        assert mock_db.execute_query.called


# ---------------------------------------------------------------------------
# 4. Tenant not in the token claim -> falls back to DB.
# ---------------------------------------------------------------------------

class TestTenantNotInClaimFallsBack:
    def test_tenant_absent_from_claim_falls_back_to_db(self, mock_db):
        roles_by_tenant = {"TenantB": ["STR_Read"]}
        active_by_tenant = {"TenantB": ["STR"]}
        _wire_db(mock_db, roles_by_tenant, active_by_tenant)

        # Token answers for TenantA only; we ask about TenantB.
        claims = _token_claims({"TenantA": ["finance_read"]})

        caps = resolve_capabilities(claims, "TenantB", mock_db)

        expected = set(
            resolve_entitlement(
                user_roles_by_tenant=roles_by_tenant,
                active_modules_by_tenant=active_by_tenant,
                module_registry=MODULE_REGISTRY,
            )["TenantB"]
        )
        assert caps == expected
        assert "str_read" in caps
        assert mock_db.execute_query.called


# ---------------------------------------------------------------------------
# 5. R5.3 guarantee: token-path and DB-path yield IDENTICAL decisions.
# ---------------------------------------------------------------------------

class TestTokenPathEqualsDbPath:
    """For the same seeded state, the token and DB carriers give the same answer."""

    @pytest.mark.parametrize(
        "roles_by_tenant,active_by_tenant",
        [
            ({"T": ["Finance_CRUD"]}, {"T": ["FIN"]}),
            ({"T": ["Finance_Read"]}, {"T": ["FIN"]}),
            ({"T": ["Finance_CRUD", "STR_CRUD"]}, {"T": ["FIN", "STR"]}),
            ({"T": ["Finance_CRUD"]}, {"T": ["STR"]}),        # role for inactive module
            ({"T": ["Finance_CRUD", "STR_CRUD"]}, {"T": []}),  # no active modules
            ({"T": ["System_CRUD"]}, {"T": ["FIN"]}),          # global role -> none
        ],
    )
    def test_token_and_db_paths_are_identical(
        self, mock_db, roles_by_tenant, active_by_tenant
    ):
        tenant = "T"

        # DB path: no claim -> fall back to MySQL.
        _wire_db(mock_db, roles_by_tenant, active_by_tenant)
        db_caps = resolve_capabilities(
            {"email": "user@example.com"}, tenant, mock_db
        )

        # Token path: the SAME state, stamped into the token by the shared resolver.
        resolved = resolve_entitlement(
            user_roles_by_tenant=roles_by_tenant,
            active_modules_by_tenant=active_by_tenant,
            module_registry=MODULE_REGISTRY,
        )
        token_claims = _token_claims({tenant: resolved[tenant]})
        # A fresh mock proves the token path took NO DB read.
        token_caps = resolve_capabilities(token_claims, tenant, mock_db_only_token())

        assert token_caps == db_caps  # R5.3 / R4.1 one-rule-two-carriers

    def test_direct_db_helper_equals_resolver(self, mock_db):
        # resolve_capabilities_from_db is the exact composition T2 proved equal
        # to the Flask decision; confirm it equals the shared resolver here too.
        roles_by_tenant = {"T": ["Finance_Read", "STR_CRUD"]}
        active_by_tenant = {"T": ["FIN"]}  # STR inactive
        _wire_db(mock_db, roles_by_tenant, active_by_tenant)

        db_caps = resolve_capabilities_from_db("user@example.com", "T", mock_db)
        expected = set(
            resolve_entitlement(
                user_roles_by_tenant=roles_by_tenant,
                active_modules_by_tenant=active_by_tenant,
                module_registry=MODULE_REGISTRY,
            )["T"]
        )
        assert db_caps == expected
        assert not any(c.startswith("str_") for c in db_caps)  # inactive module gated


def mock_db_only_token():
    """A DB stand-in that FAILS if touched — proves the token path avoids MySQL."""
    from unittest.mock import MagicMock

    db = MagicMock()
    db.execute_query.side_effect = AssertionError(
        "token path must not query the database"
    )
    return db
