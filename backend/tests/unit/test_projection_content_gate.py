"""Content-gate tests for the Members config projection write (R1, task 1).

These tests are written BEFORE the fix (spec
`.kiro/specs/Members/members-config-projection-and-cleanup`). Task 1 asks for the
exploration + property tests that pin the INTENDED content-driven write behaviour; on
the current (unfixed) `ProjectionSync` the version-strictly-greater gate in
`_conditional_put` refuses a correcting write whenever the incoming version is not
strictly greater than the stored one — even when the CONTENT differs. Task 1.1 (this
file's first test) reproduces that exact wedge and is EXPECTED TO FAIL on current code:
a failing assertion here is the SUCCESS case — it confirms the bug exists. The fix lands
in tasks 2–4; task 4.2 re-runs these tests green.

In-memory fakes only (no real AWS / MySQL): the `FakeTable` / `FakeSource` /
`FakeParameterService` seams defined in `test_projection_sync.py` are REUSED here so the
tests exercise the real `ProjectionSync` write path against the same conditional-version
semantics a real DynamoDB table enforces.

Feature: members-config-projection-and-cleanup
Validates: Requirements 1.2, 1.3, 1.6, 1.8
"""

import pytest

from services import projection_schema as schema
from services.module_registry import MODULE_REGISTRY
from services.projection_sync import ProjectionSync, build_config_fields_row

# Reuse the exact in-memory seams the existing projection-sync suite drives the sole
# writer with — same conditional-version table semantics, same read-only param service.
from tests.unit.test_projection_sync import (
    FakeParameterService,
    FakeSource,
    FakeTable,
    _tenant_source,
)

# A stable per-param revision for the `members.field_overlay` param. The WEDGE is that
# the stored row is stamped at THIS SAME revision while carrying stale (6-value) content,
# so the strict-greater version gate can never heal it.
_OVERLAY_REVISION = "2026-01-01T00:00:00"

# The membership.status vocabulary. The stored (wedged) row carries the 6 platform
# values; the source overlay authors the 7-value set that ADDS the tenant value `died`
# ("Overleden") — the concrete regression that triggered this spec (R1.8).
_STATUS_SIX = ["active", "inactive", "pending", "suspended", "honorary", "lapsed"]
_STATUS_SEVEN = [*_STATUS_SIX, "died"]

_FIELDS_SK = schema.build_sort_key(schema.RECORD_TYPE_CONFIG, schema.CONFIG_ID_FIELDS)


@pytest.fixture
def sam_module(monkeypatch):
    """A test-local SAM-backed module so the projection gate fires (mirrors
    test_projection_sync.py) without touching the shipped registry."""
    name = "SAM_TEST_MODULE"
    monkeypatch.setitem(
        MODULE_REGISTRY,
        name,
        {
            "description": "Temporary SAM-backed test module",
            "required_params": {},
            "required_tax_rates": [],
            "required_roles": ["SamTest_Read"],
            "backing": {
                "kind": "sam",
                "api_base_env": "SAM_TEST_MODULE_API_BASE",
                "data_namespace": "sam_test",
            },
        },
    )
    return name


def _status_overlay(values):
    """A `members.field_overlay` value authoring `membership.status` as a fixed-field
    override whose enum vocabulary is `values` — the shape the builder maps 1:1 into
    `config#fields.overrides["membership.status"]`, exactly as `gender` values flow."""
    return {
        "fixed_overrides": {
            "membership.status": {
                "label": {"nl": "Status", "en": "Status"},
                "choices": list(values),
            }
        }
    }


def _overlay_params(tenant_id, overlay):
    """A FakeParameterService serving `overlay` for members.field_overlay at the fixed
    wedge revision (the stored row will be stamped at the SAME revision)."""
    return FakeParameterService(
        params={("members", "field_overlay", tenant_id): overlay},
        revisions={("members", "field_overlay", tenant_id): _OVERLAY_REVISION},
    )


def _status_values_in(table, tenant_id):
    """The `membership.status` choices currently stored on the tenant's config#fields row."""
    stored = table.store.get((tenant_id, _FIELDS_SK))
    assert stored is not None, "expected a stored config#fields row"
    return stored["overrides"]["membership.status"]["choices"]


# ===========================================================================
# Task 1.1 — reproduce the exact wedge (EXPECTED TO FAIL on current code)
# ===========================================================================


# ===========================================================================
# Task 1.2 — Property P2 (idempotent): an unchanged source re-syncs to a
# byte-identical row and writes nothing (EXPECTED TO PASS on current code)
# ===========================================================================
#
# P2 (design.md): "Idempotent — for any row whose built content equals stored
# content, a re-sync writes nothing and leaves the row byte-identical."
# Validates: Requirements 1.3, 1.6.
#
# This property holds on BOTH the current (unfixed) and fixed code: for an
# UNCHANGED source the freshly-built row carries the SAME version as the stored
# row, so the current strict-greater gate (`_supersedes(incoming, stored)` with
# incoming == stored → False) already SKIPS the write — which is exactly the
# idempotent no-op P2 demands. (The fix in tasks 2–4 makes the gate
# content-driven, which must ALSO skip when content is equal — so P2 keeps
# holding.) If this test does NOT pass on current code, do not weaken it —
# investigate and report.
#
# Detection of "writes nothing / byte-identical" uses the `FakeTable` reused from
# `test_projection_sync.py`, which already records every `put_item` in
# `put_calls` and stores items keyed by (tenant_id, sk). A genuine (persisting)
# write only happens when `_conditional_put` passes its gate AND reaches
# `table.put_item`; on an unchanged re-sync the gate short-circuits BEFORE
# `put_item`, so `put_calls` does not grow. We assert both: (a) no new
# `put_item` was recorded by the re-sync, and (b) the whole stored partition is
# byte-for-byte identical (deep-equal) to the pre-re-sync snapshot — including
# the `version`/bookkeeping attributes, i.e. no churn of any kind.

from hypothesis import given, settings
from hypothesis import strategies as st

# The platform membership.status vocabulary values the generator draws from. A
# generated overlay authors a non-empty, de-duplicated, order-preserving subset
# (optionally incl. the tenant value `died`) as the fixed-field override — the
# same authoring shape as the wedge test above, so the built row is realistic.
_STATUS_VOCAB = [*_STATUS_SIX, "died"]


def _status_subsets():
    """Non-empty, order-preserving, de-duplicated subsets of the status vocab.

    A smart generator constrained to the real input space: `membership.status`
    choices are a non-empty ordered set of known status values (the tenant may or
    may not include `died`). De-duplication + order preservation mirror how the
    builder maps `choices` 1:1 onto `overrides["membership.status"]["choices"]`.
    """

    def _dedupe(values):
        seen = {}
        for v in values:
            seen.setdefault(v, None)
        return list(seen.keys())

    return st.lists(
        st.sampled_from(_STATUS_VOCAB), min_size=1, max_size=len(_STATUS_VOCAB)
    ).map(_dedupe)


def _snapshot(table):
    """A deep (byte-identical) copy of the whole stored projection partition map."""
    import copy

    return {k: copy.deepcopy(v) for k, v in table.store.items()}


# ===========================================================================
# Task 1.3 — Property P4 (concrete regression): a tenant overlay authoring
# `membership.status` incl. `died` projects `overrides["membership.status"]`
# containing `died`, exactly as `gender` values already do.
# (EXPECTED TO PASS on current code — this pins the BUILDER output, not the
#  write-gate wedge.)
# ===========================================================================
#
# P4 (design.md): "Concrete regression — a tenant overlay authoring
# `membership.status` including `died` projects a `config#fields` whose
# `overrides["membership.status"]` vocabulary contains `died`, exactly as
# `gender` values already do." Validates: Requirement 1.8.
#
# The POINT of P4 vs the task-1.1 wedge test: P4 verifies the BUILDER output
# directly (`build_config_fields_row` maps the authored overlay's
# `membership.status` choices — incl. `died` — into `overrides["membership.status"]`,
# parallel to how the authored `gender` values flow into
# `overrides["personal.gender"]`). This is about the BUILT ROW'S CONTENT, NOT the
# write-gate wedge — so P4 PASSES on current (unfixed) code (the builder already
# produces the correct content; it's the WRITE that wedges). If it does NOT pass,
# do not weaken it — investigate and report.
#
# To show the "same as gender" parallel faithfully, the overlay authors BOTH a
# `personal.gender` override and a `membership.status` override (incl. `died`) as
# `fixed_overrides` with the RICH `{value, label:{nl,en}}` choices shape the real
# h-dcn tenant config uses (`scripts/onboarding/members/h-dcn/members_config.json`:
# both `gender` and `status` are OPEN enums the tenant authors — a `choices` list
# of value/label dicts, no shipped `options`). Both are OPEN enums the tenant
# authors identically, so `died` must land in `membership.status` exactly as the
# gender values land in `personal.gender`.

# The authored `gender` vocabulary (h-dcn's M/V/X/N open-enum), as a fixed-field
# override — the SAME authoring shape as `membership.status`. Used to assert the
# `died`-in-status parallel: status values flow into the built row exactly as
# these gender values do.
_GENDER_VALUES = ["M", "V", "X", "N"]
_GENDER_LABELS = {
    "M": {"nl": "Man", "en": "Male"},
    "V": {"nl": "Vrouw", "en": "Female"},
    "X": {"nl": "Anders", "en": "Other"},
    "N": {"nl": "Wil niet zeggen", "en": "Prefer not to say"},
}

# Bilingual labels for the status values the generator may draw (incl. the
# tenant-authored `died`/"Overleden" that triggered this spec, R1.8). Mirrors the
# h-dcn status seed shape — a rich `{value, label:{nl,en}}` choice per value.
_STATUS_LABELS = {
    "active": {"nl": "Actief", "en": "Active"},
    "inactive": {"nl": "Inactief", "en": "Inactive"},
    "pending": {"nl": "In behandeling", "en": "Pending"},
    "suspended": {"nl": "Geschorst", "en": "Suspended"},
    "honorary": {"nl": "Erelid", "en": "Honorary"},
    "lapsed": {"nl": "Verlopen", "en": "Lapsed"},
    "died": {"nl": "Overleden", "en": "Died"},
}


def _rich_choices(values, labels):
    """Render `values` as the RICH `[{value, label:{nl,en}}, …]` choices shape the
    real tenant config authors for an OPEN enum (gender/status) — a list of
    value/label dicts, no shipped `options`. The builder carries this verbatim onto
    `config#fields.overrides[dotted]["choices"]` (`_map_fixed_override`)."""
    return [{"value": v, "label": labels[v]} for v in values]


def _gender_and_status_overlay(status_values):
    """A `members.field_overlay` authoring BOTH `personal.gender` (the fixed M/V/X/N
    open-enum) AND `membership.status` (= `status_values`, which the generator
    guarantees includes `died`) as `fixed_overrides` — the exact parallel the spec
    (R1.8) asks for: status is an OPEN enum authored just like gender, so a
    tenant-added value (`died`) must surface in the built row's
    `overrides["membership.status"]` exactly as the gender values do in
    `overrides["personal.gender"]`."""
    return {
        "fixed_overrides": {
            "personal.gender": {
                "functional_group": "personal",
                "label": {"nl": "Geslacht", "en": "Gender"},
                "choices": _rich_choices(_GENDER_VALUES, _GENDER_LABELS),
            },
            "membership.status": {
                "functional_group": "membership",
                "label": {"nl": "Status", "en": "Status"},
                "choices": _rich_choices(status_values, _STATUS_LABELS),
            },
        }
    }


def _choice_values(choices):
    """The ordered `value`s of a projected `overrides[dotted]["choices"]` list.

    Faithful to how the builder carries an OPEN-enum vocabulary: a rich choice is a
    `{value, label}` dict (the gender/status authoring shape), a bare choice is a
    plain string. Extract the `value` either way so the assertion compares the
    authored vocabulary regardless of representation."""
    values = []
    for choice in choices:
        if isinstance(choice, dict):
            values.append(choice["value"])
        else:
            values.append(choice)
    return values


def _status_subsets_including_died():
    """Non-empty, order-preserving, de-duplicated status subsets that ALWAYS include
    the tenant-authored `died` (R1.8's concrete regression value).

    A smart generator constrained to the real input space: `membership.status`
    choices are a non-empty ordered set of known status values, and P4 is
    specifically about the tenant value `died` surviving projection — so every
    generated vocabulary includes `died` (placed at a generated position among the
    platform values, de-duplicated, order preserved), exactly how a tenant adds
    `died` to the seeded list."""

    def _dedupe(values):
        seen = {}
        for v in values:
            seen.setdefault(v, None)
        return list(seen.keys())

    platform = _STATUS_SIX

    return st.lists(
        st.sampled_from(platform), min_size=0, max_size=len(platform)
    ).flatmap(
        lambda base: st.integers(min_value=0, max_value=len(base)).map(
            lambda pos: _dedupe([*base[:pos], "died", *base[pos:]])
        )
    )


@settings(max_examples=100, deadline=None)
@given(status_values=_status_subsets_including_died())
def test_build_config_fields_projects_tenant_status_value_like_gender(status_values):
    """Feature: members-config-projection-and-cleanup, Property 4: Concrete regression.

    Validates: Requirements 1.8.

    For ANY tenant-authored `membership.status` vocabulary that includes the tenant
    value `died`, the freshly BUILT `config#fields` row carries `died` in
    `overrides["membership.status"]`'s vocabulary, EXACTLY as the authored `gender`
    values (M/V/X/N) land in `overrides["personal.gender"]`:
      * both authored fixed-field overrides are present on the built row,
      * `overrides["membership.status"]` carries the full authored status
        vocabulary (incl. `died`) verbatim and in order, and
      * `overrides["personal.gender"]` carries the full authored gender vocabulary
        verbatim and in order — the two flow through the builder identically.

    This pins the BUILDER output (content), not the write gate — so it holds on the
    current (unfixed) code. The builder already maps a tenant-authored open-enum
    value into the projected row; the spec's wedge is in the WRITE decision
    (task 1.1), not here.
    """
    tenant_id = "h-dcn"
    overlay = _gender_and_status_overlay(status_values)
    params = _overlay_params(tenant_id, overlay)

    item = build_config_fields_row({"administration": tenant_id}, params)

    overrides = item.attributes["overrides"]

    # Both authored fixed-field overrides are projected — status is authored exactly
    # like gender, so both must appear.
    assert "membership.status" in overrides, (
        "P4 VIOLATED: the built config#fields row dropped the authored "
        "`membership.status` override entirely."
    )
    assert "personal.gender" in overrides, (
        "P4 VIOLATED: the built config#fields row dropped the authored "
        "`personal.gender` override entirely."
    )

    status_choice_values = _choice_values(overrides["membership.status"]["choices"])
    gender_choice_values = _choice_values(overrides["personal.gender"]["choices"])

    # The concrete regression (R1.8): the tenant-authored `died` survives into the
    # projected status vocabulary.
    assert "died" in status_choice_values, (
        "P4 VIOLATED (R1.8): the tenant-authored `died` did not land in the built "
        f"`overrides['membership.status']` vocabulary {status_choice_values!r} — a "
        "tenant-added status value must project exactly as `gender` values do."
    )

    # The full authored vocabularies flow through the builder verbatim and in order,
    # for BOTH fields — status is projected identically to gender (the parallel the
    # spec names).
    assert status_choice_values == list(status_values), (
        "P4 VIOLATED: the built status vocabulary "
        f"{status_choice_values!r} != the authored {list(status_values)!r}."
    )
    assert gender_choice_values == _GENDER_VALUES, (
        "P4 VIOLATED: the built gender vocabulary "
        f"{gender_choice_values!r} != the authored {_GENDER_VALUES!r} — status and "
        "gender must flow through the builder identically."
    )


def test_build_config_fields_projects_died_in_status_like_gender_concrete(sam_module):
    """R1.8 concrete regression (worked example): the exact `died`/"Overleden" case
    that triggered the spec.

    A tenant authors the 7-value `membership.status` open enum (the 6 platform
    values PLUS `died`/"Overleden") alongside the M/V/X/N `gender` open enum. The
    freshly BUILT `config#fields` row carries `died` in
    `overrides["membership.status"]`'s vocabulary exactly as it carries M/V/X/N in
    `overrides["personal.gender"]` — both open enums the tenant authors, projected
    the same way. Holds on current (unfixed) code: this is the builder's content,
    not the write gate (task 1.1's wedge).
    """
    tenant_id = "h-dcn"
    overlay = _gender_and_status_overlay(_STATUS_SEVEN)
    params = _overlay_params(tenant_id, overlay)

    item = build_config_fields_row({"administration": tenant_id}, params)
    overrides = item.attributes["overrides"]

    status_values = _choice_values(overrides["membership.status"]["choices"])
    gender_values = _choice_values(overrides["personal.gender"]["choices"])

    assert status_values == _STATUS_SEVEN  # 6 platform values + `died`
    assert "died" in status_values
    # Same-as-gender parallel: the gender open enum is carried verbatim too.
    assert gender_values == _GENDER_VALUES


# ===========================================================================
# Task 3.3 — GENERALITY: the content-gate heals a wedge on ANY config#* row
# type, not just config#fields/status. The write decision lives in the shared
# ProjectionSync seam (`_conditional_put` / `_content_key` over the flat
# `to_dynamodb_item()` payload, excluding version/updated_at/tenant_id/sk), so
# it is row-type-agnostic. These tests reproduce-and-heal the SAME
# equal-version-different-content wedge for `config#scope` AND `config#mail`
# (NOT status / config#fields), proving the heal is not a special case (R1.7).
#
# Validates: Requirements 1.2, 1.3, 1.5, 1.6, 1.7
# ===========================================================================

from services.projection_sync import build_config_mail_row

_MAIL_SK = schema.build_sort_key(schema.RECORD_TYPE_CONFIG, schema.CONFIG_ID_MAIL)

# A stable per-param revision stamped on the source param that drives each row.
# The WEDGE is that the stored row is stamped at THIS SAME revision while
# carrying STALE content, so the strict-greater version gate can never heal it —
# only the content-gate can. (Same mechanism as the config#fields wedge above,
# but for a DIFFERENT row type, which is the whole point of generality.)
_MAIL_REVISION = "2026-03-01T00:00:00"


# --- config#scope generality: retired here, preserved by the config#mail twins ---
#
# Task 3.7 removed config#scope from ProjectionSync's emission (SAM owns it). The content-gate
# GENERALITY guarantee (R1.2/R1.7 — the content-gate heals ANY config#* row type on a content
# change at an equal version, not just config#fields/status) was formerly proven here using
# config#scope as a second vehicle. config#scope is no longer sync-emitted, so it can no longer
# be a vehicle; the guarantee is PRESERVED by the config#mail twins below
# (`test_sync_heals_wedged_config_mail_*` / `test_sync_rerun_unchanged_config_mail_is_noop`) —
# a DISTINCT non-status config#* row healing through the same `_conditional_put` / `_content_key`
# seam — plus the original config#fields wedge above. No generality coverage is lost.

# --- config#mail wedge setup (driven by the `members.mail_domain` param) ---------


def _mail_params(tenant_id, domain):
    """A FakeParameterService authoring `members.mail_domain = domain` (mail
    enabled), stamped at the fixed mail wedge revision. STALE vs FRESH differ only
    in the domain string, at the SAME revision — a pure content change at an equal
    version for the config#mail row type."""
    return FakeParameterService(
        params={
            ("members", "mail_enabled", tenant_id): True,
            ("members", "mail_domain", tenant_id): domain,
        },
        revisions={("members", "mail_domain", tenant_id): _MAIL_REVISION},
    )


def _mail_domain_in(table, tenant_id):
    """The `mail_domain` currently stored on the tenant's config#mail row."""
    stored = table.store.get((tenant_id, _MAIL_SK))
    assert stored is not None, "expected a stored config#mail row"
    return stored["mail_domain"]


_MAIL_STALE_DOMAIN = "old-domain.example"
_MAIL_FRESH_DOMAIN = "h-dcn.nl"


def test_sync_heals_wedged_config_mail_when_content_differs_at_equal_version(
    sam_module,
):
    """R1.2/R1.7 GENERALITY — the SAME wedge-and-heal for `config#mail`: a stored
    `config#mail` row holds a STALE `mail_domain` at version V; the source authors
    a DIFFERENT domain at the SAME version V. A sync MUST write the fresh domain
    (content differs → heal), EVEN THOUGH the incoming version is not strictly
    greater than the stored one.

    A THIRD distinct `config#*` row type healing through the SAME shared seam
    (`_conditional_put` / `_content_key`) confirms the content-gate is row-type-
    agnostic, not a status/config#fields special-case (R1.7).
    """
    tenant_id = "h-dcn"
    table = FakeTable()
    params = _mail_params(tenant_id, _MAIL_FRESH_DOMAIN)

    # Pre-seed the WEDGED stored row: STALE domain, stamped at the SAME version the
    # builder computes for this source (the mail_domain param's own revision).
    stale_item = build_config_mail_row(
        {"administration": tenant_id}, _mail_params(tenant_id, _MAIL_STALE_DOMAIN)
    )
    assert stale_item.version == _MAIL_REVISION  # stored version == source version V
    table.store[(tenant_id, _MAIL_SK)] = stale_item.to_dynamodb_item()
    assert _mail_domain_in(table, tenant_id) == _MAIL_STALE_DOMAIN

    source = FakeSource({tenant_id: _tenant_source(tenant_id, sam_module)})
    sync = ProjectionSync(source, table=table, parameter_service=params)

    sync.sync_administration(tenant_id)

    # The heal: the stored row now carries the fresh domain, proving the write
    # followed CONTENT, not the (equal) version — for config#mail.
    healed = _mail_domain_in(table, tenant_id)
    assert healed == _MAIL_FRESH_DOMAIN, (
        "GENERALITY WEDGE (config#mail): the stored row still carries the stale "
        f"mail_domain {healed!r} — the content-gate failed to heal a config#mail "
        "row, so the fix is a config#fields/status special-case, not general (R1.7)."
    )


def test_sync_rerun_unchanged_config_mail_is_noop(sam_module):
    """R1.3/R1.6 GENERALITY (idempotence) — for config#mail too, a re-sync against
    an UNCHANGED source writes nothing and leaves the row byte-identical (equal
    content → skip), the mirror of the heal above."""
    tenant_id = "h-dcn"
    table = FakeTable()
    params = _mail_params(tenant_id, _MAIL_FRESH_DOMAIN)
    source = FakeSource({tenant_id: _tenant_source(tenant_id, sam_module)})
    sync = ProjectionSync(source, table=table, parameter_service=params)

    first = sync.sync_administration(tenant_id)
    assert first.written > 0
    assert _mail_domain_in(table, tenant_id) == _MAIL_FRESH_DOMAIN
    snapshot = {k: dict(v) for k, v in table.store.items()}
    put_calls_after_first = len(table.put_calls)

    second = sync.sync_administration(tenant_id)

    assert second.written == 0, (
        f"idempotence VIOLATED (config#mail): re-sync wrote {second.written} row(s)."
    )
    assert len(table.put_calls) == put_calls_after_first
    assert {k: dict(v) for k, v in table.store.items()} == snapshot


# ===========================================================================
# Task 4.1 — validate-before-write: a malformed config#* build is REJECTED
# (raises) BEFORE any put, and the tenant's batch aborts ATOMICALLY (nothing
# written). This is the LOUD-failure path (design.md A4, R1.4): a build that
# cannot produce a valid row never silently stale-leaves — the raise surfaces
# through the save route's `_project_tenant_change` outcome.
# ===========================================================================
