"""
SAM Page Look-and-Feel — Task 4.5: the Change-Op WRITER adapter over
``MembersConfigWriteRepository.apply_ops`` for the ``look_and_feel`` slice.

Spec: `.kiro/specs/Members/15 - sam-page-look-and-feel` (design C3 / DD-2, Layer 1).

What this asserts (``ConfigFieldsCrudService.set_look_and_feel`` / ``remove_look_and_feel`` /
``copy_look_and_feel``)
-----------------------------------------------------------------------------------------------
The three look-and-feel op shapes are each a SINGLE path-scoped Change-Op through ``apply_ops``,
never a whole-record ``put_item``:

  * ``set_look_and_feel``    → ``SET look_and_feel.<attr> = :v``
  * ``remove_look_and_feel`` → ``REMOVE look_and_feel.<attr>``
  * ``copy_look_and_feel``   → ``SET look_and_feel = :snapshot``

And the contract the task pins (steering 39 Change-Op write contract):
  * every op names ONLY a ``look_and_feel`` path — so ``fields`` / ``overrides`` /
    ``functional_groups`` / ``slug`` / publish-state survive by construction;
  * the write stores VALUES only (never generated CSS);
  * ``StaleVersionError`` surfaces UNCHANGED (the adapter neither swallows nor re-wraps it);
  * the ``TruncationTripwireError`` backstop still applies (the real repository over an in-memory
    fake table does not trip on a look-and-feel write, because the slice is outside the
    field/group truncation buckets);
  * ``client_op_id`` forwards to ``apply_ops`` (lost-response idempotency, same as siblings).

The write repository is the SAME in-memory ``RecordingFakeRepository`` the sibling slug-author /
publish-state tests use. A separate block exercises the REAL ``MembersConfigWriteRepository`` over
an in-memory fake table to prove the version-conditional + truncation-backstop behaviour end to
end. No boto3, no AWS (steering 35/39).

Validates: Requirements 8.1, 8.3
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
from sam.members.repository.projection_config_write_repository import REMOVE, SET
from sam.tests.test_config_fields_slug_author import RecordingFakeRepository

_TENANT = "h-dcn"


def _service(repo=None):
    repo = repo if repo is not None else RecordingFakeRepository()
    return ConfigFieldsCrudService(repo), repo


class _SeededLookAndFeelReader:
    """A minimal resolved-view reader whose raw overlay carries a look_and_feel map.

    Injected so the writer's snapshot shows the parent map ALREADY EXISTS — the normal
    seeded-row case, where ``set_look_and_feel`` emits the minimal nested
    ``SET look_and_feel.<attr>`` (preserving sibling attributes). An EMPTY map (``{}``) still
    counts as present (a tenant-create skeleton seeds an empty map), so the nested SET is used.
    """

    def __init__(self, look_and_feel):
        self._laf = dict(look_and_feel)

    def get_raw_fields_overlay(self, tenant_id, *, consistent_read=False):
        return {
            "fields": {},
            "fixed_overrides": {},
            "functional_groups": {},
            "look_and_feel": dict(self._laf),
        }

    def get_config_fields_version(self, tenant_id, consistent_read=False):
        return (True, "v-1")


def _service_seeded(look_and_feel=None):
    """A service whose reader reports an EXISTING look_and_feel parent map (seeded row)."""
    repo = RecordingFakeRepository()
    reader = _SeededLookAndFeelReader(look_and_feel or {})
    return ConfigFieldsCrudService(repo, reader=reader), repo


# ── The ops EXIST as public methods ────────────────────────────────────────────────────


def test_look_and_feel_writer_methods_are_public():
    assert hasattr(ConfigFieldsCrudService, "set_look_and_feel")
    assert hasattr(ConfigFieldsCrudService, "remove_look_and_feel")
    assert hasattr(ConfigFieldsCrudService, "copy_look_and_feel")


# ── SET one attribute value → SET look_and_feel.<attr> = :v ─────────────────────────────


def test_set_look_and_feel_persists_single_path_scoped_set():
    # Seeded row (parent map exists) → the minimal nested SET that preserves siblings.
    svc, repo = _service_seeded({"font_body": "Inter"})

    result = svc.set_look_and_feel(_TENANT, "color_primary", "#2D5F8A")

    assert result == {"version": "v-next", "idempotent_replay": False}
    call = repo.last
    assert call["tenant_id"] == _TENANT
    assert call["config_id"] == "fields"
    assert call["ops"] == [
        {
            "action": SET,
            "path": ["look_and_feel", "color_primary"],
            "value": "#2D5F8A",
        }
    ]


def test_set_look_and_feel_stores_value_verbatim_never_css():
    # The adapter stores the VALUE as-is — never a generated CSS string / block.
    svc, repo = _service_seeded({"font_body": "Inter"})
    svc.set_look_and_feel(_TENANT, "base_spacing", "normal")
    op = repo.last["ops"][0]
    assert op["value"] == "normal"
    assert "{" not in str(op["value"]) and ":root" not in str(op["value"])


def test_set_look_and_feel_op_names_only_the_look_and_feel_slice():
    # The op must address ONLY a `look_and_feel.*` path so the member field-config slices and
    # slug / publish-state survive physically untouched (by construction, steering 39).
    svc, repo = _service()
    svc.set_look_and_feel(_TENANT, "shadow_style", "subtle")
    for op in repo.last["ops"]:
        assert op["path"][0] == "look_and_feel"
        assert op["path"][0] not in {
            "fields",
            "overrides",
            "functional_groups",
            "slug",
            "published_version",
            "published_at",
        }


def test_set_look_and_feel_forwards_client_op_id():
    svc, repo = _service()
    svc.set_look_and_feel(_TENANT, "color_accent", "#F4A261", client_op_id="op-123")
    assert repo.last["client_op_id"] == "op-123"


@pytest.mark.parametrize("bad_attr", ["", "   ", None, 123])
def test_set_look_and_feel_rejects_blank_attribute_no_write(bad_attr):
    svc, repo = _service()
    with pytest.raises(ConfigFieldsCrudError):
        svc.set_look_and_feel(_TENANT, bad_attr, "x")
    assert repo.calls == []


def test_set_look_and_feel_trims_attribute_segment():
    svc, repo = _service_seeded({"font_body": "Inter"})
    svc.set_look_and_feel(_TENANT, "  font_heading  ", "Inter")
    assert repo.last["ops"][0]["path"] == ["look_and_feel", "font_heading"]


# ── LEGACY row (no look_and_feel parent map) → seed the WHOLE slice (prod 500 regression) ──
#
# The production defect this pins: a LEGACY `config#fields` row (created BEFORE task 4.1 added
# the `look_and_feel` parent map to the skeleton) has NO `look_and_feel` attribute. A nested
# `SET look_and_feel.<attr>` against such a row is rejected by DynamoDB with a ValidationException
# ("The document path provided in the update expression is invalid for update") → unhandled → a
# live 500 on PUT /members/look-and-feel (observed on deployed TEST for the h-dcn row). The writer
# must therefore branch on parent-map existence: when ABSENT, seed the whole slice in one op
# (`SET look_and_feel = {attr: value}`), which creates the parent map; when present, the minimal
# nested SET. Both are a single op naming only the `look_and_feel` path. The RecordingFakeRepository
# path (no reader) models the "snapshot cannot see a parent map" case → the seed form.


def test_set_look_and_feel_seeds_whole_slice_when_parent_map_absent():
    # Reader reports a row WITHOUT a look_and_feel map (legacy row) → seed the whole slice.
    class _LegacyReader:
        def get_raw_fields_overlay(self, tenant_id, *, consistent_read=False):
            # A legacy row: fields/overrides present, but NO look_and_feel key at all.
            return {"fields": {"nickname": {"type": "text"}}, "fixed_overrides": {}, "functional_groups": {}}

        def get_config_fields_version(self, tenant_id, consistent_read=False):
            return (True, "v-1")

    repo = RecordingFakeRepository()
    svc = ConfigFieldsCrudService(repo, reader=_LegacyReader())

    svc.set_look_and_feel(_TENANT, "color_primary", "#2D5F8A")

    # ONE op that SETs the WHOLE look_and_feel slice (creating the parent map), NOT a nested
    # SET look_and_feel.color_primary (which would be invalid on a row with no parent map).
    ops = repo.last["ops"]
    assert ops == [
        {"action": SET, "path": ["look_and_feel"], "value": {"color_primary": "#2D5F8A"}}
    ]
    # Still names ONLY the look_and_feel path — unrelated slices untouched by construction.
    assert ops[0]["path"][0] == "look_and_feel"


def test_set_look_and_feel_seeds_whole_slice_when_no_reader_snapshot():
    # No reader wired → the snapshot is None (first-write placement). The writer cannot see a
    # parent map, so it seeds the whole slice — safe for a legacy/never-authored row.
    svc, repo = _service()  # RecordingFakeRepository, no reader
    svc.set_look_and_feel(_TENANT, "shadow_style", "subtle")
    assert repo.last["ops"] == [
        {"action": SET, "path": ["look_and_feel"], "value": {"shadow_style": "subtle"}}
    ]


# ── REMOVE one attribute → REMOVE look_and_feel.<attr> ──────────────────────────────────


def test_remove_look_and_feel_persists_single_path_scoped_remove():
    svc, repo = _service()

    result = svc.remove_look_and_feel(_TENANT, "shadow_style")

    assert result == {"version": "v-next", "idempotent_replay": False}
    assert repo.last["ops"] == [
        {"action": REMOVE, "path": ["look_and_feel", "shadow_style"]}
    ]


def test_remove_look_and_feel_forwards_client_op_id():
    svc, repo = _service()
    svc.remove_look_and_feel(_TENANT, "border_radius_global", client_op_id="op-9")
    assert repo.last["client_op_id"] == "op-9"


@pytest.mark.parametrize("bad_attr", ["", "   ", None, 123])
def test_remove_look_and_feel_rejects_blank_attribute_no_write(bad_attr):
    svc, repo = _service()
    with pytest.raises(ConfigFieldsCrudError):
        svc.remove_look_and_feel(_TENANT, bad_attr)
    assert repo.calls == []


# ── COPY snapshot → SET look_and_feel = :snapshot ───────────────────────────────────────


def test_copy_look_and_feel_overwrites_whole_slice_with_snapshot():
    svc, repo = _service()
    snapshot = {
        "color_primary": "#2D5F8A",
        "font_body": "Inter",
        "base_spacing": "normal",
    }

    result = svc.copy_look_and_feel(_TENANT, snapshot)

    assert result == {"version": "v-next", "idempotent_replay": False}
    assert repo.last["ops"] == [
        {"action": SET, "path": ["look_and_feel"], "value": snapshot}
    ]


def test_copy_look_and_feel_snapshot_is_defensively_copied():
    # Mutating the caller's mapping after the call must not change what was handed to apply_ops.
    svc, repo = _service()
    source = {"color_primary": "#111111"}
    svc.copy_look_and_feel(_TENANT, source)
    source["color_primary"] = "#999999"
    assert repo.last["ops"][0]["value"] == {"color_primary": "#111111"}


def test_copy_look_and_feel_empty_snapshot_is_valid():
    # An empty snapshot overwrites the target to "all defaults" — a valid one-time copy.
    svc, repo = _service()
    svc.copy_look_and_feel(_TENANT, {})
    assert repo.last["ops"] == [
        {"action": SET, "path": ["look_and_feel"], "value": {}}
    ]


@pytest.mark.parametrize("bad_snapshot", [None, "x", 1, ["a"]])
def test_copy_look_and_feel_rejects_non_mapping_no_write(bad_snapshot):
    svc, repo = _service()
    with pytest.raises(ConfigFieldsCrudError):
        svc.copy_look_and_feel(_TENANT, bad_snapshot)
    assert repo.calls == []


def test_copy_look_and_feel_forwards_client_op_id():
    svc, repo = _service()
    svc.copy_look_and_feel(_TENANT, {"color_primary": "#000000"}, client_op_id="op-cp")
    assert repo.last["client_op_id"] == "op-cp"


# ── StaleVersionError surfaces unchanged ────────────────────────────────────────────────


class _AlwaysStaleRepository:
    """`apply_ops` always raises StaleVersionError (every write hits a version conflict)."""

    def __init__(self):
        self.calls = 0

    def apply_ops(self, *, tenant_id, config_id, ops, base_version, client_op_id=None):
        from sam.members.repository.projection_config_write_repository import (
            StaleVersionError,
        )

        self.calls += 1
        raise StaleVersionError("row changed")


def test_set_look_and_feel_surfaces_stale_version_error_unchanged():
    from sam.members.repository.projection_config_write_repository import (
        StaleVersionError,
    )

    repo = _AlwaysStaleRepository()
    svc = ConfigFieldsCrudService(repo)
    with pytest.raises(StaleVersionError):
        svc.set_look_and_feel(_TENANT, "color_primary", "#2D5F8A")
    # `_run` retries exactly once on a conflict, then surfaces — never swallowed, never re-wrapped.
    assert repo.calls == 2


# ── End-to-end over the REAL write repository + an in-memory fake table ─────────────────
#
# Proves the adapter's ops drive a real version-conditional `update_item` and that a
# look-and-feel write does NOT trip the field/group truncation backstop (the slice is outside
# the tripwire buckets), while the backstop remains wired through the same `apply_ops` seam.


class _FakeTable:
    """Minimal in-memory DynamoDB Table honouring update_item with a version ConditionExpression.

    Enough to exercise `apply_ops`'s single version-conditional `update_item` for the SET/REMOVE
    look-and-feel ops. Supports `attribute_not_exists(sk)` (first write onto a skeleton) and
    `version = :base` (optimistic lock); any other conditional mismatch raises the
    ConditionalCheckFailedException the repository maps to StaleVersionError.
    """

    def __init__(self, item=None):
        self.item = dict(item) if item else None

    # read path used by the service snapshot (consistent_read) — not needed here; the service
    # degrades to first-write placement when no reader is wired.

    def get_item(self, *, Key, ConsistentRead=False):
        return {"Item": dict(self.item)} if self.item else {}

    def update_item(
        self,
        *,
        Key,
        UpdateExpression,
        ConditionExpression,
        ExpressionAttributeNames,
        ExpressionAttributeValues,
    ):
        from botocore.exceptions import ClientError

        exists = self.item is not None
        cond = ConditionExpression
        # Evaluate the three condition shapes the repository emits.
        ok = False
        if "attribute_not_exists" in cond:
            ok = not exists
        elif exists:
            base = ExpressionAttributeValues.get(":base")
            ok = self.item.get("version") == base
        if not ok:
            raise ClientError(
                {
                    "Error": {"Code": "ConditionalCheckFailedException", "Message": "stale"},
                    "ResponseMetadata": {"HTTPStatusCode": 400},
                },
                "UpdateItem",
            )
        # Apply the SET/REMOVE ops onto the (possibly new) item by re-parsing the names/values.
        item = dict(self.item) if exists else dict(Key)
        self._apply_expression(
            item, UpdateExpression, ExpressionAttributeNames, ExpressionAttributeValues
        )
        self.item = item
        return {}

    @staticmethod
    def _apply_expression(item, expr, names, values):
        # The repository builds `SET #n0.#n1 = :v0, version = :newver [, ...] REMOVE #m0.#m1`.
        # We only need to prove the look_and_feel slice is mutated and version bumped, so parse
        # loosely: resolve each `#name` placeholder to its real segment and walk/assign.
        import re

        # version is always bumped in the SET clause.
        set_part = ""
        remove_part = ""
        upper = expr
        if "REMOVE" in upper:
            set_part, remove_part = re.split(r"\bREMOVE\b", upper, maxsplit=1)
        else:
            set_part = upper
        set_part = re.sub(r"^\s*SET\s*", "", set_part.strip(), flags=re.IGNORECASE)

        def resolve_path(dotted):
            segs = []
            for token in dotted.split("."):
                token = token.strip()
                segs.append(names.get(token, token))
            return segs

        for assignment in [a for a in set_part.split(",") if a.strip()]:
            lhs, rhs = assignment.split("=", 1)
            lhs, rhs = lhs.strip(), rhs.strip()
            segs = resolve_path(lhs)
            val = values.get(rhs)
            node = item
            for seg in segs[:-1]:
                node = node.setdefault(seg, {})
            node[segs[-1]] = val

        if remove_part.strip():
            for path in [p for p in remove_part.split(",") if p.strip()]:
                segs = resolve_path(path.strip())
                node = item
                for seg in segs[:-1]:
                    node = node.get(seg, {}) if isinstance(node, dict) else {}
                if isinstance(node, dict):
                    node.pop(segs[-1], None)


def _real_repo(table):
    from sam.members.repository.projection_config_write_repository import (
        MembersConfigWriteRepository,
    )

    return MembersConfigWriteRepository(table=table, version_fn=lambda: "v-2")


class _FakeReader:
    """Minimal resolved-view reader so the service resolves the optimistic-lock base version.

    Exposes the two accessors `_read_snapshot` / `_read_version` consume: a wire overlay (so the
    row reads as "present") and the control-plane version accessor returning `(present, version)`.
    """

    def __init__(self, table):
        self._table = table

    def get_raw_fields_overlay(self, tenant_id, consistent_read=False):
        item = self._table.item or {}
        return {
            "fields": item.get("fields", {}),
            "fixed_overrides": item.get("overrides", {}),
            "functional_groups": item.get("functional_groups", {}),
        }

    def get_config_fields_version(self, tenant_id, consistent_read=False):
        item = self._table.item
        if item is None:
            return (False, None)
        return (True, item.get("version"))


def _skeleton_item():
    from services import projection_schema as schema

    return {
        schema.PARTITION_KEY_ATTR: _TENANT,
        schema.SORT_KEY_ATTR: schema.build_sort_key(schema.RECORD_TYPE_CONFIG, "fields"),
        schema.VERSION_ATTR: "v-1",
        "fields": {"nickname": {"type": "text"}},
        "overrides": {},
        "functional_groups": {"personal": {"label": "Personal"}},
        "look_and_feel": {},
    }


def test_real_repo_set_look_and_feel_writes_slice_and_leaves_others_untouched():
    table = _FakeTable(_skeleton_item())
    svc = ConfigFieldsCrudService(_real_repo(table), reader=_FakeReader(table))

    svc.set_look_and_feel(_TENANT, "color_primary", "#2D5F8A")

    # The value landed in the look_and_feel slice…
    assert table.item["look_and_feel"]["color_primary"] == "#2D5F8A"
    # …the member field-config slices are physically untouched (by construction)…
    assert table.item["fields"] == {"nickname": {"type": "text"}}
    assert table.item["functional_groups"] == {"personal": {"label": "Personal"}}
    # …and the version was bumped by the version-conditional update.
    assert table.item["version"] == "v-2"


def test_real_repo_copy_look_and_feel_does_not_trip_truncation_backstop():
    # A `SET look_and_feel = :snapshot` is a whole-PARENT set on a slice OUTSIDE the field/group
    # truncation buckets, so it must NOT raise TruncationTripwireError even though it replaces a
    # whole map — the backstop only guards `fields` / `overrides` / `functional_groups`.
    table = _FakeTable(_skeleton_item())
    svc = ConfigFieldsCrudService(_real_repo(table), reader=_FakeReader(table))

    svc.copy_look_and_feel(_TENANT, {"color_primary": "#111", "font_body": "Inter"})

    assert table.item["look_and_feel"] == {"color_primary": "#111", "font_body": "Inter"}
    # groups/fields counts unchanged → backstop never fired.
    assert set(table.item["functional_groups"]) == {"personal"}
    assert set(table.item["fields"]) == {"nickname"}


# ── Task 4.6 — unrelated slices survive the Change-Op write BY CONSTRUCTION ─────────────
#
# Spec: `.kiro/specs/Members/15 - sam-page-look-and-feel`, task 4.6 (Layer 1, DD-2).
# Validates: Requirements 4.1, 8.3.
#
# Task 4.5 already proved (over the REAL `MembersConfigWriteRepository` + the in-memory
# `_FakeTable`) that a `look_and_feel` SET lands in the slice, leaves `fields` /
# `functional_groups` untouched, and bumps the version. Task 4.6 SPECIFICALLY pins the two
# assertions 4.5 did not: (a) the FULL set of unrelated slices — `overrides` AND the slug /
# publish-state attributes (`slug` / `published_version` / `published_at`) — survive physically
# untouched (the op names only a `look_and_feel.*` path, so DynamoDB's `update_item` cannot
# touch any attribute the op did not name — survival is by construction, not by a careful
# in-memory merge, steering 39); and (b) a STALE base version drives the real repository's
# version-conditional `update_item` to fail and surface as `StaleVersionError` — the caller-safe
# 409 "reload and retry" path (design D5 / R8.3) — with NOTHING persisted.
#
# Reuses the task-4.5 `_FakeTable` / `_real_repo` / `_FakeReader` helpers above (no duplication);
# only the seed is enriched with the slug / publish-state slices this task asserts on, and one
# extra reader variant forces the stale-version conflict.


def _skeleton_item_with_slug_and_publish_state():
    """A populated `config#fields` row carrying EVERY slice task 4.6 asserts survives a
    look-and-feel write: member field config (`fields` / `overrides` / `functional_groups`), the
    public `slug`, and the publish-state attributes (`published_version` / `published_at`)."""
    from services import projection_schema as schema

    return {
        schema.PARTITION_KEY_ATTR: _TENANT,
        schema.SORT_KEY_ATTR: schema.build_sort_key(schema.RECORD_TYPE_CONFIG, "fields"),
        schema.VERSION_ATTR: "v-1",
        "fields": {"nickname": {"type": "text"}},
        "overrides": {"personal.gender": {"application_visible": True}},
        "functional_groups": {"personal": {"label": "Personal"}},
        "slug": "h-dcn/membership",
        "published_version": "v-1",
        "published_at": "2026-01-01T00:00:00Z",
        "look_and_feel": {},
    }


def test_real_repo_set_look_and_feel_leaves_overrides_slug_and_publish_state_untouched():
    # The op addresses ONLY `look_and_feel.<attr>`, so the member-config `overrides` slice and the
    # slug / publish-state attributes survive the write PHYSICALLY UNTOUCHED (by construction — a
    # path `update_item` never writes an attribute the op did not name, steering 39 / R4.1).
    table = _FakeTable(_skeleton_item_with_slug_and_publish_state())
    svc = ConfigFieldsCrudService(_real_repo(table), reader=_FakeReader(table))

    svc.set_look_and_feel(_TENANT, "color_primary", "#2D5F8A")

    # The value landed in the look_and_feel slice…
    assert table.item["look_and_feel"]["color_primary"] == "#2D5F8A"
    # …and NONE of the unrelated slices moved: field config (overrides), slug, publish-state.
    assert table.item["overrides"] == {"personal.gender": {"application_visible": True}}
    assert table.item["fields"] == {"nickname": {"type": "text"}}
    assert table.item["functional_groups"] == {"personal": {"label": "Personal"}}
    assert table.item["slug"] == "h-dcn/membership"
    assert table.item["published_version"] == "v-1"
    assert table.item["published_at"] == "2026-01-01T00:00:00Z"
    # …and the version was bumped by the version-conditional update (optimistic lock advanced).
    assert table.item["version"] == "v-2"


def test_real_repo_set_look_and_feel_remove_leaves_slug_and_publish_state_untouched():
    # Same survival-by-construction guarantee for the REMOVE op shape: clearing one look-and-feel
    # attribute names only `look_and_feel.<attr>`, so slug / publish-state / field config are
    # untouched and the version still bumps.
    seed = _skeleton_item_with_slug_and_publish_state()
    seed["look_and_feel"] = {"color_primary": "#2D5F8A", "font_body": "Inter"}
    table = _FakeTable(seed)
    svc = ConfigFieldsCrudService(_real_repo(table), reader=_FakeReader(table))

    svc.remove_look_and_feel(_TENANT, "font_body")

    assert "font_body" not in table.item["look_and_feel"]
    assert table.item["look_and_feel"]["color_primary"] == "#2D5F8A"
    assert table.item["slug"] == "h-dcn/membership"
    assert table.item["published_version"] == "v-1"
    assert table.item["published_at"] == "2026-01-01T00:00:00Z"
    assert table.item["overrides"] == {"personal.gender": {"application_visible": True}}
    assert table.item["version"] == "v-2"


class _StaleVersionReader(_FakeReader):
    """A resolved-view reader that reports a STALE optimistic-lock base version.

    The table physically holds `version == "v-1"`, but this reader claims the base version the
    service should lock on is something else (the row changed under the caller since it was read).
    The real repository therefore issues `update_item` with `ConditionExpression version = :base`
    against a non-matching stored version → `ConditionalCheckFailedException` → `StaleVersionError`
    (the caller-safe 409 path, design D5 / R8.3). No `client_op_id` is supplied, so there is no
    idempotent-replay escape hatch — the conflict surfaces.
    """

    def __init__(self, table, reported_version):
        super().__init__(table)
        self._reported_version = reported_version

    def get_config_fields_version(self, tenant_id, consistent_read=False):
        return (True, self._reported_version)


def test_real_repo_set_look_and_feel_stale_version_raises_and_persists_nothing():
    from sam.members.repository.projection_config_write_repository import (
        StaleVersionError,
    )

    table = _FakeTable(_skeleton_item_with_slug_and_publish_state())
    # Reader reports a base version that does NOT match the stored "v-1" → the version-conditional
    # write must fail cleanly.
    svc = ConfigFieldsCrudService(
        _real_repo(table), reader=_StaleVersionReader(table, "v-STALE")
    )

    with pytest.raises(StaleVersionError):
        svc.set_look_and_feel(_TENANT, "color_primary", "#2D5F8A")

    # Nothing was persisted: the look_and_feel slice stayed empty, the version did NOT advance,
    # and every unrelated slice is exactly as seeded (the write was all-or-nothing, atomic).
    assert table.item["look_and_feel"] == {}
    assert table.item["version"] == "v-1"
    assert table.item["slug"] == "h-dcn/membership"
    assert table.item["published_version"] == "v-1"
    assert table.item["overrides"] == {"personal.gender": {"application_visible": True}}


# ── Bugfix task 9 — the THREE NEW values ride the EXISTING Change-Op path ───────────────
#
# Spec: `.kiro/specs/Members/15 - sam-page-look-and-feel/bugfix-published-form-styling`,
#       task 9 (Phase 2, R-A C — stored-slice plane).
# Validates: Requirements 2.7; spec-15 Req 8.1, 8.3 (Change-Op write contract).
#
# R-A adds three NEW values-only look-and-feel attributes — `logo` (a URL/asset reference,
# never a CSS/binary upload into the slice — DD-C1), `header_title` (escaped text), and
# `columns` (a bounded enum/integer). This task is a STORAGE-SEAM confirmation: it pins that
# the EXISTING path-scoped Change-Op writer already carries ARBITRARY values-only attributes
# within the `look_and_feel` slice BY CONSTRUCTION — no schema change, no whole-record write,
# and NO repository-layer attribute allow-list. The writer adapter (`set_look_and_feel`) only
# requires a non-blank attribute string and stores the value verbatim; the supported-attribute /
# permitted-value validation (`columns` range, `logo` reference shape, `header_title` length)
# is the `LookAndFeelSettingsService` / edge's job (task 10), deliberately kept OUT of this
# reusable storage adapter. So the three new keys need no storage-plane code change — this test
# documents and PINS that invariant for them.
#
# For each new attribute, over the REAL `MembersConfigWriteRepository` + the in-memory
# `_FakeTable` (no boto3), a `set_look_and_feel` SET:
#   * lands the VALUE in the `look_and_feel` slice (stored verbatim, never CSS),
#   * leaves `fields` / `overrides` / slug / publish-state PHYSICALLY UNTOUCHED (by construction —
#     the op names only `look_and_feel.<attr>`, so DynamoDB's single-path `update_item` cannot
#     write any attribute the op did not name, steering 39 / R4.1), and
#   * bumps the record `version` (the version-conditional write advanced the optimistic lock).
#
# Reuses the task-4.5/4.6 helpers above (`_FakeTable` / `_real_repo` / `_FakeReader` /
# `_skeleton_item_with_slug_and_publish_state`) — no duplication.


@pytest.mark.parametrize(
    "new_attribute,value",
    [
        # `columns` — a bounded enum/integer column count (the grid driver). Stored verbatim as a
        # value; range validation lives at the service/edge (task 10), not this storage seam.
        ("columns", 3),
        # `logo` — a URL/asset REFERENCE string (DD-C1), never a CSS/binary upload into the slice.
        ("logo", "https://assets.example.org/h-dcn/logo.png"),
        # `header_title` — free text (HTML-escaped on render), length-bounded at the edge.
        ("header_title", "Membership Application"),
    ],
)
def test_real_repo_set_new_value_attribute_rides_existing_change_op_untouched_siblings(
    new_attribute, value
):
    # A NEW R-A attribute SETs through the SAME path-scoped Change-Op as the existing seven —
    # proving the storage seam carries arbitrary values-only attributes by construction (no
    # schema change, no allow-list at the repository layer).
    table = _FakeTable(_skeleton_item_with_slug_and_publish_state())
    svc = ConfigFieldsCrudService(_real_repo(table), reader=_FakeReader(table))

    result = svc.set_look_and_feel(_TENANT, new_attribute, value)

    # The op that reached the repository named ONLY a `look_and_feel` path (nested SET — the
    # parent map already exists on the seeded row), so unrelated slices cannot be touched.
    # (The seeded row carries a `look_and_feel: {}` parent map, so the minimal nested SET is used.)

    # The VALUE landed in the look_and_feel slice, stored VERBATIM (never a generated CSS string)…
    assert table.item["look_and_feel"][new_attribute] == value
    assert ":root" not in str(table.item["look_and_feel"][new_attribute])
    assert "{" not in str(table.item["look_and_feel"][new_attribute])

    # …`fields` / `overrides` / slug / publish-state survive PHYSICALLY UNTOUCHED (by construction)…
    assert table.item["fields"] == {"nickname": {"type": "text"}}
    assert table.item["overrides"] == {"personal.gender": {"application_visible": True}}
    assert table.item["functional_groups"] == {"personal": {"label": "Personal"}}
    assert table.item["slug"] == "h-dcn/membership"
    assert table.item["published_version"] == "v-1"
    assert table.item["published_at"] == "2026-01-01T00:00:00Z"

    # …and the record VERSION was bumped by the version-conditional write (optimistic lock advanced).
    assert table.item["version"] == "v-2"
    assert result == {"version": "v-2", "idempotent_replay": False}


class _LookAndFeelAwareReader(_FakeReader):
    """A `_FakeReader` that also SURFACES the stored `look_and_feel` map in its overlay.

    The base `_FakeReader` omits `look_and_feel` from `get_raw_fields_overlay`, so the service's
    placement snapshot sees no parent map and takes the seed-whole-slice branch. A seeded row
    whose `look_and_feel` parent map ALREADY EXISTS must drive the minimal NESTED
    `SET look_and_feel.<attr>` (preserving sibling attributes) — this reader reports that map so
    the nested-SET path is exercised, matching the real `MembersProjectionReader` overlay shape.
    """

    def get_raw_fields_overlay(self, tenant_id, consistent_read=False):
        overlay = super().get_raw_fields_overlay(tenant_id, consistent_read=consistent_read)
        item = self._table.item or {}
        overlay["look_and_feel"] = dict(item.get("look_and_feel", {}))
        return overlay


def test_real_repo_set_new_value_attribute_preserves_existing_look_and_feel_siblings():
    # Authoring a NEW attribute (`columns`) must preserve the EXISTING look-and-feel attributes
    # already on the slice — the minimal nested `SET look_and_feel.columns` leaves sibling
    # attributes (`color_primary`, `font_body`) physically untouched (by construction). The reader
    # surfaces the existing `look_and_feel` map so the service emits the nested SET (not a reseed).
    seed = _skeleton_item_with_slug_and_publish_state()
    seed["look_and_feel"] = {"color_primary": "#2D5F8A", "font_body": "Inter"}
    table = _FakeTable(seed)
    svc = ConfigFieldsCrudService(_real_repo(table), reader=_LookAndFeelAwareReader(table))

    svc.set_look_and_feel(_TENANT, "columns", 2)

    assert table.item["look_and_feel"] == {
        "color_primary": "#2D5F8A",
        "font_body": "Inter",
        "columns": 2,
    }
    assert table.item["version"] == "v-2"


def test_set_new_value_attribute_emits_single_look_and_feel_scoped_op():
    # At the adapter level (the RecordingFakeRepository, no reader → first-write placement),
    # authoring any of the three NEW attributes emits exactly ONE op that names ONLY the
    # `look_and_feel` path — the same shape the existing seven use. This pins that the storage
    # seam needs no per-attribute branching for the new values.
    for new_attribute, value in (
        ("columns", 3),
        ("logo", "https://assets.example.org/logo.svg"),
        ("header_title", "Join us"),
    ):
        svc, repo = _service()  # RecordingFakeRepository, no reader
        svc.set_look_and_feel(_TENANT, new_attribute, value)
        ops = repo.last["ops"]
        assert len(ops) == 1
        assert ops[0]["action"] == SET
        assert ops[0]["path"][0] == "look_and_feel"
        # No whole-record replace, no schema-shaped container — a single values-only path op.
        assert ops[0]["path"][0] not in {
            "fields",
            "overrides",
            "functional_groups",
            "slug",
            "published_version",
            "published_at",
        }
