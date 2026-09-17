"""
S4 D2 / T11 — unit tests for the PreTokenGen governance seam.

Covers the read-only reader (R2.2) and a sample of the fail-fast config resolver
(R2.5) that T11 puts in place for T12/T13 to build on. The reader is exercised
with a fake DB (no live MySQL); the config resolver is driven with injected env
maps (no process-env mutation).
"""

import os
import sys

import pytest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from sam.pretokengen.governance_reader import (
    GovernanceConfigError,
    GovernanceReader,
    resolve_db_config,
)


class FakeDb:
    def __init__(self, rows_by_table):
        self._rows_by_table = rows_by_table
        self.calls = []

    def execute_query(self, query, params=None, fetch=True, commit=False, **kwargs):
        self.calls.append({"query": query, "params": params, "fetch": fetch, "commit": commit})
        normalized = " ".join(query.split()).lower()
        if "from user_tenant_roles" in normalized:
            return list(self._rows_by_table.get("user_tenant_roles", []))
        if "from tenant_modules" in normalized:
            tenants = set(params or ())
            return [
                r
                for r in self._rows_by_table.get("tenant_modules", [])
                if r["administration"] in tenants
            ]
        raise AssertionError(f"Unexpected query: {query}")


_FULL_ENV = {
    "ENTITLEMENT_DB_HOST": "governance-db.internal",
    "ENTITLEMENT_DB_PORT": "3306",
    "ENTITLEMENT_DB_USER": "entitlement_ro",
    "ENTITLEMENT_DB_PASSWORD": "secret",
    "ENTITLEMENT_DB_NAME": "finance",
}


class TestResolveDbConfig:
    def test_resolves_all_explicit_vars(self):
        cfg = resolve_db_config(_FULL_ENV)
        assert cfg.host == "governance-db.internal"
        assert cfg.port == 3306
        assert cfg.user == "entitlement_ro"
        assert cfg.database == "finance"

    @pytest.mark.parametrize("missing", sorted(_FULL_ENV.keys()))
    def test_missing_var_fails_fast(self, missing):
        env = {k: v for k, v in _FULL_ENV.items() if k != missing}
        with pytest.raises(GovernanceConfigError):
            resolve_db_config(env)

    def test_blank_var_fails_fast(self):
        env = dict(_FULL_ENV, ENTITLEMENT_DB_HOST="   ")
        with pytest.raises(GovernanceConfigError):
            resolve_db_config(env)

    def test_non_integer_port_fails_fast(self):
        env = dict(_FULL_ENV, ENTITLEMENT_DB_PORT="notaport")
        with pytest.raises(GovernanceConfigError):
            resolve_db_config(env)

    def test_does_not_fall_back_to_localhost(self):
        # No ambient default: an empty env raises rather than resolving localhost.
        with pytest.raises(GovernanceConfigError):
            resolve_db_config({})


class TestGovernanceReader:
    def test_user_roles_grouped_by_tenant(self):
        db = FakeDb(
            {
                "user_tenant_roles": [
                    {"administration": "TenantA", "role": "Finance_CRUD"},
                    {"administration": "TenantA", "role": "STR_Read"},
                    {"administration": "TenantB", "role": "Tenant_Admin"},
                ]
            }
        )
        reader = GovernanceReader(db)
        result = reader.get_user_roles_by_tenant("user@example.com")
        assert result == {
            "TenantA": ["Finance_CRUD", "STR_Read"],
            "TenantB": ["Tenant_Admin"],
        }
        # read-only + parameterized on email
        assert db.calls[0]["fetch"] is True
        assert db.calls[0]["commit"] is False
        assert db.calls[0]["params"] == ("user@example.com",)

    def test_active_modules_filtered_to_given_tenants(self):
        db = FakeDb(
            {
                "tenant_modules": [
                    {"administration": "TenantA", "module_name": "FIN"},
                    {"administration": "TenantB", "module_name": "STR"},
                ]
            }
        )
        reader = GovernanceReader(db)
        result = reader.get_active_modules_by_tenant(["TenantA"])
        assert result == {"TenantA": ["FIN"]}
        assert db.calls[0]["commit"] is False

    def test_empty_tenants_does_not_touch_db(self):
        db = FakeDb({})
        reader = GovernanceReader(db)
        assert reader.get_active_modules_by_tenant([]) == {}
        assert db.calls == []
