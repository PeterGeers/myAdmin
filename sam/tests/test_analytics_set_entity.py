"""
Pure-unit tests for the :class:`AnalyticsSetEntry` entity (F-012).

Pin the entity model's validate() / to_item() / from_item() behaviour, mirroring the sibling
``test_membership_type_catalog`` entity tests. The CRITICAL case is F-011: an EMPTY
``group_columns`` AND EMPTY ``aggregate_measures`` filtered-list definition is first-class —
validate() must accept it (it never requires those to be non-empty).

Validates: finding F-011 (filtered-list set with empty group/measures is valid) + F-012.
"""

from __future__ import annotations

import os
import sys

import pytest

_REPO_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from sam.members.domain.analytics_set import (
    DELIVERY_MODE_PER_RECIPIENT,
    DELIVERY_MODE_TO_FIXED,
    AnalyticsSetEntry,
    AnalyticsSetValidationError,
)


def _definition(*, group=None, measures=None):
    """A snake_case PivotConfig-shaped definition (the frontend sends this)."""
    return {
        "data_source": "members",
        "group_columns": group if group is not None else [],
        "aggregate_measures": measures if measures is not None else [],
        "filters": {},
        "column_pivot": None,
        "column_nest_levels": [],
        "display_mode": "flat",
        "include_rollup": False,
    }


def _entry(**overrides):
    base = {
        "tenant_id": "h-dcn",
        "set_id": "abc123",
        "name": "Paper clubblad",
        "kind": "count",
        "definition": _definition(
            group=["membership_type"], measures=[{"function": "COUNT", "column": "*"}]
        ),
        "created_at": "2024-01-01T00:00:00+00:00",
        "updated_at": "2024-01-01T00:00:00+00:00",
    }
    base.update(overrides)
    return AnalyticsSetEntry(**base)


class TestAnalyticsSetEntryValidate:
    def test_valid_count_set_passes(self):
        _entry(kind="count").validate()  # must not raise

    def test_valid_list_set_passes(self):
        _entry(kind="list").validate()  # must not raise

    def test_empty_group_and_measures_is_first_class(self):
        # THE F-011 regression at the entity level: an empty-group, empty-measures filtered-list
        # set is valid — validate() must NOT require group_columns / aggregate_measures.
        entry = _entry(kind="list", definition=_definition(group=[], measures=[]))
        entry.validate()  # must not raise

    def test_blank_name_is_invalid(self):
        with pytest.raises(AnalyticsSetValidationError) as exc:
            _entry(name="  ").validate()
        assert "name" in exc.value.errors

    def test_blank_tenant_is_invalid(self):
        with pytest.raises(AnalyticsSetValidationError) as exc:
            _entry(tenant_id="").validate()
        assert "tenant_id" in exc.value.errors

    def test_blank_set_id_is_invalid(self):
        with pytest.raises(AnalyticsSetValidationError) as exc:
            _entry(set_id="").validate()
        assert "set_id" in exc.value.errors

    def test_set_id_with_separator_is_invalid(self):
        with pytest.raises(AnalyticsSetValidationError) as exc:
            _entry(set_id="has#hash").validate()
        assert "set_id" in exc.value.errors

    def test_bad_kind_is_invalid(self):
        with pytest.raises(AnalyticsSetValidationError) as exc:
            _entry(kind="pie").validate()
        assert "kind" in exc.value.errors

    def test_non_mapping_definition_is_invalid(self):
        with pytest.raises(AnalyticsSetValidationError) as exc:
            _entry(definition=["not", "a", "mapping"]).validate()
        assert "definition" in exc.value.errors

    # R11.2/R11.3 — origin + created_by (shared-library attribution).
    def test_origin_defaults_to_user(self):
        assert _entry().origin == "user"

    def test_valid_origin_passes(self):
        _entry(origin="user").validate()
        _entry(origin="predefined").validate()

    def test_bad_origin_is_invalid(self):
        with pytest.raises(AnalyticsSetValidationError) as exc:
            _entry(origin="imported").validate()
        assert "origin" in exc.value.errors

    def test_created_by_is_optional_and_ungated(self):
        # created_by is attribution-only (a user sub) — blank is fine, never a validation error.
        _entry(created_by="").validate()
        _entry(created_by="c2559464-sub").validate()


class TestAnalyticsSetEntryRoundTrip:
    def test_to_item_carries_the_domain_shape(self):
        item = _entry(created_by="sub-1").to_item()
        assert item["tenant_id"] == "h-dcn"
        assert item["set_id"] == "abc123"
        assert item["name"] == "Paper clubblad"
        assert item["kind"] == "count"
        assert item["definition"]["data_source"] == "members"
        assert item["origin"] == "user"
        assert item["created_by"] == "sub-1"
        assert item["created_at"] == "2024-01-01T00:00:00+00:00"
        assert item["updated_at"] == "2024-01-01T00:00:00+00:00"

    def test_from_item_defaults_origin_and_created_by_for_legacy_item(self):
        # A legacy stored item written before origin/created_by existed.
        rebuilt = AnalyticsSetEntry.from_item(
            {"tenant_id": "h-dcn", "set_id": "x", "name": "N", "kind": "list"}
        )
        assert rebuilt.origin == "user"
        assert rebuilt.created_by == ""

    def test_to_item_validates_first(self):
        with pytest.raises(AnalyticsSetValidationError):
            _entry(name="").to_item()

    def test_from_item_is_inverse_of_to_item(self):
        original = _entry(kind="list", definition=_definition(group=[], measures=[]))
        rebuilt = AnalyticsSetEntry.from_item(original.to_item())
        assert rebuilt == original

    def test_from_item_tolerates_physical_key_attrs(self):
        item = _entry().to_item()
        item["sk"] = "analyticsset#abc123"  # physical attr the repo adds
        rebuilt = AnalyticsSetEntry.from_item(item)
        assert rebuilt.set_id == "abc123"
        assert rebuilt.name == "Paper clubblad"

    def test_from_item_defaults_absent_definition_and_kind(self):
        rebuilt = AnalyticsSetEntry.from_item(
            {"tenant_id": "h-dcn", "set_id": "x", "name": "N"}
        )
        assert rebuilt.definition == {}
        assert rebuilt.kind == "count"


def _label_options():
    """The shared snake_case label_options block (one model with R6, task 6.3)."""
    return {
        "format": "L7160",
        "sort": "name",
        "font_size": 10,
        "alignment": "left",
        "border": False,
        "country": True,
        "start": 0,
    }


class TestAnalyticsSetEntryDelivery:
    """R3 — the optional `delivery` block: mode discriminator + per-mode recipient rules."""

    # ── absence / default (a legacy set carries no delivery) ──────────────────────────
    def test_delivery_defaults_to_none(self):
        assert _entry().delivery is None

    def test_no_delivery_set_validates(self):
        _entry(delivery=None).validate()  # must not raise

    # ── to_fixed mode: requires a non-empty recipients list ───────────────────────────
    def test_to_fixed_with_recipients_passes(self):
        _entry(
            delivery={
                "mode": DELIVERY_MODE_TO_FIXED,
                "template_id": None,
                "attachment": "csv",
                "recipients": ["agent@example.com"],
                "label_options": None,
            }
        ).validate()  # must not raise

    def test_to_fixed_without_recipients_is_invalid(self):
        with pytest.raises(AnalyticsSetValidationError) as exc:
            _entry(delivery={"mode": DELIVERY_MODE_TO_FIXED, "recipients": []}).validate()
        assert "delivery" in exc.value.errors

    def test_to_fixed_missing_recipients_key_is_invalid(self):
        with pytest.raises(AnalyticsSetValidationError) as exc:
            _entry(delivery={"mode": DELIVERY_MODE_TO_FIXED}).validate()
        assert "delivery" in exc.value.errors

    def test_to_fixed_blank_recipient_is_invalid(self):
        with pytest.raises(AnalyticsSetValidationError) as exc:
            _entry(
                delivery={"mode": DELIVERY_MODE_TO_FIXED, "recipients": ["  "]}
            ).validate()
        assert "delivery" in exc.value.errors

    def test_to_fixed_with_pdf_labels_and_label_options_passes(self):
        _entry(
            delivery={
                "mode": DELIVERY_MODE_TO_FIXED,
                "attachment": "pdf_labels",
                "recipients": ["agent@example.com"],
                "label_options": _label_options(),
            }
        ).validate()  # must not raise

    # ── per_recipient mode: stores NO recipients ──────────────────────────────────────
    def test_per_recipient_without_recipients_passes(self):
        _entry(
            delivery={
                "mode": DELIVERY_MODE_PER_RECIPIENT,
                "template_id": "template-1",
                "attachment": None,
                "label_options": None,
            }
        ).validate()  # must not raise

    def test_per_recipient_empty_recipients_passes(self):
        # An explicit empty list is fine — it just stores none.
        _entry(
            delivery={"mode": DELIVERY_MODE_PER_RECIPIENT, "recipients": []}
        ).validate()  # must not raise

    def test_per_recipient_storing_recipients_is_invalid(self):
        # per_recipient resolves addresses from the dataset at run time — storing them is a
        # shape error (design §2.1).
        with pytest.raises(AnalyticsSetValidationError) as exc:
            _entry(
                delivery={
                    "mode": DELIVERY_MODE_PER_RECIPIENT,
                    "recipients": ["someone@example.com"],
                }
            ).validate()
        assert "delivery" in exc.value.errors

    # ── mode discriminator + shape ────────────────────────────────────────────────────
    def test_bad_mode_is_invalid(self):
        with pytest.raises(AnalyticsSetValidationError) as exc:
            _entry(delivery={"mode": "broadcast"}).validate()
        assert "delivery" in exc.value.errors

    def test_missing_mode_is_invalid(self):
        with pytest.raises(AnalyticsSetValidationError) as exc:
            _entry(delivery={"recipients": ["a@example.com"]}).validate()
        assert "delivery" in exc.value.errors

    def test_non_mapping_delivery_is_invalid(self):
        with pytest.raises(AnalyticsSetValidationError) as exc:
            _entry(delivery=["not", "a", "mapping"]).validate()
        assert "delivery" in exc.value.errors

    def test_bad_attachment_is_invalid(self):
        with pytest.raises(AnalyticsSetValidationError) as exc:
            _entry(
                delivery={
                    "mode": DELIVERY_MODE_PER_RECIPIENT,
                    "attachment": "zip",
                }
            ).validate()
        assert "delivery" in exc.value.errors

    def test_non_mapping_label_options_is_invalid(self):
        with pytest.raises(AnalyticsSetValidationError) as exc:
            _entry(
                delivery={
                    "mode": DELIVERY_MODE_TO_FIXED,
                    "recipients": ["a@example.com"],
                    "label_options": "not-a-mapping",
                }
            ).validate()
        assert "delivery" in exc.value.errors


class TestAnalyticsSetEntryDeliveryRoundTrip:
    """R3 — to_item/from_item round-trip of the new delivery field; legacy load still works."""

    def test_to_item_carries_delivery_block(self):
        delivery = {
            "mode": DELIVERY_MODE_TO_FIXED,
            "template_id": "template-9",
            "attachment": "pdf_labels",
            "recipients": ["agent@example.com", "ops@example.com"],
            "label_options": _label_options(),
        }
        item = _entry(delivery=delivery).to_item()
        assert item["delivery"] == delivery

    def test_to_item_emits_none_delivery_when_absent(self):
        item = _entry(delivery=None).to_item()
        assert item["delivery"] is None

    def test_to_item_validates_delivery_first(self):
        # A malformed delivery block must block the write.
        with pytest.raises(AnalyticsSetValidationError):
            _entry(delivery={"mode": DELIVERY_MODE_TO_FIXED, "recipients": []}).to_item()

    def test_from_item_round_trips_to_fixed_delivery(self):
        original = _entry(
            delivery={
                "mode": DELIVERY_MODE_TO_FIXED,
                "template_id": None,
                "attachment": "csv",
                "recipients": ["agent@example.com"],
                "label_options": None,
            }
        )
        rebuilt = AnalyticsSetEntry.from_item(original.to_item())
        assert rebuilt == original

    def test_from_item_round_trips_per_recipient_delivery(self):
        original = _entry(
            delivery={
                "mode": DELIVERY_MODE_PER_RECIPIENT,
                "template_id": "template-1",
                "attachment": None,
                "label_options": None,
            }
        )
        rebuilt = AnalyticsSetEntry.from_item(original.to_item())
        assert rebuilt == original

    def test_legacy_set_without_delivery_still_loads(self):
        # A legacy stored item written before the delivery field existed must load with
        # delivery defaulted to None (and keep working).
        rebuilt = AnalyticsSetEntry.from_item(
            {"tenant_id": "h-dcn", "set_id": "x", "name": "N", "kind": "list"}
        )
        assert rebuilt.delivery is None
        rebuilt.validate()  # must not raise

    def test_from_item_degrades_non_mapping_delivery_to_none(self):
        rebuilt = AnalyticsSetEntry.from_item(
            {
                "tenant_id": "h-dcn",
                "set_id": "x",
                "name": "N",
                "kind": "list",
                "delivery": "corrupt",
            }
        )
        assert rebuilt.delivery is None
