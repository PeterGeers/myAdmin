"""
S4 T3 — INCREMENTAL resolver edge cases (fills the gaps T1 did not cover).

Scope discipline (avoid duplication)
------------------------------------
T1 (``test_entitlement_resolver.py``, 16 tests) already covers the bulk of the
T3 test matrix — full-access user, read-only user, role-for-inactive-module
excluded, tenant-with-no-active-modules empty, multi-tenant independence,
duplicate roles, empty input, global-roles-not-re-derived, and single-tenant
sorted/purity. T2 (``test_entitlement_resolver_flask_equivalence.py``, 9 tests)
proves resolver ≡ Flask decision.

This file adds ONLY the T3-listed cases that were genuinely NOT asserted by T1:

1. **Unicode "emails"** — an honest treatment. The resolver signature
   (``resolve_entitlement(user_roles_by_tenant, active_modules_by_tenant,
   module_registry)``) is purely per-tenant: it takes NO email/user-identity
   argument, so an email value can never change its output. The relevant place
   unicode CAN appear on this pure boundary is the **tenant key** (the
   ``administration`` string the Lambda groups the user's rows by) and the role
   strings. These tests prove non-ASCII / unicode tenant keys and role strings
   are carried and matched cleanly (no crash, no mojibake, correct keying), and
   pin the fact that user identity is not an input to the resolver.
2. **Multi-tenant with one tenant ABSENT from the active-modules map** — T1
   pins the single-tenant "absent tenant → empty" case; this pins that the
   absence of one tenant does not perturb the tenants that DO resolve.
3. **Capability-ordering stability for a LARGER multi-tenant user** (the
   size-budget / ``s4test-multi`` fixture shape) — T1's sorted check is
   single-tenant; this pins deterministic sorted ordering across every tenant
   of a realistic multi-tenant admin, which the T4/T5 codec relies on.

Covers R1.1 (roles ∩ active modules → capabilities). The resolver is pure, so
these tests pass plain dict/list structures and the real ``MODULE_REGISTRY`` /
``ROLE_PERMISSIONS`` maps — no DB, no mocks needed (testing-standards: no
mysql.connector import, no real DB access, no os.environ DB reads).

Reference: .kiro/specs/multi-tenant/s4-token-entitlement-projection/
  requirements.md R1.1; tasks.md T3.
"""

import os
import sys

import pytest

sys.path.append(os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from auth.cognito_utils import ROLE_PERMISSIONS
from auth.entitlement_resolver import resolve_entitlement
from services.module_registry import MODULE_REGISTRY


def caps_for(*roles):
    """Expected sorted capabilities for a set of roles (wildcard short-circuits).

    Derived from the SAME ``ROLE_PERMISSIONS`` map the resolver reads, so the
    assertions test the composition rather than a hand-copied constant.
    """
    acc = set()
    for role in roles:
        perms = ROLE_PERMISSIONS.get(role, [])
        if "*" in perms:
            return ["*"]
        acc.update(perms)
    return sorted(acc)


class TestUnicodeTenantKeys:
    """R1.1 — unicode/non-ASCII tenant keys and role strings resolve cleanly.

    The resolver takes no email/user argument, so 'unicode emails' is only
    meaningful on this pure boundary as the unicode *tenant key* (and role)
    that the Lambda will pass after grouping ``user_tenant_roles`` rows. These
    tests prove such keys pass through without crashing, corruption, or
    mis-keying.
    """

    def test_unicode_tenant_key_resolves_and_is_preserved_exactly(self):
        # A tenant whose administration name contains non-ASCII characters.
        tenant = "Café-Müller-会社"
        result = resolve_entitlement(
            user_roles_by_tenant={tenant: ["Finance_Read"]},
            active_modules_by_tenant={tenant: ["FIN"]},
            module_registry=MODULE_REGISTRY,
        )

        # The exact unicode key round-trips (no normalisation / mangling) and
        # resolves to the correct capability set.
        assert list(result.keys()) == [tenant]
        assert result[tenant] == caps_for("Finance_Read")

    def test_emoji_and_rtl_tenant_keys_kept_distinct(self):
        # Distinct unicode keys (emoji, right-to-left script) must not collide.
        t_emoji = "tenant-🏢"
        t_rtl = "شركة"
        result = resolve_entitlement(
            user_roles_by_tenant={
                t_emoji: ["Finance_CRUD"],
                t_rtl: ["STR_Read"],
            },
            active_modules_by_tenant={
                t_emoji: ["FIN"],
                t_rtl: ["STR"],
            },
            module_registry=MODULE_REGISTRY,
        )

        assert set(result.keys()) == {t_emoji, t_rtl}
        assert result[t_emoji] == caps_for("Finance_CRUD")
        assert result[t_rtl] == caps_for("STR_Read")

    def test_unicode_role_string_that_matches_no_module_contributes_nothing(self):
        # A stray unicode role name is simply not a required_role of any module,
        # so it is dropped by the module gate (no crash, no partial grant).
        tenant = "Åström"
        result = resolve_entitlement(
            user_roles_by_tenant={tenant: ["Fïnance_Rëad", "Finance_Read"]},
            active_modules_by_tenant={tenant: ["FIN"]},
            module_registry=MODULE_REGISTRY,
        )

        # Only the real Finance_Read role survives; the unicode look-alike does not.
        assert result == {tenant: caps_for("Finance_Read")}

    def test_resolver_output_independent_of_any_email_identity(self):
        # Documents/pins that email is NOT a resolver input: the same per-tenant
        # rows always produce the same map regardless of which user they belong
        # to. (There is no email parameter to pass — this asserts the contract.)
        rows = {"TenantEmail": ["Finance_Read"]}
        active = {"TenantEmail": ["FIN"]}

        first = resolve_entitlement(rows, active, MODULE_REGISTRY)
        second = resolve_entitlement(rows, active, MODULE_REGISTRY)

        assert first == second == {"TenantEmail": caps_for("Finance_Read")}
        # The signature has exactly three parameters; identity is not among them.
        import inspect

        params = list(inspect.signature(resolve_entitlement).parameters)
        assert params == [
            "user_roles_by_tenant",
            "active_modules_by_tenant",
            "module_registry",
        ]


class TestMultiTenantTenantAbsentFromActiveModules:
    """R1.1 — one tenant absent from the active-modules map doesn't perturb others.

    T1 pins the single-tenant "tenant absent from active-modules map → empty"
    case. This pins that, in a multi-tenant user, the absent tenant resolves to
    empty while the OTHER tenants still resolve correctly (per-tenant isolation
    of the missing-key path).
    """

    def test_absent_tenant_is_empty_others_unaffected(self):
        result = resolve_entitlement(
            user_roles_by_tenant={
                "TenantWithModules": ["Finance_CRUD"],
                "TenantMissingFromModulesMap": ["Finance_CRUD"],
                "TenantWithStr": ["STR_Read"],
            },
            active_modules_by_tenant={
                "TenantWithModules": ["FIN"],
                # "TenantMissingFromModulesMap" deliberately absent.
                "TenantWithStr": ["STR"],
            },
            module_registry=MODULE_REGISTRY,
        )

        assert result["TenantWithModules"] == caps_for("Finance_CRUD")
        assert result["TenantMissingFromModulesMap"] == []  # absent -> empty
        assert result["TenantWithStr"] == caps_for("STR_Read")
        # The tenant key is still present so the caller sees the user belongs there.
        assert set(result.keys()) == {
            "TenantWithModules",
            "TenantMissingFromModulesMap",
            "TenantWithStr",
        }


class TestLargeMultiTenantOrderingStability:
    """R1.1 — deterministic sorted ordering across every tenant of a large user.

    Mirrors the ``s4test-multi`` size-budget fixture shape (a realistic
    multi-tenant admin). T1 asserts sorted order for a single tenant; the T4/T5
    codec relies on stable ordering for EVERY tenant so the encoded claim is
    deterministic. This pins that guarantee at scale.
    """

    def _large_user(self):
        return dict(
            user_roles_by_tenant={
                "TenantAlpha": ["Finance_CRUD", "STR_CRUD"],
                "TenantBeta": ["Finance_Read", "STR_Read"],
                "TenantGamma": ["Tenant_Admin"],
                "TenantDelta": ["Finance_Export", "STR_Export"],
                "TenantEpsilon": ["Finance_CRUD"],
            },
            active_modules_by_tenant={
                "TenantAlpha": ["FIN", "STR"],
                "TenantBeta": ["FIN", "STR"],
                "TenantGamma": ["TENADMIN"],
                "TenantDelta": ["FIN", "STR"],
                "TenantEpsilon": ["FIN"],
            },
            module_registry=MODULE_REGISTRY,
        )

    def test_every_tenant_capability_list_is_sorted(self):
        result = resolve_entitlement(**self._large_user())

        assert set(result.keys()) == {
            "TenantAlpha",
            "TenantBeta",
            "TenantGamma",
            "TenantDelta",
            "TenantEpsilon",
        }
        for tenant, caps in result.items():
            assert caps == sorted(caps), f"{tenant} capabilities not sorted: {caps}"

    def test_large_user_resolution_is_deterministic(self):
        first = resolve_entitlement(**self._large_user())
        second = resolve_entitlement(**self._large_user())

        assert first == second

    def test_large_user_expected_capabilities_per_tenant(self):
        result = resolve_entitlement(**self._large_user())

        assert result["TenantAlpha"] == caps_for("Finance_CRUD", "STR_CRUD")
        assert result["TenantBeta"] == caps_for("Finance_Read", "STR_Read")
        assert result["TenantGamma"] == caps_for("Tenant_Admin")
        assert result["TenantDelta"] == caps_for("Finance_Export", "STR_Export")
        assert result["TenantEpsilon"] == caps_for("Finance_CRUD")
