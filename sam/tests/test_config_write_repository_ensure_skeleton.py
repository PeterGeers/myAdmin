"""
Spec 03 Task 2.0a — unit tests for the NEW-TENANT row-skeleton create primitive
(:meth:`MembersConfigWriteRepository.ensure_skeleton`).

``ensure_skeleton`` is the create-time half of design C6 (review Must-fix #1). A freshly created
tenant must get its ``config#fields`` row seeded with the parent-map skeleton
``{fields: {}, overrides: {}, functional_groups: {}}`` plus a seeded ``version`` BEFORE the first
Change-Op, because the Phase-2 path ``update_item`` requires those parent maps to exist (an
``if_not_exists``-in-the-same-op seed is rejected by DynamoDB as "document paths overlap"). The
migration (task 2.0) backfills the SAME skeleton onto legacy rows; this primitive seeds a brand-new
tenant.

What this asserts
-----------------
1. **A new tenant gets the FULL skeleton + a version** — ``ensure_skeleton`` creates the row with
   the three empty parent maps and a non-empty ``version`` stamp, and reports ``created=True``.
2. **Idempotent + NEVER overwrites a populated row** — a second call (or a call against an
   already-provisioned tenant that carries real fields / overrides / groups) is a no-op that leaves
   the stored row byte-for-byte untouched (conditional ``attribute_not_exists(sk)``), reporting
   ``created=False``.
3. **A first Change-Op (create-verb) succeeds onto the skeleton** — after seeding, the first
   ``apply_ops`` create (``base_version=None`` → ``attribute_not_exists(sk)`` ... which, because the
   skeleton row now EXISTS, is the legacy/first-versioned case) lands its entry while every untouched
   sibling map survives. This is the end-to-end proof that the skeleton unblocks the Change-Op path.

The blank-tenant guard (R5.5) is retained, matching :meth:`put_config` / :meth:`apply_ops`.

DynamoDB is faked in-memory with a ``ConditionalSkeletonTable`` that HONOURS the conditional
``put_item`` (``attribute_not_exists(sk)``) AND the condition-evaluating ``update_item`` (the three
version branches), so the seed → first-Change-Op round-trip is genuinely exercised over ONE store,
not mocked away.

**Validates: Requirements 1.5, 6.2**
"""

import os
import re
import sys

import pytest

# repo root + backend/src on sys.path (mirrors the sibling write-repo tests).
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)
_BACKEND_SRC = os.path.join(_REPO_ROOT, "backend", "src")
if _BACKEND_SRC not in sys.path:
    sys.path.insert(0, _BACKEND_SRC)

from botocore.exceptions import ClientError

from services import projection_schema as schema

from sam.members.repository.projection_config_write_repository import (
    FIELDS_SKELETON_PARENTS,
    SET,
    LEGACY_NO_VERSION,
    MembersConfigWriteRepository,
)

_TENANT_ID = "skeleton-tenant"
_FIELDS_SK = "config#fields"


# ---------------------------------------------------------------------------
# A condition-honouring fake table (conditional put_item + the three update branches)
# ---------------------------------------------------------------------------


def _conditional_check_failed(op_name: str) -> ClientError:
    """A real botocore ``ClientError`` with the ``ConditionalCheckFailedException`` code."""
    return ClientError(
        {
            "Error": {
                "Code": "ConditionalCheckFailedException",
                "Message": "The conditional request failed",
            }
        },
        op_name,
    )


class ConditionalSkeletonTable:
    """In-memory DynamoDB ``Table`` fake honouring the conditional ``put_item`` AND ``update_item``.

    Enough of DynamoDB's semantics to prove the expressions the repository builds are correct:
    - ``put_item`` with ``ConditionExpression="attribute_not_exists(#sk)"`` raises a
      ``ConditionalCheckFailedException`` ClientError when the row already exists (the IF-ABSENT
      skeleton create); a put with no condition is a plain upsert;
    - ``update_item`` evaluates the three version ConditionExpression shapes + applies the built
      SET/REMOVE expression (same evaluator as the apply_ops suite) so a first Change-Op onto the
      seeded skeleton genuinely lands.
    """

    def __init__(self):
        self.store: dict[tuple, dict] = {}
        self.put_items: list[dict] = []
        self.update_calls: list[dict] = []

    # -- helpers --------------------------------------------------------------

    def _key_tuple(self, key):
        return (key[schema.PARTITION_KEY_ATTR], key[schema.SORT_KEY_ATTR])

    def seed(self, item: dict):
        self.store[self._key_tuple(item)] = dict(item)

    # -- boto3-shaped surface -------------------------------------------------

    def get_item(self, Key=None, ConsistentRead=False):
        item = self.store.get(self._key_tuple(Key))
        return {"Item": dict(item)} if item else {}

    def put_item(self, Item=None, ConditionExpression=None, ExpressionAttributeNames=None):
        self.put_items.append(dict(Item))
        key = (Item[schema.PARTITION_KEY_ATTR], Item[schema.SORT_KEY_ATTR])
        if ConditionExpression is not None:
            names = ExpressionAttributeNames or {}
            m = re.fullmatch(r"attribute_not_exists\((#\w+)\)", ConditionExpression)
            assert m, f"unexpected put condition: {ConditionExpression!r}"
            segment = names[m.group(1)]
            assert segment == schema.SORT_KEY_ATTR
            if key in self.store:
                # The row already exists — the IF-ABSENT create must be rejected (no overwrite).
                raise _conditional_check_failed("PutItem")
        self.store[key] = dict(Item)
        return {}

    def update_item(
        self,
        Key=None,
        UpdateExpression=None,
        ConditionExpression=None,
        ExpressionAttributeNames=None,
        ExpressionAttributeValues=None,
    ):
        self.update_calls.append({"UpdateExpression": UpdateExpression})
        names = ExpressionAttributeNames or {}
        values = ExpressionAttributeValues or {}
        self._base = values.get(":base")
        key_tuple = self._key_tuple(Key)
        existing = self.store.get(key_tuple)
        if not self._condition_holds(ConditionExpression, names, existing):
            raise _conditional_check_failed("UpdateItem")
        item = dict(existing) if existing else dict(Key)
        self._apply_update(item, UpdateExpression, names, values)
        self.store[key_tuple] = item
        return {}

    # -- condition + update evaluation (mirrors the apply_ops suite's fake) ----

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
            path = self._resolve_path(path_expr.strip(), names)
            self._remove_nested(item, path)

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


def _make_repo(table, version="v-seed"):
    return MembersConfigWriteRepository(table=table, version_fn=lambda: version)


# ---------------------------------------------------------------------------
# 1. A new tenant gets the FULL skeleton + version
# ---------------------------------------------------------------------------


class TestNewTenantGetsSkeleton:
    def test_new_tenant_is_seeded_with_full_skeleton_and_version(self):
        """A never-authored tenant gets ``{fields,overrides,functional_groups}: {}`` + a version.

        Validates: Requirement 1.5
        """
        table = ConditionalSkeletonTable()
        repo = _make_repo(table, version="2026-01-01T00:00:00+00:00")

        result = repo.ensure_skeleton(_TENANT_ID)

        assert result == {"created": True, "version": "2026-01-01T00:00:00+00:00"}
        stored = table.store[(_TENANT_ID, _FIELDS_SK)]
        # The three parent maps all exist AND are empty (the C6 skeleton shape).
        for parent in FIELDS_SKELETON_PARENTS:
            assert stored[parent] == {}
        # The row carries the canonical key + a non-empty version stamp.
        assert stored[schema.PARTITION_KEY_ATTR] == _TENANT_ID
        assert stored[schema.SORT_KEY_ATTR] == _FIELDS_SK
        assert stored[schema.VERSION_ATTR] == "2026-01-01T00:00:00+00:00"
        assert table.put_items, "expected exactly one conditional put for the create"

    def test_skeleton_write_is_scoped_to_the_callers_tenant_partition(self):
        """The skeleton is written under the caller's own tenant partition only.

        Validates: Requirement 1.5
        """
        table = ConditionalSkeletonTable()
        repo = _make_repo(table)

        repo.ensure_skeleton("tenant-a")

        assert ("tenant-a", _FIELDS_SK) in table.store
        assert ("tenant-b", _FIELDS_SK) not in table.store


# ---------------------------------------------------------------------------
# 2. Idempotent + NEVER overwrites a populated row (conditional create)
# ---------------------------------------------------------------------------


class TestIdempotentNeverOverwrites:
    def test_second_call_is_an_idempotent_no_op(self):
        """Calling ensure_skeleton twice writes once; the second call reports created=False.

        Validates: Requirement 1.5
        """
        table = ConditionalSkeletonTable()
        repo = _make_repo(table, version="v-first")

        first = repo.ensure_skeleton(_TENANT_ID)
        before = dict(table.store[(_TENANT_ID, _FIELDS_SK)])
        second = repo.ensure_skeleton(_TENANT_ID)
        after = table.store[(_TENANT_ID, _FIELDS_SK)]

        assert first == {"created": True, "version": "v-first"}
        assert second == {"created": False, "version": None}
        # The stored row is byte-for-byte unchanged by the second call.
        assert after == before

    def test_populated_row_is_never_overwritten_or_truncated(self):
        """A tenant that ALREADY has real fields / overrides / groups is left fully intact.

        This is the safety guarantee: ensure_skeleton can never truncate a provisioned tenant's
        catalog back to the empty skeleton (conditional ``attribute_not_exists(sk)``).

        Validates: Requirement 1.5
        """
        table = ConditionalSkeletonTable()
        populated = {
            schema.PARTITION_KEY_ATTR: _TENANT_ID,
            schema.SORT_KEY_ATTR: _FIELDS_SK,
            schema.VERSION_ATTR: "v-real",
            "fields": {"nickname": {"key": "nickname", "type": "string"}},
            "overrides": {"personal.gender": {"label": "Gender"}},
            "functional_groups": {
                "personal": {"key": "personal", "order": 1},
                "membership": {"key": "membership", "order": 2},
            },
        }
        table.seed(populated)
        repo = _make_repo(table, version="v-would-clobber")

        result = repo.ensure_skeleton(_TENANT_ID)

        assert result == {"created": False, "version": None}
        # Every real attribute survives — nothing truncated, nothing version-bumped.
        assert table.store[(_TENANT_ID, _FIELDS_SK)] == populated

    def test_blank_tenant_rejected_before_any_write(self):
        """A blank tenant raises ValueError before any put (tenancy boundary R5.5)."""
        table = ConditionalSkeletonTable()
        repo = _make_repo(table)
        for blank in ("", None):
            with pytest.raises(ValueError):
                repo.ensure_skeleton(blank)
        assert table.put_items == []


# ---------------------------------------------------------------------------
# 3. A first Change-Op (create-verb) succeeds onto the seeded skeleton
# ---------------------------------------------------------------------------


class TestFirstChangeOpOntoSkeleton:
    def test_first_change_op_lands_on_the_seeded_skeleton(self):
        """ensure_skeleton → first apply_ops create: the entry lands, siblings survive.

        The end-to-end proof the skeleton unblocks the Phase-2 path. The seeded row carries a
        ``version`` (case i) so the first Change-Op optimistic-locks on the seeded version.

        Validates: Requirements 1.5, 6.2
        """
        table = ConditionalSkeletonTable()
        seed_repo = _make_repo(table, version="v-seed")
        seed_result = seed_repo.ensure_skeleton(_TENANT_ID)
        assert seed_result["created"] is True

        # A fresh create-verb op onto the now-existing skeleton (optimistic lock on the seeded
        # version). This is exactly what ConfigFieldsCrudService emits for a first field write.
        op_repo = _make_repo(table, version="v-after")
        entry = {"key": "shoe_size", "type": "number"}
        result = op_repo.apply_ops(
            _TENANT_ID,
            schema.CONFIG_ID_FIELDS,
            [{"action": SET, "path": ["fields", "shoe_size"], "value": entry}],
            base_version=seed_result["version"],
        )

        assert result == {"version": "v-after", "idempotent_replay": False}
        stored = table.store[(_TENANT_ID, _FIELDS_SK)]
        assert stored["fields"]["shoe_size"] == entry
        # Untouched sibling parent maps survive (structural no-truncation).
        assert stored["overrides"] == {}
        assert stored["functional_groups"] == {}
        assert stored[schema.VERSION_ATTR] == "v-after"

    def test_legacy_row_first_change_op_uses_the_no_version_branch(self):
        """A legacy skeleton (no version) takes a first Change-Op via LEGACY_NO_VERSION.

        Covers the belt branch: ensure_skeleton seeds a version, but a migration-era row might
        predate it — the first Change-Op still lands via ``attribute_not_exists(version)``.

        Validates: Requirement 6.2
        """
        table = ConditionalSkeletonTable()
        legacy_skeleton = {
            schema.PARTITION_KEY_ATTR: _TENANT_ID,
            schema.SORT_KEY_ATTR: _FIELDS_SK,
            "fields": {},
            "overrides": {},
            "functional_groups": {},
            # no version attribute
        }
        table.seed(legacy_skeleton)
        repo = _make_repo(table, version="v-first-versioned")

        result = repo.apply_ops(
            _TENANT_ID,
            schema.CONFIG_ID_FIELDS,
            [{"action": SET, "path": ["fields", "x"], "value": {"key": "x"}}],
            base_version=LEGACY_NO_VERSION,
        )

        assert result["version"] == "v-first-versioned"
        stored = table.store[(_TENANT_ID, _FIELDS_SK)]
        assert stored["fields"]["x"] == {"key": "x"}
        assert stored[schema.VERSION_ATTR] == "v-first-versioned"
