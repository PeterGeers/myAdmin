"""
S5c Task 3.1 — the **view-context model** (design C-VIEW, R5.1/R5.1a).

A **view context** is a tenant-configurable, named column-set over the resolved member
field config — "which fields show together" (design C-VIEW). It generalizes myAdmin's
single-view ``ui.tables`` per-view shape to *multiple selectable contexts*: each context
carries a ``key`` / bilingual ``label`` / ``permission_roles`` (a view-convenience gate)
plus the ``ui.tables``-shaped presentation primitives (``columns`` /
``filterable_columns`` / ``default_sort`` / ``page_size``) the SPA hands to the existing
``useFilterableTable`` / ``FilterableHeader`` toolkit.

This module owns only the **model** + its provider seam — it is deliberately
**storage-agnostic** (no boto3) and **tenant-agnostic** (no ``if tenant == ...``),
mirroring :mod:`sam.members.domain.scope_dimensions` and
:mod:`sam.members.domain.field_resolver`. Where the contexts come from is *injected* via a
:class:`ViewContextsProvider` ``Protocol``; the SAM-plane concrete provider is the
DynamoDB-backed projection reader
(:class:`sam.members.repository.projection_config_reader.MembersProjectionReader`), wired
elsewhere.

Empty-is-valid (R5.1)
---------------------
A tenant that has authored **no** view contexts — or whose projected ``config#views`` row
is missing/empty — resolves to **exactly one default context** over all visible fields
(:func:`default_view_context`). The default context carries **empty** ``columns`` /
``filterable_columns`` as the *"all visible fields"* sentinel: the renderer expands an
empty ``columns`` to the tenant's ``FieldConfig.visible_fields()`` so the default context
needs no field references to resolve (and so can never dangle). This keeps the module from
ever forcing a context the tenant did not author, and never crashes on an unconfigured
tenant.

Reference resolution (R5.1a) is NOT done here
---------------------------------------------
This module does not look a column ``field_key`` up in ``FieldConfig`` — that resolution /
skip-on-unresolvable happens at render (SPA) and the fail-fast rejection happens at Save
(the Flask-plane ``services.members_config_validation``). The view-context model is the
plain shape both sides agree on.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Optional, Protocol, Sequence, runtime_checkable

__all__ = [
    "DEFAULT_CONTEXT_KEY",
    "ViewContext",
    "ViewContextsProvider",
    "StaticViewContextsProvider",
    "default_view_context",
]

#: The stable ``key`` of the synthesized default context (empty-is-valid, R5.1). A tenant
#: that authors no contexts still gets exactly one context with this key, over all visible
#: fields. Chosen to be a namespaced token so it cannot collide with a tenant-authored key.
DEFAULT_CONTEXT_KEY = "__default__"


@dataclass(frozen=True)
class ViewContext:
    """One named, selectable column-set over the resolved field config (design C-VIEW).

    A presentation-facing shape: it carries what the SPA needs to render the context (its
    label + the ``ui.tables``-shaped primitives) and the ``permission_roles`` gate for the
    context dropdown (a *view convenience*, not an authorization boundary — row scope
    filtering per C-SCOPE is always applied server-side regardless of the selected context).

    ``columns`` / ``filterable_columns`` entries are ``field_key``s validated against
    ``FieldConfig`` at authoring/render (R5.1a) — NOT here. An **empty** ``columns`` means
    "all visible fields" (the default-context sentinel, :func:`default_view_context`).

    Attributes:
        key: Stable identifier for the context (never user-facing, not translated).
        label: Bilingual ``{"nl": ..., "en": ...}`` display label (may be empty).
        permission_roles: Roles allowed to select this context in the dropdown. Empty =
            available to any caller who can see the page (view-convenience gate only).
        columns: Ordered ``field_key``s to show as columns. Empty = all visible fields.
        filterable_columns: The subset of ``field_key``s that are filterable.
        default_sort: ``{"field": <field_key>, "direction": "asc"|"desc"}`` or ``None``.
        page_size: Rows per page, or ``None`` (renderer applies its own default).
    """

    key: str
    label: Mapping[str, str] = field(default_factory=dict)
    permission_roles: Sequence[str] = ()
    columns: Sequence[str] = ()
    filterable_columns: Sequence[str] = ()
    default_sort: Optional[Mapping[str, Any]] = None
    page_size: Optional[int] = None

    @property
    def is_default(self) -> bool:
        """True iff this is the synthesized empty-is-valid default context (R5.1)."""
        return self.key == DEFAULT_CONTEXT_KEY


def default_view_context() -> ViewContext:
    """Return the single default context used when a tenant authored none (R5.1).

    Over **all visible fields** — expressed as empty ``columns`` (the "all visible fields"
    sentinel the renderer expands from ``FieldConfig.visible_fields()``), so the default
    context references no field keys and thus can never dangle. This is the empty-is-valid
    collapse: a missing/empty ``config#views`` row → exactly one context, never an error.
    """
    return ViewContext(
        key=DEFAULT_CONTEXT_KEY,
        label={"nl": "Overzicht", "en": "Overview"},
        permission_roles=(),
        columns=(),
        filterable_columns=(),
        default_sort=None,
        page_size=None,
    )


@runtime_checkable
class ViewContextsProvider(Protocol):
    """Read-only provider of a tenant's view contexts (the view-context seam).

    Mirrors :class:`sam.members.domain.field_resolver.TenantOverlayProvider` /
    :class:`sam.members.domain.scope_dimensions.ScopeConfigProvider`: the domain depends on
    this ``Protocol``, never on where the contexts live. The SAM-plane concrete provider is
    the DynamoDB-backed projection reader; tests pass a static one.
    """

    def get_view_contexts(self, tenant_id: str) -> tuple[ViewContext, ...]:
        """Return the tenant's view contexts (never empty — ≥1 default, R5.1)."""
        ...


class StaticViewContextsProvider:
    """In-memory :class:`ViewContextsProvider` — the tenant-agnostic reference provider.

    Holds a ``{tenant_id: contexts}`` map. A tenant with no entry (or an empty list) yields
    exactly one :func:`default_view_context` (empty-is-valid, R5.1), matching the
    DynamoDB-backed reader's behavior so tests and production agree.
    """

    def __init__(self, contexts_by_tenant: Optional[Mapping[str, Sequence[ViewContext]]] = None):
        self._contexts_by_tenant = dict(contexts_by_tenant or {})

    def get_view_contexts(self, tenant_id: str) -> tuple[ViewContext, ...]:
        contexts = tuple(self._contexts_by_tenant.get(tenant_id) or ())
        return contexts if contexts else (default_view_context(),)
