"""03a harness-first: UNIFIED selectable-vocabulary round-trip against live local DynamoDB.

The acceptance gate for spec `Members/03a - enum-vocab-roundtrip-and-no-silent-fallbacks`.
The owner directive is ONE vocabulary model: EVERY selectable field (enum, reference, scope-
backed) resolves to ONE canonical `options` list in ONE shape, read by every consumer with NO
field-kind branching. The kinds differ ONLY in the SOURCE that populates `options` (inline /
live catalog / scope dimension). This gate drives ALL THREE kinds through the ONE read path and
asserts the per-kind round-trip invariant (design "Fix Checking", G3).

The symmetry invariant is NOT identical across kinds (design G3 — named honestly):
  * enum      — strict PUT == GET of the INLINE vocabulary (the source lives in the row).
  * scope     — `options` populated from the scope dimension AND `scope.values` is the DERIVED
                projection `[o.value for o in options]` (one list, never two copies).
  * reference — `options` == the CURRENT active catalog for the key, and BOTH reads (staff
                editor + member form) agree with EACH OTHER and with the catalog. NOT `options ==
                what was PUT`: the catalog lives elsewhere and changes independently (G3 carve-out).

Cases:
  * test_roundtrip_symmetry_options_authored       — enum options-authored: PASS today.
  * test_roundtrip_symmetry_choices_only_legacy_row — enum bare-`choices` (real h-dcn shape):
        FAIL today — the variable-field resolve does not promote choices->options, so the editor
        reads an EMPTY vocabulary.
  * test_roundtrip_symmetry_scope_backed_field      — scope: FAIL today — `options` round-trips
        but `FieldScope.values` is a SEPARATE stored copy that came back `()` (the
        `FieldScope(values=())` divergence); `scope.values != [o.value for o in options]`.
  * test_roundtrip_symmetry_reference_membership_type — reference: asserts the G3 carve-out
        (both reads == current catalog). See the case docstring for its observed status today.

All failing cases are the SAME disease: no populated `options` from the declared source, read
split by kind / a vocabulary tracked under two names or in two places.

Container-gated: SKIPS cleanly without the local-DynamoDB container.
"""

from __future__ import annotations

import os
import sys

import pytest

_REPO_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)
_BACKEND_SRC = os.path.join(_REPO_ROOT, "backend", "src")
if _BACKEND_SRC not in sys.path:
    sys.path.insert(0, _BACKEND_SRC)

from services import projection_schema as schema  # noqa: E402

from sam.members.domain.config_fields_crud_service import ConfigFieldsCrudService  # noqa: E402
from sam.members.domain.field_resolver import FieldResolver  # noqa: E402
from sam.members.domain.membership_service import MembershipService  # noqa: E402
from sam.members.domain.membership_type_catalog import MembershipTypeEntry  # noqa: E402
from sam.members.repository.members_repository import DynamoDbMembersRepository  # noqa: E402
from sam.members.repository.projection_config_reader import MembersProjectionReader  # noqa: E402
from sam.members.repository.projection_config_write_repository import (  # noqa: E402
    MembersConfigWriteRepository,
)

pytestmark = pytest.mark.e2e

_TENANT = "enum-roundtrip-tenant"
_VOCAB = ["internet", "facebook", "bigtwin", "family", "other", "young-ones"]

_vc = 0


def _version():
    global _vc
    _vc += 1
    return f"v-rt-{_vc:06d}"


def _key():
    return schema.build_key(
        _TENANT, schema.build_sort_key(schema.RECORD_TYPE_CONFIG, schema.CONFIG_ID_FIELDS)
    )


def _service(table):
    return ConfigFieldsCrudService(
        MembersConfigWriteRepository(table=table, version_fn=_version),
        reader=MembersProjectionReader(table=table),
    )


def _field_config_service(table):
    """The read-assembly SEAM (`get_field_config` / `get_public_field_config`) wired over the
    live table. The projection reader is BOTH the overlay provider (field resolution) AND the
    scope-config provider; the real `DynamoDbMembersRepository` supplies the membership-type
    catalog `_active_membership_type_options` merges in. This is the ONE read path the design
    unifies all three kinds on."""
    reader = MembersProjectionReader(table=table)
    repo = DynamoDbMembersRepository(table=table)
    return MembershipService(repo, overlay_provider=reader, scope_config_provider=reader)


@pytest.fixture
def table(seeded_config_fields_table):
    t = seeded_config_fields_table["table"]
    if t.get_item(Key=_key()).get("Item") is not None:
        t.delete_item(Key=_key())
    return t


def _resolved_vocab(table) -> list[str]:
    """The vocabulary the config editor would show: resolved field.options values (the shape
    MembersFieldModal.optionsToChoices reads). Fresh reader = real production read."""
    cfg = FieldResolver(MembersProjectionReader(table=table)).resolve(_TENANT)
    f = next((x for x in cfg.fields if x.key == "referral_source"), None)
    if f is None:
        return []
    return [o.value for o in (f.options or [])]


# ─────────────────────────────────────────────────────────────────────────────────────
# ENUM — strict PUT == GET of the INLINE vocabulary (the source lives in the row)
# ─────────────────────────────────────────────────────────────────────────────────────
def test_roundtrip_symmetry_options_authored(table):
    """PUT a field authored under `options` -> GET via the editor read path -> input == output."""
    MembersConfigWriteRepository(table=table, version_fn=_version).ensure_skeleton(_TENANT)
    svc = _service(table)
    svc.set_group(_TENANT, "membership", {"label": {"en": "Membership"}, "order": 30})
    svc.set_field(_TENANT, "referral_source", {
        "type": "enum", "label": {"en": "Ref"}, "order": 50, "functional_group": "membership",
        "options": [{"value": v, "label": {"en": v, "nl": v}} for v in _VOCAB],
    })
    assert _resolved_vocab(table) == _VOCAB, "options-authored vocabulary must round-trip identically"


def test_roundtrip_symmetry_choices_only_legacy_row(table):
    """The REAL h-dcn shape: vocabulary stored under bare `choices`, `options` absent.

    EXPECTED FAIL on unfixed code (harness-first proof): the editor read path yields an EMPTY
    vocabulary because the variable-field resolve does not promote choices->options. The 03a
    fix (single canonical `options` + no silent fallback) makes input == output here too.
    """
    MembersConfigWriteRepository(table=table, version_fn=_version).ensure_skeleton(_TENANT)
    svc = _service(table)
    svc.set_group(_TENANT, "membership", {"label": {"en": "Membership"}, "order": 30})
    # Author under bare `choices` (the legacy shape the real row has), no `options`.
    svc.set_field(_TENANT, "referral_source", {
        "type": "enum", "label": {"en": "Ref"}, "order": 50, "functional_group": "membership",
        "choices": list(_VOCAB),
    })
    got = _resolved_vocab(table)
    assert got == _VOCAB, (
        f"ROUND-TRIP BROKEN (bug): authored {_VOCAB} but the editor read path returned {got}. "
        f"A choices-only row resolves to empty options -> choices disappear in the config editor."
    )


# ─────────────────────────────────────────────────────────────────────────────────────
# SCOPE — `options` populated AND `scope.values` is the DERIVED projection of `options`
# ─────────────────────────────────────────────────────────────────────────────────────
_SCOPE_VOCAB = ["Noord", "Zuid", "Oost", "West"]


def test_roundtrip_symmetry_scope_backed_field(table):
    """Author a scope-backed selectable field; its `options` and its `scope.values` MUST be the
    SAME single list (design G2/F7 — `scope.values == [o.value for o in options]`).

    EXPECTED FAIL on unfixed code (NEW counterexample): a scope field's `options` round-trips,
    but `FieldScope.values` is a SEPARATELY stored copy — here it comes back `()` while `options`
    is populated. Two copies of one vocabulary, only one survives: the `FieldScope(values=())`
    divergence (design bug-condition manifestation #2). The 03a fix makes `scope.values` the
    DERIVED projection of the one canonical `options` at a single seam point, so they can never
    diverge.
    """
    MembersConfigWriteRepository(table=table, version_fn=_version).ensure_skeleton(_TENANT)
    svc = _service(table)
    svc.set_group(_TENANT, "membership", {"label": {"en": "Membership"}, "order": 30})
    # A scope-backed field: inline `options` (the vocabulary) AND a `scope` sub-object marking it
    # a scope axis. The scope is authored WITHOUT an independent `values` copy — under the ONE
    # vocabulary model the values ARE the field's options, so the read must DERIVE them.
    svc.set_field(_TENANT, "region", {
        "type": "enum", "label": {"en": "Region"}, "order": 55, "functional_group": "membership",
        "options": [{"value": v, "label": {"en": v, "nl": v}} for v in _SCOPE_VOCAB],
        "scope": {"enabled": True, "required_for": ["Members_CRUD"]},
    })

    cfg = FieldResolver(MembersProjectionReader(table=table)).resolve(_TENANT)
    field = next((f for f in cfg.fields if f.key == "region"), None)
    assert field is not None, "scope-backed field `region` must resolve"

    option_values = [o.value for o in (field.options or [])]
    assert option_values == _SCOPE_VOCAB, (
        f"scope field `options` must carry the authored vocabulary; got {option_values}"
    )
    assert field.scope is not None and field.scope.enabled, (
        "the field must resolve as an enabled scope axis"
    )
    scope_values = list(field.scope.values)
    assert scope_values == option_values, (
        f"SCOPE VOCAB SPLIT (bug): `options` = {option_values} but `scope.values` = {scope_values}. "
        f"`options` and `scope.values` are tracked as TWO copies of one vocabulary — `scope.values` "
        f"came back `{tuple(scope_values)}` while `options` is populated (the FieldScope(values=()) "
        f"divergence). They must be the SAME single list: scope.values == [o.value for o in options]."
    )


# ─────────────────────────────────────────────────────────────────────────────────────
# REFERENCE — `options` == the CURRENT active catalog; both reads agree (G3 carve-out)
# ─────────────────────────────────────────────────────────────────────────────────────
_CATALOG = [("erelid", 10), ("donateur", 20), ("sponsor", 30)]


def _seed_catalog(table):
    repo = DynamoDbMembersRepository(table=table)
    for code, order in _CATALOG:
        repo.save_membership_type(
            _TENANT,
            MembershipTypeEntry(
                tenant_id=_TENANT, type_code=code, label={"nl": code, "en": code},
                active=True, order=order,
            ),
        )
    return [code for code, _ in _CATALOG]


def _option_values(options) -> list[str]:
    return [str(o.get("value")) for o in (options or [])]


def test_roundtrip_symmetry_reference_membership_type(table):
    """A `membership_type` REFERENCE field: its `options` are the LIVE catalog (NOT inline), and
    BOTH reads (staff editor + member form) MUST agree with EACH OTHER and with the CURRENT active
    catalog (design G3 carve-out — NOT `options == what was PUT`, because the catalog lives
    elsewhere and changes independently of the field config).

    This is the generalized symmetry invariant for a kind whose source is external. The fix
    populates `options` from the injected active catalog at the ONE read-assembly seam, uniformly,
    so the staff editor read and the member-form read never disagree and both equal the catalog.
    """
    MembersConfigWriteRepository(table=table, version_fn=_version).ensure_skeleton(_TENANT)
    svc = _service(table)
    catalog_codes = _seed_catalog(table)
    # Put membership_type ON the public form so the member-form read includes it (that read
    # filters to application_visible fields) — making the two reads an apples-to-apples compare.
    svc.set_field_application(_TENANT, "membership_type", {"application_visible": True})

    seam = _field_config_service(table)

    staff = seam.get_field_config(_TENANT)
    staff_mt = next((f for f in staff["fields"] if f["key"] == "membership_type"), None)
    assert staff_mt is not None, "membership_type must be present in the staff config"

    public = seam.get_public_field_config(_TENANT)
    public_mt = next((f for f in public["fields"] if f["key"] == "membership_type"), None)
    assert public_mt is not None, (
        "membership_type must be present in the member-form config (it was made application_visible)"
    )

    staff_values = _option_values(staff_mt.get("options"))
    public_values = _option_values(public_mt.get("options"))

    # Both reads agree with the CURRENT active catalog (NOT with what was PUT — G3).
    assert staff_values == catalog_codes, (
        f"staff editor read must resolve membership_type options to the CURRENT active catalog "
        f"{catalog_codes}; got {staff_values}"
    )
    assert public_values == catalog_codes, (
        f"member-form read must resolve membership_type options to the CURRENT active catalog "
        f"{catalog_codes}; got {public_values}"
    )
    # ... AND with EACH OTHER (the asymmetry this spec kills: the two reads must never disagree).
    assert staff_values == public_values, (
        f"READ ASYMMETRY (bug): the staff editor read {staff_values} and the member-form read "
        f"{public_values} disagree on the reference field's options — one canonical `options` from "
        f"the declared source must be seen identically by every consumer."
    )


# ─────────────────────────────────────────────────────────────────────────────────────
# Task 2 — PRESERVATION cases (observation-first, BEFORE the fix). These assert the OBSERVED
# current behaviour for the NON-bug inputs and MUST PASS on unfixed code (the baseline to keep).
# They are additive to the task-1 RED gate above and do not touch its cases.
# Validates: Requirements 3.1, 3.3
# ─────────────────────────────────────────────────────────────────────────────────────


def _resolved_options(table, key: str):
    """The full rich options the editor read path resolves for `key` (value, label pairs)."""
    cfg = FieldResolver(MembersProjectionReader(table=table)).resolve(_TENANT)
    f = next((x for x in cfg.fields if x.key == key), None)
    if f is None or f.options is None:
        return None
    return [(o.value, dict(o.label)) for o in f.options]


def test_preservation_options_authored_roundtrips_and_is_stable(table):
    """R3.1 preservation (observed on UNFIXED code): an `options`-authored selectable field
    already resolves to a populated `options` through the editor read path, round-trips
    IDENTICALLY (value + i18n label), and a SECOND read returns the SAME thing — the non-bug
    path the fix must leave untouched. Also exercises the spec-03 Change-Op path (a scoped
    `set_field`, no whole-row replace); re-reading proves nothing else drifted (R3.3).
    """
    MembersConfigWriteRepository(table=table, version_fn=_version).ensure_skeleton(_TENANT)
    svc = _service(table)
    svc.set_group(_TENANT, "membership", {"label": {"en": "Membership"}, "order": 30})
    authored = [{"value": v, "label": {"en": v, "nl": v}} for v in _VOCAB]
    svc.set_field(_TENANT, "referral_source", {
        "type": "enum", "label": {"en": "Ref"}, "order": 50, "functional_group": "membership",
        "options": authored,
    })

    expected = [(v, {"en": v, "nl": v}) for v in _VOCAB]
    first = _resolved_options(table, "referral_source")
    assert first == expected, "options-authored field must resolve to the full authored vocabulary"
    # A second read of the same (unchanged) row returns the SAME resolved options — stable,
    # no drift (the already-resolving read path is deterministic; Change-Op left it intact).
    assert _resolved_options(table, "referral_source") == first


def test_preservation_options_authored_write_is_isolated(table):
    """R3.3 preservation: authoring a SECOND options-authored field via a scoped Change-Op does
    NOT disturb the first field's already-resolving vocabulary (no whole-row replace; a sibling
    field survives by construction). Observed on UNFIXED code; must stay true after the fix.
    """
    MembersConfigWriteRepository(table=table, version_fn=_version).ensure_skeleton(_TENANT)
    svc = _service(table)
    svc.set_group(_TENANT, "membership", {"label": {"en": "Membership"}, "order": 30})
    svc.set_field(_TENANT, "referral_source", {
        "type": "enum", "label": {"en": "Ref"}, "order": 50, "functional_group": "membership",
        "options": [{"value": v, "label": {"en": v, "nl": v}} for v in _VOCAB],
    })
    # A SECOND, unrelated options-authored field authored through the Change-Op path.
    svc.set_field(_TENANT, "preferred_contact", {
        "type": "enum", "label": {"en": "Contact"}, "order": 60, "functional_group": "membership",
        "options": [{"value": c, "label": {"en": c, "nl": c}} for c in ("email", "phone")],
    })

    # The FIRST field's vocabulary is untouched by the second write (isolation preserved).
    assert _resolved_vocab(table) == _VOCAB
    # … and the second field resolved its own authored vocabulary.
    assert [v for v, _ in (_resolved_options(table, "preferred_contact") or [])] == ["email", "phone"]

