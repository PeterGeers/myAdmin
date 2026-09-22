#!/usr/bin/env python3
"""verify-member-scope-normalization.py — the R9.5 normalization check (S5d task 2.4).

Verifies that, for a tenant, EVERY distinct member scope-field value is a member of the
scope dimension's canonical value set (no un-normalized values) — the R9.5 first clause.
Exact-match enforcement (R3.5) is only correct if a member's stored value and a granted
value are drawn from ONE canonical vocabulary; a variant spelling (a trailing space,
``"Noord Holland"`` vs ``"Noord-Holland"``) makes an exact filter SILENTLY return nothing.
This check surfaces such a gap (R9.3) so it is VISIBLE rather than an unexplained empty
result — the class of bug hit and fixed in s5c.

Mirrors ``scripts/aws/backfill-hdcn-members.py``: argparse → resolve → read READ-ONLY →
run the PURE core (:func:`sam.members.migration.scope_normalization_verify.
verify_scope_normalization`) → print a report → exit code. It only ever READS the members
table (via the repository's ``list_members``) and the governance projection (for the
dimension's canonical values); it writes NOTHING.

Where the canonical value set comes from
----------------------------------------
The dimension + its canonical ``values`` are resolved from the governance projection's
``config#scope`` row via ``MembersProjectionReader.get_scope_config`` (the SAM-plane read of
the MySQL ``members.scope_dimensions`` source of truth, D4/R5.1). If the projection carries
no scope config for the tenant (empty — e.g. a fresh local table), pass ``--dimension`` to
name the dimension and the check falls back to the in-repo h-dcn reference config
(``HDCN_SCOPE_CONFIG``) for that dimension's canonical values.

Usage (from repo root, WSL)
---------------------------
  # Verify h-dcn's region normalization against real AWS (nonprofit data account, read-only):
  MEMBERS_TABLE=sam-members GOVERNANCE_PROJECTION_TABLE=governance-projection \
      AWS_REGION=eu-west-1 AWS_PROFILE=nonprofit-deploy \
      backend/.venv/bin/python scripts/aws/verify-member-scope-normalization.py \
      --tenant h-dcn

  # Against the local emulator (endpoint set → local DynamoDB, no real AWS):
  MEMBERS_TABLE=sam-members-local GOVERNANCE_PROJECTION_TABLE=governance-projection-local \
      AWS_REGION=eu-west-1 AWS_ENDPOINT_URL_DYNAMODB=http://localhost:8000 \
      backend/.venv/bin/python scripts/aws/verify-member-scope-normalization.py \
      --tenant h-dcn --dimension region

Exit code: 0 = clean (every distinct value is canonical), 1 = an internal error, 2 = a
scope dimension could not be resolved, 3 = un-normalized member value(s) found (R9.3).
"""

from __future__ import annotations

import argparse
import os
import sys

# repo root + backend/src on sys.path so `sam.members...` and its `services.*` dependency
# both import (mirrors backfill-hdcn-members.py + sam/tests path setup).
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)
_BACKEND_SRC = os.path.join(_REPO_ROOT, "backend", "src")
if _BACKEND_SRC not in sys.path:
    sys.path.insert(0, _BACKEND_SRC)

from sam.members.domain.scope_dimensions import HDCN_SCOPE_CONFIG, ScopeDimension
from sam.members.migration.scope_normalization_verify import (
    ScopeNormalizationReport,
    verify_scope_normalization,
)
from sam.members.repository.members_repository import DynamoDbMembersRepository

DEFAULT_REGION = "eu-west-1"


def _resolve_dimension(
    tenant_id: str,
    *,
    dimension_key: str | None,
    reader=None,
) -> ScopeDimension | None:
    """Resolve the scope dimension (+ its canonical values) for ``tenant_id`` (read-only).

    Prefers the governance projection's ``config#scope`` row (D4/R5.1 — the SAM-plane read of
    the MySQL source of truth). Falls back to the in-repo ``HDCN_SCOPE_CONFIG`` reference when
    the projection carries no (matching) dimension, so the check still runs against a local
    table seeded before the projection is populated. Returns ``None`` when no dimension can be
    resolved (the caller exits with a clear message).

    When ``dimension_key`` is given, that specific dimension is selected; otherwise the FIRST
    ENABLED dimension is used (h-dcn has exactly one — ``region``).
    """
    dimensions: tuple[ScopeDimension, ...] = ()
    if reader is None:
        try:
            from sam.members.repository.projection_config_reader import (
                MembersProjectionReader,
            )

            reader = MembersProjectionReader()
        except Exception:  # noqa: BLE001 — projection unavailable → fall back below
            reader = None
    if reader is not None:
        try:
            dimensions = tuple(reader.get_scope_config(tenant_id).enabled())
        except Exception:  # noqa: BLE001 — read failure → fall back to the reference config
            dimensions = ()

    if not dimensions:
        # Fallback: the in-repo reference config (h-dcn's region dimension as DATA).
        dimensions = tuple(d for d in HDCN_SCOPE_CONFIG if d.enabled)

    if dimension_key:
        for dim in dimensions:
            if dim.key == dimension_key:
                return dim
        return None
    return dimensions[0] if dimensions else None


def _print_report(report: ScopeNormalizationReport) -> None:
    """Render the R9.5 normalization report (census + offenders)."""
    print("=" * 68)
    print("Member scope-field normalization check (R9.5)")
    print("=" * 68)
    print(f"  tenant          : {report.tenant_id}")
    print(f"  dimension       : {report.dimension_key}  (field: {report.field_key})")
    print(f"  members scanned : {report.members_scanned}")
    print(f"  canonical set   : {list(report.canonical_values)}")
    print(f"  distinct values : {list(report.distinct_values)}")
    print("-" * 68)
    if report.ok:
        print("  ✅ PASS — every distinct member scope-field value is canonical.")
        print("     (An exact grant filters correctly; no silent empty results.)")
    else:
        print(f"  ❌ FAIL — {len(report.offenders)} un-normalized value(s) (R9.3):")
        for value in report.offenders:
            print(f"       - {value!r}  (no canonical counterpart in the dimension's set)")
        print()
        print("  These member values would SILENTLY match nothing under exact enforcement.")
        print("  Re-normalize the member data (re-run the backfill / member write with the")
        print("  shared scope_canon) so every value lands on a canonical spelling (R9.2).")
    print("=" * 68)


def verify(
    tenant_id: str,
    *,
    region: str,
    dimension_key: str | None = None,
    repo=None,
    reader=None,
) -> int:
    """Read the tenant's members READ-ONLY, run the R9.5 check, print + return an exit code."""
    dimension = _resolve_dimension(tenant_id, dimension_key=dimension_key, reader=reader)
    if dimension is None:
        which = f" {dimension_key!r}" if dimension_key else ""
        print(
            f"ERROR: could not resolve scope dimension{which} for tenant {tenant_id!r} "
            "(no config#scope row and no reference config match). Pass --dimension or seed "
            "the tenant's scope config.",
            file=sys.stderr,
        )
        return 2

    # The repository resolves its table lazily + fail-fast from MEMBERS_TABLE / AWS_REGION
    # (region is threaded through the boto3 resource by env; kept as a CLI knob for parity
    # with the backfill runner). list_members is read-only and tenant-scoped (Property 1).
    repository = repo or DynamoDbMembersRepository()
    members = list(repository.list_members(tenant_id))

    report = verify_scope_normalization(tenant_id, members, dimension)
    _print_report(report)
    return 0 if report.ok else 3


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Verify every distinct member scope-field value is canonical for a tenant "
        "(R9.5). Read-only; exits non-zero when un-normalized values are found.",
    )
    parser.add_argument(
        "--tenant",
        required=True,
        help="The administration (tenant) whose members to check (e.g. 'h-dcn'). REQUIRED — "
        "there is no hardcoded/default tenant (R8, steering 31).",
    )
    parser.add_argument(
        "--dimension",
        default=None,
        help="The scope dimension key to check (e.g. 'region'). Default: the first ENABLED "
        "dimension from the tenant's scope config.",
    )
    parser.add_argument(
        "--region",
        default=os.environ.get("AWS_REGION", DEFAULT_REGION),
        help=f"AWS region (default: env AWS_REGION or {DEFAULT_REGION}).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return verify(
            args.tenant,
            region=args.region,
            dimension_key=args.dimension,
        )
    except Exception as exc:  # noqa: BLE001 — surface any failure to the CLI
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
