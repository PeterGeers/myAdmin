"""
S5c Task 3.4 — the **generic-placeholder** ``members.view_contexts`` seed (design C-VIEW, R5.1/R4.5).

This is the ILLUSTRATIVE onboarding default a tenant sees the first time they open the Members
authoring UI's view-context editor (Phase 2). It demonstrates the ``members.view_contexts`` shape
— a list of ``ui.tables``-shaped contexts (``key`` / bilingual ``label`` / ``permission_roles`` /
``columns`` / ``filterable_columns`` / ``default_sort`` / ``page_size``) — as **DATA**, not code.
The generic core never hardcodes a tenant's view contexts (design C-VIEW); they are authored /
seeded as ``members.view_contexts`` parameter data.

Why placeholders (R4.5)
-----------------------
The platform seed must stay tenant-agnostic (no ``if tenant == "h-dcn"`` anywhere; no h-dcn
vocabulary). So this seed references ONLY keys that resolve in the *generic* field set the
platform ships:

- the **Fixed** fields (``sam/members/domain/fixed_fields.py``) — e.g. ``member_number``,
  ``first_name``, ``email``, ``status``, ``membership_type``, ``joined_date``;
- the **Calculated** fields (``sam/members/domain/calculated_fields.py``) — e.g.
  ``display_name``, ``years_member``;
- the two **generic-placeholder overlay** fields seeded by task 1.4
  (``sam/members/domain/seed_overlay.py``) — ``field_a`` / ``field_b``.

It does **NOT** reference any real tenant's field list (no ``iban`` / ``motor_type`` / ``region``
etc.). A real tenant (h-dcn in Phase 6/7) replaces this whole list with their own authored
contexts over their own authored field set.

What it seeds
-------------
Two contexts (an overview + one specialized), matching the "overview + one specialized" pattern
task 3.3's renderer tests model (overview + financial), but kept fully generic:

- ``overview`` — a general, broadly-visible column set open to both member roles
  (``Members_Read`` + ``Members_CRUD``);
- ``administration`` — a narrower, **role-restricted** context (``Members_CRUD`` only) surfacing
  the more administrative columns (member number, join date, the placeholder overlay fields).

Every ``columns`` / ``filterable_columns`` / ``default_sort.field`` entry below is a ``field_key``
that resolves in the fixed ⊕ calculated ⊕ (task-1.4 seeded) overlay field set, so the render-time
"skip unresolvable key" path (Property 7) never silently drops the whole context.

Relationship to the empty-is-valid default
-------------------------------------------
A tenant with **no** authored contexts still gets exactly one synthesized default context
(:func:`sam.members.domain.view_contexts.default_view_context`, R5.1). This seed is the
*illustrative starter* a tenant may keep, edit, or replace — it is not the empty-is-valid
fallback.

The module exposes both the domain objects (:func:`build_seed_view_contexts` →
``tuple[ViewContext, ...]``, for tests / an in-memory :class:`StaticViewContextsProvider`) and the
projection-shaped list (:func:`seed_view_contexts_list`, the ``members.view_contexts`` JSON the
Phase-2 editor pre-populates and the projection carries), kept in lock-step by the builder
consuming the list.
"""

from __future__ import annotations

from typing import Any

from .view_contexts import ViewContext

__all__ = [
    "SEED_VIEW_CONTEXTS",
    "seed_view_contexts_list",
    "build_seed_view_contexts",
]


#: The two generic-placeholder view contexts the platform ships as an onboarding starter.
#: Overview (open to both member roles) + one narrower, role-restricted "administration"
#: context. Every referenced key resolves in the fixed ⊕ calculated ⊕ task-1.4 overlay set.
SEED_VIEW_CONTEXTS: tuple[dict[str, Any], ...] = (
    {
        "key": "overview",
        "label": {"nl": "Overzicht", "en": "Overview"},
        # Available to both member roles (view-convenience gate only; row scope is always
        # enforced server-side regardless of the selected context).
        "permission_roles": ["Members_Read", "Members_CRUD"],
        # A general column set: the calculated display name + core contact/membership fields.
        "columns": [
            "display_name",
            "email",
            "phone",
            "status",
            "membership_type",
        ],
        "filterable_columns": ["status", "membership_type"],
        "default_sort": {"field": "display_name", "direction": "asc"},
        "page_size": 50,
    },
    {
        "key": "administration",
        "label": {"nl": "Administratie", "en": "Administration"},
        # Narrower / role-restricted: only Members_CRUD may select it.
        "permission_roles": ["Members_CRUD"],
        # A more administrative set: member number, join date, tenure, plus the two
        # generic-placeholder overlay fields seeded by task 1.4 (field_a / field_b).
        "columns": [
            "member_number",
            "display_name",
            "joined_date",
            "years_member",
            "field_a",
            "field_b",
        ],
        "filterable_columns": ["member_number", "field_b"],
        "default_sort": {"field": "member_number", "direction": "asc"},
        "page_size": 25,
    },
)


def seed_view_contexts_list() -> list[dict[str, Any]]:
    """Return the generic-placeholder ``members.view_contexts`` value (projection ``config#views`` shape).

    This is the JSON the Phase-2 typed editor pre-populates and the projection carries. It uses
    ONLY generic placeholder / platform-generic field keys — never a real tenant's field list
    (R4.5). Every ``columns`` / ``filterable_columns`` / ``default_sort.field`` entry resolves in
    the fixed ⊕ calculated ⊕ task-1.4-seeded-overlay field set.
    """
    return [
        {
            "key": ctx["key"],
            "label": dict(ctx["label"]),
            "permission_roles": list(ctx["permission_roles"]),
            "columns": list(ctx["columns"]),
            "filterable_columns": list(ctx["filterable_columns"]),
            "default_sort": dict(ctx["default_sort"]) if ctx.get("default_sort") else None,
            "page_size": ctx.get("page_size"),
        }
        for ctx in SEED_VIEW_CONTEXTS
    ]


def build_seed_view_contexts() -> tuple[ViewContext, ...]:
    """Build the seed :class:`ViewContext` tuple from :func:`seed_view_contexts_list` (domain objects).

    Consumes the same projection-shaped list a real tenant's data flows through, so the seed and
    the JSON stay in lock-step and exercise the identical provider/render path.
    """
    raw = seed_view_contexts_list()
    return tuple(
        ViewContext(
            key=ctx["key"],
            label=dict(ctx.get("label") or {}),
            permission_roles=tuple(ctx.get("permission_roles") or ()),
            columns=tuple(ctx.get("columns") or ()),
            filterable_columns=tuple(ctx.get("filterable_columns") or ()),
            default_sort=dict(ctx["default_sort"]) if ctx.get("default_sort") else None,
            page_size=ctx.get("page_size"),
        )
        for ctx in raw
    )
