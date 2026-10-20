#!/usr/bin/env python3
"""migrate_config_scope_to_sam.py — spec 02 Task 3.4 (operational, PRE builder removal).

Reusable, **idempotent** migration of every live tenant's scope config into the SAM-owned
``config#scope`` row in ``governance_projection``, then a read-back verify through the UNCHANGED
Members projection reader (``MembersProjectionReader.get_scope_config``) to assert equivalence
per tenant.

How this differs from the fields migration (Task 1.12)
------------------------------------------------------
- **Source = the per-field ``scope`` attribute on ``members.field_overlay``.** Task 3.1 made the
  overlay the SINGLE authoring source for ``config#scope`` (the standalone
  ``members.scope_dimensions`` fallback was removed). So the scope body is produced by the SAME
  Flask builder the reader already consumes end-to-end — ``build_config_scope_row`` — which
  DERIVES the ``dimensions`` from the overlay's per-field ``scope`` axes. Writer/reader cannot
  drift (spec R8.1).
- **``members.scope_dimensions`` is NOT deleted.** Under the frontend-mirror model (Req 22/26) the
  standalone param is KEPT as the frontend-written Flask MIRROR the grant validators read. This
  script therefore has NO ``--delete-mysql`` phase. Instead it can SEED that mirror from the
  SAM-authoritative dimensions (``--seed-mirror``) so the grant validators keep reading a current
  mirror for tenants that have not yet re-saved scope through the new UI (Req 22.4 / 26.3).
- **No verify-before-retire-delete gate** applies to this key under the mirror model — only the
  read-back verify of ``config#scope`` is required (Req 10 scope leg).

Write path = the SAM write repository (``MembersConfigWriteRepository.put_config`` with a fresh
``next_write_stamp()`` version); read-back verify = the real reader
(``MembersProjectionReader.get_scope_config``). An empty dimensions set is valid (tenant-wide).

Phased, opt-in (spec Req 10.1/10.4/10.5)
----------------------------------------
- (default)        DRY RUN — read MySQL + shape + print per-tenant plan; writes NOTHING.
- ``--write``      perform the DynamoDB writes + read-back verify (TEST by default).
- ``--prod``       target the PROD data account / ``governance_projection`` table (gated by an
                   explicit STS identity check). Without it the run targets the TEST table.
- ``--seed-mirror`` after a verified SAM write, SEED the Flask ``members.scope_dimensions`` mirror
                   from the SAM-authoritative dimensions (best-effort; the frontend otherwise
                   populates it on first scope save). Requires ``--write``.

Account / table target — identical discipline to migrate_config_fields_to_sam.py:
- MySQL (read, + mirror write only under --seed-mirror): the resolved ``finance`` schema for the
  current ``APP_ENV`` / ``DB_*`` env (TEST = local Docker, PROD = Railway).
- DynamoDB (write/read): the ``nonprofit-deploy`` data account ``506221081911``, ``eu-west-1``.
  TEST = ``test_governance_projection``; PROD = ``governance_projection``.

Run (TEST, from repo root, venv active) — DRY RUN first, then real:
    AWS_PROFILE=nonprofit-deploy PYTHONPATH=backend/src backend/.venv/bin/python \
        backend/scripts/migrate_config_scope_to_sam.py --tenant h-dcn
    AWS_PROFILE=nonprofit-deploy PYTHONPATH=backend/src backend/.venv/bin/python \
        backend/scripts/migrate_config_scope_to_sam.py --write

The pure shaping/equivalence helpers (``shape_config_scope_body`` / ``scope_config_from_body`` /
``scope_configs_equivalent``) carry NO boto3 / MySQL dependency and are unit-tested in
``backend/tests/unit/test_migrate_config_scope_to_sam.py``.
"""

from __future__ import annotations

import argparse
import os
import sys
from typing import Any

_MYSQL_NAMESPACE = "members"
#: The standalone param KEPT as the frontend-written mirror (never deleted; optionally seeded).
_MYSQL_SCOPE_DIMENSIONS_KEY = "scope_dimensions"

_DATA_ACCOUNT = "506221081911"
_TEST_TABLE = "test_governance_projection"
_PROD_TABLE = "governance_projection"


# ──────────────────────────────────────────────────────────────────────────────────────
# Pure shaping / equivalence helpers (no boto3, no MySQL — unit-tested in isolation).
# ──────────────────────────────────────────────────────────────────────────────────────


def shape_config_scope_body(scope_row_attributes: dict) -> dict:
    """Return the SAM ``config#scope`` body from the Flask builder's attributes.

    ``build_config_scope_row`` produces ``{"dimensions": [...]}`` already in the exact shape
    ``MembersProjectionReader.get_scope_config`` reads back (R8.1). This normalizes to a NEW dict
    carrying only ``dimensions`` (empty list when the tenant authored no field scope axis —
    tenant-wide, R8.5). Never mutates the input.
    """
    body = dict(scope_row_attributes or {})
    dimensions = body.get("dimensions")
    if not isinstance(dimensions, list):
        dimensions = []
    return {"dimensions": list(dimensions)}


def scope_config_from_body(body: dict, tenant_id: str):
    """Rebuild the reader's ``ScopeConfig`` from a ``config#scope`` body (expected value).

    Reconstructs the EXACT way ``MembersProjectionReader.get_scope_config`` does, by feeding a
    synthetic projected item through the reader on an in-memory table — so "what we wrote" and
    "what the reader resolves" are compared on a level field. Returns a ``ScopeConfig``.
    """
    from sam.members.repository.projection_config_reader import MembersProjectionReader

    from services import projection_schema as schema

    item = {
        **(body or {}),
        schema.PARTITION_KEY_ATTR: tenant_id,
        schema.SORT_KEY_ATTR: schema.build_sort_key(
            schema.RECORD_TYPE_CONFIG, schema.CONFIG_ID_SCOPE
        ),
    }
    reader = MembersProjectionReader(table=_InMemoryTable([item]))
    return reader.get_scope_config(tenant_id)


def scope_configs_equivalent(expected, actual) -> bool:
    """Return whether two resolved ``ScopeConfig`` objects are equivalent.

    ``ScopeConfig`` / ``ScopeDimension`` are frozen dataclasses, so structural equality is value
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
    """Point boto3 at the data account + the correct projection table; return the table name."""
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


def _build_scope_body(tenant_id: str, parameter_service: Any) -> dict:
    """Read + shape one tenant's ``config#scope`` body (derived from the overlay scope axes)."""
    from services.projection_sync import build_config_scope_row

    row = build_config_scope_row({"administration": tenant_id}, parameter_service)
    # ``build_config_scope_row`` never returns None for a present tenant.
    return shape_config_scope_body(dict(row.attributes))


def _migrate(args: argparse.Namespace) -> int:
    """Drive the migration for the selected tenants; return a process exit code."""
    _src = os.path.join(os.path.dirname(__file__), "..", "src")
    if _src not in sys.path:
        sys.path.insert(0, _src)

    from dotenv import load_dotenv

    _backend_env = os.path.join(os.path.dirname(__file__), "..", ".env")
    load_dotenv(_backend_env)

    from database import DatabaseManager
    from services._projection_source import DatabaseSourceProvider
    from services.parameter_service import ParameterService

    db = DatabaseManager()
    param_svc = ParameterService(db)

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
    repo = None
    if write:
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
        body = _build_scope_body(tenant_id, param_svc)
        n_dims = len(body.get("dimensions") or [])
        tenant_wide = " (tenant-wide)" if n_dims == 0 else ""
        print(f"[migrate] {tenant_id}: dimensions={n_dims}{tenant_wide}")
        if not write:
            continue

        version = next_write_stamp()
        repo.put_config(
            tenant_id=tenant_id,
            config_id=schema.CONFIG_ID_SCOPE,
            attributes=body,
            version=version,
        )
        read_back = MembersProjectionReader().get_scope_config(tenant_id)
        expected = scope_config_from_body(body, tenant_id)
        if scope_configs_equivalent(expected, read_back):
            print(f"[migrate] {tenant_id}: read-back verify OK (version={version})")
        else:
            failures.append(tenant_id)
            print(f"[migrate] {tenant_id}: read-back verify FAILED", file=sys.stderr)
            continue

        if args.seed_mirror:
            _seed_mirror(param_svc, tenant_id, body.get("dimensions") or [])

    if write and failures:
        print(
            f"[migrate] ABORT: read-back verify failed for: {', '.join(failures)}",
            file=sys.stderr,
        )
        return 1

    if args.seed_mirror and not write:
        raise SystemExit("[migrate] --seed-mirror requires --write.")

    if write:
        print(
            f"[migrate] DONE — {len(tenants)} tenant(s) migrated + read-back verified."
        )
    else:
        print(
            "[migrate] DRY RUN complete. Re-run with --write to perform the migration."
        )
    return 0


def _seed_mirror(param_svc: Any, tenant_id: str, dimensions: list) -> None:
    """SEED the Flask ``members.scope_dimensions`` MIRROR from the SAM-authoritative dimensions.

    Best-effort (Req 22.4/26.3): keeps the grant validators reading a current mirror for a tenant
    that has not re-saved scope through the new UI yet. NOT a delete — the mirror is KEPT. Writes
    the SAME dimension set SAM authored, via ``ParameterService.set_param`` (the canonical
    tenant-scope write). SAM stays authoritative; a mirror write failure is surfaced, not fatal.
    """
    try:
        param_svc.set_param(
            "tenant",
            tenant_id,
            _MYSQL_NAMESPACE,
            _MYSQL_SCOPE_DIMENSIONS_KEY,
            list(dimensions),
            value_type="json",
        )
        print(
            f"[migrate] {tenant_id}: seeded members.scope_dimensions mirror "
            f"({len(dimensions)} dimension(s))"
        )
    except Exception as exc:
        print(
            f"[migrate] {tenant_id}: mirror seed FAILED (SAM stays authoritative): {exc}",
            file=sys.stderr,
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
        "--seed-mirror",
        action="store_true",
        help="Seed the Flask members.scope_dimensions mirror from SAM dimensions (best-effort).",
    )
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    return _migrate(_parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
