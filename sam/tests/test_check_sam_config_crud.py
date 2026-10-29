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

import pytest  # noqa: E402

from check_sam_config_crud import (  # noqa: E402
    RAW_WRITE_METHODS,
    RAW_SHAPE_KEYS,
    RAW_WRITE_ALLOWED_FILES,
    RESPONSE_SHAPE_ALLOWED_FILES,
    SCAN_DIRS,
    EXCLUDED_DIRS,
    VOCAB_KEY,
    WRITE_PATH_FILES,
    VOCAB_CONSUMER_DIRS,
    check_file,
    check_file_report_only,
    scan_directory,
    scan_directory_report_only,
    main,
    _is_dotted_group_key,
)


def run_main(file_paths) -> int:
    """Run the guard's ``main`` over ``file_paths`` (single-file mode) and return its exit code.

    ``main`` calls ``sys.exit`` (so the shell sees the code); we capture the ``SystemExit`` and
    return its integer code. This is how the planted-violation tests prove the guard actually
    BLOCKS (exit 1) rather than merely reporting — the post-task-12 blocking contract.
    """
    with pytest.raises(SystemExit) as exc:
        main([str(p) for p in file_paths])
    code = exc.value.code
    return 0 if code is None else int(code)


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


# ═══════════════════════════════════════════════════════════════════════════════════════════
# 03a anti-reintroduction rules (a)(b)(d) — now BLOCKING (design C8, R2.7; 03a task 12).
#
# Each rule gets a PLANTED-VIOLATION proof: plant the retired pattern → the guard DETECTS it (via
# ``check_file_report_only``) AND ``main`` exits NON-ZERO on it (the guard FAILS the build); the
# clean/current shape → no finding and ``main`` exits ZERO. The two detection helpers remain
# SEPARATE entry points so each rule family can be exercised in isolation, but after the task-12
# flip a finding from either family fails the build — asserted here through ``main`` /
# :func:`run_main` so the proof is "plant → FAILS, revert → passes", not merely "reported".
# ═══════════════════════════════════════════════════════════════════════════════════════════

# A write-surface module path rule (a) scans (one of WRITE_PATH_FILES), and a vocabulary-consumer
# module path rules (b)/(d) scan (under VOCAB_CONSUMER_DIRS). Both are the real repo-relative
# layout so the scope predicates match exactly as a full scan would.
_WRITE_PATH_REL = "sam/members/domain/config_fields_crud_service.py"
_CONSUMER_REL = "sam/members/repository/_fields_overlay_reader.py"
_SERIALIZER_REL = "sam/members/domain/_membership_catalog.py"
_WRITE_VALIDATOR_REL = "sam/members/domain/config_write_service.py"


# ─────────────────────────────────────────────────────────────────────────────────────────
# (a) a ``choices`` vocabulary key on the config#fields WRITE path
# ─────────────────────────────────────────────────────────────────────────────────────────


class TestRuleAChoicesOnWritePath:
    """Rule (a): ``choices`` re-added to the config#fields WRITE surface (03a C2, retired)."""

    def test_planted_choices_in_definition_attrs_set_is_reported(self, tmp_path):
        """A PLANTED ``"choices"`` element in a FIELD_DEFINITION_ATTRS frozenset is REPORTED."""
        f = _write(
            tmp_path,
            _WRITE_PATH_REL,
            """\
            FIELD_DEFINITION_ATTRS = frozenset(
                {"type", "label", "options", "choices", "scope"}
            )
            """,
        )
        findings = check_file_report_only(f)
        assert len(findings) == 1
        assert "choices" in findings[0]
        assert "rule (a)" in findings[0]
        # BLOCKING (task 12): the guard FAILS the build on this plant.
        assert run_main([f]) == 1

    def test_planted_choices_dict_key_in_write_payload_is_reported(self, tmp_path):
        """A PLANTED ``choices`` dict-literal key in a write payload is REPORTED."""
        f = _write(
            tmp_path,
            _WRITE_PATH_REL,
            """\
            def build_write(values):
                return {"options": values, "choices": values}
            """,
        )
        findings = check_file_report_only(f)
        assert len(findings) == 1
        assert "choices" in findings[0]
        assert "rule (a)" in findings[0]
        # BLOCKING (task 12): the guard FAILS the build on this plant.
        assert run_main([f]) == 1

    def test_clean_options_only_write_surface_has_no_finding(self, tmp_path):
        """The current ``options``-only write definition-attr set yields NO rule-(a) finding."""
        f = _write(
            tmp_path,
            _WRITE_PATH_REL,
            """\
            FIELD_DEFINITION_ATTRS = frozenset(
                {"type", "label", "order", "required", "visible", "options", "scope"}
            )
            """,
        )
        assert check_file_report_only(f) == []
        # BLOCKING (task 12): revert → the guard PASSES (exit 0).
        assert run_main([f]) == 0

    def test_sanctioned_remove_legacy_choices_op_is_not_reported(self, tmp_path):
        """``remove_legacy_choices`` naming ``"choices"`` as a REMOVE path SEGMENT is clean.

        It appears as a LIST element (an op path segment) and in a ``"choices" not in stored``
        membership Compare — neither a set element nor a dict key — so rule (a) does not flag the
        one sanctioned migration op.
        """
        f = _write(
            tmp_path,
            _WRITE_PATH_REL,
            """\
            def remove_legacy_choices(placement, stored):
                if "choices" not in stored:
                    return {"no_op": True}
                return {"action": "REMOVE", "path": [placement["map"], placement["key"], "choices"]}
            """,
        )
        assert check_file_report_only(f) == []

    def test_choices_key_outside_write_path_is_not_reported(self, tmp_path):
        """A ``choices`` definition-attr set in a NON-write-surface module is out of scope for (a)."""
        f = _write(
            tmp_path,
            "sam/members/domain/some_other_module.py",
            """\
            ATTRS = frozenset({"options", "choices"})
            """,
        )
        # Not in WRITE_PATH_FILES → rule (a) does not apply (rule (b)/(d) shapes are also absent).
        assert check_file_report_only(f) == []


# ─────────────────────────────────────────────────────────────────────────────────────────
# (b) an ``options or choices`` / ``choices or options`` fallback, or a get("choices") source read
# ─────────────────────────────────────────────────────────────────────────────────────────


class TestRuleBVocabularyFallback:
    """Rule (b): the retired two-names vocabulary fallback shapes (F1/F9/F10/F12)."""

    def test_planted_options_or_choices_coalesce_is_reported(self, tmp_path):
        """A PLANTED ``field.options or field.choices`` coalesce in a reader is REPORTED."""
        f = _write(
            tmp_path,
            _CONSUMER_REL,
            """\
            def resolve(field):
                return field.options or field.choices
            """,
        )
        findings = check_file_report_only(f)
        assert len(findings) == 1
        assert "rule (b)" in findings[0]
        # BLOCKING (task 12): the guard FAILS the build on this plant.
        assert run_main([f]) == 1

    def test_planted_choices_or_options_coalesce_is_reported(self, tmp_path):
        """The reversed ``field.choices or field.options`` coalesce is REPORTED too."""
        f = _write(
            tmp_path,
            _CONSUMER_REL,
            """\
            def resolve(field):
                return field.choices or field.options
            """,
        )
        findings = check_file_report_only(f)
        assert len(findings) == 1
        assert "rule (b)" in findings[0]
        # BLOCKING (task 12): the guard FAILS the build on this plant.
        assert run_main([f]) == 1

    def test_planted_get_choices_source_read_in_validator_is_reported(self, tmp_path):
        """A PLANTED ``spec.get("choices")`` vocabulary-source read (F12 shape) is REPORTED."""
        f = _write(
            tmp_path,
            _WRITE_VALIDATOR_REL,
            """\
            def field_choice_values(spec):
                return _collect(spec.get("options")) or _collect(spec.get("choices"))
            """,
        )
        findings = check_file_report_only(f)
        # The coalesce (b1) AND the get("choices") source read (b2) both match — dedup by lineno
        # collapses them to ONE finding on that line.
        assert len(findings) == 1
        assert "rule (b)" in findings[0]
        # BLOCKING (task 12): the guard FAILS the build on this plant.
        assert run_main([f]) == 1

    def test_fail_loud_choices_read_is_not_reported(self, tmp_path):
        """A C6 fail-loud ``if field.choices: raise …`` (NOT a coalesce) yields NO finding.

        The retired SHAPE is the ``X or Y`` coalesce; a bare ``field.choices`` read that feeds a
        loud raise (the asymmetry boundary) is legitimate and must not be flagged.
        """
        f = _write(
            tmp_path,
            "sam/members/domain/_membership_writes_fieldconfig.py",
            """\
            def public_field_options(field, tenant_id):
                if field.options:
                    return [dict(o) for o in field.options]
                if field.choices:
                    raise UnpropagatedVocabularyError(tenant_id, field.key, kind="inline-enum")
                return None
            """,
        )
        assert check_file_report_only(f) == []
        # BLOCKING (task 12): a legitimate fail-loud read does NOT fail the build (exit 0).
        assert run_main([f]) == 0

    def test_clean_options_only_serializer_has_no_finding(self, tmp_path):
        """A serializer reading only ``field_options`` (the seam's one options) is clean for (b)."""
        f = _write(
            tmp_path,
            _SERIALIZER_REL,
            """\
            def serialize_field(field, field_options):
                payload = {}
                payload["options"] = (
                    [dict(o) for o in field_options] if field_options is not None else None
                )
                return payload
            """,
        )
        assert check_file_report_only(f) == []
        # BLOCKING (task 12): revert → the guard PASSES (exit 0).
        assert run_main([f]) == 0

    def test_coalesce_outside_consumer_layer_is_not_reported(self, tmp_path):
        """An ``options or choices`` coalesce in a non-consumer module is out of scope for (b)."""
        f = _write(
            tmp_path,
            "sam/tests/helpers/vocab.py",
            """\
            def resolve(field):
                return field.options or field.choices
            """,
        )
        assert check_file_report_only(f) == []


# ─────────────────────────────────────────────────────────────────────────────────────────
# (d) FieldScope.values populated independently of options
# ─────────────────────────────────────────────────────────────────────────────────────────


class TestRuleDScopeValuesIndependence:
    """Rule (d): scope ``values`` re-split from ``options`` (the FieldScope(values=()) divergence)."""

    def test_planted_fieldscope_values_kwarg_is_reported(self, tmp_path):
        """A PLANTED ``FieldScope(values=…)`` construction is REPORTED."""
        f = _write(
            tmp_path,
            _CONSUMER_REL,
            """\
            def build_scope(spec, values):
                return FieldScope(enabled=True, values=values)
            """,
        )
        findings = check_file_report_only(f)
        assert len(findings) == 1
        assert "rule (d)" in findings[0]
        # BLOCKING (task 12): the guard FAILS the build on this plant.
        assert run_main([f]) == 1

    def test_planted_scope_values_assignment_is_reported(self, tmp_path):
        """A PLANTED assignment to a scope ``.values`` attribute is REPORTED."""
        f = _write(
            tmp_path,
            _CONSUMER_REL,
            """\
            def build_scope(field, values):
                field.scope.values = values
                return field
            """,
        )
        findings = check_file_report_only(f)
        assert len(findings) == 1
        assert "rule (d)" in findings[0]
        # BLOCKING (task 12): the guard FAILS the build on this plant.
        assert run_main([f]) == 1

    def test_clean_options_only_fieldscope_has_no_finding(self, tmp_path):
        """The current ``FieldScope(options=options)`` construction (values DERIVED) is clean."""
        f = _write(
            tmp_path,
            _CONSUMER_REL,
            """\
            def build_scope(spec, options):
                return FieldScope(enabled=True, options=options)
            """,
        )
        assert check_file_report_only(f) == []
        # BLOCKING (task 12): revert → the guard PASSES (exit 0).
        assert run_main([f]) == 0

    def test_fieldscope_values_outside_consumer_layer_is_not_reported(self, tmp_path):
        """A ``FieldScope(values=…)`` in a non-consumer module is out of scope for (d)."""
        f = _write(
            tmp_path,
            "sam/tests/fixtures/scopes.py",
            """\
            FIXTURE = FieldScope(values=("a", "b"))
            """,
        )
        assert check_file_report_only(f) == []


# ─────────────────────────────────────────────────────────────────────────────────────────
# Blocking semantics: the 03a rules (a)(b)(d) now FAIL the build (task-12 flip, G6)
# ─────────────────────────────────────────────────────────────────────────────────────────


class TestBlockingSemantics:
    """The 03a rules (a)(b)(d) are now BLOCKING: a finding fails the build (exit 1) via ``main``.

    The two detection helpers stay SEPARATE entry points: ``check_file`` returns ONLY the two
    original spec-03 findings and ``check_file_report_only`` returns ONLY the 03a rule (a/b/d)
    findings — so a rule-(a) plant is still absent from ``check_file`` at the function level. The
    BLOCKING contract lives in ``main``, which folds BOTH families into the exit code; these tests
    assert that contract directly (plant → exit 1, revert → exit 0).
    """

    def test_planted_rule_a_violation_fails_the_build(self, tmp_path):
        """A planted rule-(a) violation makes the guard EXIT NON-ZERO (the task-12 blocking flip).

        ``check_file`` (the spec-03 family) is still empty for a rule-(a) plant — the families are
        reported by separate entry points — but ``main`` now FAILS the build on the rule-(a)
        finding.
        """
        f = _write(
            tmp_path,
            _WRITE_PATH_REL,
            """\
            FIELD_DEFINITION_ATTRS = frozenset({"options", "choices"})
            """,
        )
        assert check_file_report_only(f)      # detected by the 03a family
        assert check_file(f) == []            # not a spec-03-family finding (separate entry point)
        assert run_main([f]) == 1             # BLOCKING: the guard fails the build

    def test_scan_directory_report_only_aggregates_findings(self, tmp_path):
        """``scan_directory_report_only`` aggregates rule findings across the tree."""
        _write(
            tmp_path,
            _CONSUMER_REL,
            "def resolve(field):\n    return field.options or field.choices\n",
        )
        _write(
            tmp_path,
            "sam/members/domain/clean.py",
            "def serialize(field, field_options):\n    return {'options': field_options}\n",
        )
        findings = scan_directory_report_only(tmp_path / "sam")
        assert len(findings) == 1
        assert "rule (b)" in findings[0]

    def test_scan_directory_report_only_skips_excluded_dirs(self, tmp_path):
        """A planted coalesce under an excluded build dir (.aws-sam) is not scanned."""
        _write(
            tmp_path,
            "sam/members/.aws-sam/build/copy/_fields_overlay_reader.py",
            "def resolve(field):\n    return field.options or field.choices\n",
        )
        assert scan_directory_report_only(tmp_path / "sam") == []

    def test_spec03_blocking_check_still_fails_the_build(self, tmp_path):
        """A planted spec-03 raw-write violation also fails the build via ``main`` (unchanged)."""
        f = _write(
            tmp_path,
            "sam/members/repository/rogue_config_writer.py",
            _gov("def w(table, i):\n    table.put_item(Item=i)\n"),
        )
        assert check_file(f)                  # spec-03 blocking finding present
        assert run_main([f]) == 1             # still BLOCKING

    def test_clean_file_passes_the_build(self, tmp_path):
        """A clean options-only file makes the guard EXIT ZERO (no finding in either family)."""
        f = _write(
            tmp_path,
            _SERIALIZER_REL,
            "def serialize(field, field_options):\n    return {'options': field_options}\n",
        )
        assert check_file(f) == []
        assert check_file_report_only(f) == []
        assert run_main([f]) == 0             # BLOCKING contract: clean tree passes


class TestRule03aConfig:
    """Module-level configuration sanity checks for the 03a rules."""

    def test_vocab_key_is_choices(self):
        assert VOCAB_KEY == "choices"

    def test_write_path_files_use_posix_paths(self):
        for path in WRITE_PATH_FILES:
            assert "\\" not in path, f"{path} uses backslashes"
            assert path.startswith("sam/"), path
        assert "sam/members/domain/config_fields_crud_service.py" in WRITE_PATH_FILES
        assert "sam/members/domain/config_write_service.py" in WRITE_PATH_FILES

    def test_vocab_consumer_dirs_target_members_domain_and_repository(self):
        assert "sam/members/domain/" in VOCAB_CONSUMER_DIRS
        assert "sam/members/repository/" in VOCAB_CONSUMER_DIRS
