"""
Property-based tests for DriftDetector
=======================================

Uses Hypothesis to verify that the drift detector correctly identifies
signature and key drift between source and test files.

Properties tested:
    - Property 12: Source-test drift detection
"""

from __future__ import annotations

import os
import textwrap

import pytest
from hypothesis import given, settings, HealthCheck, strategies as st

from scripts.test_maintenance.drift_detector import (
    DriftDetector,
    DriftIssue,
    VALID_DRIFT_TYPES,
    VALID_SEVERITIES,
)


# ---------------------------------------------------------------------------
# Strategies — generate parameter names and dict keys
# ---------------------------------------------------------------------------

# Valid Python identifier strategy (for parameter names)
_st_identifier = st.from_regex(r"[a-z][a-z0-9_]{0,15}", fullmatch=True).filter(
    lambda s: s not in {"self", "cls", "return", "import", "class", "def",
                        "if", "else", "for", "while", "try", "except",
                        "with", "as", "from", "in", "is", "not", "and",
                        "or", "pass", "break", "continue", "yield",
                        "lambda", "global", "nonlocal", "assert", "raise",
                        "del", "True", "False", "None"}
)

# Dict key strategy (business-like keys)
_st_dict_key = st.from_regex(r"[a-z][a-z0-9_]{2,20}", fullmatch=True).filter(
    lambda s: s not in {"return_value", "side_effect", "called",
                        "call_count", "type", "class", "module",
                        "name", "args", "kwargs", "self", "cls"}
)


# ---------------------------------------------------------------------------
# Helpers — create source and test files
# ---------------------------------------------------------------------------

def _write_source_file(tmp_path, func_name, params, dict_keys=None):
    """Create a source file with a function and optional dict return."""
    param_str = ", ".join(params)
    lines = [
        f"def {func_name}({param_str}):",
        f'    """Docstring for {func_name}."""',
    ]

    if dict_keys:
        dict_items = ", ".join(f"'{k}': None" for k in dict_keys)
        lines.append(f"    return {{{dict_items}}}")
    else:
        lines.append("    return None")

    lines.append("")

    src_file = tmp_path / "source.py"
    src_file.write_text("\n".join(lines), encoding="utf-8")
    return str(src_file)


def _write_test_file_with_call(tmp_path, func_name, call_kwargs):
    """Create a test file that calls a function with keyword arguments."""
    kwarg_str = ", ".join(f"{k}=None" for k in call_kwargs)
    lines = [
        "import pytest",
        "",
        f"def test_{func_name}():",
        f"    result = {func_name}({kwarg_str})",
        "    assert result is not None",
        "",
    ]

    test_file = tmp_path / "test_source.py"
    test_file.write_text("\n".join(lines), encoding="utf-8")
    return str(test_file)


def _write_test_file_with_dict_keys(tmp_path, func_name, test_keys):
    """Create a test file that references dictionary keys in assertions."""
    lines = [
        "import pytest",
        "",
        f"def test_{func_name}():",
        "    result = {",
    ]
    for key in test_keys:
        lines.append(f"        '{key}': 'value',")
    lines.append("    }")
    lines.append("    assert result is not None")
    lines.append("")

    test_file = tmp_path / "test_source.py"
    test_file.write_text("\n".join(lines), encoding="utf-8")
    return str(test_file)


class _FakeDependencyMap:
    """Minimal dependency map for testing."""

    def __init__(self, backend=None, frontend=None):
        self.backend = backend or {}
        self.frontend = frontend or {}
        self.untested = []


# ---------------------------------------------------------------------------
# Property 12: Source-test drift detection
# ---------------------------------------------------------------------------

# Feature: test-maintenance-framework, Property 12: Source-test drift detection
class TestSourceTestDriftDetection:
    """For any source file change modifying a function signature or
    dictionary key, and any dependent test file, the detector flags the
    test with a DriftIssue.
    """

    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.too_slow],
    )
    @given(
        func_name=_st_identifier,
        source_params=st.lists(_st_identifier, min_size=1, max_size=5, unique=True),
        extra_test_kwargs=st.lists(_st_identifier, min_size=1, max_size=3, unique=True),
    )
    def test_signature_drift_detected_for_removed_params(
        self,
        tmp_path_factory,
        func_name,
        source_params,
        extra_test_kwargs,
    ):
        """When a test calls a function with keyword arguments that no
        longer exist in the source signature, the detector flags it.
        """
        tmp_path = tmp_path_factory.mktemp("drift")

        # Ensure extra kwargs are not in source params
        extra_test_kwargs = [
            k for k in extra_test_kwargs if k not in source_params
        ]
        if not extra_test_kwargs:
            return  # Skip if all extra kwargs happen to be in source params

        # Source has source_params
        src_file = _write_source_file(tmp_path, func_name, source_params)

        # Test calls with source_params + extra_test_kwargs (the extras are "old" params)
        all_test_kwargs = source_params + extra_test_kwargs
        test_file = _write_test_file_with_call(
            tmp_path, func_name, all_test_kwargs
        )

        dep_map = _FakeDependencyMap()
        detector = DriftDetector(dep_map)
        issues = detector.detect_signature_drift(src_file, [test_file])

        # Should detect drift for the extra kwargs
        assert len(issues) > 0, (
            f"Expected signature drift for extra kwargs "
            f"{extra_test_kwargs} not in source params {source_params}"
        )

        for issue in issues:
            assert issue.source_file == src_file
            assert issue.test_file == test_file
            assert issue.drift_type == "signature_change"
            assert issue.drift_type in VALID_DRIFT_TYPES
            assert issue.severity in VALID_SEVERITIES
            assert issue.description, "DriftIssue must have a description"
            assert issue.old_value, "DriftIssue must have old_value"
            assert issue.new_value, "DriftIssue must have new_value"

    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.too_slow],
    )
    @given(
        func_name=_st_identifier,
        params=st.lists(_st_identifier, min_size=1, max_size=5, unique=True),
    )
    def test_no_drift_when_signatures_match(
        self,
        tmp_path_factory,
        func_name,
        params,
    ):
        """When test calls match the source signature exactly, no drift
        should be detected.
        """
        tmp_path = tmp_path_factory.mktemp("nodrift")

        src_file = _write_source_file(tmp_path, func_name, params)
        test_file = _write_test_file_with_call(tmp_path, func_name, params)

        dep_map = _FakeDependencyMap()
        detector = DriftDetector(dep_map)
        issues = detector.detect_signature_drift(src_file, [test_file])

        assert len(issues) == 0, (
            f"Expected no drift when signatures match. "
            f"Params: {params}, Issues: {issues}"
        )

    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.too_slow],
    )
    @given(
        func_name=_st_identifier,
        source_keys=st.lists(_st_dict_key, min_size=3, max_size=5, unique=True),
        extra_test_keys=st.lists(_st_dict_key, min_size=1, max_size=2, unique=True),
    )
    def test_key_drift_detected_for_removed_keys(
        self,
        tmp_path_factory,
        func_name,
        source_keys,
        extra_test_keys,
    ):
        """When a test references dictionary keys that no longer exist in
        the source, the detector flags it.

        The drift detector requires:
        - Source and test dicts with >= 3 keys each
        - >= 60% key overlap between test and best-matching source dict
        So we generate source dicts with 3-5 keys and 1-2 extra test keys,
        ensuring the overlap threshold is met.
        """
        tmp_path = tmp_path_factory.mktemp("keydrift")

        # Ensure extra keys are not in source keys
        extra_test_keys = [
            k for k in extra_test_keys if k not in source_keys
        ]
        if not extra_test_keys:
            return  # Skip if all extra keys happen to be in source keys

        src_file = _write_source_file(
            tmp_path, func_name, ["data"], dict_keys=source_keys
        )

        # Test references source_keys + extra_test_keys
        all_test_keys = source_keys + extra_test_keys
        test_file = _write_test_file_with_dict_keys(
            tmp_path, func_name, all_test_keys
        )

        dep_map = _FakeDependencyMap()
        detector = DriftDetector(dep_map)
        issues = detector.detect_key_drift(src_file, [test_file])

        # Should detect drift for the extra keys
        assert len(issues) > 0, (
            f"Expected key drift for extra keys "
            f"{extra_test_keys} not in source keys {source_keys}"
        )

        for issue in issues:
            assert issue.source_file == src_file
            assert issue.test_file == test_file
            assert issue.drift_type == "key_rename"
            assert issue.drift_type in VALID_DRIFT_TYPES
            assert issue.severity in VALID_SEVERITIES
            assert issue.description, "DriftIssue must have a description"

    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.too_slow],
    )
    @given(
        func_name=_st_identifier,
        keys=st.lists(_st_dict_key, min_size=1, max_size=5, unique=True),
    )
    def test_no_key_drift_when_keys_match(
        self,
        tmp_path_factory,
        func_name,
        keys,
    ):
        """When test dict keys match the source exactly, no drift should
        be detected.
        """
        tmp_path = tmp_path_factory.mktemp("nokeydrift")

        src_file = _write_source_file(
            tmp_path, func_name, ["data"], dict_keys=keys
        )
        test_file = _write_test_file_with_dict_keys(
            tmp_path, func_name, keys
        )

        dep_map = _FakeDependencyMap()
        detector = DriftDetector(dep_map)
        issues = detector.detect_key_drift(src_file, [test_file])

        assert len(issues) == 0, (
            f"Expected no key drift when keys match. "
            f"Keys: {keys}, Issues: {issues}"
        )

    # ------------------------------------------------------------------
    # Edge cases
    # ------------------------------------------------------------------

    def test_nonexistent_source_produces_no_issues(self, tmp_path):
        """A nonexistent source file should produce zero drift issues."""
        dep_map = _FakeDependencyMap()
        detector = DriftDetector(dep_map)

        issues = detector.detect_signature_drift(
            "/nonexistent/source.py",
            [str(tmp_path / "test.py")],
        )
        assert issues == []

    def test_nonexistent_test_produces_no_issues(self, tmp_path):
        """A nonexistent test file should produce zero drift issues."""
        src_file = _write_source_file(tmp_path, "func", ["a", "b"])

        dep_map = _FakeDependencyMap()
        detector = DriftDetector(dep_map)

        issues = detector.detect_signature_drift(
            src_file,
            ["/nonexistent/test.py"],
        )
        assert issues == []

    def test_empty_source_produces_no_issues(self, tmp_path):
        """An empty source file should produce zero drift issues."""
        src_file = tmp_path / "source.py"
        src_file.write_text("", encoding="utf-8")

        test_file = _write_test_file_with_call(tmp_path, "func", ["a"])

        dep_map = _FakeDependencyMap()
        detector = DriftDetector(dep_map)

        issues = detector.detect_signature_drift(
            str(src_file), [str(test_file)]
        )
        assert issues == []

    def test_drift_issue_fields_are_valid(self, tmp_path):
        """All DriftIssue fields must have valid values."""
        issue = DriftIssue(
            source_file="src.py",
            test_file="test.py",
            line_number=10,
            drift_type="signature_change",
            severity="high",
            old_value="old_param",
            new_value="new_param",
            description="Parameter renamed",
        )
        assert issue.drift_type in VALID_DRIFT_TYPES
        assert issue.severity in VALID_SEVERITIES
        assert issue.source_file
        assert issue.test_file
        assert issue.line_number > 0
        assert issue.description

    def test_generate_drift_report(self, tmp_path):
        """DriftReport should summarize issues correctly."""
        dep_map = _FakeDependencyMap()
        detector = DriftDetector(dep_map)

        issues = [
            DriftIssue(
                source_file="src1.py",
                test_file="test1.py",
                line_number=5,
                drift_type="signature_change",
                severity="high",
                old_value="old",
                new_value="new",
                description="Param changed",
            ),
            DriftIssue(
                source_file="src1.py",
                test_file="test2.py",
                line_number=10,
                drift_type="key_rename",
                severity="medium",
                old_value="old_key",
                new_value="new_key",
                description="Key renamed",
            ),
        ]

        report = detector.generate_drift_report(issues)
        assert len(report.issues) == 2
        assert report.files_analyzed == 3  # src1, test1, test2
        assert "src1.py" in report.source_files
        assert "test1.py" in report.test_files
        assert "test2.py" in report.test_files
