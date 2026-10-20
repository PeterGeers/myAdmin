"""
Spec 02 (members-config-sam-owned-write-path) Task 3.2 — **Property 1**: round-trip
write/read equivalence for ``config#scope`` through the SAM-owned write path.

Validates: Requirements 8.1, 8.2, 8.3, 8.5, 1.5

What this asserts (the SAM write path round-trip)
-------------------------------------------------
Task 3.1 made the per-field ``scope`` attribute on the SAM-owned ``config#fields`` overlay the
SINGLE authoring source for ``config#scope`` and REMOVED the legacy standalone
``members.scope_dimensions`` fallback (the dead-toggle defect). So the old Property-2
equivalence between the two authoring representations (standalone list vs field attribute) is
MOOT — there is only one source now. This file is re-homed onto the property that matters for
the SAM-owned write path:

    put_config('scope', {dimensions}) --DynamoDB-- get_scope_config --> ScopeConfig

For ANY valid set of scope dimensions written through
:class:`~sam.members.repository.projection_config_write_repository.MembersConfigWriteRepository`,
reading the row back through the UNCHANGED
:class:`~sam.members.repository.projection_config_reader.MembersProjectionReader`
``get_scope_config`` yields a :class:`ScopeConfig` **equivalent to what was written** (same
keys, fields, enabled flags, values, labels, required_for). An EMPTY ``dimensions`` set
round-trips to a tenant-wide config (``is_tenant_wide()``), never an error (R1.6 / R8.5).

Genuine (non-tautological) equivalence
---------------------------------------
The reader normalises each projected dimension dict onto a :class:`ScopeDimension` (fills
defaults, ``field`` defaults to ``key``, list→tuple, drops unknown keys). The strategies here
generate ONLY the written ``dimensions`` input shape and the assertions compute the SAME
normalisation the write→read path applies — so this asserts real round-trip fidelity, not that
two identical dicts are equal. The generators are constrained to VALID dimensions (unique
non-blank keys; an enabled dimension declares ≥1 unique non-blank value; no ``all_wildcard`` /
``multi_valued``) so the reader's ``ScopeConfig`` construction never raises.

No live AWS: the writer puts into an in-memory fake exposing ``put_item`` and the reader queries
the same fake's ``query`` surface (mirrors ``sam/tests/test_config_roundtrip_props.py``).
"""

import os
import sys

from hypothesis import given, settings
from hypothesis import strategies as st

# repo root on sys.path (mirrors sam/conftest.py) so `sam.members` imports.
_REPO_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

# backend/src on sys.path so the shared `services.projection_schema` resolves (mirrors
# test_config_roundtrip_props.py — the projection schema is shared across both planes).
_BACKEND_SRC = os.path.join(_REPO_ROOT, "backend", "src")
if _BACKEND_SRC not in sys.path:
    sys.path.insert(0, _BACKEND_SRC)

from services import projection_schema as schema

from sam.members.domain.config_write_version import next_write_stamp
from sam.members.domain.scope_dimensions import ScopeConfig
from sam.members.repository.projection_config_reader import MembersProjectionReader
from sam.members.repository.projection_config_write_repository import (
    MembersConfigWriteRepository,
)
from sam.tests.test_config_roundtrip_props import FakeTable

_TENANT_ID = "scope-roundtrip-tenant"


class WritableFakeTable(FakeTable):
    """A :class:`FakeTable` that also exposes the boto3 ``put_item(Item=...)`` surface the
    write repository calls, so the SAME in-memory store is written by the repository and read
    by the reader's ``query`` — a real write→read round-trip with no live AWS."""

    def put_item(self, Item):
        self.put(Item)


# ---------------------------------------------------------------------------
# Strategies — a VALID set of written scope dimensions (the config#scope body)
# ---------------------------------------------------------------------------

_TOKEN = st.text(
    alphabet="abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_",
    min_size=1,
    max_size=12,
)


def _i18n_label():
    return st.dictionaries(
        keys=st.sampled_from(["nl", "en", "de", "fr"]),
        values=st.text(min_size=1, max_size=20),
        max_size=4,
    )


@st.composite
def _dimension(draw, key: str):
    """One VALID ``config#scope`` dimension dict (the ScopeDimension shape the reader reads).

    An enabled dimension declares ≥1 unique non-blank value (the ``ScopeConfig`` validation rule
    the reader re-applies). ``field`` is written as the dimension's own key (the canonical
    binding; the reader defaults ``field`` to ``key`` anyway). No ``all_wildcard`` /
    ``multi_valued`` (s5d clean break, R8.1).
    """
    return {
        "key": key,
        "field": key,
        "enabled": draw(st.booleans()),
        "values": draw(st.lists(_TOKEN, min_size=1, max_size=5, unique=True)),
        "label": draw(_i18n_label()),
        "required_for": draw(st.lists(_TOKEN, max_size=3, unique=True)),
    }


@st.composite
def _dimensions(draw):
    """A list of 1..4 VALID dimensions with UNIQUE keys."""
    keys = draw(st.lists(_TOKEN, min_size=1, max_size=4, unique=True))
    return [draw(_dimension(key)) for key in keys]


def _write_then_read(dimensions) -> ScopeConfig:
    """put_config('scope', {dimensions}) into a fake table, then read it back via the reader."""
    table = WritableFakeTable()
    repo = MembersConfigWriteRepository(table=table)
    repo.put_config(
        tenant_id=_TENANT_ID,
        config_id=schema.CONFIG_ID_SCOPE,
        attributes={"dimensions": dimensions},
        version=next_write_stamp(),
    )
    return MembersProjectionReader(table=table).get_scope_config(_TENANT_ID)


def _expected(dimensions):
    """The normalisation the reader applies (field defaults to key; list→tuple; defaults)."""
    return [
        {
            "key": d["key"],
            "field": d.get("field") or d["key"],
            "enabled": bool(d.get("enabled", True)),
            "values": tuple(d.get("values") or ()),
            "label": dict(d.get("label") or {}),
            "required_for": tuple(d.get("required_for") or ()),
        }
        for d in dimensions
    ]


def _comparable(cfg: ScopeConfig):
    return [
        {
            "key": d.key,
            "field": d.field,
            "enabled": d.enabled,
            "values": tuple(d.values),
            "label": dict(d.label),
            "required_for": tuple(d.required_for),
        }
        for d in cfg.dimensions
    ]


# ---------------------------------------------------------------------------
# Property 1 — round-trip write/read equivalence for config#scope.
# ---------------------------------------------------------------------------


@settings(max_examples=200)
@given(dimensions=_dimensions())
def test_property_config_scope_write_read_round_trips(dimensions):
    """Feature: members-config-sam-owned-write-path, Property 1 (config#scope).

    Validates: Requirements 8.1, 8.2, 8.3, 8.5, 1.5

    For ANY valid dimensions written through the SAM-owned write repository, the reader rebuilds
    a ``ScopeConfig`` whose dimensions equal (after the reader's normalisation) what was written
    — the write→read round-trip preserves the config.
    """
    resolved = _write_then_read(dimensions)
    assert _comparable(resolved) == _expected(dimensions)


def test_empty_dimensions_round_trips_to_tenant_wide():
    """R8.5 / R1.6: an EMPTY written ``dimensions`` list reads back as a tenant-wide config
    (``is_tenant_wide()``), never an error."""
    resolved = _write_then_read([])
    assert resolved.dimensions == ()
    assert resolved.is_tenant_wide()


def test_unwritten_scope_row_reads_tenant_wide():
    """A tenant with NO ``config#scope`` row at all reads back tenant-wide (missing row → empty,
    R1.6) — the reader never raises on an unconfigured tenant."""
    table = WritableFakeTable()
    resolved = MembersProjectionReader(table=table).get_scope_config(_TENANT_ID)
    assert resolved.dimensions == ()
    assert resolved.is_tenant_wide()
