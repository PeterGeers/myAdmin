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
from services.projection_sync import build_config_fields_row, build_config_scope_row

from sam.members.domain.field_resolver import TenantOverlay
from sam.members.domain.fixed_fields import FIXED_FIELDS, FieldType
from sam.members.domain.scope_dimensions import ScopeConfig
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
    construct it: an *enabled* dimension declares ≥1 unique non-blank value, and ``all_wildcard``
    (if any) is never one of those values.
    """
    enabled = draw(st.booleans())
    # A unique, non-blank value set. Enabled dimensions MUST have ≥1 value (validation rule);
    # a disabled dimension may have any (its body is ignored) — keep ≥1 for simplicity.
    values = draw(
        st.lists(_TOKEN, min_size=1, max_size=5, unique=True)
    )
    # all_wildcard is a ROLE name, and must not collide with any scope value.
    all_wildcard = draw(
        st.one_of(
            st.none(),
            _TOKEN.filter(lambda w: w not in values),
        )
    )
    return {
        "key": key,
        "label": draw(_i18n_label()),
        "enabled": enabled,
        "multi_valued": draw(st.booleans()),
        "values": values,
        "all_wildcard": all_wildcard,
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
        "label": dict(authored.get("label") or {}),
        "enabled": bool(authored.get("enabled", True)),
        "multi_valued": bool(authored.get("multi_valued", False)),
        "values": tuple(authored.get("values") or ()),
        "all_wildcard": authored.get("all_wildcard"),
        "required_for": tuple(authored.get("required_for") or ()),
    }


def _actual_dimension(dim) -> dict:
    """The reader's resolved ``ScopeDimension`` projected to the comparable shape."""
    return {
        "key": dim.key,
        "label": dict(dim.label),
        "enabled": dim.enabled,
        "multi_valued": dim.multi_valued,
        "values": tuple(dim.values),
        "all_wildcard": dim.all_wildcard,
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
