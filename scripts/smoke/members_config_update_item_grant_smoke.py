#!/usr/bin/env python3
"""members_config_update_item_grant_smoke.py — deployed-stage IAM-grant smoke test.

Spec 03 (`config-fields-foolproof-crud`) task **8.6** — the deployed-stage counterpart
to the local E2E invariant suite (`sam/tests/e2e/`, design **C5**). It closes **harness
gap (i)** that the external design review flagged (design.md C5 "Harness gaps", R9 / R11):

    local DynamoDB (steering 42 / `amazon/dynamodb-local`) does NOT enforce IAM. So the
    `dynamodb:UpdateItem` grant added to the Members Lambda execution role in task 2.1
    (`template.yaml` Sid ``MembersWriteGovernanceProjectionConfig``) passes the whole E2E
    suite REGARDLESS of whether the grant is present — the emulator never checks. A
    missing or mis-scoped grant would only surface as ``AccessDeniedException`` in REAL
    AWS, at runtime, on the first Change-Op write. This smoke test exercises that grant
    against the deployed TEST stack so it is actually proven, not assumed.

────────────────────────────────────────────────────────────────────────────────────────
WHY THIS SPECIFIC APPROACH (assume the Lambda role, then update_item)
────────────────────────────────────────────────────────────────────────────────────────
The thing under test is **the Members Lambda execution role's** ``dynamodb:UpdateItem``
grant — NOT the deploy role's permissions, NOT the API's auth. Three approaches were
weighed:

  (a) Call ``update_item`` directly with the ambient NonprofitDeployRole credentials.
      REJECTED — NonprofitDeployRole has broad deploy permissions, so the write would
      succeed whether or not the Lambda role grant exists. This proves nothing about the
      grant under test. (The task brief explicitly forbids this.)

  (b) Invoke the deployed ``PUT /members/config/fields`` Change-Op route end-to-end over
      HTTPS. This DOES run as the Lambda role, but it requires a valid Cognito access
      token for the TEST pool (`eu-west-1_xyrlzfqbl`) with an admin entitlement. Minting
      that unattended (no client secret, SRP/USER_PASSWORD flow + a seeded admin user)
      is brittle and drags Cognito into a DynamoDB-IAM smoke test. A 200 would also not
      cleanly ISOLATE the grant as the thing proven (many other things must also line up).

  (c) **CHOSEN:** discover the deployed ``members-test`` Lambda's execution-role ARN from
      its live configuration, ``sts:AssumeRole`` INTO that exact role, and issue the real
      Change-Op-shaped ``update_item`` under those temporary credentials. This reproduces
      *exactly* the principal the Lambda runs as, so the ONLY thing that lets the write
      succeed is the ``MembersWriteGovernanceProjectionConfig`` grant. If task 2.1 had not
      added ``dynamodb:UpdateItem``, this call returns ``AccessDeniedException`` and the
      smoke test FAILS — which is the whole point. It needs no Cognito token and isolates
      the grant precisely.

Approach (c) requires the operator's principal (NonprofitDeployRole) to be allowed to
assume the Lambda role (the role's trust policy must list it, or the operator uses an
admin principal). If assume-role is not permitted in your context, re-run with
``--approach=caller-identity-check`` which still FAILS CLOSED: it verifies the deployed
role's *attached policy* actually contains ``dynamodb:UpdateItem`` on the governance
table via ``iam:SimulatePrincipalPolicy`` (a read-only check, no write) — a weaker but
non-destructive fallback that still catches a missing grant. The default is (c).

────────────────────────────────────────────────────────────────────────────────────────
WHAT THE WRITE ACTUALLY TOUCHES (non-destructive / self-reverting)
────────────────────────────────────────────────────────────────────────────────────────
The grant (Sid ``MembersWriteGovernanceProjectionConfig``) is scoped to the WHOLE
``governance_projection`` table ARN, so ANY ``update_item`` on that table under the Lambda
role exercises the exact grant. To keep the write 100% isolated from real tenant data, it
targets a DEDICATED sentinel item:

    tenant_id = "__smoketest__"        (partition key — not a real tenant)
    sk        = "config#__smoketest__" (sort key — not "config#fields")

It performs the SAME mechanics the Change-Op write repo
(``sam/members/repository/projection_config_write_repository.py::apply_ops``) performs: a
single path ``update_item`` with a combined ``SET`` + a version-conditional
``ConditionExpression`` (the three-case version guard, design D5). It then asserts:

  1. the write SUCCEEDED (the grant is present — a missing grant raises AccessDenied); and
  2. an ISOLATION property (the invariant idea, reused): a REAL ``config#fields`` row read
     before and after the write is BYTE-IDENTICAL — a Change-Op touches only its target.
     (The sentinel write cannot touch a real row; this check proves the harness is
     exercising the real table and would catch a catastrophically-wrong write path.)

Finally it REMOVES the sentinel item it created (``delete_item``), so the test is
self-reverting and idempotent — safe to re-run any number of times. If a previous run was
interrupted, the first step cleans up any stale sentinel before writing.

────────────────────────────────────────────────────────────────────────────────────────
RUNBOOK — the operator runs this AFTER a TEST deploy (NOT part of this prepare-only task)
────────────────────────────────────────────────────────────────────────────────────────
1. DEPLOY the new stack to TEST first (this smoke test must run against the NEW Change-Op
   path, not the old whole-record stack). Either:
       * push the ``test`` branch (steering 43 fires ``deploy-sam-members.yml`` via OIDC); or
       * manual:  sam deploy --config-env test   (from ``sam/members/``)
   The deployed TEST stack was last updated 2026-10-23 (BEFORE this spec), so a deploy is
   mandatory — ``--require-fresh-deploy`` (default on) refuses to run if the deployed
   function's ``LastModified`` predates a date you pass, as a guard against testing stale
   code. See ``--help``.

2. Sanity-check identity (the script also does this and FAILS FAST, steering 41 override-
   ranking trap):

       env -u AWS_ACCESS_KEY_ID -u AWS_SECRET_ACCESS_KEY -u AWS_SESSION_TOKEN \
         aws sts get-caller-identity --profile nonprofit-deploy --region eu-west-1 --output json
       # MUST print Account 506221081911 / NonprofitDeployRole.

3. RUN the smoke test (from the repo root, WSL). Strip any lingering static keys +
   endpoint override (steering 41) so the profile resolves the DATA account and the client
   talks to REAL AWS (never the local emulator):

       env -u AWS_ENDPOINT_URL_DYNAMODB -u AWS_ACCESS_KEY_ID -u AWS_SECRET_ACCESS_KEY -u AWS_SESSION_TOKEN \
         AWS_REGION=eu-west-1 AWS_PROFILE=nonprofit-deploy \
         backend/.venv/bin/python scripts/smoke/members_config_update_item_grant_smoke.py

   Options:
       --stack-name NAME   deployed CFN stack (default: test-sam-members, steering 43)
       --function-name N   deployed Lambda   (default: members-test)
       --table NAME        governance table  (default: test_governance_projection)
       --approach {assume-role,caller-identity-check}   (default: assume-role — see above)
       --require-fresh-deploy / --no-require-fresh-deploy  (default: on)
       --deployed-after YYYY-MM-DD   fail if the Lambda LastModified is before this
                                     (default: 2026-10-24 — the day after the old stack)

4. WHAT SUCCESS LOOKS LIKE — exit code 0 and a final line:

       SMOKE PASS: Members Lambda role 'members-...' holds dynamodb:UpdateItem on
       'test_governance_projection' (grant exercised by a real Change-Op update_item;
       isolation invariant held; sentinel cleaned up).

   FAILURE (exit 1) prints the reason. The signal that task 2.1's grant is MISSING is an
   ``AccessDeniedException`` on the update_item under the assumed Lambda role — the exact
   failure that local DynamoDB can never produce, which is why this test exists.

SAFETY: this script NEVER touches PROD (it refuses any table without the ``test_`` prefix
unless ``--i-understand-this-targets-prod`` is given) and NEVER touches a real tenant row
(it writes only the ``__smoketest__`` sentinel partition). It is read-mostly: one sentinel
write + its own cleanup. No real tenant data is created, modified, or deleted.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import os
import sys

# Bootstrap: find the repo root by walking up to a marker, then hand off to the shared
# onboarding `_lib` for repo-root + backend/src setup (scripts/onboarding/README.md
# "Robust paths (R4)"), matching scripts/test-environment/copy-prod-to-test.py.
_r = os.path.abspath(__file__)
while _r != os.path.dirname(_r):
    _r = os.path.dirname(_r)
    if os.path.isdir(os.path.join(_r, ".git")) or os.path.isdir(os.path.join(_r, ".kiro")):
        break
if _r not in sys.path:
    sys.path.insert(0, _r)
from scripts.onboarding._lib.paths import ensure_backend_src_on_path

ensure_backend_src_on_path()

# ---------------------------------------------------------------------------
# Verified environment facts (steering 23 / 41 / 43; samconfig.toml [test]).
# ---------------------------------------------------------------------------
#: DATA account that owns the governance_projection table + the Lambda role (steering 23).
EXPECTED_ACCOUNT_ID = "506221081911"
#: The role name the identity check expects to see in the caller ARN (steering 41).
EXPECTED_ROLE_NAME = "NonprofitDeployRole"
DEFAULT_REGION = "eu-west-1"

#: Deployed TEST stack / Lambda / table (samconfig.toml [test]; steering 43). The CFN
#: stack name is hyphenated; the table keeps the underscore prefix.
DEFAULT_STACK_NAME = "test-sam-members"
DEFAULT_FUNCTION_NAME = "members-test"
DEFAULT_TABLE_NAME = "test_governance_projection"

#: The TEST table boundary — defense in depth so the smoke test cannot hit PROD.
TEST_TABLE_PREFIX = "test_"

#: The sentinel item the write targets — a non-tenant partition + a non-"fields" sort key,
#: so the exercised update_item can never touch real tenant config data.
SENTINEL_TENANT_ID = "__smoketest__"
SENTINEL_CONFIG_ID = "__smoketest__"

#: Guard default: the old TEST stack was last updated 2026-10-23 (before this spec), so a
#: fresh deploy must be newer than the day after.
DEFAULT_DEPLOYED_AFTER = "2026-10-24"

#: The session name used when assuming the Lambda role (shows up in CloudTrail).
ASSUME_SESSION_NAME = "members-config-update-item-grant-smoke"


class SmokeError(RuntimeError):
    """A smoke-test precondition or assertion failed (fail closed)."""


class NotTestTargetError(SmokeError):
    """The target table is not demonstrably TEST and the prod override was not given."""


# ---------------------------------------------------------------------------
# PURE helpers (no AWS, no boto3) — unit-tested locally by
# sam/tests/test_members_config_update_item_grant_smoke.py
# ---------------------------------------------------------------------------


def build_sentinel_sort_key(config_id: str = SENTINEL_CONFIG_ID) -> str:
    """The sentinel sort key, built the SAME way the schema builds a config SK.

    Mirrors ``projection_schema.build_sort_key(RECORD_TYPE_CONFIG, <id>)`` ->
    ``"config#<id>"`` (record type ``config`` + separator ``#``) so the write exercises a
    realistic ``config#*`` key shape — but with the ``__smoketest__`` id, never ``fields``.
    """
    # Kept inline (not importing the schema) so the script stays runnable as a standalone
    # CLI; the values are asserted against the real schema in the paired unit test.
    return f"config#{config_id}"


def assert_test_target(table_name: str, *, allow_prod: bool) -> None:
    """Refuse a non-``test_`` table unless the explicit prod override was given.

    Defense in depth (mirrors copy-prod-to-test.py's destination guard): even a mistyped
    ``--table`` cannot make the smoke test write a PROD table by accident.
    """
    if table_name.startswith(TEST_TABLE_PREFIX):
        return
    if allow_prod:
        return
    raise NotTestTargetError(
        f"target table {table_name!r} does not start with {TEST_TABLE_PREFIX!r}; this "
        "smoke test targets the TEST stack only. Pass --i-understand-this-targets-prod to "
        "override (not recommended — the deployed-stage grant is identical on both envs)."
    )


def assert_expected_identity(caller_arn: str, account_id: str) -> None:
    """Fail closed unless the caller is the DATA account's NonprofitDeployRole.

    Catches the steering-41 override-ranking trap where lingering static keys silently run
    against the PERSONAL account (344561557829) — which would surface as
    ``ResourceNotFoundException`` on a table that only exists in nonprofit-deploy.
    """
    if account_id != EXPECTED_ACCOUNT_ID:
        raise SmokeError(
            f"caller account is {account_id!r}, expected {EXPECTED_ACCOUNT_ID!r} "
            f"(the DATA account). Likely the override-ranking trap (steering 41): strip "
            f"AWS_ACCESS_KEY_ID/SECRET/SESSION and use AWS_PROFILE=nonprofit-deploy. "
            f"Caller ARN: {caller_arn}"
        )
    if EXPECTED_ROLE_NAME not in caller_arn:
        raise SmokeError(
            f"caller ARN {caller_arn!r} does not carry {EXPECTED_ROLE_NAME!r}; identity "
            "must resolve to the NonprofitDeployRole (steering 23/41)."
        )


def parse_deployed_after(value: str) -> _dt.datetime:
    """Parse a ``YYYY-MM-DD`` cutoff into a UTC-aware datetime (fail loud on bad input)."""
    try:
        # A date-only value has no offset; we immediately pin it to UTC on the next line,
        # so the intermediate naive datetime is intentional (DTZ007 suppressed with reason).
        d = _dt.datetime.strptime(value, "%Y-%m-%d")  # noqa: DTZ007
    except ValueError as exc:
        raise SmokeError(f"--deployed-after {value!r} is not YYYY-MM-DD") from exc
    return d.replace(tzinfo=_dt.timezone.utc)


def assert_fresh_deploy(last_modified: _dt.datetime, cutoff: _dt.datetime) -> None:
    """Refuse to run against a Lambda whose code predates the spec's deploy cutoff.

    ``last_modified`` is the deployed function's LastModified (UTC-aware). A stale deploy
    means we'd be "proving" the grant on the OLD whole-record stack, not the new Change-Op
    path — so fail fast and tell the operator to deploy first.
    """
    if last_modified < cutoff:
        raise SmokeError(
            f"deployed Lambda LastModified {last_modified.isoformat()} is before the "
            f"fresh-deploy cutoff {cutoff.date().isoformat()}. Deploy the new stack to TEST "
            "first (sam deploy --config-env test, or push the test branch — steering 43), "
            "then re-run. Override with --no-require-fresh-deploy if you know why."
        )


def build_update_plan(sort_key: str, new_version: str) -> dict:
    """Build the SAME SET + version-conditional expression the Change-Op repo issues.

    Mirrors ``projection_config_write_repository.apply_ops`` / ``_build_update_plan``: a
    single path ``update_item`` that SETs a value AND bumps ``version`` under a
    ``ConditionExpression``. For the sentinel we use the FIRST-WRITE / no-row case
    (``attribute_not_exists(sk)``) so the op both creates and version-stamps the sentinel
    exactly as the repo's create-verb branch does (design D5, review Must-fix #2).

    Returns a kwargs dict ready to splat into ``table.update_item(Key=..., **plan)``.
    """
    return {
        # SET a harmless probe attribute AND the authoritative version stamp, same as the
        # repo bumps version in the same expression as the op's SET.
        "UpdateExpression": "SET #probe = :probe, #version = :version",
        # First-write case (design D5 case iii): the row must not already exist. This makes
        # the op idempotent-safe — a stale sentinel is cleaned up before this runs.
        "ConditionExpression": "attribute_not_exists(#sk)",
        "ExpressionAttributeNames": {
            "#probe": "smoke_probe",
            "#version": "version",
            "#sk": "sk",
        },
        "ExpressionAttributeValues": {
            ":probe": "update_item-grant-smoke",
            ":version": new_version,
        },
    }


# ---------------------------------------------------------------------------
# AWS plane — thin client wrapper (injected with a fake in the unit test)
# ---------------------------------------------------------------------------


class SmokeAwsClient:
    """Deployed-stage AWS calls, isolated behind one class so the pure logic stays testable.

    All boto3 is lazy-imported so importing this module (and the unit test) needs no AWS.
    """

    def __init__(self, *, region: str, session=None):
        self._region = region
        if session is not None:
            self._session = session
        else:
            import boto3  # lazy — only when actually hitting AWS

            self._session = boto3.Session()

    # --- identity / discovery (read-only) ---------------------------------
    def whoami(self) -> tuple[str, str]:
        """Return ``(caller_arn, account_id)`` from STS (read-only)."""
        sts = self._session.client("sts", region_name=self._region)
        resp = sts.get_caller_identity()
        return resp["Arn"], resp["Account"]

    def describe_function_role(self, function_name: str) -> tuple[str, _dt.datetime]:
        """Return ``(role_arn, last_modified_utc)`` for the deployed Lambda (read-only)."""
        lam = self._session.client("lambda", region_name=self._region)
        cfg = lam.get_function_configuration(FunctionName=function_name)
        role_arn = cfg["Role"]
        last_modified = _parse_lambda_timestamp(cfg["LastModified"])
        return role_arn, last_modified

    # --- the grant exercise (assume-role approach) ------------------------
    def assume_role_resource(self, role_arn: str):
        """Assume ``role_arn`` and return a DynamoDB resource bound to its temp creds.

        This is the crux: the returned resource acts AS the Members Lambda execution role,
        so its DynamoDB calls are authorized by that role's policy — the grant under test.
        """
        sts = self._session.client("sts", region_name=self._region)
        creds = sts.assume_role(
            RoleArn=role_arn, RoleSessionName=ASSUME_SESSION_NAME
        )["Credentials"]
        import boto3  # lazy

        assumed = boto3.Session(
            aws_access_key_id=creds["AccessKeyId"],
            aws_secret_access_key=creds["SecretAccessKey"],
            aws_session_token=creds["SessionToken"],
            region_name=self._region,
        )
        return assumed.resource("dynamodb", region_name=self._region)

    # --- the caller-identity-check fallback (read-only, no write) ---------
    def simulate_update_item(self, role_arn: str, table_arn: str) -> bool:
        """Return True iff the role's policy ALLOWS dynamodb:UpdateItem on the table.

        A read-only ``iam:SimulatePrincipalPolicy`` — the non-destructive fallback that
        still catches a missing grant without performing any write.
        """
        iam = self._session.client("iam", region_name=self._region)
        resp = iam.simulate_principal_policy(
            PolicySourceArn=role_arn,
            ActionNames=["dynamodb:UpdateItem"],
            ResourceArns=[table_arn],
        )
        results = resp.get("EvaluationResults", [])
        return bool(results) and results[0].get("EvalDecision") == "allowed"


def _parse_lambda_timestamp(value: str) -> _dt.datetime:
    """Parse Lambda's LastModified (ISO-8601, e.g. ``2026-10-23T12:34:56.000+0000``)."""
    # Lambda returns e.g. "2026-10-23T12:34:56.000+0000"; normalise the offset for fromiso.
    v = value.strip()
    if v.endswith("+0000"):
        v = v[:-5] + "+00:00"
    try:
        dt = _dt.datetime.fromisoformat(v)
    except ValueError:
        # Fallback for a trailing 'Z'.
        dt = _dt.datetime.fromisoformat(v.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=_dt.timezone.utc)
    return dt


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


def _now_version_stamp() -> str:
    """A monotonic ISO-8601 UTC version stamp (same shape as the repo's write stamp)."""
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def run_smoke(
    *,
    region: str,
    function_name: str,
    table_name: str,
    approach: str,
    require_fresh_deploy: bool,
    deployed_after: str,
    allow_prod: bool,
    client: SmokeAwsClient | None = None,
) -> int:
    """Run the deployed-stage smoke test. Returns a process exit code (0 = pass)."""
    assert_test_target(table_name, allow_prod=allow_prod)

    aws = client or SmokeAwsClient(region=region)

    # 1. Identity must be the DATA account's NonprofitDeployRole (fail fast).
    caller_arn, account_id = aws.whoami()
    assert_expected_identity(caller_arn, account_id)
    print(f"identity OK: {caller_arn} (account {account_id})")

    # 2. Discover the deployed Lambda's execution-role ARN + freshness.
    role_arn, last_modified = aws.describe_function_role(function_name)
    print(f"deployed {function_name!r}: role={role_arn} last_modified={last_modified.isoformat()}")
    if require_fresh_deploy:
        assert_fresh_deploy(last_modified, parse_deployed_after(deployed_after))

    table_arn = f"arn:aws:dynamodb:{region}:{account_id}:table/{table_name}"

    if approach == "caller-identity-check":
        allowed = aws.simulate_update_item(role_arn, table_arn)
        if not allowed:
            raise SmokeError(
                f"policy simulation says the Lambda role {role_arn} is NOT allowed "
                f"dynamodb:UpdateItem on {table_arn}. Task 2.1's grant "
                "(MembersWriteGovernanceProjectionConfig) is missing or mis-scoped."
            )
        print(
            "SMOKE PASS (caller-identity-check): policy simulation confirms the Members "
            f"Lambda role holds dynamodb:UpdateItem on {table_name} (no write performed)."
        )
        return 0

    # approach == "assume-role": exercise the grant with a REAL update_item AS the role.
    ddb = aws.assume_role_resource(role_arn)
    table = ddb.Table(table_name)
    sentinel_key = {"tenant_id": SENTINEL_TENANT_ID, "sk": build_sentinel_sort_key()}

    # Clean up any stale sentinel from an interrupted prior run (idempotent re-run).
    _delete_sentinel(table, sentinel_key, label="pre-clean")

    # Snapshot a REAL config#fields row (if any) for the isolation invariant. We read
    # whatever tenant rows exist; the sentinel write must leave them byte-identical.
    before = _snapshot_real_config_fields(table)

    # 3. The grant exercise: a real Change-Op-shaped path update_item AS the Lambda role.
    from botocore.exceptions import ClientError

    plan = build_update_plan(sentinel_key["sk"], _now_version_stamp())
    try:
        table.update_item(Key=sentinel_key, **plan)
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "")
        if code == "AccessDeniedException":
            raise SmokeError(
                "AccessDeniedException on update_item AS the Members Lambda role — this is "
                "EXACTLY the failure task 2.1's grant prevents and that local DynamoDB can "
                "never catch. The dynamodb:UpdateItem grant "
                "(MembersWriteGovernanceProjectionConfig) is missing or mis-scoped on "
                f"{role_arn} for {table_arn}."
            ) from exc
        raise SmokeError(f"update_item failed unexpectedly ({code}): {exc}") from exc

    print("grant exercised: update_item AS the Lambda role SUCCEEDED (grant present).")

    # 4a. Assert the write landed.
    written = table.get_item(Key=sentinel_key).get("Item")
    if not written or written.get("smoke_probe") != "update_item-grant-smoke":
        _delete_sentinel(table, sentinel_key, label="post-fail")
        raise SmokeError("sentinel write did not land as expected — write path is broken.")

    # 4b. Isolation invariant: real config#fields rows unchanged (reuse the E2E idea).
    after = _snapshot_real_config_fields(table)
    if after != before:
        _delete_sentinel(table, sentinel_key, label="post-isolation-fail")
        raise SmokeError(
            "ISOLATION VIOLATED: a real config#fields row changed around a sentinel write. "
            "The write path is touching rows it must not — investigate before trusting the "
            "Change-Op path on this stack."
        )
    print(f"isolation invariant held: {len(before)} real config#fields row(s) byte-identical.")

    # 5. Self-revert: remove the sentinel we created.
    _delete_sentinel(table, sentinel_key, label="cleanup")

    print(
        f"SMOKE PASS: Members Lambda role {role_arn!r} holds dynamodb:UpdateItem on "
        f"{table_name!r} (grant exercised by a real Change-Op update_item; isolation "
        "invariant held; sentinel cleaned up)."
    )
    return 0


def _snapshot_real_config_fields(table) -> dict:
    """Return a map of {tenant_id: item} for every REAL ``config#fields`` row.

    Scans with a filter on ``sk = 'config#fields'`` (NOT the sentinel). Used to prove a
    sentinel write leaves real tenant config untouched. Read-only.
    """
    from boto3.dynamodb.conditions import Attr

    items: dict = {}
    kwargs = {"FilterExpression": Attr("sk").eq("config#fields")}
    while True:
        resp = table.scan(**kwargs)
        for item in resp.get("Items", []):
            items[item.get("tenant_id")] = item
        last = resp.get("LastEvaluatedKey")
        if not last:
            break
        kwargs["ExclusiveStartKey"] = last
    return items


def _delete_sentinel(table, key: dict, *, label: str) -> None:
    """Delete the sentinel item if present (best-effort, idempotent)."""
    try:
        table.delete_item(Key=key)
    except Exception as exc:  # noqa: BLE001 — cleanup must never mask the real result
        print(f"WARNING: sentinel {label} delete failed (non-fatal): {exc}", file=sys.stderr)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=(
            "Deployed-stage smoke test for the Members Lambda role's dynamodb:UpdateItem "
            "grant (spec 03 task 8.6). Run AFTER deploying the new stack to TEST. See the "
            "module docstring for the full runbook."
        )
    )
    p.add_argument("--region", default=os.environ.get("AWS_REGION", DEFAULT_REGION))
    p.add_argument("--stack-name", default=DEFAULT_STACK_NAME, dest="stack_name")
    p.add_argument("--function-name", default=DEFAULT_FUNCTION_NAME, dest="function_name")
    p.add_argument("--table", default=DEFAULT_TABLE_NAME, dest="table_name")
    p.add_argument(
        "--approach",
        choices=("assume-role", "caller-identity-check"),
        default="assume-role",
        help="assume-role (default): exercise the grant with a real update_item AS the "
        "Lambda role. caller-identity-check: read-only policy simulation fallback.",
    )
    p.add_argument(
        "--require-fresh-deploy",
        action="store_true",
        default=True,
        dest="require_fresh_deploy",
    )
    p.add_argument(
        "--no-require-fresh-deploy",
        action="store_false",
        dest="require_fresh_deploy",
    )
    p.add_argument("--deployed-after", default=DEFAULT_DEPLOYED_AFTER, dest="deployed_after")
    p.add_argument(
        "--i-understand-this-targets-prod",
        action="store_true",
        dest="allow_prod",
        help="Allow a non-test_ table. Not recommended — the grant is identical per env.",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return run_smoke(
            region=args.region,
            function_name=args.function_name,
            table_name=args.table_name,
            approach=args.approach,
            require_fresh_deploy=args.require_fresh_deploy,
            deployed_after=args.deployed_after,
            allow_prod=args.allow_prod,
        )
    except NotTestTargetError as exc:
        print(f"REFUSED (target guard): {exc}", file=sys.stderr)
        return 2
    except SmokeError as exc:
        print(f"SMOKE FAIL: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:  # noqa: BLE001 — surface any failure to the CLI
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
