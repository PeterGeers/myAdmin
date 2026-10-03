"""
Tests for the Test_Account provisioning script
(`scripts/test-environment/provision-test-account.py`) — test-environment spec Req 17.

Pin the script's contract + safety without touching real AWS: an in-memory fake
cognito-idp client records create/update/password calls, so the tests prove the
Req-17 behaviours directly:

- Creates the user in the test pool if absent (17.1); updates in place if present.
- Sets a PERMANENT password (Permanent=True) so there is NO forced-change trap
  (17.2) — the fake records the Permanent flag.
- Seeds custom:tenants / custom:role to the SPECIFIED shape, including a shape with
  no production counterpart (17.3); single vs multi tenant claim shape is honoured.
- Prod-mirror is a SEPARATE, explicit Copy_Utility step (17.4) — --mirror-prod only
  PRINTS the Copy_Utility command and reads nothing from prod here.
- Writes the TEST pool ONLY (17.5): a non-test pool is refused before any write.
- Dry-run is the default (writes nothing); --apply writes.

Validates: Requirements 17.1-17.6
"""

from __future__ import annotations

import importlib.util
import os
import sys

import pytest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)
_BACKEND_SRC = os.path.join(_REPO_ROOT, "backend", "src")
if _BACKEND_SRC not in sys.path:
    sys.path.insert(0, _BACKEND_SRC)


def _load_script_module():
    """Import the hyphen-named provisioning script by path (not a valid module name)."""
    path = os.path.join(_REPO_ROOT, "scripts", "test-environment", "provision-test-account.py")
    spec = importlib.util.spec_from_file_location("provision_test_account", path)
    module = importlib.util.module_from_spec(spec)
    # Register BEFORE exec so @dataclass (under `from __future__ import annotations`)
    # can resolve the module's own namespace during class processing.
    sys.modules["provision_test_account"] = module
    spec.loader.exec_module(module)
    return module


prov = _load_script_module()
TEST_POOL = prov.TEST_POOL_ID


# ---------------------------------------------------------------------------
# In-memory fake cognito-idp client
# ---------------------------------------------------------------------------


class _FakeUserNotFound(Exception):
    pass


class _FakeExceptions:
    UserNotFoundException = _FakeUserNotFound


class FakeCognito:
    """Records create/update/password calls against an in-memory user store."""

    exceptions = _FakeExceptions

    def __init__(self, existing: dict[str, dict] | None = None):
        self.users: dict[str, dict] = dict(existing or {})
        self.created: list[str] = []
        self.updated: list[str] = []
        self.password_calls: list[tuple[str, bool]] = []  # (email, permanent)

    def admin_get_user(self, UserPoolId=None, Username=None):
        if Username not in self.users:
            raise _FakeUserNotFound()
        return {"Username": Username}

    def admin_create_user(self, UserPoolId=None, Username=None, UserAttributes=None, **_):
        self.users[Username] = {a["Name"]: a["Value"] for a in (UserAttributes or [])}
        self.created.append(Username)

    def admin_update_user_attributes(self, UserPoolId=None, Username=None, UserAttributes=None, **_):
        self.users.setdefault(Username, {})
        self.users[Username].update({a["Name"]: a["Value"] for a in (UserAttributes or [])})
        self.updated.append(Username)

    def admin_set_user_password(self, UserPoolId=None, Username=None, Password=None, Permanent=None):
        self.password_calls.append((Username, bool(Permanent)))


def _client(existing=None):
    fake = FakeCognito(existing=existing)
    return prov.CognitoAdminClient(region="eu-west-1", pool_id=TEST_POOL, client=fake), fake


# ---------------------------------------------------------------------------
# Account shape rendering
# ---------------------------------------------------------------------------


class TestAccountShape:
    def test_single_tenant_is_scalar_claim(self):
        shape = prov.build_account_shape("t@example.org", ["TenantA"], "Admin")
        assert shape.tenants_claim() == "TenantA"

    def test_multi_tenant_is_json_array_claim(self):
        shape = prov.build_account_shape("t@example.org", ["A", "B"], "Member")
        assert shape.tenants_claim() == '["A", "B"]'

    def test_shape_may_be_a_non_production_configuration(self):
        # Req 17.3: any valid shape, including one with no prod counterpart.
        shape = prov.build_account_shape("t@example.org", ["Imaginary-Tenant"], "MadeUpRole")
        attrs = {a["Name"]: a["Value"] for a in shape.cognito_attributes()}
        assert attrs["custom:tenants"] == "Imaginary-Tenant"
        assert attrs["custom:role"] == "MadeUpRole"

    @pytest.mark.parametrize("bad_email", ["", "   ", "not-an-email"])
    def test_invalid_email_rejected(self, bad_email):
        with pytest.raises(prov.ProvisioningError):
            prov.build_account_shape(bad_email, ["A"], "Admin")

    def test_empty_tenants_rejected(self):
        with pytest.raises(prov.ProvisioningError):
            prov.build_account_shape("t@example.org", [], "Admin")

    def test_empty_role_rejected(self):
        with pytest.raises(prov.ProvisioningError):
            prov.build_account_shape("t@example.org", ["A"], "")


# ---------------------------------------------------------------------------
# Create-if-absent + permanent password (no forced-change trap)
# ---------------------------------------------------------------------------


class TestProvision:
    def test_dry_run_writes_nothing(self):
        client, fake = _client()
        shape = prov.build_account_shape("t@example.org", ["A"], "Admin")
        result = prov.provision_test_account(shape, region="eu-west-1", apply=False, client=client)
        assert result.applied is False
        assert fake.created == [] and fake.updated == [] and fake.password_calls == []

    def test_apply_creates_absent_user_and_sets_permanent_password(self):
        client, fake = _client()
        shape = prov.build_account_shape("new@example.org", ["A"], "Admin")
        result = prov.provision_test_account(
            shape, region="eu-west-1", apply=True, password="Pw!12345", client=client
        )
        assert result.created is True and result.applied is True
        assert fake.created == ["new@example.org"]
        # Permanent password set → clears the forced-change trap (Req 17.2).
        assert fake.password_calls == [("new@example.org", True)]
        assert fake.users["new@example.org"]["custom:tenants"] == "A"
        assert fake.users["new@example.org"]["custom:role"] == "Admin"

    def test_apply_updates_existing_user_in_place(self):
        client, fake = _client(existing={"ex@example.org": {"custom:role": "Old"}})
        shape = prov.build_account_shape("ex@example.org", ["A", "B"], "NewRole")
        result = prov.provision_test_account(
            shape, region="eu-west-1", apply=True, password="Pw!12345", client=client
        )
        assert result.created is False
        assert fake.created == [] and fake.updated == ["ex@example.org"]
        assert fake.users["ex@example.org"]["custom:role"] == "NewRole"
        assert fake.password_calls == [("ex@example.org", True)]

    def test_generated_password_when_none_supplied(self):
        client, fake = _client()
        shape = prov.build_account_shape("gen@example.org", ["A"], "Admin")
        result = prov.provision_test_account(
            shape, region="eu-west-1", apply=True, password=None, client=client
        )
        assert result.generated_password is not None
        assert fake.password_calls == [("gen@example.org", True)]


# ---------------------------------------------------------------------------
# TEST-pool-only guard (Req 17.5)
# ---------------------------------------------------------------------------


class TestPoolGuard:
    def test_non_test_pool_is_refused(self):
        with pytest.raises(prov.NotTestPoolError):
            prov.CognitoAdminClient(
                region="eu-west-1", pool_id="eu-west-1_Hdp40eWmu", client=FakeCognito()
            )

    def test_test_pool_is_accepted(self):
        c = prov.CognitoAdminClient(region="eu-west-1", pool_id=TEST_POOL, client=FakeCognito())
        assert c is not None


# ---------------------------------------------------------------------------
# Prod-mirror is a separate, explicit Copy_Utility step (Req 17.4)
# ---------------------------------------------------------------------------


class TestMirrorProd:
    def test_mirror_prod_only_prints_copy_utility_command(self, capsys):
        rc = prov.main(["--email", "t@example.org", "--mirror-prod", "ref@example.org"])
        out = capsys.readouterr().out
        assert rc == 0
        # It points at the Copy_Utility (never reads prod itself here).
        assert "copy-prod-to-test.py cognito" in out
        assert "--i-understand-this-writes-test" in out
        assert "ref@example.org" in out


# ---------------------------------------------------------------------------
# CLI exit codes
# ---------------------------------------------------------------------------


class TestCli:
    def test_dry_run_is_the_default(self, monkeypatch):
        # Inject a fake so even if it tried to write, no real AWS is touched.
        fake = FakeCognito()
        monkeypatch.setattr(
            prov.CognitoAdminClient,
            "__init__",
            lambda self, *, region, pool_id, client=None: setattr(self, "_client", fake)
            or setattr(self, "_pool_id", pool_id),
        )
        rc = prov.main(["--email", "t@example.org", "--tenants", "A", "--role", "Admin"])
        assert rc == 0
        assert fake.created == [] and fake.password_calls == []

    def test_missing_tenants_without_mirror_is_invalid(self):
        rc = prov.main(["--email", "t@example.org", "--role", "Admin"])
        assert rc == 2  # ProvisioningError → exit 2
