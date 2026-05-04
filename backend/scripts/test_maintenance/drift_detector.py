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
    has_kwargs: bool = False  # True when the function accepts **kwargs


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

        # When multiple source functions share the same name (e.g. a class
        # method and a standalone route function), keep only the one with
        # the most parameters.  Tests typically call the richer signature
        # (the class method), so matching against the bare route function
        # produces false positives.
        best_by_name: Dict[str, "_FunctionSignature"] = {}
        for sig in source_sigs:
            existing = best_by_name.get(sig.name)
            if existing is None or len(sig.params) > len(existing.params):
                best_by_name[sig.name] = sig

        # Also consult the global best-signature map (built by
        # detect_all_drift) so that when a route file defines
        # send_invoice() with few params but a service file defines
        # send_invoice(self, tenant, invoice_id, options, ...), we use
        # the richer service signature.
        global_best = getattr(self, "_global_best_sig", {})
        for name in list(best_by_name.keys()):
            g_sig = global_best.get(name)
            if g_sig is not None and g_sig is not best_by_name[name]:
                # Always prefer the global best — it was selected using
                # source-priority (service > other > route) and param
                # count, so it's the most representative signature.
                best_by_name[name] = g_sig

        source_sigs = list(best_by_name.values())

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

        # --- Pre-compute a global "best signature" lookup ----------------
        # When multiple source files define a function with the same name
        # (e.g. a route function and a service method), keep the one from
        # the service layer.  Tests typically call service methods, not
        # route functions directly.  Route functions have decorator-injected
        # params (user_email, user_roles, tenant, user_tenants) that don't
        # appear in test calls.
        #
        # Priority: service > other > route
        global_best_sig: Dict[str, _FunctionSignature] = {}
        _global_best_source: Dict[str, str] = {}  # func_name -> source_file

        def _source_priority(path: str) -> int:
            """Higher = preferred."""
            norm = path.replace("\\", "/")
            if "/services/" in norm:
                return 2
            if "/routes/" in norm:
                return 0
            return 1

        for source_file in backend_map:
            sigs = _extract_function_signatures(source_file)
            if not sigs:
                continue
            prio = _source_priority(source_file)
            for sig in sigs:
                existing = global_best_sig.get(sig.name)
                if existing is None:
                    global_best_sig[sig.name] = sig
                    _global_best_source[sig.name] = source_file
                else:
                    existing_prio = _source_priority(
                        _global_best_source.get(sig.name, "")
                    )
                    # Prefer higher priority source, or more params at
                    # same priority, or **kwargs
                    if (
                        prio > existing_prio
                        or (prio == existing_prio
                            and len(sig.params) > len(existing.params))
                        or (not existing.has_kwargs and sig.has_kwargs)
                    ):
                        global_best_sig[sig.name] = sig
                        _global_best_source[sig.name] = source_file

        # Store the global lookup so detect_signature_drift can use it
        self._global_best_sig = global_best_sig

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

        # If the source function accepts **kwargs, any keyword argument is
        # valid — skip drift detection entirely for this function.
        if src_sig.has_kwargs:
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

        if src_sig.has_kwargs:
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

        Detects two kinds of drift:

        1. **Source key missing from tests** — a key that the source file
           defines in a dictionary literal is not referenced anywhere in
           the test file.  This suggests the test's mock data may be stale.
        2. **Overlapping-context mismatch** — when a source dict and a test
           dict share at least half their keys, any key present in the test
           dict but absent from the source dict is flagged.  This catches
           renamed keys while ignoring unrelated test fixture data.

        The previous approach (flag every test key absent from source)
        produced massive false-positive counts because test files naturally
        contain many keys that have no counterpart in the source (HTTP
        headers, JWT claims, fixture data, etc.).
        """
        issues: List[DriftIssue] = []

        # Build flat sets
        all_source_keys: Set[str] = set()
        for keys in source_keys.values():
            all_source_keys.update(keys)

        all_test_keys: Set[str] = set()
        for keys in test_keys.values():
            all_test_keys.update(keys)

        # --- Strategy 1: source keys missing from overlapping test dicts ---
        # Only flag a source key as missing when the test file already
        # references *other* keys from the same source dict context.
        # This avoids false positives where a test simply doesn't mock
        # that particular dict at all.
        for s_context, s_keys in source_keys.items():
            if len(s_keys) < 3:
                continue  # skip tiny source dicts

            # How many of this source dict's keys appear in the test?
            matched = s_keys & all_test_keys
            if len(matched) < max(2, len(s_keys) * 0.5):
                # Test doesn't reference enough keys from this dict —
                # it's probably not trying to mock it.
                continue

            for key in s_keys - all_test_keys:
                if _is_likely_data_key(key):
                    issues.append(DriftIssue(
                        source_file=source_file,
                        test_file=test_file,
                        line_number=0,
                        drift_type="key_rename",
                        severity="low",
                        old_value=key,
                        new_value="(key not found in test)",
                        description=(
                            f"Source defines dictionary key '{key}' "
                            f"(in context '{s_context}') that is not "
                            f"referenced in the test file, but the test "
                            f"does reference {len(matched)} other key(s) "
                            f"from the same source dict. The test's mock "
                            f"data may be outdated."
                        ),
                    ))

        # --- Strategy 2: overlapping-context mismatch ---
        # For each test dict, find the best-matching source dict.  If they
        # share ≥50 % of keys, flag test-only keys as potential renames.
        for t_context, t_keys in test_keys.items():
            if len(t_keys) < 3:
                continue  # skip tiny dicts

            best_overlap = 0
            best_s_keys: Set[str] = set()

            for s_keys in source_keys.values():
                overlap = len(t_keys & s_keys)
                if overlap > best_overlap:
                    best_overlap = overlap
                    best_s_keys = s_keys

            # Require ≥60 % overlap with the best-matching source dict
            if best_overlap < max(2, len(t_keys) * 0.6):
                continue

            for key in t_keys - best_s_keys:
                if _is_likely_data_key(key):
                    issues.append(DriftIssue(
                        source_file=source_file,
                        test_file=test_file,
                        line_number=0,
                        drift_type="key_rename",
                        severity="low",
                        old_value=key,
                        new_value="(key not found in matching source dict)",
                        description=(
                            f"Test dict (context '{t_context}') shares "
                            f"{best_overlap} key(s) with a source dict but "
                            f"also contains '{key}' which is absent from "
                            f"the source. The key may have been renamed."
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
            has_kwargs = node.args.kwarg is not None

            signatures.append(_FunctionSignature(
                name=node.name,
                params=params,
                line_number=node.lineno,
                defaults_count=defaults_count,
                has_kwargs=has_kwargs,
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
    """Return ``True`` if *key* looks like a genuine data/business key
    that warrants drift detection.

    Filters out:
    - Mock framework artifacts (``return_value``, ``side_effect``, …)
    - HTTP headers and standard request/response keys
    - JWT / Cognito / auth claim keys
    - Common test fixture data (env vars, config keys)
    - Flask / WSGI keys
    - Python builtins and very short keys

    The goal is to only flag keys that represent *application-specific*
    data structures (e.g. database column names, API response fields)
    where a rename in the source should be reflected in the test.
    """
    # Skip very short keys (likely loop variables or similar)
    if len(key) <= 1:
        return False

    # --- Exact-match skip sets ---

    _MOCK_KEYS = {
        "return_value", "side_effect", "called", "call_count",
        "call_args", "call_args_list", "assert_called",
        "assert_called_once", "assert_called_with",
        "assert_called_once_with", "assert_not_called",
        "reset_mock", "configure_mock",
    }

    _PYTHON_KEYS = {
        "type", "class", "module", "name", "args", "kwargs",
        "self", "cls", "True", "False", "None",
    }

    # Standard HTTP headers (case-sensitive as they appear in test code)
    _HTTP_HEADER_KEYS = {
        "Authorization", "Content-Type", "Accept", "Accept-Encoding",
        "Accept-Language", "Cache-Control", "Connection", "Cookie",
        "Host", "Origin", "Referer", "User-Agent",
        "X-Forwarded-For", "X-Forwarded-Proto", "X-Request-ID",
        "X-Tenant", "X-Correlation-ID", "X-Api-Key",
        "Location", "Set-Cookie", "WWW-Authenticate",
        "Access-Control-Allow-Origin", "Access-Control-Allow-Headers",
        "Access-Control-Allow-Methods",
    }

    # JWT / Cognito / auth keys
    _AUTH_KEYS = {
        "alg", "typ", "kid", "iss", "sub", "aud", "exp", "iat", "nbf",
        "jti", "nonce", "at_hash", "c_hash", "auth_time", "token_use",
        "scope", "client_id",
        "email", "email_verified", "phone_number", "phone_number_verified",
        "username", "Username", "UserAttributes",
        "custom:tenants", "custom:tenant_id", "custom:role",
        "cognito:groups", "cognito:username",
        "Name", "Value",  # Cognito UserAttributes structure
        "AccessToken", "IdToken", "RefreshToken", "TokenType",
        "ExpiresIn", "AuthenticationResult",
    }

    # Flask / WSGI / test client keys
    _FLASK_KEYS = {
        "TESTING", "DEBUG", "SECRET_KEY", "SERVER_NAME",
        "APPLICATION_ROOT", "PREFERRED_URL_SCHEME",
        "json", "data", "status_code", "status", "headers",
        "content_type", "mimetype", "charset",
    }

    # Environment variable names commonly used in test fixtures
    _ENV_KEYS = {
        "TEST_MODE", "DB_HOST", "DB_PORT", "DB_USER", "DB_PASSWORD",
        "DB_NAME", "DATABASE_URL",
        "COGNITO_USER_POOL_ID", "COGNITO_CLIENT_ID", "COGNITO_REGION",
        "AWS_REGION", "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY",
        "GOOGLE_DRIVE_FOLDER_ID", "GOOGLE_CREDENTIALS",
        "FLASK_ENV", "FLASK_APP", "FLASK_DEBUG",
        "OPENROUTER_API_KEY", "SNS_TOPIC_ARN",
    }

    # Common generic / structural keys in test assertions
    _GENERIC_KEYS = {
        "id", "key", "value", "error", "message", "detail", "details",
        "success", "result", "results", "count", "total", "page",
        "limit", "offset", "sort", "order", "filter", "query",
        "created_at", "updated_at", "deleted_at", "timestamp",
        "description", "title", "label", "text", "code",
        "url", "path", "method", "params", "body", "response",
        "files", "items", "entries",
    }

    all_skip = (
        _MOCK_KEYS | _PYTHON_KEYS | _HTTP_HEADER_KEYS | _AUTH_KEYS
        | _FLASK_KEYS | _ENV_KEYS | _GENERIC_KEYS
    )
    if key in all_skip:
        return False

    # --- Pattern-based filtering ---

    # Keys starting with common prefixes for headers / env / config
    _lower = key.lower()
    if _lower.startswith(("x-", "http_", "content-", "access-control-")):
        return False

    # Cognito / AWS custom attributes (custom:*, cognito:*)
    if ":" in key:
        return False

    return True
