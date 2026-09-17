"""
Unit tests for the S4 D1 pure resolved-entitlement resolver.

Covers R1.1 (roles ∩ active modules → capabilities), R1.2 (pure/deterministic),
R1.4 (global roles not re-derived). Property-based coverage is T6–T9.

The resolver is pure: these tests pass plain dict/list structures and the real
``MODULE_REGISTRY`` / ``ROLE_PERMISSIONS`` maps — no DB, no mocks needed.

Reference: .kiro/specs/multi-tenant/s4-token-entitlement-projection/
"""

import os
import sys

import pytest

sys.path.append(os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from auth.cognito_utils import ROLE_PERMISSIONS
from auth.entitlement_resolver import GLOBAL_ROLES, resolve_entitlement
from services.module_registry import MODULE_REGISTRY


# ---------------------------------------------------------------------------
# Helpers — expected capability sets derived from the SAME maps the resolver
# reads, so tests assert the composition, not a hand-copied constant.
# ---------------------------------------------------------------------------

def caps_for(*roles):
    """Expected sorted capabilities for a set of roles (wildcard short-circuits)."""
    acc = set()
    for role in roles:
        perms = ROLE_PERMISSIONS.get(role, [])
        if "*" in perms:
            return ["*"]
        acc.update(perms)
    return sorted(acc)


class TestFullAccessUser:
    """R1.1 — a Finance_CRUD user in a tenant with FIN active gets all FIN caps."""

    def test_finance_crud_with_fin_active_returns_finance_crud_caps(self):
        result = resolve_entitlement(
            user_roles_by_tenant={"ExampleTenant": ["Finance_CRUD"]},
            active_modules_by_tenant={"ExampleTenant": ["FIN"]},
            module_registry=MODULE_REGISTRY,
        )

        assert result == {"ExampleTenant": caps_for("Finance_CRUD")}
        # Sanity: the full-access role really does include write/delete caps.
        assert "finance_create" in result["ExampleTenant"]
        assert "finance_delete" in result["ExampleTenant"]

    def test_multiple_active_modules_union_capabilities(self):
        result = resolve_entitlement(
            user_roles_by_tenant={"ExampleTenant": ["Finance_CRUD", "STR_CRUD"]},
            active_modules_by_tenant={"ExampleTenant": ["FIN", "STR"]},
            module_registry=MODULE_REGISTRY,
        )

        assert result == {"ExampleTenant": caps_for("Finance_CRUD", "STR_CRUD")}


class TestReadOnlyUser:
    """R1.1 — a Finance_Read user gets only read/list caps, no write/delete."""

    def test_finance_read_returns_only_read_caps(self):
        result = resolve_entitlement(
            user_roles_by_tenant={"ExampleTenant": ["Finance_Read"]},
            active_modules_by_tenant={"ExampleTenant": ["FIN"]},
            module_registry=MODULE_REGISTRY,
        )

        caps = result["ExampleTenant"]
        assert result == {"ExampleTenant": caps_for("Finance_Read")}
        assert "finance_read" in caps
        assert "finance_create" not in caps
        assert "finance_delete" not in caps


class TestRoleForInactiveModuleExcluded:
    """R1.1 — a role whose module is inactive/absent contributes nothing."""

    def test_role_for_inactive_module_excluded(self):
        # User holds Finance_CRUD but FIN is not active for the tenant.
        result = resolve_entitlement(
            user_roles_by_tenant={"ExampleTenant": ["Finance_CRUD"]},
            active_modules_by_tenant={"ExampleTenant": ["STR"]},
            module_registry=MODULE_REGISTRY,
        )

        # STR is active but the user has no STR role -> empty.
        assert result == {"ExampleTenant": []}

    def test_only_active_module_roles_survive_mixed(self):
        # FIN active, STR inactive. User has both a FIN role and an STR role.
        result = resolve_entitlement(
            user_roles_by_tenant={"ExampleTenant": ["Finance_Read", "STR_CRUD"]},
            active_modules_by_tenant={"ExampleTenant": ["FIN"]},
            module_registry=MODULE_REGISTRY,
        )

        # Only the FIN role's caps appear; STR caps are excluded.
        assert result == {"ExampleTenant": caps_for("Finance_Read")}
        assert not any(c.startswith("str_") for c in result["ExampleTenant"])


class TestTenantWithNoActiveModules:
    """R1.1 — a tenant with no active modules resolves to an empty capability set."""

    def test_no_active_modules_returns_empty_list(self):
        result = resolve_entitlement(
            user_roles_by_tenant={"ExampleTenant": ["Finance_CRUD", "STR_CRUD"]},
            active_modules_by_tenant={"ExampleTenant": []},
            module_registry=MODULE_REGISTRY,
        )

        # Tenant key present (user belongs there) but no capabilities.
        assert result == {"ExampleTenant": []}

    def test_tenant_absent_from_active_modules_map_returns_empty(self):
        result = resolve_entitlement(
            user_roles_by_tenant={"ExampleTenant": ["Finance_CRUD"]},
            active_modules_by_tenant={},  # tenant not present at all
            module_registry=MODULE_REGISTRY,
        )

        assert result == {"ExampleTenant": []}


class TestMultiTenantUser:
    """R1.1 — each tenant resolved independently from its own roles + modules."""

    def test_multi_tenant_independent_resolution(self):
        result = resolve_entitlement(
            user_roles_by_tenant={
                "TenantA": ["Finance_CRUD"],
                "TenantB": ["STR_Read"],
                "TenantC": ["Finance_CRUD"],  # FIN inactive here
            },
            active_modules_by_tenant={
                "TenantA": ["FIN"],
                "TenantB": ["STR"],
                "TenantC": ["STR"],  # user has no STR role in C
            },
            module_registry=MODULE_REGISTRY,
        )

        assert result["TenantA"] == caps_for("Finance_CRUD")
        assert result["TenantB"] == caps_for("STR_Read")
        assert result["TenantC"] == []  # role-for-inactive-module -> empty
        assert set(result.keys()) == {"TenantA", "TenantB", "TenantC"}


class TestDuplicateRoles:
    """R1.1 — duplicate roles in the input are tolerated (deduplicated)."""

    def test_duplicate_roles_do_not_change_result(self):
        with_dupes = resolve_entitlement(
            user_roles_by_tenant={"ExampleTenant": ["Finance_Read", "Finance_Read"]},
            active_modules_by_tenant={"ExampleTenant": ["FIN"]},
            module_registry=MODULE_REGISTRY,
        )
        without = resolve_entitlement(
            user_roles_by_tenant={"ExampleTenant": ["Finance_Read"]},
            active_modules_by_tenant={"ExampleTenant": ["FIN"]},
            module_registry=MODULE_REGISTRY,
        )

        assert with_dupes == without == {"ExampleTenant": caps_for("Finance_Read")}


class TestEmptyInput:
    """R1.1 — empty inputs produce an empty map (no crash)."""

    def test_empty_roles_map_returns_empty_map(self):
        result = resolve_entitlement(
            user_roles_by_tenant={},
            active_modules_by_tenant={"ExampleTenant": ["FIN"]},
            module_registry=MODULE_REGISTRY,
        )
        assert result == {}

    def test_tenant_with_empty_roles_returns_empty_caps(self):
        result = resolve_entitlement(
            user_roles_by_tenant={"ExampleTenant": []},
            active_modules_by_tenant={"ExampleTenant": ["FIN"]},
            module_registry=MODULE_REGISTRY,
        )
        assert result == {"ExampleTenant": []}


class TestGlobalRolesNotReDerived:
    """R1.4 — global roles are not re-derived into the per-tenant map."""

    def test_global_role_in_rows_contributes_nothing(self):
        # A global role appearing in per-tenant rows is not a module required_role,
        # so it contributes no per-tenant capabilities — authority stays the
        # cognito:groups claim.
        for global_role in GLOBAL_ROLES:
            result = resolve_entitlement(
                user_roles_by_tenant={"ExampleTenant": [global_role]},
                active_modules_by_tenant={"ExampleTenant": ["FIN", "STR"]},
                module_registry=MODULE_REGISTRY,
            )
            assert result == {"ExampleTenant": []}, global_role

    def test_no_module_lists_a_global_role_as_required(self):
        # Guards the R1.4 assumption: none of the registry modules grant a global
        # role, so the per-tenant map can never surface global authority.
        for descriptor in MODULE_REGISTRY.values():
            required = set(descriptor.get("required_roles", []) or [])
            assert required.isdisjoint(GLOBAL_ROLES)


class TestPurityDeterminism:
    """R1.2 — resolving twice yields an identical map (idempotent, deterministic)."""

    def test_resolving_twice_is_identical(self):
        args = dict(
            user_roles_by_tenant={
                "TenantA": ["Finance_CRUD", "STR_Read"],
                "TenantB": ["STR_CRUD"],
            },
            active_modules_by_tenant={"TenantA": ["FIN", "STR"], "TenantB": ["STR"]},
            module_registry=MODULE_REGISTRY,
        )
        first = resolve_entitlement(**args)
        second = resolve_entitlement(**args)

        assert first == second

    def test_capabilities_are_sorted(self):
        result = resolve_entitlement(
            user_roles_by_tenant={"ExampleTenant": ["Finance_CRUD"]},
            active_modules_by_tenant={"ExampleTenant": ["FIN"]},
            module_registry=MODULE_REGISTRY,
        )
        caps = result["ExampleTenant"]
        assert caps == sorted(caps)


class TestWildcardRole:
    """A wildcard-permission role granted by an active module yields ['*']."""

    def test_wildcard_role_via_tenant_admin_is_not_wildcard(self):
        # Tenant_Admin is NOT a wildcard role; it has explicit caps. TENADMIN
        # module grants it. Confirms the non-wildcard path for an admin module.
        result = resolve_entitlement(
            user_roles_by_tenant={"ExampleTenant": ["Tenant_Admin"]},
            active_modules_by_tenant={"ExampleTenant": ["TENADMIN"]},
            module_registry=MODULE_REGISTRY,
        )
        assert result == {"ExampleTenant": caps_for("Tenant_Admin")}
        assert "*" not in result["ExampleTenant"]
