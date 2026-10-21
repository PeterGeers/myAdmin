#!/usr/bin/env python3
"""migrate_config_mail_to_sam.py — spec 02 Task 5.5 (operational, PRE builder removal).

Reusable, **idempotent** migration of every live tenant's MySQL ``members.mail_*`` parameters
into the SAM-owned ``config#mail`` row in ``governance_projection``, then a read-back verify
through the UNCHANGED Members projection reader (the ``MembersProjectionReader`` mail accessors)
to assert equivalence per tenant.

How this mirrors — and differs from — the fields / scope migrations
-------------------------------------------------------------------
- **Source = the ``members`` mail params** (``mail_enabled`` / ``mail_domain`` /
  ``mail_local_part`` / ``mail_certified`` / ``application_consent_notice`` / the scope-copy
  toggle). The body is produced by the SAME Flask builder the reader already consumes end-to-end
  — ``build_config_mail_row`` — so writer and reader cannot drift (spec R1.4 / Property 1).
- **``mail_reply_to_default`` is SAM-only net-new** (spec 02 Task 5.1). It has no pre-existing
  MySQL authoring source to migrate — a tenant that never authored one simply projects a row
  WITHOUT the attribute (the scheduled-send resolver then falls back to the composed From). So
  this migration carries whatever ``build_config_mail_row`` reads today and never fabricates a
  reply-to default.
- **No ``--delete-mysql`` phase and no mirror-seed.** The mail params remain the frontend
  authoring source in MySQL until Step 7 moves authoring onto the SAM write door; this migration
  is purely the forward copy + read-back verify (the fields migration's irreversible delete is
  gated separately, Req 10). Only the read-back verify of ``config#mail`` is required here.

Write path = the SAM write repository (``MembersConfigWriteRepository.put_config`` with a fresh
``next_write_stamp()`` version); read-back verify = the real reader's mail accessors. A tenant
that has authored no mail params still projects a fail-closed row (``mail_enabled=False`` /
``mail_certified=False`` / ``mail_local_part="noreply"``, no domain) — valid and expected.

Phased, opt-in (spec Req 10.1/10.4/10.5)
----------------------------------------
- (default)        DRY RUN — read MySQL + shape + print per-tenant plan; writes NOTHING.
- ``--write``      perform the DynamoDB writes + read-back verify (TEST by default).
- ``--prod``       target the PROD data account / ``governance_projection`` table (gated by an
                   explicit STS identity check). Without it the run targets the TEST table.

Account / table target — identical discipline to migrate_config_scope_to_sam.py:
- MySQL (read): the resolved ``finance`` schema for the current ``APP_ENV`` / ``DB_*`` env
  (TEST = local Docker, PROD = Railway). This script issues ZERO MySQL writes.
- DynamoDB (write/read): the ``nonprofit-deploy`` data account ``506221081911``, ``eu-west-1``.
  TEST = ``test_governance_projection``; PROD = ``governance_projection``.

Run (TEST, from repo root, venv active) — DRY RUN first, then real:
    AWS_PROFILE=nonprofit-deploy PYTHONPATH=backend/src backend/.venv/bin/python \
        backend/scripts/migrate_config_mail_to_sam.py --tenant h-dcn
    AWS_PROFILE=nonprofit-deploy PYTHONPATH=backend/src backend/.venv/bin/python \
        backend/scripts/migrate_config_mail_to_sam.py --write

The pure shaping/equivalence helpers (``shape_config_mail_body`` / ``mail_config_from_body`` /
``mail_configs_equivalent``) carry NO boto3 / MySQL dependency and are unit-tested in
``backend/tests/unit/test_migrate_config_mail_to_sam.py``.
"""

from __future__ import annotations

import argparse
import os
import sys
from typing import Any

_DATA_ACCOUNT = "506221081911"
_TEST_TABLE = "test_governance_projection"
_PROD_TABLE = "governance_projection"


# ──────────────────────────────────────────────────────────────────────────────────────
# Pure shaping / equivalence helpers (no boto3, no MySQL — unit-tested in isolation).
# ──────────────────────────────────────────────────────────────────────────────────────


def shape_config_mail_body(mail_row_attributes: dict) -> dict:
    """Return the SAM ``config#mail`` body from the Flask builder's attributes.

    ``build_config_mail_row`` already produces the EXACT shape the ``MembersProjectionReader``
    mail accessors read back (R1.4): ``mail_enabled`` / ``mail_local_part`` / ``mail_certified``
    always present, with ``mail_domain`` / ``mail_reply_to_default`` / ``consent_notice`` present
    only when authored. Unlike the scope body (a single ``dimensions`` key) there is nothing to
    normalize — this returns a NEW shallow copy of the attributes so the caller can hand it to
    the write repo without aliasing the builder's row. Never mutates the input.
    """
    return dict(mail_row_attributes or {})


def mail_config_from_body(body: dict, tenant_id: str) -> dict:
    """Rebuild the reader's resolved mail view from a ``config#mail`` body (expected value).

    Reconstructs EXACTLY the way the Members edge resolves mail config, by feeding a synthetic
    projected item through the real ``MembersProjectionReader`` on an in-memory table — so "what
    we wrote" and "what the reader resolves" are compared on a level field. Returns a plain dict
    of the reader's six resolved accessors (the comparable projection of the mail row).
    """
    from sam.members.repository.projection_config_reader import MembersProjectionReader

    from services import projection_schema as schema

    item = {
        **(body or {}),
        schema.PARTITION_KEY_ATTR: tenant_id,
        schema.SORT_KEY_ATTR: schema.build_sort_key(
            schema.RECORD_TYPE_CONFIG, schema.CONFIG_ID_MAIL
        ),
    }
    reader = MembersProjectionReader(table=_InMemoryTable([item]))
    return _resolved_mail_view(reader, tenant_id)


def _resolved_mail_view(reader: Any, tenant_id: str) -> dict:
    """Project a reader onto the comparable resolved mail view (the read-back equivalence key).

    These are the SAME six accessors the SAM edge / pre-send resolver consume, so equivalence on
    this view IS read-back equivalence for the mail subset (R1.4 / Req 10.2). ``consent_notice``
    is carried as the reader's resolved ``get_consent_notice`` dict (or ``None``).
    """
    return {
        "mail_enabled": reader.is_mail_enabled(tenant_id),
        "mail_certified": reader.is_mail_certified(tenant_id),
        "mail_domain": reader.get_mail_domain(tenant_id),
        "mail_local_part": reader.get_mail_local_part(tenant_id),
        "mail_reply_to_default": reader.get_mail_reply_to_default(tenant_id),
        "consent_notice": reader.get_consent_notice(tenant_id),
    }


def mail_configs_equivalent(expected: dict, actual: dict) -> bool:
    """Return whether two resolved mail views are equivalent.

    Both are plain dicts of the reader's resolved accessors, so value equality IS the
    equivalence check the read-back verify needs.
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


def _build_mail_body(tenant_id: str, parameter_service: Any) -> dict:
    """Read + shape one tenant's ``config#mail`` body (derived from the members mail params)."""
    from services.projection_sync import build_config_mail_row

    row = build_config_mail_row({"administration": tenant_id}, parameter_service)
    # ``build_config_mail_row`` never returns None for a present tenant (fail-closed row).
    return shape_config_mail_body(dict(row.attributes))


def _mail_plan_summary(body: dict) -> str:
    """A compact per-tenant plan line for the DRY RUN / write log."""
    enabled = bool(body.get("mail_enabled"))
    certified = bool(body.get("mail_certified"))
    domain = body.get("mail_domain") or "(none)"
    local_part = body.get("mail_local_part") or "noreply"
    reply_to = body.get("mail_reply_to_default")
    reply_bit = f" reply_to={reply_to}" if reply_to else ""
    notice_bit = " consent_notice" if body.get("consent_notice") else ""
    return (
        f"enabled={enabled} certified={certified} from={local_part}@{domain}"
        f"{reply_bit}{notice_bit}"
    )


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
        body = _build_mail_body(tenant_id, param_svc)
        print(f"[migrate] {tenant_id}: {_mail_plan_summary(body)}")
        if not write:
            continue

        version = next_write_stamp()
        repo.put_config(
            tenant_id=tenant_id,
            config_id=schema.CONFIG_ID_MAIL,
            attributes=body,
            version=version,
        )
        reader = MembersProjectionReader()
        actual = _resolved_mail_view(reader, tenant_id)
        expected = mail_config_from_body(body, tenant_id)
        if mail_configs_equivalent(expected, actual):
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

    if write:
        print(
            f"[migrate] DONE — {len(tenants)} tenant(s) migrated + read-back verified."
        )
    else:
        print(
            "[migrate] DRY RUN complete. Re-run with --write to perform the migration."
        )
    return 0


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
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    return _migrate(_parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
