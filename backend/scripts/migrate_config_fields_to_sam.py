#!/usr/bin/env python3
"""migrate_config_fields_to_sam.py — spec 02 Task 1.12 (operational, PRE builder removal).

Reusable, **idempotent** migration of every live tenant's MySQL ``members.field_overlay``
parameter into the SAM-owned ``config#fields`` row in ``governance_projection``, then a
read-back verify through the UNCHANGED Members projection reader
(``MembersProjectionReader.get_overlay``) to assert equivalence per tenant.

What it does (and does NOT do)
------------------------------
- **Migrates ``members.field_overlay`` ONLY.** The tenant-level ``members.default_page_size``
  is RETIRED (spec Req 7.2 / Requirement 25 — rows-per-page is now a per-user runtime
  selector); it is NEVER copied to SAM. The shaped ``config#fields`` body carries
  ``fields`` / ``overrides`` / ``functional_groups`` and NO ``default_page_size``.
- **Shape = the exact reader shape.** The body is produced by the SAME Flask builder the
  reader already consumes (``build_config_fields_row``), with ``default_page_size`` popped,
  so the SAM-written row is byte-for-byte what ``get_overlay`` expects — writer/reader
  cannot drift (spec R1.4).
- **Write path = the SAM write repository.** ``MembersConfigWriteRepository.put_config`` with
  a fresh ``next_write_stamp()`` version — the real SAM write door, not a raw ``put_item``.
- **Read-back verify = the real reader.** After each write the script re-reads via
  ``MembersProjectionReader.get_overlay`` and asserts the resolved ``TenantOverlay`` equals
  the overlay the written body reconstructs to. A tenant that fails verify is reported and
  (by default) aborts the run.

Phased, opt-in, reversible (spec Req 10.1/10.4/10.5/10.6)
---------------------------------------------------------
Every mutating phase is a separate, explicit, DEFAULT-OFF flag so nothing destructive or
PROD-touching happens by accident:

- (default)        DRY RUN — read MySQL + shape + print per-tenant plan; writes NOTHING.
- ``--write``      perform the DynamoDB writes + read-back verify (TEST by default).
- ``--prod``       target the PROD data account / ``governance_projection`` table. Without it
                   the run targets the TEST table (``test_governance_projection``). Gated by
                   an explicit identity sanity-check before any write.
- ``--delete-mysql`` DELETE the migrated ``members.field_overlay`` row AND the retired
                   ``members.default_page_size`` row from MySQL. This is the LAST, irreversible
                   step — it must only run AFTER a PROD read-back verify. Requires ``--write``
                   and refuses to run unless ``--i-have-prod-verified`` is also passed.

The MySQL params are KEPT until SAM is verified live in PROD, so the data migration stays
reversible (Req 10.5).

Account / table target
-----------------------
- MySQL (read): the resolved ``finance`` schema for the current ``APP_ENV`` / ``DB_*`` env
  (TEST = local Docker, PROD = Railway). This script issues ZERO MySQL writes unless
  ``--delete-mysql`` is given.
- DynamoDB (write/read): the ``nonprofit-deploy`` data account ``506221081911``, ``eu-west-1``.
  TEST = ``test_governance_projection``; PROD = ``governance_projection``. The script sets
  ``GOVERNANCE_PROJECTION_TABLE`` accordingly, unsets ``AWS_ENDPOINT_URL_DYNAMODB``, scrubs any
  static AWS keys so ``AWS_PROFILE`` resolves, and REFUSES to write unless STS resolves
  ``506221081911``.

Run (TEST, from repo root, venv active) — DRY RUN first, then real:
    AWS_PROFILE=nonprofit-deploy PYTHONPATH=backend/src backend/.venv/bin/python \
        backend/scripts/migrate_config_fields_to_sam.py --tenant h-dcn
    AWS_PROFILE=nonprofit-deploy PYTHONPATH=backend/src backend/.venv/bin/python \
        backend/scripts/migrate_config_fields_to_sam.py --write

The pure shaping/equivalence helpers (``shape_config_fields_body`` / ``overlay_from_body`` /
``overlays_equivalent``) carry NO boto3 / MySQL dependency and are unit-tested in
``backend/tests/unit/test_migrate_config_fields_to_sam.py``.
"""

from __future__ import annotations

import argparse
import os
import sys
from typing import Any

# The retired attribute — present on the Flask-built body, NEVER migrated to SAM (Req 7.2/25).
_RETIRED_PAGE_SIZE_ATTR = "default_page_size"

# The two MySQL param keys cleaned up by ``--delete-mysql`` (Req 10.6): the migrated overlay
# and the retired page-size scalar (deleted, never re-homed).
_MYSQL_NAMESPACE = "members"
_MYSQL_FIELD_OVERLAY_KEY = "field_overlay"
_MYSQL_DEFAULT_PAGE_SIZE_KEY = "default_page_size"

_DATA_ACCOUNT = "506221081911"
_TEST_TABLE = "test_governance_projection"
_PROD_TABLE = "governance_projection"


# ──────────────────────────────────────────────────────────────────────────────────────
# Pure shaping / equivalence helpers (no boto3, no MySQL — unit-tested in isolation).
# ──────────────────────────────────────────────────────────────────────────────────────


def shape_config_fields_body(fields_row_attributes: dict) -> dict:
    """Return the SAM ``config#fields`` body from the Flask builder's attributes.

    Takes the attributes dict produced by ``build_config_fields_row`` — which carries
    ``fields`` / ``overrides`` / ``functional_groups`` AND the retired ``default_page_size`` —
    and returns a NEW dict with ``default_page_size`` REMOVED (migrate ``field_overlay`` only,
    Req 7.2/25). Never mutates the input.

    This is the single place the "do not re-home default_page_size" rule is enforced on the
    write side, so the SAM row carries exactly ``fields`` / ``overrides`` / ``functional_groups``
    — the shape ``MembersProjectionReader.get_overlay`` reads back unchanged (R1.4).
    """
    body = dict(fields_row_attributes or {})
    body.pop(_RETIRED_PAGE_SIZE_ATTR, None)
    return body


def overlay_from_body(body: dict, tenant_id: str):
    """Rebuild the reader's ``TenantOverlay`` from a ``config#fields`` body (expected value).

    Reconstructs the EXACT same way ``MembersProjectionReader.get_overlay`` does, by feeding a
    synthetic projected item through the reader on an empty fake table — so "what we wrote"
    and "what the reader resolves" are compared on a level field. Returns a ``TenantOverlay``.
    """
    from services import projection_schema as schema

    from sam.members.repository.projection_config_reader import MembersProjectionReader

    item = {
        **(body or {}),
        schema.PARTITION_KEY_ATTR: tenant_id,
        schema.SORT_KEY_ATTR: schema.build_sort_key(
            schema.RECORD_TYPE_CONFIG, schema.CONFIG_ID_FIELDS
        ),
    }
    reader = MembersProjectionReader(table=_InMemoryTable([item]))
    return reader.get_overlay(tenant_id)


def overlays_equivalent(expected, actual) -> bool:
    """Return whether two resolved ``TenantOverlay`` objects are equivalent.

    ``TenantOverlay`` and its members are frozen dataclasses, so structural equality is value
    equality — a direct ``==`` is the equivalence check the read-back verify needs.
    """
    return expected == actual


class _InMemoryTable:
    """Minimal fake DynamoDB Table exposing ``query`` for the reader (one partition)."""

    def __init__(self, items: list[dict]):
        self._items = list(items)

    def query(self, **_kwargs) -> dict:
        return {"Items": list(self._items)}


# ──────────────────────────────────────────────────────────────────────────────────────
# Runtime wiring (boto3 + MySQL) — only reached by the CLI, never by the unit tests.
# ──────────────────────────────────────────────────────────────────────────────────────


def _prepare_aws_env(*, prod: bool) -> str:
    """Point boto3 at the data account + the correct projection table; return the table name.

    Scrubs the identity-account static keys the ``.env`` may inject so ``AWS_PROFILE`` resolves
    (credential-hygiene, steering 41), unsets the local-dynamodb endpoint, and sets
    ``GOVERNANCE_PROJECTION_TABLE`` to the TEST or PROD table.
    """
    table = _PROD_TABLE if prod else _TEST_TABLE
    os.environ["GOVERNANCE_PROJECTION_TABLE"] = table
    os.environ.pop("AWS_ENDPOINT_URL_DYNAMODB", None)
    os.environ.setdefault("AWS_REGION", "eu-west-1")
    os.environ.pop("AWS_ACCESS_KEY_ID", None)
    os.environ.pop("AWS_SECRET_ACCESS_KEY", None)
    os.environ.pop("AWS_SESSION_TOKEN", None)
    if not os.environ.get("AWS_PROFILE"):
        raise SystemExit(
            "AWS_PROFILE must be set (expected nonprofit-deploy) — refusing to touch the "
            "real projection without an explicit data-account profile."
        )
    return table


def _assert_data_account() -> None:
    """Fail loud unless boto3 resolves the data account 506221081911 (steering 41)."""
    import boto3

    ident = boto3.client("sts", region_name="eu-west-1").get_caller_identity()
    print(f"[migrate] STS account = {ident['Account']} arn={ident['Arn']}")
    if ident["Account"] != _DATA_ACCOUNT:
        raise SystemExit(
            f"[migrate] Refusing: resolved account {ident['Account']} is NOT the data "
            f"account {_DATA_ACCOUNT}."
        )


def _build_fields_body(tenant_id: str, parameter_service: Any) -> dict:
    """Read + shape one tenant's ``config#fields`` body (field_overlay only, no page_size)."""
    from services.projection_sync import build_config_fields_row

    row = build_config_fields_row({"administration": tenant_id}, parameter_service)
    # ``build_config_fields_row`` never returns None for a present tenant.
    return shape_config_fields_body(dict(row.attributes))


def _migrate(args: argparse.Namespace) -> int:
    """Drive the migration for the selected tenants; return a process exit code."""
    # backend/src on path so ``services.*`` / ``database`` import (PYTHONPATH may already do it).
    _src = os.path.join(os.path.dirname(__file__), "..", "src")
    if _src not in sys.path:
        sys.path.insert(0, _src)

    # Load the local-dev MySQL target (DB_* in backend/.env → localhost Docker, the resolved
    # TEST target per the #database skill). We never EDIT .env; we only read the DB_* it
    # already carries so DatabaseManager connects to local Docker instead of empty defaults.
    # The AWS *keys* were already scrubbed from the env files (steering 41), so loading .env
    # does not clobber AWS_PROFILE; we still scrub AWS keys in _prepare_aws_env as a
    # belt-and-suspenders before any DynamoDB write.
    from dotenv import load_dotenv

    _backend_env = os.path.join(os.path.dirname(__file__), "..", ".env")
    load_dotenv(_backend_env)

    from database import DatabaseManager
    from services.parameter_service import ParameterService
    from services._projection_source import DatabaseSourceProvider

    db = DatabaseManager()
    param_svc = ParameterService(db)

    # Resolve the live tenant list (min: the --tenant filter, else every tenant).
    if args.tenant:
        tenants = [args.tenant]
    else:
        tenants = DatabaseSourceProvider(db).list_administrations()
    if not tenants:
        print("[migrate] No live tenants found — nothing to migrate.")
        return 0
    print(f"[migrate] tenants in scope ({len(tenants)}): {', '.join(sorted(tenants))}")

    write = args.write
    table_name = None
    repo = reader = None
    if write:
        # The SAM plane lives at the repo root (``sam/...``); add it so the write repository +
        # reader + version helper import. This operational script is the one place that bridges
        # the Flask (MySQL) and SAM (DynamoDB) planes at RUNTIME — the import-plane boundary
        # (steering 30/31/36) governs product code, not a one-off migration driver.
        _repo_root = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "..")
        )
        if _repo_root not in sys.path:
            sys.path.insert(0, _repo_root)

        table_name = _prepare_aws_env(prod=args.prod)
        _assert_data_account()
        from sam.members.domain.config_write_version import next_write_stamp
        from sam.members.repository.projection_config_reader import (
            MembersProjectionReader,
        )
        from sam.members.repository.projection_config_write_repository import (
            MembersConfigWriteRepository,
        )
        from services import projection_schema as schema

        repo = MembersConfigWriteRepository()
        print(
            f"[migrate] WRITE target table = {table_name} ({'PROD' if args.prod else 'TEST'})"
        )
    else:
        print("[migrate] DRY RUN — shaping + planning only; NO DynamoDB writes.")

    failures: list[str] = []
    for tenant_id in sorted(tenants):
        body = _build_fields_body(tenant_id, param_svc)
        n_fields = len(body.get("fields") or {})
        n_over = len(body.get("overrides") or {})
        n_groups = len(body.get("functional_groups") or [])
        print(
            f"[migrate] {tenant_id}: fields={n_fields} overrides={n_over} "
            f"functional_groups={n_groups} default_page_size=OMITTED"
        )
        if not write:
            continue

        version = next_write_stamp()
        repo.put_config(
            tenant_id=tenant_id,
            config_id=schema.CONFIG_ID_FIELDS,
            attributes=body,
            version=version,
        )
        # Fresh reader each tenant so the per-invocation partition cache never serves stale data.
        read_back = MembersProjectionReader().get_overlay(tenant_id)
        expected = overlay_from_body(body, tenant_id)
        if overlays_equivalent(expected, read_back):
            print(f"[migrate] {tenant_id}: read-back verify OK (version={version})")
        else:
            failures.append(tenant_id)
            print(f"[migrate] {tenant_id}: read-back verify FAILED", file=sys.stderr)

    if write and failures:
        print(
            f"[migrate] ABORT: read-back verify failed for: {', '.join(failures)}",
            file=sys.stderr,
        )
        return 1

    if args.delete_mysql:
        if not write:
            raise SystemExit("[migrate] --delete-mysql requires --write.")
        if not args.i_have_prod_verified:
            raise SystemExit(
                "[migrate] Refusing --delete-mysql: pass --i-have-prod-verified only AFTER a "
                "PROD read-back verify. MySQL params stay until SAM is verified live in PROD "
                "(reversibility, Req 10.5)."
            )
        _delete_mysql_params(param_svc, sorted(tenants))

    if write:
        print(
            f"[migrate] DONE — {len(tenants)} tenant(s) migrated + read-back verified."
        )
    else:
        print(
            "[migrate] DRY RUN complete. Re-run with --write to perform the migration."
        )
    return 0


def _delete_mysql_params(param_svc: Any, tenants: list[str]) -> None:
    """DELETE the migrated ``field_overlay`` + retired ``default_page_size`` MySQL rows (Req 10.6).

    Only reached after an explicit ``--delete-mysql --i-have-prod-verified`` opt-in following a
    PROD read-back verify. Delegates to ``ParameterService.delete_param`` (the canonical
    tenant-scope delete — correct column quoting + cache invalidation) for both keys per tenant.
    """
    print(
        "[migrate] DELETE MySQL params (field_overlay + retired default_page_size) ..."
    )
    for tenant_id in tenants:
        for key in (_MYSQL_FIELD_OVERLAY_KEY, _MYSQL_DEFAULT_PAGE_SIZE_KEY):
            param_svc.delete_param("tenant", tenant_id, _MYSQL_NAMESPACE, key)
        print(
            f"[migrate] {tenant_id}: deleted members.field_overlay + members.default_page_size"
        )


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--tenant",
        help="Migrate a single tenant (e.g. h-dcn). Default: all live tenants.",
    )
    p.add_argument(
        "--write",
        action="store_true",
        help="Perform the DynamoDB writes + read-back verify.",
    )
    p.add_argument(
        "--prod",
        action="store_true",
        help="Target PROD governance_projection (default: TEST).",
    )
    p.add_argument(
        "--delete-mysql",
        action="store_true",
        help="DELETE the migrated field_overlay + retired default_page_size MySQL rows (gated).",
    )
    p.add_argument(
        "--i-have-prod-verified",
        action="store_true",
        help="Confirm a PROD read-back verify already succeeded (required for --delete-mysql).",
    )
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    return _migrate(_parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
