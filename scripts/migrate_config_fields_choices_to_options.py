#!/usr/bin/env python3
"""
03a C7 — Small, idempotent, targeted ``choices`` → ``options`` backfill (SAM plane).

Real usage is LIMITED (essentially the one h-dcn ``referral_source`` / ``personal.gender``
row-entry carries bare ``choices``), so this is a SMALL idempotent targeted backfill — NOT a
flag-day, NOT a PITR prod-copy rehearsal. **Fix-forward is an acceptable alternative** (the next
normal ``set_field`` write re-stores the row as ``options``). This script exists so an operator
can run the backfill deterministically and prove the round-trip against the REAL row.

What it does (KIND-AWARE — the C7↔C2/W2 correction)
---------------------------------------------------
For a ``config#fields`` row it enumerates every field/override ENTRY that still carries a bare
``choices`` attribute (vocabulary under the legacy key). What it does with that entry depends on
the field's KIND (classified exactly as the write-edge W1/W2 guards classify it):

- an **INLINE ENUM** field — CONVERT: rewrite the vocabulary to the ONE canonical inline
  ``options`` shape (value-only ``[{"value": v} for v in choices]``) and DROP ``choices``.
- a **SCOPE-BACKED** (W2) or **REFERENCE** (W1) field — DROP, never convert: its vocabulary comes
  from the ``config#scope`` dimension / the live catalog (injected at the C4 read seam), never
  inline, so the legacy ``choices`` AND any stale inline ``options`` are DROPPED (writing inline
  ``options`` here would be rejected by the W1/W2 write-edge guard — the crash this corrects).

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
    "classify_entry_kind",
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
    - ``spec`` — the entry's CURRENTLY STORED spec (the overlay mapping for this entry), carried so
      the live driver can classify the field's KIND (scope-backed / reference / inline enum) the
      SAME way the write-edge guards (W1/W2) do, and so decide CONVERT-vs-DROP without re-reading.
    - ``has_inline_options`` — whether the stored spec already carries a (stale) inline ``options``
      attribute that must be dropped for a scope-backed / reference field.
    """

    map_name: str
    entry_key: str
    field_key: str
    options: list[dict] = field(default_factory=list)
    dropped: int = 0
    spec: Mapping[str, Any] = field(default_factory=dict)
    has_inline_options: bool = False


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
                    spec=dict(spec),
                    has_inline_options="options" in spec,
                )
            )
    return plans


# ── Kind classification (REUSES the service's own W1/W2 classifiers so they never drift) ────

# Kind tokens — the per-entry rewrite strategy.
_KIND_REFERENCE = "reference"  # W1 — catalog-sourced; inline vocabulary DROPPED, never converted
_KIND_SCOPE_BACKED = "scope-backed"  # W2 — dimension-sourced; inline vocabulary DROPPED
_KIND_INLINE_ENUM = "inline-enum"  # the only kind that CONVERTS choices -> inline options


def classify_entry_kind(field_key: str, spec: Mapping[str, Any]) -> str:
    """Classify a planned entry's KIND the SAME way the write-edge guards (W1/W2) do.

    This is the C7↔C2/W2 correction the design review missed: the backfill cannot blindly CONVERT
    every legacy ``choices`` into inline ``options`` — for a REFERENCE field (W1) or a SCOPE-BACKED
    field (W2), inline ``options`` is exactly the payload ``set_field`` REJECTS (its vocabulary
    comes from the live catalog / the ``config#scope`` dimension, injected at the C4 read seam, not
    inline). Converting would make the migration CRASH on the W2/W1 guard (the real h-dcn ``region``
    case). For those kinds the correct behaviour is DROP-not-convert.

    Classification is delegated to :class:`ConfigFieldsCrudService`'s OWN classifiers
    (:meth:`_is_reference_field` / :meth:`_is_scope_backed_field`) — fed the field's STORED spec as
    both the "payload" and the "stored" view (the migration authors no new payload). Reusing the
    service's predicates guarantees the migration's CONVERT-vs-DROP decision can never disagree with
    what the W1/W2 guards would actually do at write time — the two cannot drift.
    """
    from sam.members.domain.config_fields_crud_service import ConfigFieldsCrudService

    # The migration has no authored payload; the stored spec IS the observable kind. Pass it as the
    # empty-payload + stored pair the guards classify from (payload ∪ snapshot — here payload is {}).
    if ConfigFieldsCrudService._is_reference_field(field_key, {}, spec):
        return _KIND_REFERENCE
    if ConfigFieldsCrudService._is_scope_backed_field({}, spec):
        return _KIND_SCOPE_BACKED
    return _KIND_INLINE_ENUM


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

    KIND-AWARE rewrite (the C7↔C2/W2 correction)
    --------------------------------------------
    A legacy ``choices`` entry is NOT uniformly converted to inline ``options`` — the correct
    rewrite depends on the field's KIND (classified by :func:`classify_entry_kind`, which reuses the
    service's OWN W1/W2 classifiers so it can never disagree with the write-edge guards):

    - **INLINE ENUM** (the common case): CONVERT — ``set_field(tenant, key, {"options": [...]})``
      writes the canonical inline ``options`` (an allowed definition attr), then
      ``remove_legacy_choices(tenant, key)`` drops the retired ``choices``. Two scoped Change-Ops.
    - **SCOPE-BACKED** (W2) and **REFERENCE** (W1): DROP, never convert. These fields source their
      vocabulary from the ``config#scope`` dimension / the live catalog (injected at the C4 read
      seam), NOT inline. An inline ``options`` payload is exactly what ``set_field`` REJECTS for
      them (W2/W1) — so a CONVERT would CRASH the migration (the real h-dcn ``region`` case this
      corrects). Instead we DROP the legacy inline vocabulary: ``remove_legacy_choices(tenant, key)``
      drops ``choices`` AND ``remove_inline_options(tenant, key)`` drops any stale inline ``options``
      — both dedicated legacy-removal ops that bypass the W1/W2 guards — so the dimension/catalog
      becomes the SOLE source.

    In every case a SINGLE ``{"options": ..., "choices": None}`` call is impossible (C2 removed
    ``choices`` from the write surface), and NO whole-row replace is issued — each op is a
    version-conditional ``update_item`` on a named path (R3.3 / steering 39).
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
        kind = classify_entry_kind(plan.field_key, plan.spec)
        dry_tag = " [DRY-RUN]" if dry_run else ""

        if kind in (_KIND_SCOPE_BACKED, _KIND_REFERENCE):
            # DROP-not-convert: the vocabulary is sourced from the config#scope dimension (W2) or
            # the live catalog (W1), never inline. Drop both the legacy `choices` and any stale
            # inline `options` so the dimension/catalog is the sole source. An inline `options`
            # payload here would be REJECTED by set_field's W1/W2 guard (the crash this corrects).
            stale_note = " + stale inline options" if plan.has_inline_options else ""
            source = "config#scope" if kind == _KIND_SCOPE_BACKED else "live catalog"
            print(
                f"[{tenant_id}] {plan.map_name}.{plan.entry_key}: {kind} -> dropped inline "
                f"vocabulary (choices{stale_note}); sources from {source}{dry_tag}",
                file=out,
            )
            if dry_run:
                continue
            service.remove_legacy_choices(tenant_id, plan.field_key)
            if plan.has_inline_options:
                service.remove_inline_options(tenant_id, plan.field_key)
            continue

        # INLINE ENUM: the existing CONVERT flow — write canonical inline `options`, drop `choices`.
        drop_note = f" ({plan.dropped} malformed dropped)" if plan.dropped else ""
        print(
            f"[{tenant_id}] {plan.map_name}.{plan.entry_key}: choices -> "
            f"{len(plan.options)} value-only options{drop_note}{dry_tag}",
            file=out,
        )
        if dry_run:
            continue
        # Two scoped Change-Ops: write the canonical options (allowed — `options` is on the write
        # surface), then drop the retired `choices` via the dedicated legacy-removal op. `choices`
        # is OFF the normal write surface (C2), so a single {"options":..., "choices": None} call
        # would be rejected by set_field's attr-surface guard before it could REMOVE.
        service.set_field(
            tenant_id,
            plan.field_key,
            {"options": plan.options},
        )
        service.remove_legacy_choices(tenant_id, plan.field_key)
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
