#!/usr/bin/env python3
"""copy-prod-to-test.py — the Copy_Utility (test-environment spec, Req 16 + 20.4).

The ONE supported way to make the Test_Environment's *contents* look like the
Production_Environment, when a specific test needs that parity. It copies, one-
directionally, from PROD into TEST:

  * **Cognito account attributes** — a named reference account's non-secret
    attributes (``custom:tenants`` / ``custom:role`` / email) from PROD Pool A
    into the TEST pool (`myAdmin-test`), creating the TEST user if absent. It
    NEVER copies passwords or secrets.
  * **DynamoDB table data** — items from a PROD table (e.g. ``governance_projection``
    or ``sam-members``) into the matching ``test_``-prefixed TEST table.

Folder standard (scripts/onboarding/README.md conventions): this lives in a
purpose-named subfolder (``scripts/test-environment/``), bootstraps the repo root
via the shared ``_lib.paths`` marker walk (never ad-hoc ``dirname`` counting), is
dry-run-first, and is documented in the folder README. It is NOT tenant-onboarding
tooling, so it sits under ``scripts/test-environment/`` rather than
``scripts/onboarding/``.

Hard guardrails (Req 16.2-16.6, 19, 20) — the whole point of this utility:

  1. **Explicit human invocation only** (16.2/16.3). Dry-run is the DEFAULT; a
     real copy requires BOTH ``--apply`` and ``--i-understand-this-writes-test``.
     There is no scheduler/startup/import hook — the module does nothing on import.
  2. **One-directional, PROD → TEST only** (16.4/16.5). The SOURCE clients are
     PROD; the DESTINATION clients are TEST. The source is only ever read
     (Scan/GetItem, admin_get_user); the destination is the only thing written.
     There is no code path that writes toward PROD.
  3. **Destination must BE test** (defense in depth). Before any write the
     utility asserts the destination DynamoDB table name starts with ``test_``
     and the destination Cognito pool is the test pool — and that source != dest.
     A destination that is not demonstrably TEST aborts (``NotTestDestinationError``).
  4. **Separate from the running unit** (16.6). This is a standalone CLI, never
     invoked by the Flask/SAM running units.
  5. **No secrets in the repo** (19.1). Pool ids are PUBLIC identifiers; no
     passwords/secrets are read, written, or printed.

Accounts (23-aws-accounts.md):
  * Cognito pools live in the IDENTITY/personal account (344561557829): PROD Pool
    A ``eu-west-1_Hdp40eWmu``, TEST ``eu-west-1_xyrlzfqbl``.
  * DynamoDB tables live in the DATA account (506221081911). Copying within one
    account is the default; the clients are built from the ambient profile/creds.

Usage (from repo root, WSL) — dry-run is the default, prints the plan only:

  # Preview a Cognito reference-account copy (nothing written):
  backend/.venv/bin/python scripts/test-environment/copy-prod-to-test.py cognito \\
      --email reference.user@example.org

  # Preview a DynamoDB projection copy:
  backend/.venv/bin/python scripts/test-environment/copy-prod-to-test.py dynamodb \\
      --source-table governance_projection

  # Actually write TEST (requires BOTH flags), Cognito in the identity account:
  AWS_PROFILE=personal AWS_REGION=eu-west-1 \\
      backend/.venv/bin/python scripts/test-environment/copy-prod-to-test.py cognito \\
      --email reference.user@example.org --apply --i-understand-this-writes-test

  # Actually write TEST, DynamoDB in the data account:
  AWS_PROFILE=nonprofit-deploy AWS_REGION=eu-west-1 \\
      backend/.venv/bin/python scripts/test-environment/copy-prod-to-test.py dynamodb \\
      --source-table governance_projection --apply --i-understand-this-writes-test
"""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass, field

# Bootstrap: find the repo root by walking up to a marker, then hand off to the
# shared onboarding `_lib` for repo-root + backend/src setup (scripts/onboarding/
# README.md "Robust paths (R4)"). This tiny block is the one place that must locate
# the root BEFORE `_lib` is importable; everything else goes through `_lib`.
_r = os.path.abspath(__file__)
while _r != os.path.dirname(_r):
    _r = os.path.dirname(_r)
    if os.path.isdir(os.path.join(_r, ".git")) or os.path.isdir(os.path.join(_r, ".kiro")):
        break
if _r not in sys.path:
    sys.path.insert(0, _r)
from scripts.onboarding._lib.paths import ensure_backend_src_on_path  # noqa: E402

ensure_backend_src_on_path()

# Public, non-secret Cognito pool identifiers (23-aws-accounts.md). The PROD pool
# is the copy SOURCE; the TEST pool is the copy DESTINATION. These are the only
# pools this utility ever touches, and TEST is the only one it writes.
PROD_POOL_ID = "eu-west-1_Hdp40eWmu"  # Pool A (myAdmin) — SOURCE (read-only)
TEST_POOL_ID = "eu-west-1_xyrlzfqbl"  # myAdmin-test     — DESTINATION (write)

#: The TEST DynamoDB table boundary. The destination table MUST start with this
#: prefix or the copy is refused (defense in depth over the one-directional design).
TEST_TABLE_PREFIX = "test_"

DEFAULT_REGION = "eu-west-1"

#: Cognito attributes that MAY be copied PROD -> TEST. Deliberately a small, non-
#: secret allow-list: identity + entitlement shape only. Passwords/secrets and
#: Cognito-managed fields (sub, status, timestamps) are never copied.
COPYABLE_COGNITO_ATTRS = ("email", "email_verified", "custom:tenants", "custom:role", "custom:scope")


class CopyDirectionError(RuntimeError):
    """A copy would write toward PROD, or source and destination are the same.

    Raised BEFORE any write. The Copy_Utility is strictly one-directional
    (Req 16.4/16.5): PROD is read-only, TEST is the only writable side.
    """


class NotTestDestinationError(RuntimeError):
    """The destination is not demonstrably the TEST environment.

    Raised when the destination DynamoDB table does not carry the ``test_``
    prefix, or the destination Cognito pool is not the test pool. Defense in
    depth: even a mis-wired client cannot write a non-TEST destination.
    """


class ConfirmationRequiredError(RuntimeError):
    """``--apply`` was given without the explicit write acknowledgement.

    A real write requires BOTH ``--apply`` and ``--i-understand-this-writes-test``
    so a copy can never happen as an accidental or automated side effect
    (Req 16.2/16.3).
    """


# ---------------------------------------------------------------------------
# Shared destination-safety assertions (used by both planes)
# ---------------------------------------------------------------------------


def _assert_cognito_direction(source_pool: str, dest_pool: str) -> None:
    """Refuse unless source is PROD Pool A and destination is the TEST pool."""
    if dest_pool == source_pool:
        raise CopyDirectionError(
            f"source and destination Cognito pools are identical ({dest_pool}); "
            "the Copy_Utility only copies PROD -> TEST, never pool-to-itself."
        )
    if dest_pool != TEST_POOL_ID:
        raise NotTestDestinationError(
            f"destination Cognito pool {dest_pool!r} is not the TEST pool "
            f"({TEST_POOL_ID}); the Copy_Utility writes the TEST pool ONLY."
        )
    if source_pool != PROD_POOL_ID:
        raise CopyDirectionError(
            f"source Cognito pool {source_pool!r} is not PROD Pool A ({PROD_POOL_ID}); "
            "the Copy_Utility copies FROM production only."
        )


def _assert_dynamodb_direction(source_table: str, dest_table: str) -> None:
    """Refuse unless the destination is a distinct ``test_``-prefixed table."""
    if dest_table == source_table:
        raise CopyDirectionError(
            f"source and destination tables are identical ({dest_table}); the "
            "Copy_Utility only copies PROD -> TEST, never a table onto itself."
        )
    if not dest_table.startswith(TEST_TABLE_PREFIX):
        raise NotTestDestinationError(
            f"destination table {dest_table!r} does not start with "
            f"{TEST_TABLE_PREFIX!r}; the Copy_Utility writes TEST tables ONLY."
        )
    if source_table.startswith(TEST_TABLE_PREFIX):
        raise CopyDirectionError(
            f"source table {source_table!r} is itself a TEST table; the "
            "Copy_Utility copies FROM a production (unprefixed) table only."
        )


def _derive_test_table_name(source_table: str) -> str:
    """The TEST destination table for a PROD source table: prepend ``test_``."""
    return f"{TEST_TABLE_PREFIX}{source_table}"


# ---------------------------------------------------------------------------
# Cognito plane — copy a reference account's non-secret attributes PROD -> TEST
# ---------------------------------------------------------------------------


class CognitoCopyClient:
    """Read PROD user attributes; create/update the TEST user. TEST is write-only side.

    Two boto3 ``cognito-idp`` calls could use the same client (same identity
    account) — the DIRECTION is enforced by which pool id each call targets, which
    the guards above assert. Injected in tests with an in-memory fake.
    """

    def __init__(self, *, region: str, client=None):
        if client is not None:
            self._client = client
        else:
            import boto3  # lazy — only when actually applying

            self._client = boto3.client("cognito-idp", region_name=region)

    def read_prod_attributes(self, email: str) -> dict[str, str]:
        """Read the PROD user's copyable attributes (read-only; raises if absent)."""
        resp = self._client.admin_get_user(UserPoolId=PROD_POOL_ID, Username=email)
        attrs = {a["Name"]: a["Value"] for a in resp.get("UserAttributes", [])}
        # Keep only the non-secret allow-list.
        return {k: v for k, v in attrs.items() if k in COPYABLE_COGNITO_ATTRS}

    def test_user_exists(self, email: str) -> bool:
        try:
            self._client.admin_get_user(UserPoolId=TEST_POOL_ID, Username=email)
            return True
        except self._client.exceptions.UserNotFoundException:
            return False

    def write_test_user(self, email: str, attributes: dict[str, str], *, created: bool) -> None:
        """Create (if absent) + set attributes on the TEST user. Writes TEST pool ONLY."""
        attr_list = [{"Name": k, "Value": v} for k, v in attributes.items()]
        if created:
            self._client.admin_create_user(
                UserPoolId=TEST_POOL_ID,
                Username=email,
                UserAttributes=attr_list,
                MessageAction="SUPPRESS",  # no invite email; provisioning sets the password
            )
        else:
            self._client.admin_update_user_attributes(
                UserPoolId=TEST_POOL_ID, Username=email, UserAttributes=attr_list
            )


@dataclass
class CognitoCopyResult:
    email: str
    attributes: dict[str, str] = field(default_factory=dict)
    created: bool = False
    applied: bool = False


def copy_cognito_account(
    email: str,
    *,
    region: str,
    apply: bool,
    confirmed: bool,
    client: CognitoCopyClient | None = None,
) -> CognitoCopyResult:
    """Copy one reference account's non-secret attributes PROD Pool A -> TEST pool.

    Dry-run (default) reads PROD and prints what WOULD be written; nothing is
    written. ``apply`` requires ``confirmed`` and writes the TEST pool only.
    """
    # Direction + destination safety (enforced regardless of apply, so a dry-run
    # against a mis-set destination still surfaces the problem).
    _assert_cognito_direction(PROD_POOL_ID, TEST_POOL_ID)

    cognito = client or CognitoCopyClient(region=region)
    attributes = cognito.read_prod_attributes(email)
    already = cognito.test_user_exists(email)
    result = CognitoCopyResult(email=email, attributes=attributes, created=not already)

    _print_cognito_plan(result, apply=apply)

    if not apply:
        return result
    if not confirmed:
        raise ConfirmationRequiredError(
            "--apply requires --i-understand-this-writes-test (the copy writes the "
            "TEST Cognito pool)."
        )
    cognito.write_test_user(email, attributes, created=result.created)
    result.applied = True
    return result


def _print_cognito_plan(result: CognitoCopyResult, *, apply: bool) -> None:
    print("=" * 64)
    print("Copy_Utility — Cognito reference account (PROD Pool A -> TEST pool)")
    print("=" * 64)
    print(f"  source pool  : {PROD_POOL_ID} (PROD Pool A, read-only)")
    print(f"  dest pool    : {TEST_POOL_ID} (myAdmin-test, write)")
    print(f"  email        : {result.email}")
    print(f"  dest user    : {'CREATE (absent)' if result.created else 'UPDATE (exists)'}")
    print(f"  mode         : {'APPLY' if apply else 'DRY-RUN (writes nothing)'}")
    print("  attributes copied (non-secret allow-list; NO password/secret):")
    if not result.attributes:
        print("    (none found on the PROD user)")
    for k in sorted(result.attributes):
        print(f"    {k} = {result.attributes[k]}")
    print("=" * 64)


# ---------------------------------------------------------------------------
# DynamoDB plane — copy items PROD table -> matching test_ table
# ---------------------------------------------------------------------------


class DynamoCopyClient:
    """Scan a PROD table (read-only); BatchWrite into the TEST table (write-only side).

    Injected in tests with an in-memory fake. The source table is only ever
    scanned; the destination table is the only thing written.
    """

    def __init__(self, *, region: str, resource=None):
        if resource is not None:
            self._resource = resource
        else:
            from services.dynamodb_client import get_dynamodb_resource  # lazy

            self._resource = get_dynamodb_resource(region=region)

    def scan_source(self, table_name: str) -> list[dict]:
        """Read ALL items from the PROD source table (read-only)."""
        table = self._resource.Table(table_name)
        items: list[dict] = []
        kwargs: dict = {}
        while True:
            resp = table.scan(**kwargs)
            items.extend(resp.get("Items", []))
            last = resp.get("LastEvaluatedKey")
            if not last:
                break
            kwargs["ExclusiveStartKey"] = last
        return items

    def write_dest(self, table_name: str, items: list[dict]) -> int:
        """Write items into the TEST destination table. Writes the dest table ONLY."""
        table = self._resource.Table(table_name)
        written = 0
        with table.batch_writer() as batch:
            for item in items:
                batch.put_item(Item=item)
                written += 1
        return written


@dataclass
class DynamoCopyResult:
    source_table: str
    dest_table: str
    item_count: int = 0
    written: int = 0
    applied: bool = False


def copy_dynamodb_table(
    source_table: str,
    *,
    region: str,
    apply: bool,
    confirmed: bool,
    dest_table: str | None = None,
    client: DynamoCopyClient | None = None,
) -> DynamoCopyResult:
    """Copy all items from a PROD table into its ``test_``-prefixed TEST table.

    Dry-run (default) scans the source and reports the item count; nothing is
    written. ``apply`` requires ``confirmed`` and writes the TEST table only.
    """
    dest = dest_table or _derive_test_table_name(source_table)
    _assert_dynamodb_direction(source_table, dest)

    dynamo = client or DynamoCopyClient(region=region)
    items = dynamo.scan_source(source_table)
    result = DynamoCopyResult(source_table=source_table, dest_table=dest, item_count=len(items))

    _print_dynamo_plan(result, apply=apply)

    if not apply:
        return result
    if not confirmed:
        raise ConfirmationRequiredError(
            "--apply requires --i-understand-this-writes-test (the copy writes the "
            f"TEST table {dest!r})."
        )
    result.written = dynamo.write_dest(dest, items)
    result.applied = True
    print(f"\nWrote {result.written} item(s) into {dest}.")
    return result


def _print_dynamo_plan(result: DynamoCopyResult, *, apply: bool) -> None:
    print("=" * 64)
    print("Copy_Utility — DynamoDB table (PROD -> TEST)")
    print("=" * 64)
    print(f"  source table : {result.source_table} (PROD, read-only)")
    print(f"  dest table   : {result.dest_table} (TEST, write)")
    print(f"  items read   : {result.item_count}")
    print(f"  mode         : {'APPLY' if apply else 'DRY-RUN (writes nothing)'}")
    print("=" * 64)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    # Common flags live on a PARENT parser so they are accepted in natural position
    # on either subcommand (e.g. `dynamodb --source-table X --apply`), not only
    # before the subcommand. This avoids the argparse "unrecognized arguments"
    # trap that bites when a global flag is written after the subcommand.
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--region",
        default=os.environ.get("AWS_REGION", DEFAULT_REGION),
        help=f"AWS region (default: env AWS_REGION or {DEFAULT_REGION}).",
    )
    common.add_argument(
        "--apply",
        action="store_true",
        help="Actually write TEST. Without this the utility only prints the plan (dry-run is "
        "the default). Must be combined with --i-understand-this-writes-test.",
    )
    common.add_argument(
        "--i-understand-this-writes-test",
        dest="confirmed",
        action="store_true",
        help="Explicit acknowledgement that --apply writes the TEST environment. Required with "
        "--apply so a copy can never happen as an accidental or automated side effect.",
    )

    parser = argparse.ArgumentParser(
        parents=[common],
        description="Copy_Utility — copy PROD contents into TEST, one-directionally and only "
        "on explicit human request. Dry-run by default; a real write needs BOTH --apply and "
        "--i-understand-this-writes-test.",
    )

    sub = parser.add_subparsers(dest="plane", required=True)

    cog = sub.add_parser(
        "cognito",
        parents=[common],
        help="Copy a reference account's non-secret attributes.",
    )
    cog.add_argument(
        "--email",
        required=True,
        help="The reference account email to copy from PROD Pool A into the TEST pool.",
    )

    dyn = sub.add_parser(
        "dynamodb",
        parents=[common],
        help="Copy a PROD table's items into its test_ table.",
    )
    dyn.add_argument(
        "--source-table",
        required=True,
        help="The PROD (unprefixed) source table, e.g. governance_projection or sam-members.",
    )
    dyn.add_argument(
        "--dest-table",
        default=None,
        help="Override the destination table (default: 'test_' + source). Must start with "
        "'test_' or the copy is refused.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.plane == "cognito":
            copy_cognito_account(
                args.email,
                region=args.region,
                apply=args.apply,
                confirmed=args.confirmed,
            )
        elif args.plane == "dynamodb":
            copy_dynamodb_table(
                args.source_table,
                region=args.region,
                apply=args.apply,
                confirmed=args.confirmed,
                dest_table=args.dest_table,
            )
        else:  # pragma: no cover - argparse enforces a known subcommand
            raise ValueError(f"unknown plane {args.plane!r}")
    except ConfirmationRequiredError as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 2
    except (CopyDirectionError, NotTestDestinationError) as exc:
        print(f"REFUSED (direction/destination guard): {exc}", file=sys.stderr)
        return 2
    except Exception as exc:  # noqa: BLE001 — surface any failure to the CLI
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
