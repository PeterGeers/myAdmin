"""
S5 Task 4.2 — the h-dcn **Lidmaatschap Beheer** catalog seed DATA + a pure planner (R2.4,
R4.1 Rung 1 — config/data; design C8; "generic core stays tenant-agnostic", Property 5).

The Lidmaatschap Beheer catalog is a tenant-scoped, empty-by-default managed catalog of
membership types (design C8). The generic module core ships it EMPTY and tenant-agnostic —
there is **no** ``if tenant == "h-dcn"`` anywhere in the core. h-dcn's own membership types
(Erelid / Donateur / Sponsor / Gewoon lid) are **tenant DATA**, seeded here exactly like the
field overlay (task 1.2), the scope config (task 1.3), and the member backfill (task 4.1).
This module is the one legitimate place the pilot literal ``"h-dcn"`` and h-dcn's type values
live — it is seed data, not engine logic.

Two concerns are split so the seed set is unit-testable without any live system:

1. **The seed DATA** — :data:`HDCN_MEMBERSHIP_TYPES`, an importable tuple of
   :class:`MembershipTypeEntry` (``tenant_id="h-dcn"``, ``active=True``, real nl/en labels,
   sensible ``order``). Reusable + assertable; lives in the migration module, NOT the domain
   core.

2. **A pure planner** — :func:`build_seed_plan` diffs the seed set against what a repository
   already holds (via ``list_membership_types``) and returns a :class:`CatalogSeedPlan`
   classifying each entry as *create* / *update* / *unchanged*. It performs NO writes; the
   runner renders it (dry-run) or applies it via ``save_membership_type``.

**Single source of truth for the ``type_code`` set.** The member backfill (task 4.1) maps
h-dcn's free-text type labels to catalog codes via
:class:`sam.members.migration.hdcn_backfill.MembershipTypeMapper` (its
``DEFAULT_ALIASES``). This module **derives its expected code set from that same mapper**
(:data:`BACKFILL_EMITTABLE_CODES`) and asserts, at import time, that the seed set covers
every code the backfill can emit — so a backfilled member can never reference a membership
type that was not seeded (design C8 referential integrity), and the two files cannot diverge.

Soft-delete semantics (C8): seeding sets ``active=True``. Retiring a type later is
``active=False`` (task 5.3 / a management action) — never a hard delete. This module never
deactivates or deletes; a re-seed is an idempotent upsert.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Mapping, Optional, Sequence

from sam.members.domain.membership_type_catalog import MembershipTypeEntry
from sam.members.migration.hdcn_backfill import HDCN_TENANT_ID, MembershipTypeMapper

__all__ = [
    "HDCN_TENANT_ID",
    "HDCN_MEMBERSHIP_TYPES",
    "BACKFILL_EMITTABLE_CODES",
    "CatalogSeedPlan",
    "SeedItem",
    "build_seed_plan",
]


#: Every catalog ``type_code`` the task-4.1 backfill can emit — derived from the SAME mapper
#: the backfill uses (single source of truth), so the seed and the backfill cannot diverge.
#: The backfill maps its known labels through ``DEFAULT_ALIASES`` (Erelid→``erelid``,
#: Donateur→``donateur``, Sponsor→``sponsor``, "Gewoon lid"→``gewoon_lid``); any other label
#: is normalized on the fly, but the *known* h-dcn vocabulary is exactly this set. The seed
#: MUST cover all of these (asserted at import), so no backfilled member references a missing
#: (or inactive) type.
BACKFILL_EMITTABLE_CODES: frozenset[str] = frozenset(
    MembershipTypeMapper.DEFAULT_ALIASES.values()
)


def _hdcn_entry(type_code: str, nl: str, en: str, order: int) -> MembershipTypeEntry:
    """Build one active h-dcn catalog entry (stamped with the pilot tenant)."""
    return MembershipTypeEntry(
        tenant_id=HDCN_TENANT_ID,
        type_code=type_code,
        label={"nl": nl, "en": en},
        active=True,
        order=order,
    )


#: h-dcn's Lidmaatschap Beheer catalog, as tenant DATA (design C8). The ``type_code``s are the
#: references the backfill maps to and the member record stores; they MUST equal the codes the
#: 4.1 mapper emits (asserted below). Labels are the real Dutch names with English
#: translations; ``order`` is the dropdown/presentation order (ascending). All ``active=True``
#: — retiring a type later is a soft-delete (``active=False``), not part of this seed.
HDCN_MEMBERSHIP_TYPES: tuple[MembershipTypeEntry, ...] = (
    _hdcn_entry("gewoon_lid", "Gewoon lid", "Regular member", 10),
    _hdcn_entry("gezins_lid", "Gezinslid", "Family member", 15),
    _hdcn_entry("erelid", "Erelid", "Honorary member", 20),
    _hdcn_entry("donateur", "Donateur", "Donor", 30),
    _hdcn_entry("gezins_donateur", "Gezinsdonateur", "Family donor", 35),
    _hdcn_entry("sponsor", "Sponsor", "Sponsor", 40),
    # A.4: "Overig" (Other) — the catch-all membership type. Admin-gated at the option level
    # (ONBOARDING §4 bucket 3); seeded here so a backfilled member mapped to `overig` resolves.
    _hdcn_entry("overig", "Overig", "Other", 50),
)


def _validate_seed_set() -> None:
    """Fail LOUD at import if the seed set is malformed or drifts from the backfill mapping.

    Guards three invariants so a bad edit can never ship silently:
    - every seeded entry is a well-formed, active, ``h-dcn``-owned catalog entry;
    - ``type_code``s are unique within the seed set (no duplicate catalog id);
    - the seed COVERS every code the 4.1 backfill can emit — a backfilled member can therefore
      never reference an unseeded type (C8 referential integrity, single source of truth).
    """
    seen: set[str] = set()
    for entry in HDCN_MEMBERSHIP_TYPES:
        entry.validate()  # shape (non-blank tenant/code, nl label, integer order)
        if entry.tenant_id != HDCN_TENANT_ID:
            raise AssertionError(
                f"seed entry {entry.type_code!r} is not owned by {HDCN_TENANT_ID!r}"
            )
        if not entry.active:
            raise AssertionError(f"seed entry {entry.type_code!r} must be active when seeded")
        if entry.type_code in seen:
            raise AssertionError(f"duplicate type_code in seed set: {entry.type_code!r}")
        seen.add(entry.type_code)

    missing = BACKFILL_EMITTABLE_CODES - seen
    if missing:
        raise AssertionError(
            "h-dcn catalog seed is missing codes the 4.1 backfill can emit "
            f"(a backfilled member would reference a missing type): {sorted(missing)}"
        )


# Enforce the invariants at import time — the seed is DATA, so a drift is a hard error here
# rather than a surprise at apply-time or a dangling member reference in production.
_validate_seed_set()


# ── The seed plan (what the runner renders / applies) ─────────────────────────────────


@dataclass(frozen=True)
class SeedItem:
    """One seed entry paired with what would happen to it: create / update / unchanged."""

    entry: MembershipTypeEntry
    action: str  # "create" | "update" | "unchanged"


@dataclass
class CatalogSeedPlan:
    """The result of diffing the seed set against a repository's current catalog.

    A pure, in-memory plan: in dry-run the runner renders it and writes NOTHING; only with
    ``--apply`` does it upsert the ``create``/``update`` items via ``save_membership_type``.
    Idempotent: a re-seed after a full apply yields all ``unchanged`` (nothing to write).
    """

    tenant_id: str
    items: list[SeedItem] = field(default_factory=list)

    @property
    def to_create(self) -> list[MembershipTypeEntry]:
        return [i.entry for i in self.items if i.action == "create"]

    @property
    def to_update(self) -> list[MembershipTypeEntry]:
        return [i.entry for i in self.items if i.action == "update"]

    @property
    def unchanged(self) -> list[MembershipTypeEntry]:
        return [i.entry for i in self.items if i.action == "unchanged"]

    @property
    def to_write(self) -> list[MembershipTypeEntry]:
        """Every entry that would be persisted (create + update) — nothing in dry-run."""
        return [i.entry for i in self.items if i.action in ("create", "update")]


def _same_entry(a: MembershipTypeEntry, b: MembershipTypeEntry) -> bool:
    """True if two entries carry the same seedable content (code / label / active / order)."""
    return (
        a.type_code == b.type_code
        and dict(a.label) == dict(b.label)
        and bool(a.active) == bool(b.active)
        and int(a.order) == int(b.order)
    )


def build_seed_plan(
    existing: Sequence[MembershipTypeEntry],
    *,
    seed: Sequence[MembershipTypeEntry] = HDCN_MEMBERSHIP_TYPES,
    tenant_id: str = HDCN_TENANT_ID,
) -> CatalogSeedPlan:
    """Diff the seed set against a tenant's current catalog into a :class:`CatalogSeedPlan`.

    Pure + non-destructive — it reads ``existing`` (what ``list_membership_types`` returned)
    and classifies each seed entry:

    - **create** — no catalog entry with this ``type_code`` exists yet;
    - **update** — an entry exists but differs (label/active/order changed);
    - **unchanged** — an identical entry already exists (a re-seed writes nothing).

    Existing catalog entries NOT in the seed are left untouched (never reported for delete —
    soft-delete/retire is a separate management action, C8).
    """
    by_code: Mapping[str, MembershipTypeEntry] = {e.type_code: e for e in existing}
    plan = CatalogSeedPlan(tenant_id=tenant_id)
    for entry in seed:
        # Stamp every seed entry with the PLAN's tenant so the seed set can be applied to any
        # administration (no hardcoded tenant on the runner) and the repository's no-cross-
        # tenant-write guard (Property 1) is satisfied — the entry and the caller agree.
        entry = replace(entry, tenant_id=tenant_id)
        current = by_code.get(entry.type_code)
        if current is None:
            action = "create"
        elif _same_entry(current, entry):
            action = "unchanged"
        else:
            action = "update"
        plan.items.append(SeedItem(entry=entry, action=action))
    return plan
