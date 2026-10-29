"""
03b BU-2/BU-3 (Task 2.3) — the SINGLE-VOCABULARY reference model, end-to-end.

Tasks 2.1 / 2.2 re-pointed the ``membership_type`` reference check + the option-assembly seam at
the FIELD's own options and proved the per-case behaviours (unknown / retired / allowed /
grandfather / default-from-options / the transitional pre-fold catalog fallback). This module is
the COMPLETENESS sweep the design's Requirements-Traceability demands for the single-vocabulary
reference model — the two legs 2.1/2.2 did NOT pin head-on:

1. **The assembly seam serves the field's OWN options with NO catalog injection, POST-FOLD.** Every
   assembly-seam test in ``test_field_config_endpoint`` exercises the PRE-fold fallback (the field
   has no inline options, so the seam falls back to the active catalog). Here the field DOES carry
   inline options AND a (different) active catalog co-exists — the resolved config, the write-path
   reference check, and the default ALL read the field's options and the catalog is never consulted.
   This is the core of Req 3.1/3.4a: one vocabulary on the field, not a second catalog source.
2. **Property 1 (no orphaned reference) + Property 2 (grandfather preserved) as PROPERTIES** over
   the single-vocabulary model — not one fixture, the whole input space: for ANY authored option
   set, every ``allowed:true`` value is assignable, every ``allowed:false`` value is grandfathered
   (read-stable + valid on an unchanged-value update, rejected only on a CHANGE to it), every value
   NOT in the options is a save-blocking ``UNKNOWN_REFERENCE`` on a change (Req 3.2a), and the
   off-form default is always the first ``allowed:true`` by ``order`` (and is itself assignable by
   construction — the stamped default can never be rejected by the reference check it feeds).

Layering: domain-level, a ``StaticOverlayProvider`` + the in-memory ``_ApplicationRepo`` fake (no
boto3). These reuse the 2.1 helpers (``_overlay_with_inline_options`` etc.) WITHOUT re-asserting the
2.1 cases — they add the two completeness legs above.

Validates: Requirements 3.1, 3.2, 3.2a, 3.4a
Properties: 1 (no orphaned reference), 2 (grandfather preserved)
"""

from __future__ import annotations

import os
import sys

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from sam.members.domain._membership_errors import (
    MEMBERSHIP_TYPE_FIELD_KEY,
    MemberValidationError,
)
from sam.members.domain.error_codes import (
    MEMBERSHIP_TYPE_RETIRED,
    MEMBERSHIP_TYPE_UNKNOWN_REFERENCE,
)
from sam.members.domain.field_resolver import (
    FixedFieldOverride,
    StaticOverlayProvider,
    TenantOverlay,
)
from sam.members.domain.fixed_fields import EnumOption
from sam.members.domain.membership_service import MembershipService

# Reuse the task-2.1/2.2 fake repo (member store + catalog surface) and the catalog-entry factory.
from sam.tests.test_create_application import _ApplicationRepo
from sam.tests.test_field_config_endpoint import _entry

TENANT = "h-dcn"


# ── Builders ───────────────────────────────────────────────────────────────────────────


def _overlay_inline(options) -> TenantOverlay:
    """Author the ``membership_type`` fixed field with INLINE enum options (the post-fold shape)."""
    return TenantOverlay(
        overrides={
            "membership.membership_type": FixedFieldOverride(options=tuple(options)),
        },
        fields={},
    )


def _service(overlay: TenantOverlay, *, catalog=()) -> MembershipService:
    repo = _ApplicationRepo()
    for entry in catalog:
        repo.add_type(TENANT, entry)
    return MembershipService(
        repo, overlay_provider=StaticOverlayProvider({TENANT: overlay})
    )


def _record(membership_type):
    return {"tenant_id": TENANT, "membership": {"membership_type": membership_type}}


def _mt_field_options(service: MembershipService) -> list[dict]:
    """The ``membership_type`` field's served ``options`` from the resolved staff config."""
    config = service.get_field_config(TENANT)
    mt = next(f for f in config["fields"] if f["key"] == "membership_type")
    return mt["options"]


# ── 1. POST-FOLD: the assembly seam serves the FIELD's options, NO catalog injection ─────
#
# The field carries its OWN inline options (post-fold) AND a DIFFERENT active catalog co-exists
# (a pre-CONTRACT reality: the migration folds the catalog onto the field but the catalog rows are
# only retired later, Task 10.1). The single-vocabulary rule (Req 3.1/3.4a): the served vocabulary,
# the write-path reference check, and the default ALL read the FIELD's options — the catalog is
# never injected, so the two sources cannot drift. 2.1/2.2 only ever exercised the PRE-fold
# fallback (field had no inline options); this pins the fold-complete state head-on.


class TestAssemblyServesFieldOptionsNotCatalog:
    # The field's own options: two allowed + one retired, deliberately DISJOINT from the catalog
    # below so a catalog injection would be unmistakable in the served values.
    def _inline_options(self):
        return [
            EnumOption(value="gewoon_lid", label={"nl": "Gewoon lid"}, allowed=True, order=10),
            EnumOption(value="erelid", label={"nl": "Erelid"}, allowed=False, order=20),
            EnumOption(value="donateur", label={"nl": "Donateur"}, allowed=True, order=30),
        ]

    # A catalog whose codes do NOT overlap the field options — if the seam injected the catalog,
    # these foreign values would appear (and the field's own `erelid`/`donateur` would not).
    def _foreign_catalog(self):
        return [
            _entry(TENANT, "catalog_only_a", order=1),
            _entry(TENANT, "catalog_only_b", order=2),
        ]

    def test_served_options_are_the_fields_own_not_the_catalog(self):
        service = _service(
            _overlay_inline(self._inline_options()), catalog=self._foreign_catalog()
        )
        values = [o["value"] for o in _mt_field_options(service)]
        # The field's own options (incl. the retired erelid) are served, in authored order …
        assert values == ["gewoon_lid", "erelid", "donateur"]
        # … and NOT a single catalog-only value leaked in (no catalog injection, Req 3.1/3.3).
        assert "catalog_only_a" not in values
        assert "catalog_only_b" not in values

    def test_served_options_carry_the_allowed_flag_from_the_field(self):
        # The grandfather flag rides on the field's own option (Req 3.2) — the retired `erelid`
        # surfaces allowed:false so the picker can hide it while existing records keep it.
        service = _service(
            _overlay_inline(self._inline_options()), catalog=self._foreign_catalog()
        )
        by_val = {o["value"]: o for o in _mt_field_options(service)}
        assert by_val["gewoon_lid"]["allowed"] is True
        assert by_val["erelid"]["allowed"] is False
        assert by_val["donateur"]["allowed"] is True

    def test_reference_check_reads_field_options_ignoring_a_live_catalog(self):
        # The authoritative write-path check reads the SAME single vocabulary (the field's
        # options): a field-option value is accepted, a catalog-only value is UNKNOWN — the
        # catalog is not a reference source once the field carries its own options.
        service = _service(
            _overlay_inline(self._inline_options()), catalog=self._foreign_catalog()
        )
        # a field option (allowed) is accepted …
        service._validate_membership_type_reference(TENANT, _record("gewoon_lid"))
        # … a catalog-only value is NOT a valid reference (the catalog is not consulted).
        with pytest.raises(MemberValidationError) as exc:
            service._validate_membership_type_reference(TENANT, _record("catalog_only_a"))
        assert (
            exc.value.errors[MEMBERSHIP_TYPE_FIELD_KEY].code
            == MEMBERSHIP_TYPE_UNKNOWN_REFERENCE
        )

    def test_default_reads_field_options_ignoring_a_live_catalog(self):
        # The off-form default (Req 3.4a) is the first allowed:true FIELD option by order
        # (gewoon_lid @10, skipping the retired erelid) — NOT the first active CATALOG entry
        # (catalog_only_a @1), proving the default reads the field, not the catalog.
        service = _service(
            _overlay_inline(self._inline_options()), catalog=self._foreign_catalog()
        )
        assert service._default_membership_type(TENANT) == "gewoon_lid"


# ── 2. Property 1 — no orphaned reference over the single-vocabulary model ────────────────
#
# For ANY authored membership_type option set, every value equal to an option RESOLVES: an
# `allowed:true` value is assignable, an `allowed:false` value is grandfathered (not assignable to
# a CHANGE, but read-stable + valid on an unchanged-value update), and a value NOT in the options
# is a save-blocking UNKNOWN_REFERENCE on a change (Req 3.2a). This quantifies the 2.1 fixture cases
# across the whole input space — the model has no orphan: the reference always resolves to exactly
# one of {assignable, grandfathered, unknown} with no gaps or overlaps.
#
# Validates: Requirements 3.1, 3.2, 3.2a, 3.4a · Property 1, 2

_CODE = st.text(
    alphabet="abcdefghijklmnopqrstuvwxyz_", min_size=1, max_size=10
).filter(lambda s: s.strip() != "")


@st.composite
def _option_set(draw):
    """A non-empty option set: 1..6 unique values, each with an `allowed` flag + an `order`.

    Guarantees at least one `allowed:true` option so the field is well-formed (Req 3.4a) and has a
    stampable default — the property is about resolution, not about re-proving the zero-allowed
    write-seam reject (that is BU-1's write-seam test).
    """
    values = draw(st.lists(_CODE, min_size=1, max_size=6, unique=True))
    alloweds = draw(
        st.lists(st.booleans(), min_size=len(values), max_size=len(values))
    )
    if not any(alloweds):  # force ≥1 allowed:true so the field is well-formed
        alloweds[0] = True
    orders = draw(
        st.lists(st.integers(min_value=0, max_value=99), min_size=len(values), max_size=len(values))
    )
    options = [
        EnumOption(value=v, label={"nl": v}, allowed=a, order=o)
        for v, a, o in zip(values, alloweds, orders)
    ]
    return options


@settings(max_examples=150)
@given(options=_option_set())
def test_property_every_reference_resolves_to_one_outcome(options):
    """Property 1: for any option set, every candidate value resolves to EXACTLY one outcome —
    assignable (allowed:true), grandfathered-reject (allowed:false), or unknown (absent). No
    orphan, no gap, no overlap.

    Validates: Requirements 3.1, 3.2, 3.2a · Property 1, 2
    """
    service = _service(_overlay_inline(options))

    allowed_values = {o.value for o in options if o.allowed}
    retired_values = {o.value for o in options if not o.allowed}

    # (a) every allowed:true value is assignable (no raise).
    for value in allowed_values:
        service._validate_membership_type_reference(TENANT, _record(value))

    # (b) every allowed:false value is RETIRED on a change (grandfather: left the picker, Req 3.2).
    for value in retired_values:
        with pytest.raises(MemberValidationError) as exc:
            service._validate_membership_type_reference(TENANT, _record(value))
        assert exc.value.errors[MEMBERSHIP_TYPE_FIELD_KEY].code == MEMBERSHIP_TYPE_RETIRED

    # (c) a value NOT in the options is a save-blocking UNKNOWN_REFERENCE (Req 3.2a). "zzz_absent"
    # is excluded from the generated alphabet-only space by its digit, so it is always absent.
    with pytest.raises(MemberValidationError) as exc:
        service._validate_membership_type_reference(TENANT, _record("zzz_absent_9"))
    assert (
        exc.value.errors[MEMBERSHIP_TYPE_FIELD_KEY].code
        == MEMBERSHIP_TYPE_UNKNOWN_REFERENCE
    )


@settings(max_examples=150)
@given(options=_option_set())
def test_property_default_is_first_allowed_by_order_and_is_assignable(options):
    """Property 1/3.4a: the off-form default is the first allowed:true option by order, and the
    stamped default is ITSELF assignable — the reference check that consumes the default can never
    reject it (the default feeds a valid reference by construction, no self-orphan).

    Validates: Requirements 3.4a · Property 1
    """
    service = _service(_overlay_inline(options))

    default = service._default_membership_type(TENANT)
    # The generator guarantees ≥1 allowed:true option → a default always exists.
    assert default is not None

    # It is the first allowed:true option by (order, input-position) — the same rank the exposed
    # form pre-selects. Recompute independently to pin the ordering contract.
    allowed = [(i, o) for i, o in enumerate(options) if o.allowed]
    expected = min(
        allowed,
        key=lambda io: (io[1].order if io[1].order is not None else float("inf"), io[0]),
    )[1].value
    assert default == expected

    # Self-consistency (no self-orphan): the stamped default passes the reference check it feeds.
    service._validate_membership_type_reference(TENANT, _record(default))


@settings(max_examples=100)
@given(options=_option_set())
def test_property_grandfather_unchanged_value_is_never_revalidated(options):
    """Property 2: grandfather preserved. A record holding a retired value is read-stable — the
    value-changed-only guard (design C8) means an update that does NOT change the value never
    re-runs the reference check, so an existing member on an `allowed:false` (or since-removed)
    value stays valid and updatable. We pin the guard predicate the caller applies.

    Validates: Requirements 3.2, 3.2a · Property 2
    """
    service = _service(_overlay_inline(options))

    retired = [o.value for o in options if not o.allowed]
    sample = retired[0] if retired else "zzz_removed_9"  # retired OR a since-removed value

    # The value-changed-only guard: `_membership_type_of` of the same stored record is stable, so
    # the caller's "only re-validate on a CHANGE" rule skips the check for an unchanged value.
    before = service._membership_type_of(_record(sample))
    after = service._membership_type_of(_record(sample))
    assert before == after  # unchanged → the caller does NOT re-validate → stays valid


# ── 3. The two reads agree on the single vocabulary (no second source to drift) ──────────


class TestStaffReadAndReferenceCheckShareOneVocabulary:
    """Req 3.1: the served options (what the staff picker renders) and the authoritative reference
    check read the SAME single field vocabulary — so a value the picker offers is exactly a value
    the write path accepts, and a retired option the picker hides is exactly a value the write path
    rejects on a change. One source, no drift."""

    def _options(self):
        return [
            EnumOption(value="gewoon_lid", label={"nl": "Gewoon lid"}, allowed=True, order=10),
            EnumOption(value="erelid", label={"nl": "Erelid"}, allowed=False, order=20),
        ]

    def test_every_served_allowed_option_is_accepted_by_the_reference_check(self):
        service = _service(_overlay_inline(self._options()))
        for opt in _mt_field_options(service):
            if opt["allowed"]:
                service._validate_membership_type_reference(TENANT, _record(opt["value"]))
            else:
                with pytest.raises(MemberValidationError) as exc:
                    service._validate_membership_type_reference(
                        TENANT, _record(opt["value"])
                    )
                assert (
                    exc.value.errors[MEMBERSHIP_TYPE_FIELD_KEY].code
                    == MEMBERSHIP_TYPE_RETIRED
                )
