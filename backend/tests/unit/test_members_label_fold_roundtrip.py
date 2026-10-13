"""
Phase 1 — Catalog Backbone, task 5.4 / R3.2 (Flask/MySQL plane).

Tenant-label save fold: the Flask authoring editor presents a tenant field/group/
fixed-override label as ONE text input per supported locale, keyed ``label_<locale>``
(``label_nl`` / ``label_en`` / … — the ``members_parameters.json`` field_def). On save
those per-locale inputs are FOLDED into the stored inline ``{nl, en, …}`` label dict
(``members_config_validation.fold_field_overlay_labels``), BEFORE the overlay is stored,
so the stored (and therefore served) label shape is the inline dict the SAM resolver and
the governance projection builders consume (R2.2, shape unchanged).

This module proves the FULL round-trip, inputs → stored → served:

- **inputs**  — an overlay authored with per-locale ``label_<locale>`` inputs;
- **stored**  — the fold assembles each entry's ``label`` into an inline ``{nl,en,…}`` dict
  (the ``label_<locale>`` inputs are consumed, not stored);
- **served**  — the governance projection builder ``build_config_fields_row`` reads the
  stored overlay and emits the SAME inline ``label`` dict onto ``config#fields`` — the shape
  the SAM-plane reader (``TenantOverlay``) consumes.

Pure Flask-plane: the fold is a pure function and the projection builder reads via an
in-memory parameter stand-in (no DB, no AWS, no mocks of the units under test).

Reference: .kiro/specs/Members/Parameter redesign/phase-1-catalog-backbone/design.md §3
"""

from __future__ import annotations

import pytest

from services.members_config_validation import (
    fold_field_overlay_labels,
    fold_members_param,
    validate_field_overlay,
)
from services.projection_sync import build_config_fields_row

# Reuse the read-only in-memory ParameterService stand-in from the projection tests.
from tests.unit.test_projection_sync import FakeParameterService


# ---------------------------------------------------------------------------
# The fold: per-locale label_<locale> inputs → inline {nl,en,…} dict
# ---------------------------------------------------------------------------


class TestFoldFieldOverlayLabels:

    def test_fold_field_overlay_labels_variable_field_folds_per_locale_inputs(self):
        overlay = {
            "fields": {
                "motor_brand": {
                    "type": "string",
                    "label_en": "Motor brand",
                    "label_nl": "Motormerk",
                    "functional_group": "motor",
                    "order": 10,
                }
            }
        }

        folded = fold_field_overlay_labels(overlay)

        field = folded["fields"]["motor_brand"]
        assert field["label"] == {"en": "Motor brand", "nl": "Motormerk"}
        # The per-locale inputs are consumed, not stored.
        assert "label_en" not in field
        assert "label_nl" not in field
        # Every other authored aspect is carried through unchanged.
        assert field["type"] == "string"
        assert field["functional_group"] == "motor"
        assert field["order"] == 10

    def test_fold_field_overlay_labels_functional_group_folds_per_locale_inputs(self):
        overlay = {
            "functional_groups": [
                {"key": "motor", "label_en": "Motor", "label_nl": "Motorfiets", "order": 1},
            ]
        }

        folded = fold_field_overlay_labels(overlay)

        group = folded["functional_groups"][0]
        assert group["label"] == {"en": "Motor", "nl": "Motorfiets"}
        assert "label_en" not in group and "label_nl" not in group
        assert group["key"] == "motor"
        assert group["order"] == 1

    def test_fold_field_overlay_labels_fixed_override_folds_per_locale_inputs(self):
        overlay = {
            "fixed_overrides": {
                "personal.street": {"label_en": "Street", "label_nl": "Straat"},
            }
        }

        folded = fold_field_overlay_labels(overlay)

        override = folded["fixed_overrides"]["personal.street"]
        assert override["label"] == {"en": "Street", "nl": "Straat"}
        assert "label_en" not in override and "label_nl" not in override

    def test_fold_field_overlay_labels_is_locale_generic(self):
        # Adding a third language is a data change only — the fold needs no code change (R3.6).
        overlay = {
            "fields": {
                "club": {
                    "type": "string",
                    "label_en": "Club",
                    "label_nl": "Club",
                    "label_de": "Verein",
                }
            }
        }

        folded = fold_field_overlay_labels(overlay)

        assert folded["fields"]["club"]["label"] == {
            "en": "Club",
            "nl": "Club",
            "de": "Verein",
        }

    def test_fold_field_overlay_labels_merges_into_existing_inline_dict(self):
        # An already-folded inline label dict is preserved; a per-locale input updates its
        # own locale key (re-authoring one language overwrites just that key).
        overlay = {
            "fields": {
                "club": {
                    "type": "string",
                    "label": {"nl": "Oud", "en": "Old"},
                    "label_nl": "Nieuw",
                }
            }
        }

        folded = fold_field_overlay_labels(overlay)

        assert folded["fields"]["club"]["label"] == {"nl": "Nieuw", "en": "Old"}
        assert "label_nl" not in folded["fields"]["club"]

    def test_fold_field_overlay_labels_already_inline_dict_is_unchanged(self):
        # Idempotent: an overlay whose labels are already inline dicts (no label_<locale>
        # inputs) is returned structurally unchanged — re-folding a stored overlay is a no-op.
        overlay = {
            "functional_groups": [
                {"key": "motor", "label": {"nl": "Motor", "en": "Motor"}, "order": 1},
            ],
            "fields": {
                "club": {"type": "string", "label": {"nl": "Club", "en": "Club"}},
            },
        }

        folded = fold_field_overlay_labels(overlay)

        assert folded["functional_groups"][0]["label"] == {"nl": "Motor", "en": "Motor"}
        assert folded["fields"]["club"]["label"] == {"nl": "Club", "en": "Club"}

    def test_fold_field_overlay_labels_entry_without_label_stays_label_free(self):
        overlay = {"fields": {"club": {"type": "string", "order": 2}}}

        folded = fold_field_overlay_labels(overlay)

        assert "label" not in folded["fields"]["club"]
        assert folded["fields"]["club"] == {"type": "string", "order": 2}

    def test_fold_field_overlay_labels_does_not_mutate_input(self):
        overlay = {"fields": {"club": {"type": "string", "label_en": "Club"}}}

        fold_field_overlay_labels(overlay)

        # The caller's object is untouched (fold returns a new structure).
        assert overlay["fields"]["club"] == {"type": "string", "label_en": "Club"}

    def test_fold_field_overlay_labels_non_string_input_dropped(self):
        # An authoring quirk (non-string per-locale value) is dropped, not folded — the
        # stored label dict stays {str: str}.
        overlay = {"fields": {"club": {"type": "string", "label_en": 123}}}

        folded = fold_field_overlay_labels(overlay)

        assert folded["fields"]["club"].get("label", {}) == {}
        assert "label_en" not in folded["fields"]["club"]

    def test_fold_members_param_only_folds_field_overlay(self):
        contexts = [{"key": "c", "label_en": "C", "columns": ["email"]}]
        # Not field_overlay → returned unchanged (the dispatch is key-scoped).
        assert fold_members_param("view_contexts", contexts) is contexts

    def test_fold_members_param_non_mapping_overlay_passthrough(self):
        assert fold_members_param("field_overlay", None) is None
        assert fold_members_param("field_overlay", []) == []


# ---------------------------------------------------------------------------
# The full round-trip: inputs → stored → served
# ---------------------------------------------------------------------------


class TestTenantLabelSaveRoundTrip:

    def _authored_inputs(self) -> dict:
        """What the editor sends: per-locale label_<locale> inputs on every entry."""
        return {
            "functional_groups": [
                {"key": "motor", "label_en": "Motor", "label_nl": "Motorfiets", "order": 1},
            ],
            "fields": {
                "motor_brand": {
                    "type": "string",
                    "label_en": "Motor brand",
                    "label_nl": "Motormerk",
                    "functional_group": "motor",
                    "order": 10,
                }
            },
            "fixed_overrides": {
                "personal.street": {
                    "label_en": "Street",
                    "label_nl": "Straat",
                    "functional_group": "motor",
                }
            },
        }

    def test_round_trip_inputs_fold_to_inline_dict_then_project_served_shape(self):
        # 1. INPUTS — the editor's per-locale inputs.
        inputs = self._authored_inputs()

        # 2. STORED — the save folds per-locale inputs into the inline {nl,en} dict. The
        #    folded value is what the save-path validates and persists.
        stored = fold_members_param("field_overlay", inputs)
        validate_field_overlay(stored)  # folded overlay still passes save-time validation

        # Every authored label is now an inline {nl,en} dict; no label_<locale> survives.
        assert stored["functional_groups"][0]["label"] == {"nl": "Motorfiets", "en": "Motor"}
        assert stored["fields"]["motor_brand"]["label"] == {
            "nl": "Motormerk",
            "en": "Motor brand",
        }
        assert stored["fixed_overrides"]["personal.street"]["label"] == {
            "nl": "Straat",
            "en": "Street",
        }
        for entry in (
            stored["functional_groups"][0],
            stored["fields"]["motor_brand"],
            stored["fixed_overrides"]["personal.street"],
        ):
            assert "label_en" not in entry and "label_nl" not in entry

        # 3. SERVED — the governance projection builder reads the STORED overlay (as the
        #    tenant-scope members.field_overlay param) and emits the SAME inline label dict
        #    onto config#fields (the shape TenantOverlay / the SAM resolver consume).
        params = FakeParameterService(
            {("members", "field_overlay", "h-dcn"): stored}
        )
        item = build_config_fields_row({"administration": "h-dcn", "version": 1}, params)

        served_group = item.attributes["functional_groups"][0]
        served_field = item.attributes["fields"]["motor_brand"]
        served_override = item.attributes["overrides"]["personal.street"]

        # The inline {nl,en} dict is preserved END-TO-END; the shape is unchanged (R2.2).
        assert served_group["label"] == {"nl": "Motorfiets", "en": "Motor"}
        assert served_field["label"] == {"nl": "Motormerk", "en": "Motor brand"}
        assert served_override["label"] == {"nl": "Straat", "en": "Street"}

    def test_round_trip_add_a_language_flows_through_unchanged(self):
        # R3.6: a tenant backfilling a third locale needs no code change — the de label
        # folds and projects exactly like nl/en.
        inputs = {
            "fields": {
                "club": {
                    "type": "string",
                    "label_en": "Club",
                    "label_nl": "Club",
                    "label_de": "Verein",
                }
            }
        }

        stored = fold_members_param("field_overlay", inputs)
        params = FakeParameterService(
            {("members", "field_overlay", "h-dcn"): stored}
        )
        item = build_config_fields_row({"administration": "h-dcn"}, params)

        assert item.attributes["fields"]["club"]["label"] == {
            "en": "Club",
            "nl": "Club",
            "de": "Verein",
        }

    def test_round_trip_already_stored_inline_dict_is_stable(self):
        # An overlay already stored as inline {nl,en} dicts (e.g. re-saved) round-trips
        # unchanged — fold is idempotent, so served == stored == inputs.
        stored_inline = {
            "fields": {
                "club": {"type": "string", "label": {"nl": "Club", "en": "Club"}},
            }
        }

        refolded = fold_members_param("field_overlay", stored_inline)
        params = FakeParameterService(
            {("members", "field_overlay", "h-dcn"): refolded}
        )
        item = build_config_fields_row({"administration": "h-dcn"}, params)

        assert item.attributes["fields"]["club"]["label"] == {"nl": "Club", "en": "Club"}


if __name__ == "__main__":  # pragma: no cover
    pytest.main([__file__, "-q"])
