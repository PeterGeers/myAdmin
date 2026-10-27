"""
Spec 03 Task 2.4 — unit tests for the Change-Op write path
(:meth:`MembersConfigWriteRepository.apply_ops`).

``apply_ops`` is the runtime Change-Op write verb (design C2 + D5, design-review Must-fix #1/#2).
It issues ONE version-conditional ``update_item`` built from a set of SET/REMOVE PATH ops. These
tests cover the four behaviours the task names:

1. **Combined expression build** — the ops' paths become one ``UpdateExpression`` with every key
   segment (INCLUDING a dotted ``{group}.{key}`` override key) bound through
   ``ExpressionAttributeNames`` (never inline, so a ``.`` is a literal key — design-review Q2);
   ``version`` is bumped in the same SET clause.
2. **The three version-condition branches** (design D5): existing row with version
   (``version = :base``), existing legacy row with no version
   (``attribute_not_exists(version)``), and no row yet (``attribute_not_exists(sk)``). A stale base
   → ``StaleVersionError`` with NO partial change.
3. **Overlapping-path rejection** — ops whose paths overlap are rejected up front with
   ``ChangeOpError`` BEFORE any ``update_item`` (the "document paths overlap" class).
4. **The idempotency parameter** (task 4.2, proven end-to-end) — an optional ``client_op_id`` is
   stamped on the row; and on a conditional-check failure the three cases are distinguished:
   (a) a lost-response retry carrying the SAME id that already produced the current version →
   recognised as an idempotent replay (success, not a spurious self-409); (b) the SAME id sent but
   a genuinely DIFFERENT concurrent edit produced the current version (stored id differs) → a real
   409 with no clobber; (c) an ABSENT id on a stale base → the ordinary 409, the idempotency
   re-read never attempted (unchanged pre-4.2 behaviour).

DynamoDB is faked in-memory with a ``ConditionalFakeTable`` that EVALUATES the three
ConditionExpression shapes + applies a parsed SET/REMOVE UpdateExpression over bound
ExpressionAttributeNames/Values, so the tests exercise the real expression the repository builds —
not a stub that ignores it.

**Validates: Requirements 1.3, 1.5, 4.2, 6.1, 6.2**
"""

import os
import re
import sys

import pytest

# repo root + backend/src on sys.path (mirrors the sibling write-repo test).
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)
_BACKEND_SRC = os.path.join(_REPO_ROOT, "backend", "src")
if _BACKEND_SRC not in sys.path:
    sys.path.insert(0, _BACKEND_SRC)

from services import projection_schema as schema

from sam.members.repository.projection_config_write_repository import (
    LEGACY_NO_VERSION,
    REMOVE,
    SET,
    ChangeOpError,
    MembersConfigWriteRepository,
    StaleVersionError,
    TruncationTripwireError,
)

_TENANT_ID = "apply-ops-tenant"
_FIELDS_SK = "config#fields"


# ---------------------------------------------------------------------------
# A botocore ClientError lookalike + a condition-evaluating fake table
# ---------------------------------------------------------------------------


from botocore.exceptions import ClientError


def _conditional_check_failed() -> ClientError:
    """A real botocore ``ClientError`` with a ``ConditionalCheckFailedException`` code.

    The repository catches ``botocore.exceptions.ClientError`` (the established SAM pattern,
    ``mail_send_adapters.py``), so the fake raises the genuine type DynamoDB would.
    """
    return ClientError(
        {"Error": {"Code": "ConditionalCheckFailedException", "Message": "The conditional request failed"}},
        "UpdateItem",
    )


class ConditionalFakeTable:
    """In-memory DynamoDB ``Table`` fake that honours the three ConditionExpression shapes and
    applies the built SET/REMOVE UpdateExpression.

    Enough of DynamoDB's semantics to prove the expression the repository builds is correct:
    - evaluates ``attribute_not_exists(sk)`` / ``attribute_not_exists(version)`` / ``version = :base``
      against the stored row, raising a ``ConditionalCheckFailedException`` ClientError when false;
    - resolves ``#n<i>`` name placeholders + ``:v<i>`` / ``:base`` value placeholders;
    - applies each ``SET a.b.c = :v`` (nested) and ``REMOVE a.b.c``, creating nested maps as needed.
    """

    def __init__(self):
        self.store: dict[tuple, dict] = {}
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

    def update_item(
        self,
        Key=None,
        UpdateExpression=None,
        ConditionExpression=None,
        ExpressionAttributeNames=None,
        ExpressionAttributeValues=None,
    ):
        self.update_calls.append(
            {
                "UpdateExpression": UpdateExpression,
                "ConditionExpression": ConditionExpression,
                "ExpressionAttributeNames": dict(ExpressionAttributeNames or {}),
                "ExpressionAttributeValues": dict(ExpressionAttributeValues or {}),
            }
        )
        names = ExpressionAttributeNames or {}
        values = ExpressionAttributeValues or {}
        self._base = values.get(":base")
        key_tuple = self._key_tuple(Key)
        existing = self.store.get(key_tuple)

        if not self._condition_holds(ConditionExpression, names, existing):
            raise _conditional_check_failed()

        item = dict(existing) if existing else dict(Key)
        self._apply_update(item, UpdateExpression, names, values)
        self.store[key_tuple] = item
        return {}

    # -- condition evaluation -------------------------------------------------

    def _condition_holds(self, condition, names, existing) -> bool:
        if condition is None:
            return True
        m = re.fullmatch(r"attribute_not_exists\((#n\d+)\)", condition)
        if m:
            segment = names[m.group(1)]
            if segment == schema.SORT_KEY_ATTR:
                return existing is None  # no row yet
            # attribute_not_exists(version): row must exist WITHOUT the version attr.
            return existing is not None and schema.VERSION_ATTR not in existing
        m = re.fullmatch(r"(#n\d+) = :base", condition)
        if m:
            segment = names[m.group(1)]
            # the caller-read base is compared to the stored attr value
            return existing is not None and existing.get(segment) == self._base
        raise AssertionError(f"unexpected condition: {condition!r}")

    # -- update application ---------------------------------------------------

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
        # "SET a = :v, b = :w REMOVE c, d" — split on the REMOVE keyword boundary.
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


def _make_repo(table, version="v-new"):
    """A repo with a pinned deterministic version stamp so the bump is assertable."""
    return MembersConfigWriteRepository(table=table, version_fn=lambda: version)


def _skeleton_row(version="v1"):
    return {
        schema.PARTITION_KEY_ATTR: _TENANT_ID,
        schema.SORT_KEY_ATTR: _FIELDS_SK,
        schema.VERSION_ATTR: version,
        "fields": {},
        "overrides": {},
        "functional_groups": {},
    }


# ---------------------------------------------------------------------------
# 1. Combined expression build (dotted keys via ExpressionAttributeNames)
# ---------------------------------------------------------------------------


class TestCombinedExpressionBuild:
    def test_set_and_remove_ops_build_one_expression_with_bound_names(self):
        """A SET + a REMOVE become one expression; every segment binds via a name placeholder.

        Validates: Requirements 1.3, 6.1
        """
        table = ConditionalFakeTable()
        table.seed(_skeleton_row(version="v1"))
        repo = _make_repo(table, version="v-2")

        ops = [
            {"action": SET, "path": ["overrides", "personal.gender", "label"], "value": "Gender"},
            {"action": REMOVE, "path": ["fields", "nickname"]},
        ]
        result = repo.apply_ops(_TENANT_ID, schema.CONFIG_ID_FIELDS, ops, base_version="v1")

        call = table.update_calls[-1]
        expr = call["UpdateExpression"]
        names = call["ExpressionAttributeNames"]
        # Dotted override key is a BOUND NAME, never inline — a "." never appears as a literal
        # segment in the names map (it would be parsed as a nested path otherwise).
        assert "personal.gender" in names.values()
        assert "SET " in expr and "REMOVE " in expr
        # No raw key name leaks inline into the expression — only #n placeholders + value refs.
        assert "overrides" not in expr
        assert "personal.gender" not in expr
        # version is bumped in the SAME expression.
        assert schema.VERSION_ATTR in names.values()
        assert result["version"] == "v-2"
        # The nested value actually landed on the stored row under the dotted key.
        stored = table.store[(_TENANT_ID, _FIELDS_SK)]
        assert stored["overrides"]["personal.gender"]["label"] == "Gender"
        assert "nickname" not in stored["fields"]
        assert stored[schema.VERSION_ATTR] == "v-2"

    def test_create_whole_entry_set_writes_the_entry_map(self):
        """A CREATE op (``SET fields.<key> = :whole_entry``) stores the whole entry map.

        Validates: Requirement 1.3
        """
        table = ConditionalFakeTable()
        table.seed(_skeleton_row(version="v1"))
        repo = _make_repo(table, version="v-2")

        entry = {"key": "shoe_size", "type": "number", "label": {"en": "Shoe size"}}
        ops = [{"action": SET, "path": ["fields", "shoe_size"], "value": entry}]
        repo.apply_ops(_TENANT_ID, schema.CONFIG_ID_FIELDS, ops, base_version="v1")

        stored = table.store[(_TENANT_ID, _FIELDS_SK)]
        assert stored["fields"]["shoe_size"] == entry
        # Untouched sibling maps survive (structural no-truncation).
        assert stored["overrides"] == {}
        assert stored["functional_groups"] == {}


# ---------------------------------------------------------------------------
# 2. The three version-condition branches (design D5)
# ---------------------------------------------------------------------------


class TestVersionConditionBranches:
    def test_existing_row_with_version_matches_base(self):
        """(i) existing row + ``base_version`` == stored version → write succeeds, bumps version.

        Validates: Requirement 6.2
        """
        table = ConditionalFakeTable()
        table.seed(_skeleton_row(version="v1"))
        repo = _make_repo(table, version="v-2")

        result = repo.apply_ops(
            _TENANT_ID,
            schema.CONFIG_ID_FIELDS,
            [{"action": SET, "path": ["fields", "x"], "value": {"key": "x"}}],
            base_version="v1",
        )
        assert result == {"version": "v-2", "idempotent_replay": False}
        assert table.store[(_TENANT_ID, _FIELDS_SK)][schema.VERSION_ATTR] == "v-2"

    def test_existing_row_with_stale_version_raises_and_makes_no_change(self):
        """(i) a STALE base version → StaleVersionError, no partial change.

        Validates: Requirement 6.2
        """
        table = ConditionalFakeTable()
        table.seed(_skeleton_row(version="v5"))
        repo = _make_repo(table, version="v-new")

        with pytest.raises(StaleVersionError):
            repo.apply_ops(
                _TENANT_ID,
                schema.CONFIG_ID_FIELDS,
                [{"action": SET, "path": ["fields", "x"], "value": {"key": "x"}}],
                base_version="v1",  # stale — stored is v5
            )
        stored = table.store[(_TENANT_ID, _FIELDS_SK)]
        assert stored[schema.VERSION_ATTR] == "v5"  # unchanged
        assert "x" not in stored["fields"]  # no partial change

    def test_legacy_row_without_version_uses_attribute_not_exists_branch(self):
        """(ii) existing row with NO version + LEGACY_NO_VERSION sentinel → first versioned write.

        Validates: Requirement 6.2
        """
        table = ConditionalFakeTable()
        legacy = _skeleton_row()
        del legacy[schema.VERSION_ATTR]  # a pre-version row
        table.seed(legacy)
        repo = _make_repo(table, version="v-first")

        result = repo.apply_ops(
            _TENANT_ID,
            schema.CONFIG_ID_FIELDS,
            [{"action": SET, "path": ["fields", "x"], "value": {"key": "x"}}],
            base_version=LEGACY_NO_VERSION,
        )
        assert result["version"] == "v-first"
        assert table.store[(_TENANT_ID, _FIELDS_SK)][schema.VERSION_ATTR] == "v-first"

    def test_legacy_branch_rejects_a_row_that_already_has_a_version(self):
        """(ii) the legacy branch fails (correctly) if the row ALREADY carries a version.

        Validates: Requirement 6.2
        """
        table = ConditionalFakeTable()
        table.seed(_skeleton_row(version="v1"))  # already versioned
        repo = _make_repo(table)

        with pytest.raises(StaleVersionError):
            repo.apply_ops(
                _TENANT_ID,
                schema.CONFIG_ID_FIELDS,
                [{"action": SET, "path": ["fields", "x"], "value": {"key": "x"}}],
                base_version=LEGACY_NO_VERSION,
            )

    def test_no_row_uses_attribute_not_exists_sk_and_creates(self):
        """(iii) base_version None + no row → attribute_not_exists(sk), creates the row.

        Validates: Requirement 6.2
        """
        table = ConditionalFakeTable()  # empty — no row
        repo = _make_repo(table, version="v-create")

        result = repo.apply_ops(
            _TENANT_ID,
            schema.CONFIG_ID_FIELDS,
            [{"action": SET, "path": ["fields", "x"], "value": {"key": "x"}}],
            base_version=None,
        )
        assert result["version"] == "v-create"
        stored = table.store[(_TENANT_ID, _FIELDS_SK)]
        assert stored["fields"]["x"] == {"key": "x"}

    def test_no_row_branch_rejects_when_a_row_already_exists(self):
        """(iii) base_version None but a row EXISTS → the create condition fails (no clobber).

        Validates: Requirement 6.2
        """
        table = ConditionalFakeTable()
        table.seed(_skeleton_row(version="v1"))
        repo = _make_repo(table)

        with pytest.raises(StaleVersionError):
            repo.apply_ops(
                _TENANT_ID,
                schema.CONFIG_ID_FIELDS,
                [{"action": SET, "path": ["fields", "x"], "value": {"key": "x"}}],
                base_version=None,
            )


# ---------------------------------------------------------------------------
# 3. Overlapping-path rejection (up front, BEFORE any update_item)
# ---------------------------------------------------------------------------


class TestOverlappingPathRejection:
    def test_prefix_overlap_is_rejected_before_any_write(self):
        """SET overrides.x + SET overrides.x.label overlap → ChangeOpError, no update_item.

        Validates: Requirement 1.3
        """
        table = ConditionalFakeTable()
        table.seed(_skeleton_row(version="v1"))
        repo = _make_repo(table)

        ops = [
            {"action": SET, "path": ["overrides", "x"], "value": {}},
            {"action": SET, "path": ["overrides", "x", "label"], "value": "L"},
        ]
        with pytest.raises(ChangeOpError):
            repo.apply_ops(_TENANT_ID, schema.CONFIG_ID_FIELDS, ops, base_version="v1")
        assert table.update_calls == []  # BEFORE any call

    def test_identical_paths_are_rejected(self):
        """Two ops on the identical path overlap → ChangeOpError.

        Validates: Requirement 1.3
        """
        table = ConditionalFakeTable()
        repo = _make_repo(table)
        ops = [
            {"action": SET, "path": ["fields", "x", "label"], "value": "a"},
            {"action": SET, "path": ["fields", "x", "label"], "value": "b"},
        ]
        with pytest.raises(ChangeOpError):
            repo.apply_ops(_TENANT_ID, schema.CONFIG_ID_FIELDS, ops, base_version=None)
        assert table.update_calls == []

    def test_sibling_paths_do_not_overlap(self):
        """Distinct sibling aspects (…label vs …order) do NOT overlap — both apply atomically.

        Validates: Requirement 1.3
        """
        table = ConditionalFakeTable()
        table.seed(_skeleton_row(version="v1"))
        repo = _make_repo(table, version="v-2")
        ops = [
            {"action": SET, "path": ["overrides", "a.b", "label"], "value": "L"},
            {"action": SET, "path": ["overrides", "a.b", "order"], "value": 3},
        ]
        repo.apply_ops(_TENANT_ID, schema.CONFIG_ID_FIELDS, ops, base_version="v1")
        stored = table.store[(_TENANT_ID, _FIELDS_SK)]["overrides"]["a.b"]
        assert stored == {"label": "L", "order": 3}

    @pytest.mark.parametrize(
        "ops",
        [
            [],  # empty set
            [{"action": "DELETE", "path": ["fields", "x"]}],  # unknown action
            [{"action": SET, "path": [], "value": 1}],  # empty path
            [{"action": SET, "path": ["fields", ""], "value": 1}],  # blank segment
            [{"action": SET, "path": ["fields", "x"]}],  # SET without value
            ["not-a-mapping"],  # malformed op
        ],
    )
    def test_malformed_op_sets_are_rejected_before_any_write(self, ops):
        """Empty / malformed / unknown-action / blank-segment / value-less ops all reject up front.

        Validates: Requirement 1.3
        """
        table = ConditionalFakeTable()
        repo = _make_repo(table)
        with pytest.raises(ChangeOpError):
            repo.apply_ops(_TENANT_ID, schema.CONFIG_ID_FIELDS, ops, base_version=None)
        assert table.update_calls == []


# ---------------------------------------------------------------------------
# 4. The idempotency parameter (client_op_id)
# ---------------------------------------------------------------------------


class TestIdempotency:
    def test_client_op_id_is_stamped_on_the_row(self):
        """A supplied client_op_id is written onto the row (last_client_op_id) in the same update.

        Validates: Requirement 4.2
        """
        table = ConditionalFakeTable()
        table.seed(_skeleton_row(version="v1"))
        repo = _make_repo(table, version="v-2")

        repo.apply_ops(
            _TENANT_ID,
            schema.CONFIG_ID_FIELDS,
            [{"action": SET, "path": ["fields", "x"], "value": {"key": "x"}}],
            base_version="v1",
            client_op_id="op-abc",
        )
        stored = table.store[(_TENANT_ID, _FIELDS_SK)]
        assert stored["last_client_op_id"] == "op-abc"

    def test_lost_response_retry_with_same_op_id_is_idempotent_replay(self):
        """A stale-version retry whose client_op_id already produced the current row → success.

        Validates: Requirement 4.2
        """
        table = ConditionalFakeTable()
        # The row already reflects the FIRST (successful but lost-response) write: bumped version
        # + the op id stamped. The client retries with the now-stale base it originally read.
        row = _skeleton_row(version="v-2")
        row["last_client_op_id"] = "op-abc"
        table.seed(row)
        repo = _make_repo(table, version="v-3")

        result = repo.apply_ops(
            _TENANT_ID,
            schema.CONFIG_ID_FIELDS,
            [{"action": SET, "path": ["fields", "x"], "value": {"key": "x"}}],
            base_version="v1",  # stale — the retry carries the pre-write base
            client_op_id="op-abc",  # SAME id that already applied
        )
        assert result == {"version": "v-2", "idempotent_replay": True}
        # No second write happened — the stored version is still the first write's v-2, not v-3.
        assert table.store[(_TENANT_ID, _FIELDS_SK)][schema.VERSION_ATTR] == "v-2"

    def test_stale_retry_with_a_different_op_id_is_a_genuine_conflict(self):
        """A stale retry whose op id does NOT match the stored one is a real 409.

        This is the "same id sent, but a genuinely DIFFERENT concurrent edit produced the current
        version" case: the row carries a DIFFERENT ``last_client_op_id`` (another writer's op got
        there first), so this retry's id does not match and the write is a real conflict — NOT a
        false-positive idempotent replay.

        Validates: Requirement 4.2
        """
        table = ConditionalFakeTable()
        row = _skeleton_row(version="v-2")
        row["last_client_op_id"] = "op-OTHER"
        table.seed(row)
        repo = _make_repo(table)

        with pytest.raises(StaleVersionError):
            repo.apply_ops(
                _TENANT_ID,
                schema.CONFIG_ID_FIELDS,
                [{"action": SET, "path": ["fields", "x"], "value": {"key": "x"}}],
                base_version="v1",
                client_op_id="op-abc",
            )
        # No clobber — the other writer's version + op id stand.
        stored = table.store[(_TENANT_ID, _FIELDS_SK)]
        assert stored[schema.VERSION_ATTR] == "v-2"
        assert stored["last_client_op_id"] == "op-OTHER"

    def test_absent_op_id_on_a_stale_base_is_a_plain_409_no_replay_check(self):
        """With NO client_op_id, a stale base is the ordinary 409 — the idempotency re-read is
        never even attempted (absent id → current/pre-4.2 behaviour, unchanged).

        Validates: Requirement 4.2, 6.2
        """
        table = ConditionalFakeTable()
        row = _skeleton_row(version="v-2")
        # A row that WAS produced by some idempotency-carrying write; irrelevant here because the
        # retry supplies no id, so the stored id must not rescue it.
        row["last_client_op_id"] = "op-abc"
        table.seed(row)
        repo = _make_repo(table)

        with pytest.raises(StaleVersionError):
            repo.apply_ops(
                _TENANT_ID,
                schema.CONFIG_ID_FIELDS,
                [{"action": SET, "path": ["fields", "x"], "value": {"key": "x"}}],
                base_version="v1",  # stale — stored is v-2
                client_op_id=None,  # absent → NO idempotency shortcut
            )
        stored = table.store[(_TENANT_ID, _FIELDS_SK)]
        assert stored[schema.VERSION_ATTR] == "v-2"  # no change
        assert "x" not in stored["fields"]


# ---------------------------------------------------------------------------
# Guards retained from put_config (closed id set + non-empty tenant)
# ---------------------------------------------------------------------------


class TestGuardsRetained:
    @pytest.mark.parametrize("blank", ["", None])
    def test_blank_tenant_rejected_before_any_write(self, blank):
        """A blank tenant raises ValueError before any update_item (tenancy boundary R5.5)."""
        table = ConditionalFakeTable()
        repo = _make_repo(table)
        with pytest.raises(ValueError):
            repo.apply_ops(
                blank,
                schema.CONFIG_ID_FIELDS,
                [{"action": SET, "path": ["fields", "x"], "value": 1}],
                base_version=None,
            )
        assert table.update_calls == []

    @pytest.mark.parametrize("bad_id", ["views", "tenant", "unknown", ""])
    def test_config_id_outside_closed_set_rejected_before_any_write(self, bad_id):
        """A config_id outside {fields, scope, mail} raises ValueError before any update_item."""
        table = ConditionalFakeTable()
        repo = _make_repo(table)
        with pytest.raises(ValueError):
            repo.apply_ops(
                _TENANT_ID,
                bad_id,
                [{"action": SET, "path": ["fields", "x"], "value": 1}],
                base_version=None,
            )
        assert table.update_calls == []


# ---------------------------------------------------------------------------
# 5. Runtime truncation tripwire (spec 03 task 8.4 / R11.5) — last-line defense
# ---------------------------------------------------------------------------
#
# The write repository REFUSES a config#fields op set that would SILENTLY shrink the stored
# group/field COUNT unless an explicit whole-entry delete op accounts for the drop. This is the
# last-line defense underneath the structural Change-Op guarantee: even if a LOGIC BUG upstream
# produced an op set that reduces a count with no delete, the write is refused — nothing reaches
# DynamoDB. A LEGITIMATE explicit delete (a REMOVE of a whole fields.<key> / overrides.<dotted> /
# functional_groups.<gkey> entry) is ALLOWED (the count may drop by exactly what was deleted).
#
# Both directions are covered: (1) an explicit delete is allowed; (2) a silent shrink is refused,
# no write performed. The fake HONOURS the pre-write get_item the tripwire reads, so the base count
# is the real stored count — not a stub.
# ---------------------------------------------------------------------------


def _populated_fields_row(version="v1"):
    """A config#fields row with real groups + fields so a shrink is observable.

    Two groups, two variable fields (``fields``), one base override (``overrides``). Group count = 2;
    field count = 2 (fields) + 1 (overrides) = 3.
    """
    return {
        schema.PARTITION_KEY_ATTR: _TENANT_ID,
        schema.SORT_KEY_ATTR: _FIELDS_SK,
        schema.VERSION_ATTR: version,
        "fields": {
            "nickname": {"key": "nickname", "type": "string"},
            "shoe_size": {"key": "shoe_size", "type": "number"},
        },
        "overrides": {
            "personal.gender": {"label": "Gender"},
        },
        "functional_groups": {
            "personal": {"order": 1, "label": "Personal"},
            "contact": {"order": 2, "label": "Contact"},
        },
    }


class TestTruncationTripwireAllowsLegitimateDeletes:
    """Direction (1): an EXPLICIT delete op is allowed — the count may drop by what was deleted."""

    def test_explicit_delete_field_is_allowed(self):
        """A REMOVE of a whole ``fields.<key>`` entry (delete_field) is allowed; count drops by 1.

        Validates: Requirement 11.5
        """
        table = ConditionalFakeTable()
        table.seed(_populated_fields_row(version="v1"))
        repo = _make_repo(table, version="v-2")

        result = repo.apply_ops(
            _TENANT_ID,
            schema.CONFIG_ID_FIELDS,
            [{"action": REMOVE, "path": ["fields", "nickname"]}],
            base_version="v1",
        )
        assert result["version"] == "v-2"
        stored = table.store[(_TENANT_ID, _FIELDS_SK)]
        assert "nickname" not in stored["fields"]
        assert "shoe_size" in stored["fields"]  # sibling survives
        assert set(stored["functional_groups"]) == {"personal", "contact"}

    def test_explicit_delete_group_is_allowed(self):
        """A REMOVE of a whole ``functional_groups.<gkey>`` entry (delete_group) is allowed.

        Validates: Requirement 11.5
        """
        table = ConditionalFakeTable()
        table.seed(_populated_fields_row(version="v1"))
        repo = _make_repo(table, version="v-2")

        result = repo.apply_ops(
            _TENANT_ID,
            schema.CONFIG_ID_FIELDS,
            [{"action": REMOVE, "path": ["functional_groups", "contact"]}],
            base_version="v1",
        )
        assert result["version"] == "v-2"
        stored = table.store[(_TENANT_ID, _FIELDS_SK)]
        assert set(stored["functional_groups"]) == {"personal"}

    def test_explicit_reset_field_override_delete_is_allowed(self):
        """A REMOVE of a whole ``overrides.<dotted>`` entry (reset_field → revert to base) allowed.

        Validates: Requirement 11.5
        """
        table = ConditionalFakeTable()
        table.seed(_populated_fields_row(version="v1"))
        repo = _make_repo(table, version="v-2")

        result = repo.apply_ops(
            _TENANT_ID,
            schema.CONFIG_ID_FIELDS,
            [{"action": REMOVE, "path": ["overrides", "personal.gender"]}],
            base_version="v1",
        )
        assert result["version"] == "v-2"
        assert "personal.gender" not in table.store[(_TENANT_ID, _FIELDS_SK)]["overrides"]

    def test_multiple_explicit_deletes_drop_count_by_exactly_that_many(self):
        """Two whole-entry deletes in one request drop the field count by exactly two — allowed.

        Validates: Requirement 11.5
        """
        table = ConditionalFakeTable()
        table.seed(_populated_fields_row(version="v1"))
        repo = _make_repo(table, version="v-2")

        ops = [
            {"action": REMOVE, "path": ["fields", "nickname"]},
            {"action": REMOVE, "path": ["fields", "shoe_size"]},
        ]
        result = repo.apply_ops(
            _TENANT_ID, schema.CONFIG_ID_FIELDS, ops, base_version="v1"
        )
        assert result["version"] == "v-2"
        assert table.store[(_TENANT_ID, _FIELDS_SK)]["fields"] == {}

    def test_attribute_edit_does_not_trip_and_preserves_counts(self):
        """An attribute-level SET (not a whole-entry op) never changes a count → never trips.

        Validates: Requirement 11.5
        """
        table = ConditionalFakeTable()
        table.seed(_populated_fields_row(version="v1"))
        repo = _make_repo(table, version="v-2")

        repo.apply_ops(
            _TENANT_ID,
            schema.CONFIG_ID_FIELDS,
            [{"action": SET, "path": ["fields", "nickname", "label"], "value": "Nick"}],
            base_version="v1",
        )
        stored = table.store[(_TENANT_ID, _FIELDS_SK)]
        assert len(stored["fields"]) == 2  # unchanged count
        assert stored["fields"]["nickname"]["label"] == "Nick"

    def test_growth_empty_to_populated_is_allowed(self):
        """The C6 first write (empty skeleton → one field) is GROWTH, never a shrink → allowed.

        Validates: Requirement 11.5
        """
        table = ConditionalFakeTable()
        table.seed(_skeleton_row(version="v1"))  # all empty maps
        repo = _make_repo(table, version="v-2")

        repo.apply_ops(
            _TENANT_ID,
            schema.CONFIG_ID_FIELDS,
            [{"action": SET, "path": ["fields", "x"], "value": {"key": "x"}}],
            base_version="v1",
        )
        assert "x" in table.store[(_TENANT_ID, _FIELDS_SK)]["fields"]


class TestTruncationTripwireRefusesSilentShrink:
    """Direction (2): a SILENT shrink (count drops, NO delete op) is refused, no write performed.

    Each test simulates a LOGIC BUG that produced an op set whose net effect reduces a bucket's
    entry count without an explicit whole-entry delete to account for it. The tripwire refuses with
    TruncationTripwireError and nothing is written (``update_calls == []``).
    """

    def test_silent_field_shrink_via_whole_fields_map_set_is_refused(self):
        """A buggy ``SET fields = {only one of two}`` (whole-map replace) would shrink → refused.

        This is the exact occurrence-3 class: a partial whole-map payload that drops entries with no
        delete op. The Change-Op model should never emit this; the tripwire catches it if a bug does.

        Validates: Requirement 11.5
        """
        table = ConditionalFakeTable()
        table.seed(_populated_fields_row(version="v1"))  # fields has 2 entries
        repo = _make_repo(table, version="v-2")

        # A path of length 2 ["fields", "nickname"] SET keeps count; to force a SILENT shrink we
        # simulate the whole-map replace a buggy caller might emit: SET the "fields" PARENT itself
        # to a smaller map. This drops field entries with NO delete op.
        buggy_ops = [
            {"action": SET, "path": ["fields"], "value": {"nickname": {"key": "nickname"}}},
        ]
        with pytest.raises(TruncationTripwireError):
            repo.apply_ops(
                _TENANT_ID, schema.CONFIG_ID_FIELDS, buggy_ops, base_version="v1"
            )
        assert table.update_calls == []  # nothing written
        stored = table.store[(_TENANT_ID, _FIELDS_SK)]
        assert len(stored["fields"]) == 2  # untouched

    def test_silent_group_shrink_via_whole_groups_map_set_is_refused(self):
        """A buggy whole ``functional_groups`` replace that drops a group with no delete → refused.

        The exact catalog-truncation scenario the spec exists to kill, caught at runtime.

        Validates: Requirement 11.5
        """
        table = ConditionalFakeTable()
        table.seed(_populated_fields_row(version="v1"))  # 2 groups
        repo = _make_repo(table, version="v-2")

        buggy_ops = [
            {
                "action": SET,
                "path": ["functional_groups"],
                "value": {"personal": {"order": 1}},  # dropped "contact", no delete op
            },
        ]
        with pytest.raises(TruncationTripwireError):
            repo.apply_ops(
                _TENANT_ID, schema.CONFIG_ID_FIELDS, buggy_ops, base_version="v1"
            )
        assert table.update_calls == []
        assert set(table.store[(_TENANT_ID, _FIELDS_SK)]["functional_groups"]) == {
            "personal",
            "contact",
        }

    def test_shrink_beyond_the_explicit_deletes_is_refused(self):
        """A whole-map replace that drops 2 while only 1 delete op is present → still refused.

        A reduction is allowed only UP TO the number of explicit deletes. Here a buggy whole-``fields``
        replace keeps one entry (net -1 from the replace) PLUS an explicit delete op is present, but
        the replace itself silently loses an entry the delete does not name — refused.

        Validates: Requirement 11.5
        """
        table = ConditionalFakeTable()
        table.seed(_populated_fields_row(version="v1"))  # fields: nickname, shoe_size (2)
        repo = _make_repo(table, version="v-2")

        # overrides has 1 entry; delete it (legit, +1 allowed drop) but ALSO a buggy whole-fields
        # replace that silently drops shoe_size. Net projected field count = 1 (only nickname),
        # base = 3, explicit deletes = 1 → allowed floor = 2 > 1 → refused.
        buggy_ops = [
            {"action": REMOVE, "path": ["overrides", "personal.gender"]},
            {"action": SET, "path": ["fields"], "value": {"nickname": {"key": "nickname"}}},
        ]
        with pytest.raises(TruncationTripwireError):
            repo.apply_ops(
                _TENANT_ID, schema.CONFIG_ID_FIELDS, buggy_ops, base_version="v1"
            )
        assert table.update_calls == []

    def test_tripwire_does_not_fire_for_scope_or_mail_rows(self):
        """scope/mail rows have no catalog/field-count invariant — the tripwire is fields-only.

        A whole-map SET on config#scope is not a config#fields truncation, so it is not refused by
        the tripwire (it may be rejected elsewhere, but NOT by this last-line defense).

        Validates: Requirement 11.5
        """
        table = ConditionalFakeTable()
        table.seed(
            {
                schema.PARTITION_KEY_ATTR: _TENANT_ID,
                schema.SORT_KEY_ATTR: "config#scope",
                schema.VERSION_ATTR: "v1",
                "dimensions": {"a": 1, "b": 2},
            }
        )
        repo = _make_repo(table, version="v-2")

        # A whole "dimensions" replace that drops an entry — NOT tripped (scope row).
        repo.apply_ops(
            _TENANT_ID,
            schema.CONFIG_ID_SCOPE,
            [{"action": SET, "path": ["dimensions"], "value": {"a": 1}}],
            base_version="v1",
        )
        assert table.store[(_TENANT_ID, "config#scope")]["dimensions"] == {"a": 1}
