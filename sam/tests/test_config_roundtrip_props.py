"""
S5b Task 5.4 — property-based **config round-trip** tests (design Correctness Properties).

Feature: s5b-members-runnable-in-spa, Property 2: Config round-trips MySQL → projection →
resolved provider.

Validates: Requirements 1.1, 1.2, 1.3, 10.6

What this asserts (the FULL round-trip, deferred until the reader existed)
--------------------------------------------------------------------------
For any *valid* tenant scope/field configuration authored in MySQL (the ``members.*``
tenant-scope parameters Tenant Admin authors), building the ``config#scope`` / ``config#fields``
projection row via the S5b builders (``services.projection_sync``, tasks 5.1/5.2) and then
reading it back through the module projection reader
(``sam.members.repository.projection_config_reader.MembersProjectionReader``, task 8.1) yields a
:class:`ScopeConfig` / :class:`TenantOverlay` **equivalent to the authored configuration** — a
round-trip through the projection preserves the config:

    authored config (params) --builder--> projection row --reader--> resolved provider shape

Two properties, each ≥100 generated iterations (``@settings(max_examples=100)``):

- ``test_property_config_scope_round_trips`` (R1.1/R1.2): authored ``scope_dimensions`` →
  ``build_config_scope_row`` → ``row.to_dynamodb_item()`` → reader ``get_scope_config`` →
  :class:`ScopeConfig` equivalent to the authored dimensions.
- ``test_property_config_fields_round_trips`` (R1.3): authored ``field_overlay`` →
  ``build_config_fields_row`` → row → reader ``get_overlay`` → :class:`TenantOverlay`
  equivalent to the authored overlay.

Genuine (non-tautological) equivalence
---------------------------------------
The builder + reader each normalise (fill defaults, drop unknown keys, list→tuple, string→
:class:`FieldType`, default an overlay field's ``key`` to its map key, carry only present
override aspects). The strategies here therefore GENERATE ONLY the authored *input* shape (the
Tenant-Admin param dicts) and the assertions compute the SAME normalisation the
authored→builder→reader path applies, so the test asserts real round-trip fidelity — the
resolved provider shape a valid authored config collapses to — not that two identical dicts are
equal. The strategies are also constrained to VALID configs (unique non-blank dimension keys;
an enabled dimension declares ≥1 unique non-blank value; ``all_wildcard`` is never one of the
values; overlay field keys never collide with a fixed field key; an enum overlay field declares
choices) so construction of the reader's ``ScopeConfig`` / the resolver's overlay never raises —
otherwise we'd be testing the wrong thing.

No live AWS, no MySQL: the builder reads a ``FakeParameterService`` (mirrors
``backend/tests/unit/test_projection_sync.py``) and the reader queries a ``FakeTable`` (mirrors
``sam/tests/test_members_projection_reader.py``).
"""

import os
import sys

from hypothesis import given, settings
from hypothesis import strategies as st

# repo root on sys.path (mirrors sam/conftest.py) so `sam.members` imports.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

# backend/src on sys.path so `services.*` (the builders + schema) resolve (mirrors
# test_members_projection_reader.py — the projection schema is shared across both planes).
_BACKEND_SRC = os.path.join(_REPO_ROOT, "backend", "src")
if _BACKEND_SRC not in sys.path:
    sys.path.insert(0, _BACKEND_SRC)

from services import projection_schema as schema
from services.projection_sync import (
    build_config_fields_row,
    build_config_scope_row,
    build_config_views_row,
)

from sam.members.domain.field_resolver import TenantOverlay
from sam.members.domain.fixed_fields import FIXED_FIELDS, FieldType
from sam.members.domain.scope_dimensions import ScopeConfig
from sam.members.domain.view_contexts import DEFAULT_CONTEXT_KEY
from sam.members.repository.projection_config_reader import MembersProjectionReader

# The canonical keys a variable overlay field may NOT collide with (fixed base registry).
_FIXED_KEYS = frozenset(f.key for f in FIXED_FIELDS)
# The canonical dotted keys a fixed-field override addresses (only real fixed fields).
_FIXED_DOTTED = tuple(f.dotted_key() for f in FIXED_FIELDS)

_TENANT_ID = "round-trip-tenant"


# ---------------------------------------------------------------------------
# In-memory fakes (mirror the existing example tests exactly)
# ---------------------------------------------------------------------------


class FakeParameterService:
    """Read-only ``ParameterService`` stand-in — returns pre-set values, no I/O.

    Mirrors ``backend/tests/unit/test_projection_sync.py``: values keyed by
    ``(namespace, key, tenant)``.
    """

    def __init__(self, params=None):
        self._params = params or {}
        self.calls: list[dict] = []

    def get_param(self, namespace, key, tenant=None, role=None, user=None):
        self.calls.append({"namespace": namespace, "key": key, "tenant": tenant})
        return self._params.get((namespace, key, tenant))


class FakeTable:
    """In-memory query-side stand-in for a boto3 DynamoDB Table.

    Mirrors ``sam/tests/test_members_projection_reader.py``: ``query`` returns only the
    seeded items whose partition key matches the boto3 ``Key(...).eq(...)`` condition.
    """

    def __init__(self):
        self.store: dict[tuple, dict] = {}

    def put(self, item: dict) -> None:
        key = (item[schema.PARTITION_KEY_ATTR], item[schema.SORT_KEY_ATTR])
        self.store[key] = dict(item)

    def query(self, KeyConditionExpression=None):
        tenant_id = KeyConditionExpression.get_expression()["values"][1]
        items = [dict(v) for k, v in self.store.items() if k[0] == tenant_id]
        return {"Items": items}


# ---------------------------------------------------------------------------
# Strategies — generate ONLY valid authored config (the Tenant-Admin param shape)
# ---------------------------------------------------------------------------

# A constrained, JSON-safe alphabet for keys/values so generated config is valid + serialisable
# (non-blank, no leading/trailing-whitespace surprises, no collisions with the wildcard sentinel).
_TOKEN = st.text(
    alphabet="abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_",
    min_size=1,
    max_size=12,
)


def _i18n_label():
    """An i18n label dict (possibly empty) — the presentation-only ``{"nl":..,"en":..}`` shape."""
    return st.dictionaries(
        keys=st.sampled_from(["nl", "en", "de", "fr"]),
        values=st.text(min_size=1, max_size=20),
        max_size=4,
    )


@st.composite
def _scope_dimension(draw, key: str):
    """A single VALID authored scope-dimension dict for a given (unique) ``key``.

    Enforces the invariants ``ScopeConfig``'s eager validation requires so the reader can
    construct it: an *enabled* dimension declares ≥1 unique non-blank value. s5d clean break
    (R2.2/R8.1): the ``Regio_*`` ``all_wildcard`` role-name encoding is removed.
    """
    enabled = draw(st.booleans())
    # A unique, non-blank value set. Enabled dimensions MUST have ≥1 value (validation rule);
    # a disabled dimension may have any (its body is ignored) — keep ≥1 for simplicity.
    values = draw(
        st.lists(_TOKEN, min_size=1, max_size=5, unique=True)
    )
    return {
        "key": key,
        "label": draw(_i18n_label()),
        "enabled": enabled,
        "values": values,
        "required_for": draw(st.lists(_TOKEN, max_size=3, unique=True)),
    }


@st.composite
def _scope_dimensions(draw):
    """A list of 1..4 VALID authored dimensions with UNIQUE keys."""
    keys = draw(st.lists(_TOKEN, min_size=1, max_size=4, unique=True))
    return [draw(_scope_dimension(key)) for key in keys]


@st.composite
def _overlay_field(draw, name: str):
    """A single VALID authored variable-overlay field dict.

    ``name`` (the map key) is guaranteed by the caller not to collide with a fixed-field key.
    An enum field MUST declare choices (overlay-validity rule).
    """
    ftype = draw(st.sampled_from([t.value for t in FieldType]))
    choices = None
    if ftype == FieldType.ENUM.value:
        choices = draw(st.lists(_TOKEN, min_size=1, max_size=4, unique=True))
    spec = {
        "key": name,  # authored key == map key (the common, unambiguous case)
        "type": ftype,
        "required": draw(st.booleans()),
        "label": draw(_i18n_label()),
        "choices": choices,
        "visible": draw(st.booleans()),
        "order": draw(st.integers(min_value=-50, max_value=50)),
    }
    return spec


@st.composite
def _fixed_override(draw):
    """A fixed-field override dict carrying ONLY a random subset of the four aspects.

    Presentation-only + additive: an unauthored aspect is simply absent (the round-trip must
    leave it ``None``). At least one aspect is present so the override is meaningful.
    """
    present = draw(
        st.lists(
            st.sampled_from(["label", "visible", "required", "order"]),
            min_size=1,
            max_size=4,
            unique=True,
        )
    )
    spec: dict = {}
    if "label" in present:
        spec["label"] = draw(_i18n_label())
    if "visible" in present:
        spec["visible"] = draw(st.booleans())
    if "required" in present:
        spec["required"] = draw(st.booleans())
    if "order" in present:
        spec["order"] = draw(st.integers(min_value=-50, max_value=50))
    return spec


@st.composite
def _field_overlay(draw):
    """A VALID authored ``field_overlay`` payload: ``{"fields": {...}, "overrides": {...}}``.

    Variable-field keys never collide with a fixed-field key; overrides are keyed by a real
    fixed dotted key.
    """
    field_names = draw(
        st.lists(
            _TOKEN.filter(lambda k: k not in _FIXED_KEYS),
            max_size=4,
            unique=True,
        )
    )
    fields = {name: draw(_overlay_field(name)) for name in field_names}

    override_keys = draw(
        st.lists(st.sampled_from(_FIXED_DOTTED), max_size=4, unique=True)
    )
    overrides = {dotted: draw(_fixed_override()) for dotted in override_keys}
    return {"fields": fields, "overrides": overrides}


# ---------------------------------------------------------------------------
# Expected-normalisation helpers — the SAME normalisation the authored→builder→reader
# path applies, so equivalence is genuine (not a tautology).
# ---------------------------------------------------------------------------


def _expected_dimension(authored: dict) -> dict:
    """What a single authored dimension collapses to after builder + reader normalisation."""
    return {
        "key": authored["key"],
        # field defaults to key for back-compat when not authored.
        "field": authored.get("field") or authored["key"],
        "label": dict(authored.get("label") or {}),
        "enabled": bool(authored.get("enabled", True)),
        "values": tuple(authored.get("values") or ()),
        "required_for": tuple(authored.get("required_for") or ()),
    }


def _actual_dimension(dim) -> dict:
    """The reader's resolved ``ScopeDimension`` projected to the comparable shape."""
    return {
        "key": dim.key,
        "field": dim.field,
        "label": dict(dim.label),
        "enabled": dim.enabled,
        "values": tuple(dim.values),
        "required_for": tuple(dim.required_for),
    }


def _expected_overlay_field(name: str, authored: dict) -> dict:
    """What a single authored overlay field collapses to after builder + reader normalisation."""
    ftype = authored.get("type", "string")
    try:
        resolved_type = FieldType(ftype)
    except (ValueError, TypeError):
        resolved_type = FieldType.STRING
    choices = authored.get("choices")
    return {
        "key": authored.get("key") or name,  # builder defaults key to the map name
        "type": resolved_type,
        "required": bool(authored.get("required", False)),
        "label": dict(authored.get("label") or {}),
        "choices": tuple(choices) if choices is not None else None,
        "visible": bool(authored.get("visible", True)),
        "order": int(authored.get("order", 0) or 0),
    }


def _actual_overlay_field(f) -> dict:
    """The reader's resolved ``OverlayField`` projected to the comparable shape."""
    return {
        "key": f.key,
        "type": f.type,
        "required": f.required,
        "label": dict(f.label),
        "choices": tuple(f.choices) if f.choices is not None else None,
        "visible": f.visible,
        "order": f.order,
    }


def _expected_override(authored: dict) -> dict:
    """What an authored fixed-field override collapses to — absent aspects stay ``None``."""
    def _val(aspect, cast):
        return cast(authored[aspect]) if aspect in authored and authored[aspect] is not None else None

    return {
        "label": dict(authored["label"]) if isinstance(authored.get("label"), dict) else None,
        "visible": _val("visible", bool),
        "required": _val("required", bool),
        "order": _val("order", int),
    }


def _actual_override(o) -> dict:
    return {
        "label": dict(o.label) if o.label is not None else None,
        "visible": o.visible,
        "required": o.required,
        "order": o.order,
    }


# ---------------------------------------------------------------------------
# Property 2a — config#scope round-trips MySQL → projection → resolved provider (R1.1/R1.2)
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(dimensions=_scope_dimensions())
def test_property_config_scope_round_trips(dimensions):
    """Feature: s5b-members-runnable-in-spa, Property 2 (config#scope leg).

    Validates: Requirements 1.1, 1.2, 1.3, 10.6

    Authored ``members.scope_dimensions`` → ``build_config_scope_row`` →
    ``to_dynamodb_item()`` → reader ``get_scope_config`` yields a ``ScopeConfig`` equivalent to
    the authored dimensions (a projection round-trip preserves the scope config).
    """
    params = FakeParameterService(
        {("members", "scope_dimensions", _TENANT_ID): dimensions}
    )

    # authored --builder--> projection row
    row = build_config_scope_row({"administration": _TENANT_ID}, params)
    assert row is not None

    # projection row --> fake table --> reader
    table = FakeTable()
    table.put(row.to_dynamodb_item())
    config = MembersProjectionReader(table=table).get_scope_config(_TENANT_ID)

    # resolved provider shape equivalent to the authored config
    assert isinstance(config, ScopeConfig)
    assert config.tenant_id == _TENANT_ID
    assert [_actual_dimension(d) for d in config.dimensions] == [
        _expected_dimension(a) for a in dimensions
    ]


# ---------------------------------------------------------------------------
# Property 2b — config#fields round-trips MySQL → projection → resolved provider (R1.3)
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(overlay=_field_overlay())
def test_property_config_fields_round_trips(overlay):
    """Feature: s5b-members-runnable-in-spa, Property 2 (config#fields leg).

    Validates: Requirements 1.1, 1.2, 1.3, 10.6

    Authored ``members.field_overlay`` → ``build_config_fields_row`` → ``to_dynamodb_item()`` →
    reader ``get_overlay`` yields a ``TenantOverlay`` equivalent to the authored overlay
    (``FieldType`` converted; override present-only aspects preserved, absent stay ``None``).
    """
    params = FakeParameterService(
        {("members", "field_overlay", _TENANT_ID): overlay}
    )

    # authored --builder--> projection row
    row = build_config_fields_row({"administration": _TENANT_ID}, params)
    assert row is not None

    # projection row --> fake table --> reader
    table = FakeTable()
    table.put(row.to_dynamodb_item())
    resolved = MembersProjectionReader(table=table).get_overlay(_TENANT_ID)

    assert isinstance(resolved, TenantOverlay)

    # Variable fields equivalent to authored (keyed by map name).
    authored_fields = overlay["fields"]
    assert set(resolved.fields.keys()) == set(authored_fields.keys())
    for name, authored_spec in authored_fields.items():
        assert _actual_overlay_field(resolved.fields[name]) == _expected_overlay_field(
            name, authored_spec
        )

    # Fixed-field overrides equivalent to authored (present-only aspects; absent stay None).
    authored_overrides = overlay["overrides"]
    assert set(resolved.overrides.keys()) == set(authored_overrides.keys())
    for dotted, authored_spec in authored_overrides.items():
        assert _actual_override(resolved.overrides[dotted]) == _expected_override(
            authored_spec
        )


# ═══════════════════════════════════════════════════════════════════════════════════════
# S5c Task 1.5 — Property 2 EXTENDED to the broadened base (Fixed ⊕ Calculated) + the new
# overlay-model attributes (functional_groups, functional_group, rich options, member-number
# format).
#
# Feature: s5c-members-runnable-in-spa, Property 2 (extended).
# Validates: Requirements 4, 4.4, 4.9, 4.10, 4.11, 4.12
#
# Two legs, matching what is actually built as of Phase 1:
#
#   2c (full round-trip, broadened base): for any VALID authored ``field_overlay``, the
#       authored→builder→reader→FieldResolver.resolve() path always yields the WHOLE broadened
#       base — one FIXED resolved field per FIXED_FIELDS AND one CALCULATED read-only field per
#       CALCULATED_FIELDS — plus exactly the authored variable fields, with unique dotted keys.
#       (The s5b builder carries the s5b overlay subset; the broadened *base* is code, so it must
#       survive every round-trip regardless of the authored overlay.)
#
#   2d (reader reconstruction of the new attributes): the Phase-1 reader (`get_overlay`)
#       reconstructs a projected ``config#fields`` row that DIRECTLY carries the broadened
#       attributes — a ``functional_groups`` catalog, per-field ``functional_group``, rich enum
#       ``options`` ({value,label,roles?}), and a ``member_number`` format — into an equivalent
#       ``TenantOverlay`` that ``FieldResolver`` then surfaces on the resolved fields. This is the
#       reader leg the module already supports (the authoring UI that WRITES these attributes is
#       Phase 2, tasks 2.x); the strategies compute the same normalisation the reader applies so
#       the equivalence is genuine, not tautological.
# ═══════════════════════════════════════════════════════════════════════════════════════

from sam.members.domain.calculated_fields import CALCULATED_FIELDS
from sam.members.domain.field_resolver import (
    FieldOrigin,
    FieldResolver,
    StaticOverlayProvider,
)
from sam.members.repository.projection_config_reader import MembersProjectionReader as _Reader

import services.projection_schema as _schema  # noqa: F401 (kept explicit for clarity)

_FIXED_DOTTED_SET = frozenset(f.dotted_key() for f in FIXED_FIELDS)
_CALC_DOTTED_SET = frozenset(c.dotted_key() for c in CALCULATED_FIELDS)

# The optional fixed fields (an override may only TIGHTEN optional→required; loosening a
# platform-required field is rejected by the resolver, so a resolver-safe overlay must not).
_OPTIONAL_FIXED_DOTTED = tuple(f.dotted_key() for f in FIXED_FIELDS if not f.required)


@st.composite
def _resolver_safe_field_overlay(draw):
    """A VALID authored ``field_overlay`` that ALSO satisfies the resolver's invariants.

    Reuses the s5b overlay strategy shape but restricts fixed-field overrides to OPTIONAL fixed
    fields (so an override never tries to loosen a platform-required field, which
    ``FieldResolver.resolve`` rejects fail-fast). This lets the property drive the config through
    the FULL authored→builder→reader→resolve path, not just the reader.
    """
    field_names = draw(
        st.lists(_TOKEN.filter(lambda k: k not in _FIXED_KEYS), max_size=4, unique=True)
    )
    fields = {name: draw(_overlay_field(name)) for name in field_names}

    override_keys = draw(
        st.lists(st.sampled_from(_OPTIONAL_FIXED_DOTTED), max_size=4, unique=True)
    )
    overrides = {dotted: draw(_fixed_override()) for dotted in override_keys}
    return {"fields": fields, "overrides": overrides}


# ---------------------------------------------------------------------------
# Property 2c — the broadened base survives the full round-trip
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(overlay=_resolver_safe_field_overlay())
def test_property_broadened_base_survives_round_trip(overlay):
    """Feature: s5c-members-runnable-in-spa, Property 2 (broadened-base leg).

    Validates: Requirements 4, 4.4, 4.10

    Authored ``members.field_overlay`` → ``build_config_fields_row`` → ``to_dynamodb_item()`` →
    reader ``get_overlay`` → ``FieldResolver.resolve()`` always reproduces the WHOLE broadened
    base: every fixed field (origin FIXED) AND every calculated field (origin CALCULATED,
    read-only), plus exactly the authored variable fields — with all dotted keys unique.
    """
    params = FakeParameterService({("members", "field_overlay", _TENANT_ID): overlay})

    row = build_config_fields_row({"administration": _TENANT_ID}, params)
    assert row is not None

    table = FakeTable()
    table.put(row.to_dynamodb_item())
    reader = MembersProjectionReader(table=table)

    cfg = FieldResolver(reader).resolve(_TENANT_ID)
    dotted = [f.dotted_key() for f in cfg.fields]

    # The broadened base is fully present, regardless of what the overlay added.
    fixed = {f.dotted_key() for f in cfg.fields if f.origin is FieldOrigin.FIXED}
    calc = {f.dotted_key() for f in cfg.fields if f.origin is FieldOrigin.CALCULATED}
    assert fixed == _FIXED_DOTTED_SET
    assert calc == _CALC_DOTTED_SET
    # Every calculated field is read-only and carries its inputs.
    assert all(f.read_only and f.calculated_from for f in cfg.calculated_fields())
    # Exactly the authored variable fields, and no key collisions anywhere.
    assert len(cfg.variable_fields()) == len(overlay["fields"])
    assert len(dotted) == len(set(dotted))


# ---------------------------------------------------------------------------
# Property 2d — the functional_groups catalog round-trips through the projection reader
# ---------------------------------------------------------------------------
#
# Scope note (what is actually built as of Phase 1): the module reader
# (``MembersProjectionReader.get_overlay``) reconstructs the ``functional_groups`` CATALOG from a
# projected ``config#fields`` row. The per-field / per-override reconstruction of the OTHER new
# attributes (a field's ``functional_group``, rich ``options``, ``show_when``, a
# ``member_number`` format) is wired by the Phase-2 authoring path (tasks 2.x, `[~]`), so it is
# asserted at the domain layer in Property 2e below, not here. This test asserts only the leg the
# reader supports today.
# ---------------------------------------------------------------------------


@st.composite
def _functional_groups_catalog(draw):
    """A ``functional_groups`` catalog: 1..4 entries with unique keys."""
    keys = draw(st.lists(_TOKEN, min_size=1, max_size=4, unique=True))
    return [
        {"key": k, "label": draw(_i18n_label()), "order": draw(st.integers(0, 20))}
        for k in keys
    ]


def _config_fields_item(row_attrs: dict) -> dict:
    """Wrap a raw ``config#fields`` attribute dict into a projected DynamoDB item."""
    item = {
        _schema.PARTITION_KEY_ATTR: _TENANT_ID,
        _schema.SORT_KEY_ATTR: _schema.build_sort_key(_schema.RECORD_TYPE_CONFIG, "fields"),
    }
    item.update(row_attrs)
    return item


@settings(max_examples=100)
@given(catalog=_functional_groups_catalog())
def test_property_functional_groups_catalog_round_trips(catalog):
    """Feature: s5c-members-runnable-in-spa, Property 2 (functional-group catalog leg).

    Validates: Requirements 4.9, 4.10

    A projected ``config#fields`` row carrying a ``functional_groups`` catalog reads back through
    ``get_overlay`` into a ``TenantOverlay`` whose catalog is equivalent (keys + order preserved),
    and the resolver still yields the whole broadened base over it — never a crash.
    """
    table = FakeTable()
    table.put(_config_fields_item({"functional_groups": catalog, "fields": {}, "fixed_overrides": {}}))
    overlay = _Reader(table=table).get_overlay(_TENANT_ID)
    assert isinstance(overlay, TenantOverlay)

    # Catalog reconstructed 1:1 (keys + order).
    assert set(overlay.functional_groups) == {g["key"] for g in catalog}
    for g in catalog:
        assert overlay.functional_groups[g["key"]].order == int(g.get("order", 0) or 0)

    # The resolver still produces the whole broadened base over the reconstructed overlay.
    cfg = FieldResolver(StaticOverlayProvider({_TENANT_ID: overlay})).resolve(_TENANT_ID)
    dotted = {f.dotted_key() for f in cfg.fields}
    assert _FIXED_DOTTED_SET.issubset(dotted)
    assert _CALC_DOTTED_SET.issubset(dotted)


# ---------------------------------------------------------------------------
# Property 2e — the new overlay-model attributes round-trip at the domain layer
# (TenantOverlay ⊕ the broadened attributes → FieldResolver.resolve surfaces them)
# ---------------------------------------------------------------------------

from sam.members.domain.field_resolver import (  # noqa: E402
    FixedFieldOverride,
    FunctionalGroup,
    OverlayField,
)
from sam.members.domain.fixed_fields import (  # noqa: E402
    EnumOption,
    FieldType,
    MemberNumberFormat,
)

_ROLE = st.sampled_from(["Members_CRUD", "Members_Read", "System_User_Management"])


@st.composite
def _enum_options(draw):
    """A non-empty list of rich enum options ``{value, label, roles?}`` with unique values."""
    values = draw(st.lists(_TOKEN, min_size=1, max_size=3, unique=True))
    opts = []
    for v in values:
        roles = draw(st.one_of(st.none(), st.lists(_ROLE, min_size=1, max_size=2, unique=True)))
        opts.append(
            EnumOption(value=v, label=draw(_i18n_label()), roles=tuple(roles) if roles else None)
        )
    return tuple(opts)


@st.composite
def _rich_domain_overlay(draw):
    """A ``TenantOverlay`` carrying the broadened per-field/override attributes (Phase-1 domain).

    A ``functional_groups`` catalog; a variable enum field carrying ``functional_group`` + rich
    ``options`` + ``show_when``; and a ``member_number`` override carrying a format. Everything is
    constructed so ``FieldResolver.resolve`` accepts it (functional_group references the catalog).
    """
    group_keys = draw(st.lists(_TOKEN, min_size=1, max_size=3, unique=True))
    catalog = {k: FunctionalGroup(key=k, order=i) for i, k in enumerate(group_keys)}

    fname = draw(_TOKEN.filter(lambda k: k not in _FIXED_KEYS))
    options = draw(_enum_options())
    show_when = {"field": "membership.membership_type", "in": draw(st.lists(_TOKEN, min_size=1, max_size=2))}
    ovl_field = OverlayField(
        key=fname,
        type=FieldType.ENUM,
        options=options,
        functional_group=draw(st.sampled_from(group_keys)),
        show_when=show_when,
    )

    fmt = MemberNumberFormat(prefix=draw(st.sampled_from(["Nr-", "M", ""])), width=draw(st.integers(1, 6)))
    overrides = {"membership.member_number": FixedFieldOverride(member_number_format=fmt)}

    overlay = TenantOverlay(
        fields={fname: ovl_field}, overrides=overrides, functional_groups=catalog
    )
    return overlay, fname, options, show_when, fmt


@settings(max_examples=100)
@given(built=_rich_domain_overlay())
def test_property_new_overlay_attributes_surface_on_resolved_fields(built):
    """Feature: s5c-members-runnable-in-spa, Property 2 (new-attributes domain leg).

    Validates: Requirements 4.9, 4.11, 4.12, 4.2, 4.8

    For any valid ``TenantOverlay`` carrying the broadened attributes, ``FieldResolver.resolve``
    surfaces them onto the resolved fields: a variable field's ``functional_group`` + rich
    ``options`` (with role gates) + ``show_when``, and the ``member_number`` format — while the
    whole broadened base survives and nothing raises.
    """
    overlay, fname, options, show_when, fmt = built
    cfg = FieldResolver(StaticOverlayProvider({_TENANT_ID: overlay})).resolve(_TENANT_ID)

    # The broadened base survives.
    dotted = {f.dotted_key() for f in cfg.fields}
    assert _FIXED_DOTTED_SET.issubset(dotted)
    assert _CALC_DOTTED_SET.issubset(dotted)

    # The variable field surfaces its functional_group, options (values + role gates), show_when.
    resolved = cfg.field(f"overlay.{fname}")
    assert resolved is not None
    assert resolved.functional_group == overlay.fields[fname].functional_group
    assert resolved.options is not None
    assert tuple(o.value for o in resolved.options) == tuple(o.value for o in options)
    for authored, got in zip(options, resolved.options):
        assert got.roles == authored.roles
    # choices stay coherent with the rich options.
    assert tuple(resolved.choices) == tuple(o.value for o in options)
    assert resolved.show_when == show_when

    # The member_number format surfaces on the resolved member_number field.
    mn = cfg.field("membership.member_number")
    assert mn.member_number_format == fmt


# ═══════════════════════════════════════════════════════════════════════════════════════
# S5c Task 3.1 — Property 2 EXTENDED: view_contexts round-trips MySQL → projection → reader
# via the SIBLING config#views row (Open Design Item 1, settled).
#
# Feature: s5c-members-runnable-in-spa, Property 2 (view_contexts leg).
# Validates: Requirements 5.1
#
# For any VALID authored members.view_contexts, building the config#views row via
# build_config_views_row and reading it back through get_view_contexts yields ViewContexts
# equivalent to the authored contexts. Plus the empty-is-valid collapse: no/empty
# view_contexts → exactly one default context.
# ═══════════════════════════════════════════════════════════════════════════════════════


@st.composite
def _view_context(draw, key: str):
    """A single VALID authored view-context dict for a given (unique) ``key``."""
    columns = draw(st.lists(_TOKEN, min_size=1, max_size=5, unique=True))
    # filterable is a subset of columns (the common, well-formed case).
    filterable = draw(st.lists(st.sampled_from(columns), max_size=len(columns), unique=True))
    default_sort = draw(
        st.one_of(
            st.none(),
            st.builds(
                lambda f, d: {"field": f, "direction": d},
                st.sampled_from(columns),
                st.sampled_from(["asc", "desc"]),
            ),
        )
    )
    return {
        "key": key,
        "label": draw(_i18n_label()),
        "permission_roles": draw(st.lists(_TOKEN, max_size=3, unique=True)),
        "columns": columns,
        "filterable_columns": filterable,
        "default_sort": default_sort,
        "page_size": draw(st.one_of(st.none(), st.integers(min_value=1, max_value=500))),
    }


@st.composite
def _view_contexts(draw):
    """A list of 1..4 VALID authored view contexts with UNIQUE keys (never DEFAULT_CONTEXT_KEY)."""
    keys = draw(
        st.lists(
            _TOKEN.filter(lambda k: k != DEFAULT_CONTEXT_KEY),
            min_size=1,
            max_size=4,
            unique=True,
        )
    )
    return [draw(_view_context(key)) for key in keys]


def _expected_view_context(authored: dict) -> dict:
    """What a single authored view context collapses to after builder + reader normalisation."""
    default_sort = authored.get("default_sort")
    return {
        "key": authored["key"],
        "label": dict(authored.get("label") or {}),
        "permission_roles": tuple(authored.get("permission_roles") or ()),
        "columns": tuple(authored.get("columns") or ()),
        "filterable_columns": tuple(authored.get("filterable_columns") or ()),
        "default_sort": dict(default_sort) if isinstance(default_sort, dict) else None,
        "page_size": authored.get("page_size"),
    }


def _actual_view_context(ctx) -> dict:
    """The reader's resolved ``ViewContext`` projected to the comparable shape."""
    return {
        "key": ctx.key,
        "label": dict(ctx.label),
        "permission_roles": tuple(ctx.permission_roles),
        "columns": tuple(ctx.columns),
        "filterable_columns": tuple(ctx.filterable_columns),
        "default_sort": dict(ctx.default_sort) if ctx.default_sort is not None else None,
        "page_size": ctx.page_size,
    }


@settings(max_examples=100)
@given(contexts=_view_contexts())
def test_property_config_views_round_trips(contexts):
    """Feature: s5c-members-runnable-in-spa, Property 2 (config#views leg).

    Validates: Requirements 5.1

    Authored ``members.view_contexts`` → ``build_config_views_row`` → ``to_dynamodb_item()`` →
    reader ``get_view_contexts`` yields ``ViewContext``s equivalent to the authored contexts
    (a projection round-trip through the sibling config#views row preserves the view contexts).
    """
    params = FakeParameterService(
        {("members", "view_contexts", _TENANT_ID): contexts}
    )

    row = build_config_views_row({"administration": _TENANT_ID}, params)
    assert row is not None

    table = FakeTable()
    table.put(row.to_dynamodb_item())
    resolved = MembersProjectionReader(table=table).get_view_contexts(_TENANT_ID)

    assert [_actual_view_context(c) for c in resolved] == [
        _expected_view_context(a) for a in contexts
    ]


def test_property_config_views_empty_is_one_default_context():
    """Feature: s5c-members-runnable-in-spa, Property 2 (empty-is-valid leg).

    Validates: Requirements 5.1

    A tenant that authored no view_contexts → builder emits an empty ``contexts`` row →
    the reader collapses it to EXACTLY ONE default context (over all visible fields).
    """
    params = FakeParameterService({})  # nothing authored

    row = build_config_views_row({"administration": _TENANT_ID}, params)
    assert row.attributes["contexts"] == []

    table = FakeTable()
    table.put(row.to_dynamodb_item())
    resolved = MembersProjectionReader(table=table).get_view_contexts(_TENANT_ID)

    assert len(resolved) == 1
    assert resolved[0].key == DEFAULT_CONTEXT_KEY
