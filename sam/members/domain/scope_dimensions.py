"""
S5 Task 1.3 — the **scope-dimension model** (design C4, R3.2/R3.3/R3.4).

A **scope dimension** is a tenant-configurable, *within-tenant* partition + role-scoping
filter (see ``scope-dimension-design.md``). It generalizes h-dcn's "region": a member
belongs to scope value(s); a permission role is scoped to a subset of those values; a
regional user sees only their subset while admin/national see all.

This module owns only the **model** (the tenant-agnostic *config shape* + its validation +
the h-dcn wiring), not the access-resolution algorithm. ``resolve_scope_access`` — which
turns a user's roles into an ``allowed_scopes`` set — is task 3.1 and consumes the
:class:`ScopeDimension` objects this module produces.

Design constraints honoured here (per the design of record):

- **``scope_dimensions`` is a LIST** — the model is multi-dimension capable from day one
  (soccer/hockey: team + season) even though h-dcn wires a single dimension. Nothing in the
  shape assumes exactly one dimension.
- **Each dimension binds to a member ``field``** — the normal member field key whose value a
  record is scoped by (``field`` defaults to the dimension ``key`` for back-compat: h-dcn's
  ``region`` dimension binds to the ``region`` field). A member is single-valued per scope
  field (R3.2) — the record holds a scalar on that field; only the USER GRANT is multi-value.
- **``enabled:false`` (or no dimension) collapses to tenant-wide** — a disabled dimension
  is a no-op: everyone is effectively ``["*"]``, no code path differs, clubs without
  sub-scoping pay nothing. :func:`enabled_dimensions` filters those out.
- **Tenant-agnostic + storage-agnostic** — no ``if tenant == "h-dcn"``, no DynamoDB/boto3, and
  NO tenant's real vocabulary baked in (Decision D17). A tenant's scope config is *injected*
  via the provider (from ``members.scope_dimensions`` → projection). :data:`SAMPLE_SCOPE_CONFIG`
  is a neutral, clearly-synthetic fixture for the provider seam + unit tests ONLY — never a
  tenant's production data.

The overlay/provider seam mirrors ``field_resolver.py``: the config is *injected* via a
:class:`ScopeConfigProvider` ``Protocol``; the SAM-plane concrete provider is DynamoDB-backed
tenant config, wired in a later step. A tenant with no configured dimensions resolves to an
**empty** list (→ tenant-wide), never an error.

What this module is NOT:
- It does not resolve a user's roles to ``allowed_scopes`` (that is ``resolve_scope_access``,
  task 3.1 / design C4).
- It does not validate a member's ``scope_values`` against the dimension's ``values`` (that
  is the MembershipService's job when it writes a record — Step 5).
- It does not persist anything (the repository, task 1.4 / Step 4).
"""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field as dataclass_field
from typing import Mapping, Optional, Protocol, Sequence, runtime_checkable

__all__ = [
    "WILDCARD",
    "ScopeDimension",
    "ScopeConfig",
    "ScopeConfigError",
    "ScopeConfigProvider",
    "StaticScopeConfigProvider",
    "enabled_dimensions",
    "SAMPLE_SCOPE_CONFIG",
]

#: The "all values" sentinel a fully-scoped (admin/national) user resolves to, and the
#: all-access GRANT value carried in a projected ``scopegrant#`` row. A disabled dimension
#: resolves to this too. Kept here so the model, the resolver, the edge, and the repository
#: filter all agree on one token. s5d clean break (R2.2): the ``Regio_*`` ``all_wildcard``
#: role-name encoding is removed — the all-access sentinel is this GRANT value, not a role.
WILDCARD = "*"


# ── The dimension model (tenant config — Rung 1) ─────────────────────────────────────


@dataclass(frozen=True)
class ScopeDimension:
    """One tenant-configurable scope dimension (h-dcn: ``region``; soccer: ``team``).

    Frozen because a dimension is configuration data, resolved once per tenant and shared.
    The fields map 1:1 to the design's scope-dimension config (design "Scope dimension
    config"):

    - ``key`` — the dimension's identifier (also the ``scopegrant#…#<key>`` projection key and
      the ``config#scope`` dimension key). h-dcn: ``"region"``.
    - ``field`` — the member FIELD key this dimension binds to: the normal member field whose
      (scalar) value a record is scoped by. Defaults to ``key`` for back-compat (h-dcn's
      ``region`` dimension binds to the ``region`` field). ``members.scope_dimensions`` (the
      MySQL param) is the source of truth for which field each dimension binds to. A member is
      single-valued per scope field (R3.2); only the user GRANT is multi-value.
    - ``label`` — i18n display label (``{"nl": ..., "en": ...}``); presentation only.
    - ``enabled`` — ``False`` collapses this dimension to tenant-wide (a no-op; see
      :func:`enabled_dimensions`). A tenant with *no sub-scoping* sets ``enabled=False``.
    - ``values`` — the closed set of scope values (h-dcn: Noord/Zuid/Oost/West). May be
      empty for a dynamically-sourced dimension, but an *enabled* dimension must declare at
      least one value (a scope with no values is a misconfiguration).
    - ``required_for`` — capabilities that REQUIRE a scope grant: holding one of these
      *without* any grant in this dimension is a deny (h-dcn's "permission requires region
      assignment"). Consumed by ``resolve_scope_access`` (task 3.1).
    """

    key: str
    field: Optional[str] = None
    label: Mapping[str, str] = dataclass_field(default_factory=dict)
    enabled: bool = True
    values: Sequence[str] = ()
    required_for: Sequence[str] = ()

    def __post_init__(self) -> None:
        # ``field`` defaults to the dimension ``key`` (back-compat: h-dcn's ``region``
        # dimension binds to the ``region`` field). Frozen dataclass → set via object.
        if self.field is None:
            object.__setattr__(self, "field", self.key)

    def allows_value(self, value: str) -> bool:
        """Whether ``value`` is a declared value of this dimension (case-sensitive)."""
        return value in tuple(self.values)

    def normalized_values(self) -> tuple[str, ...]:
        """The dimension's declared values as a stable tuple (de-duplicated, order kept)."""
        seen: set[str] = set()
        out: list[str] = []
        for v in self.values:
            if v not in seen:
                seen.add(v)
                out.append(v)
        return tuple(out)


class ScopeConfigError(Exception):
    """Raised when a tenant's scope config is malformed (a config bug, not user input).

    Carries ``reasons`` (dimension key → why) so a misconfiguration surfaces every problem
    at once rather than one at a time — mirroring ``OverlayError`` / ``FieldValidationError``.
    """

    def __init__(self, reasons: Mapping[str, str]):
        self.reasons = dict(reasons)
        detail = "; ".join(f"{k}: {v}" for k, v in self.reasons.items())
        super().__init__(f"invalid scope-dimension config: {detail}")


@dataclass(frozen=True)
class ScopeConfig:
    """A tenant's scope configuration: a **list** of :class:`ScopeDimension` (design C4).

    The list is the whole point of R3.2/R3.4 — the model is multi-dimension capable from the
    start (a tenant may declare region *and* season), while a tenant with none supplies an
    empty list (→ tenant-wide everywhere). Construction validates the list eagerly (fail
    fast on a config bug).
    """

    tenant_id: str
    dimensions: tuple[ScopeDimension, ...] = ()

    def __post_init__(self) -> None:
        _reject_invalid_config(self.tenant_id, self.dimensions)

    def enabled(self) -> tuple[ScopeDimension, ...]:
        """Only the dimensions that are switched on (disabled ones collapse to tenant-wide)."""
        return enabled_dimensions(self.dimensions)

    def dimension(self, key: str) -> Optional[ScopeDimension]:
        """Return the dimension with ``key`` (enabled or not), or ``None`` if absent."""
        for d in self.dimensions:
            if d.key == key:
                return d
        return None

    def is_tenant_wide(self) -> bool:
        """True when no dimension is enabled — the tenant is effectively un-partitioned.

        This is the ``enabled:false`` / no-dimension collapse: with nothing enabled, every
        user sees everything (``["*"]``) and no scope code path differs (R3.2).
        """
        return len(self.enabled()) == 0


def enabled_dimensions(
    dimensions: Sequence[ScopeDimension],
) -> tuple[ScopeDimension, ...]:
    """Filter a dimension list to the enabled ones (the tenant-wide collapse for the rest).

    A standalone helper (not just a method) so the resolver (task 3.1) and repository filter
    can apply the same collapse to a raw dimension list without constructing a
    :class:`ScopeConfig`.
    """
    return tuple(d for d in dimensions if d.enabled)


# ── Config validation (fail fast on a misconfiguration) ──────────────────────────────


def _reject_invalid_config(
    tenant_id: str,
    dimensions: Sequence[ScopeDimension],
) -> None:
    """Raise :class:`ScopeConfigError` if the dimension list is malformed.

    Enforced invariants (a *disabled* dimension is exempt from value/role checks — it is a
    no-op and its body is ignored):

    - ``tenant_id`` is a non-empty string;
    - dimension ``key`` is a non-empty string and unique within the tenant;
    - an **enabled** dimension declares at least one value (a scope with no values can never
      grant anything — a misconfiguration);
    - an enabled dimension's declared ``values`` are non-blank and contain no duplicates.

    (s5d clean break, R2.2/R8.1: the ``Regio_*`` ``all_wildcard`` role-name encoding is
    removed, so there is no longer an all-wildcard-vs-value collision check.)
    """
    if not isinstance(tenant_id, str) or not tenant_id.strip():
        raise ScopeConfigError({"<tenant_id>": "must be a non-empty string"})

    reasons: dict[str, str] = {}
    seen_keys: set[str] = set()

    for dim in dimensions:
        key = dim.key
        if not isinstance(key, str) or not key.strip():
            reasons["<dimension>"] = "dimension key must be a non-empty string"
            continue
        if key in seen_keys:
            reasons[key] = "duplicate dimension key"
            continue
        seen_keys.add(key)

        # A disabled dimension is a no-op: its body is never consulted, so skip value checks.
        if not dim.enabled:
            continue

        values = tuple(dim.values)
        if not values:
            reasons[key] = "an enabled dimension must declare at least one value"
            continue

        if any((not isinstance(v, str)) or (not v.strip()) for v in values):
            reasons[key] = "scope values must be non-blank strings"
            continue

        if len(set(values)) != len(values):
            reasons[key] = "scope values must be unique"
            continue

    if reasons:
        raise ScopeConfigError(reasons)


# ── The config provider seam (mirrors field_resolver's TenantOverlayProvider) ─────────


@runtime_checkable
class ScopeConfigProvider(Protocol):
    """Supplies a tenant's :class:`ScopeConfig`, resolved by ``tenant_id``.

    The consumer depends on this shape, not on where the config lives — exactly as
    ``FieldResolver`` depends on a ``TenantOverlayProvider``. The SAM-plane concrete provider
    is DynamoDB-backed tenant config, injected in a later step; the domain layer never
    imports it. A tenant with no configured dimensions MUST yield a :class:`ScopeConfig` with
    an **empty** dimension list (→ tenant-wide), never an error.
    """

    def get_scope_config(self, tenant_id: str) -> ScopeConfig:
        ...


class StaticScopeConfigProvider:
    """An in-memory :class:`ScopeConfigProvider` backed by a ``{tenant_id: [dimensions]}`` map.

    The storage-agnostic default: used by tests and any caller that already holds the config
    (e.g. a synthetic :data:`SAMPLE_SCOPE_CONFIG`), and the reference against which the
    DynamoDB-backed provider is later swapped in. Unknown tenants resolve to an **empty**
    config (tenant-wide) — the fail-safe default (a missing scope config is not an error;
    it simply means the tenant is un-partitioned).
    """

    def __init__(
        self,
        configs: Optional[Mapping[str, Sequence[ScopeDimension]]] = None,
    ):
        # Validate each tenant's dimensions eagerly by materialising a ScopeConfig.
        self._configs: dict[str, ScopeConfig] = {
            tenant_id: ScopeConfig(tenant_id=tenant_id, dimensions=tuple(dims))
            for tenant_id, dims in dict(configs or {}).items()
        }

    def get_scope_config(self, tenant_id: str) -> ScopeConfig:
        if tenant_id in self._configs:
            return self._configs[tenant_id]
        return ScopeConfig(tenant_id=tenant_id, dimensions=())


# ── Sample scope config (SYNTHETIC fixture — NOT tenant data; Decision D17) ───────────

#: REFERENCE / TEST FIXTURE ONLY — **not** any tenant's config and **not** a runtime source.
#: A tenant's real region vocabulary lives ONLY in its ``members.scope_dimensions`` parameter
#: (MySQL, authored at onboarding) → projected to ``config#scope`` → read by the SAM edge via
#: the ``ScopeConfigProvider``. The generic core must NOT ship any tenant's vocabulary, so this
#: fixture uses ABSTRACT synthetic values (``North/South/East/West``) that are obviously not a
#: real Dutch region set — just enough to exercise the scope MECHANISM in unit tests. The
#: runtime has NO fallback to this constant (Decision D16): a missing/failed projection is a
#: system error, not a silent substitution.
#:
#: This is tenant-agnostic *shape* data — the generic core has no ``if tenant == "h-dcn"``.
#: Setting ``enabled=False`` (or an empty list) collapses to tenant-wide with no code path
#: change (R3.2). s5d clean break (R2.2/R8.1): the ``Regio_*`` role encoding is REMOVED — a
#: member user's scope is authored in ``user_tenant_scope`` and all-access is the projected
#: ``["*"]`` grant, not a role name.
SAMPLE_SCOPE_CONFIG: tuple[ScopeDimension, ...] = (
    ScopeDimension(
        key="region",
        # field defaults to key ("region") — binds to the member's `region` field.
        label={"en": "Region"},
        enabled=True,
        # ABSTRACT synthetic values ONLY (D17) — deliberately NOT a real region set, so no
        # tenant's vocabulary lives in the core. A tenant's real regions are authored in its
        # `members.scope_dimensions` param / the onboarding data file, never here.
        values=(
            "North",
            "South",
            "East",
            "West",
        ),
        required_for=("Members_CRUD",),
    ),
)
