"""
Pagination precedence — Property 1 (SAM leg), Phase 2 task 2.2.

**Property 1: Pagination precedence is total and deterministic.**
The resolved rows-per-page equals the first present of
``userPreference → default_page_size → platformDefault`` and is always a positive integer.

On the SAM plane the precedence resolver is effectively the reader
``MembersProjectionReader.get_default_page_size`` (the ``default_page_size`` leg of the
chain) plus the renderer precedence surfaced on the field-config response. There is NO shared
precedence FUNCTION on the SAM side — the resolver lives on the SPA
(``frontend/src/pages/membersPagination.ts``, covered by
``membersPagination.property.test.ts``). So this SAM property is focused, per the task, on the
reader's **positive-int-or-None guarantee**: whatever stray value a ``config#fields`` row
carries under ``default_page_size``, the reader returns a POSITIVE INT or ``None`` — never a
zero/negative/NaN/boolean/non-int default leaks into the precedence chain. That guarantee is
exactly what makes the SPA precedence rule total ("the tenantDefault leg is a positive int or
absent, never a poisoned value").

**Validates: Requirements 2.2, 2.3, 2.4, 9.4**

DynamoDB is faked in-memory (mirrors ``test_members_projection_reader.py``) — no live AWS, no
MySQL. hypothesis drives the generated projected values.
"""

import os
import sys

from hypothesis import given, settings
from hypothesis import strategies as st

# repo root + backend/src on sys.path (mirrors sam/conftest.py + the sibling reader test, so
# `sam.members` and `services.projection_schema` resolve).
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)
_BACKEND_SRC = os.path.join(_REPO_ROOT, "backend", "src")
if _BACKEND_SRC not in sys.path:
    sys.path.insert(0, _BACKEND_SRC)

from services import projection_schema as schema

from sam.members.repository.projection_config_reader import MembersProjectionReader


# ---------------------------------------------------------------------------
# In-memory fake DynamoDB table (query side only) — mirrors test_members_projection_reader.py
# ---------------------------------------------------------------------------


class FakeTable:
    def __init__(self):
        self.store: dict[tuple, dict] = {}

    def put(self, item: dict) -> None:
        key = (item[schema.PARTITION_KEY_ATTR], item[schema.SORT_KEY_ATTR])
        self.store[key] = dict(item)

    def query(self, KeyConditionExpression=None):
        tenant_id = _tenant_from_condition(KeyConditionExpression)
        items = [dict(v) for k, v in self.store.items() if k[0] == tenant_id]
        return {"Items": items}


def _tenant_from_condition(condition):
    expr = condition.get_expression()
    return expr["values"][1]


def _config_fields_item(tenant_id, *, default_page_size=..., version=1):
    """A ``config#fields`` row; set ``default_page_size`` only when a value is supplied."""
    item = {
        schema.PARTITION_KEY_ATTR: tenant_id,
        schema.SORT_KEY_ATTR: schema.build_sort_key(schema.RECORD_TYPE_CONFIG, "fields"),
        "fields": {},
        "overrides": {},
        schema.VERSION_ATTR: version,
    }
    if default_page_size is not ...:
        item["default_page_size"] = default_page_size
    return item


# ---------------------------------------------------------------------------
# Generators
# ---------------------------------------------------------------------------

_TENANT_ID = st.text(
    alphabet="abcdefghijklmnopqrstuvwxyz0123456789-", min_size=1, max_size=24
)

# A POSITIVE int page size — the only shape that is a usable default.
_positive_int = st.integers(min_value=1, max_value=100_000)

# Values that must collapse to None (the read-side fail-safe guard, R2.4): non-positive ints,
# booleans, non-ints, and absent.
_non_positive_int = st.integers(max_value=0)
_bool = st.booleans()
_non_int = st.one_of(
    st.text(max_size=6),
    st.floats(allow_nan=True, allow_infinity=True),
    st.none(),
    st.lists(st.integers(), max_size=3),
    st.dictionaries(st.text(max_size=3), st.integers(), max_size=3),
)
_unusable = st.one_of(_non_positive_int, _bool, _non_int)


# ---------------------------------------------------------------------------
# Property 1 (SAM leg): get_default_page_size returns a positive int or None — total,
# never a poisoned value, so the SPA precedence chain's tenantDefault leg is always safe.
# ---------------------------------------------------------------------------


@settings(max_examples=200)
@given(tenant_id=_TENANT_ID, page_size=_positive_int)
def test_property_authored_positive_page_size_is_returned_verbatim(tenant_id, page_size):
    """A projected POSITIVE ``default_page_size`` is returned as that exact positive int (R2.2)."""
    table = FakeTable()
    table.put(_config_fields_item(tenant_id, default_page_size=page_size))

    resolved = MembersProjectionReader(table=table).get_default_page_size(tenant_id)

    assert resolved == page_size
    assert isinstance(resolved, int) and not isinstance(resolved, bool)
    assert resolved > 0


@settings(max_examples=200)
@given(tenant_id=_TENANT_ID, raw=_unusable)
def test_property_unusable_page_size_collapses_to_none(tenant_id, raw):
    """Any non-positive / non-int / boolean stored value collapses to None (R2.4 fail-safe)."""
    table = FakeTable()
    table.put(_config_fields_item(tenant_id, default_page_size=raw))

    resolved = MembersProjectionReader(table=table).get_default_page_size(tenant_id)

    assert resolved is None


@settings(max_examples=100)
@given(tenant_id=_TENANT_ID)
def test_property_absent_attribute_or_row_is_none(tenant_id):
    """A ``config#fields`` row with no ``default_page_size``, and a missing row, both → None."""
    # Row present, attribute absent.
    table = FakeTable()
    table.put(_config_fields_item(tenant_id))
    assert MembersProjectionReader(table=table).get_default_page_size(tenant_id) is None

    # No row at all (unconfigured tenant).
    assert MembersProjectionReader(table=FakeTable()).get_default_page_size(tenant_id) is None


@settings(max_examples=200)
@given(
    tenant_id=_TENANT_ID,
    stored=st.one_of(_positive_int, _unusable),
)
def test_property_result_is_always_positive_int_or_none(tenant_id, stored):
    """Totality: over ANY stored value, the reader yields a positive int OR None — never a
    zero/negative/NaN/boolean default (the invariant the SPA precedence chain relies on)."""
    table = FakeTable()
    table.put(_config_fields_item(tenant_id, default_page_size=stored))

    resolved = MembersProjectionReader(table=table).get_default_page_size(tenant_id)

    assert resolved is None or (
        isinstance(resolved, int) and not isinstance(resolved, bool) and resolved > 0
    )


@settings(max_examples=100)
@given(tenant_id=_TENANT_ID, stored=st.one_of(_positive_int, _unusable, st.none()))
def test_property_reader_is_deterministic(tenant_id, stored):
    """Determinism: the same stored row resolves to the same result every time."""
    table = FakeTable()
    table.put(_config_fields_item(tenant_id, default_page_size=stored))
    reader = MembersProjectionReader(table=table)

    assert reader.get_default_page_size(tenant_id) == reader.get_default_page_size(tenant_id)
