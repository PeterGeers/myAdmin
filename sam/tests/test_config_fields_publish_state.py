"""
bugfix-published-form-submit Round 3, Task 11.4 — unit tests for the publish-state Change-Op.

Parent spec: `.kiro/specs/Members/14 - public-pages-multi-tenant-serving`.
Bugfix spec: `.kiro/specs/Members/14 .../bugfix-published-form-submit` (design.md "Round 3").

What this asserts (`ConfigFieldsCrudService.set_publish_state`)
-----------------------------------------------------------------
Mirrors `set_form_slug`'s persist step (steering 39, `test_config_fields_slug_author.py`): a
SINGLE version-conditional `update_item` (via `apply_ops`) that SETs ONLY the two top-level
publish-state attributes (`published_version` / `published_at`), never a whole-record put, so
every untouched slice (`slug`, `fields`, `overrides`, `functional_groups`) survives BY
CONSTRUCTION.

- a valid call persists EXACTLY two `SET` ops, each naming only its own path;
- malformed `published_version` / `published_at` are rejected before any write (`apply_ops` never
  called);
- `client_op_id` forwards to `apply_ops` (lost-response idempotency, same as the sibling ops).

The write repository is the SAME in-memory `RecordingFakeRepository` the slug-author tests use.
No boto3, no AWS (steering 35/39).

Validates (bugfix): Requirements 8.4, 9.4
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
_BACKEND_SRC = os.path.join(_REPO_ROOT, "backend", "src")
if _BACKEND_SRC not in sys.path:
    sys.path.insert(0, _BACKEND_SRC)

from sam.members.domain.config_fields_crud_service import (
    ConfigFieldsCrudError,
    ConfigFieldsCrudService,
)
from sam.members.repository.projection_config_write_repository import SET
from sam.tests.test_config_fields_slug_author import RecordingFakeRepository

_TENANT = "h-dcn"


def _service(repo=None):
    repo = repo if repo is not None else RecordingFakeRepository()
    return ConfigFieldsCrudService(repo), repo


def test_set_publish_state_is_a_public_method():
    assert hasattr(ConfigFieldsCrudService, "set_publish_state")


def test_set_publish_state_persists_exactly_two_single_path_sets():
    svc, repo = _service()

    result = svc.set_publish_state(
        _TENANT, published_version=1, published_at="2026-01-01T00:00:00+00:00"
    )

    assert result == {"version": "v-next", "idempotent_replay": False}
    call = repo.last
    assert call["tenant_id"] == _TENANT
    assert call["config_id"] == "fields"
    assert call["ops"] == [
        {"action": SET, "path": ["published_version"], "value": 1},
        {
            "action": SET,
            "path": ["published_at"],
            "value": "2026-01-01T00:00:00+00:00",
        },
    ]


def test_set_publish_state_ops_never_name_an_unrelated_path():
    # Each op addresses ONLY its own top-level attribute — DynamoDB leaves `slug` / `fields` /
    # `overrides` / `functional_groups` physically untouched (by construction, steering 39).
    svc, repo = _service()
    svc.set_publish_state(
        _TENANT, published_version=2, published_at="2026-01-02T00:00:00+00:00"
    )
    paths = {tuple(op["path"]) for op in repo.last["ops"]}
    assert paths == {("published_version",), ("published_at",)}


def test_set_publish_state_forwards_client_op_id():
    svc, repo = _service()
    svc.set_publish_state(
        _TENANT,
        published_version=1,
        published_at="2026-01-01T00:00:00+00:00",
        client_op_id="op-456",
    )
    assert repo.last["client_op_id"] == "op-456"


@pytest.mark.parametrize("bad_version", [0, -1, True, "1", 1.5, None])
def test_set_publish_state_rejects_malformed_version_no_write(bad_version):
    svc, repo = _service()
    with pytest.raises(ConfigFieldsCrudError):
        svc.set_publish_state(
            _TENANT, published_version=bad_version, published_at="2026-01-01"
        )
    assert repo.calls == []


@pytest.mark.parametrize("bad_at", ["", "   ", None, 123])
def test_set_publish_state_rejects_malformed_published_at_no_write(bad_at):
    svc, repo = _service()
    with pytest.raises(ConfigFieldsCrudError):
        svc.set_publish_state(_TENANT, published_version=1, published_at=bad_at)
    assert repo.calls == []


# ── Publish service: persistence failure after a live artifact write is non-fatal ─────


def test_publish_still_succeeds_and_warns_when_state_persistence_fails(
    monkeypatch, caplog
):
    from sam.members.domain.application_publish import PUBLIC_API_BASE_ENV_VAR
    from sam.tests import test_published_form_submit_round3_bug_condition as r3

    class _FailingWriter:
        def record_publish(self, tenant_id, *, published_version, published_at):
            raise RuntimeError("boom")

    monkeypatch.setenv(PUBLIC_API_BASE_ENV_VAR, "https://api.test.example")
    store = r3._FakeFieldsStore()
    svc = r3._build_publish_service(store)
    svc._publish_state_writer = _FailingWriter()

    with caplog.at_level("WARNING"):
        result = svc.publish(r3._TENANT)

    # The artifact is live, so the publish is reported as a success (not a 500)…
    assert result["success"] is True and result["published_version"] == 1
    # …nothing was persisted, and the failure was logged without leaking the exception message.
    assert "published_version" not in store.row
    assert any("publish state not persisted" in r.getMessage() for r in caplog.records)
    assert not any("boom" in r.getMessage() for r in caplog.records)


# ── Read side: the persisted state is surfaced (staff GET -> `everPublished`, public -> version) ──


def test_reader_surfaces_published_state_from_the_stored_row_and_empty_when_absent():
    from services import projection_schema as schema
    from sam.members.repository.projection_config_reader import MembersProjectionReader
    from sam.tests import test_published_form_submit_round3_bug_condition as r3

    table = r3._FakeTable()
    reader = MembersProjectionReader(table=table)
    assert reader.get_published_state(_TENANT) == {}  # never published / no row

    table.put(
        {
            schema.PARTITION_KEY_ATTR: _TENANT,
            schema.SORT_KEY_ATTR: schema.build_sort_key(schema.RECORD_TYPE_CONFIG, "fields"),
            "slug": "h-dcn-aanmelden",
            "published_version": 3,
            "published_at": "2026-01-01T00:00:00+00:00",
            schema.VERSION_ATTR: 5,
        }
    )
    # The reader caches the partition per instance, so read through a fresh one.
    reader = MembersProjectionReader(table=table)
    assert reader.get_published_state(_TENANT) == {
        "published_version": 3,
        "published_at": "2026-01-01T00:00:00+00:00",
    }


def test_field_config_reads_carry_published_state_but_public_omits_published_at():
    from services import projection_schema as schema
    from sam.members.handler import app
    from sam.members.repository.projection_config_reader import MembersProjectionReader
    from sam.tests import test_published_form_submit_round3_bug_condition as r3

    table = r3._FakeTable()
    table.put(
        {
            schema.PARTITION_KEY_ATTR: _TENANT,
            schema.SORT_KEY_ATTR: schema.build_sort_key(schema.RECORD_TYPE_CONFIG, "fields"),
            "published_version": 2,
            "published_at": "2026-01-02T00:00:00+00:00",
            schema.VERSION_ATTR: 1,
        }
    )
    with r3._production_service_over(table) as svc:
        staff = svc.get_field_config(_TENANT)
        public = svc.get_public_field_config(_TENANT)

    assert staff["published_version"] == 2
    assert staff["published_at"] == "2026-01-02T00:00:00+00:00"
    assert public["published_version"] == 2
    assert "published_at" not in public
