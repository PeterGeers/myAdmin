"""
Spec 03 Task 2.2 — unit tests for :class:`ConfigFieldsCrudService`, the DISJOINT identity-keyed
Change-Op surface for ``config#fields`` (design C1; design-review Must-fix #3).

What this asserts (the 2.2 surface — placement/verb mechanics are task 2.3)
---------------------------------------------------------------------------
- **Disjointness (the Must-fix #3 guarantee):** ``set_field`` REJECTS an ``application_*`` /
  ``format`` key; ``set_field_application`` REJECTS a DEFINITION key. Neither op can reach the
  other's surface — the structural barrier D3(A) rests on.
- **Absent-vs-null semantics:** an attr ABSENT from the payload yields NO op (untouched); an
  explicit ``None`` yields a scoped ``REMOVE`` of just that aspect; a value yields a ``SET``.
- **The emitted ops match the task-2.4 contract shape:** each op is
  ``{"action": SET|REMOVE, "path": [raw segments outer→inner], "value": <for SET>}``; the service
  hands them to ``apply_ops(tenant_id, config_id="fields", ops, base_version, client_op_id)`` and
  never supplies a storage path or a whole object itself.
- **Identity placement:** a base field (registry) → ``overrides.<dotted>``; a variable field →
  ``fields.<key>``; a group → ``functional_groups.<gkey>``. ``reset_field`` / ``delete_field`` /
  ``delete_group`` emit a single whole-entry ``REMOVE``.
- **Guard rails:** ``delete_field`` refuses a base field (use ``reset_field``); an empty attrs
  payload is rejected.

The repository is an in-memory ``RecordingFakeRepository`` that RECORDS the ops/args handed to
``apply_ops`` (no boto3, no DynamoDB — this service is pure domain, steering 35/39).

**Validates: Requirements 1.3, 2.2, 4.1, 7.2**
"""

import os
import sys

import pytest

# repo root + backend/src on sys.path (mirrors the sibling config-write tests).
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)
_BACKEND_SRC = os.path.join(_REPO_ROOT, "backend", "src")
if _BACKEND_SRC not in sys.path:
    sys.path.insert(0, _BACKEND_SRC)

from sam.members.domain.config_fields_crud_service import (
    ConfigFieldsCrudError,
    ConfigFieldsCrudService,
)
from sam.members.repository.projection_config_write_repository import REMOVE, SET

_TENANT = "crud-tenant"


# ---------------------------------------------------------------------------
# In-memory fake repository (records the apply_ops contract) + fake reader
# ---------------------------------------------------------------------------


class RecordingFakeRepository:
    """Records every ``apply_ops`` call so a test can assert the emitted ops + args.

    Mirrors only the task-2.4 signature the service depends on — no boto3, no update_item. Returns
    the shape the real repository returns so the service passes the result through unchanged.
    """

    def __init__(self):
        self.calls: list[dict] = []

    def apply_ops(self, *, tenant_id, config_id, ops, base_version, client_op_id=None):
        self.calls.append(
            {
                "tenant_id": tenant_id,
                "config_id": config_id,
                "ops": list(ops),
                "base_version": base_version,
                "client_op_id": client_op_id,
            }
        )
        return {"version": "v-next", "idempotent_replay": False}

    @property
    def last(self) -> dict:
        assert self.calls, "apply_ops was never called"
        return self.calls[-1]


class FakeReader:
    """In-memory resolved-view reader for the task-2.3 placement/version mechanics.

    Returns a canned raw ``config#fields`` WIRE overlay (the ``get_raw_fields_overlay`` shape:
    ``fields`` / ``fixed_overrides`` / ``functional_groups`` maps, plus an optional ``version``)
    and RECORDS whether the service requested a strongly-consistent read — so a test can assert
    the ``ConsistentRead`` flag actually flows from the service through the reader (design C1 step
    1 / design-review Should-fix). The ``overrides`` storage map is served under the wire key
    ``fixed_overrides`` (the reader's one-key contract), which is what the service's existence
    check reads.
    """

    def __init__(self, row=None):
        self._row = row
        self.consistent_read_calls: list[bool] = []
        self.version_read_calls: list[bool] = []

    def get_raw_fields_overlay(self, tenant_id, *, consistent_read=False):
        self.consistent_read_calls.append(consistent_read)
        # The AUTHORING WIRE shape carries NO ``version`` — just like the real reader (its contract
        # is "stored maps minus key + version"; the body feeds ``field_overlay`` API responses). A
        # test row may still carry a ``version`` key; strip it here so the wire overlay matches the
        # real reader and the base-version decision is forced through get_config_fields_version.
        if not self._row:
            return {}
        return {k: v for k, v in self._row.items() if k != "version"}

    def get_config_fields_version(self, tenant_id, *, consistent_read=False):
        """The SEPARATE control-plane version read the Change-Op service uses (matches the real
        :meth:`MembersProjectionReader.get_config_fields_version`): ``(present, version)``.

        ``present`` is ``True`` when a row exists at all — modelled here as "the test wired a row".
        ``None`` row → ``(False, None)`` (no row); a row with no ``version`` → ``(True, None)``
        (existing legacy/versionless); a row with a ``version`` → ``(True, <version>)``.
        """
        self.version_read_calls.append(consistent_read)
        if not self._row:
            return (False, None)
        return (True, self._row.get("version"))


class LegacyFakeReader:
    """A reader whose ``get_raw_fields_overlay`` predates the ``consistent_read`` kwarg.

    Proves the service degrades gracefully (falls back to the default read) rather than crashing
    when wired to an older/foreign reader signature — the consistent-read flag is a strengthening,
    not a hard precondition for placement.
    """

    def __init__(self, row=None):
        self._row = row
        self.plain_calls = 0

    def get_raw_fields_overlay(self, tenant_id):
        self.plain_calls += 1
        return dict(self._row) if self._row else {}


@pytest.fixture
def repo():
    return RecordingFakeRepository()


@pytest.fixture
def service(repo):
    """Service with NO reader: no snapshot observable → placement defaults to the CREATE verb
    (correct for a first write onto the C6 skeleton). Disjointness / surface-guard tests that do
    not care about the verb use this fixture."""
    return ConfigFieldsCrudService(repo)


def _existing_service(repo, *entries):
    """A service wired to a reader whose row ALREADY contains the given entries, so placement
    chooses the UPDATE (per-aspect) verb.

    ``entries`` are ``(wire_container_key, entry_key)`` pairs, e.g.
    ``("fixed_overrides", "membership.status")`` for a base-field override that exists, or
    ``("fields", "shirt_size")`` for a variable field that exists. A ``version`` is included so
    the base-version is an optimistic lock (an existing authored row).
    """
    row = {"fields": {}, "fixed_overrides": {}, "functional_groups": {}, "version": "v-1"}
    for container_key, entry_key in entries:
        row.setdefault(container_key, {})[entry_key] = {}
    return ConfigFieldsCrudService(repo, reader=FakeReader(row))


# ---------------------------------------------------------------------------
# DISJOINTNESS — the Must-fix #3 guarantee
# ---------------------------------------------------------------------------


def test_set_field_rejects_application_attribute_keys(service):
    """set_field is structurally unable to write an application_* attr (design-review Must-fix #3)."""
    with pytest.raises(ConfigFieldsCrudError) as exc:
        service.set_field(_TENANT, "gender", {"application_visible": True})
    assert "application_visible" in str(exc.value)


def test_set_field_rejects_format_key(service):
    """`format` belongs to the application surface, not the definition surface."""
    with pytest.raises(ConfigFieldsCrudError):
        service.set_field(_TENANT, "email", {"format": {"checker": "EMAIL"}})


def test_set_field_application_rejects_definition_keys(service):
    """set_field_application cannot reach a field DEFINITION attribute (D3(A) barrier)."""
    with pytest.raises(ConfigFieldsCrudError) as exc:
        service.set_field_application(_TENANT, "gender", {"label": {"en": "Gender"}})
    assert "label" in str(exc.value)


def test_set_field_application_rejects_definition_required_not_application_required(service):
    """The bare `required` (definition) is rejected even though `application_required` is allowed."""
    with pytest.raises(ConfigFieldsCrudError):
        service.set_field_application(_TENANT, "gender", {"required": True})


def test_empty_attrs_payload_rejected(service):
    """An empty attrs payload is a caller error, never a silent no-op write."""
    with pytest.raises(ConfigFieldsCrudError):
        service.set_field(_TENANT, "gender", {})


# ---------------------------------------------------------------------------
# ABSENT vs NULL semantics + op contract shape
# ---------------------------------------------------------------------------


def test_set_field_update_existing_entry_emits_per_aspect_set(repo):
    """When the override entry EXISTS (UPDATE verb) a present value → one per-aspect SET op; attrs
    the payload OMITS yield no op (untouched). (task 2.3 create-vs-update by existence.)"""
    svc = _existing_service(repo, ("fixed_overrides", "membership.status"))
    svc.set_field(_TENANT, "status", {"order": 20})
    ops = repo.last["ops"]
    assert ops == [
        {"action": SET, "path": ["overrides", "membership.status", "order"], "value": 20}
    ]


def test_set_field_update_existing_entry_explicit_null_emits_scoped_remove(repo):
    """UPDATE verb + an explicit None → a scoped REMOVE of just that aspect (clear-vs-unchanged)."""
    svc = _existing_service(repo, ("fixed_overrides", "membership.status"))
    svc.set_field(_TENANT, "status", {"label": None})
    ops = repo.last["ops"]
    assert ops == [{"action": REMOVE, "path": ["overrides", "membership.status", "label"]}]


def test_set_field_update_existing_entry_mixed_set_and_null(repo):
    """UPDATE verb + a mixed payload emits one op per PRESENT attr: SET for a value, REMOVE for a
    null; an omitted attr is untouched."""
    svc = _existing_service(repo, ("fixed_overrides", "membership.status"))
    svc.set_field(_TENANT, "status", {"order": 30, "visible": None})
    ops = repo.last["ops"]
    assert {"action": SET, "path": ["overrides", "membership.status", "order"], "value": 30} in ops
    assert {"action": REMOVE, "path": ["overrides", "membership.status", "visible"]} in ops
    assert len(ops) == 2


# ---------------------------------------------------------------------------
# CREATE-vs-UPDATE VERB by EXISTENCE (task 2.3 — design-review Must-fix #1)
# ---------------------------------------------------------------------------


def test_set_field_create_new_entry_emits_single_whole_entry_set(repo):
    """When the entry does NOT exist (CREATE verb) the service seeds the WHOLE entry with a SINGLE
    ``SET <map>.<key> = :whole`` — NEVER ``SET <map>.<key>.<attr>`` on an absent parent (which
    DynamoDB rejects) and NEVER ``if_not_exists`` parent-seed + child-set in one expression."""
    svc = _existing_service(repo)  # row present + versioned, but the override entry is absent
    svc.set_field(_TENANT, "status", {"order": 20, "visible": True})
    ops = repo.last["ops"]
    assert ops == [
        {
            "action": SET,
            "path": ["overrides", "membership.status"],
            "value": {"order": 20, "visible": True},
        }
    ]


def test_set_field_create_drops_null_from_seeded_entry(repo):
    """On a CREATE there is nothing to clear, so an explicit None is simply absent from the seeded
    whole-entry map (absent = not-authored), and real values are kept."""
    svc = _existing_service(repo)
    svc.set_field(_TENANT, "status", {"order": 5, "label": None})
    ops = repo.last["ops"]
    assert ops == [
        {"action": SET, "path": ["overrides", "membership.status"], "value": {"order": 5}}
    ]


def test_no_reader_defaults_to_create_verb(service, repo):
    """With no reader wired (existence unobservable) placement defaults to CREATE — the correct
    verb for a first write onto the C6 skeleton."""
    service.set_field(_TENANT, "status", {"order": 1})
    ops = repo.last["ops"]
    assert ops == [
        {"action": SET, "path": ["overrides", "membership.status"], "value": {"order": 1}}
    ]
    assert repo.last["base_version"] is None


def test_apply_ops_called_with_fields_config_id_and_null_base_version(service, repo):
    """The service targets config_id='fields' and (stub) base_version None for a first write."""
    service.set_field(_TENANT, "status", {"order": 10})
    call = repo.last
    assert call["tenant_id"] == _TENANT
    assert call["config_id"] == "fields"
    assert call["base_version"] is None


def test_client_op_id_threaded_through(service, repo):
    """An optional client_op_id is passed verbatim to apply_ops (idempotency hook)."""
    service.set_field(_TENANT, "status", {"order": 10}, client_op_id="op-123")
    assert repo.last["client_op_id"] == "op-123"


# ---------------------------------------------------------------------------
# APPLICATION op — placement + shape
# ---------------------------------------------------------------------------


def test_set_field_application_update_existing_emits_app_attr_ops(repo):
    """set_field_application (UPDATE verb) writes the four app attrs under the resolved entry path
    only, one per-aspect op each."""
    svc = _existing_service(repo, ("fixed_overrides", "personal.gender"))
    svc.set_field_application(
        _TENANT, "gender", {"application_visible": True, "application_required": False}
    )
    ops = repo.last["ops"]
    paths = {tuple(op["path"]): op for op in ops}
    assert ("overrides", "personal.gender", "application_visible") in paths
    assert ("overrides", "personal.gender", "application_required") in paths
    assert paths[("overrides", "personal.gender", "application_visible")]["value"] is True
    # application_required=False is a real value (not null) → a SET, not a REMOVE.
    assert paths[("overrides", "personal.gender", "application_required")]["action"] == SET


# ---------------------------------------------------------------------------
# IDENTITY PLACEMENT — variable vs base vs group
# ---------------------------------------------------------------------------


def test_variable_field_places_under_fields_map(service, repo):
    """A key unknown to the registry (a tenant variable field) places under fields.<key>."""
    service.set_field(_TENANT, "shirt_size", {"label": {"en": "Shirt size"}})
    op = repo.last["ops"][0]
    assert op["path"][0] == "fields"
    assert op["path"][1] == "shirt_size"


def test_base_field_places_under_overrides_dotted(service, repo):
    """A base field (registry) places under overrides.<dotted>, bare key resolved to dotted."""
    service.set_field(_TENANT, "gender", {"order": 5})
    op = repo.last["ops"][0]
    assert op["path"][0] == "overrides"
    assert op["path"][1] == "personal.gender"


def test_already_dotted_base_key_accepted(service, repo):
    """An already-dotted base key resolves without re-dotting."""
    service.set_field(_TENANT, "membership.status", {"order": 5})
    op = repo.last["ops"][0]
    assert op["path"][1] == "membership.status"


def test_set_group_places_under_functional_groups(service, repo):
    """A group op addresses functional_groups.<gkey> only (catalog can't truncate)."""
    service.set_group(_TENANT, "personal", {"order": 1, "label": {"en": "Personal"}})
    ops = repo.last["ops"]
    for op in ops:
        assert op["path"][0] == "functional_groups"
        assert op["path"][1] == "personal"


def test_set_group_rejects_non_group_attr(service):
    """set_group only writes {label, order}."""
    with pytest.raises(ConfigFieldsCrudError):
        service.set_group(_TENANT, "personal", {"type": "string"})


# ---------------------------------------------------------------------------
# RESET / DELETE — whole-entry REMOVE
# ---------------------------------------------------------------------------


def test_reset_field_removes_whole_override_entry(service, repo):
    """reset_field reverts a base field to base by removing the whole override entry."""
    service.reset_field(_TENANT, "gender")
    ops = repo.last["ops"]
    assert ops == [{"action": REMOVE, "path": ["overrides", "personal.gender"]}]


def test_delete_field_removes_whole_variable_entry(service, repo):
    """delete_field removes a whole variable-field entry under fields.<key>."""
    service.delete_field(_TENANT, "shirt_size")
    ops = repo.last["ops"]
    assert ops == [{"action": REMOVE, "path": ["fields", "shirt_size"]}]


def test_delete_field_refuses_base_field(service):
    """delete_field refuses a base field — use reset_field to drop its override (R2.5)."""
    with pytest.raises(ConfigFieldsCrudError) as exc:
        service.delete_field(_TENANT, "gender")
    assert "reset_field" in str(exc.value)


# ---------------------------------------------------------------------------
# remove_legacy_choices — the C7 backfill's legacy-cleanup companion (03a C2↔C7)
# ---------------------------------------------------------------------------
#
# C2 retired `choices` from FIELD_DEFINITION_ATTRS, so `set_field` rejects any payload
# mentioning `choices` (even `choices: None`) before it could become a scoped REMOVE. The
# migration therefore needs a dedicated, narrow op to retire the legacy attribute — modelled on
# reset_field/delete_field (derive a placement, emit a scoped REMOVE directly, bypassing the
# attr-surface guard). It emits a SINGLE scoped `REMOVE <map>.<key>.choices` (never a whole-row
# put_item) and is a safe no-op when the field carries no `choices`.


def _reader_row_with(container_key, entry_key, spec):
    """A FakeReader row whose stored entry carries the given spec (so a test can observe a
    `choices` attribute on the snapshot the service reads for placement)."""
    row = {"fields": {}, "fixed_overrides": {}, "functional_groups": {}, "version": "v-1"}
    row[container_key][entry_key] = dict(spec)
    return FakeReader(row)


def test_remove_legacy_choices_emits_scoped_remove_on_choices_path(repo):
    """remove_legacy_choices emits a SINGLE scoped REMOVE on the field's `choices` path — modelled
    on reset_field, bypassing the attr-surface guard (which now forbids `choices`)."""
    reader = _reader_row_with(
        "fixed_overrides", "personal.gender", {"type": "enum", "choices": ["man", "vrouw"]}
    )
    svc = ConfigFieldsCrudService(repo, reader=reader)

    svc.remove_legacy_choices(_TENANT, "gender")

    ops = repo.last["ops"]
    assert ops == [{"action": REMOVE, "path": ["overrides", "personal.gender", "choices"]}]
    # It targets config#fields via the Change-Op path (not a whole-row replace).
    assert repo.last["config_id"] == "fields"


def test_remove_legacy_choices_on_variable_field_targets_fields_map(repo):
    """For a tenant VARIABLE field the scoped REMOVE addresses fields.<key>.choices."""
    reader = _reader_row_with(
        "fields", "referral_source", {"type": "enum", "choices": ["internet", "facebook"]}
    )
    svc = ConfigFieldsCrudService(repo, reader=reader)

    svc.remove_legacy_choices(_TENANT, "referral_source")

    assert repo.last["ops"] == [
        {"action": REMOVE, "path": ["fields", "referral_source", "choices"]}
    ]


def test_remove_legacy_choices_is_noop_when_no_choices_attribute(repo):
    """When the stored entry carries NO `choices` (already migrated / never legacy) nothing is
    written — apply_ops is never called with an empty op set (it requires a non-empty sequence)."""
    reader = _reader_row_with(
        "fixed_overrides",
        "personal.gender",
        {"type": "enum", "options": [{"value": "man"}]},
    )
    svc = ConfigFieldsCrudService(repo, reader=reader)

    result = svc.remove_legacy_choices(_TENANT, "gender")

    assert result.get("no_op") is True
    assert repo.calls == [], "a no-op must not reach apply_ops (never a whole-row replace either)"


def test_remove_legacy_choices_is_noop_when_field_entry_absent(repo):
    """A field with no stored entry at all carries no `choices` → safe no-op, no write."""
    svc = ConfigFieldsCrudService(repo, reader=FakeReader({}))

    result = svc.remove_legacy_choices(_TENANT, "gender")

    assert result.get("no_op") is True
    assert repo.calls == []


# ---------------------------------------------------------------------------
# remove_inline_options — the C7 companion for SCOPE-BACKED (W2) / REFERENCE (W1) fields
# ---------------------------------------------------------------------------
#
# A scope-backed / reference field sources its vocabulary from the config#scope dimension / the
# live catalog, NEVER inline. `set_field` REJECTS an inline `options` payload on such a field
# (W1/W2), so — exactly like `remove_legacy_choices` for the retired `choices` — the migration
# needs a dedicated narrow op to DROP a stale inline `options`. It emits a SINGLE scoped
# `REMOVE <map>.<key>.options` (never a whole-row put_item) and is a safe no-op when the field
# carries no inline `options`.


def test_remove_inline_options_emits_scoped_remove_on_options_path(repo):
    """remove_inline_options emits a SINGLE scoped REMOVE on the field's `options` path — modelled
    on remove_legacy_choices, bypassing the W1/W2 source-integrity guard."""
    reader = _reader_row_with(
        "fields",
        "region",
        {"scope": {"enabled": True}, "options": [{"value": "stale"}]},
    )
    svc = ConfigFieldsCrudService(repo, reader=reader)

    svc.remove_inline_options(_TENANT, "region")

    ops = repo.last["ops"]
    assert ops == [{"action": REMOVE, "path": ["fields", "region", "options"]}]
    # It targets config#fields via the Change-Op path (not a whole-row replace).
    assert repo.last["config_id"] == "fields"


def test_remove_inline_options_on_override_targets_overrides_map(repo):
    """For a base/calculated override the scoped REMOVE addresses overrides.<dotted>.options."""
    reader = _reader_row_with(
        "fixed_overrides",
        "personal.gender",
        {"scope": {"enabled": True}, "options": [{"value": "stale"}]},
    )
    svc = ConfigFieldsCrudService(repo, reader=reader)

    svc.remove_inline_options(_TENANT, "gender")

    assert repo.last["ops"] == [
        {"action": REMOVE, "path": ["overrides", "personal.gender", "options"]}
    ]


def test_remove_inline_options_is_noop_when_no_options_attribute(repo):
    """When the stored entry carries NO inline `options` nothing is written — apply_ops is never
    called with an empty op set."""
    reader = _reader_row_with(
        "fields",
        "region",
        {"scope": {"enabled": True}},
    )
    svc = ConfigFieldsCrudService(repo, reader=reader)

    result = svc.remove_inline_options(_TENANT, "region")

    assert result.get("no_op") is True
    assert repo.calls == [], "a no-op must not reach apply_ops (never a whole-row replace either)"


def test_remove_inline_options_is_noop_when_field_entry_absent(repo):
    """A field with no stored entry at all carries no inline `options` → safe no-op, no write."""
    svc = ConfigFieldsCrudService(repo, reader=FakeReader({}))

    result = svc.remove_inline_options(_TENANT, "region")

    assert result.get("no_op") is True
    assert repo.calls == []


def test_delete_group_removes_whole_group_entry(service, repo):
    """delete_group removes the whole functional_groups.<gkey> entry."""
    service.delete_group(_TENANT, "custom_group")
    ops = repo.last["ops"]
    assert ops == [{"action": REMOVE, "path": ["functional_groups", "custom_group"]}]


# ---------------------------------------------------------------------------
# base_version seam — reader-backed resolution (task 2.3/2.4 wiring point)
# ---------------------------------------------------------------------------


def test_base_version_from_existing_versioned_row(repo):
    """With a reader, an existing versioned row yields its version as the optimistic-lock base."""
    reader = FakeReader({"fields": {}, "version": "v-7"})
    svc = ConfigFieldsCrudService(repo, reader=reader)
    svc.set_field(_TENANT, "status", {"order": 1})
    assert repo.last["base_version"] == "v-7"


def test_base_version_legacy_row_without_version(repo):
    """An existing row with NO version resolves to the LEGACY sentinel."""
    from sam.members.repository.projection_config_write_repository import LEGACY_NO_VERSION

    reader = FakeReader({"fields": {"shirt_size": {}}})
    svc = ConfigFieldsCrudService(repo, reader=reader)
    svc.set_field(_TENANT, "shirt_size", {"order": 1})
    assert repo.last["base_version"] == LEGACY_NO_VERSION


def test_base_version_no_row_is_none(repo):
    """No stored row → base_version None (first write onto the skeleton)."""
    reader = FakeReader(None)
    svc = ConfigFieldsCrudService(repo, reader=reader)
    svc.set_field(_TENANT, "status", {"order": 1})
    assert repo.last["base_version"] is None


def test_base_version_never_authored_tenant_is_none(repo):
    """A never-authored tenant — NO ``config#fields`` row at all — resolves base_version None
    (first write onto the skeleton, case iii).

    With the SEPARATE control-plane version read (get_config_fields_version → ``(present, ...)``)
    the service can now tell "no row" apart from "existing legacy versionless row" PRECISELY — it
    no longer has to infer it from an all-empty wire overlay. A truly absent row reports
    ``present=False`` → base_version None."""
    reader = FakeReader(None)
    svc = ConfigFieldsCrudService(repo, reader=reader)
    svc.set_field(_TENANT, "status", {"order": 1})
    assert repo.last["base_version"] is None


def test_base_version_existing_versionless_skeleton_row_is_legacy(repo):
    """An EXISTING row with empty containers and NO version (a legacy skeleton the migration has
    not version-backfilled) resolves to LEGACY_NO_VERSION (case ii), NOT None.

    This is the sharper classification the control-plane read enables: the row physically EXISTS
    (``present=True``) but carries no ``version``, so the first versioned write must use the
    ``attribute_not_exists(version)`` branch — not ``attribute_not_exists(sk)`` (which would fail
    against a row that already exists). The old all-empty-overlay heuristic could not distinguish
    this from a missing row; the dedicated version read can."""
    from sam.members.repository.projection_config_write_repository import LEGACY_NO_VERSION

    reader = FakeReader({"fields": {}, "fixed_overrides": {}, "functional_groups": {}})
    svc = ConfigFieldsCrudService(repo, reader=reader)
    svc.set_field(_TENANT, "status", {"order": 1})
    assert repo.last["base_version"] == LEGACY_NO_VERSION


# ---------------------------------------------------------------------------
# TASK 2.3 mechanics — ConsistentRead flows; dotted segments; legacy fallback;
# group materialize verb
# ---------------------------------------------------------------------------


def test_placement_read_requests_consistent_read(repo):
    """The validate-and-place read is STRONGLY-CONSISTENT: the service passes consistent_read=True
    to the reader (design C1 step 1 / design-review Should-fix — avoids a spurious 409)."""
    reader = FakeReader({"fields": {}, "fixed_overrides": {}, "functional_groups": {}})
    svc = ConfigFieldsCrudService(repo, reader=reader)
    svc.set_field(_TENANT, "status", {"order": 1})
    assert reader.consistent_read_calls, "the reader was never consulted"
    assert all(reader.consistent_read_calls), (
        "every placement read must request ConsistentRead=True, got "
        f"{reader.consistent_read_calls!r}"
    )


def test_one_consistent_read_per_op(repo):
    """Placement + base-version share ONE strongly-consistent snapshot per op (one read, not two)."""
    reader = FakeReader({"fields": {}, "fixed_overrides": {}, "functional_groups": {}})
    svc = ConfigFieldsCrudService(repo, reader=reader)
    svc.set_field(_TENANT, "status", {"order": 1})
    assert len(reader.consistent_read_calls) == 1


def test_dotted_override_key_is_a_single_literal_segment(repo):
    """A base/calculated field's override key is handed on as ONE dotted LITERAL segment
    (``personal.gender``), not split into nested path segments — the repository binds it through
    ExpressionAttributeNames so the '.' is a key name, not a document path (design-review Q2)."""
    reader = FakeReader(
        {"fields": {}, "fixed_overrides": {"personal.gender": {}}, "functional_groups": {}, "version": "v-2"}
    )
    svc = ConfigFieldsCrudService(repo, reader=reader)
    svc.set_field(_TENANT, "gender", {"order": 5})
    op = repo.last["ops"][0]
    # UPDATE verb (entry exists) → aspect path [map, dotted-key, attr]; the dotted key is intact.
    assert op["path"] == ["overrides", "personal.gender", "order"]
    assert "." in op["path"][1] and op["path"][1].count(".") == 1


def test_create_override_uses_dotted_key_as_whole_entry_path(repo):
    """On a CREATE of a base-field override the whole-entry SET addresses ``overrides.<dotted>`` —
    still ONE literal dotted segment, seeded as a whole map."""
    reader = FakeReader({"fields": {}, "fixed_overrides": {}, "functional_groups": {}, "version": "v-2"})
    svc = ConfigFieldsCrudService(repo, reader=reader)
    svc.set_field(_TENANT, "gender", {"order": 5})
    op = repo.last["ops"][0]
    assert op == {
        "action": SET,
        "path": ["overrides", "personal.gender"],
        "value": {"order": 5},
    }


def test_legacy_reader_without_consistent_read_kwarg_degrades(repo):
    """A reader whose get_raw_fields_overlay predates the consistent_read kwarg does not crash the
    op — the service falls back to the default read (the flag is a strengthening, not a hard
    precondition)."""
    reader = LegacyFakeReader(
        {"fields": {}, "fixed_overrides": {"membership.status": {}}, "functional_groups": {}, "version": "v-9"}
    )
    svc = ConfigFieldsCrudService(repo, reader=reader)
    svc.set_field(_TENANT, "status", {"order": 3})
    assert reader.plain_calls == 1
    # Existence still observed via the fallback read → UPDATE verb + optimistic-lock base version.
    assert repo.last["ops"] == [
        {"action": SET, "path": ["overrides", "membership.status", "order"], "value": 3}
    ]
    assert repo.last["base_version"] == "v-9"


def test_set_group_materialize_absent_base_group_creates_whole_entry(repo):
    """set_group on a group ABSENT from the overlay materializes it: a single whole-entry
    ``SET functional_groups.<gkey> = :g`` (R4.1) — the base-group materialize, catalog untouched."""
    reader = FakeReader({"fields": {}, "fixed_overrides": {}, "functional_groups": {}, "version": "v-3"})
    svc = ConfigFieldsCrudService(repo, reader=reader)
    svc.set_group(_TENANT, "personal", {"order": 1, "label": {"en": "Personal"}})
    ops = repo.last["ops"]
    assert ops == [
        {
            "action": SET,
            "path": ["functional_groups", "personal"],
            "value": {"order": 1, "label": {"en": "Personal"}},
        }
    ]


def test_set_group_update_existing_group_emits_per_aspect(repo):
    """set_group on an EXISTING group updates the named aspect only (UPDATE verb)."""
    reader = FakeReader(
        {"fields": {}, "fixed_overrides": {}, "functional_groups": {"personal": {}}, "version": "v-3"}
    )
    svc = ConfigFieldsCrudService(repo, reader=reader)
    svc.set_group(_TENANT, "personal", {"order": 2})
    ops = repo.last["ops"]
    assert ops == [
        {"action": SET, "path": ["functional_groups", "personal", "order"], "value": 2}
    ]


# ===========================================================================
# TASK 2.6 — server-owned placement + delete-safety guards
# (design C1; requirements R2.2 / R2.5 / R4.3; design-review Should-fix)
# ===========================================================================
#
# What this block asserts (the 2.6 surface — on top of the 2.2/2.3 mechanics above):
#   1. CLIENT NEVER SUPPLIES PLACEMENT (R2.2): the service decides fields vs overrides + the
#      dotted key from the registry alone; a client-supplied placement hint (a storage map /
#      dotted key / raw-shape key smuggled into the attrs payload) is REJECTED, never honoured.
#   2. DELETE IS EXPLICIT-ONLY (R2.5): a delete only ever happens via delete_field / delete_group;
#      it is never inferred from an omitted / null attr in a set op.
#   3. DELETE-NON-EMPTY-GROUP REFUSED (R4.3): delete_group on a group that still holds an authored
#      field raises a caller-safe ConfigFieldsCrudError (no REMOVE op emitted).
#   4. DELETE_FIELD-IN-USE REFUSED (review Should-fix): delete_field on a variable field that has
#      member data OR a dangling reference raises a caller-safe error that offers hide
#      (visible=false); a field that is NOT in use deletes cleanly.
#   5. BASE-FIELD DELETE STILL REFUSED (Q9): delete_field refuses a base field (use reset_field) —
#      2.2's guard is preserved.
#
# The in-memory fakes simulate "group has fields" (seed the snapshot's fields/fixed_overrides with
# a spec carrying functional_group=<group>) and "field has member data / a reference" (a
# FakeUsageProbe the service consults through its injected usage_probe seam). No boto3, no
# DynamoDB — pure domain (steering 35/39).
#
# **Validates: Requirements 2.2, 2.5, 4.3**


class FakeUsageProbe:
    """In-memory member-data / reference usage probe for the delete_field safety guard.

    Exposes the rich ``field_usage(tenant_id, field_key)`` shape the service prefers: a mapping
    with ``member_data`` (bool — a member record stores a value under the key) and ``references``
    (an iterable of human-readable reference names, or falsey). Records every lookup so a test can
    assert the guard actually consulted the probe.
    """

    def __init__(self, usage_by_key=None):
        self._usage = dict(usage_by_key or {})
        self.calls: list[tuple[str, str]] = []

    def field_usage(self, tenant_id, field_key):
        self.calls.append((tenant_id, field_key))
        return self._usage.get(field_key, {"member_data": False, "references": ()})


class BooleanUsageProbe:
    """A simpler probe exposing only the boolean ``field_in_use`` shape (member-data only).

    Proves the service accepts the minimal probe contract too (normalised to member_data)."""

    def __init__(self, in_use_keys=()):
        self._in_use = set(in_use_keys)
        self.calls: list[tuple[str, str]] = []

    def field_in_use(self, tenant_id, field_key):
        self.calls.append((tenant_id, field_key))
        return field_key in self._in_use


def _service_with_snapshot(repo, *, fields=None, overrides=None, groups=None, usage_probe=None):
    """A service whose reader serves a snapshot with the given authored overlay containers.

    ``fields`` / ``overrides`` / ``groups`` are maps of entry-key -> spec (the spec may carry a
    ``functional_group`` aspect so the delete-group guard can see a field holding the group). The
    ``overrides`` map is served under the wire key ``fixed_overrides`` (the reader's one-key
    contract), matching how the real reader serves it.
    """
    row = {
        "fields": dict(fields or {}),
        "fixed_overrides": dict(overrides or {}),
        "functional_groups": dict(groups or {}),
        "version": "v-1",
    }
    return ConfigFieldsCrudService(repo, reader=FakeReader(row), usage_probe=usage_probe)


# ---------------------------------------------------------------------------
# 1 — CLIENT NEVER SUPPLIES PLACEMENT (R2.2)
# ---------------------------------------------------------------------------


def test_client_cannot_supply_storage_placement_via_attrs(service):
    """A client-supplied placement hint smuggled into the attrs payload (a storage map name / a
    dotted key / a raw-shape key) is REJECTED — it is outside the definition surface, so the
    service never honours a caller-chosen storage path (R2.2 / steering 39)."""
    for smuggled in ("overrides", "fields", "functional_groups", "fixed_overrides", "field_overlay"):
        with pytest.raises(ConfigFieldsCrudError):
            service.set_field(_TENANT, "shirt_size", {"label": {"en": "X"}, smuggled: {"a": 1}})


def test_placement_is_decided_by_registry_not_by_caller(repo):
    """The SAME bare identity always lands where the REGISTRY dictates, regardless of caller — a
    base field → overrides.<dotted>, a variable field → fields.<key>. The caller supplies only the
    identity + attrs; the storage map/key is server-owned."""
    svc = ConfigFieldsCrudService(repo)
    svc.set_field(_TENANT, "gender", {"order": 1})  # base field (registry)
    assert repo.last["ops"][0]["path"][:2] == ["overrides", "personal.gender"]
    svc.set_field(_TENANT, "shirt_size", {"order": 1})  # unknown → variable
    assert repo.last["ops"][0]["path"][:2] == ["fields", "shirt_size"]


def test_no_op_carries_a_client_chosen_storage_path(service, repo):
    """Every emitted op's path is built by the service from [map, key, (attr)] — the attrs payload
    never appears as a path segment, so a caller cannot inject a storage path."""
    service.set_field(_TENANT, "shirt_size", {"label": {"en": "Shirt"}, "order": 3})
    for op in repo.last["ops"]:
        assert op["path"][0] in ("fields", "overrides", "functional_groups")


# ---------------------------------------------------------------------------
# 2 — DELETE IS EXPLICIT-ONLY (R2.5)
# ---------------------------------------------------------------------------


def test_set_field_null_attr_does_not_delete_the_field(repo):
    """An explicit None in a set op REMOVEs only that ASPECT — it never removes the whole field
    entry (a delete is only ever the explicit delete_field op, R2.5)."""
    svc = _existing_service(repo, ("fields", "shirt_size"))
    svc.set_field(_TENANT, "shirt_size", {"label": None})
    ops = repo.last["ops"]
    # a scoped aspect REMOVE, NOT a whole-entry REMOVE
    assert ops == [{"action": REMOVE, "path": ["fields", "shirt_size", "label"]}]
    assert ops[0]["path"] != ["fields", "shirt_size"]


def test_omitting_a_field_from_a_set_op_never_removes_it(repo):
    """Omission is NOT a signal to delete: a set op touching one field emits ops only for that
    field; other authored fields are never addressed, so nothing else is removed (R2.5)."""
    svc = _service_with_snapshot(
        repo,
        fields={"shirt_size": {"functional_group": "merch"}, "dietary": {"functional_group": "merch"}},
    )
    svc.set_field(_TENANT, "shirt_size", {"order": 2})
    for op in repo.last["ops"]:
        assert op["path"][1] == "shirt_size"  # only the named field is addressed


def test_delete_field_is_the_only_whole_entry_field_removal(repo):
    """The whole-entry field REMOVE is reachable ONLY through the explicit delete_field op."""
    svc = _service_with_snapshot(repo, fields={"shirt_size": {}})
    svc.delete_field(_TENANT, "shirt_size")
    assert repo.last["ops"] == [{"action": REMOVE, "path": ["fields", "shirt_size"]}]


# ---------------------------------------------------------------------------
# 3 — DELETE-NON-EMPTY-GROUP REFUSED (R4.3)
# ---------------------------------------------------------------------------


def test_delete_group_refused_when_it_still_holds_a_variable_field(repo):
    """delete_group refuses a group still holding an authored VARIABLE field (R4.3) — no op."""
    svc = _service_with_snapshot(
        repo,
        fields={"shirt_size": {"functional_group": "merch"}},
        groups={"merch": {"label": {"en": "Merch"}}},
    )
    with pytest.raises(ConfigFieldsCrudError) as exc:
        svc.delete_group(_TENANT, "merch")
    assert "shirt_size" in str(exc.value)
    assert not repo.calls, "a refused delete must NOT emit a REMOVE op"


def test_delete_group_refused_when_it_still_holds_an_override_field(repo):
    """A base-field override reassigned into the group also blocks the group delete (R4.3)."""
    svc = _service_with_snapshot(
        repo,
        overrides={"personal.gender": {"functional_group": "merch"}},
        groups={"merch": {}},
    )
    with pytest.raises(ConfigFieldsCrudError) as exc:
        svc.delete_group(_TENANT, "merch")
    assert "personal.gender" in str(exc.value)
    assert not repo.calls


def test_delete_group_allowed_when_empty(repo):
    """An empty group (no authored field references it) deletes cleanly — one whole-entry REMOVE."""
    svc = _service_with_snapshot(
        repo,
        fields={"shirt_size": {"functional_group": "other_group"}},
        groups={"merch": {}, "other_group": {}},
    )
    svc.delete_group(_TENANT, "merch")
    assert repo.last["ops"] == [{"action": REMOVE, "path": ["functional_groups", "merch"]}]


# ---------------------------------------------------------------------------
# 4 — DELETE_FIELD-IN-USE REFUSED (review Should-fix) — offer hide
# ---------------------------------------------------------------------------


def test_delete_field_refused_when_member_data_exists(repo):
    """delete_field refuses a variable field with member data and offers hide (visible=false)."""
    probe = FakeUsageProbe({"shirt_size": {"member_data": True, "references": ()}})
    svc = _service_with_snapshot(repo, fields={"shirt_size": {}}, usage_probe=probe)
    with pytest.raises(ConfigFieldsCrudError) as exc:
        svc.delete_field(_TENANT, "shirt_size")
    msg = str(exc.value)
    assert "visible=false" in msg and "member" in msg.lower()
    assert ("crud-tenant", "shirt_size") in probe.calls
    assert not repo.calls, "a refused delete must NOT emit a REMOVE op"


def test_delete_field_refused_when_a_reference_dangles(repo):
    """A dangling group/application reference blocks the delete and is named in the reason."""
    probe = FakeUsageProbe(
        {"shirt_size": {"member_data": False, "references": ["application form"]}}
    )
    svc = _service_with_snapshot(repo, fields={"shirt_size": {}}, usage_probe=probe)
    with pytest.raises(ConfigFieldsCrudError) as exc:
        svc.delete_field(_TENANT, "shirt_size")
    assert "application form" in str(exc.value)
    assert not repo.calls


def test_delete_field_allowed_when_not_in_use(repo):
    """A variable field with no member data and no reference deletes cleanly."""
    probe = FakeUsageProbe({"shirt_size": {"member_data": False, "references": ()}})
    svc = _service_with_snapshot(repo, fields={"shirt_size": {}}, usage_probe=probe)
    svc.delete_field(_TENANT, "shirt_size")
    assert repo.last["ops"] == [{"action": REMOVE, "path": ["fields", "shirt_size"]}]


def test_delete_field_accepts_boolean_usage_probe(repo):
    """The minimal boolean field_in_use probe contract is honoured (normalised to member_data)."""
    probe = BooleanUsageProbe(in_use_keys={"shirt_size"})
    svc = _service_with_snapshot(repo, fields={"shirt_size": {}}, usage_probe=probe)
    with pytest.raises(ConfigFieldsCrudError):
        svc.delete_field(_TENANT, "shirt_size")
    assert not repo.calls


def test_delete_field_without_a_probe_does_not_block_on_member_data(repo):
    """With no usage_probe wired the member-data leg is unobservable and does not block — the
    delete proceeds (production always wires a probe; this keeps the 2.2 surface exercisable)."""
    svc = _service_with_snapshot(repo, fields={"shirt_size": {}})  # no usage_probe
    svc.delete_field(_TENANT, "shirt_size")
    assert repo.last["ops"] == [{"action": REMOVE, "path": ["fields", "shirt_size"]}]


# ---------------------------------------------------------------------------
# 5 — BASE-FIELD DELETE STILL REFUSED (Q9) — 2.2's guard preserved
# ---------------------------------------------------------------------------


def test_delete_field_still_refuses_a_base_field(repo):
    """A base field is never deletable — use reset_field to drop its override (Q9 / R2.5). The
    usage guard never even runs (the base-field refusal fires first), so no probe is needed."""
    probe = FakeUsageProbe()
    svc = _service_with_snapshot(repo, usage_probe=probe)
    with pytest.raises(ConfigFieldsCrudError) as exc:
        svc.delete_field(_TENANT, "gender")
    assert "reset_field" in str(exc.value)
    assert not repo.calls
    assert not probe.calls, "the base-field refusal must precede the usage probe"


# ===========================================================================
# TASK 2.5 — base-group MATERIALIZE (R4.1) + the structural
# "catalog cannot truncate" property (R4.2) — fixes root-cause occurrences 2 + 3
# (design C1/D2; requirements R4.1/R4.2; root-cause-analysis occurrences 2 & 3)
# ===========================================================================
#
# What this block PROVES (the behaviour already lands via tasks 2.3 + 2.4 — the service's
# create-vs-update verb and the repository's single-path ``update_item``; this task adds the
# explicit proof it asked for):
#
#   1. BASE-GROUP MATERIALIZE (R4.1 — fixes occurrence 2 "base-group edit no-op / blank form"):
#      ``set_group`` on a base group that is ABSENT from the overlay emits exactly ONE
#      ``SET functional_groups.<gkey> = :g`` (a whole override entry seeding the edit), and when
#      that op is applied through the REAL repository ``apply_ops`` over a seeded catalog EVERY
#      OTHER group is byte-identical afterwards.
#
#      Note on "resolved base values + the edit" (design D4 — minimal-delta authoring): materialize
#      SETs ONLY the edited aspects under ``functional_groups.<gkey>``, NOT a full resolved copy of
#      the base group. That is deliberate — the stored row stays a true tenant delta; the resolver
#      composes base ⊕ overlay on read, so the base group's un-edited attributes (its code-defined
#      label/order) still surface. A full-resolved-copy materialize would re-introduce the "fat
#      stored entry" the root cause flagged. So the proof below asserts the EDIT is materialised and
#      the SIBLINGS survive — it does NOT (correctly) assert a resolved base copy was written.
#
#   2. CATALOG CANNOT TRUNCATE — STRUCTURAL (R4.2 — fixes occurrence 3 "functional_groups truncated
#      6→2"): NO group op ever addresses the WHOLE ``functional_groups`` map. Every group op's path
#      is ``["functional_groups", <gkey>, ...]`` (length ≥ 2) — never the bare
#      ``["functional_groups"]``. Because an ``update_item`` only writes the attributes a path names,
#      a partial/empty groups payload is PHYSICALLY unable to shrink the catalog. This is the exact
#      occurrence-3 scenario, now impossible by construction, not by a flawless merge.
#
#   3. OTHER-GROUPS-UNTOUCHED INVARIANT (R1.2/R4.2): editing one existing group, materialising an
#      absent base group, and deleting an empty group each leave every OTHER group byte-identical
#      when applied end-to-end (service → real ``apply_ops`` → condition-evaluating fake table).
#
# The proof runs END-TO-END: the real ``ConfigFieldsCrudService`` emits the ops and the real
# ``MembersConfigWriteRepository.apply_ops`` applies them to a ``_CatalogFakeTable`` that EVALUATES
# the built SET/REMOVE UpdateExpression + the version condition (mirrors the sibling
# ``ConditionalFakeTable`` in ``test_config_write_repository_apply_ops.py``), so the "other groups
# survive" claim is tested against the real expression, not a stub that ignores it.
#
# **Validates: Requirements 1.2, 4.1, 4.2**

import copy
import re

from botocore.exceptions import ClientError

from services import projection_schema as schema

from sam.members.repository.projection_config_write_repository import (
    MembersConfigWriteRepository,
    StaleVersionError,
)

_FIELDS_SK = "config#fields"


def _conditional_check_failed() -> ClientError:
    """A genuine botocore ``ClientError`` with the ConditionalCheckFailedException code."""
    return ClientError(
        {"Error": {"Code": "ConditionalCheckFailedException", "Message": "conditional request failed"}},
        "UpdateItem",
    )


class _CatalogFakeTable:
    """Condition-evaluating in-memory DynamoDB ``Table`` fake (self-contained copy of the sibling
    ``ConditionalFakeTable``) that APPLIES the built SET/REMOVE UpdateExpression + honours the
    version condition — so "other groups survive" is proven against the REAL expression the
    repository builds, not a stub that ignores it."""

    def __init__(self):
        self.store: dict[tuple, dict] = {}

    def _key_tuple(self, key):
        return (key[schema.PARTITION_KEY_ATTR], key[schema.SORT_KEY_ATTR])

    def seed(self, item: dict):
        self.store[self._key_tuple(item)] = copy.deepcopy(item)

    def get_item(self, Key=None, ConsistentRead=False):
        item = self.store.get(self._key_tuple(Key))
        return {"Item": copy.deepcopy(item)} if item else {}

    def update_item(
        self,
        Key=None,
        UpdateExpression=None,
        ConditionExpression=None,
        ExpressionAttributeNames=None,
        ExpressionAttributeValues=None,
    ):
        names = ExpressionAttributeNames or {}
        values = ExpressionAttributeValues or {}
        self._base = values.get(":base")
        key_tuple = self._key_tuple(Key)
        existing = self.store.get(key_tuple)
        if not self._condition_holds(ConditionExpression, names, existing):
            raise _conditional_check_failed()
        item = copy.deepcopy(existing) if existing else dict(Key)
        self._apply_update(item, UpdateExpression, names, values)
        self.store[key_tuple] = item
        return {}

    def _condition_holds(self, condition, names, existing) -> bool:
        if condition is None:
            return True
        m = re.fullmatch(r"attribute_not_exists\((#n\d+)\)", condition)
        if m:
            segment = names[m.group(1)]
            if segment == schema.SORT_KEY_ATTR:
                return existing is None
            return existing is not None and schema.VERSION_ATTR not in existing
        m = re.fullmatch(r"(#n\d+) = :base", condition)
        if m:
            segment = names[m.group(1)]
            return existing is not None and existing.get(segment) == self._base
        raise AssertionError(f"unexpected condition: {condition!r}")

    def _resolve_path(self, dotted_placeholder: str, names) -> list[str]:
        return [names[p] for p in dotted_placeholder.split(".")]

    def _apply_update(self, item, update_expression, names, values):
        set_part, remove_part = self._split_clauses(update_expression)
        for clause in set_part:
            path_expr, _, val_ph = clause.partition(" = ")
            path = self._resolve_path(path_expr.strip(), names)
            self._set_nested(item, path, values[val_ph.strip()])
        for path_expr in remove_part:
            self._remove_nested(item, self._resolve_path(path_expr.strip(), names))

    @staticmethod
    def _split_clauses(update_expression):
        set_clauses, remove_clauses = [], []
        set_match = re.search(r"SET (.*?)(?: REMOVE |$)", update_expression)
        remove_match = re.search(r"REMOVE (.*)$", update_expression)
        if set_match and set_match.group(1).strip():
            set_clauses = [c.strip() for c in set_match.group(1).split(",")]
        if remove_match:
            remove_clauses = [c.strip() for c in remove_match.group(1).split(",")]
        return set_clauses, remove_clauses

    @staticmethod
    def _set_nested(item, path, value):
        node = item
        for seg in path[:-1]:
            node = node.setdefault(seg, {})
        node[path[-1]] = value

    @staticmethod
    def _remove_nested(item, path):
        node = item
        for seg in path[:-1]:
            node = node.get(seg, {})
        node.pop(path[-1], None)


# The occurrence-3 catalog: a SIX-group `functional_groups` map, like the real h-dcn row that was
# truncated 6→2. Mixed shapes (bilingual labels, orders) so "byte-identical" is a real assertion.
_SIX_GROUPS = {
    "personal": {"label": {"en": "Personal", "nl": "Persoonlijk"}, "order": 10},
    "contact": {"label": {"en": "Contact", "nl": "Contact"}, "order": 20},
    "membership": {"label": {"en": "Membership", "nl": "Lidmaatschap"}, "order": 30},
    "medical": {"label": {"en": "Medical", "nl": "Medisch"}, "order": 40},
    "emergency": {"label": {"en": "Emergency", "nl": "Noodgeval"}, "order": 50},
    "consent": {"label": {"en": "Consent", "nl": "Toestemming"}, "order": 60},
}


def _seed_catalog_row(table, *, groups, version="v1", fields=None, overrides=None):
    """Seed the fake table with a full `config#fields` row carrying `groups` in functional_groups."""
    table.seed(
        {
            schema.PARTITION_KEY_ATTR: _TENANT,
            schema.SORT_KEY_ATTR: _FIELDS_SK,
            schema.VERSION_ATTR: version,
            "fields": dict(fields or {}),
            "overrides": dict(overrides or {}),
            "functional_groups": copy.deepcopy(groups),
        }
    )


def _reader_over(table):
    """A FakeReader whose wire overlay mirrors the stored row (so placement sees the live groups).

    Serves the stored `overrides` map under the reader's wire key `fixed_overrides` (the one-key
    contract) + `fields` / `functional_groups` verbatim, plus the `version`, so the service's
    existence check + base-version resolution see the same row the repository will write to.
    """
    stored = table.store[(_TENANT, _FIELDS_SK)]
    return FakeReader(
        {
            "fields": copy.deepcopy(stored.get("fields", {})),
            "fixed_overrides": copy.deepcopy(stored.get("overrides", {})),
            "functional_groups": copy.deepcopy(stored.get("functional_groups", {})),
            "version": stored.get(schema.VERSION_ATTR),
        }
    )


def _e2e_service(table, version_fn):
    """A real ConfigFieldsCrudService wired to the real apply_ops repository over the fake table."""
    repo = MembersConfigWriteRepository(table=table, version_fn=version_fn)
    return ConfigFieldsCrudService(repo, reader=_reader_over(table))


def _stored_groups(table):
    return table.store[(_TENANT, _FIELDS_SK)]["functional_groups"]


# ---------------------------------------------------------------------------
# 1 — BASE-GROUP MATERIALIZE (R4.1) — absent group materialised, siblings survive
# ---------------------------------------------------------------------------


def test_materialize_absent_base_group_emits_single_whole_entry_set():
    """`set_group` on a base group ABSENT from the overlay emits exactly ONE whole-entry SET under
    `functional_groups.<gkey>` — the materialize verb (R4.1); never a partial-catalog write."""
    repo = RecordingFakeRepository()
    # Overlay has NO groups authored yet → the group is absent → CREATE/materialize verb.
    reader = FakeReader(
        {"fields": {}, "fixed_overrides": {}, "functional_groups": {}, "version": "v1"}
    )
    svc = ConfigFieldsCrudService(repo, reader=reader)
    svc.set_group(_TENANT, "medical", {"order": 45, "label": {"en": "Medical info"}})
    ops = repo.last["ops"]
    assert ops == [
        {
            "action": SET,
            "path": ["functional_groups", "medical"],
            "value": {"order": 45, "label": {"en": "Medical info"}},
        }
    ], "materialize must be ONE whole-entry SET on functional_groups.<gkey>"
    # It is an UPDATE of exactly one named group path — never the whole catalog.
    assert ops[0]["path"][:2] == ["functional_groups", "medical"]
    assert repo.last["base_version"] == "v1"


def test_materialize_absent_base_group_leaves_other_groups_byte_identical():
    """END-TO-END: materialising an ABSENT base group through the real apply_ops over a seeded
    6-group catalog adds that group and leaves ALL other groups byte-identical (R4.1 — occurrence
    2: a base-group edit must not blank the form / drop the catalog)."""
    table = _CatalogFakeTable()
    # The overlay already authors FIVE of the six groups; "medical" is a base group ABSENT from the
    # overlay — editing it must MATERIALISE it without disturbing the other five.
    authored = {k: v for k, v in _SIX_GROUPS.items() if k != "medical"}
    _seed_catalog_row(table, groups=authored, version="v1")
    before = copy.deepcopy(_stored_groups(table))

    svc = _e2e_service(table, version_fn=lambda: "v2")
    svc.set_group(_TENANT, "medical", {"order": 45, "label": {"en": "Medical info"}})

    after = _stored_groups(table)
    # The absent base group is now materialised with exactly the edited aspects (minimal delta, D4).
    assert after["medical"] == {"order": 45, "label": {"en": "Medical info"}}
    # EVERY other group is byte-identical to before — nothing else moved.
    for gkey, spec in before.items():
        assert after[gkey] == spec, f"group {gkey!r} must be untouched by the materialize"
    assert set(after) == set(before) | {"medical"}


def test_edit_existing_group_leaves_other_groups_byte_identical():
    """END-TO-END: editing ONE existing group's order updates only that group; the full 6-group
    catalog otherwise survives byte-identical (R1.2/R4.2)."""
    table = _CatalogFakeTable()
    _seed_catalog_row(table, groups=_SIX_GROUPS, version="v1")
    before = copy.deepcopy(_stored_groups(table))

    svc = _e2e_service(table, version_fn=lambda: "v2")
    svc.set_group(_TENANT, "contact", {"order": 25})

    after = _stored_groups(table)
    assert after["contact"]["order"] == 25
    # contact's label is preserved (only the named aspect changed)...
    assert after["contact"]["label"] == before["contact"]["label"]
    # ...and every OTHER group is byte-identical.
    for gkey in ("personal", "membership", "medical", "emergency", "consent"):
        assert after[gkey] == before[gkey], f"group {gkey!r} must be untouched"
    assert set(after) == set(before)


# ---------------------------------------------------------------------------
# 2 — CATALOG CANNOT TRUNCATE, STRUCTURALLY (R4.2) — occurrence 3
# ---------------------------------------------------------------------------


def test_no_group_op_ever_addresses_the_whole_functional_groups_map():
    """STRUCTURAL (R4.2 — the occurrence-3 fix): across every group op (materialize, update,
    delete), NO emitted op addresses the bare `["functional_groups"]` map — each op's path is
    `["functional_groups", <gkey>, ...]` (length ≥ 2). An update_item that never names the whole
    map is physically unable to truncate the catalog."""
    repo = RecordingFakeRepository()

    # Materialize (absent group → CREATE verb), via a reader with no authored groups.
    svc_create = ConfigFieldsCrudService(
        repo, reader=FakeReader({"fields": {}, "fixed_overrides": {}, "functional_groups": {}, "version": "v1"})
    )
    svc_create.set_group(_TENANT, "medical", {"order": 45})

    # Update an EXISTING group → UPDATE (per-aspect) verb.
    svc_update = ConfigFieldsCrudService(
        repo, reader=FakeReader({"fields": {}, "fixed_overrides": {}, "functional_groups": {"personal": {}}, "version": "v1"})
    )
    svc_update.set_group(_TENANT, "personal", {"order": 1})

    # Delete an EMPTY group → whole-entry REMOVE on functional_groups.<gkey>.
    svc_delete = _service_with_snapshot(repo, groups={"spare": {}})
    svc_delete.delete_group(_TENANT, "spare")

    # EVERY recorded group op addresses a NAMED group, never the whole map.
    group_ops = [
        op
        for call in repo.calls
        for op in call["ops"]
        if op["path"] and op["path"][0] == "functional_groups"
    ]
    assert group_ops, "expected at least one functional_groups op across the three calls"
    for op in group_ops:
        assert op["path"] != ["functional_groups"], (
            "NO op may address the whole functional_groups map — that is the occurrence-3 "
            f"truncation; got {op!r}"
        )
        assert len(op["path"]) >= 2 and op["path"][0] == "functional_groups"


def test_partial_group_payload_cannot_shrink_the_catalog_end_to_end():
    """END-TO-END occurrence-3 tripwire: a save that edits ONE group (a "partial groups payload")
    applied through the real apply_ops over the seeded 6-group catalog leaves the count at SIX —
    it cannot truncate 6→fewer (R4.2). The exact PROD corruption, now structurally impossible."""
    table = _CatalogFakeTable()
    _seed_catalog_row(table, groups=_SIX_GROUPS, version="v1")
    assert len(_stored_groups(table)) == 6

    svc = _e2e_service(table, version_fn=lambda: "v2")
    # A realistic "partial payload" save: the UI edited only the 'personal' group's order.
    svc.set_group(_TENANT, "personal", {"order": 11})

    after = _stored_groups(table)
    assert len(after) == 6, "a partial group edit must NEVER reduce the catalog count (occurrence 3)"
    assert set(after) == set(_SIX_GROUPS)
    assert after["personal"]["order"] == 11


def test_materialize_then_edit_sequence_keeps_catalog_whole():
    """A sequence — materialise an absent base group, then edit an existing one — grows the catalog
    by exactly the materialised group and never drops a sibling (R4.1 + R4.2 together)."""
    table = _CatalogFakeTable()
    authored = {k: v for k, v in _SIX_GROUPS.items() if k != "consent"}  # 5 authored, consent absent
    _seed_catalog_row(table, groups=authored, version="v1")

    versions = iter(["v2", "v3"])
    # 1) materialise the absent base group 'consent'
    _e2e_service(table, version_fn=lambda: next(versions)).set_group(
        _TENANT, "consent", {"order": 60, "label": {"en": "Consent"}}
    )
    # 2) edit an existing group (fresh service re-reads the now-6-group row)
    _e2e_service(table, version_fn=lambda: next(versions)).set_group(
        _TENANT, "personal", {"order": 12}
    )

    after = _stored_groups(table)
    assert set(after) == set(_SIX_GROUPS), "catalog must end whole (all six groups present)"
    assert after["consent"] == {"order": 60, "label": {"en": "Consent"}}
    assert after["personal"]["order"] == 12
    # the four untouched groups are byte-identical to their seed
    for gkey in ("contact", "membership", "medical", "emergency"):
        assert after[gkey] == _SIX_GROUPS[gkey]


# ---------------------------------------------------------------------------
# 3 — DELETE an empty group leaves other groups byte-identical (R4.2/R1.2)
# ---------------------------------------------------------------------------


def test_delete_empty_group_removes_only_that_group_end_to_end():
    """END-TO-END: deleting an EMPTY group removes only its `functional_groups.<gkey>` entry; the
    other five groups survive byte-identical (no whole-catalog rewrite)."""
    table = _CatalogFakeTable()
    _seed_catalog_row(table, groups=_SIX_GROUPS, version="v1")  # no fields reference any group
    before = copy.deepcopy(_stored_groups(table))

    svc = _e2e_service(table, version_fn=lambda: "v2")
    svc.delete_group(_TENANT, "emergency")  # empty (no authored field references it) → allowed

    after = _stored_groups(table)
    assert "emergency" not in after
    assert set(after) == set(before) - {"emergency"}
    for gkey in after:
        assert after[gkey] == before[gkey], f"group {gkey!r} must be untouched by the delete"


# ===========================================================================
# TASK 3.2 — SCOPE correctness (design C4 "SCOPE"; requirements R5.2)
# ===========================================================================
#
# What this block PROVES (the three R5.2 clauses, each an INVARIANT case):
#
#   1. `set_field` PRESERVES the `scope` sub-object VERBATIM:
#      a. a Change-Op touching OTHER definition attrs (e.g. order/label) NEVER mutates a
#         field's stored `scope` — END-TO-END through the real apply_ops over a seeded row the
#         `scope` map is byte-identical afterwards (this is the R1/R5.2 isolation guarantee for
#         the scope aspect specifically);
#      b. a `set_field` CARRYING a `scope` value writes it UNCHANGED — the service passes the
#         `scope` object through verbatim (it is a DEFINITION attr, `scope ∈ FIELD_DEFINITION_ATTRS`),
#         never reshaping it.
#
#   2. `config#scope` (a SEPARATE governance_projection row) is UNTOUCHED by ANY field/group op:
#      every op a field/group Change-Op emits addresses a `config#fields` path only
#      (`fields.*` / `overrides.*` / `functional_groups.*`), and the service ALWAYS calls
#      `apply_ops(config_id="fields", ...)` — never `config_id="scope"`. A field/group write is
#      structurally incapable of mutating the scope-dimension row (design C4: "A group/field write
#      never touches `config#scope`").
#
#   3. A scope-dimension-backed CHOICELESS enum still sources its values from `config#scope`
#      (single source) AFTER a field write: the resolver sources a choiceless overlay `enum`'s
#      choices from the tenant's scope vocabulary (`scope_vocab`, derived from the `config#scope`
#      row), and that path is driven by the SEPARATE scope row — a `config#fields` write leaves it
#      intact, so the enum keeps resolving its values from `config#scope` (design C4; R5.2).
#
# The `scope` aspect is carried as a nested map under the override entry
# (`overrides.<dotted>.scope`), so clause 1a runs END-TO-END (service → real `apply_ops` →
# condition-evaluating `_CatalogFakeTable`) to prove the stored `scope` survives a sibling-attr
# edit. Clause 3 is proven at the RESOLVER level (the single source of the choiceless-enum-from-
# scope rule, `FieldResolver._as_variable_field`), exactly as the sibling scope-vocab tests do.
#
# **Validates: Requirements 5.2**

from sam.members.domain.config_fields_crud_service import (
    FIELD_DEFINITION_ATTRS,
    _CONFIG_ID_FIELDS,
)
from sam.members.domain.fixed_fields import EnumOption, FieldType
from sam.members.domain.field_resolver import (
    FieldResolver,
    FixedFieldOverride,
    OverlayError,
    OverlayField,
    StaticOverlayProvider,
    TenantOverlay,
)

# A representative stored `scope` sub-object as it rides on an override entry (the SAM read shape
# of FieldScope: enabled + value vocabulary + i18n label + the grant-requiring capabilities).
_SCOPE_SUBOBJECT = {
    "enabled": True,
    "values": ["North", "South", "East", "West"],
    "label": {"en": "Region", "nl": "Regio"},
    "required_for": ["Members_CRUD"],
}


# ---------------------------------------------------------------------------
# 1a — set_field touching OTHER attrs PRESERVES `scope` verbatim (END-TO-END)
# ---------------------------------------------------------------------------


def test_set_field_other_attr_preserves_stored_scope_verbatim_end_to_end():
    """END-TO-END (R5.2): editing a NON-scope attribute of a field that carries a stored `scope`
    sub-object leaves that `scope` byte-identical — the write addresses only the named aspect, so
    the scope axis definition (and therefore the `config#scope` derivation it feeds) stays correct."""
    table = _CatalogFakeTable()
    # A tenant VARIABLE field that IS a scope axis (the real h-dcn `region` shape): it carries a
    # `scope` sub-object + an order under `fields.<key>`.
    _seed_catalog_row(
        table,
        groups={"personal": {"label": {"en": "Personal"}, "order": 10}},
        version="v1",
        fields={"region": {"type": "enum", "order": 40, "scope": copy.deepcopy(_SCOPE_SUBOBJECT)}},
    )
    before_scope = copy.deepcopy(
        table.store[(_TENANT, _FIELDS_SK)]["fields"]["region"]["scope"]
    )

    svc = _e2e_service(table, version_fn=lambda: "v2")
    # Edit a DIFFERENT aspect (order) — never names `scope`.
    svc.set_field(_TENANT, "region", {"order": 41})

    entry = table.store[(_TENANT, _FIELDS_SK)]["fields"]["region"]
    assert entry["order"] == 41, "the named aspect changed"
    assert entry["scope"] == before_scope, (
        "the stored `scope` sub-object MUST be byte-identical — a sibling-attr edit may not mutate "
        "the scope axis (R5.2 / design C4)"
    )


# ---------------------------------------------------------------------------
# 1b — set_field CARRYING `scope` writes it VERBATIM (no reshaping)
# ---------------------------------------------------------------------------


def test_scope_is_a_definition_attr_set_field_may_carry_it():
    """`scope` is part of the DEFINITION surface, so `set_field` accepts it (and
    `set_field_application` would reject it — it is not an application attr)."""
    assert "scope" in FIELD_DEFINITION_ATTRS


def test_set_field_carrying_scope_writes_it_unchanged(repo):
    """A `set_field` carrying a `scope` value hands it to apply_ops VERBATIM — the service never
    reshapes the scope sub-object (R5.2). (UPDATE verb: the variable field exists → per-aspect SET.)
    `region` is a tenant VARIABLE scope-axis field → placed under `fields.<key>`."""
    svc = _existing_service(repo, ("fields", "region"))
    scope_value = copy.deepcopy(_SCOPE_SUBOBJECT)
    svc.set_field(_TENANT, "region", {"scope": scope_value})
    ops = repo.last["ops"]
    assert ops == [
        {"action": SET, "path": ["fields", "region", "scope"], "value": scope_value}
    ]
    # Identity-equal: the exact object handed in is written through, byte-for-byte.
    assert ops[0]["value"] == _SCOPE_SUBOBJECT


def test_set_field_create_carrying_scope_seeds_it_in_whole_entry(repo):
    """On a CREATE of a scope-axis variable field the whole-entry seed carries the `scope`
    sub-object unchanged inside the seeded map (verbatim, not reshaped)."""
    svc = _existing_service(repo)  # entry absent → CREATE verb
    scope_value = copy.deepcopy(_SCOPE_SUBOBJECT)
    svc.set_field(_TENANT, "region", {"order": 40, "scope": scope_value})
    ops = repo.last["ops"]
    assert ops == [
        {
            "action": SET,
            "path": ["fields", "region"],
            "value": {"order": 40, "scope": scope_value},
        }
    ]


# ---------------------------------------------------------------------------
# 2 — config#scope (a SEPARATE row) is UNTOUCHED by any field/group op
# ---------------------------------------------------------------------------


def test_every_field_and_group_op_targets_only_config_fields_never_config_scope(repo):
    """STRUCTURAL (R5.2 / design C4): across every field + group op kind, the service ALWAYS calls
    apply_ops with config_id='fields' and NEVER 'scope' — a field/group write is physically unable
    to reach the separate `config#scope` row."""
    svc = _service_with_snapshot(
        repo,
        fields={"shirt_size": {}, "region": {"scope": copy.deepcopy(_SCOPE_SUBOBJECT)}},
        overrides={"personal.gender": {}},
        groups={"custom": {}},
    )
    svc.set_field(_TENANT, "region", {"order": 1})
    svc.set_field(_TENANT, "shirt_size", {"label": {"en": "X"}})
    svc.set_field_application(_TENANT, "region", {"application_visible": True})
    svc.reset_field(_TENANT, "gender")
    svc.set_group(_TENANT, "custom", {"order": 2})

    assert repo.calls, "expected the ops above to reach apply_ops"
    for call in repo.calls:
        assert call["config_id"] == _CONFIG_ID_FIELDS == "fields", (
            f"a field/group op must target config#fields only, got config_id={call['config_id']!r}"
        )


def test_no_field_or_group_op_addresses_a_scope_row_path(repo):
    """Every emitted op's path is rooted at a `config#fields` container (`fields` / `overrides` /
    `functional_groups`) — never a `scope`/`config#scope`/`dimensions` path. The scope-dimension
    row is addressed by NO field/group op (design C4)."""
    svc = _service_with_snapshot(
        repo,
        fields={"region": {"scope": copy.deepcopy(_SCOPE_SUBOBJECT)}},
        groups={"custom": {}},
    )
    svc.set_field(_TENANT, "region", {"order": 1})
    svc.set_group(_TENANT, "custom", {"label": {"en": "Custom"}})
    svc.delete_field(_TENANT, "region")

    for call in repo.calls:
        for op in call["ops"]:
            assert op["path"][0] in ("fields", "overrides", "functional_groups"), (
                f"an op rooted outside config#fields can reach config#scope; got {op['path']!r}"
            )
            # The `scope` aspect, when present, is only ever a NESTED aspect UNDER an override
            # entry (overrides.<dotted>.scope) — never a top-level/separate-row path.
            assert op["path"][0] != "scope" and op["path"][0] != "dimensions"


# ---------------------------------------------------------------------------
# 3 — a scope-dimension-backed CHOICELESS enum still sources from config#scope
#     (single source) after a config#fields write
# ---------------------------------------------------------------------------


def _resolve_region_choices(overlay: TenantOverlay, *, scope_vocab):
    """Resolve the choiceless `region` overlay enum and return its resolved choices."""
    resolver = FieldResolver(StaticOverlayProvider({_TENANT: overlay}))
    config = resolver.resolve(_TENANT, scope_vocab=scope_vocab)
    region = next(f for f in config.fields if f.key == "region")
    return tuple(region.choices or ())


def test_choiceless_scope_enum_sources_values_from_config_scope_single_source():
    """R5.2 / design C4: a scope-dimension-backed CHOICELESS overlay enum (`region`, no inline
    choices/options) sources its values from the tenant's scope vocabulary — the `config#scope`
    row (passed as `scope_vocab`), the SINGLE source — NOT from duplicated inline choices."""
    # A choiceless enum overlay field — the exact h-dcn `region` shape (no inline choices/options).
    overlay = TenantOverlay(
        fields={"region": OverlayField(key="region", type=FieldType.ENUM, label={"en": "Region"})}
    )
    # The scope vocabulary comes from the SEPARATE config#scope row (the single source).
    scope_vocab = {"region": ("North", "South", "East", "West")}

    choices = _resolve_region_choices(overlay, scope_vocab=scope_vocab)
    assert choices == ("North", "South", "East", "West"), (
        "the choiceless scope enum must source its values from config#scope (scope_vocab), the "
        "single source"
    )


def test_choiceless_scope_enum_still_resolves_from_config_scope_after_a_fields_write():
    """R5.2: a `config#fields` write (which NEVER touches `config#scope`, proven above) leaves the
    scope row intact, so the choiceless `region` enum keeps resolving its values from the SAME
    `config#scope` vocabulary before AND after the write.

    The write is simulated end-to-end on the config#fields plane; the scope vocabulary (config#scope)
    is a SEPARATE, unchanged source, so re-resolving with the same `scope_vocab` yields the same
    values — demonstrating the single-source rule survives a fields mutation."""
    scope_vocab = {"region": ("North", "South", "East", "West")}

    # BEFORE: the overlay authors the choiceless region enum; it sources from config#scope.
    overlay_before = TenantOverlay(
        fields={"region": OverlayField(key="region", type=FieldType.ENUM, label={"en": "Region"})}
    )
    before = _resolve_region_choices(overlay_before, scope_vocab=scope_vocab)

    # A config#fields write runs end-to-end (edits an unrelated field) — config#scope is untouched
    # (the separate row is never addressed, per test_every_field_and_group_op_targets_only_... above).
    table = _CatalogFakeTable()
    _seed_catalog_row(
        table,
        groups={"personal": {"order": 10}},
        version="v1",
        fields={"region": {"type": "enum", "label": {"en": "Region"}}},
    )
    _e2e_service(table, version_fn=lambda: "v2").set_field(_TENANT, "shirt_size", {"order": 7})

    # AFTER: the SAME config#scope vocabulary still drives the choiceless enum's values — the
    # fields write did not disturb the single source.
    overlay_after = TenantOverlay(
        fields={"region": OverlayField(key="region", type=FieldType.ENUM, label={"en": "Region"})}
    )
    after = _resolve_region_choices(overlay_after, scope_vocab=scope_vocab)

    assert before == after == ("North", "South", "East", "West"), (
        "the choiceless scope enum must keep sourcing from config#scope (single source) across a "
        "config#fields write (R5.2)"
    )


def test_choiceless_scope_enum_without_vocab_is_still_a_config_bug():
    """Fail-fast preserved (design C4 / R5.2): a choiceless enum NOT backed by a scope dimension
    (absent from scope_vocab) is STILL rejected — scope sourcing is the ONLY sanctioned way a
    choiceless enum is valid, so the single-source rule does not become a loophole."""
    overlay = TenantOverlay(
        fields={"region": OverlayField(key="region", type=FieldType.ENUM, label={"en": "Region"})}
    )
    with pytest.raises(OverlayError):
        # No scope_vocab entry for `region` → a genuinely choiceless enum → config bug.
        _resolve_region_choices(overlay, scope_vocab={})


# ===========================================================================
# TASK 3.1 — ENUM correctness (design C4 "ENUM"; requirements R5.1 / R5.5)
# ===========================================================================
#
# What this block PROVES (the two R5.1/R5.5 clauses, each an INVARIANT case):
#
#   1. A tenant-authored ENUM value never DROPS on read (R5.1): with the single-vocabulary model
#      (C5) an override authoring its value list under the ONE canonical `options`
#      ([{value,label,roles?}]) reaches the resolved field's `choices` (derived from `options`).
#      Proven at the RESOLVER level (the single source of the base ⊕ overlay enum-value rule) so a
#      value a tenant added (e.g. the reported `died`) survives resolution rather than falling back
#      to the fixed field's BASE choices (the config#fields enum-choices data-loss). The retired
#      `options or choices` coalesce (F1) is gone; C7 migrates legacy bare-`choices` rows.
#
#   2. A `set_field` OPTIONS change rewrites ONLY the vocabulary data (R5.5 / R1): editing a
#      field's enum options through the Change-Op path leaves the field's OTHER attributes (label,
#      order, functional_group, type) byte-identical. Proven END-TO-END through the real `apply_ops`
#      over a seeded row (service → real repo → condition-evaluating `_CatalogFakeTable`) AND
#      reinforced by the always-running invariant harness (`assert_change_op_isolated`) over the
#      resolved record, so an options-only edit is isolated: under the per-aspect SET model an
#      options change addresses only `overrides.<dotted>.options`, never a sibling attr. This is the ENUM facet of
#      the root-cause guarantee — the `overrides` whole-entry REPLACE that stripped the stored label
#      when choices were edited (root-cause-analysis) is structurally gone.
#
# Clause 1 runs at the resolver (the authority for base ⊕ overlay enum values). Clause 2 runs
# end-to-end on the config#fields plane AND through the generic invariant engine, mirroring the
# Task 3.2 (SCOPE) structure above and reusing `_CatalogFakeTable` / `_e2e_service` /
# `_seed_catalog_row`.
#
# **Validates: Requirements 5.1, 5.5**

from sam.tests.e2e.invariant import ChangeOp, assert_change_op_isolated


def _resolve_field(overlay: TenantOverlay, field_key: str):
    """Resolve `overlay` for the test tenant and return the resolved field with `field_key`."""
    resolver = FieldResolver(StaticOverlayProvider({_TENANT: overlay}))
    config = resolver.resolve(_TENANT)
    return next(f for f in config.fields if f.key == field_key)


# ---------------------------------------------------------------------------
# 1 — a tenant-authored ENUM value never drops on read (the options⊕choices fallback)
# ---------------------------------------------------------------------------


def test_override_enum_value_from_rich_options_reaches_resolved_choices():
    """R5.1: a fixed-enum override authoring its values under rich `options` ({value,label}) resolves
    those values into the field's `choices` — a tenant value (`died`) is not dropped."""
    overlay = TenantOverlay(
        overrides={
            "membership.status": FixedFieldOverride(
                options=(
                    EnumOption(value="active", label={"en": "Active"}),
                    EnumOption(value="died", label={"nl": "Overleden", "en": "Passed Away"}),
                )
            )
        }
    )
    status = _resolve_field(overlay, "status")
    assert status.type is FieldType.ENUM
    assert "died" in tuple(status.choices or ()), (
        "a tenant-authored enum value authored under `options` must reach the resolved choices "
        "(R5.1 — the options fallback)"
    )


def test_override_enum_value_from_options_reaches_resolved_choices_value_only():
    """R5.1 (single-vocabulary, C5): a fixed-enum override authoring value-only `options`
    (`[{value:"man"},...]`, the canonical shape a migrated bare-`choices` list becomes) resolves
    those values into the field's `choices`, so a tenant value is not dropped and the resolver does
    NOT fall back to the base choices. The retired `options or choices` coalesce is gone — there is
    ONE vocabulary (`options`); C7 migrates legacy bare-`choices` rows into it."""
    overlay = TenantOverlay(
        overrides={"personal.gender": FixedFieldOverride(options=(
            EnumOption(value="man"),
            EnumOption(value="vrouw"),
            EnumOption(value="anders"),
        ))}
    )
    gender = _resolve_field(overlay, "gender")
    assert tuple(gender.choices or ()) == ("man", "vrouw", "anders")


def test_resolved_choices_stay_coherent_with_options():
    """design C4: the resolver keeps `choices` (the bare value list) coherent with the rich
    `options` a tenant authored — `choices` is exactly the options' values, in order."""
    overlay = TenantOverlay(
        overrides={
            "membership.status": FixedFieldOverride(
                options=(
                    EnumOption(value="active", label={"en": "Active"}),
                    EnumOption(value="lapsed", label={"en": "Lapsed"}),
                    EnumOption(value="died", label={"en": "Died"}),
                )
            )
        }
    )
    status = _resolve_field(overlay, "status")
    assert tuple(o.value for o in (status.options or ())) == tuple(status.choices or ())
    assert tuple(status.choices or ()) == ("active", "lapsed", "died")


# ---------------------------------------------------------------------------
# 2 — a set_field CHOICES change rewrites ONLY the choice data (END-TO-END + invariant)
# ---------------------------------------------------------------------------


def _seed_enum_override_row(table, *, options):
    """Seed a row whose `membership.status` override is an enum carrying label/order/group + options.

    Single-vocabulary (C5): the enum vocabulary is stored under the ONE canonical `options`
    attribute ([{value, label?}]). The sibling attributes (label/order/functional_group/type) are
    what a vocabulary-only edit must leave untouched — the ENUM facet of the root-cause
    'whole-entry replace stripped the label'.
    """
    _seed_catalog_row(
        table,
        groups={"membership": {"label": {"en": "Membership"}, "order": 30}},
        version="v1",
        overrides={
            "membership.status": {
                "type": "enum",
                "label": {"en": "Status", "nl": "Status"},
                "order": 35,
                "functional_group": "membership",
                "options": list(options),
            }
        },
    )


def test_set_field_options_change_rewrites_only_vocab_data_end_to_end():
    """END-TO-END (R5.5 / R1): editing ONLY the enum `options` of a field through the Change-Op
    path rewrites the stored `options` and leaves every OTHER stored aspect (label/order/
    functional_group/type) byte-identical — the ENUM facet of the no-strip guarantee. Single
    vocabulary (C5): the edit targets the ONE canonical `options` attribute."""
    table = _CatalogFakeTable()
    _seed_enum_override_row(table, options=[{"value": "active"}, {"value": "lapsed"}])
    before_entry = copy.deepcopy(
        table.store[(_TENANT, _FIELDS_SK)]["overrides"]["membership.status"]
    )

    svc = _e2e_service(table, version_fn=lambda: "v2")
    # A realistic vocabulary-only edit: the admin added `died` to the status enum.
    new_options = [
        {"value": "active", "label": {"en": "Active"}},
        {"value": "lapsed", "label": {"en": "Lapsed"}},
        {"value": "died", "label": {"nl": "Overleden", "en": "Passed Away"}},
    ]
    svc.set_field(_TENANT, "membership.status", {"options": new_options})

    entry = table.store[(_TENANT, _FIELDS_SK)]["overrides"]["membership.status"]
    # The vocabulary data was rewritten...
    assert entry["options"] == new_options
    # ...and EVERY other stored aspect is byte-identical (the whole-entry-replace strip is gone).
    for aspect in ("type", "label", "order", "functional_group"):
        assert entry[aspect] == before_entry[aspect], (
            f"an options-only edit must preserve the field's {aspect!r} (R5.5 / R1) — got "
            f"{entry.get(aspect)!r}, expected {before_entry[aspect]!r}"
        )


def test_set_field_options_change_emits_only_the_options_path(repo):
    """The Change-Op for a vocabulary-only edit addresses ONLY `overrides.<dotted>.options` — never
    a sibling attr (per-aspect SET). This is WHY the end-to-end strip cannot happen (R5.5). Single
    vocabulary (C5): the one canonical attribute is `options`."""
    svc = _existing_service(repo, ("fixed_overrides", "membership.status"))
    svc.set_field(_TENANT, "status", {"options": [{"value": "died"}]})
    ops = repo.last["ops"]
    assert ops == [
        {
            "action": SET,
            "path": ["overrides", "membership.status", "options"],
            "value": [{"value": "died"}],
        }
    ], "an options-only edit must emit exactly one SET on the options aspect, nothing else"


def test_set_field_options_change_is_isolated_on_the_resolved_record():
    """INVARIANT (R5.5 / R9): read-resolve → apply an options-only `set_field` → read-resolve, and
    assert via the generic engine that ONLY `fields.status.options` changed on the RESOLVED record
    (the enum value survives AND nothing else — label/order/group — moved).

    Drives the real resolver (reader over the stored row) + the real `apply_ops`, so this is the
    end-to-end isolation proof the Change-Op path delivers — the GREEN counterpart to the xfail RED
    whole-row case in `sam/tests/e2e/test_config_fields_roundtrip_red.py`. Single vocabulary (C5):
    the edit targets the ONE canonical `options` attribute; the derived `choices` stays coherent."""
    table = _CatalogFakeTable()
    _seed_enum_override_row(table, options=[{"value": "active"}, {"value": "lapsed"}])

    def read_resolved() -> dict:
        """Resolve the stored row through the real reader mapping + resolver into the keyed shape
        the invariant engine diffs (mirrors the e2e `_serialize_resolved`)."""
        # Resolve base ⊕ overlay via a StaticOverlayProvider built from the stored override shape,
        # routed through the REAL reader `_build_override` (single-vocabulary `options`, C5).
        reader_overlay = _overlay_from_stored(table)
        resolver = FieldResolver(StaticOverlayProvider({_TENANT: reader_overlay}))
        config = resolver.resolve(_TENANT)
        return {
            "fields": {
                f.key: {
                    "type": getattr(f.type, "value", f.type),
                    "label": dict(f.label or {}),
                    "order": f.order,
                    "functional_group": f.functional_group,
                    "options": (
                        [o.value for o in f.options] if f.options is not None else None
                    ),
                }
                for f in config.fields
            }
        }

    before = read_resolved()
    svc = _e2e_service(table, version_fn=lambda: "v2")
    svc.set_field(
        _TENANT,
        "membership.status",
        {"options": [{"value": "active"}, {"value": "lapsed"}, {"value": "died"}]},
    )
    after = read_resolved()

    # The enum value SURVIVED the write (it is now present in the resolved options)...
    assert "died" in (after["fields"]["status"]["options"] or [])
    # ...and the options-only edit is ISOLATED: only fields.status.options changed.
    op = ChangeOp.set_field_attr("status", "options")
    assert_change_op_isolated(before, op, after)


def _overlay_from_stored(table) -> TenantOverlay:
    """Build a TenantOverlay from the stored config#fields row via the real reader mapping.

    Routes the stored `overrides` map through `MembersProjectionReader._build_override` (the unit
    under proof for the single-vocabulary `options` read, C5) so the resolved record reflects the
    REAL read path — not a hand-built overlay."""
    from sam.members.repository.projection_config_reader import MembersProjectionReader

    stored = table.store[(_TENANT, _FIELDS_SK)]
    overrides = {
        dotted: MembersProjectionReader._build_override(spec)
        for dotted, spec in stored.get("overrides", {}).items()
        if isinstance(spec, dict)
    }
    return TenantOverlay(overrides=overrides)


# ===========================================================================
# TASK 4.2 — client_op_id IDEMPOTENCY, proven END-TO-END through the service
# (design C2 "Idempotency"; requirements R6)
# ===========================================================================
#
# Task 2.4 built the repository idempotency HOOK (apply_ops stamps `last_client_op_id`; on a
# conditional-check failure it re-reads and returns success when the stored id already equals the
# retry's id). Task 2.7 threads `client_op_id` from the edge (the Change-Op body) through the
# service to apply_ops. This block COMPLETES + PROVES the behaviour END-TO-END: it drives the REAL
# ConfigFieldsCrudService → the REAL MembersConfigWriteRepository.apply_ops → the condition-
# evaluating `_CatalogFakeTable`, exercising the three cases the design names:
#
#   1. LOST-RESPONSE REPLAY → SUCCESS (not a self-409): a retry carrying the SAME `client_op_id`
#      that ALREADY produced the current stored version is recognised as an idempotent replay —
#      the service returns `{"version": <already-applied>, "idempotent_replay": True}` and NO
#      second write happens (the stored version is unchanged).
#
#   2. SAME id, GENUINELY DIFFERENT concurrent edit → still 409: a retry carrying a `client_op_id`
#      that does NOT match the row's stored `last_client_op_id` (because another, different edit
#      advanced the version) is a real StaleVersionError — the idempotency hook does not
#      false-positive, and no clobber occurs.
#
#   3. ABSENT id on a stale base → current behaviour (plain 409): with NO `client_op_id`, a stale
#      base version is the ordinary StaleVersionError — the idempotency shortcut is never attempted.
#
# The lost-response retry is modelled faithfully: the stored row reflects the FIRST (successful but
# lost-response) write — bumped version + stamped op id — while the service reads the STALE base
# the client originally held (via a reader pinned to that pre-write version). That is exactly the
# shape of a client that never saw the first write's response and retried with its old base.
#
# **Validates: Requirements 6.1, 6.2 (idempotent-replay path, design C2)**


def _service_over_table_with_base_version(table, *, base_version, version_fn):
    """A real service whose placement/version read reports `base_version` (the STALE base the
    client originally read), wired to the real apply_ops repository over `table`.

    `_e2e_service` reads the version from the CURRENT table state, which would already be the
    post-first-write version — the wrong thing for a lost-response retry. Here the reader is pinned
    to the pre-write `base_version` (what the client held) while the table already carries the
    first write's result, so the conditional check fails and the idempotency hook decides the
    outcome from the stored `last_client_op_id`.
    """
    stored = table.store[(_TENANT, _FIELDS_SK)]
    reader = FakeReader(
        {
            "fields": copy.deepcopy(stored.get("fields", {})),
            "fixed_overrides": copy.deepcopy(stored.get("overrides", {})),
            "functional_groups": copy.deepcopy(stored.get("functional_groups", {})),
            "version": base_version,
        }
    )
    repo = MembersConfigWriteRepository(table=table, version_fn=version_fn)
    return ConfigFieldsCrudService(repo, reader=reader)


def _seed_variable_field_row(table, *, version, last_client_op_id=None, field_value=None):
    """Seed a row carrying a `shirt_size` variable field at `version`, optionally with a stamped
    `last_client_op_id` (modelling a row already produced by an idempotency-carrying write)."""
    row = {
        schema.PARTITION_KEY_ATTR: _TENANT,
        schema.SORT_KEY_ATTR: _FIELDS_SK,
        schema.VERSION_ATTR: version,
        "fields": {"shirt_size": field_value} if field_value is not None else {},
        "overrides": {},
        "functional_groups": {},
    }
    if last_client_op_id is not None:
        row["last_client_op_id"] = last_client_op_id
    table.seed(row)


def test_lost_response_retry_same_op_id_returns_success_through_the_service():
    """1 — END-TO-END idempotent replay: a retry whose `client_op_id` already produced the current
    version returns SUCCESS (idempotent_replay=True), NOT a self-409, and makes NO second write.

    Validates: Requirement 6.2 (idempotent replay, design C2)
    """
    table = _CatalogFakeTable()
    # The row reflects the FIRST write that the client never saw the response for: the version was
    # bumped to v-2 and the op id `op-abc` was stamped, and the field value it set is present.
    _seed_variable_field_row(
        table, version="v-2", last_client_op_id="op-abc", field_value={"key": "shirt_size", "order": 1}
    )
    before = copy.deepcopy(table.store[(_TENANT, _FIELDS_SK)])

    # The client retries with the STALE base (v-1, what it read before the first write) + the SAME
    # op id. version_fn would mint v-3 IF a write happened — it must NOT.
    svc = _service_over_table_with_base_version(table, base_version="v-1", version_fn=lambda: "v-3")
    result = svc.set_field(_TENANT, "shirt_size", {"order": 1}, client_op_id="op-abc")

    # The service passes the repository's idempotent-replay result through verbatim.
    assert result == {"version": "v-2", "idempotent_replay": True}
    # NO second write: the stored row is byte-identical to the first write's result (still v-2).
    assert table.store[(_TENANT, _FIELDS_SK)] == before
    assert table.store[(_TENANT, _FIELDS_SK)][schema.VERSION_ATTR] == "v-2"


def test_same_op_id_but_a_different_concurrent_edit_still_409s_through_the_service():
    """2 — END-TO-END genuine conflict: a retry carrying `op-abc` against a row that was advanced
    by a DIFFERENT edit (stored `last_client_op_id` is `op-OTHER`) is a real StaleVersionError —
    the idempotency hook does not false-positive, and nothing is clobbered.

    Validates: Requirement 6.2 (no spurious replay on a genuine concurrent edit)
    """
    table = _CatalogFakeTable()
    # A DIFFERENT writer's op (`op-OTHER`) got there first and advanced the version to v-2.
    _seed_variable_field_row(
        table, version="v-2", last_client_op_id="op-OTHER", field_value={"key": "shirt_size", "order": 9}
    )
    before = copy.deepcopy(table.store[(_TENANT, _FIELDS_SK)])

    svc = _service_over_table_with_base_version(table, base_version="v-1", version_fn=lambda: "v-3")
    with pytest.raises(StaleVersionError):
        svc.set_field(_TENANT, "shirt_size", {"order": 1}, client_op_id="op-abc")

    # No clobber — the other writer's version + op id + value stand.
    assert table.store[(_TENANT, _FIELDS_SK)] == before


def test_absent_op_id_on_a_stale_base_is_a_plain_409_through_the_service():
    """3 — END-TO-END absent id: with NO `client_op_id`, a stale base is the ordinary 409
    (StaleVersionError) — the idempotency shortcut is never attempted (unchanged pre-4.2 behaviour).

    Validates: Requirement 6.2 (stale write rejected atomically when no idempotency token given)
    """
    table = _CatalogFakeTable()
    # The row carries a stamped op id, but the retry supplies NONE — the stored id must not rescue it.
    _seed_variable_field_row(
        table, version="v-2", last_client_op_id="op-abc", field_value={"key": "shirt_size", "order": 9}
    )
    before = copy.deepcopy(table.store[(_TENANT, _FIELDS_SK)])

    svc = _service_over_table_with_base_version(table, base_version="v-1", version_fn=lambda: "v-3")
    with pytest.raises(StaleVersionError):
        svc.set_field(_TENANT, "shirt_size", {"order": 1})  # no client_op_id

    assert table.store[(_TENANT, _FIELDS_SK)] == before  # atomic — no partial change


def test_first_write_with_op_id_succeeds_and_stamps_the_row_through_the_service():
    """The happy path (no conflict): the FIRST write carrying a `client_op_id` succeeds, stamps the
    row's `last_client_op_id`, and bumps the version — this is the state a later lost-response retry
    recognises as an idempotent replay (case 1 above).

    Validates: Requirement 6.1
    """
    table = _CatalogFakeTable()
    _seed_variable_field_row(table, version="v-1")  # fresh row, no op id yet

    svc = _e2e_service(table, version_fn=lambda: "v-2")
    result = svc.set_field(_TENANT, "shirt_size", {"order": 1}, client_op_id="op-abc")

    assert result == {"version": "v-2", "idempotent_replay": False}
    stored = table.store[(_TENANT, _FIELDS_SK)]
    assert stored["last_client_op_id"] == "op-abc"
    assert stored[schema.VERSION_ATTR] == "v-2"


# ===========================================================================
# TASK 4.1 — GUARDED ONE-SHOT auto-retry on a version conflict
# (design C2 "Concurrency + retry"; requirements R6.2; design-review Should-fix)
# ===========================================================================
#
# What this block PROVES (on top of the 2.4 conditional-write + 4.2 idempotency above):
#
#   1. RETRY SUCCEEDS on a SHARED-ROW conflict from an UNRELATED edit: under D3(A) the configurator
#      and the form-builder share one `config#fields` row, so a row-level `version` conflict can be
#      raised by a concurrent edit to a DIFFERENT identity. The service catches the first
#      StaleVersionError, RE-READS strongly-consistent, RE-DERIVES the ops against the fresh view,
#      and retries the write ONCE — it then lands, AND the unrelated concurrent edit survives
#      (the retry is isolated to its own identity; it does not clobber the other writer's change).
#
#   2. RE-DERIVE ON RETRY (not a blind replay): when the concurrent edit changed the entry's
#      EXISTENCE (a CREATE that another writer turned into an already-existing entry), the retry
#      re-runs placement against the fresh snapshot and emits the UPDATE verb — so the second
#      attempt is correct for the new state, never a stale CREATE that would fail or clobber.
#
#   3. RETRY-ALSO-CONFLICTS → 409 (never loop): if the row keeps changing on EVERY attempt (a
#      genuine, sustained concurrent edit), the service retries exactly ONCE and then surfaces the
#      StaleVersionError — which the edge maps to a caller-safe 409 "reload and retry". No partial
#      change is made, and the write is attempted at most twice (one retry, bounded).
#
#   4. NO RETRY on a validation error: a ConfigFieldsCrudError raised while DERIVING the ops (an
#      out-of-surface attr, a base-field delete) is raised on the FIRST pass before any apply_ops —
#      it is never retried (a retry would be pointless and would re-run the guard).
#
# The proof runs END-TO-END through the real `ConfigFieldsCrudService` + the real
# `MembersConfigWriteRepository.apply_ops` over a `_RacingCatalogTable` that models a concurrent
# writer: its first `update_item` simulates another edit having already committed (the caller's
# version condition fails AND the stored row is advanced by an UNRELATED change), so the service's
# re-read sees the fresh version and the retry's optimistic lock matches. A fresh reader is built
# from the live table on each read, so the re-derive genuinely re-observes the concurrent state.
#
# **Validates: Requirements 6.2**


class _RacingCatalogTable(_CatalogFakeTable):
    """A `_CatalogFakeTable` that injects a CONCURRENT writer on the first N `update_item` calls.

    On each of the first `fail_times` writes it behaves as if another client committed first: it
    applies a provided `concurrent_edit` to the stored row (advancing its `version` to the next
    `concurrent_versions` value) and then raises ConditionalCheckFailedException for the CALLER's
    write — exactly the shared-row conflict D3(A) warns about. After `fail_times` such injections,
    writes evaluate normally (so a re-read + retry can succeed). Every `update_item` is counted.
    """

    def __init__(self, *, fail_times, concurrent_edit=None, concurrent_versions=()):
        super().__init__()
        self._remaining_failures = fail_times
        self._concurrent_edit = concurrent_edit or (lambda row: None)
        self._concurrent_versions = iter(concurrent_versions)
        self.update_calls = 0

    def update_item(self, **kwargs):
        self.update_calls += 1
        if self._remaining_failures > 0:
            self._remaining_failures -= 1
            # A concurrent writer committed first: mutate the stored row + bump its version, then
            # fail the caller's conditional write (its base version is now stale).
            key_tuple = (_TENANT, _FIELDS_SK)
            existing = self.store.get(key_tuple)
            if existing is not None:
                self._concurrent_edit(existing)
                try:
                    existing[schema.VERSION_ATTR] = next(self._concurrent_versions)
                except StopIteration:
                    pass
            raise _conditional_check_failed()
        return super().update_item(**kwargs)


def _service_fresh_reader_each_read(table, version_fn):
    """A real service whose reader is REBUILT from the live table on every placement read, so the
    one-shot retry genuinely re-observes the concurrent state (not a snapshot pinned at construction).

    `FakeReader` caches the row it was built with; the retry must see the CURRENT row, so we inject
    a tiny reader shim that reads the table fresh each call (mirroring a real ConsistentRead reader).
    """

    class _LiveReader:
        def get_raw_fields_overlay(self, tenant_id, *, consistent_read=False):
            stored = table.store.get((_TENANT, _FIELDS_SK))
            if not stored:
                return {}
            return {
                "fields": copy.deepcopy(stored.get("fields", {})),
                "fixed_overrides": copy.deepcopy(stored.get("overrides", {})),
                "functional_groups": copy.deepcopy(stored.get("functional_groups", {})),
            }

        def get_config_fields_version(self, tenant_id, *, consistent_read=False):
            stored = table.store.get((_TENANT, _FIELDS_SK))
            if not stored:
                return (False, None)
            return (True, stored.get(schema.VERSION_ATTR))

    repo = MembersConfigWriteRepository(table=table, version_fn=version_fn)
    return ConfigFieldsCrudService(repo, reader=_LiveReader())


def test_one_shot_retry_succeeds_after_an_unrelated_concurrent_edit_end_to_end():
    """1 — END-TO-END: a shared-row version conflict raised by an UNRELATED concurrent edit is
    absorbed by the GUARDED one-shot retry: the service re-reads, re-derives, retries once, the
    write lands, AND the concurrent edit survives (the retry is isolated to its own identity).

    Validates: Requirement 6.2
    """
    # The concurrent writer edits a DIFFERENT group ("contact") while our op edits "personal".
    def concurrent_edit(row):
        row.setdefault("functional_groups", {}).setdefault("contact", {})["order"] = 99

    table = _RacingCatalogTable(
        fail_times=1, concurrent_edit=concurrent_edit, concurrent_versions=["v-concurrent"]
    )
    _seed_catalog_row(table, groups=copy.deepcopy(_SIX_GROUPS), version="v1")

    # version_fn mints the stamp for OUR successful retry write.
    svc = _service_fresh_reader_each_read(table, version_fn=lambda: "v-ours")
    result = svc.set_group(_TENANT, "personal", {"order": 11})

    # The write ultimately SUCCEEDED (the retry landed), after EXACTLY two update_item attempts.
    assert result["version"] == "v-ours"
    assert result["idempotent_replay"] is False
    assert table.update_calls == 2, "expected one failed attempt + one successful retry"

    after = _stored_groups(table)
    # OUR edit landed...
    assert after["personal"]["order"] == 11
    # ...AND the unrelated concurrent edit SURVIVED (the retry did not clobber it).
    assert after["contact"]["order"] == 99
    # the catalog is still whole — no sibling dropped.
    assert set(after) == set(_SIX_GROUPS)


def test_one_shot_retry_re_derives_create_to_update_when_entry_now_exists_end_to_end():
    """2 — END-TO-END re-derive (not a blind replay): our op CREATEs a group that a concurrent
    writer materialised first. On the conflict the retry re-reads, SEES the now-existing entry, and
    emits the UPDATE verb — the second attempt is correct for the new state and lands cleanly.

    Validates: Requirement 6.2
    """
    # The concurrent writer MATERIALISES the very group we are creating ("medical"), with a label.
    def concurrent_edit(row):
        row.setdefault("functional_groups", {})["medical"] = {
            "label": {"en": "Medical"},
            "order": 40,
        }

    table = _RacingCatalogTable(
        fail_times=1, concurrent_edit=concurrent_edit, concurrent_versions=["v-concurrent"]
    )
    # Seed WITHOUT "medical" so our first-pass placement picks the CREATE verb.
    authored = {k: v for k, v in _SIX_GROUPS.items() if k != "medical"}
    _seed_catalog_row(table, groups=copy.deepcopy(authored), version="v1")

    svc = _service_fresh_reader_each_read(table, version_fn=lambda: "v-ours")
    # We set only `order`; the concurrent writer already seeded the label.
    svc.set_group(_TENANT, "medical", {"order": 45})

    assert table.update_calls == 2
    after = _stored_groups(table)
    # The UPDATE-verb retry set ONLY `order` on the now-existing entry — the concurrent writer's
    # label SURVIVES (a blind CREATE replay would have overwritten the whole entry, dropping it).
    assert after["medical"]["order"] == 45
    assert after["medical"]["label"] == {"en": "Medical"}, (
        "the retry must UPDATE the now-existing entry, not blind-replay a CREATE that clobbers it"
    )


def test_retry_also_conflicts_surfaces_stale_version_and_makes_no_change_end_to_end():
    """3 — END-TO-END sustained conflict: when the row keeps changing on EVERY attempt, the service
    retries EXACTLY ONCE and then surfaces StaleVersionError (the edge maps it to a caller-safe
    409). The write is attempted at most twice and NO partial change from our op is made.

    Validates: Requirement 6.2
    """
    # The concurrent writer bumps the row on EVERY write attempt (an unrelated, sustained edit).
    def concurrent_edit(row):
        row.setdefault("functional_groups", {}).setdefault("contact", {})["order"] = (
            row.get("functional_groups", {}).get("contact", {}).get("order", 20) + 1
        )

    table = _RacingCatalogTable(
        fail_times=99,  # never stops failing — a genuine sustained conflict
        concurrent_edit=concurrent_edit,
        concurrent_versions=["v-c1", "v-c2", "v-c3"],
    )
    _seed_catalog_row(table, groups=copy.deepcopy(_SIX_GROUPS), version="v1")
    before = copy.deepcopy(_stored_groups(table))

    svc = _service_fresh_reader_each_read(table, version_fn=lambda: "v-ours")
    with pytest.raises(StaleVersionError):
        svc.set_group(_TENANT, "personal", {"order": 11})

    # Bounded: one initial attempt + exactly ONE retry = two update_item calls, never a loop.
    assert table.update_calls == 2, "the retry must be ONE-SHOT, never a loop"
    # OUR op made no change — `personal.order` is unchanged from its seed (only the concurrent
    # writer's `contact` moved, which is not our write).
    after = _stored_groups(table)
    assert after["personal"]["order"] == before["personal"]["order"], (
        "our op must make NO partial change when both attempts are rejected"
    )


def test_validation_error_in_derive_is_not_retried():
    """4 — a ConfigFieldsCrudError raised while DERIVING the ops (out-of-surface attr) is raised on
    the FIRST pass before any apply_ops — it is never retried, and no write is attempted.

    Validates: Requirement 6.2
    """
    table = _RacingCatalogTable(fail_times=1)
    _seed_catalog_row(table, groups=copy.deepcopy(_SIX_GROUPS), version="v1")

    svc = _service_fresh_reader_each_read(table, version_fn=lambda: "v-ours")
    with pytest.raises(ConfigFieldsCrudError):
        # An application attr on set_field is rejected while deriving — before any update_item.
        svc.set_field(_TENANT, "gender", {"application_visible": True})

    assert table.update_calls == 0, "a validation error must never reach (or retry) a write"


# ===========================================================================
# 03a TASK 7 (C2) + TASK 8 (C3) — write surface accepts `options` ONLY; the
# Change-Op + one-key (`overrides`→`fixed_overrides`) contract is preserved; a
# duplicate-`value` `options` list is rejected caller-safe BEFORE any repo call.
# ===========================================================================
#
# What this block PROVES:
#   C2 — `choices` is RETIRED from the write surface: `set_field` now rejects a `choices`
#        definition attr out-of-surface (ConfigFieldsCrudError), accepting ONLY the one canonical
#        `options` vocabulary. The storage key stays `overrides`, served under the wire key
#        `fixed_overrides` (the one-key contract), and the write remains a Change-Op on a single
#        path (no whole-row replace) — asserted here on a base-field `options` write.
#   C3 — an `options` list carrying a DUPLICATE `value` is rejected with a caller-safe
#        ConfigFieldsCrudError (subclasses ValueError → 400) BEFORE any repository call, so a
#        duplicate never reaches storage (P4 / R2.4, steering 30).
#
# Validates: Requirements 2.1, 2.4, 3.2, 3.3 · Components: C2, C3 (P4), F12


# ---------------------------------------------------------------------------
# C2 — `choices` is no longer an accepted definition attribute
# ---------------------------------------------------------------------------


def test_choices_is_retired_from_the_definition_surface():
    """C2 (R2.1): `choices` is NOT in the definition surface — the write accepts ONLY `options`."""
    assert "choices" not in FIELD_DEFINITION_ATTRS
    assert "options" in FIELD_DEFINITION_ATTRS


def test_set_field_rejects_choices_definition_attribute(service):
    """C2: a `set_field` carrying the retired `choices` attr is rejected out-of-surface — the one
    canonical vocabulary is `options` (R2.1/R3.3). Rejected BEFORE any repository call."""
    with pytest.raises(ConfigFieldsCrudError) as exc:
        service.set_field(
            _TENANT, "gender", {"choices": [{"value": "man"}, {"value": "vrouw"}]}
        )
    assert "choices" in str(exc.value)


def test_set_field_options_write_preserves_change_op_and_one_key_contract(service, repo):
    """C2 (R3.3): an `options` write to a base field places under the STORAGE map `overrides`
    (served under the wire key `fixed_overrides` — the one-key contract) and remains a Change-Op on
    a SINGLE path — a whole-entry SET on CREATE, never a whole-row replace.

    `service` has no reader → CREATE verb (one whole-entry SET under `overrides.<dotted>`)."""
    service.set_field(
        _TENANT, "gender", {"options": [{"value": "man"}, {"value": "vrouw"}]}
    )
    ops = repo.last["ops"]
    assert ops == [
        {
            "action": SET,
            "path": ["overrides", "personal.gender"],
            "value": {"options": [{"value": "man"}, {"value": "vrouw"}]},
        }
    ], "the write is ONE whole-entry SET addressing the single `overrides.<dotted>` storage path"
    # The storage map name is `overrides` (NOT the wire key `fixed_overrides`) — the service writes
    # to storage; the reader serves that same map under `fixed_overrides` (the one-key contract).
    assert ops[0]["path"][0] == "overrides"
    assert _CONFIG_ID_FIELDS == "fields"


def test_set_field_update_options_emits_single_options_path(repo):
    """C2 (R3.3): on an EXISTING entry an `options` edit emits exactly ONE per-aspect SET on the
    `options` path — a single-path Change-Op, no sibling attr and no whole-row replace."""
    svc = _existing_service(repo, ("fixed_overrides", "membership.status"))
    svc.set_field(_TENANT, "status", {"options": [{"value": "active"}, {"value": "died"}]})
    assert repo.last["ops"] == [
        {
            "action": SET,
            "path": ["overrides", "membership.status", "options"],
            "value": [{"value": "active"}, {"value": "died"}],
        }
    ]


# ---------------------------------------------------------------------------
# C3 (P4) — duplicate-`value` `options` list rejected caller-safe before any repo call
# ---------------------------------------------------------------------------


def test_set_field_rejects_duplicate_option_values_before_repo_call(service, repo):
    """C3 (R2.4): an `options` list with a duplicate `value` is rejected via ConfigFieldsCrudError
    (→ caller-safe 400) BEFORE any repository call — the duplicate never reaches storage."""
    with pytest.raises(ConfigFieldsCrudError) as exc:
        service.set_field(
            _TENANT,
            "gender",
            {"options": [{"value": "man"}, {"value": "vrouw"}, {"value": "man"}]},
        )
    # The rejection is a ValueError subclass (the edge maps it to a 400).
    assert isinstance(exc.value, ValueError)
    # The server-side-logged detail names the duplicated value; the client sees only a generic msg.
    assert "man" in str(exc.value)
    # No write was attempted — the guard fired before any repository call.
    assert not repo.calls


def test_set_field_rejects_duplicate_bare_string_option_values(service, repo):
    """C3 (R2.4): the duplicate guard also catches bare-string `options` entries (shorthand for
    `{"value": <string>}`) — rejected before any repository call."""
    with pytest.raises(ConfigFieldsCrudError):
        service.set_field(_TENANT, "gender", {"options": ["man", "vrouw", "man"]})
    assert not repo.calls


def test_set_field_accepts_unique_option_values_duplicate_guard_passes(service, repo):
    """C3: a well-formed `options` list with all-unique values passes the duplicate guard and is
    written (the guard rejects ONLY genuine duplicates, never a valid vocabulary)."""
    service.set_field(
        _TENANT, "gender", {"options": [{"value": "man"}, {"value": "vrouw"}, {"value": "anders"}]}
    )
    assert repo.calls, "a unique-valued options list must still be written"


# ===========================================================================
# 03a TASK 7 (C2) — WRITE-SIDE SOURCE-INTEGRITY GUARDS W1 / W2 / W3
# (design "Write-side vocabulary invariants" W1/W2/W3; Property 5)
# ===========================================================================
#
# Because C1 now seeds the editor from `options` IDENTICALLY for every kind, the write edge must
# stop a stale catalog/scope snapshot being re-frozen inline, and stop an inline-source enum being
# made selectable with no vocabulary. Three NEW caller-safe rejections (ConfigFieldsCrudError →
# 400), each BEFORE any repository call (no `str(e)` leak — the reason is server-side-logged):
#
#   W1 — a REFERENCE field (the `membership_type` reference key, or a field whose declared `type`
#        is `reference`) may NOT carry an inline `options` payload. Its options are a snapshot of
#        the LIVE catalog populated at the read seam (C4); persisting them inline would re-freeze a
#        stale copy — the two-copies disease on the WRITE side.
#   W2 — a SCOPE-BACKED field (an enabled `scope` sub-object, sourced from `scope_vocab`) may NOT
#        carry inline `options` (Bug 2's shape) — rejected at the write edge so the stored row
#        stays honest (no inline vocabulary competing with the dimension).
#   W3 — an INLINE-SOURCE enum may NOT be saved selectable with an EXPLICIT empty `options` list
#        (the write-edge invariant). Scoped to an EXPLICIT `options: []` — staging a field WITHOUT
#        an `options` key stays legitimate (an absent key never trips W3), which is what makes the
#        read-time fail-loud discriminator unambiguous.
#
# Kind is classified from the payload UNIONED with the field's stored spec in the snapshot (an
# UPDATE may carry only `options`, so the kind is read from what is already stored when the payload
# is silent) — mirroring how the read seam classifies reference (MEMBERSHIP_TYPE_FIELD_KEY) and how
# the resolver carries `scope`.
#
# Validates: Requirements 2.1, 2.4, 2.6, 3.2, 3.3 · Components: C2, P5 (W1/W2/W3)


from sam.members.domain._membership_errors import MEMBERSHIP_TYPE_FIELD_KEY


# ---------------------------------------------------------------------------
# W1 — reference field rejects an inline `options` payload (→ caller-safe 400)
# ---------------------------------------------------------------------------


def test_w1_reference_field_by_membership_type_key_rejects_inline_options(repo):
    """W1: the `membership_type` reference field (classified by its reference key, mirroring the
    read seam's MEMBERSHIP_TYPE_FIELD_KEY check) rejects an inline `options` payload — its
    vocabulary is the live catalog, never inline. Rejected BEFORE any repository call."""
    # An existing override entry so the field is observable; the payload carries inline options.
    svc = _existing_service(repo, ("fixed_overrides", MEMBERSHIP_TYPE_FIELD_KEY))
    with pytest.raises(ConfigFieldsCrudError) as exc:
        svc.set_field(
            _TENANT,
            "membership_type",
            {"options": [{"value": "gold"}, {"value": "silver"}]},
        )
    assert "reference" in str(exc.value).lower()
    assert not repo.calls, "W1 must reject BEFORE any repository call"


def test_w1_reference_field_by_declared_type_rejects_inline_options(repo):
    """W1: a field whose declared `type` is `reference` (in the payload) rejects inline options,
    even for a non-`membership_type` identity."""
    svc = ConfigFieldsCrudService(repo)
    with pytest.raises(ConfigFieldsCrudError) as exc:
        svc.set_field(
            _TENANT,
            "some_ref",
            {"type": "reference", "options": [{"value": "x"}]},
        )
    assert "reference" in str(exc.value).lower()
    assert not repo.calls


def test_w1_reference_field_kind_read_from_stored_spec_when_payload_silent(repo):
    """W1: on an UPDATE whose payload carries ONLY `options` (no `type`), the reference kind is read
    from the field's STORED spec in the snapshot (`type: reference`) — still rejected."""
    svc = _service_with_snapshot(
        repo, fields={"some_ref": {"type": "reference", "label": {"en": "Ref"}}}
    )
    with pytest.raises(ConfigFieldsCrudError) as exc:
        svc.set_field(_TENANT, "some_ref", {"options": [{"value": "x"}]})
    assert "reference" in str(exc.value).lower()
    assert not repo.calls


def test_w1_reference_field_without_options_is_accepted(repo):
    """W1 is scoped to an INLINE OPTIONS payload: editing a NON-vocabulary attr (order/label) of a
    reference field is still allowed — the guard only rejects re-freezing inline options."""
    svc = _existing_service(repo, ("fixed_overrides", MEMBERSHIP_TYPE_FIELD_KEY))
    svc.set_field(_TENANT, "membership_type", {"order": 31})
    assert repo.calls, "a reference field edit that carries no `options` must still be written"
    assert repo.last["ops"] == [
        {"action": SET, "path": ["overrides", MEMBERSHIP_TYPE_FIELD_KEY, "order"], "value": 31}
    ]


# ---------------------------------------------------------------------------
# W2 — scope-backed field rejects an inline `options` payload (→ caller-safe 400)
# ---------------------------------------------------------------------------


def test_w2_scope_backed_field_by_payload_scope_rejects_inline_options(repo):
    """W2: a `set_field` carrying BOTH an enabled `scope` sub-object AND inline `options` is
    rejected — a scope-backed field sources its vocabulary from `scope_vocab`, never inline."""
    svc = ConfigFieldsCrudService(repo)
    scope_value = copy.deepcopy(_SCOPE_SUBOBJECT)  # enabled=True
    with pytest.raises(ConfigFieldsCrudError) as exc:
        svc.set_field(
            _TENANT,
            "region",
            {"scope": scope_value, "options": [{"value": "North"}]},
        )
    assert "scope" in str(exc.value).lower()
    assert not repo.calls, "W2 must reject BEFORE any repository call"


def test_w2_scope_backed_field_kind_read_from_stored_spec_when_payload_silent(repo):
    """W2: on an UPDATE whose payload carries ONLY `options` (no `scope`), the scope-backed kind is
    read from the STORED spec in the snapshot (an enabled `scope`) — still rejected."""
    svc = _service_with_snapshot(
        repo, fields={"region": {"scope": copy.deepcopy(_SCOPE_SUBOBJECT)}}
    )
    with pytest.raises(ConfigFieldsCrudError) as exc:
        svc.set_field(_TENANT, "region", {"options": [{"value": "North"}]})
    assert "scope" in str(exc.value).lower()
    assert not repo.calls


def test_w2_scope_backed_field_without_options_is_accepted(repo):
    """W2 is scoped to an INLINE OPTIONS payload: carrying `scope` alone (no `options`) is the
    legitimate way to author a scope axis — accepted and written verbatim."""
    svc = ConfigFieldsCrudService(repo)
    scope_value = copy.deepcopy(_SCOPE_SUBOBJECT)
    svc.set_field(_TENANT, "region", {"scope": scope_value})
    assert repo.calls, "authoring a scope axis without inline `options` must be accepted"
    assert repo.last["ops"] == [
        {"action": SET, "path": ["fields", "region"], "value": {"scope": scope_value}}
    ]


def test_w2_disabled_scope_is_not_scope_backed(repo):
    """W2: a `scope` sub-object with `enabled: False` is NOT an enabled scope axis, so it does not
    make the field scope-backed — an inline enum with that disabled scope is handled by W3, not W2
    (here with non-empty options it is a clean inline-enum write)."""
    svc = ConfigFieldsCrudService(repo)
    svc.set_field(
        _TENANT,
        "maybe_scope",
        {"type": "enum", "scope": {"enabled": False}, "options": [{"value": "a"}]},
    )
    assert repo.calls, "a disabled-scope inline enum with non-empty options is a clean write"


# ---------------------------------------------------------------------------
# W3 — inline-source enum rejects an EXPLICIT empty `options` payload (→ 400)
# ---------------------------------------------------------------------------


def test_w3_inline_enum_with_explicit_empty_options_is_rejected(repo):
    """W3: an inline-source enum (declared `type: enum`) saved selectable with an EXPLICIT empty
    `options` list is rejected — the write-edge invariant (an inline enum cannot read back empty
    unless the vocabulary failed to propagate). Rejected BEFORE any repository call."""
    svc = ConfigFieldsCrudService(repo)
    with pytest.raises(ConfigFieldsCrudError) as exc:
        svc.set_field(_TENANT, "shirt_size", {"type": "enum", "options": []})
    msg = str(exc.value).lower()
    assert "enum" in msg and "options" in msg
    assert not repo.calls, "W3 must reject BEFORE any repository call"


def test_w3_inline_enum_kind_read_from_stored_spec_when_payload_silent(repo):
    """W3: on an UPDATE whose payload carries ONLY an explicit empty `options` (no `type`), the
    inline-enum kind is read from the STORED spec (`type: enum`) — still rejected."""
    svc = _service_with_snapshot(repo, fields={"shirt_size": {"type": "enum"}})
    with pytest.raises(ConfigFieldsCrudError):
        svc.set_field(_TENANT, "shirt_size", {"options": []})
    assert not repo.calls


def test_w3_legitimate_staging_without_options_key_does_not_reject(repo):
    """W3 is scoped to an EXPLICIT empty `options`: staging an inline enum WITHOUT an `options` key
    (authoring its label/order first, adding the vocabulary later) is legitimate and NOT rejected —
    an ABSENT `options` key never trips W3."""
    svc = ConfigFieldsCrudService(repo)
    svc.set_field(_TENANT, "shirt_size", {"type": "enum", "label": {"en": "Shirt size"}})
    assert repo.calls, "staging an enum without an `options` key must be accepted (W3 scope)"


def test_w3_inline_enum_with_non_empty_options_is_accepted(repo):
    """W3: an inline enum saved with a NON-EMPTY `options` list satisfies the write-edge invariant
    and is written — the guard rejects ONLY an explicitly-empty vocabulary."""
    svc = ConfigFieldsCrudService(repo)
    svc.set_field(
        _TENANT,
        "shirt_size",
        {"type": "enum", "options": [{"value": "s"}, {"value": "m"}]},
    )
    assert repo.calls, "an inline enum with a non-empty options list must be written"


def test_w3_unknown_kind_explicit_empty_options_not_rejected(repo):
    """W3 fires only when the field is KNOWN to be an inline enum (payload/stored `type: enum`): an
    explicit empty `options` on a field of UNKNOWN kind (no `type` anywhere, not reference, not
    scope) is NOT rejected by W3 — the guard does not guess a kind it cannot observe. (This is the
    conservative create-vs-update scoping: W3 targets an enum being made selectable, which implies
    a known enum type.)"""
    svc = ConfigFieldsCrudService(repo)
    svc.set_field(_TENANT, "mystery", {"options": []})
    assert repo.calls, "an explicit empty options on an unknown-kind field is not a W3 violation"
