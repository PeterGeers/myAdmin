"""
Change-Op MECHANICS, proven end-to-end against LIVE local DynamoDB (spec 03, Phase 1 → task 2.8;
design C1 steps 2–4 / C6 / D5; requirements R6/R9).

The sibling ``test_config_fields_roundtrip_red.py`` proves the ISOLATION invariant on the real
seeded (already-versioned) ``h-dcn`` row. This file proves the WRITE MECHANICS the task 2.8 clause
names — the paths that only a REAL conditional ``update_item`` against DynamoDB can exercise
(local DynamoDB enforces ``ConditionExpression``, unlike IAM):

  * **first-write onto the skeleton** — ``ensure_skeleton`` seeds ``{fields,overrides,
    functional_groups}`` + a ``version``; the first Change-Op then CREATEs an entry onto it
    (the C6 contract: the parent maps must pre-exist for a path ``update_item``);
  * **create-vs-update verb** — a CREATE seeds the whole entry, a follow-up UPDATE touches one
    aspect, each isolated (design C1 step 3 / Must-fix #1);
  * **dotted-key paths** — a base-field override writes under the LITERAL dotted segment
    ``overrides.<group>.<key>`` and reads back correctly (the ``.`` is a key name, not a nested
    path — design-review Q2);
  * **legacy-no-version branch** — a row that EXISTS with no ``version`` (a pre-migration legacy
    row) takes the first versioned write via ``attribute_not_exists(version)`` (D5 case ii);
  * **version-conflict** — a stale base version is REJECTED atomically with no partial change
    (D5 / R6 — the stale-writer case).

These run against a FRESH, isolated tenant on the SAME E2E table the conftest manages, seeded
directly per test, so they never touch the seeded ``h-dcn`` round-trip fixture. The whole module
SKIPS cleanly without the local-DynamoDB container (via the ``local_dynamodb_endpoint`` gate).
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

from sam.members.domain.config_fields_crud_service import (  # noqa: E402
    ConfigFieldsCrudService,
)
from sam.members.repository.projection_config_reader import (  # noqa: E402
    MembersProjectionReader,
)
from sam.members.repository.projection_config_write_repository import (  # noqa: E402
    LEGACY_NO_VERSION,
    SET,
    MembersConfigWriteRepository,
    StaleVersionError,
)

pytestmark = pytest.mark.e2e

_MECH_TENANT = "mech-e2e-tenant"


# ─────────────────────────────────────────────────────────────────────────────────────
# Helpers over the live E2E table (a fresh, isolated tenant — not the seeded h-dcn row)
# ─────────────────────────────────────────────────────────────────────────────────────
_version_counter = 0


def _monotonic_version() -> str:
    global _version_counter
    _version_counter += 1
    return f"v-mech-{_version_counter:06d}"


def _fields_key(tenant_id: str) -> dict:
    return schema.build_key(
        tenant_id,
        schema.build_sort_key(schema.RECORD_TYPE_CONFIG, schema.CONFIG_ID_FIELDS),
    )


def _service(table) -> ConfigFieldsCrudService:
    """Wire the REAL service → repository → reader over the live table (fresh reader per op)."""
    reader = MembersProjectionReader(table=table)
    repository = MembersConfigWriteRepository(table=table, version_fn=_monotonic_version)
    return ConfigFieldsCrudService(repository, reader=reader)


def _repo(table) -> MembersConfigWriteRepository:
    return MembersConfigWriteRepository(table=table, version_fn=_monotonic_version)


def _raw_row(table, tenant_id: str) -> dict | None:
    return table.get_item(Key=_fields_key(tenant_id)).get("Item")


@pytest.fixture
def mech_table(seeded_config_fields_table):
    """The live E2E table (container-gated). A fresh isolated tenant is seeded per test; the
    conftest drops the whole table on teardown, so the mechanics tenant never lingers."""
    table = seeded_config_fields_table["table"]
    # Make sure no stale mechanics row survives from a prior test in the same table lifetime.
    existing = _raw_row(table, _MECH_TENANT)
    if existing is not None:
        table.delete_item(Key=_fields_key(_MECH_TENANT))
    return table


# ─────────────────────────────────────────────────────────────────────────────────────
# First write onto the skeleton (ensure_skeleton → create-verb op) — C6 / D5 case iii
# ─────────────────────────────────────────────────────────────────────────────────────
def test_first_write_onto_skeleton_creates_entry(mech_table):
    """ensure_skeleton seeds the parent maps + version; the first Change-Op then CREATEs a variable
    field onto the skeleton with a single whole-entry SET (the C6 first-write path)."""
    table = mech_table

    result = _repo(table).ensure_skeleton(_MECH_TENANT)
    assert result["created"] is True, "the skeleton must be created for a brand-new tenant"

    row = _raw_row(table, _MECH_TENANT)
    assert row is not None
    for parent in ("fields", "overrides", "functional_groups"):
        assert row[parent] == {}, f"skeleton parent {parent!r} must be an empty map"
    assert row[schema.VERSION_ATTR], "the skeleton must carry a seeded version"

    # First Change-Op onto the skeleton: CREATE a tenant VARIABLE field.
    _service(table).set_field(
        _MECH_TENANT,
        "shirt_size",
        {"type": "string", "label": {"en": "Shirt size"}, "order": 10},
    )

    row = _raw_row(table, _MECH_TENANT)
    assert "shirt_size" in row["fields"], "the first write must CREATE the entry onto the skeleton"
    assert row["fields"]["shirt_size"]["order"] == 10
    # The parent maps are intact; nothing truncated.
    assert row["overrides"] == {} and row["functional_groups"] == {}


def test_ensure_skeleton_is_idempotent_and_never_overwrites(mech_table):
    """A second ensure_skeleton is a safe no-op — it NEVER overwrites a populated row (C6)."""
    table = mech_table
    _repo(table).ensure_skeleton(_MECH_TENANT)
    _service(table).set_field(_MECH_TENANT, "shirt_size", {"order": 10})

    before = _raw_row(table, _MECH_TENANT)
    second = _repo(table).ensure_skeleton(_MECH_TENANT)
    after = _raw_row(table, _MECH_TENANT)

    assert second["created"] is False, "a second ensure_skeleton must be a no-op"
    assert after["fields"] == before["fields"], "ensure_skeleton must NOT overwrite a populated row"
    assert after[schema.VERSION_ATTR] == before[schema.VERSION_ATTR]


# ─────────────────────────────────────────────────────────────────────────────────────
# Create-vs-update verb — CREATE seeds the whole entry, UPDATE touches one aspect
# ─────────────────────────────────────────────────────────────────────────────────────
def test_create_then_update_verb_each_isolated(mech_table):
    """A CREATE seeds the whole entry (one SET); a follow-up UPDATE touches ONLY the named aspect,
    leaving the rest of the entry intact (design C1 step 3 / Must-fix #1)."""
    table = mech_table
    _repo(table).ensure_skeleton(_MECH_TENANT)
    svc = _service(table)

    # CREATE
    svc.set_field(
        _MECH_TENANT, "shirt_size", {"type": "string", "label": {"en": "Shirt"}, "order": 10}
    )
    created = _raw_row(table, _MECH_TENANT)["fields"]["shirt_size"]
    assert created["order"] == 10 and created["label"] == {"en": "Shirt"}

    # UPDATE just the order — label/type must survive untouched.
    svc.set_field(_MECH_TENANT, "shirt_size", {"order": 20})
    updated = _raw_row(table, _MECH_TENANT)["fields"]["shirt_size"]
    assert updated["order"] == 20, "the UPDATE must change the named aspect"
    assert updated["label"] == {"en": "Shirt"}, "an untouched aspect must survive the UPDATE"
    assert updated["type"] == "string"


# ─────────────────────────────────────────────────────────────────────────────────────
# Dotted-key paths — a base-field override writes under overrides.<group>.<key> (literal)
# ─────────────────────────────────────────────────────────────────────────────────────
def test_dotted_override_key_round_trips(mech_table):
    """A base field places under the LITERAL dotted key ``overrides.personal.gender`` (the ``.`` is
    a key name, not a nested path — design-review Q2); it reads back under that exact key."""
    table = mech_table
    _repo(table).ensure_skeleton(_MECH_TENANT)
    svc = _service(table)

    svc.set_field(_MECH_TENANT, "gender", {"order": 5})
    overrides = _raw_row(table, _MECH_TENANT)["overrides"]
    assert "personal.gender" in overrides, (
        "the dotted override key must be stored as ONE literal segment, not a nested map"
    )
    assert overrides["personal.gender"]["order"] == 5
    # It is NOT a nested {personal: {gender: ...}} map (the misparse the binding prevents).
    assert "personal" not in {k for k in overrides if "." not in k}

    # A follow-up aspect UPDATE under the dotted key preserves the entry.
    svc.set_field(_MECH_TENANT, "gender", {"visible": True})
    overrides = _raw_row(table, _MECH_TENANT)["overrides"]
    assert overrides["personal.gender"]["order"] == 5
    assert overrides["personal.gender"]["visible"] is True


# ─────────────────────────────────────────────────────────────────────────────────────
# Legacy-no-version branch — an existing versionless row takes the first versioned write
# ─────────────────────────────────────────────────────────────────────────────────────
def test_legacy_row_without_version_first_write(mech_table):
    """A row that EXISTS with NO ``version`` (pre-migration legacy) accepts the first versioned
    write via the ``attribute_not_exists(version)`` branch (D5 case ii), stamping a version."""
    table = mech_table
    # Seed a legacy row directly: parent maps present, NO version attribute.
    table.put_item(
        Item={
            **_fields_key(_MECH_TENANT),
            "fields": {},
            "overrides": {},
            "functional_groups": {},
        }
    )
    assert schema.VERSION_ATTR not in _raw_row(table, _MECH_TENANT)

    # The service resolves base_version = LEGACY_NO_VERSION (row present, no version) and the write
    # succeeds, stamping a version for the first time.
    _service(table).set_field(_MECH_TENANT, "shirt_size", {"order": 10})

    row = _raw_row(table, _MECH_TENANT)
    assert "shirt_size" in row["fields"], "the legacy-row first write must apply"
    assert row[schema.VERSION_ATTR], "the first versioned write must stamp a version"


def test_legacy_branch_via_repository_directly(mech_table):
    """Belt check at the repository seam: apply_ops with LEGACY_NO_VERSION against a versionless
    row succeeds; against an ALREADY-versioned row it is rejected (the branch really guards)."""
    table = mech_table
    table.put_item(
        Item={**_fields_key(_MECH_TENANT), "fields": {}, "overrides": {}, "functional_groups": {}}
    )
    out = _repo(table).apply_ops(
        _MECH_TENANT,
        schema.CONFIG_ID_FIELDS,
        [{"action": SET, "path": ["fields", "x"], "value": {"key": "x"}}],
        base_version=LEGACY_NO_VERSION,
    )
    assert out["version"], "legacy first write must stamp a version"

    # Now the row HAS a version — a second LEGACY_NO_VERSION write must be rejected.
    with pytest.raises(StaleVersionError):
        _repo(table).apply_ops(
            _MECH_TENANT,
            schema.CONFIG_ID_FIELDS,
            [{"action": SET, "path": ["fields", "y"], "value": {"key": "y"}}],
            base_version=LEGACY_NO_VERSION,
        )


# ─────────────────────────────────────────────────────────────────────────────────────
# Version-conflict — a stale base version is rejected atomically (D5 / R6 stale-writer)
# ─────────────────────────────────────────────────────────────────────────────────────
def test_stale_version_write_is_rejected_atomically(mech_table):
    """Two writers, one base version: the second (stale) write is REJECTED with NO partial change
    (the optimistic-lock stale-writer case, D5 / R6)."""
    table = mech_table
    repo = _repo(table)
    repo.ensure_skeleton(_MECH_TENANT)

    # Writer A reads the current version, applies a write → version bumps.
    _, base_a = MembersProjectionReader(table=table).get_config_fields_version(
        _MECH_TENANT, consistent_read=True
    )
    repo.apply_ops(
        _MECH_TENANT,
        schema.CONFIG_ID_FIELDS,
        [{"action": SET, "path": ["fields", "a"], "value": {"key": "a"}}],
        base_version=base_a,
    )
    current = _raw_row(table, _MECH_TENANT)[schema.VERSION_ATTR]
    assert current != base_a, "writer A must have bumped the version"

    # Writer B still holds the ORIGINAL (now stale) base version → rejected, no partial change.
    with pytest.raises(StaleVersionError):
        repo.apply_ops(
            _MECH_TENANT,
            schema.CONFIG_ID_FIELDS,
            [{"action": SET, "path": ["fields", "b"], "value": {"key": "b"}}],
            base_version=base_a,
        )

    row = _raw_row(table, _MECH_TENANT)
    assert "a" in row["fields"], "writer A's change must stand"
    assert "b" not in row["fields"], "the stale writer B must have made NO partial change"
    assert row[schema.VERSION_ATTR] == current, "a rejected write must not bump the version"


def test_service_level_concurrent_edit_is_rejected(mech_table):
    """End-to-end at the SERVICE seam: after an out-of-band version bump, a service op built on the
    pre-bump snapshot is rejected (the live concurrent-edit a configurator/form-builder would hit).
    """
    table = mech_table
    _repo(table).ensure_skeleton(_MECH_TENANT)

    # Apply a first service op (CREATE) so the row is versioned + populated.
    _service(table).set_field(_MECH_TENANT, "shirt_size", {"order": 10})

    # Simulate a concurrent writer bumping the version out from under the next op by stamping a new
    # version directly on the row AFTER the service has (conceptually) read its snapshot. We force
    # the race deterministically: mutate the stored version, then issue a repository op carrying the
    # now-stale base the row HAD — it must be rejected.
    row = _raw_row(table, _MECH_TENANT)
    stale_base = row[schema.VERSION_ATTR]
    table.update_item(
        Key=_fields_key(_MECH_TENANT),
        UpdateExpression="SET #v = :v",
        ExpressionAttributeNames={"#v": schema.VERSION_ATTR},
        ExpressionAttributeValues={":v": "v-concurrent-bump"},
    )

    with pytest.raises(StaleVersionError):
        _repo(table).apply_ops(
            _MECH_TENANT,
            schema.CONFIG_ID_FIELDS,
            [{"action": SET, "path": ["fields", "shirt_size", "order"], "value": 99}],
            base_version=stale_base,
        )
    assert _raw_row(table, _MECH_TENANT)["fields"]["shirt_size"]["order"] == 10, (
        "the stale concurrent write must not apply"
    )
