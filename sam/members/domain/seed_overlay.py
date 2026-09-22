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

from .field_resolver import (
    FixedFieldOverride,
    FunctionalGroup,
    OverlayField,
    TenantOverlay,
)
from .fixed_fields import EnumOption, FieldType

__all__ = [
    "SEED_FUNCTIONAL_GROUPS",
    "seed_overlay_dict",
    "build_seed_overlay",
]


#: The base functional-group catalog every tenant starts with (generic; a tenant edits it).
#: ``group_a`` is a neutral placeholder custom group demonstrating the mechanism (NOT h-dcn's
#: real "motor"/"financial" groups — those are authored as data at onboarding).
SEED_FUNCTIONAL_GROUPS: tuple[dict[str, Any], ...] = (
    {"key": "personal", "label": {"nl": "Persoonlijk", "en": "Personal"}, "order": 1},
    {"key": "address", "label": {"nl": "Adres", "en": "Address"}, "order": 2},
    {"key": "membership", "label": {"nl": "Lidmaatschap", "en": "Membership"}, "order": 3},
    {"key": "administrative", "label": {"nl": "Administratie", "en": "Administrative"}, "order": 4},
    {"key": "group_a", "label": {"nl": "Groep A", "en": "Group A"}, "order": 5},
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
