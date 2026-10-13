"""
S5c Task 1.4 — the **generic-placeholder** ``members.field_overlay`` seed (design C-FIELDS, R4.5).

This is the ILLUSTRATIVE onboarding default a tenant sees the first time they open the Members
authoring UI (Phase 2). It demonstrates the full ``members.field_overlay`` shape — a
``functional_groups`` catalog, a ``fields`` map of added variable fields, and ``fixed_overrides``
(presentation overrides of fixed/calculated fields, incl. ``functional_group``) — using **GENERIC
PLACEHOLDER names** ("Field A", "Region A", ...), **NOT** any real tenant's field list (R4.5).

Why placeholders (R4.5)
-----------------------
The classification-table **Parameter** rows (``guardian_name``; communication prefs; motor
``motor_brand``/``motor_type``/``build_year``/``license_plate``; ``iban``/``payment_method``;
``notes``/``signature_date``) are **h-dcn's real overlay** — they are authored as *data* at
onboarding (Phase 6), not baked into the platform. The platform seed must stay tenant-agnostic
(no ``if tenant == "h-dcn"`` anywhere; no h-dcn vocabulary), so it seeds a couple of neutral
placeholder fields under placeholder functional groups instead. A real tenant replaces this whole
object with their own authored overlay.

What it seeds
-------------
- a ``functional_groups`` catalog: the base display groups every tenant starts with
  (``personal`` / ``address`` / ``membership`` / ``administrative``) plus one neutral custom
  group (``group_a``) to show the mechanism;
- ``fixed_overrides`` that move the **address** fixed fields (``street`` / ``postal_code`` /
  ``city`` / ``country``) — which STORE under ``personal`` — into the ``address`` *functional*
  (display) group (R4.9: display group changes, storage bucket does not);
- two placeholder variable ``fields`` (``field_a`` string, ``field_b`` a small enum with rich
  ``{value,label,roles?}`` options, one option role-restricted) under ``group_a``.

Scope notes (from the classification table):
- ``region`` is a **scope dimension** (``members.scope_dimensions``), NOT the field overlay — it
  is seeded separately (generic ``Region A/B/C``) and is not defined here.
- ``welcome_pack_*`` is **OUT** (R11.2) — defined nowhere.

The module exposes both the domain object (:func:`build_seed_overlay` → :class:`TenantOverlay`,
for tests / an in-memory provider) and the projection-shaped dict (:func:`seed_overlay_dict`,
the ``config#fields`` JSON the Phase-2 editor pre-populates and the projection carries). The two
are kept in lock-step by :func:`build_seed_overlay` consuming the dict, so the seed round-trips
through the same reader path (``MembersProjectionReader.get_overlay``) that real tenant data does.
"""

from __future__ import annotations

from typing import Any

from .attribute_catalog import BASE_FUNCTIONAL_GROUPS
from .field_resolver import (
    FixedFieldOverride,
    FunctionalGroup,
    OverlayField,
    TenantOverlay,
)
from .fixed_fields import EnumOption, FieldType

__all__ = [
    "SEED_FUNCTIONAL_GROUPS",
    "build_seed_overlay",
    "seed_overlay_dict",
]


def _base_group_dict(group: FunctionalGroup) -> dict[str, Any]:
    """Project a base :class:`FunctionalGroup` into the projection ``config#fields`` dict shape.

    Keeps the seed's ``{"key","label","order"}`` dict form while sourcing the VALUES from the one
    base-group definition (:data:`BASE_FUNCTIONAL_GROUPS`), so there is no second hand-maintained
    copy of the base groups to drift (task 1.2 / R5.2).
    """
    return {"key": group.key, "label": dict(group.label), "order": group.order}


#: One neutral placeholder custom group demonstrating the overlay mechanism — this is seed/test
#: DATA, NOT a base group (NOT h-dcn's real "motor"/"financial" groups, which are authored as data
#: at onboarding). Its ``order`` continues the base sequence so the seed renders predictably.
_SEED_ONLY_FUNCTIONAL_GROUPS: tuple[dict[str, Any], ...] = (
    {"key": "group_a", "label": {"nl": "Groep A", "en": "Group A"}, "order": 5},
)


#: The base functional-group catalog every tenant starts with (generic; a tenant edits it).
#:
#: The base groups are DERIVED from :data:`BASE_FUNCTIONAL_GROUPS` (the single base-group
#: definition for the module, in ``attribute_catalog.py``) rather than being a second hand-typed
#: copy — task 1.2 / R5.2: ONE base-group definition, not two. The seed-only extras
#: (:data:`_SEED_ONLY_FUNCTIONAL_GROUPS`, e.g. ``group_a``) stay seed/test data and are appended
#: after the base groups.
SEED_FUNCTIONAL_GROUPS: tuple[dict[str, Any], ...] = (
    tuple(_base_group_dict(g) for g in BASE_FUNCTIONAL_GROUPS) + _SEED_ONLY_FUNCTIONAL_GROUPS
)


def seed_overlay_dict() -> dict[str, Any]:
    """Return the generic-placeholder ``members.field_overlay`` object (projection ``config#fields`` shape).

    This is the JSON the Phase-2 typed editor pre-populates and the projection carries. It uses
    ONLY generic placeholder names (Field A/B, Group A) — never a real tenant's field list (R4.5).
    """
    return {
        "functional_groups": [dict(g) for g in SEED_FUNCTIONAL_GROUPS],
        "fields": {
            # A neutral placeholder string field under the custom group.
            "field_a": {
                "type": "string",
                "required": False,
                "visible": True,
                "label": {"nl": "Veld A", "en": "Field A"},
                "functional_group": "group_a",
                "order": 10,
            },
            # A placeholder enum field showing the rich-option shape + value-level role gating:
            # option "option_2" is restricted to Members_CRUD (R4.12) — illustrative only.
            "field_b": {
                "type": "enum",
                "required": False,
                "visible": True,
                "label": {"nl": "Veld B", "en": "Field B"},
                "functional_group": "group_a",
                "options": [
                    {"value": "option_1", "label": {"nl": "Optie 1", "en": "Option 1"}},
                    {
                        "value": "option_2",
                        "label": {"nl": "Optie 2", "en": "Option 2"},
                        "roles": ["Members_CRUD"],
                    },
                ],
                "order": 20,
            },
        },
        # Move the address fixed fields into the "address" DISPLAY group (storage stays personal).
        "fixed_overrides": {
            "personal.street": {"functional_group": "address"},
            "personal.postal_code": {"functional_group": "address"},
            "personal.city": {"functional_group": "address"},
            "personal.country": {"functional_group": "address"},
        },
    }


def build_seed_overlay() -> TenantOverlay:
    """Build the seed :class:`TenantOverlay` from :func:`seed_overlay_dict` (domain object).

    Consumes the same projection-shaped dict a real tenant's data flows through, so the seed and
    the JSON stay in lock-step and exercise the identical resolve path.
    """
    raw = seed_overlay_dict()

    functional_groups = {
        g["key"]: FunctionalGroup(
            key=g["key"], label=dict(g.get("label") or {}), order=int(g.get("order", 0) or 0)
        )
        for g in raw["functional_groups"]
    }

    def _options(specs: Any) -> tuple[EnumOption, ...] | None:
        if not specs:
            return None
        return tuple(
            EnumOption(
                value=str(o["value"]),
                label=dict(o.get("label") or {}),
                roles=tuple(o["roles"]) if o.get("roles") else None,
            )
            for o in specs
        )

    fields = {}
    for name, spec in raw["fields"].items():
        options = _options(spec.get("options"))
        fields[name] = OverlayField(
            key=name,
            type=FieldType(spec.get("type", "string")),
            required=bool(spec.get("required", False)),
            label=dict(spec.get("label") or {}),
            choices=tuple(o.value for o in options) if options is not None else None,
            options=options,
            functional_group=spec.get("functional_group"),
            show_when=spec.get("show_when"),
            visible=bool(spec.get("visible", True)),
            order=int(spec.get("order", 0) or 0),
        )

    overrides = {
        dotted: FixedFieldOverride(functional_group=spec.get("functional_group"))
        for dotted, spec in raw["fixed_overrides"].items()
    }

    return TenantOverlay(
        fields=fields, overrides=overrides, functional_groups=functional_groups
    )
