#!/usr/bin/env python3
"""seed-hdcn-members-config.py — author h-dcn's members CONFIG in MySQL (onboarding, D18).

Upserts the two tenant members-config parameters from the SINGLE onboarding source
(``scripts/onboarding/members/h-dcn/members_config.json``) into the Flask/MySQL ``parameters``
table via
``ParameterService.set_param`` (an idempotent ``INSERT ... ON DUPLICATE KEY UPDATE``):

  - ``members.scope_dimensions`` — the tenant's region vocabulary (→ projected ``config#scope``)
  - ``members.field_overlay``    — fields / dropdowns / functional groups / gender+status enums
                                   / the ``M00001`` member_number format (→ projected ``config#fields``)

This is CONFIG AUTHORING, **not a backfill** — it writes exactly two rows. It is the scripted
form of rollout-plan steps C.3/C.4 (the alternative is the Tenant-Admin members-config UI).
Writing the params fires ``enqueue_sync`` (via the ParameterService/route layer in the app);
this script only sets the params — run the projection sync (C.11) if needed afterwards.

Dry-run-first + idempotent (mirrors the other onboarding scripts):
  # Dry run (DEFAULT — writes nothing): show current vs desired for each param.
  cd backend && PYTHONPATH=src python ../scripts/onboarding/members/h-dcn/seed-hdcn-members-config.py --tenant h-dcn

  # Apply (upsert both params):
  cd backend && PYTHONPATH=src python ../scripts/onboarding/members/h-dcn/seed-hdcn-members-config.py --tenant h-dcn --apply

PREREQUISITE (rollout C.1): the tenant must have the MEMBERS module ACTIVE — the ``members.*``
parameter namespace is gated to it (``parameter_schema.py``). If ``set_param`` is rejected for
a gated namespace, enable the module first (``tenant_modules`` row), then re-run.

NOTE: this is a Flask/MySQL-plane script (steering 31) — run it with ``backend/src`` on the
path so ``database`` / ``services`` import. It does NOT touch DynamoDB/AWS.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))

# Bootstrap: find the repo root by walking up to a marker (NOT by counting dirname levels —
# Tenant-Onboarding Tooling R4), put it on sys.path, then hand off to the shared onboarding
# `_lib` for repo-root + backend/src setup.
_r = os.path.abspath(__file__)
while _r != os.path.dirname(_r):
    _r = os.path.dirname(_r)
    if os.path.isdir(os.path.join(_r, ".git")) or os.path.isdir(os.path.join(_r, ".kiro")):
        break
if _r not in sys.path:
    sys.path.insert(0, _r)
from scripts.onboarding._lib.paths import (  # noqa: E402
    ensure_backend_src_on_path,
    import_by_path,
)

ensure_backend_src_on_path()

_MEMBERS_NAMESPACE = "members"
_SCOPE_DIMENSIONS_KEY = "scope_dimensions"
_FIELD_OVERLAY_KEY = "field_overlay"


def _load_config_loader():
    """Import the tenant config loader by path (the dashed `h-dcn` dir isn't a package).

    The loader is CO-LOCATED in this same tenant dir (this seed runner is an h-dcn tool living
    beside members_config.json and its loader). Resolved via the shared `_lib`
    ``import_by_path`` (R4.2), not an ad-hoc ``spec_from_file_location``.
    """
    path = os.path.join(_THIS_DIR, "members_config_loader.py")
    return import_by_path("members_config_loader", os.path.abspath(path))


def _diff_line(key: str, current, desired) -> str:
    same = current == desired
    mark = "= (unchanged)" if same else "→ WOULD UPDATE"
    cur = "ABSENT" if current is None else json.dumps(current, ensure_ascii=False)[:80]
    return f"  members.{key}: {mark}\n      current: {cur}\n      desired: {json.dumps(desired, ensure_ascii=False)[:80]}"


def seed(tenant_id: str, *, apply: bool, config_path: str | None, svc=None) -> int:
    """Author the two members-config params (dry-run or apply). Returns a process exit code."""
    loader = _load_config_loader()
    cfg = loader.load_members_config(config_path or loader.DEFAULT_CONFIG_PATH)
    desired_scope = loader.scope_dimensions_param(cfg)
    desired_overlay = loader.field_overlay_param(cfg)

    if svc is None:
        from database import DatabaseManager
        from services.parameter_service import ParameterService

        svc = ParameterService(DatabaseManager(test_mode=False))

    current_scope = svc.get_param(_MEMBERS_NAMESPACE, _SCOPE_DIMENSIONS_KEY, tenant=tenant_id)
    current_overlay = svc.get_param(_MEMBERS_NAMESPACE, _FIELD_OVERLAY_KEY, tenant=tenant_id)

    print("=" * 68)
    print(f"h-dcn members-config seed — tenant={tenant_id!r}  mode={'APPLY' if apply else 'DRY-RUN'}")
    print("=" * 68)
    print(_diff_line(_SCOPE_DIMENSIONS_KEY, current_scope, desired_scope))
    print(_diff_line(_FIELD_OVERLAY_KEY, current_overlay, desired_overlay))
    print("-" * 68)

    if not apply:
        print("DRY-RUN: no writes made. Re-run with --apply to upsert the two params.")
        return 0

    svc.set_param(
        "tenant", tenant_id, _MEMBERS_NAMESPACE, _SCOPE_DIMENSIONS_KEY,
        desired_scope, value_type="json", created_by="seed-hdcn-members-config",
    )
    svc.set_param(
        "tenant", tenant_id, _MEMBERS_NAMESPACE, _FIELD_OVERLAY_KEY,
        desired_overlay, value_type="json", created_by="seed-hdcn-members-config",
    )
    print("APPLIED: upserted members.scope_dimensions + members.field_overlay.")
    print("Next: run the projection sync (rollout C.11) if config#scope/config#fields is stale.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Author h-dcn's members.scope_dimensions + members.field_overlay in MySQL "
        "from the onboarding config file. Dry-run by default; --apply to upsert.",
    )
    parser.add_argument(
        "--tenant",
        required=True,
        help="The administration (tenant) to author the members config for (e.g. 'h-dcn'). "
        "REQUIRED — no hardcoded/default tenant (steering 31).",
    )
    parser.add_argument(
        "--config",
        default=None,
        help="Path to the members-config JSON (default: "
        "scripts/onboarding/members/h-dcn/members_config.json).",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually upsert the two params. Without this the script only prints the diff "
        "(dry-run is the default for safety).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return seed(args.tenant, apply=args.apply, config_path=args.config)
    except Exception as exc:  # noqa: BLE001 — surface any failure to the CLI
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
