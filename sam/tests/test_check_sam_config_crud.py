"""Unit tests for the SAM ``config#fields`` CRUD guard (``scripts/check_sam_config_crud.py``).

The SAM-plane sibling of ``backend/tests/unit/test_check_db_imports.py`` /
``test_check_raw_connection.py``. It tests the guard that mechanically enforces the Change-Op
write contract (steering ``39-backend-data-access-sam-dynamodb.md`` → Enforcement; spec
``03 - config-fields-foolproof-crud`` requirement R11.2; ADR 0009), on BOTH its checks:

  (a) a RAW governance-table write (``.put_item`` / ``.update_item`` / ``.delete_item``) in a
      governance-writer module OUTSIDE the two sanctioned sites → flagged; the sanctioned write
      repository + the C6 migration are allow-listed; a write on a DIFFERENT aggregate (no
      governance-table marker) and a test module are out of scope.

  (b) a RAW storage-shape key (``field_overlay`` / ``overrides`` / ``fixed_overrides`` /
      dotted ``{group}.{key}``) as a DICT-LITERAL key in a response-shaping module → flagged;
      a frozenset membership set / docstring mention is NOT; a resolved Flat_View response is
      clean.

The planted-violation cases (a PLANTED raw write / raw-shape key FAILS the guard) and the
clean-tree cases (a Change-Op write / Flat_View response PASSES) are the task-8.1 proof that
the guard blocks what it must and nothing it must not. The end-to-end "plant a real violation
in the tree, confirm CI blocks, revert" proof is the SEPARATE task 9.2.

Lives under ``sam/tests/`` (runs via ``sam/pytest.ini``) — the home for SAM-plane tests, next
to the tree the guard scans — mirroring how the Flask guards' tests live under
``backend/tests/unit/`` next to ``backend/``.

Validates: Requirements R11.2
"""

import sys
import textwrap
from pathlib import Path

# The guard lives at repo-root ``scripts/`` (not a package on sys.path). Add that dir so we can
# import it by module name — mirrors test_check_db_imports.py / test_check_raw_connection.py.
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_REPO_ROOT / "scripts"))

from check_sam_config_crud import (  # noqa: E402
    RAW_WRITE_METHODS,
    RAW_SHAPE_KEYS,
    RAW_WRITE_ALLOWED_FILES,
    RESPONSE_SHAPE_ALLOWED_FILES,
    SCAN_DIRS,
    EXCLUDED_DIRS,
    check_file,
    scan_directory,
    _is_dotted_group_key,
)


def _write(root: Path, rel: str, body: str) -> Path:
    """Write a dedented snippet to ``root/rel`` and return the path.

    ``rel`` is the repo-root-relative POSIX path the guard keys its allow-lists on, so tests
    construct files UNDER a fake repo root mirroring the real layout (e.g.
    ``sam/members/repository/projection_config_write_repository.py``) to exercise allow-list
    matching exactly as the full scan would.
    """
    f = root / rel
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(textwrap.dedent(body), encoding="utf-8")
    return f


# The governance-table marker line: a module carrying it resolves the projection table, so it
# is a governance-table writer and its raw writes are in scope for check (a). Kept as a single
# unindented line so it can be prepended to any dedented body without disturbing indentation.
_GOV_MARKER = "schema = None  # get_projection_table_resource\n"


def _gov(body: str) -> str:
    """A governance-writer module source: the marker line + a dedented ``body``."""
    return _GOV_MARKER + textwrap.dedent(body)


# ─────────────────────────────────────────────────────────────────────────────────────────
# (a) Raw governance-table writes
# ─────────────────────────────────────────────────────────────────────────────────────────


class TestRawGovernanceWrites:
    """check (a): a raw write in a governance-writer module outside the sanctioned sites."""

    def test_planted_put_item_in_governance_writer_is_flagged(self, tmp_path):
        """A PLANTED ``.put_item(`` in a non-sanctioned governance-writer module FAILS the guard."""
        f = _write(
            tmp_path,
            "sam/members/repository/rogue_config_writer.py",
            _gov(
                """\
                def write(table, item):
                    table.put_item(Item=item)
                """
            ),
        )
        violations = check_file(f)
        assert len(violations) == 1
        assert "put_item" in violations[0]
        assert "rogue_config_writer.py" in violations[0]

    def test_planted_update_item_is_flagged(self, tmp_path):
        """A planted ``.update_item(`` is flagged (the runtime path belongs to the repo)."""
        f = _write(
            tmp_path,
            "sam/members/handler/rogue_update.py",
            _gov(
                """\
                def write(table, key):
                    table.update_item(Key=key, UpdateExpression="SET a = :b")
                """
            ),
        )
        violations = check_file(f)
        assert len(violations) == 1
        assert "update_item" in violations[0]

    def test_planted_delete_item_is_flagged(self, tmp_path):
        """A planted ``.delete_item(`` is flagged."""
        f = _write(
            tmp_path,
            "sam/members/domain/rogue_delete.py",
            _gov(
                """\
                def wipe(table, key):
                    table.delete_item(Key=key)
                """
            ),
        )
        violations = check_file(f)
        assert len(violations) == 1
        assert "delete_item" in violations[0]

    def test_sanctioned_write_repository_is_allowed(self, tmp_path):
        """The Change-Op write repository may call put_item/update_item — it is allow-listed."""
        f = _write(
            tmp_path,
            "sam/members/repository/projection_config_write_repository.py",
            _gov(
                """\
                def put_config(table, item):
                    table.put_item(Item=item)

                def apply_ops(table, key):
                    table.update_item(Key=key, UpdateExpression="SET v = :x")
                """
            ),
        )
        assert check_file(f) == []

    def test_sanctioned_migration_is_allowed(self, tmp_path):
        """The one-time C6 LIST->MAP migration may whole-row put_item — it is allow-listed."""
        f = _write(
            tmp_path,
            "sam/members/migration/functional_groups_list_to_map.py",
            _gov(
                """\
                def migrate(table, item):
                    table.put_item(Item=item)
                """
            ),
        )
        assert check_file(f) == []

    def test_write_on_a_different_aggregate_is_not_flagged(self, tmp_path):
        """A raw write in a module with NO governance-table marker (members table) is clean.

        ``members_repository`` writes the ``sam-members`` table, a different aggregate — it is
        not the governance projection, so its put_item/delete_item are out of scope for (a).
        """
        f = _write(
            tmp_path,
            "sam/members/repository/members_repository.py",
            """\
            class MembersRepository:
                def __init__(self, table):
                    self._table = table

                def save(self, item):
                    self._table.put_item(Item=item)

                def remove(self, key):
                    self._table.delete_item(Key=key)
            """,
        )
        assert check_file(f) == []

    def test_test_module_seeding_the_table_is_not_flagged(self, tmp_path):
        """A ``sam/tests/**`` module that SEEDS the projection table is out of scope (steering 42)."""
        f = _write(
            tmp_path,
            "sam/tests/e2e/conftest.py",
            _gov(
                """\
                def seed(table, item):
                    table.put_item(Item=item)
                """
            ),
        )
        assert check_file(f) == []

    def test_put_item_mention_in_docstring_only_is_not_flagged(self, tmp_path):
        """A governance module that only MENTIONS put_item in prose (no call) is clean (AST)."""
        f = _write(
            tmp_path,
            "sam/members/repository/doc_only.py",
            _gov(
                '''\
                def reader(table):
                    """This reader never calls put_item / update_item — it only queries."""
                    return table.query()
                '''
            ),
        )
        assert check_file(f) == []


# ─────────────────────────────────────────────────────────────────────────────────────────
# (b) Raw storage-shape key in an API response
# ─────────────────────────────────────────────────────────────────────────────────────────


class TestRawShapeInResponse:
    """check (b): a raw storage-shape key as a dict-literal key in a response-shaping module."""

    def test_planted_field_overlay_response_key_is_flagged(self, tmp_path):
        """A PLANTED ``field_overlay`` dict key in a handler response FAILS the guard."""
        f = _write(
            tmp_path,
            "sam/members/handler/app.py",
            """\
            def build_response(overlay):
                return {"statusCode": 200, "body": {"field_overlay": overlay}}
            """,
        )
        violations = check_file(f)
        assert len(violations) == 1
        assert "field_overlay" in violations[0]

    def test_planted_overrides_and_fixed_overrides_keys_are_flagged(self, tmp_path):
        """Raw ``overrides`` / ``fixed_overrides`` dict keys in a response are each flagged."""
        f = _write(
            tmp_path,
            "sam/members/handler/routes_response.py",
            """\
            def build(a, b):
                return {"overrides": a, "fixed_overrides": b}
            """,
        )
        violations = check_file(f)
        assert len(violations) == 2
        joined = " ".join(violations)
        assert "overrides" in joined and "fixed_overrides" in joined

    def test_planted_dotted_group_key_in_response_is_flagged(self, tmp_path):
        """A dotted ``{group}.{key}`` physical override key in a response is flagged."""
        f = _write(
            tmp_path,
            "sam/members/handler/app.py",
            """\
            def build(value):
                return {"personal.gender": value}
            """,
        )
        violations = check_file(f)
        assert len(violations) == 1
        assert "personal.gender" in violations[0]

    def test_flat_view_response_is_clean(self, tmp_path):
        """A resolved Flat_View response (bare-key fields, no raw shape) PASSES the guard."""
        f = _write(
            tmp_path,
            "sam/members/handler/app.py",
            """\
            def build(fields):
                return {
                    "statusCode": 200,
                    "body": {"fields": fields, "version": "v1"},
                }
            """,
        )
        # ``fields`` is the resolved Flat_View container key (not a raw storage-shape key); it is
        # NOT in RAW_SHAPE_KEYS, so a Flat_View response is clean.
        assert check_file(f) == []

    def test_raw_shape_key_outside_response_layer_is_not_flagged(self, tmp_path):
        """A repository module that shapes the STORED item with ``overrides`` is clean for (b).

        (b) only guards what crosses OUT to a response — the repository legitimately builds the
        stored item with the physical container keys. (That module's writes are governed by (a),
        not (b).)
        """
        f = _write(
            tmp_path,
            "sam/members/repository/projection_config_write_repository.py",
            """\
            def build_item(fields, overrides):
                return {"fields": fields, "overrides": overrides}
            """,
        )
        assert check_file(f) == []

    def test_allow_listed_response_file_may_name_raw_keys_defensively(self, tmp_path):
        """An allow-listed stale-bundle guard file may name the raw keys without being flagged.

        The Task 5.3a guard REJECTS a cached old bundle whose body carries the raw keys; naming
        them defensively there is sanctioned (a reviewed allow-list entry), not an emission.
        """
        f = _write(
            tmp_path,
            "sam/members/handler/_dispatch.py",
            """\
            def reject(body):
                # Defensive: a response payload naming the offending keys is allow-listed here.
                return {"field_overlay": None, "overrides": None}
            """,
        )
        assert check_file(f) == []

    def test_frozenset_membership_set_of_raw_keys_is_not_flagged(self, tmp_path):
        """Raw keys as frozenset MEMBERS (the stale-bundle rejection set) are not dict keys."""
        f = _write(
            tmp_path,
            "sam/members/handler/stale_guard.py",
            """\
            WHOLE_OVERLAY_BODY_KEYS = frozenset(
                {"fields", "overrides", "fixed_overrides", "functional_groups", "field_overlay"}
            )

            def is_stale(body):
                return bool(set(body) & WHOLE_OVERLAY_BODY_KEYS)
            """,
        )
        # These appear as SET elements, never as dict-literal keys, so (b) does not flag them.
        assert check_file(f) == []


# ─────────────────────────────────────────────────────────────────────────────────────────
# scan_directory + dotted-key heuristic + config sanity
# ─────────────────────────────────────────────────────────────────────────────────────────


class TestScanDirectory:
    """scan_directory aggregates check_file over a tree and skips excluded dirs."""

    def test_scan_aggregates_violations(self, tmp_path):
        """scan_directory finds a planted violation and a clean file alongside it."""
        _write(
            tmp_path,
            "sam/members/handler/rogue.py",
            _gov("def w(table, i):\n    table.put_item(Item=i)\n"),
        )
        _write(
            tmp_path,
            "sam/members/handler/clean.py",
            "def build(fields):\n    return {'fields': fields}\n",
        )
        violations = scan_directory(tmp_path / "sam")
        assert len(violations) == 1
        assert "rogue.py" in violations[0]

    def test_scan_skips_excluded_dirs(self, tmp_path):
        """A planted write under an excluded dir (.aws-sam build output) is not scanned."""
        _write(
            tmp_path,
            "sam/members/.aws-sam/build/copy.py",
            _gov("def w(table, i):\n    table.put_item(Item=i)\n"),
        )
        assert scan_directory(tmp_path / "sam") == []


class TestDottedGroupKeyHeuristic:
    """The dotted ``{group}.{key}`` matcher is precise (no i18n / error-code false positives)."""

    def test_single_dot_identifier_segments_match(self):
        assert _is_dotted_group_key("personal.gender")
        assert _is_dotted_group_key("membership.status")

    def test_multi_dot_error_code_does_not_match(self):
        """A machine code like ``errors.api.staleClient`` (two dots) is NOT a group.key."""
        assert not _is_dotted_group_key("errors.api.staleClient")

    def test_no_dot_bare_key_does_not_match(self):
        assert not _is_dotted_group_key("gender")

    def test_blank_segment_does_not_match(self):
        assert not _is_dotted_group_key("personal.")
        assert not _is_dotted_group_key(".gender")


class TestGuardConfig:
    """Module-level configuration sanity checks."""

    def test_raw_write_methods(self):
        assert RAW_WRITE_METHODS == frozenset({"put_item", "update_item", "delete_item"})

    def test_raw_shape_keys(self):
        assert RAW_SHAPE_KEYS == frozenset({"field_overlay", "overrides", "fixed_overrides"})

    def test_sanctioned_writers_are_allow_listed(self):
        assert (
            "sam/members/repository/projection_config_write_repository.py"
            in RAW_WRITE_ALLOWED_FILES
        )
        assert (
            "sam/members/migration/functional_groups_list_to_map.py"
            in RAW_WRITE_ALLOWED_FILES
        )

    def test_response_shape_allow_list_uses_posix_paths(self):
        for path in RESPONSE_SHAPE_ALLOWED_FILES:
            assert "\\" not in path, f"{path} uses backslashes"
            assert path.startswith("sam/"), path

    def test_scan_dirs_targets_sam_plane(self):
        assert "sam" in SCAN_DIRS

    def test_excluded_dirs_prunes_build_output_and_caches(self):
        assert ".aws-sam" in EXCLUDED_DIRS
        assert "__pycache__" in EXCLUDED_DIRS
        assert ".venv" in EXCLUDED_DIRS
