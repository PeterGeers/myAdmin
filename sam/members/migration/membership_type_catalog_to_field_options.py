"""
spec 03b Task 7.2 — the membership_type **EXPAND** migration (design "Migration" §
EXPAND→DEPLOY→VERIFY→CONTRACT; Req 6.1a / 6.2).

WHAT THIS DOES
--------------
Folds each tenant's CURRENT ``membershiptype#<code>`` catalog into the ``membership_type``
field's enum ``options`` on that tenant's ``config#fields`` row, and REMOVES the forbidden legacy
``choices`` key wherever it co-exists with ``options`` (including the region/scope field). After
the fold the field's own ``options`` list is the single canonical vocabulary (03a: ``options`` is
the canonical verb; ``choices`` is forbidden on config fields) and member records reference it
directly — no separate catalog read on the runtime path (design BU-1/BU-3).

Fold rule (design "Migration-safety proof", one option per catalog entry):

    each catalog entry ``{type_code, label{nl,en}, active, order}`` →
        an option ``{value: type_code, label, order, allowed: active}``

An ACTIVE catalog entry folds to ``allowed:true`` (offered in the picker); a RETIRED entry
(``active:false``, e.g. h-dcn's ``erelid``) folds to ``allowed:false`` — the grandfather case:
hidden from the picker for new/changed records, but still RESOLVING the reference of the members
who already hold it (so it is never an orphan — Req 3.2 / Property 2). The option ``value`` is the
immutable former ``type_code`` the member record points at.

The ``choices`` removal is INDEPENDENT of membership_type: any field override that carries BOTH a
``choices`` key AND an ``options`` key has the forbidden ``choices`` key dropped (``options`` is
authoritative). This covers ``region`` (live h-dcn carries inline ``choices``+``options``) and any
other field where the residue co-exists. A ``choices`` key with NO ``options`` alongside it is left
untouched here — this migration never DROPS a vocabulary, it only removes the redundant forbidden
copy (03a is the shape that guarantees ``options`` exists; 03b's membership_type fold CREATES the
``options`` for the one field that lacked them).

region is NOT re-folded — its ``options`` already carry the 10 live values (design: region needs no
data migration, only the derive-on-save trigger of Req 4). The migration only strips its forbidden
``choices`` residue.

STORAGE SHAPE (what this operates on)
-------------------------------------
It is a per-tenant ``config#fields`` row. ``membership_type`` is a FIXED field, so its authored
override lives in the row's ``overrides`` map (the STORAGE key — the reader serves it to the
frontend under the wire key ``fixed_overrides``, but at rest it is ``overrides``) under the dotted
key ``membership.membership_type``. The fold writes the option list onto that override entry's
``options``; the choices-removal walks every override entry.

SAFETY — READ THE RUNBOOK FIRST (``membership_type_catalog_to_field_options_RUNBOOK.md``)
-----------------------------------------------------------------------------------------
Exactly like the sibling ``functional_groups_list_to_map.py`` migration, this module is DRY-RUN BY
DEFAULT and DOES NOT touch AWS unless BOTH are true:

  1. ``--apply`` is passed explicitly, AND
  2. ``--i-have-a-restore-point`` is passed explicitly (an affirmation that a PITR restore point /
     on-demand backup was taken FIRST — the script cannot verify this for you).

Without ``--apply`` it only READS (the config#fields row + the catalog rows per tenant) and prints
the planned fold + the resulting option values per tenant (Req 6.2 "LIST the resulting values for
owner verification"). With ``--apply`` but without the restore-point affirmation it REFUSES to
write. **The agent that wrote this file did NOT run it against TEST, PROD, or any real AWS data**
(Task 7.3 runs it on TEST, Task 12 on PROD).

The transform itself (:func:`fold_catalog_into_options`, :func:`strip_forbidden_choices`,
:func:`plan_row_fold`) is PURE and unit-tested
(``sam/tests/test_membership_type_catalog_to_field_options_migration.py``) over the committed REAL
h-dcn fixture — no boto3, so the dangerous bit (the write) is isolated behind the two explicit gates
and the fold is provable offline. After the fold, the Task-7.1 integrity scan
(``scripts/scan_membership_type_integrity.py``) passes over the transformed output.

IDEMPOTENT + RE-RUNNABLE
------------------------
Running it twice is safe: a row whose ``membership_type`` option values already cover every ACTIVE
catalog ``type_code`` (and whose retired entries are already folded to ``allowed:false``) AND which
carries NO forbidden ``choices`` key alongside an ``options`` key is detected
(:func:`row_needs_fold` returns ``False``) and SKIPPED — no write. A re-run after a partial apply
converges without double-writing.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

__all__ = [
    "DOTTED_MEMBERSHIP_TYPE_KEY",
    "CatalogEntry",
    "RowFoldPlan",
    "fold_catalog_into_options",
    "strip_forbidden_choices",
    "merge_folded_options",
    "row_needs_fold",
    "plan_row_fold",
]

#: The dotted override key under which ``membership_type`` lives in the stored ``config#fields``
#: ``overrides`` map (``<group>.<key>`` — a fixed field in the ``membership`` storage bucket). The
#: same key the integrity scan (:data:`scripts.scan_membership_type_integrity.DOTTED_MEMBERSHIP_TYPE_KEY`)
#: resolves options under.
DOTTED_MEMBERSHIP_TYPE_KEY = "membership.membership_type"


# ── Normalised catalog input (the pure core consumes this — no boto3) ─────────────────


@dataclass(frozen=True)
class CatalogEntry:
    """One ``membershiptype#<code>`` catalog entry at fold time (the shape being folded away).

    Mirrors :class:`sam.members.domain.membership_type_catalog.MembershipTypeEntry`'s domain
    attributes — ``type_code`` (the immutable reference key → the option ``value``), the per-
    language ``label``, ``active`` (→ the option's ``allowed``), and presentation ``order``.
    """

    type_code: str
    label: Mapping[str, str] = field(default_factory=dict)
    active: bool = True
    order: int = 0

    @classmethod
    def from_entry(cls, entry: Any) -> "CatalogEntry":
        """Build from a :class:`MembershipTypeEntry` (the repository's resolved catalog row)."""
        return cls(
            type_code=str(getattr(entry, "type_code", "")),
            label=dict(getattr(entry, "label", {}) or {}),
            active=bool(getattr(entry, "active", True)),
            order=int(getattr(entry, "order", 0) or 0),
        )

    @classmethod
    def from_raw(cls, raw: Mapping) -> "CatalogEntry":
        """Build from a plain fixture/stored dict (the unit-test path over the real fixture)."""
        label = raw.get("label") or {}
        try:
            order = int(raw.get("order", 0) or 0)
        except (TypeError, ValueError):
            order = 0
        return cls(
            type_code=str(raw.get("type_code", "")),
            label=dict(label) if isinstance(label, Mapping) else {},
            active=bool(raw.get("active", True)),
            order=order,
        )


# ── The pure transform (no boto3 — unit-testable offline) ─────────────────────────────


def fold_catalog_into_options(catalog: Sequence[CatalogEntry]) -> list[dict]:
    """Fold a tenant's catalog entries into the canonical ``membership_type`` option list.

    One option per catalog entry, ordered by ``(order, value)`` (stable, matching the catalog's
    own ``sort_order_key``):

        ``{value: type_code, label: {…}, order: <order>, allowed: <active>}``

    - ``value`` = the immutable ``type_code`` the member record references.
    - ``label`` = the catalog label carried through verbatim (per-language, value stays neutral).
    - ``order`` = the catalog ``order`` (presentation order preserved).
    - ``allowed`` = the catalog ``active`` flag — a RETIRED (``active:false``) entry folds to
      ``allowed:false`` (grandfathered), an active one to ``allowed:true`` (offered).

    A blank / malformed ``type_code`` is skipped (it could never be a valid reference key). The
    result is deterministic so an idempotent re-run produces the identical list.
    """
    options: list[dict] = []
    seen: set[str] = set()
    for entry in sorted(catalog, key=lambda e: (int(e.order), str(e.type_code))):
        code = (entry.type_code or "").strip()
        if not code or code in seen:
            continue
        seen.add(code)
        options.append(
            {
                "value": code,
                "label": dict(entry.label or {}),
                "order": int(entry.order),
                "allowed": bool(entry.active),
            }
        )
    return options


def merge_folded_options(
    existing: Any, folded: Sequence[Mapping]
) -> list[dict]:
    """Merge freshly-folded options onto whatever the field override already carries.

    The fold is the SOURCE OF TRUTH for every catalog ``value`` (its label/order/allowed), but an
    option authored by the admin that has NO catalog counterpart (a value that only ever lived on
    the field) is PRESERVED — the migration never drops an authored option. Concretely:

    - every folded option is present with its folded ``value/label/order/allowed``;
    - any pre-existing option whose ``value`` is NOT in the fold rides through unchanged, appended
      after the folded set in its original relative order.

    For the membership_type field in live data the override carries NO inline options pre-fold, so
    this is simply the folded list; the merge exists so a RE-RUN (options already present) and a
    partially-authored field converge without data loss, and it keeps the transform total.
    """
    folded_by_value = {str(o.get("value")): dict(o) for o in folded}
    result: list[dict] = [dict(o) for o in folded]
    if isinstance(existing, (list, tuple)):
        for opt in existing:
            if not isinstance(opt, Mapping):
                continue
            value = str(opt.get("value"))
            if value and value not in folded_by_value:
                result.append(dict(opt))
    return result


def strip_forbidden_choices(overrides: Mapping[str, Any]) -> tuple[dict, list[str]]:
    """Return a copy of ``overrides`` with the forbidden ``choices`` key removed where ``options`` co-exists.

    ``options`` is the ONLY canonical representation on a config field (03a); ``choices`` is
    forbidden residue. For EVERY override entry that is a mapping carrying BOTH ``choices`` AND
    ``options``, the ``choices`` key is dropped (``options`` is authoritative and left untouched).
    This covers ``region`` (inline ``choices``+``options`` in live h-dcn) and any other field.

    An entry carrying ``choices`` WITHOUT ``options`` is left untouched — removing it would drop a
    vocabulary the field still relies on; this migration only removes the redundant forbidden copy,
    never a sole source of values.

    Returns ``(new_overrides, dotted_keys_cleaned)`` — the cleaned map plus the list of dotted keys
    whose ``choices`` was removed (for the plan/report). Pure: the input is not mutated.
    """
    new_overrides: dict[str, Any] = {}
    cleaned: list[str] = []
    for dotted, entry in overrides.items():
        if (
            isinstance(entry, Mapping)
            and "choices" in entry
            and "options" in entry
        ):
            new_entry = {k: v for k, v in entry.items() if k != "choices"}
            new_overrides[dotted] = new_entry
            cleaned.append(str(dotted))
        else:
            new_overrides[dotted] = entry
    return new_overrides, cleaned


def _active_codes(catalog: Sequence[CatalogEntry]) -> set[str]:
    return {(e.type_code or "").strip() for e in catalog if e.active and (e.type_code or "").strip()}


def _retired_codes(catalog: Sequence[CatalogEntry]) -> set[str]:
    return {
        (e.type_code or "").strip()
        for e in catalog
        if not e.active and (e.type_code or "").strip()
    }


def row_needs_fold(overrides: Mapping[str, Any], catalog: Sequence[CatalogEntry]) -> bool:
    """Return ``True`` when the row still needs the EXPAND fold and/or a ``choices`` strip.

    A row needs work when ANY of these holds:

    - ANY override entry carries BOTH a forbidden ``choices`` key and an ``options`` key (the
      ``choices`` residue must be stripped — Req 6.1a);
    - an ACTIVE catalog ``type_code`` is NOT yet a ``membership_type`` option ``value`` (the fold
      has not run / is incomplete);
    - a RETIRED catalog ``type_code`` that IS present as an option is not yet ``allowed:false``
      (it must be folded to the grandfather flag);
    - the membership catalog is non-empty but the ``membership_type`` override carries no options
      at all (the pre-fold state).

    A row whose membership_type options already cover every active code, whose retired codes are
    ``allowed:false`` where present, and which carries no forbidden ``choices`` beside ``options``
    returns ``False`` — the idempotent skip.
    """
    # 1. forbidden choices residue anywhere.
    _, cleaned = strip_forbidden_choices(overrides)
    if cleaned:
        return True

    entry = overrides.get(DOTTED_MEMBERSHIP_TYPE_KEY)
    existing_options = (
        entry.get("options") if isinstance(entry, Mapping) else None
    ) or []
    by_value = {
        str(o.get("value")): o
        for o in existing_options
        if isinstance(o, Mapping)
    }

    active = _active_codes(catalog)
    retired = _retired_codes(catalog)

    # 2. catalog present but no options folded yet.
    if (active or retired) and not by_value:
        return True

    # 3. an active code missing from the options.
    if any(code not in by_value for code in active):
        return True

    # 4. a retired code present as an option but not yet allowed:false.
    for code in retired:
        opt = by_value.get(code)
        if opt is not None and bool(opt.get("allowed", True)) is not False:
            return True

    return False


@dataclass(frozen=True)
class RowFoldPlan:
    """The planned fold for one ``config#fields`` row — a pure, printable preview.

    ``changed`` is ``False`` for an already-folded, choices-clean row (idempotent skip).
    ``new_overrides`` is the transformed ``overrides`` map the apply step would write; it is empty
    when ``changed`` is ``False``. ``option_values`` is the resulting membership_type option
    ``(value, allowed)`` list the runner LISTS for owner verification (Req 6.2).
    """

    tenant_id: str
    changed: bool
    option_values: list[tuple[str, bool]] = field(default_factory=list)
    choices_cleaned: list[str] = field(default_factory=list)
    new_overrides: dict = field(default_factory=dict)


def plan_row_fold(
    overrides: Mapping[str, Any],
    catalog: Sequence[CatalogEntry],
    tenant_id: str,
) -> RowFoldPlan:
    """Build the (pure) EXPAND fold plan for one stored ``config#fields`` row's ``overrides`` map.

    Does NOT write — it computes the transformed ``overrides`` so both the dry-run preview and the
    apply step share ONE transform (no drift between "what it says it will do" and "what it does"):

    1. fold the catalog into the ``membership_type`` option list
       (:func:`fold_catalog_into_options`), merged onto any already-authored options
       (:func:`merge_folded_options`) so a re-run / partially-authored field never loses a value;
    2. remove the forbidden ``choices`` key wherever it co-exists with ``options``, across EVERY
       override entry (:func:`strip_forbidden_choices`), including region;
    3. preserve every OTHER override attribute (application_* flags, scope binding, type, etc.)
       verbatim — the fold changes ONLY the membership_type ``options`` + strips ``choices``.

    ``option_values`` is listed from the POST-fold membership_type options for owner verification.
    """
    changed = row_needs_fold(overrides, catalog)

    # Fold the catalog onto the membership_type override entry.
    mt_entry = overrides.get(DOTTED_MEMBERSHIP_TYPE_KEY)
    existing_mt_options = (
        mt_entry.get("options") if isinstance(mt_entry, Mapping) else None
    )
    folded = fold_catalog_into_options(catalog)
    merged_options = merge_folded_options(existing_mt_options, folded)

    # Build the new overrides: start from a deep-ish copy of the existing map.
    new_overrides: dict[str, Any] = {k: v for k, v in overrides.items()}
    if folded or isinstance(mt_entry, Mapping):
        base_entry = dict(mt_entry) if isinstance(mt_entry, Mapping) else {}
        base_entry["options"] = merged_options
        new_overrides[DOTTED_MEMBERSHIP_TYPE_KEY] = base_entry

    # Strip forbidden choices across every entry (membership_type included, now that it has options).
    new_overrides, choices_cleaned = strip_forbidden_choices(new_overrides)

    # The resulting membership_type option (value, allowed) list for the owner-verification listing.
    result_entry = new_overrides.get(DOTTED_MEMBERSHIP_TYPE_KEY)
    result_options = (
        result_entry.get("options") if isinstance(result_entry, Mapping) else None
    ) or []
    option_values = [
        (str(o.get("value")), bool(o.get("allowed", True)))
        for o in result_options
        if isinstance(o, Mapping)
    ]

    if not changed:
        return RowFoldPlan(
            tenant_id=tenant_id,
            changed=False,
            option_values=option_values,
            choices_cleaned=[],
            new_overrides={},
        )

    return RowFoldPlan(
        tenant_id=tenant_id,
        changed=True,
        option_values=option_values,
        choices_cleaned=choices_cleaned,
        new_overrides=new_overrides,
    )


# ── The boto3-backed runner (gated — only reaches AWS under two explicit flags) ───────


def _utc_stamp() -> str:
    return _dt.datetime.now(_dt.UTC).isoformat()


def _scan_config_fields_rows(table, schema):
    """Yield every ``config#fields`` row in the table (owner-run migration scope).

    A one-time migration legitimately crosses tenants (it folds EVERY tenant's row — Req 6.5
    requires covering ALL tenants, not only h-dcn), so it uses a ``scan`` filtered to the
    ``config#fields`` sort key. This is NOT a request-path read (the per-request isolation rule in
    steering 39 is the LIVE path; a gated migration/operator tool is the explicit exception — the
    same pattern the sibling ``functional_groups_list_to_map`` migration and the integrity scan
    use). Paginates so a large table is fully covered.
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


def _backup_row(item: Mapping, *, version_value: str, out) -> None:
    """Emit a backup line for one affected row BEFORE it is written (Req 6.2 "back up every row").

    The catalog is tiny, so the backup is the full stored row serialized to the operator's stdout
    (captured to the runbook's backup log). It is intentionally the WHOLE row so a manual restore
    is a direct ``put_item`` of the printed item; it complements — does not replace — the mandatory
    PITR/on-demand backup the runbook requires (the ``--i-have-a-restore-point`` affirmation).
    """
    import json

    print(
        f"BACKUP {version_value} {json.dumps(item, default=str, sort_keys=True)}",
        file=out,
    )


def run(
    argv: list[str] | None = None,
    *,
    out=None,
    projection_table=None,
    members_repository=None,
) -> int:
    """CLI entry point. DRY-RUN by default; writes ONLY under ``--apply`` + the restore affirmation.

    Returns a process exit code (0 = success / clean preview; non-zero = refused or error).

    TWO-TABLE composition root (the bug this fix closes)
    ----------------------------------------------------
    The ``config#fields`` rows this folds live in the **PROJECTION** table
    (``GOVERNANCE_PROJECTION_TABLE`` → ``get_projection_table_resource``), scanned by
    :func:`_scan_config_fields_rows`. But the ``membershiptype#<code>`` CATALOG lives in the
    **MEMBERS** table (``MEMBERS_TABLE`` → :func:`table_design.get_members_table_resource`), read by
    ``DynamoDbMembersRepository.list_membership_types``. The two are DIFFERENT physical tables and
    MUST be resolved SEPARATELY — injecting the projection table into the repository makes the
    catalog read query the wrong table, find zero rows, and silently SKIP the fold for every tenant.

    Both resolutions stay fail-fast: ``GOVERNANCE_PROJECTION_TABLE`` and ``MEMBERS_TABLE`` each have
    NO default and raise at the first real call. The two injectable params (``projection_table`` /
    ``members_repository``) default to those real fail-fast resolutions — they exist ONLY so the
    composition root is unit-testable (mirroring the sibling migrations' testability); production
    passes neither.
    """
    out = out if out is not None else sys.stdout
    parser = argparse.ArgumentParser(
        description=(
            "spec 03b Task 7.2 EXPAND migration: fold each tenant's membership_type catalog into "
            "the field's enum options and drop the forbidden `choices` key. DRY-RUN by default — "
            "READ THE RUNBOOK (membership_type_catalog_to_field_options_RUNBOOK.md)."
        )
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually WRITE the folded rows. Without this it only previews (reads only).",
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

    # Import boto3 + schema + repository lazily so the pure transform (and its unit tests) never
    # need AWS.
    try:
        from services import projection_schema as schema

        from sam.members.repository import table_design as td
        from sam.members.repository.members_repository import DynamoDbMembersRepository
    except ImportError as exc:  # pragma: no cover - env wiring
        print(f"ERROR: cannot import schema/repository ({exc})", file=sys.stderr)
        return 2

    # HARD GATE: refuse to write without the restore-point affirmation.
    if args.apply and not args.i_have_a_restore_point:
        print(
            "REFUSED: --apply requires --i-have-a-restore-point. Take a PITR restore point / "
            "on-demand backup FIRST and re-run with both flags (see "
            "membership_type_catalog_to_field_options_RUNBOOK.md).",
            file=sys.stderr,
        )
        return 3

    # TWO tables, resolved SEPARATELY (see docstring): the PROJECTION table holds the
    # config#fields rows we scan + write; the MEMBERS table holds the membershiptype# catalog the
    # repository reads. NEVER pass the projection table to the repository — that was the bug
    # (catalog read hit the wrong table, found zero rows, silently skipped every fold).
    table = (
        projection_table
        if projection_table is not None
        else schema.get_projection_table_resource()
    )
    repository = (
        members_repository
        if members_repository is not None
        else DynamoDbMembersRepository(table=td.get_members_table_resource())
    )
    version_value = _utc_stamp()

    mode = "APPLY (writing)" if args.apply else "DRY-RUN (read-only preview)"
    print(f"membership_type catalog -> field options EXPAND migration — {mode}", file=out)
    print(
        f"  table={getattr(table, 'name', '<resolved>')} version_stamp={version_value}",
        file=out,
    )

    planned = 0
    skipped = 0
    written = 0
    for item in _scan_config_fields_rows(table, schema):
        tenant_id = item.get(schema.PARTITION_KEY_ATTR, "<unknown>")
        if args.tenant and tenant_id != args.tenant:
            continue

        overrides = item.get("overrides") or {}
        catalog = [
            CatalogEntry.from_entry(e) for e in repository.list_membership_types(tenant_id)
        ]
        plan = plan_row_fold(overrides, catalog, tenant_id)

        # LIST the resulting membership_type option values per tenant for owner verification (Req 6.2).
        listing = ", ".join(
            f"{v}{'' if allowed else ' (retired)'}" for v, allowed in plan.option_values
        )

        if not plan.changed:
            skipped += 1
            print(
                f"  SKIP   {tenant_id}: options already folded + no forbidden choices "
                f"(idempotent). membership_type options: [{listing}]",
                file=out,
            )
            continue

        planned += 1
        print(
            f"  PLAN   {tenant_id}: fold {len(plan.option_values)} membership_type option(s)"
            f"{'; strip choices on ' + ', '.join(plan.choices_cleaned) if plan.choices_cleaned else ''}",
            file=out,
        )
        print(f"           membership_type options: [{listing}]", file=out)

        if args.apply:
            # Back up the affected row FIRST (Req 6.2), then write the single `overrides` attribute
            # via the sanctioned C6 whole-item put (carry the key + preserve every other attribute).
            _backup_row(item, version_value=version_value, out=out)
            new_item = dict(item)
            new_item["overrides"] = plan.new_overrides
            table.put_item(Item=new_item)
            written += 1

    print(
        f"done — planned={planned} skipped(idempotent)={skipped} "
        f"written={written if args.apply else 0}",
        file=out,
    )
    if not args.apply and planned:
        print(
            "DRY-RUN only: no rows written. Re-run with --apply --i-have-a-restore-point to fold "
            "(after the runbook's PITR/backup + TEST verify, then the integrity scan).",
            file=out,
        )
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI shim
    raise SystemExit(run())
