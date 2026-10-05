"""
Unit tests for DriftDetector patch-target resolution
=====================================================

Covers the changed-symbol test-reference check that flags ``@patch`` /
``patch.object`` targets whose trailing attribute is no longer reachable on
the module it resolves to (the F1 class of fix-induced test regression: a
lint autofix removes an import, orphaning a patch target).

The check is deliberately conservative — targets whose module prefix cannot
be imported are skipped rather than reported.

Requirements: durable prevention for the F1 fix-induced regression class.
"""

from __future__ import annotations

import textwrap

from scripts.test_maintenance.drift_detector import (
    DriftDetector,
    _extract_patch_targets,
    _resolve_patch_target,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _FakeDependencyMap:
    """Minimal dependency map for testing."""

    def __init__(self, backend=None, frontend=None):
        self.backend = backend or {}
        self.frontend = frontend or {}
        self.untested = []


def _write_py(tmp_path, filename, content):
    """Write a Python file and return its path as a string."""
    f = tmp_path / filename
    f.write_text(textwrap.dedent(content), encoding="utf-8")
    return str(f)


# ---------------------------------------------------------------------------
# _extract_patch_targets
# ---------------------------------------------------------------------------


class TestExtractPatchTargets:
    """Tests for the AST extraction of patch targets."""

    def test_extract_patch_targets_decorator_returns_string_target(self, tmp_path):
        """A ``@patch("a.b.c")`` decorator yields its dotted string target."""
        test = _write_py(
            tmp_path,
            "test_x.py",
            """\
            from unittest.mock import patch

            @patch("routes.landing_page_routes.os")
            def test_thing(mock_os):
                pass
        """,
        )

        targets = _extract_patch_targets(test)

        assert "routes.landing_page_routes.os" in {t for _, t in targets}

    def test_extract_patch_targets_call_form_returns_string_target(self, tmp_path):
        """A ``patch("a.b.c")`` call (context manager) is extracted."""
        test = _write_py(
            tmp_path,
            "test_x.py",
            """\
            from unittest.mock import patch

            def test_thing():
                with patch("services.my_service.helper") as m:
                    m.return_value = 1
        """,
        )

        targets = _extract_patch_targets(test)

        assert "services.my_service.helper" in {t for _, t in targets}

    def test_extract_patch_targets_patch_object_builds_dotted_path(self, tmp_path):
        """``patch.object(obj, "name")`` becomes ``<obj>.<name>``."""
        test = _write_py(
            tmp_path,
            "test_x.py",
            """\
            from unittest.mock import patch
            import services.my_service

            def test_thing():
                with patch.object(services.my_service, "helper"):
                    pass
        """,
        )

        targets = _extract_patch_targets(test)

        assert "services.my_service.helper" in {t for _, t in targets}

    def test_extract_patch_targets_skips_patch_dict(self, tmp_path):
        """``patch.dict`` is not a single-attribute target and is skipped."""
        test = _write_py(
            tmp_path,
            "test_x.py",
            """\
            from unittest.mock import patch

            def test_thing():
                with patch.dict("os.environ", {"A": "1"}):
                    pass
        """,
        )

        targets = _extract_patch_targets(test)

        assert all("environ" not in t for _, t in targets)

    def test_extract_patch_targets_skips_non_dotted_string(self, tmp_path):
        """A bare (dot-less) target string is skipped — not resolvable."""
        test = _write_py(
            tmp_path,
            "test_x.py",
            """\
            from unittest.mock import patch

            @patch("builtins")
            def test_thing(m):
                pass
        """,
        )

        targets = _extract_patch_targets(test)

        assert targets == []

    def test_extract_patch_targets_missing_file_returns_none(self):
        """A non-existent file yields ``None`` (unreadable)."""
        assert _extract_patch_targets("/nonexistent/test_x.py") is None


# ---------------------------------------------------------------------------
# _resolve_patch_target
# ---------------------------------------------------------------------------


class TestResolvePatchTarget:
    """Tests for resolving a dotted target against the environment."""

    def test_resolve_patch_target_existing_attribute_returns_no_gap(self):
        """A real stdlib attribute (``json.dumps``) resolves fully."""
        missing, container = _resolve_patch_target("json.dumps")

        assert missing is None
        assert container == "json.dumps"

    def test_resolve_patch_target_intermediate_module_resolves(self):
        """A submodule-qualified attribute (``os.path.join``) resolves."""
        missing, container = _resolve_patch_target("os.path.join")

        assert missing is None
        assert container == "os.path.join"

    def test_resolve_patch_target_removed_attribute_reports_gap(self):
        """An attribute absent from an importable module is reported."""
        missing, container = _resolve_patch_target("json.this_attr_does_not_exist_xyz")

        assert missing == "this_attr_does_not_exist_xyz"
        assert container == "json"

    def test_resolve_patch_target_unimportable_module_returns_none(self):
        """A target whose module cannot be imported is skipped (None)."""
        result = _resolve_patch_target("totally_made_up_pkg_zzz.module.symbol")

        assert result is None


# ---------------------------------------------------------------------------
# detect_patch_target_drift
# ---------------------------------------------------------------------------


class TestDetectPatchTargetDrift:
    """Tests for the public drift-detection method."""

    def test_detect_patch_target_drift_dangling_target_flagged(self, tmp_path):
        """A patch target whose attribute was removed is flagged as drift."""
        test = _write_py(
            tmp_path,
            "test_x.py",
            """\
            from unittest.mock import patch

            @patch("json.this_attr_does_not_exist_xyz")
            def test_thing(mock_attr):
                pass
        """,
        )

        detector = DriftDetector(_FakeDependencyMap())
        issues = detector.detect_patch_target_drift(test)

        assert len(issues) == 1
        issue = issues[0]
        assert issue.drift_type == "patch_target_unresolved"
        assert issue.severity == "high"
        assert issue.old_value == "json.this_attr_does_not_exist_xyz"
        assert issue.test_file == test
        assert "this_attr_does_not_exist_xyz" in issue.new_value

    def test_detect_patch_target_drift_valid_target_no_issue(self, tmp_path):
        """A patch target that still resolves produces no drift."""
        test = _write_py(
            tmp_path,
            "test_x.py",
            """\
            from unittest.mock import patch

            @patch("json.dumps")
            def test_thing(mock_dumps):
                pass
        """,
        )

        detector = DriftDetector(_FakeDependencyMap())
        issues = detector.detect_patch_target_drift(test)

        assert issues == []

    def test_detect_patch_target_drift_unimportable_module_no_false_positive(
        self, tmp_path
    ):
        """An unresolvable module prefix is skipped, not reported."""
        test = _write_py(
            tmp_path,
            "test_x.py",
            """\
            from unittest.mock import patch

            @patch("totally_made_up_pkg_zzz.module.symbol")
            def test_thing(m):
                pass
        """,
        )

        detector = DriftDetector(_FakeDependencyMap())
        issues = detector.detect_patch_target_drift(test)

        assert issues == []

    def test_detect_patch_target_drift_mixed_targets_flags_only_dangling(
        self, tmp_path
    ):
        """Only the dangling target among several is flagged."""
        test = _write_py(
            tmp_path,
            "test_x.py",
            """\
            from unittest.mock import patch

            @patch("json.dumps")
            @patch("json.gone_attr_abc")
            @patch("unresolvable_pkg_qqq.thing")
            def test_thing(a, b, c):
                pass
        """,
        )

        detector = DriftDetector(_FakeDependencyMap())
        issues = detector.detect_patch_target_drift(test)

        assert len(issues) == 1
        assert issues[0].old_value == "json.gone_attr_abc"

    def test_detect_patch_target_drift_missing_file_returns_empty(self):
        """A non-existent test file yields no issues."""
        detector = DriftDetector(_FakeDependencyMap())
        assert detector.detect_patch_target_drift("/nope/test_x.py") == []


# ---------------------------------------------------------------------------
# Integration with detect_all_drift
# ---------------------------------------------------------------------------


class TestDetectAllDriftPatchTargets:
    """Patch-target drift is surfaced via the full scan entry point."""

    def test_detect_all_drift_includes_patch_target_issues(self, tmp_path):
        """detect_all_drift scans mapped test files for dangling patches."""
        src = _write_py(
            tmp_path,
            "service.py",
            """\
            def process(data):
                return data
        """,
        )
        test = _write_py(
            tmp_path,
            "test_service.py",
            """\
            from unittest.mock import patch

            @patch("json.gone_attr_def")
            def test_process(m):
                pass
        """,
        )

        dep_map = _FakeDependencyMap(backend={src: [test]})
        detector = DriftDetector(dep_map)
        issues = detector.detect_all_drift()

        patch_issues = [i for i in issues if i.drift_type == "patch_target_unresolved"]
        assert len(patch_issues) == 1
        assert patch_issues[0].old_value == "json.gone_attr_def"

    def test_detect_all_drift_dedupes_test_files(self, tmp_path):
        """A test file mapped to multiple sources is scanned once."""
        src1 = _write_py(tmp_path, "a.py", "def f(x):\n    return x\n")
        src2 = _write_py(tmp_path, "b.py", "def g(y):\n    return y\n")
        test = _write_py(
            tmp_path,
            "test_ab.py",
            """\
            from unittest.mock import patch

            @patch("json.gone_attr_ghi")
            def test_both(m):
                pass
        """,
        )

        dep_map = _FakeDependencyMap(backend={src1: [test], src2: [test]})
        detector = DriftDetector(dep_map)
        issues = detector.detect_all_drift()

        patch_issues = [i for i in issues if i.drift_type == "patch_target_unresolved"]
        # Scanned once despite two source mappings → exactly one issue.
        assert len(patch_issues) == 1
