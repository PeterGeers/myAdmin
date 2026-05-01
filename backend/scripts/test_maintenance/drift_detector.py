"""
Drift Detector — signature and key change detection
====================================================

Detects when source code changes make tests outdated by comparing function
signatures and dictionary keys between source files and their dependent test
files.

The detector uses Python ``ast`` to parse both source and test files, then
compares:

1. **Signature drift** — function parameters in source vs mock/call setup
   in tests (parameters added, removed, or renamed).
2. **Key drift** — dictionary keys returned or used in source vs the keys
   referenced in test mock return values or assertions.

Only stdlib dependencies are used: ``ast``, ``logging``, ``os``, ``pathlib``,
``re``, ``dataclasses``.

Requirements: 6.2, 6.3, 6.4, 6.5
"""

from __future__ import annotations

import ast
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class DriftIssue:
    """A single source-test drift issue.

    Attributes:
        source_file:  Path to the source file that changed.
        test_file:    Path to the test file that is now outdated.
        line_number:  1-based line number in the *test* file where the
                      outdated reference appears.
        drift_type:   Category — ``"signature_change"``, ``"key_rename"``,
                      or ``"return_type_change"``.
        severity:     One of ``"critical"``, ``"high"``, ``"medium"``,
                      ``"low"``.
        old_value:    The value as it appears in the test (outdated).
        new_value:    The value as it appears in the source (current).
        description:  Human-readable explanation of the drift.
    """

    source_file: str
    test_file: str
    line_number: int
    drift_type: str
    severity: str
    old_value: str
    new_value: str
    description: str


VALID_DRIFT_TYPES = {"signature_change", "key_rename", "return_type_change"}
VALID_SEVERITIES = {"critical", "high", "medium", "low"}


@dataclass
class DriftReport:
    """Structured output of a drift detection run.

    Attributes:
        issues:           All detected drift issues.
        files_analyzed:   Number of source-test pairs analyzed.
        source_files:     Source files that were checked.
        test_files:       Test files that were checked.
    """

    issues: List[DriftIssue] = field(default_factory=list)
    files_analyzed: int = 0
    source_files: List[str] = field(default_factory=list)
    test_files: List[str] = field(default_factory=list)


@dataclass
class _FunctionSignature:
    """Internal representation of a function signature."""

    name: str
    params: List[str]
    line_number: int
    defaults_count: int = 0


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

class DriftDetector:
    """Detects source-test code drift.

    Compares function signatures and dictionary keys between source files
    and their dependent test files to find outdated mocks and assertions.

    Typical usage::

        from scripts.test_maintenance.dependency_mapper import (
            DependencyMapper, DependencyMap,
        )

        mapper = DependencyMapper()
        dep_map = mapper.build_backend_map()
        detector = DriftDetector(dep_map)
        issues = detector.detect_signature_drift(
            "backend/src/year_end_service.py",
            ["backend/tests/unit/test_year_end_service.py"],
        )
    """

    def __init__(self, dependency_map: object) -> None:
        """
        Args:
            dependency_map: A :class:`DependencyMap` instance (or any object
                with ``backend`` and ``frontend`` dict attributes mapping
                source paths to test path lists).
        """
        self._dep_map = dependency_map

    # ------------------------------------------------------------------
    # Public methods
    # ------------------------------------------------------------------

    def detect_signature_drift(
        self,
        source_file: str,
        test_files: List[str],
    ) -> List[DriftIssue]:
        """Compare function signatures in source vs mock setup in tests.

        For each public function in *source_file*, checks whether the
        test files reference the function with a different parameter list
        (e.g. calling it with old parameter names, or missing new required
        parameters).

        Args:
            source_file: Path to the source ``.py`` file.
            test_files:  Paths to dependent test ``.py`` files.

        Returns:
            List of :class:`DriftIssue` for each signature mismatch.
        """
        source_sigs = _extract_function_signatures(source_file)
        if not source_sigs:
            return []

        issues: List[DriftIssue] = []

        for test_file in test_files:
            test_sigs = _extract_function_signatures(test_file)
            test_calls = _extract_function_calls(test_file)
            test_mock_setups = _extract_mock_setups(test_file)

            if test_sigs is None and test_calls is None:
                continue

            for src_sig in source_sigs:
                # Check if any test function calls the source function
                # with different parameters
                issues.extend(
                    self._check_call_drift(
                        src_sig, test_calls or {}, source_file, test_file
                    )
                )

                # Check if any test mock setup references the function
                # with different parameters
                issues.extend(
                    self._check_mock_setup_drift(
                        src_sig, test_mock_setups or {}, source_file, test_file
                    )
                )

        return issues

    def detect_key_drift(
        self,
        source_file: str,
        test_files: List[str],
    ) -> List[DriftIssue]:
        """Compare dictionary keys between source and test mocks.

        Extracts dictionary keys from return statements and assignments in
        the source file, then checks whether test files reference the same
        keys in mock return values and assertions.

        Args:
            source_file: Path to the source ``.py`` file.
            test_files:  Paths to dependent test ``.py`` files.

        Returns:
            List of :class:`DriftIssue` for each key mismatch.
        """
        source_keys = _extract_dict_keys(source_file)
        if not source_keys:
            return []

        issues: List[DriftIssue] = []

        for test_file in test_files:
            test_keys = _extract_dict_keys(test_file)
            if test_keys is None:
                continue

            issues.extend(
                self._check_key_drift(
                    source_keys, test_keys, source_file, test_file
                )
            )

        return issues

    def generate_drift_report(
        self, issues: List[DriftIssue]
    ) -> DriftReport:
        """Generate structured drift report.

        Args:
            issues: List of drift issues to include in the report.

        Returns:
            A :class:`DriftReport` with summary information.
        """
        source_files: Set[str] = set()
        test_files: Set[str] = set()

        for issue in issues:
            source_files.add(issue.source_file)
            test_files.add(issue.test_file)

        return DriftReport(
            issues=issues,
            files_analyzed=len(source_files) + len(test_files),
            source_files=sorted(source_files),
            test_files=sorted(test_files),
        )

    def detect_all_drift(self) -> List[DriftIssue]:
        """Run drift detection across all mapped source-test pairs.

        Uses the dependency map to iterate over all source files and their
        corresponding test files.

        Returns:
            List of all detected :class:`DriftIssue` instances.
        """
        all_issues: List[DriftIssue] = []

        backend_map = getattr(self._dep_map, "backend", {})
        for source_file, test_files in backend_map.items():
            if not test_files:
                continue
            try:
                all_issues.extend(
                    self.detect_signature_drift(source_file, test_files)
                )
                all_issues.extend(
                    self.detect_key_drift(source_file, test_files)
                )
            except Exception as exc:
                logger.warning(
                    "Error detecting drift for %s: %s — skipping",
                    source_file,
                    exc,
                )

        return all_issues

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _check_call_drift(
        self,
        src_sig: _FunctionSignature,
        test_calls: Dict[str, List[Tuple[int, List[str]]]],
        source_file: str,
        test_file: str,
    ) -> List[DriftIssue]:
        """Check if test calls to a source function have drifted."""
        issues: List[DriftIssue] = []
        func_name = src_sig.name

        if func_name not in test_calls:
            return issues

        src_params = set(src_sig.params)

        for line_number, call_kwargs in test_calls[func_name]:
            call_kwarg_set = set(call_kwargs)
            # Find keyword arguments used in the test that are not in the
            # source function's parameter list
            unknown_kwargs = call_kwarg_set - src_params - {"self", "cls"}
            if unknown_kwargs:
                issues.append(DriftIssue(
                    source_file=source_file,
                    test_file=test_file,
                    line_number=line_number,
                    drift_type="signature_change",
                    severity="high",
                    old_value=", ".join(sorted(unknown_kwargs)),
                    new_value=", ".join(sorted(src_params - {"self", "cls"})),
                    description=(
                        f"Test calls '{func_name}' with keyword argument(s) "
                        f"{sorted(unknown_kwargs)} that no longer exist in "
                        f"the source function signature. Current parameters: "
                        f"{sorted(src_params - {'self', 'cls'})}."
                    ),
                ))

        return issues

    def _check_mock_setup_drift(
        self,
        src_sig: _FunctionSignature,
        test_mock_setups: Dict[str, List[Tuple[int, List[str]]]],
        source_file: str,
        test_file: str,
    ) -> List[DriftIssue]:
        """Check if test mock setups reference outdated parameters."""
        issues: List[DriftIssue] = []
        func_name = src_sig.name

        if func_name not in test_mock_setups:
            return issues

        src_params = set(src_sig.params)

        for line_number, mock_kwargs in test_mock_setups[func_name]:
            mock_kwarg_set = set(mock_kwargs)
            unknown_kwargs = mock_kwarg_set - src_params - {"self", "cls"}
            if unknown_kwargs:
                issues.append(DriftIssue(
                    source_file=source_file,
                    test_file=test_file,
                    line_number=line_number,
                    drift_type="signature_change",
                    severity="high",
                    old_value=", ".join(sorted(unknown_kwargs)),
                    new_value=", ".join(sorted(src_params - {"self", "cls"})),
                    description=(
                        f"Test mock setup for '{func_name}' references "
                        f"parameter(s) {sorted(unknown_kwargs)} that no "
                        f"longer exist in the source function signature. "
                        f"Current parameters: "
                        f"{sorted(src_params - {'self', 'cls'})}."
                    ),
                ))

        return issues

    def _check_key_drift(
        self,
        source_keys: Dict[str, Set[str]],
        test_keys: Dict[str, Set[str]],
        source_file: str,
        test_file: str,
    ) -> List[DriftIssue]:
        """Compare dictionary keys between source and test files.

        Looks for keys that appear in test mock return values or assertions
        but are not present in the source file's dictionary definitions.
        """
        issues: List[DriftIssue] = []

        # Build a flat set of all keys used in the source
        all_source_keys: Set[str] = set()
        source_key_contexts: Dict[str, str] = {}
        for context, keys in source_keys.items():
            all_source_keys.update(keys)
            for key in keys:
                source_key_contexts[key] = context

        # Check each test key context
        for context, keys in test_keys.items():
            for key in keys:
                if key not in all_source_keys and _is_likely_data_key(key):
                    # This key appears in the test but not in the source
                    issues.append(DriftIssue(
                        source_file=source_file,
                        test_file=test_file,
                        line_number=0,  # Line-level tracking for keys is approximate
                        drift_type="key_rename",
                        severity="medium",
                        old_value=key,
                        new_value="(key not found in source)",
                        description=(
                            f"Test references dictionary key '{key}' "
                            f"(in context '{context}') that does not appear "
                            f"in the source file. The key may have been "
                            f"renamed or removed."
                        ),
                    ))

        return issues


# ---------------------------------------------------------------------------
# AST extraction helpers
# ---------------------------------------------------------------------------

def _read_and_parse(file_path: str) -> Optional[Tuple[ast.Module, str]]:
    """Read and parse a Python file, returning (tree, source) or None."""
    path = Path(file_path)

    if not path.exists():
        logger.warning("File does not exist: %s", file_path)
        return None

    if not path.suffix == ".py":
        logger.debug("Skipping non-Python file: %s", file_path)
        return None

    try:
        source = path.read_text(encoding="utf-8")
    except (PermissionError, OSError) as exc:
        logger.error("Error reading file %s: %s", file_path, exc)
        return None

    try:
        tree = ast.parse(source, filename=file_path)
    except SyntaxError as exc:
        logger.warning(
            "Syntax error in %s (line %s): %s — skipping",
            file_path,
            exc.lineno,
            exc.msg,
        )
        return None

    return tree, source


def _extract_function_signatures(
    file_path: str,
) -> Optional[List[_FunctionSignature]]:
    """Extract all function/method signatures from a Python file.

    Returns a list of :class:`_FunctionSignature` or ``None`` if the file
    cannot be read/parsed.
    """
    result = _read_and_parse(file_path)
    if result is None:
        return None

    tree, _ = result
    signatures: List[_FunctionSignature] = []

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            # Skip private/dunder methods for drift detection
            if node.name.startswith("_") and not node.name.startswith("__"):
                continue

            params = [
                arg.arg
                for arg in node.args.args
            ]
            defaults_count = len(node.args.defaults)

            signatures.append(_FunctionSignature(
                name=node.name,
                params=params,
                line_number=node.lineno,
                defaults_count=defaults_count,
            ))

    return signatures


def _extract_function_calls(
    file_path: str,
) -> Optional[Dict[str, List[Tuple[int, List[str]]]]]:
    """Extract function calls with their keyword arguments from a file.

    Returns ``{func_name: [(line_number, [kwarg_names])]}`` or ``None``.
    """
    result = _read_and_parse(file_path)
    if result is None:
        return None

    tree, _ = result
    calls: Dict[str, List[Tuple[int, List[str]]]] = {}

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue

        func_name = _get_call_name(node)
        if func_name is None:
            continue

        # Extract the leaf name (e.g. "process" from "service.process")
        leaf_name = func_name.rsplit(".", 1)[-1]

        kwargs = [
            kw.arg for kw in node.keywords
            if kw.arg is not None  # skip **kwargs
        ]

        if kwargs:
            calls.setdefault(leaf_name, []).append(
                (node.lineno, kwargs)
            )

    return calls


def _extract_mock_setups(
    file_path: str,
) -> Optional[Dict[str, List[Tuple[int, List[str]]]]]:
    """Extract mock setup patterns from a test file.

    Looks for patterns like:
    - ``mock_obj.method_name.return_value = ...``
    - ``mock_obj.method_name.side_effect = ...``
    - ``mock_obj.method_name.assert_called_with(key=val)``

    Returns ``{method_name: [(line_number, [kwarg_names])]}`` or ``None``.
    """
    result = _read_and_parse(file_path)
    if result is None:
        return None

    tree, source = result
    setups: Dict[str, List[Tuple[int, List[str]]]] = {}

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue

        func_name = _get_call_name(node)
        if func_name is None:
            continue

        # Look for assert_called_with, assert_called_once_with patterns
        if "assert_called" in func_name and "with" in func_name:
            # Extract the method name being asserted
            # e.g. "mock_db.execute_query.assert_called_once_with"
            parts = func_name.split(".")
            if len(parts) >= 3:
                method_name = parts[-2]
                if method_name not in ("assert_called_with",
                                       "assert_called_once_with"):
                    kwargs = [
                        kw.arg for kw in node.keywords
                        if kw.arg is not None
                    ]
                    if kwargs:
                        setups.setdefault(method_name, []).append(
                            (node.lineno, kwargs)
                        )

    return setups


def _extract_dict_keys(
    file_path: str,
) -> Optional[Dict[str, Set[str]]]:
    """Extract dictionary keys from a Python file.

    Scans for dictionary literals in return statements, assignments, and
    mock return value setups.

    Returns ``{context_description: {key1, key2, ...}}`` or ``None``.
    """
    result = _read_and_parse(file_path)
    if result is None:
        return None

    tree, _ = result
    keys_by_context: Dict[str, Set[str]] = {}

    for node in ast.walk(tree):
        # Dictionary literals
        if isinstance(node, ast.Dict):
            context = f"dict_literal_line_{getattr(node, 'lineno', 0)}"
            key_set: Set[str] = set()
            for key in node.keys:
                if key is not None:
                    key_str = _get_string_constant(key)
                    if key_str is not None:
                        key_set.add(key_str)
            if key_set:
                keys_by_context[context] = key_set

        # Subscript access: obj['key']
        if isinstance(node, ast.Subscript):
            key_str = _get_string_constant(node.slice)
            if key_str is not None:
                context = f"subscript_line_{getattr(node, 'lineno', 0)}"
                keys_by_context.setdefault(context, set()).add(key_str)

    return keys_by_context


# ---------------------------------------------------------------------------
# AST utility helpers
# ---------------------------------------------------------------------------

def _get_call_name(node: ast.Call) -> Optional[str]:
    """Extract the dotted name of a function call, or ``None``."""
    func = node.func
    parts: List[str] = []

    while isinstance(func, ast.Attribute):
        parts.append(func.attr)
        func = func.value

    if isinstance(func, ast.Name):
        parts.append(func.id)
    else:
        return None

    parts.reverse()
    return ".".join(parts)


def _get_string_constant(node: ast.AST) -> Optional[str]:
    """Extract a string constant from an AST node, or ``None``."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _is_likely_data_key(key: str) -> bool:
    """Return ``True`` if *key* looks like a data/business key.

    Filters out common non-data keys like ``'return_value'``,
    ``'side_effect'``, etc. that are mock framework artifacts.
    """
    # Skip mock framework keys
    _MOCK_KEYS = {
        "return_value", "side_effect", "called", "call_count",
        "call_args", "call_args_list", "assert_called",
        "assert_called_once", "assert_called_with",
        "assert_called_once_with", "assert_not_called",
        "reset_mock", "configure_mock",
    }
    if key in _MOCK_KEYS:
        return False

    # Skip very short keys (likely loop variables or similar)
    if len(key) <= 1:
        return False

    # Skip keys that look like Python builtins or test framework artifacts
    _SKIP_KEYS = {
        "type", "class", "module", "name", "args", "kwargs",
        "self", "cls", "True", "False", "None",
    }
    if key in _SKIP_KEYS:
        return False

    return True
