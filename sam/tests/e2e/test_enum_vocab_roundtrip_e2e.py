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

import importlib.util
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
from sam.members.domain.scope_dimensions import (  # noqa: E402
    ScopeDimension,
    StaticScopeConfigProvider,
)

pytestmark = pytest.mark.e2e


# ── The C7 choices->options backfill, loaded from scripts/ (not an importable package) ──────
# Reused VERBATIM here (not hand-rolled) so the legacy-row cases migrate exactly the way the
# committed migration does — see `sam/tests/test_migrate_config_fields_choices_to_options.py`.
def _load_migration_module():
    path = os.path.join(_REPO_ROOT, "scripts", "migrate_config_fields_choices_to_options.py")
    spec = importlib.util.spec_from_file_location(
        "migrate_config_fields_choices_to_options", path
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


_mig = _load_migration_module()

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


def _seed_bare_choices_variable_field(table, field_key: str, vocab):
    """Seed a tenant VARIABLE field carrying bare `choices` (`options` ABSENT) DIRECTLY into the
    `config#fields` row — the real h-dcn un-migrated legacy shape.

    This mirrors the C7 migration test's `_seed_variable_field_row`
    (`sam/tests/test_migrate_config_fields_choices_to_options.py`) rather than going through
    `set_field`: the write surface (03a C2) RETIRED `choices`, so `set_field` correctly REJECTS a
    `choices` payload. A legacy row can only arrive by direct seeding (it was written before the
    invariant existed) — which is exactly the state the C7 backfill exists to migrate. Keyed under
    the `fields` map by its bare key (the real shape for a tenant-added selectable field).
    """
    item = table.get_item(Key=_key()).get("Item")
    if item is None:
        item = {
            schema.PARTITION_KEY_ATTR: _TENANT,
            schema.SORT_KEY_ATTR: schema.build_sort_key(
                schema.RECORD_TYPE_CONFIG, schema.CONFIG_ID_FIELDS
            ),
            "fields": {},
            "overrides": {},
            "functional_groups": {},
            schema.VERSION_ATTR: "v-seed",
        }
    fields = dict(item.get("fields") or {})
    fields[field_key] = {
        "type": "enum",
        "label": {"en": "Ref", "nl": "Bron"},
        "functional_group": "membership",
        "order": 50,
        "choices": list(vocab),  # bare `choices`, no `options` — the un-migrated legacy shape
    }
    item["fields"] = fields
    table.put_item(Item=item)


def _run_c7_backfill(table):
    """Run the committed C7 `choices`->`options` backfill over the live table for `_TENANT`,
    reusing the real migration driver (`migrate_tenant`) — the sanctioned way an un-migrated
    legacy row reaches the one-vocabulary model."""
    reader = MembersProjectionReader(table=table)
    service = ConfigFieldsCrudService(
        MembersConfigWriteRepository(table=table, version_fn=_version),
        reader=reader,
    )
    return _mig.migrate_tenant(_TENANT, service=service, reader=reader)


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
    """The REAL h-dcn shape: a legacy row with the vocabulary under bare `choices`, `options`
    absent — which the one-vocabulary model reaches via the C7 backfill (migrate-then-resolve).

    POST-FIX reality (design C6/C7 + Fix-Checking). The write surface RETIRED `choices` (C2), so
    a bare-`choices` row can no longer be AUTHORED through `set_field` — it exists only as an
    UN-MIGRATED legacy row, seeded directly here (the shape the C7 migration test seeds). The
    design's realization of this case's original intent — "a choices-only row must still surface
    in the editor, not vanish" — is MIGRATE-THEN-RESOLVE, not fail-loud: the C6 `choices`-present
    sentinel is the MIGRATION-WINDOW encoding of the P3 asymmetry and is RETIRED once C7 backfills
    (design Glossary / C6 / C7). An un-migrated row fails loud precisely BECAUSE it SHOULD have
    been migrated; migrating it is how the legacy vocabulary round-trips as the canonical
    `options`. So: seed the legacy bare-`choices` row DIRECTLY, run the C7 backfill, then the
    editor read path resolves the SAME six values as `options` (input == output).
    """
    MembersConfigWriteRepository(table=table, version_fn=_version).ensure_skeleton(_TENANT)
    # A legacy bare-`choices` row (the real h-dcn shape), seeded directly — NOT via set_field,
    # which (post-C2) rejects `choices`. This is the un-migrated shape the C7 backfill targets.
    _seed_bare_choices_variable_field(table, "referral_source", _VOCAB)

    # The C7 `choices`->`options` backfill — the sanctioned path onto the one-vocabulary model.
    plans = _run_c7_backfill(table)
    assert [p.entry_key for p in plans] == ["referral_source"], (
        "the C7 backfill must plan exactly the one un-migrated referral_source legacy row"
    )

    # After migration the legacy vocabulary round-trips as the canonical `options` — the choices
    # did NOT vanish from the config editor (the case's original intent), they were migrated.
    got = _resolved_vocab(table)
    assert got == _VOCAB, (
        f"ROUND-TRIP BROKEN: seeded a legacy bare-`choices` row {_VOCAB}; after the C7 backfill "
        f"the editor read path returned {got}. The legacy vocabulary must migrate to canonical "
        f"`options` and round-trip identically — a choices-only row must NOT vanish."
    )


# ─────────────────────────────────────────────────────────────────────────────────────
# SCOPE — `options` populated AND `scope.values` is the DERIVED projection of `options`
# ─────────────────────────────────────────────────────────────────────────────────────
_SCOPE_VOCAB = ["Noord", "Zuid", "Oost", "West"]


def _scope_seam(table):
    """The read-assembly SEAM wired with the region scope dimension as its SANCTIONED source.

    A scope-backed field's vocabulary comes from `config#scope` (the scope dimension), NOT inline
    options — design C4/W2. The resolver stays PURE (it does not populate `options` from the
    dimension); the seam does, in `_assemble_field_options` from the injected `scope_vocab`. So
    the post-fix read path for a scope field is the seam (`get_field_config`), exactly as the
    sanctioned-source test `sam/tests/test_members_scope_dimension_choices.py` reads it — the raw
    resolver would only carry `choices`, never `options`. The region vocabulary is provided via a
    `StaticScopeConfigProvider` (the E2E table has no `config#scope` row), mirroring that test.
    """
    reader = MembersProjectionReader(table=table)
    repo = DynamoDbMembersRepository(table=table)
    scope_provider = StaticScopeConfigProvider(
        {_TENANT: (ScopeDimension(key="region", values=_SCOPE_VOCAB),)}
    )
    return MembershipService(
        repo, overlay_provider=reader, scope_config_provider=scope_provider
    )


def test_roundtrip_symmetry_scope_backed_field(table):
    """A scope-backed selectable field: its `options` come from the scope DIMENSION (its
    sanctioned source), and its scope display vocabulary is the SAME single list — there is no
    independent `scope.values` copy to diverge (design G2/F7, C4/W2).

    Authored through the SANCTIONED source, not inline. The write edge REJECTS inline options on a
    scope-backed field (W2) — a scope field's vocabulary is `config#scope`, never inline — so the
    field is authored as a CHOICELESS scope-backed enum and the region values are provided via the
    scope dimension (`scope_vocab`), exactly as `test_members_scope_dimension_choices.py` does.
    The read-assembly seam populates the field's one canonical `options` FROM that dimension; the
    `FieldScope(values=())` divergence is impossible BY CONSTRUCTION because scope values ARE the
    field's options (one vocabulary, one derivation point) — the staff serializer therefore emits
    NO independent `values` sub-key.
    """
    MembersConfigWriteRepository(table=table, version_fn=_version).ensure_skeleton(_TENANT)
    svc = _service(table)
    svc.set_group(_TENANT, "membership", {"label": {"en": "Membership"}, "order": 30})
    # A CHOICELESS scope-backed enum: an enabled `scope` sub-object marks it a scope axis, and it
    # carries NO inline `options` (W2 rejects inline vocabulary on a scope-backed field). Its
    # dropdown vocabulary is sourced from the scope dimension at the read seam.
    svc.set_field(_TENANT, "region", {
        "type": "enum", "label": {"en": "Region"}, "order": 55, "functional_group": "membership",
        "scope": {"enabled": True, "required_for": ["Members_CRUD"]},
    })

    seam = _scope_seam(table)
    config = seam.get_field_config(_TENANT)
    region = next((f for f in config["fields"] if f["key"] == "region"), None)
    assert region is not None, "scope-backed field `region` must resolve through the seam"

    # `options` is populated from the scope dimension at the ONE read-assembly seam, in the rich
    # `{value, label}` shape (a bare scope value carries an empty i18n label, design G4).
    option_values = [str(o.get("value")) for o in (region.get("options") or [])]
    assert option_values == _SCOPE_VOCAB, (
        f"scope field `options` must be populated from the scope dimension; got {option_values}"
    )
    assert region.get("options") == [
        {"value": v, "label": {}} for v in _SCOPE_VOCAB
    ], "scope options must be the dimension values projected to the canonical rich shape (G4)"

    # The field resolves as an enabled scope axis, and the serialized scope carries NO independent
    # `values` copy — scope values ARE the field's options (single vocabulary, G2/F7), so the
    # `FieldScope(values=())` divergence cannot occur: there is only one list, the options above.
    scope = region.get("scope")
    assert scope is not None and scope.get("enabled") is True, (
        "the field must resolve as an enabled scope axis"
    )
    assert "values" not in scope, (
        "SCOPE VOCAB SPLIT would re-appear if scope carried an INDEPENDENT `values` copy. Under "
        "the one-vocabulary model scope.values is the DERIVED projection of the field's `options` "
        "(a single derivation point), so the serializer emits no separate `values` sub-key — the "
        f"one vocabulary is the options {option_values}."
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

