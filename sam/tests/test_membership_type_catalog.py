"""
S5 Task 1.5 — tests for the Lidmaatschap Beheer membership-type catalog **entity** (design C8,
R2.1/R2.4).

These pin the tenant-agnostic entry model: its shape, validation, the soft-delete transform,
and the storage-shape ``to_item`` / ``from_item`` round-trip the repository relies on. They do
NOT touch DynamoDB — persistence is covered in ``test_members_repository.py``.

Validates: Requirements R2.1, R2.4 (Lidmaatschap Beheer — generic-membership-design.md, C8)
"""

from __future__ import annotations

import os
import sys

import pytest
from hypothesis import given
from hypothesis import strategies as st

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from sam.members.domain.membership_type_catalog import (
    CATALOG_LOCALES,
    MembershipTypeEntry,
    MembershipTypeValidationError,
)


def _entry(**kw) -> MembershipTypeEntry:
    base = dict(
        tenant_id="h-dcn",
        type_code="erelid",
        label={"nl": "Erelid", "en": "Honorary member"},
        active=True,
        order=10,
    )
    base.update(kw)
    return MembershipTypeEntry(**base)


# ---------------------------------------------------------------------------
# Shape + defaults
# ---------------------------------------------------------------------------


class TestEntryShape:
    def test_entry_carries_the_design_c8_fields(self):
        e = _entry()
        assert e.tenant_id == "h-dcn"
        assert e.type_code == "erelid"
        assert e.label == {"nl": "Erelid", "en": "Honorary member"}
        assert e.active is True
        assert e.order == 10

    def test_active_defaults_true_and_order_defaults_zero(self):
        e = MembershipTypeEntry(tenant_id="t", type_code="c", label={"nl": "L"})
        assert e.active is True
        assert e.order == 0

    def test_entry_is_frozen(self):
        e = _entry()
        with pytest.raises(Exception):
            e.type_code = "changed"  # type: ignore[misc]

    def test_catalog_locales_are_nl_and_en(self):
        assert CATALOG_LOCALES == ("nl", "en")

    def test_sort_order_key_is_order_then_code(self):
        assert _entry(order=5, type_code="b").sort_order_key() == (5, "b")


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


class TestValidation:
    def test_valid_entry_passes(self):
        _entry().validate()  # no raise

    def test_blank_tenant_is_rejected(self):
        with pytest.raises(MembershipTypeValidationError) as exc:
            _entry(tenant_id="  ").validate()
        assert "tenant_id" in exc.value.errors

    def test_blank_type_code_is_rejected(self):
        with pytest.raises(MembershipTypeValidationError) as exc:
            _entry(type_code="").validate()
        assert "type_code" in exc.value.errors

    def test_type_code_with_separator_is_rejected(self):
        # The code becomes a sort-key id segment; a '#' would make the key ambiguous.
        with pytest.raises(MembershipTypeValidationError) as exc:
            _entry(type_code="ere#lid").validate()
        assert "type_code" in exc.value.errors

    def test_missing_nl_label_is_rejected(self):
        with pytest.raises(MembershipTypeValidationError) as exc:
            _entry(label={"en": "Only English"}).validate()
        assert "label" in exc.value.errors

    def test_blank_nl_label_is_rejected(self):
        with pytest.raises(MembershipTypeValidationError) as exc:
            _entry(label={"nl": "   "}).validate()
        assert "label" in exc.value.errors

    def test_non_mapping_label_is_rejected(self):
        with pytest.raises(MembershipTypeValidationError) as exc:
            _entry(label="Erelid").validate()  # type: ignore[arg-type]
        assert "label" in exc.value.errors

    def test_non_integer_order_is_rejected(self):
        with pytest.raises(MembershipTypeValidationError) as exc:
            _entry(order="10").validate()  # type: ignore[arg-type]
        assert "order" in exc.value.errors

    def test_bool_order_is_rejected(self):
        # bool is an int subclass; an order must be a real position, not True/False.
        with pytest.raises(MembershipTypeValidationError) as exc:
            _entry(order=True).validate()  # type: ignore[arg-type]
        assert "order" in exc.value.errors

    def test_error_collects_every_problem_at_once(self):
        with pytest.raises(MembershipTypeValidationError) as exc:
            MembershipTypeEntry(tenant_id="", type_code="", label={}).validate()
        assert set(exc.value.errors) >= {"tenant_id", "type_code", "label"}


# ---------------------------------------------------------------------------
# Soft-delete transform
# ---------------------------------------------------------------------------


class TestDeactivated:
    def test_deactivated_flips_active_only(self):
        e = _entry(active=True)
        d = e.deactivated()
        assert d.active is False
        # Everything else is preserved.
        assert d.type_code == e.type_code
        assert d.label == e.label
        assert d.order == e.order

    def test_deactivated_does_not_mutate_the_original(self):
        e = _entry(active=True)
        e.deactivated()
        assert e.active is True


# ---------------------------------------------------------------------------
# Storage-shape round-trip (to_item / from_item)
# ---------------------------------------------------------------------------


class TestItemRoundTrip:
    def test_to_item_emits_the_domain_attributes(self):
        item = _entry().to_item()
        assert item == {
            "tenant_id": "h-dcn",
            "type_code": "erelid",
            "label": {"nl": "Erelid", "en": "Honorary member"},
            "active": True,
            "order": 10,
        }

    def test_to_item_validates_first(self):
        with pytest.raises(MembershipTypeValidationError):
            _entry(type_code="").to_item()

    def test_from_item_tolerates_physical_key_attributes(self):
        # A stored item carries the repository's sk attribute; from_item ignores it.
        stored = {**_entry().to_item(), "sk": "membershiptype#erelid"}
        e = MembershipTypeEntry.from_item(stored)
        assert e == _entry()

    def test_from_item_defaults_active_and_order_when_absent(self):
        e = MembershipTypeEntry.from_item(
            {"tenant_id": "t", "type_code": "c", "label": {"nl": "L"}}
        )
        assert e.active is True
        assert e.order == 0

    def test_from_item_coerces_numeric_order(self):
        # DynamoDB numbers deserialize as Decimal; from_item must coerce to int.
        from decimal import Decimal

        e = MembershipTypeEntry.from_item(
            {"tenant_id": "t", "type_code": "c", "label": {"nl": "L"}, "order": Decimal("7")}
        )
        assert e.order == 7

    def test_from_item_rejects_non_mapping(self):
        with pytest.raises(MembershipTypeValidationError):
            MembershipTypeEntry.from_item(["not", "a", "mapping"])  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Property: to_item -> from_item round-trips for any valid entry
# ---------------------------------------------------------------------------

_codes = st.text(
    alphabet=st.characters(blacklist_characters="#", blacklist_categories=("Cs",)),
    min_size=1,
    max_size=20,
).filter(lambda s: s.strip())

_labels = st.builds(
    lambda nl, en: {"nl": nl, "en": en},
    nl=st.text(min_size=1, max_size=30).filter(lambda s: s.strip()),
    en=st.text(min_size=1, max_size=30).filter(lambda s: s.strip()),
)


@given(
    tenant_id=_codes,
    type_code=_codes,
    label=_labels,
    active=st.booleans(),
    order=st.integers(min_value=-100, max_value=1000),
)
def test_property_item_round_trip_is_lossless(tenant_id, type_code, label, active, order):
    """Validates: Requirements R2.4 — a valid entry survives to_item -> from_item unchanged."""
    entry = MembershipTypeEntry(
        tenant_id=tenant_id,
        type_code=type_code,
        label=label,
        active=active,
        order=order,
    )
    entry.validate()  # precondition: only well-formed entries are persisted
    assert MembershipTypeEntry.from_item(entry.to_item()) == entry
