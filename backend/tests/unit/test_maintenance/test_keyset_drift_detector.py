"""
Unit tests for KeySetDriftDetector
===================================

Covers the frozen expected-set vs schema/config source check that flags the
F1 feature-vs-test drift class: a schema dict grows a key (the Members
``mail_*`` config keys) while a test still asserts a hard-coded
``set(x.keys()) == {literal}`` — nothing catches the divergence until the
frozen-set assertion fails in CI.

The check is deliberately conservative — a frozen literal is matched to a
source dict only when they overlap strongly, and a schema module that cannot
be imported is skipped rather than reported.

Requirements: durable prevention for the F1 feature-vs-test drift class
(requirements Lesson 1 — grow a key set, update its paired frozen-set test).
"""

from __future__ import annotations

import sys
import textwrap

import pytest

from scripts.test_maintenance.keyset_drift_detector import (
    KeySetDriftDetector,
    _collect_imported_modules,
    _extract_frozen_expected_sets,
    _extract_string_set_literal,
    _is_set_keys_call,
    _best_matching_source,
)
import ast


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _FakeDependencyMap:
    """Minimal dependency map for testing the full-scan entry point."""

    def __init__(self, backend=None, frontend=None):
        self.backend = backend or {}
        self.frontend = frontend or {}
        self.untested = []


def _write_py(directory, filename, content):
    """Write a Python file and return its path as a string."""
    f = directory / filename
    f.write_text(textwrap.dedent(content), encoding="utf-8")
    return str(f)


@pytest.fixture
def importable_dir(tmp_path, monkeypatch):
    """A tmp dir placed on ``sys.path`` so schema modules can be imported.

    Yields the directory; any ``.py`` module written into it is importable by
    its bare module name for the duration of the test.
    """
    monkeypatch.syspath_prepend(str(tmp_path))
    # Drop any cached modules we create so each test re-imports fresh.
    created = []
    yield tmp_path
    for mod in created:
        sys.modules.pop(mod, None)


def _parse(source):
    return ast.parse(textwrap.dedent(source))


# ---------------------------------------------------------------------------
# _is_set_keys_call / _extract_string_set_literal
# ---------------------------------------------------------------------------


class TestSetKeysCallRecognition:
    """AST recognition of ``set(x.keys())``."""

    def test_is_set_keys_call_recognises_simple_form(self):
        node = _parse("set(x.keys())").body[0].value
        assert _is_set_keys_call(node) is True

    def test_is_set_keys_call_recognises_subscript_target(self):
        node = _parse("set(data['a']['b'].keys())").body[0].value
        assert _is_set_keys_call(node) is True

    def test_is_set_keys_call_rejects_plain_set_literal(self):
        node = _parse("{'a', 'b'}").body[0].value
        assert _is_set_keys_call(node) is False

    def test_is_set_keys_call_rejects_set_of_non_keys_call(self):
        node = _parse("set(x.values())").body[0].value
        assert _is_set_keys_call(node) is False


class TestExtractStringSetLiteral:
    """Extraction of frozen string set literals."""

    def test_extract_string_set_literal_plain_set(self):
        node = _parse("{'a', 'b', 'c'}").body[0].value
        assert _extract_string_set_literal(node) == {"a", "b", "c"}

    def test_extract_string_set_literal_unwraps_frozenset(self):
        node = _parse("frozenset({'a', 'b'})").body[0].value
        assert _extract_string_set_literal(node) == {"a", "b"}

    def test_extract_string_set_literal_rejects_non_string_member(self):
        node = _parse("{'a', 1}").body[0].value
        assert _extract_string_set_literal(node) is None

    def test_extract_string_set_literal_rejects_empty_set(self):
        # set() has no Set node; an empty {} is a dict, not a set.
        node = _parse("set()").body[0].value
        assert _extract_string_set_literal(node) is None


# ---------------------------------------------------------------------------
# _extract_frozen_expected_sets
# ---------------------------------------------------------------------------


class TestExtractFrozenExpectedSets:
    """Finding ``set(x.keys()) == {literal}`` comparisons."""

    def test_extract_frozen_sets_keys_on_left(self):
        tree = _parse("assert set(x.keys()) == {'a', 'b'}")
        found = _extract_frozen_expected_sets(tree)
        assert len(found) == 1
        assert found[0].keys == {"a", "b"}

    def test_extract_frozen_sets_keys_on_right(self):
        tree = _parse("assert {'a', 'b'} == set(x.keys())")
        found = _extract_frozen_expected_sets(tree)
        assert len(found) == 1
        assert found[0].keys == {"a", "b"}

    def test_extract_frozen_sets_skips_comparison_against_variable(self):
        tree = _parse("assert set(x.keys()) == expected_keys")
        found = _extract_frozen_expected_sets(tree)
        assert found == []

    def test_extract_frozen_sets_skips_non_eq_comparison(self):
        tree = _parse("assert set(x.keys()) <= {'a', 'b'}")
        found = _extract_frozen_expected_sets(tree)
        assert found == []


# ---------------------------------------------------------------------------
# _collect_imported_modules
# ---------------------------------------------------------------------------


class TestCollectImportedModules:
    """Collecting the dotted module names a test imports."""

    def test_collect_import_and_from_import(self):
        tree = _parse(
            """
            import services.parameter_schema
            from services.other import thing
            """
        )
        mods = _collect_imported_modules(tree)
        assert "services.parameter_schema" in mods
        assert "services.other" in mods

    def test_collect_skips_relative_import(self):
        tree = _parse("from . import sibling")
        assert _collect_imported_modules(tree) == []


# ---------------------------------------------------------------------------
# _best_matching_source
# ---------------------------------------------------------------------------


class TestBestMatchingSource:
    """Overlap gating of the frozen literal against source key sets."""

    def test_best_match_prefers_strongest_overlap(self):
        literal = {"a", "b", "c"}
        sources = [
            ("m", "unrelated", {"x", "y", "z", "a"}),
            ("m", "schema", {"a", "b", "c", "d"}),
        ]
        match = _best_matching_source(literal, sources)
        assert match is not None
        assert match[1] == "schema"

    def test_best_match_returns_none_below_overlap_threshold(self):
        literal = {"a", "b", "c", "d", "e"}
        # Only one key overlaps — far below the 60% threshold.
        sources = [("m", "fixture", {"a", "zz", "yy", "ww", "vv", "uu"})]
        assert _best_matching_source(literal, sources) is None


# ---------------------------------------------------------------------------
# detect_keyset_drift — the F1 shape (schema grew)
# ---------------------------------------------------------------------------


class TestDetectKeysetDrift:
    """End-to-end per-file detection against importable schema modules."""

    def test_detect_drift_schema_grew_flags_missing_keys(self, importable_dir):
        """A schema with extra keys the frozen literal lacks is flagged.

        This is the exact F1 shape: ``PARAMETER_SCHEMA`` nested params gained
        ``mail_domain`` / ``mail_local_part`` / ``mail_certified`` but the
        test still froze the old four-key set.
        """
        _write_py(
            importable_dir,
            "sample_schema_grew.py",
            """
            PARAMETER_SCHEMA = {
                "members": {
                    "module": "MEMBERS",
                    "params": {
                        "field_overlay": {},
                        "scope_dimensions": {},
                        "view_contexts": {},
                        "mail_enabled": {},
                        "mail_domain": {},
                        "mail_local_part": {},
                        "mail_certified": {},
                    },
                },
            }
            """,
        )
        test = _write_py(
            importable_dir,
            "test_sample_grew.py",
            """
            import sample_schema_grew

            def test_members_params_keys():
                params = sample_schema_grew.PARAMETER_SCHEMA['members']['params']
                assert set(params.keys()) == {
                    'field_overlay', 'scope_dimensions',
                    'view_contexts', 'mail_enabled',
                }
            """,
        )

        issues = KeySetDriftDetector().detect_keyset_drift(test)

        assert len(issues) == 1
        issue = issues[0]
        assert issue.drift_type == "keyset_drift"
        assert issue.severity == "high"
        assert set(issue.missing_from_test) == {
            "mail_domain", "mail_local_part", "mail_certified",
        }
        assert issue.extra_in_test == []
        assert issue.source_module == "sample_schema_grew"
        assert "mail_domain" in issue.description

    def test_detect_drift_in_sync_schema_no_issue(self, importable_dir):
        """A frozen literal matching the source exactly yields no drift."""
        _write_py(
            importable_dir,
            "sample_schema_sync.py",
            """
            CONFIG = {"a": 1, "b": 2, "c": 3}
            """,
        )
        test = _write_py(
            importable_dir,
            "test_sample_sync.py",
            """
            import sample_schema_sync

            def test_config_keys():
                assert set(sample_schema_sync.CONFIG.keys()) == {'a', 'b', 'c'}
            """,
        )

        issues = KeySetDriftDetector().detect_keyset_drift(test)
        assert issues == []

    def test_detect_drift_schema_shrank_flags_extra_keys(self, importable_dir):
        """A key removed/renamed from the source surfaces as extra_in_test."""
        _write_py(
            importable_dir,
            "sample_schema_shrank.py",
            """
            CONFIG = {"a": 1, "b": 2}
            """,
        )
        test = _write_py(
            importable_dir,
            "test_sample_shrank.py",
            """
            import sample_schema_shrank

            def test_config_keys():
                assert set(sample_schema_shrank.CONFIG.keys()) == {'a', 'b', 'c'}
            """,
        )

        issues = KeySetDriftDetector().detect_keyset_drift(test)
        assert len(issues) == 1
        assert issues[0].extra_in_test == ["c"]
        assert issues[0].missing_from_test == []

    def test_detect_drift_unimportable_module_no_false_positive(
        self, importable_dir
    ):
        """A frozen set whose module cannot be imported is skipped."""
        test = _write_py(
            importable_dir,
            "test_sample_unimportable.py",
            """
            import totally_made_up_schema_pkg_zzz

            def test_keys():
                data = totally_made_up_schema_pkg_zzz.THING
                assert set(data.keys()) == {'a', 'b', 'c'}
            """,
        )

        issues = KeySetDriftDetector().detect_keyset_drift(test)
        assert issues == []

    def test_detect_drift_unrelated_fixture_dict_no_false_positive(
        self, importable_dir
    ):
        """A frozen literal that overlaps weakly with any source is ignored."""
        _write_py(
            importable_dir,
            "sample_schema_unrelated.py",
            """
            CONFIG = {"alpha": 1, "beta": 2, "gamma": 3, "delta": 4}
            """,
        )
        test = _write_py(
            importable_dir,
            "test_sample_unrelated.py",
            """
            import sample_schema_unrelated  # noqa: F401

            def test_response_shape():
                # A response dict unrelated to CONFIG — only incidental overlap.
                resp = {}
                assert set(resp.keys()) == {
                    'status', 'body', 'headers', 'cookies', 'alpha',
                }
            """,
        )

        issues = KeySetDriftDetector().detect_keyset_drift(test)
        assert issues == []

    def test_detect_drift_missing_file_returns_empty(self):
        """A non-existent test file yields no issues."""
        assert KeySetDriftDetector().detect_keyset_drift(
            "/nope/test_x.py"
        ) == []


# ---------------------------------------------------------------------------
# detect_all_keyset_drift — full-scan entry point
# ---------------------------------------------------------------------------


class TestDetectAllKeysetDrift:
    """Key-set drift surfaced via the dependency-map scan entry point."""

    def test_detect_all_includes_keyset_issues(self, importable_dir):
        _write_py(
            importable_dir,
            "sample_schema_all.py",
            """
            CONFIG = {"a": 1, "b": 2, "c": 3, "d": 4}
            """,
        )
        src = _write_py(importable_dir, "src_all.py", "X = 1\n")
        test = _write_py(
            importable_dir,
            "test_src_all.py",
            """
            import sample_schema_all

            def test_keys():
                assert set(sample_schema_all.CONFIG.keys()) == {'a', 'b', 'c'}
            """,
        )

        dep_map = _FakeDependencyMap(backend={src: [test]})
        issues = KeySetDriftDetector(dep_map).detect_all_keyset_drift()

        assert len(issues) == 1
        assert issues[0].missing_from_test == ["d"]

    def test_detect_all_dedupes_test_files(self, importable_dir):
        """A test mapped to multiple sources is scanned once."""
        _write_py(
            importable_dir,
            "sample_schema_dedupe.py",
            """
            CONFIG = {"a": 1, "b": 2, "c": 3, "d": 4}
            """,
        )
        src1 = _write_py(importable_dir, "src_one.py", "A = 1\n")
        src2 = _write_py(importable_dir, "src_two.py", "B = 2\n")
        test = _write_py(
            importable_dir,
            "test_src_dedupe.py",
            """
            import sample_schema_dedupe

            def test_keys():
                assert set(sample_schema_dedupe.CONFIG.keys()) == {'a', 'b', 'c'}
            """,
        )

        dep_map = _FakeDependencyMap(backend={src1: [test], src2: [test]})
        issues = KeySetDriftDetector(dep_map).detect_all_keyset_drift()

        # Scanned once despite two source mappings → exactly one issue.
        assert len(issues) == 1
