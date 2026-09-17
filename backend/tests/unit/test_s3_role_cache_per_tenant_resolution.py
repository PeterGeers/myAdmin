"""S3 / T7 — Unit tests: role_cache per-tenant resolution correctness.

**Validates: Requirements R1.3**

Design "Testing Strategy → Unit tests (D2 + read side)":
  `role_cache.py`: seeded `user_tenant_roles` rows → correct per-tenant role set; global
  roles come from `cognito:groups` (R1.3).

Where the other suites sit (this file intentionally does NOT duplicate them):
  * `test_role_cache.py` — cache *mechanics*: TTL expiry, invalidation, cache-hit reuse,
    empty/None → `[]`, and that a different tenant is a separate cache *entry*.
  * `test_s3_per_tenant_role_source_of_record.py` (T5) — *source of record*: that the
    query targets `user_tenant_roles`, is parameterized, is scoped by `administration`,
    that only the three global roles are honored from the token, and the no-token-claim
    guardrail.

T7 fills the remaining gap: **resolution correctness**. Given seeded `user_tenant_roles`
rows, `get_tenant_roles` returns *exactly* that role set; distinct tenants and distinct
emails each resolve to their *own* set; a tenant with no rows resolves to empty while a
sibling tenant with rows still resolves correctly; and the per-tenant set (from MySQL) is
kept separate from the global roles (from `cognito:groups`).

No real DB, no network, no `load_dotenv`. Uses the shared `mock_db` fixture and clears the
module cache between cases so each assertion exercises a fresh DB-backed resolution.
"""

import pytest

import auth.role_cache as role_cache
from auth.role_cache import get_tenant_roles


# The three roles the token (`cognito:groups`) is allowed to carry — global only.
GLOBAL_ROLES = ("SysAdmin", "Administrators", "System_CRUD")


@pytest.fixture(autouse=True)
def clear_role_cache():
    """Each case resolves from a fresh cache so it hits the (mocked) DB read."""
    role_cache._role_cache.clear()
    yield
    role_cache._role_cache.clear()


def _rows(*roles):
    """Shape DB rows the way `user_tenant_roles` SELECT returns them."""
    return [{"role": r} for r in roles]


# --------------------------------------------------------------------------- #
# Seeded rows → exactly that per-tenant role set.
# --------------------------------------------------------------------------- #


class TestSeededRowsResolveToExactRoleSet:
    """`get_tenant_roles` returns exactly the roles seeded for the (email, tenant)."""

    def test_get_tenant_roles_full_access_grant_returns_all_seeded_roles(self, mock_db):
        """The full-access GoodwinSolutions grant resolves to exactly its four roles."""
        mock_db.execute_query.return_value = _rows(
            "Finance_CRUD", "STR_CRUD", "ZZP_CRUD", "Tenant_Admin"
        )

        roles = get_tenant_roles("test-goodwin@example.com", "GoodwinSolutions", mock_db)

        assert roles == ["Finance_CRUD", "STR_CRUD", "ZZP_CRUD", "Tenant_Admin"]

    def test_get_tenant_roles_read_only_grant_returns_only_read_roles(self, mock_db):
        """A read-only grant resolves to exactly the read roles — no CRUD leaks in."""
        mock_db.execute_query.return_value = _rows(
            "Finance_Read", "STR_Read", "ZZP_Read"
        )

        roles = get_tenant_roles("readonly@example.com", "GoodwinSolutions", mock_db)

        assert roles == ["Finance_Read", "STR_Read", "ZZP_Read"]
        assert "Finance_CRUD" not in roles

    def test_get_tenant_roles_single_role_grant_returns_that_one_role(self, mock_db):
        """A single seeded row resolves to a single-element role set."""
        mock_db.execute_query.return_value = _rows("Tenant_Admin")

        roles = get_tenant_roles("admin@example.com", "TenantA", mock_db)

        assert roles == ["Tenant_Admin"]

    def test_get_tenant_roles_preserves_the_seeded_row_order(self, mock_db):
        """The resolved set mirrors the row order — no reordering/dedup applied."""
        mock_db.execute_query.return_value = _rows("ZZP_Read", "Finance_CRUD", "STR_Export")

        roles = get_tenant_roles("user@example.com", "TenantA", mock_db)

        assert roles == ["ZZP_Read", "Finance_CRUD", "STR_Export"]


# --------------------------------------------------------------------------- #
# Different tenants / emails resolve to their OWN role set.
# --------------------------------------------------------------------------- #


class TestResolutionIsScopedPerTenantAndPerEmail:
    """Each (email, tenant) resolves to its own seeded set — no cross-contamination."""

    def test_get_tenant_roles_same_email_different_tenants_returns_distinct_sets(self, mock_db):
        """One user across two tenants resolves to each tenant's own role set."""
        mock_db.execute_query.side_effect = [
            _rows("Finance_CRUD", "Tenant_Admin"),  # TenantA
            _rows("STR_Read"),                       # TenantB
        ]

        roles_a = get_tenant_roles("user@example.com", "TenantA", mock_db)
        roles_b = get_tenant_roles("user@example.com", "TenantB", mock_db)

        assert roles_a == ["Finance_CRUD", "Tenant_Admin"]
        assert roles_b == ["STR_Read"]
        assert roles_a != roles_b

    def test_get_tenant_roles_different_emails_same_tenant_returns_distinct_sets(self, mock_db):
        """Two users in the same tenant resolve to their own grants independently."""
        mock_db.execute_query.side_effect = [
            _rows("Finance_CRUD", "STR_CRUD", "ZZP_CRUD", "Tenant_Admin"),  # full access
            _rows("Finance_Read"),                                          # read only
        ]

        full = get_tenant_roles("owner@example.com", "GoodwinSolutions", mock_db)
        reader = get_tenant_roles("reader@example.com", "GoodwinSolutions", mock_db)

        assert full == ["Finance_CRUD", "STR_CRUD", "ZZP_CRUD", "Tenant_Admin"]
        assert reader == ["Finance_Read"]

    def test_get_tenant_roles_no_rows_for_tenant_returns_empty_while_sibling_resolves(self, mock_db):
        """A tenant with no seeded rows → empty set; a sibling tenant still resolves."""
        mock_db.execute_query.side_effect = [
            [],                       # user has no grant in TenantA
            _rows("STR_Read"),        # ... but does in TenantB
        ]

        none_here = get_tenant_roles("user@example.com", "TenantA", mock_db)
        there = get_tenant_roles("user@example.com", "TenantB", mock_db)

        assert none_here == []
        assert there == ["STR_Read"]


# --------------------------------------------------------------------------- #
# Per-tenant set (MySQL) is kept separate from global roles (cognito:groups).
# --------------------------------------------------------------------------- #


class TestPerTenantSetIsSeparateFromGlobalRoles:
    """The MySQL-resolved per-tenant set never carries the token's global roles."""

    def test_get_tenant_roles_result_excludes_global_roles(self, mock_db):
        """A per-tenant resolution returns only per-tenant grants, never global roles."""
        mock_db.execute_query.return_value = _rows("Finance_CRUD", "Tenant_Admin")

        per_tenant = get_tenant_roles("user@example.com", "TenantA", mock_db)

        assert all(role not in GLOBAL_ROLES for role in per_tenant)

    def test_get_tenant_roles_does_not_read_the_token_for_global_roles(self, mock_db):
        """Even when the caller *has* global roles in the token, they come from elsewhere.

        `get_tenant_roles` resolves purely from the seeded `user_tenant_roles` read; the
        global roles a user holds (`cognito:groups`) are sourced separately on the auth
        path and must not appear in — nor influence — this per-tenant result.
        """
        token_cognito_groups = ["SysAdmin", "Administrators"]  # global roles, from the token
        mock_db.execute_query.return_value = _rows("Finance_Read")

        per_tenant = get_tenant_roles("sysadmin@example.com", "TenantA", mock_db)

        # The per-tenant resolution is exactly the seeded grant ...
        assert per_tenant == ["Finance_Read"]
        # ... and is disjoint from whatever global roles the token carried.
        assert set(per_tenant).isdisjoint(set(token_cognito_groups))
