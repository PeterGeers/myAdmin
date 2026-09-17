"""Property-based test for S3 governance projection write-time validation (T15, R5.5).

Feature: s3-claims-and-projection
Property 5: Write-time validation rejects malformed rows

Validates: Requirements R5.5

This exercises the pure ``ProjectionValidator`` surface (T14,
``services.projection_validator``) — ``validate_item`` / ``is_valid_item`` /
``validate_items`` / ``ProjectionValidationError`` — over a large generated
space of ``ProjectionItem`` values that deliberately mixes **well-formed** and
**malformed** items. The malformed cases mirror the design.md D3 "Write-time
validation (R5.5)" hazards:

  * missing / blank / whitespace / ``None`` tenant key (the cross-tenant hazard),
  * missing / malformed sort key (blank, or a ``module``/``role`` key with no id),
  * missing version (``None``),
  * a record type missing its required field (module ``is_active`` absent or
    non-bool; role ``email``/``role`` absent or blank).

Property 5 asserts three things:

  1. an item missing its tenant key or a required field is **always** rejected
     (``validate_item`` raises ``ProjectionValidationError``, so no partial or
     malformed item would be written);
  2. a well-formed item is **always** accepted (returned unchanged);
  3. in ``validate_items``, a batch containing one malformed item **raises**
     (no partial write) while each of its valid siblings would pass on its own —
     "the rest of the projection is unaffected".

The validator is pure (no I/O), so no MySQL/DynamoDB fakes are needed. The
expected verdict is computed by an **independent oracle** in this test — it does
not call the validator — so the property checks the validator against a
separately derived specification of "well-formed", not against itself.
"""

import os
import sys

import pytest
from hypothesis import given, settings, strategies as st

sys.path.append(os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from services import projection_schema as schema  # noqa: E402
from services.projection_builder import ProjectionItem  # noqa: E402
from services.projection_validator import (  # noqa: E402
    ProjectionValidationError,
    is_valid_item,
    validate_item,
    validate_items,
)


# ---------------------------------------------------------------------------
# Independent oracle — "is this item well-formed?" (does NOT use the validator)
#
# Derived independently from design.md D3 "Write-time validation (R5.5)" and the
# record shapes: tenant key present + non-blank; sort key present + well-formed
# (parseable, non-blank segments, module/role carry an id segment); version
# present (not None); required per-record-type attributes well-formed.
# ---------------------------------------------------------------------------

_RECORD_TYPES_REQUIRING_ID = {schema.RECORD_TYPE_MODULE, schema.RECORD_TYPE_ROLE}


def _blank(value) -> bool:
    """A required string-like value is blank if None or empty/whitespace-only."""
    if value is None:
        return True
    return isinstance(value, str) and value.strip() == ""


def _oracle_is_well_formed(item: ProjectionItem) -> bool:
    """Independently decide whether ``item`` should pass write-time validation.

    Mirrors the R5.5 contract without calling the validator, so the property
    tests the validator against a separately derived spec rather than itself.
    """
    # 2) Tenant key (partition key) present + non-blank.
    if _blank(item.tenant_id):
        return False

    # 3) Sort key present + well-formed.
    if _blank(item.sort_key):
        return False
    try:
        record_type, id_parts = schema.split_sort_key(item.sort_key)
    except ValueError:
        return False
    if _blank(record_type):
        return False
    if any(_blank(part) for part in id_parts):
        return False
    if record_type in _RECORD_TYPES_REQUIRING_ID and not id_parts:
        return False

    # 4) Version present (not None). Note: 0 is present, not blank.
    if item.version is None:
        return False

    # 5) Record-type required attributes well-formed.
    attrs = item.attributes or {}
    if record_type == schema.RECORD_TYPE_MODULE:
        if "is_active" not in attrs or not isinstance(attrs["is_active"], bool):
            return False
    elif record_type == schema.RECORD_TYPE_ROLE:
        if _blank(attrs.get("email")) or _blank(attrs.get("role")):
            return False

    return True


# ---------------------------------------------------------------------------
# Strategies
#
# Generate ProjectionItems drawn from a mixture of well-formed and malformed
# shapes so both branches of the property are exercised. Segments avoid the
# sort-key separator "#" (its presence is an orthogonal build_sort_key concern);
# the malformed sort keys are produced explicitly rather than via build_sort_key.
# ---------------------------------------------------------------------------

# Non-empty, separator-free text for keys/segments.
_seg_text = st.text(
    alphabet=st.characters(blacklist_characters="#", blacklist_categories=("Cs", "Cc")),
    min_size=1,
    max_size=12,
)

# A tenant key that may be present-and-good OR one of the blank hazards.
tenant_id_st = st.one_of(
    _seg_text,                    # good
    st.just(""),                  # empty
    st.just("   "),               # whitespace
    st.none(),                    # None
)

# A version that may be present (incl. 0) OR missing (None).
version_st = st.one_of(
    st.integers(min_value=0, max_value=10_000),
    st.text(min_size=1, max_size=8),
    st.none(),                    # missing version -> malformed
)


def _tenant_sort_key_st():
    """Sort keys for a 'tenant' record: the good one plus blank/malformed cases."""
    return st.one_of(
        st.just(schema.build_sort_key(schema.RECORD_TYPE_TENANT)),  # "tenant" (good)
        st.just(""),                                                # blank (malformed)
    )


def _module_sort_key_st():
    """Sort keys for a 'module' record: with id (good) and without id (malformed)."""
    return st.one_of(
        _seg_text.map(lambda n: schema.build_sort_key(schema.RECORD_TYPE_MODULE, n)),
        st.just(schema.RECORD_TYPE_MODULE),   # "module" with no id -> malformed
        st.just(""),                          # blank -> malformed
    )


def _role_sort_key_st():
    """Sort keys for a 'role' record: with email+role (good) and without (malformed)."""
    return st.one_of(
        st.tuples(_seg_text, _seg_text).map(
            lambda er: schema.build_sort_key(schema.RECORD_TYPE_ROLE, er[0], er[1])
        ),
        st.just(schema.RECORD_TYPE_ROLE),     # "role" with no id -> malformed
        st.just(""),                          # blank -> malformed
    )


# module attributes: good bool, missing, or wrong type.
_module_attrs_st = st.one_of(
    st.booleans().map(lambda b: {"is_active": b}),   # good
    st.just({}),                                     # missing is_active -> malformed
    st.just({"is_active": "yes"}),                   # non-bool -> malformed
)

# role attributes: good pair, or one missing/blank.
_role_attrs_st = st.one_of(
    st.tuples(_seg_text, _seg_text).map(lambda er: {"email": er[0], "role": er[1]}),  # good
    st.just({"email": "a@b.example"}),               # missing role -> malformed
    st.just({"role": "Reader"}),                     # missing email -> malformed
    st.just({"email": "   ", "role": "Reader"}),     # blank email -> malformed
)


def _tenant_item_st():
    return st.builds(
        ProjectionItem,
        tenant_id=tenant_id_st,
        sort_key=_tenant_sort_key_st(),
        version=version_st,
        attributes=st.just({"display_name": "Example"}),
    )


def _module_item_st():
    return st.builds(
        ProjectionItem,
        tenant_id=tenant_id_st,
        sort_key=_module_sort_key_st(),
        version=version_st,
        attributes=_module_attrs_st,
    )


def _role_item_st():
    return st.builds(
        ProjectionItem,
        tenant_id=tenant_id_st,
        sort_key=_role_sort_key_st(),
        version=version_st,
        attributes=_role_attrs_st,
    )


def projection_item_st():
    """A ProjectionItem mixing well-formed and every malformed hazard shape."""
    return st.one_of(_tenant_item_st(), _module_item_st(), _role_item_st())


# ---------------------------------------------------------------------------
# Property 5: Write-time validation rejects malformed rows
# ---------------------------------------------------------------------------


@settings(max_examples=200)
@given(item=projection_item_st())
def test_validate_item_accepts_iff_well_formed(item):
    """Feature: s3-claims-and-projection, Property 5: Write-time validation rejects malformed rows.

    For any generated item, an item missing its tenant key or a required field
    is ALWAYS rejected (``validate_item`` raises ``ProjectionValidationError``,
    so no partial/malformed item is written), and a well-formed item is ALWAYS
    accepted (returned unchanged). ``is_valid_item`` agrees with the oracle.
    """
    expected_valid = _oracle_is_well_formed(item)

    if expected_valid:
        # Well-formed -> accepted, returned unchanged, and no raise.
        assert validate_item(item) is item
        assert is_valid_item(item) is True
    else:
        # Malformed (missing tenant key or a required field) -> always rejected.
        with pytest.raises(ProjectionValidationError):
            validate_item(item)
        assert is_valid_item(item) is False


@settings(max_examples=200)
@given(items=st.lists(projection_item_st(), min_size=1, max_size=8))
def test_validate_items_batch_rejects_when_any_malformed_valid_siblings_pass_alone(items):
    """Feature: s3-claims-and-projection, Property 5: Write-time validation rejects malformed rows.

    For any generated batch, ``validate_items`` raises iff at least one item is
    malformed (one bad row fails the batch loudly — no partial write), while
    each valid sibling still passes validation on its own (the rest of the
    projection is unaffected). A fully well-formed batch is returned unchanged.
    """
    any_malformed = any(not _oracle_is_well_formed(i) for i in items)

    if any_malformed:
        # One malformed item makes the whole batch fail loudly (no partial write).
        with pytest.raises(ProjectionValidationError):
            validate_items(items)
        # ...yet every well-formed sibling would each pass individually.
        for sibling in items:
            if _oracle_is_well_formed(sibling):
                assert is_valid_item(sibling) is True
    else:
        # A fully valid batch is accepted and returned unchanged.
        assert validate_items(items) is items


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q", "--tb=short"]))
