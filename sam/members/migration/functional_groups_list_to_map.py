"""
spec 03 Task 2.0 — one-time per-tenant **`functional_groups` LIST → MAP migration** (design C6 /
D2a, design-review Q3a/Q11).

WHAT THIS DOES
--------------
Converts each tenant's stored ``config#fields`` ``functional_groups`` attribute from the legacy
ordered LIST ``[{key, label, order}, …]`` to the new MAP keyed by group key
``{key: {key, label, order}, …}``, and backfills the row skeleton (``fields`` / ``overrides`` /
``functional_groups`` parent maps) + a ``version`` stamp where absent (C6). This is the storage
change that makes the catalog truncation STRUCTURALLY impossible: after it, group writes are a
per-path ``update_item`` on ``functional_groups.<gkey>`` (Phase 2) and a partial payload can no
longer drop unlisted groups.

IT IS A **WHOLE-ROW WRITE** (``put_item``) — the one sanctioned use of the whole-row primitive
(C6) — so it is the EXACT class of operation this spec otherwise forbids on the runtime path. That
is why it is a GATED, OWNER-RUN, one-time migration, not part of the request path.

SAFETY — READ THE RUNBOOK FIRST (``functional_groups_list_to_map_RUNBOOK.md``)
------------------------------------------------------------------------------
This module is DRY-RUN BY DEFAULT and DOES NOT touch AWS unless BOTH are true:

  1. ``--apply`` is passed explicitly, AND
  2. ``--i-have-a-restore-point`` is passed explicitly (an affirmation that a PITR restore point /
     on-demand backup was taken FIRST — the script cannot verify this for you).

Without ``--apply`` it only READS (a Query per tenant) and prints the planned conversion — safe to
run against any environment to preview. With ``--apply`` but without the restore-point
affirmation it REFUSES to write. The owner runs the real migration against a COPY of PROD first,
verifies with the invariant harness, then against PROD — per the runbook. **The agent that wrote
this file did NOT run it against PROD or any real AWS data.**

The transform itself (:func:`convert_functional_groups`, :func:`plan_row_migration`) is PURE and
unit-tested (``sam/tests/test_functional_groups_list_to_map_migration.py``) — no boto3, so the
dangerous bit (the write) is isolated behind the two explicit gates and the transform is provable
offline.

IDEMPOTENT
----------
Running it twice is safe: a row already in MAP shape is detected (:func:`needs_migration` returns
``False``) and SKIPPED — no write, no version bump. So a re-run after a partial/interrupted apply
converges without double-writing.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import sys
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

__all__ = [
    "RowMigrationPlan",
    "convert_functional_groups",
    "needs_migration",
    "plan_row_migration",
]


# ── The pure transform (no boto3 — unit-testable offline) ─────────────────────────────


def convert_functional_groups(raw: Any) -> dict:
    """Convert a stored ``functional_groups`` attribute to the canonical MAP keyed by group key.

    Mirrors the reader's dual-read normalizer
    (:func:`sam.members.repository.projection_config_reader._normalize_functional_groups`) EXACTLY
    so the migrated-at-rest shape is byte-identical to what the reader already serves — the
    migration can never produce a row the reader would read differently:

    - a **LIST** ``[{key, …}, …]`` → ``{key: {key, …}}`` (each entry re-keyed by its own ``key``;
      ``order`` / ``label`` ride through verbatim — ``order`` is already in the entry, Q3a).
      Keyless / non-mapping entries are dropped (they were unreadable before too).
    - a **MAP** ``{gkey: {…}}`` → normalized copy (each entry gets its own ``key`` filled in from
      the map key when absent). Already-migrated input is returned equivalent to itself (idempotent).
    - anything else (``None`` / missing / wrong type) → ``{}`` (empty-is-valid).
    """
    if isinstance(raw, Mapping):
        out: dict = {}
        for gkey, entry in raw.items():
            if not isinstance(entry, Mapping) or not gkey:
                continue
            normalized = dict(entry)
            normalized.setdefault("key", str(gkey))
            out[str(normalized.get("key") or gkey)] = normalized
        return out
    if isinstance(raw, (list, tuple)):
        out = {}
        for entry in raw:
            if not isinstance(entry, Mapping):
                continue
            key = entry.get("key")
            if not key:
                continue
            out[str(key)] = dict(entry)
        return out
    return {}


def needs_migration(row: Mapping[str, Any]) -> bool:
    """Return ``True`` when the row still needs the LIST→MAP migration (or a skeleton/version backfill).

    A row needs migrating when ANY of these holds:
    - ``functional_groups`` is a LIST (the legacy shape) — the primary trigger;
    - a parent-map skeleton attribute (``fields`` / ``overrides`` / ``functional_groups``) is
      absent or not a map (C6 requires all three to exist for the Phase-2 path ``update_item``);
    - the ``version`` attribute is absent (C6 backfill so the version-conditional write's
      ``attribute_not_exists(version)`` branch is the rare case, not the norm).

    A row whose ``functional_groups`` is already a MAP AND has the full skeleton AND a ``version``
    returns ``False`` — idempotent skip.
    """
    groups = row.get("functional_groups")
    if isinstance(groups, (list, tuple)):
        return True
    for parent in ("fields", "overrides", "functional_groups"):
        if not isinstance(row.get(parent), Mapping):
            return True
    if "version" not in row:
        return True
    return False


@dataclass(frozen=True)
class RowMigrationPlan:
    """The planned migration for one ``config#fields`` row — a pure, printable preview.

    ``changed`` is ``False`` for an already-migrated row (idempotent skip). ``new_attributes`` is
    the attribute delta the apply step would ``put_item`` (the full row minus key, with the
    converted groups + backfilled skeleton + version); it is empty when ``changed`` is ``False``.
    """

    tenant_id: str
    changed: bool
    before_group_shape: str
    after_group_count: int
    version_backfilled: bool
    skeleton_backfilled: bool
    new_attributes: dict = field(default_factory=dict)


def plan_row_migration(
    row: Mapping[str, Any],
    tenant_id: str,
    *,
    key_attrs: tuple[str, str],
    version_attr: str,
    version_value: str,
) -> RowMigrationPlan:
    """Build the (pure) migration plan for one stored ``config#fields`` row.

    Does NOT write — it computes the converted attribute body so both the dry-run preview and the
    apply step share ONE transform (no drift between "what it says it will do" and "what it does").

    - converts ``functional_groups`` LIST→MAP (:func:`convert_functional_groups`);
    - backfills the ``{fields, overrides, functional_groups}`` skeleton where a parent map is
      absent (C6);
    - backfills ``version`` when absent (C6);
    - preserves every OTHER attribute verbatim (slug / publish-state / default_page_size / etc.) —
      the migration changes ONLY the groups shape + skeleton + version, nothing else.

    ``key_attrs`` is ``(partition_key_attr, sort_key_attr)`` whose values are carried through on the
    written item; they are excluded from the diff-able ``new_attributes`` body only for printing.
    """
    changed = needs_migration(row)
    pk_attr, sk_attr = key_attrs
    before_shape = (
        "list"
        if isinstance(row.get("functional_groups"), (list, tuple))
        else "map"
        if isinstance(row.get("functional_groups"), Mapping)
        else "absent"
    )

    if not changed:
        return RowMigrationPlan(
            tenant_id=tenant_id,
            changed=False,
            before_group_shape=before_shape,
            after_group_count=len(row.get("functional_groups") or {}),
            version_backfilled=False,
            skeleton_backfilled=False,
            new_attributes={},
        )

    # Start from the full stored row so every unrelated attribute is preserved verbatim.
    new_row = dict(row)

    converted_groups = convert_functional_groups(row.get("functional_groups"))
    new_row["functional_groups"] = converted_groups

    skeleton_backfilled = False
    for parent in ("fields", "overrides"):
        if not isinstance(new_row.get(parent), Mapping):
            new_row[parent] = {}
            skeleton_backfilled = True

    version_backfilled = version_attr not in new_row
    if version_backfilled:
        new_row[version_attr] = version_value

    # The write carries the key too; exclude it from the printable body (it is unchanged).
    new_attributes = {k: v for k, v in new_row.items() if k not in (pk_attr, sk_attr)}

    return RowMigrationPlan(
        tenant_id=tenant_id,
        changed=True,
        before_group_shape=before_shape,
        after_group_count=len(converted_groups),
        version_backfilled=version_backfilled,
        skeleton_backfilled=skeleton_backfilled,
        new_attributes=new_attributes,
    )


# ── The boto3-backed runner (gated — only reaches AWS under two explicit flags) ───────


def _utc_stamp() -> str:
    return _dt.datetime.now(_dt.UTC).isoformat()


def _scan_config_fields_rows(table, schema):
    """Yield every ``config#fields`` row in the table (owner-run migration scope).

    A one-time migration legitimately crosses tenants (it converts EVERY tenant's row), so it
    uses a ``scan`` filtered to the ``config#fields`` sort key — this is NOT a request-path read
    (the per-request isolation rule in steering 39 is about the LIVE path; a gated migration tool
    is the explicit exception). Paginates so a large table is fully covered.
    """
    sk_value = schema.build_sort_key(schema.RECORD_TYPE_CONFIG, schema.CONFIG_ID_FIELDS)
    kwargs = {
        "FilterExpression": "#sk = :sk",
        "ExpressionAttributeNames": {"#sk": schema.SORT_KEY_ATTR},
        "ExpressionAttributeValues": {":sk": sk_value},
    }
    while True:
        resp = table.scan(**kwargs)
        yield from resp.get("Items", []) or []
        start_key = resp.get("LastEvaluatedKey")
        if not start_key:
            return
        kwargs["ExclusiveStartKey"] = start_key


def run(argv: list[str] | None = None) -> int:
    """CLI entry point. DRY-RUN by default; writes ONLY under ``--apply`` + the restore affirmation.

    Returns a process exit code (0 = success / clean preview; non-zero = refused or error).
    """
    parser = argparse.ArgumentParser(
        description=(
            "One-time per-tenant config#fields functional_groups LIST->MAP migration "
            "(spec 03 Task 2.0, design C6). DRY-RUN by default — READ THE RUNBOOK."
        )
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually WRITE the converted rows (whole-row put_item). Without this it only previews.",
    )
    parser.add_argument(
        "--i-have-a-restore-point",
        action="store_true",
        help=(
            "Affirm a PITR restore point / on-demand backup was taken FIRST. REQUIRED with "
            "--apply; the script cannot verify it for you and refuses to write without it."
        ),
    )
    parser.add_argument(
        "--tenant",
        default=None,
        help="Limit to a single tenant_id (default: every tenant's config#fields row).",
    )
    args = parser.parse_args(argv)

    # Import boto3 + schema lazily so the pure transform (and its unit tests) never need AWS.
    try:
        from services import projection_schema as schema
    except ImportError as exc:  # pragma: no cover - env wiring
        print(f"ERROR: cannot import projection_schema ({exc})", file=sys.stderr)
        return 2

    # HARD GATE: refuse to write without the restore-point affirmation.
    if args.apply and not args.i_have_a_restore_point:
        print(
            "REFUSED: --apply requires --i-have-a-restore-point. Take a PITR restore point / "
            "on-demand backup FIRST and re-run with both flags (see "
            "functional_groups_list_to_map_RUNBOOK.md).",
            file=sys.stderr,
        )
        return 3

    table = schema.get_projection_table_resource()
    version_value = _utc_stamp()
    key_attrs = (schema.PARTITION_KEY_ATTR, schema.SORT_KEY_ATTR)

    mode = "APPLY (writing)" if args.apply else "DRY-RUN (read-only preview)"
    print(f"functional_groups LIST->MAP migration — {mode}")
    print(f"  table={getattr(table, 'name', '<resolved>')} version_stamp={version_value}")

    planned = 0
    skipped = 0
    written = 0
    for item in _scan_config_fields_rows(table, schema):
        tenant_id = item.get(schema.PARTITION_KEY_ATTR, "<unknown>")
        if args.tenant and tenant_id != args.tenant:
            continue
        plan = plan_row_migration(
            item,
            tenant_id,
            key_attrs=key_attrs,
            version_attr=schema.VERSION_ATTR,
            version_value=version_value,
        )
        if not plan.changed:
            skipped += 1
            print(f"  SKIP   {tenant_id}: already MAP + skeleton + version (idempotent)")
            continue
        planned += 1
        print(
            f"  PLAN   {tenant_id}: groups {plan.before_group_shape} -> map "
            f"({plan.after_group_count} groups)"
            f"{' +skeleton' if plan.skeleton_backfilled else ''}"
            f"{' +version' if plan.version_backfilled else ''}"
        )
        if args.apply:
            # The one sanctioned whole-row write (C6). Carry the key back onto the item.
            new_item = dict(plan.new_attributes)
            new_item[schema.PARTITION_KEY_ATTR] = item[schema.PARTITION_KEY_ATTR]
            new_item[schema.SORT_KEY_ATTR] = item[schema.SORT_KEY_ATTR]
            table.put_item(Item=new_item)
            written += 1

    print(
        f"done — planned={planned} skipped(idempotent)={skipped} "
        f"written={written if args.apply else 0}"
    )
    if not args.apply and planned:
        print(
            "DRY-RUN only: no rows written. Re-run with --apply --i-have-a-restore-point "
            "to migrate (after the runbook's PITR/backup + PROD-copy verify)."
        )
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI shim
    raise SystemExit(run())
