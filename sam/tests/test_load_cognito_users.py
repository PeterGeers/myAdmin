"""
S5c Task 6.4 — tests for the bulk **Cognito user load** runner (dry-run first, idempotent).

None of these touch a live Cognito pool or a live governance API (per the task constraints):

- **The pure parser** (``build_load_plan`` / ``_normalize_row``): reads the editable file
  READ-ONLY, validates each row (email/role/tenants/scope), renders the ``custom:tenants`` /
  ``custom:scope`` claim shapes, and collects malformed rows as errors instead of crashing.
- **The runner** (``scripts/aws/load-cognito-users.py``): dry-run creates NOTHING + calls no
  endpoint; ``--apply`` creates users via a FAKE cognito-idp client (in-memory) and assigns roles
  via a FAKE governance-endpoint client — and the test asserts the role went through the ENDPOINT
  SEAM, never a direct DB/projection write. Existing users are skipped (idempotent). Required args
  (``--pool-id`` / ``--source``) are enforced; there is no hardcoded pool/tenant.

HARD SEPARATION (R8.1/R8.2, C-PLAYBOOK): the script owns user creation + attributes; role
assignment is endpoint-driven. The fakes make that separation directly assertable.

Validates: Requirements R8.2, R8.3 (design C-PLAYBOOK — users by script, roles via the
governance endpoint; idempotent, dry-run, verify)
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys

import pytest

# repo root + backend/src on sys.path (mirrors the other sam runner tests).
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)
_BACKEND_SRC = os.path.join(_REPO_ROOT, "backend", "src")
if _BACKEND_SRC not in sys.path:
    sys.path.insert(0, _BACKEND_SRC)

FIXTURE = os.path.join(_REPO_ROOT, "sam", "tests", "fixtures", "cognito_users_sample.json")


def _load_runner_module():
    """Import the hyphen-named runner script by path (not a valid module name)."""
    path = os.path.join(_REPO_ROOT, "scripts", "aws", "load-cognito-users.py")
    spec = importlib.util.spec_from_file_location("load_cognito_users", path)
    module = importlib.util.module_from_spec(spec)
    # Register before exec so dataclass introspection (which resolves the module via
    # sys.modules[cls.__module__]) works for a spec-loaded, hyphen-named script.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


runner = _load_runner_module()


# ---------------------------------------------------------------------------
# In-memory fakes — no boto3, no HTTP, no live AWS / governance API
# ---------------------------------------------------------------------------


class _UserNotFound(Exception):
    pass


class _UsernameExists(Exception):
    pass


class _FakeExceptions:
    UserNotFoundException = _UserNotFound
    UsernameExistsException = _UsernameExists


class FakeCognitoBoto3Client:
    """An in-memory stand-in for the boto3 ``cognito-idp`` client.

    Records created users + their attributes + passwords so tests can assert what the SCRIPT
    (not the governance endpoint) wrote. ``admin_get_user`` raises ``UserNotFoundException`` for
    an absent user, mirroring the real client's exception seam.
    """

    def __init__(self, *, existing: set[str] | None = None):
        self.exceptions = _FakeExceptions()
        self.users: dict[str, dict] = {}
        self.passwords: dict[str, dict] = {}
        for email in existing or set():
            self.users[email] = {"pre-existing": True}

    def admin_get_user(self, *, UserPoolId, Username):  # noqa: N803 — boto3 kwarg names
        if Username not in self.users:
            raise self.exceptions.UserNotFoundException(Username)
        return {"Username": Username, "UserPoolId": UserPoolId}

    def admin_create_user(self, *, UserPoolId, Username, UserAttributes, MessageAction=None):  # noqa: N803
        if Username in self.users:
            raise self.exceptions.UsernameExistsException(Username)
        attrs = {a["Name"]: a["Value"] for a in UserAttributes}
        self.users[Username] = {"pool": UserPoolId, "attributes": attrs, "message": MessageAction}

    def admin_set_user_password(self, *, UserPoolId, Username, Password, Permanent):  # noqa: N803
        self.passwords[Username] = {"password": Password, "permanent": Permanent}


class RecordingGovernanceClient:
    """A fake governance-endpoint client that RECORDS assignments instead of POSTing.

    This is the seam that proves role assignment goes THROUGH THE ENDPOINT (never a direct DB
    write): every call to :meth:`assign_role` is captured as a ``(tenant, email, role)`` tuple.
    """

    def __init__(self):
        self.calls: list[tuple[str, str, str]] = []
        self.raise_for: set[str] = set()

    def assign_role(self, tenant: str, email: str, role: str) -> None:
        if email in self.raise_for:
            raise RuntimeError("simulated governance endpoint failure")
        self.calls.append((tenant, email, role))


def _cognito(existing=None):
    return runner.CognitoAdminClient(region="eu-west-1", client=FakeCognitoBoto3Client(existing=existing))


# ---------------------------------------------------------------------------
# The pure parser — build_load_plan / claim shapes / validation
# ---------------------------------------------------------------------------


class TestBuildLoadPlan:
    def test_parses_every_well_formed_row(self):
        plan = runner.build_load_plan(FIXTURE)
        assert plan.ok_count == 5
        assert plan.error_count == 0
        assert plan.default_tenant == "h-dcn-test"

    def test_counts_scoped_vs_general(self):
        plan = runner.build_load_plan(FIXTURE)
        assert plan.scoped_count == 2   # 601 (Noord), 602 (Zuid,Oost)
        assert plan.general_count == 3  # 701, 702, 801 (scope "all")

    def test_role_breakdown(self):
        plan = runner.build_load_plan(FIXTURE)
        assert plan.role_breakdown() == {"Members_Read": 2, "Members_CRUD": 3}

    def test_single_tenant_renders_as_scalar_claim(self):
        # A single tenant → scalar string (PreTokenGen reads a non-'['-prefixed value as ONE).
        plan = runner.build_load_plan(FIXTURE)
        by_email = {u.email: u for u in plan.users}
        assert by_email["member-scoped-601@example.com"].tenants_claim() == "h-dcn-test"

    def test_many_tenants_render_as_json_array_claim(self):
        plan = runner.build_load_plan(FIXTURE)
        by_email = {u.email: u for u in plan.users}
        claim = by_email["member-extra-801@example.com"].tenants_claim()
        assert json.loads(claim) == ["h-dcn-test", "other-club"]
        assert claim.startswith("[")  # array-shaped → read as MANY tenants

    def test_scope_claim_all_vs_subset(self):
        plan = runner.build_load_plan(FIXTURE)
        by_email = {u.email: u for u in plan.users}
        assert by_email["member-general-701@example.com"].scope_claim() == "*"
        assert json.loads(by_email["member-scoped-602@example.com"].scope_claim()) == ["Zuid", "Oost"]

    def test_cli_tenant_overrides_file_default(self, tmp_path):
        path = tmp_path / "u.json"
        path.write_text(json.dumps({"default_tenant": "file-club", "users": [
            {"email": "a@example.com", "role": "Members_Read", "scope": ["Noord"]}
        ]}), encoding="utf-8")
        plan = runner.build_load_plan(str(path), cli_default_tenant="cli-club")
        assert plan.users[0].tenants == ["cli-club"]

    def test_unknown_role_is_a_collected_error(self, tmp_path):
        path = tmp_path / "u.json"
        path.write_text(json.dumps({"default_tenant": "c", "users": [
            {"email": "a@example.com", "role": "Bogus_Role", "scope": "all"}
        ]}), encoding="utf-8")
        plan = runner.build_load_plan(str(path))
        assert plan.ok_count == 0 and plan.error_count == 1
        assert "unknown role" in plan.errors[0][1]

    def test_missing_email_is_a_collected_error(self, tmp_path):
        path = tmp_path / "u.json"
        path.write_text(json.dumps({"default_tenant": "c", "users": [
            {"role": "Members_Read", "scope": "all"}
        ]}), encoding="utf-8")
        plan = runner.build_load_plan(str(path))
        assert plan.error_count == 1 and "email" in plan.errors[0][1]

    def test_no_tenant_and_no_default_is_an_error(self, tmp_path):
        path = tmp_path / "u.json"
        path.write_text(json.dumps({"users": [
            {"email": "a@example.com", "role": "Members_Read", "scope": "all"}
        ]}), encoding="utf-8")
        plan = runner.build_load_plan(str(path))
        assert plan.error_count == 1 and "default tenant" in plan.errors[0][1]

    def test_empty_scope_list_is_an_error(self, tmp_path):
        path = tmp_path / "u.json"
        path.write_text(json.dumps({"default_tenant": "c", "users": [
            {"email": "a@example.com", "role": "Members_Read", "scope": []}
        ]}), encoding="utf-8")
        plan = runner.build_load_plan(str(path))
        assert plan.error_count == 1


# ---------------------------------------------------------------------------
# The runner — dry-run writes nothing / required args / no hardcoded pool
# ---------------------------------------------------------------------------


class TestRunnerDryRun:
    def test_dry_run_creates_nothing_and_calls_no_endpoint(self):
        cog = FakeCognitoBoto3Client()
        gov = RecordingGovernanceClient()
        rc = runner.load_users(
            FIXTURE, pool_id="eu-west-1_xyrlzfqbl", region="eu-west-1", apply=False,
            cognito=runner.CognitoAdminClient(region="eu-west-1", client=cog), governance=gov,
        )
        assert rc == 0
        assert cog.users == {}          # no user created
        assert gov.calls == []          # no endpoint call

    def test_dry_run_emits_a_plan(self, capsys):
        runner.load_users(FIXTURE, pool_id="eu-west-1_xyrlzfqbl", region="eu-west-1", apply=False)
        out = capsys.readouterr().out
        assert "Cognito bulk user load — plan" in out
        assert "DRY-RUN" in out
        assert "eu-west-1_xyrlzfqbl" in out              # resolved target pool
        assert "GOVERNANCE ENDPOINT" in out              # role path named
        assert "users in file     : 5" in out

    def test_apply_is_the_only_write_flag(self):
        args = runner.build_parser().parse_args(
            ["--pool-id", "eu-west-1_xyrlzfqbl", "--source", FIXTURE]
        )
        assert args.apply is False  # dry-run is the CLI default


class TestRunnerRequiresPoolAndSource:
    """--pool-id and --source are REQUIRED — no hardcoded pool/tenant (R8, steering 23)."""

    def test_missing_pool_is_rejected(self):
        with pytest.raises(SystemExit):
            runner.build_parser().parse_args(["--source", FIXTURE])

    def test_missing_source_is_rejected(self):
        with pytest.raises(SystemExit):
            runner.build_parser().parse_args(["--pool-id", "eu-west-1_xyrlzfqbl"])

    def test_apply_and_dry_run_are_mutually_exclusive(self):
        with pytest.raises(SystemExit):
            runner.build_parser().parse_args(
                ["--pool-id", "p", "--source", FIXTURE, "--apply", "--dry-run"]
            )

    def test_pool_alias_accepted(self):
        args = runner.build_parser().parse_args(["--pool", "eu-west-1_xyrlzfqbl", "--source", FIXTURE])
        assert args.pool_id == "eu-west-1_xyrlzfqbl"


# ---------------------------------------------------------------------------
# The runner — apply: users by script, roles via the endpoint, idempotent
# ---------------------------------------------------------------------------


class TestRunnerApply:
    def test_apply_creates_users_with_the_claim_attributes(self, capsys):
        cog = FakeCognitoBoto3Client()
        gov = RecordingGovernanceClient()
        rc = runner.load_users(
            FIXTURE, pool_id="POOL", region="eu-west-1", apply=True,
            cognito=runner.CognitoAdminClient(region="eu-west-1", client=cog), governance=gov,
        )
        assert rc == 0
        assert set(cog.users) == {
            "member-scoped-601@example.com", "member-scoped-602@example.com",
            "member-general-701@example.com", "member-general-702@example.com",
            "member-extra-801@example.com",
        }
        # custom:tenants scalar vs array shape landed on the created user.
        assert cog.users["member-scoped-601@example.com"]["attributes"]["custom:tenants"] == "h-dcn-test"
        assert cog.users["member-extra-801@example.com"]["attributes"]["custom:tenants"].startswith("[")
        # custom:scope: all → "*", subset → JSON array.
        assert cog.users["member-general-701@example.com"]["attributes"]["custom:scope"] == "*"
        assert json.loads(cog.users["member-scoped-602@example.com"]["attributes"]["custom:scope"]) == ["Zuid", "Oost"]
        # every created user got a permanent password set by the SCRIPT.
        assert all(p["permanent"] for p in cog.passwords.values())
        assert len(cog.passwords) == 5

    def test_apply_assigns_roles_only_through_the_endpoint_seam(self):
        cog = FakeCognitoBoto3Client()
        gov = RecordingGovernanceClient()
        runner.load_users(
            FIXTURE, pool_id="POOL", region="eu-west-1", apply=True,
            cognito=runner.CognitoAdminClient(region="eu-west-1", client=cog), governance=gov,
        )
        # Every role assignment is a recorded ENDPOINT call (never a direct DB/projection write).
        assigned = {(email, role) for _tenant, email, role in gov.calls}
        assert ("member-scoped-601@example.com", "Members_Read") in assigned
        assert ("member-general-701@example.com", "Members_CRUD") in assigned
        assert len(gov.calls) == 5
        # The endpoint is driven with the user's tenant (from custom:tenants[0]).
        tenants = {t for t, _e, _r in gov.calls}
        assert "h-dcn-test" in tenants

    def test_apply_is_idempotent_existing_users_skipped(self, capsys):
        # 601 + 701 already exist → created only the other 3; existing ones skipped, not recreated.
        cog = FakeCognitoBoto3Client(existing={
            "member-scoped-601@example.com", "member-general-701@example.com",
        })
        gov = RecordingGovernanceClient()
        rc = runner.load_users(
            FIXTURE, pool_id="POOL", region="eu-west-1", apply=True,
            cognito=runner.CognitoAdminClient(region="eu-west-1", client=cog), governance=gov,
        )
        assert rc == 0
        out = capsys.readouterr().out
        assert "created          : 3" in out
        assert "skipped existing : 2" in out
        # No password was reset for the pre-existing users.
        assert "member-scoped-601@example.com" not in cog.passwords

    def test_reapply_writes_nothing_new(self):
        cog = FakeCognitoBoto3Client()
        gov = RecordingGovernanceClient()
        client = runner.CognitoAdminClient(region="eu-west-1", client=cog)
        runner.load_users(FIXTURE, pool_id="POOL", region="eu-west-1", apply=True, cognito=client, governance=gov)
        created_after_first = dict(cog.users)
        # Second run over the SAME file — all users already present → all skipped.
        rc = runner.load_users(FIXTURE, pool_id="POOL", region="eu-west-1", apply=True, cognito=client, governance=gov)
        assert rc == 0
        assert cog.users == created_after_first  # nothing new created

    def test_apply_without_governance_creates_users_but_marks_role_skipped(self, capsys):
        # No governance client wired → users created + attributes set, role step skipped (for SPA).
        cog = FakeCognitoBoto3Client()
        rc = runner.load_users(
            FIXTURE, pool_id="POOL", region="eu-west-1", apply=True,
            cognito=runner.CognitoAdminClient(region="eu-west-1", client=cog), governance=None,
        )
        assert rc == 0
        assert len(cog.users) == 5             # users still created by the script
        out = capsys.readouterr().out
        assert "roles assigned   : 0" in out
        assert "roles skipped    : 5" in out   # endpoint not wired → left for the SPA

    def test_apply_refuses_a_file_with_malformed_rows(self, tmp_path):
        path = tmp_path / "bad.json"
        path.write_text(json.dumps({"default_tenant": "c", "users": [
            {"email": "ok@example.com", "role": "Members_Read", "scope": "all"},
            {"email": "bad@example.com", "role": "Nope", "scope": "all"},
        ]}), encoding="utf-8")
        cog = FakeCognitoBoto3Client()
        rc = runner.load_users(str(path), pool_id="POOL", region="eu-west-1", apply=True,
                               cognito=runner.CognitoAdminClient(region="eu-west-1", client=cog),
                               governance=RecordingGovernanceClient())
        assert rc == 2               # refused
        assert cog.users == {}       # nothing created from a partially-broken file

    def test_role_error_is_reported_not_fatal(self):
        cog = FakeCognitoBoto3Client()
        gov = RecordingGovernanceClient()
        gov.raise_for = {"member-general-702@example.com"}
        rc = runner.load_users(
            FIXTURE, pool_id="POOL", region="eu-west-1", apply=True,
            cognito=runner.CognitoAdminClient(region="eu-west-1", client=cog), governance=gov,
        )
        # Exit 3 = applied but with a reconcilable error; the user was still CREATED.
        assert rc == 3
        assert "member-general-702@example.com" in cog.users


class TestCliDefaultDryRun:
    def test_cli_main_default_is_dry_run(self, capsys):
        rc = runner.main(["--pool-id", "eu-west-1_xyrlzfqbl", "--source", FIXTURE])
        assert rc == 0
        assert "DRY-RUN" in capsys.readouterr().out
