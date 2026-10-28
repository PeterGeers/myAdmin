#!/usr/bin/env python3
"""
03a C7 — Small, idempotent, targeted ``choices`` → ``options`` backfill (SAM plane).

Real usage is LIMITED (essentially the one h-dcn ``referral_source`` / ``personal.gender``
row-entry carries bare ``choices``), so this is a SMALL idempotent targeted backfill — NOT a
flag-day, NOT a PITR prod-copy rehearsal. **Fix-forward is an acceptable alternative** (the next
normal ``set_field`` write re-stores the row as ``options``). This script exists so an operator
can run the backfill deterministically and prove the round-trip against the REAL row.

What it does
------------
For a ``config#fields`` row it enumerates every field/override ENTRY that still carries a bare
``choices`` attribute (vocabulary under the legacy key, ``options`` absent). For each such entry
it rewrites the vocabulary to the ONE canonical ``options`` shape — value-only
``[{"value": v} for v in choices]`` — and DROPS ``choices`` in the SAME change.

The one vocabulary model (design 03a): every selectable field resolves to ONE canonical
``options`` list; ``choices`` is retired. This backfill moves the few live legacy rows onto that
model BEFORE the C8 guard flips to BLOCKING (task 12), so no live bare-``choices`` row trips it.

How the write happens — the Change-Op contract (steering 39, R3.3)
------------------------------------------------------------------
The rewrite goes through :class:`ConfigFieldsCrudService.set_field`, which emits a Change-Op set
addressing ONE domain identity: ``SET <map>.<key>.options = [...]`` + ``REMOVE <map>.<key>.choices``.
Those are issued as a SINGLE version-conditional ``update_item`` on named paths — NEVER a
whole-row ``put_item`` replace. DynamoDB leaves every attribute the ops do not name physically
untouched, so a sibling entry / slice survives by construction.

Idempotence
-----------
Enumeration only selects entries that STILL carry ``choices``. Once an entry has ``options`` and
no ``choices``, a re-run selects nothing for it — a no-op. Re-running the whole script after a
successful migration plans zero ops.

``choices`` value shapes
------------------------
A legacy ``choices`` list carries EITHER bare strings (``["man", "vrouw"]``) OR rich dicts
(``[{"value": "man", "label": {...}}]`` — the real h-dcn ``personal.gender`` shape). Both reduce
to the SAME value-only ``options`` here: the per-entry value is the string itself, or the dict's
``value`` key. A malformed entry (a dict with no ``value``, or an empty/blank string) is DROPPED
with a warning rather than fabricating a value — the migration never invents vocabulary.

Layering
--------
This is an operator script, not product code: it is allowed to construct the boto3-backed
reader/writer (the composition root a one-shot migration would otherwise get from ``app.py``).
The reader/writer/service themselves keep the storage shape and the Change-Op mechanics inside
the repository layer (steering 39); this script only wires them and drives the per-entry intent.
The pure planning core (:func:`plan_choices_to_options`) is storage-agnostic and unit-tested
without any live system.
"""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

# ── Path bootstrap (repo root + backend/src) so ``sam.*`` / ``services.*`` import when the
#    script is run directly, mirroring the SAM tests' bootstrap. ─────────────────────────────
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)
_BACKEND_SRC = os.path.join(_REPO_ROOT, "backend", "src")
if _BACKEND_SRC not in sys.path:
    sys.path.insert(0, _BACKEND_SRC)

__all__ = [
    "EntryPlan",
    "options_from_choices",
    "plan_choices_to_options",
    "migrate_tenant",
    "main",
]


# ── The pure planning core (no boto3, no DynamoDB — unit-testable in isolation) ─────────────


def options_from_choices(choices: Any) -> list[dict]:
    """Reduce a legacy ``choices`` value to value-only canonical ``options``.

    Accepts the two authored legacy shapes and reduces BOTH to ``[{"value": v}, ...]``:

    - a BARE string entry ``"man"`` → ``{"value": "man"}``;
    - a RICH dict entry ``{"value": "man", "label": {...}}`` → ``{"value": "man"}`` (value-only —
      C7 rewrites to the minimal canonical shape; a richer label is not fabricated or carried, it
      is the next authoring write's job to enrich if desired).

    A malformed entry is DROPPED (never fabricated into a value): a dict with no ``value`` key, an
    empty/whitespace bare string, or a non-str/non-dict entry. A non-list ``choices`` yields an
    empty plan (nothing to migrate). The result preserves ORDER and de-duplicates nothing (the
    duplicate-value guard is a write-surface concern, C3 — this backfill faithfully reproduces the
    stored vocabulary's values).
    """
    if not isinstance(choices, Sequence) or isinstance(choices, (str, bytes)):
        return []
    options: list[dict] = []
    for entry in choices:
        if isinstance(entry, str):
            value = entry.strip()
            if value:
                options.append({"value": value})
            continue
        if isinstance(entry, Mapping) and "value" in entry:
            raw = entry["value"]
            value = str(raw).strip() if raw is not None else ""
            if value:
                options.append({"value": value})
            continue
        # non-str / non-dict / dict-without-value → dropped (never fabricate a value)
    return options


@dataclass(frozen=True)
class EntryPlan:
    """A single entry's planned ``choices`` → ``options`` rewrite.

    - ``map_name`` / ``entry_key`` — the storage placement of the entry (``fields`` + bare key, or
      ``overrides`` + dotted ``<group>.<key>``). Used only for reporting here; the Change-Op
      service re-derives placement from the identity it is handed.
    - ``field_key`` — the domain identity passed to ``set_field`` (the dotted override key for an
      override, the bare key for a variable field — both accepted by the service's registry lookup).
    - ``options`` — the value-only canonical ``options`` the entry's ``choices`` reduced to.
    - ``dropped`` — how many malformed ``choices`` entries were dropped (surfaced in the report).
    """

    map_name: str
    entry_key: str
    field_key: str
    options: list[dict] = field(default_factory=list)
    dropped: int = 0


def plan_choices_to_options(overlay: Mapping[str, Any]) -> list[EntryPlan]:
    """Enumerate the entries in a stored ``config#fields`` overlay that still carry bare ``choices``.

    ``overlay`` is the stored row's ``{fields, overrides, functional_groups, ...}`` shape (the
    at-rest shape — ``overrides`` is the storage key, not the wire ``fixed_overrides``). This
    function is the IDEMPOTENCE pivot: it selects ONLY entries where ``choices`` is present. An
    entry that already has ``options`` and no ``choices`` is not planned, so a re-run plans nothing
    for it. An entry that has BOTH ``choices`` and ``options`` is STILL planned (the legacy
    ``choices`` must be dropped to reach the one-vocabulary model); its ``options`` is rebuilt from
    the ``choices`` values so the migration is deterministic and the stale ``choices`` cannot win a
    later read.

    Returns one :class:`EntryPlan` per entry to rewrite, in a stable (map, then key) order. An
    entry whose ``choices`` reduces to ZERO usable values is still planned (so the stale ``choices``
    is dropped), with an empty ``options`` and the dropped count recorded — the write then clears
    ``choices`` and sets an empty ``options``, which the C6 fail-loud boundary will later surface if
    the field still declares a source. (A zero-value legacy ``choices`` is already broken data.)
    """
    plans: list[EntryPlan] = []
    for map_name in ("fields", "overrides"):
        container = overlay.get(map_name)
        if not isinstance(container, Mapping):
            continue
        for entry_key in sorted(container):
            spec = container[entry_key]
            if not isinstance(spec, Mapping) or "choices" not in spec:
                continue
            choices = spec.get("choices")
            options = options_from_choices(choices)
            raw_count = (
                len(choices)
                if isinstance(choices, Sequence) and not isinstance(choices, (str, bytes))
                else 0
            )
            plans.append(
                EntryPlan(
                    map_name=map_name,
                    entry_key=entry_key,
                    field_key=entry_key,
                    options=options,
                    dropped=max(0, raw_count - len(options)),
                )
            )
    return plans


# ── The live driver (wires the reader/writer/service and applies the plan) ──────────────────


def migrate_tenant(
    tenant_id: str,
    *,
    service,
    reader,
    dry_run: bool = False,
    out=None,
) -> list[EntryPlan]:
    """Read a tenant's ``config#fields`` row, plan the ``choices`` → ``options`` rewrites, and
    (unless ``dry_run``) apply each through the Change-Op ``set_field`` path.

    ``service`` is a :class:`ConfigFieldsCrudService`; ``reader`` exposes
    ``get_raw_fields_overlay(tenant_id, *, consistent_read=True)`` returning the stored overlay.
    The read is STRONGLY-CONSISTENT so the plan sees the current row. Returns the plans (so a
    caller / test can assert what was migrated). Idempotent: a tenant whose rows already carry
    ``options`` and no ``choices`` plans and applies nothing.

    Each apply is ``set_field(tenant_id, field_key, {"options": [...], "choices": None})`` — the
    service emits ``SET ...options`` + ``REMOVE ...choices`` as ONE version-conditional
    ``update_item`` (no whole-row replace, R3.3 / steering 39).
    """
    out = out if out is not None else sys.stdout
    # The reader serves the storage ``overrides`` map under the wire key ``fixed_overrides``; map
    # it back to the at-rest shape the pure planner enumerates so the two stay aligned.
    wire = reader.get_raw_fields_overlay(tenant_id, consistent_read=True)
    overlay = {
        "fields": wire.get("fields") or {},
        "overrides": wire.get("fixed_overrides") or {},
    }
    plans = plan_choices_to_options(overlay)

    if not plans:
        print(f"[{tenant_id}] no bare-`choices` entries — nothing to migrate (no-op).", file=out)
        return plans

    for plan in plans:
        drop_note = f" ({plan.dropped} malformed dropped)" if plan.dropped else ""
        print(
            f"[{tenant_id}] {plan.map_name}.{plan.entry_key}: choices -> "
            f"{len(plan.options)} value-only options{drop_note}"
            + (" [DRY-RUN]" if dry_run else ""),
            file=out,
        )
        if dry_run:
            continue
        service.set_field(
            tenant_id,
            plan.field_key,
            {"options": plan.options, "choices": None},
        )
    return plans


def _build_service_and_reader(table=None):
    """Compose the boto3-backed reader + Change-Op writer + CRUD service for a live run.

    This is the one-shot migration's composition root (what ``app.py`` would otherwise provide).
    The table resolves fail-fast from ``GOVERNANCE_PROJECTION_TABLE`` inside the repositories; a
    ``table`` may be injected (tests / a local-DynamoDB run).
    """
    from sam.members.domain.config_fields_crud_service import ConfigFieldsCrudService
    from sam.members.repository.projection_config_reader import MembersProjectionReader
    from sam.members.repository.projection_config_write_repository import (
        MembersConfigWriteRepository,
    )

    reader = MembersProjectionReader(table=table)
    writer = MembersConfigWriteRepository(table=table)
    service = ConfigFieldsCrudService(writer, reader=reader)
    return service, reader


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "03a C7 backfill: rewrite bare `choices` to value-only `options` on a tenant's "
            "config#fields row via the Change-Op path (idempotent, no whole-row replace)."
        )
    )
    parser.add_argument(
        "tenant_id",
        help="The tenant whose config#fields row to migrate (e.g. h-dcn).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Plan and print the rewrites without writing anything.",
    )
    args = parser.parse_args(argv)

    service, reader = _build_service_and_reader()
    plans = migrate_tenant(
        args.tenant_id, service=service, reader=reader, dry_run=args.dry_run
    )
    migrated = 0 if args.dry_run else len(plans)
    print(
        f"[{args.tenant_id}] done — {len(plans)} entr"
        f"{'y' if len(plans) == 1 else 'ies'} planned, {migrated} written.",
    )
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entrypoint
    raise SystemExit(main())
