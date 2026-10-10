"""
Key-Set Drift Detector — frozen expected-set vs schema/config source
=====================================================================

Detects the **feature-vs-test drift** class where a test freezes a key set
with a hard-coded literal::

    params = data['schema']['members']['params']
    assert set(params.keys()) == {
        'field_overlay', 'scope_dimensions', 'view_contexts', 'mail_enabled',
    }

…while the schema/config *source* that produces those keys has grown (or
shrunk).  When the source gains a key (e.g. the Members ``mail_*`` config
keys) nothing flags the divergence until the frozen-set assertion fails in
CI.  This detector finds the frozen literal statically, resolves the
schema/config dict the test imports, and flags when the source's key set no
longer matches the literal.

Design — deliberately conservative to avoid false positives:

1. **Find frozen expected sets** — parse the *test* file's AST for
   comparisons of the form ``set(<expr>.keys()) == {<string literals>}``
   (either operand order).  Only string-literal set/frozenset members are
   considered; a comparison against a non-literal (a variable, a comprehension)
   is skipped — we cannot know its contents statically.

2. **Resolve candidate schema sources** — import every module the test
   imports (``import x`` / ``from x import y``) and collect module-level
   ``dict`` constants plus one level of nested ``dict`` values.  Each yields
   a *source key set*.  Modules that cannot be imported are skipped (never
   reported) — exactly like the patch-target check's conservatism.

3. **Match & flag** — a frozen literal is matched to a source key set only
   when they overlap strongly (the smaller set is almost entirely contained
   in the larger: ``overlap >= 0.6 * min(len)``) **and** the two sets are not
   equal.  The overlap gate is what distinguishes a genuine schema the test
   froze from unrelated fixture dicts that merely share a key or two.

Only stdlib dependencies are used: ``ast``, ``importlib``, ``logging``,
``pathlib``, ``dataclasses``.

Requirements: durable prevention for the F1 feature-vs-test drift class
(requirements Lesson 1 — a schema/key-set that grows must update its paired
frozen-set test in lockstep).
"""

from __future__ import annotations

import ast
import importlib
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class KeySetDriftIssue:
    """A single frozen-expected-set vs schema-source drift issue.

    Attributes:
        source_module:  Dotted module the schema/config source lives in.
        source_context: Human-readable name of the matched source dict
                        (e.g. the module-level constant name).
        test_file:      Path to the test file holding the frozen literal.
        line_number:    1-based line in the *test* file where the frozen
                        ``set(...keys()) == {...}`` comparison appears.
        drift_type:     Always ``"keyset_drift"``.
        severity:       Always ``"high"`` — a frozen-set assertion WILL fail
                        in CI once the source diverges, same priority as a
                        test failure.
        missing_from_test:  Keys the source now has that the test literal
                            does not (the "schema grew" case — the F1 shape).
        extra_in_test:      Keys the test literal has that the source lacks
                            (the "schema shrank / key renamed" case).
        description:    Human-readable explanation of the drift.
    """

    source_module: str
    source_context: str
    test_file: str
    line_number: int
    drift_type: str
    severity: str
    missing_from_test: List[str]
    extra_in_test: List[str]
    description: str


#: Minimum overlap ratio (relative to the smaller set) required before a
#: frozen literal is considered to describe a given source dict.  Below this
#: the two sets are treated as unrelated and no drift is reported.
_MIN_OVERLAP_RATIO = 0.6


# ---------------------------------------------------------------------------
# Internal representation of a frozen expected set found in a test
# ---------------------------------------------------------------------------

@dataclass
class _FrozenExpectedSet:
    """A ``set(x.keys()) == {literal}`` comparison found in a test file."""

    line_number: int
    keys: Set[str]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

class KeySetDriftDetector:
    """Detects frozen expected-set vs schema/config source drift.

    Typical usage::

        detector = KeySetDriftDetector()
        issues = detector.detect_keyset_drift(
            "backend/tests/unit/test_parameter_admin_routes.py"
        )

    or, across all mapped test files via the dependency map::

        detector = KeySetDriftDetector(dependency_map)
        issues = detector.detect_all_keyset_drift()
    """

    def __init__(self, dependency_map: object = None) -> None:
        """
        Args:
            dependency_map: Optional :class:`DependencyMap`-like object with a
                ``backend`` dict attribute mapping source paths to test path
                lists.  Only used by :meth:`detect_all_keyset_drift`.
        """
        self._dep_map = dependency_map

    # ------------------------------------------------------------------
    # Per-file detection
    # ------------------------------------------------------------------

    def detect_keyset_drift(self, test_file: str) -> List[KeySetDriftIssue]:
        """Find frozen-set assertions in *test_file* that drifted from source.

        Args:
            test_file: Path to the test ``.py`` file to analyse.

        Returns:
            List of :class:`KeySetDriftIssue`, one per drifted frozen literal.
        """
        parsed = _read_and_parse(test_file)
        if parsed is None:
            return []

        tree, _ = parsed

        frozen_sets = _extract_frozen_expected_sets(tree)
        if not frozen_sets:
            return []

        # Resolve candidate schema/config source dicts from the test's imports.
        source_keysets = _collect_imported_source_keysets(tree)
        if not source_keysets:
            return []

        issues: List[KeySetDriftIssue] = []

        for frozen in frozen_sets:
            match = _best_matching_source(frozen.keys, source_keysets)
            if match is None:
                continue

            module_name, context, source_keys = match
            if source_keys == frozen.keys:
                continue  # In sync — no drift.

            missing = sorted(source_keys - frozen.keys)
            extra = sorted(frozen.keys - source_keys)

            issues.append(KeySetDriftIssue(
                source_module=module_name,
                source_context=context,
                test_file=test_file,
                line_number=frozen.line_number,
                drift_type="keyset_drift",
                severity="high",
                missing_from_test=missing,
                extra_in_test=extra,
                description=_build_description(
                    module_name, context, missing, extra
                ),
            ))

        return issues

    # ------------------------------------------------------------------
    # Full-scan entry point
    # ------------------------------------------------------------------

    def detect_all_keyset_drift(self) -> List[KeySetDriftIssue]:
        """Scan every mapped test file for key-set drift.

        A frozen expected set is a property of the test file alone, so each
        unique test file in the dependency map is analysed once.

        Returns:
            List of all :class:`KeySetDriftIssue` instances found.
        """
        backend_map = getattr(self._dep_map, "backend", {})
        all_test_files: Set[str] = set()
        for test_files in backend_map.values():
            all_test_files.update(test_files or [])

        all_issues: List[KeySetDriftIssue] = []
        for test_file in sorted(all_test_files):
            try:
                all_issues.extend(self.detect_keyset_drift(test_file))
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning(
                    "Error detecting key-set drift for %s: %s — skipping",
                    test_file,
                    exc,
                )

        return all_issues


# ---------------------------------------------------------------------------
# AST extraction — frozen expected sets
# ---------------------------------------------------------------------------

def _extract_frozen_expected_sets(
    tree: ast.Module,
) -> List[_FrozenExpectedSet]:
    """Find ``set(x.keys()) == {literal}`` comparisons in a parsed module.

    Both operand orders are recognised::

        set(x.keys()) == {"a", "b"}
        {"a", "b"} == set(x.keys())

    Only a *literal* set/frozenset of string constants on the opposite side
    counts — a comparison against a variable or comprehension is skipped
    because its contents are not statically known.
    """
    found: List[_FrozenExpectedSet] = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.Compare):
            continue

        # Only simple ``a == b`` comparisons (single Eq operator).
        if len(node.ops) != 1 or not isinstance(node.ops[0], ast.Eq):
            continue

        left = node.left
        right = node.comparators[0]

        # Identify which side is ``set(x.keys())`` and which is the literal.
        left_is_keys = _is_set_keys_call(left)
        right_is_keys = _is_set_keys_call(right)

        if left_is_keys and not right_is_keys:
            literal = _extract_string_set_literal(right)
        elif right_is_keys and not left_is_keys:
            literal = _extract_string_set_literal(left)
        else:
            # Neither side (or both sides) is a keys() call — skip.
            continue

        if literal is None:
            continue

        found.append(_FrozenExpectedSet(
            line_number=getattr(node, "lineno", 0),
            keys=literal,
        ))

    return found


def _is_set_keys_call(node: ast.AST) -> bool:
    """Return ``True`` if *node* is ``set(<expr>.keys())``.

    Matches a call to the builtin ``set`` whose single argument is itself a
    call to ``.keys()`` on some object (``set(x.keys())``,
    ``set(data['a']['b'].keys())``, etc.).
    """
    if not isinstance(node, ast.Call):
        return False
    if not (isinstance(node.func, ast.Name) and node.func.id == "set"):
        return False
    if len(node.args) != 1 or node.keywords:
        return False

    inner = node.args[0]
    if not isinstance(inner, ast.Call):
        return False
    return (
        isinstance(inner.func, ast.Attribute)
        and inner.func.attr == "keys"
    )


def _extract_string_set_literal(node: ast.AST) -> Optional[Set[str]]:
    """Extract a set/frozenset literal of string constants, or ``None``.

    Recognises ``{"a", "b"}`` (a ``Set`` node) and ``frozenset({...})`` /
    ``set({...})`` wrapping one.  Returns ``None`` if the node is not a
    literal set, is empty, or contains any non-string-constant element
    (we only freeze string key names).
    """
    # Unwrap frozenset({...}) / set({...}) one level.
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
        if node.func.id in ("frozenset", "set") and len(node.args) == 1:
            node = node.args[0]

    if not isinstance(node, ast.Set):
        return None

    keys: Set[str] = set()
    for elt in node.elts:
        if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
            keys.add(elt.value)
        else:
            # Non-string / non-constant element — not a frozen string set.
            return None

    if not keys:
        return None
    return keys


# ---------------------------------------------------------------------------
# Source resolution — import the test's modules and harvest dict key sets
# ---------------------------------------------------------------------------

def _collect_imported_modules(tree: ast.Module) -> List[str]:
    """Return the dotted module names imported by a parsed test module.

    Covers both ``import a.b`` and ``from a.b import c`` (the module ``a.b``
    is what we import to inspect its dict constants).  ``from . import x``
    relative imports are skipped — they cannot be resolved without a package
    context.
    """
    modules: List[str] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                modules.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.level and node.level > 0:
                continue  # relative import — skip
            if node.module:
                modules.append(node.module)

    # De-dupe, preserve order.
    seen: Set[str] = set()
    ordered: List[str] = []
    for m in modules:
        if m not in seen:
            seen.add(m)
            ordered.append(m)
    return ordered


def _collect_imported_source_keysets(
    tree: ast.Module,
) -> List[Tuple[str, str, Set[str]]]:
    """Harvest candidate ``(module, context, key_set)`` tuples from imports.

    For every importable module the test references, collect:

    - each module-level ``dict`` constant's top-level key set, and
    - the key set of each ``dict`` *value* nested one level inside those
      module-level dicts (so a schema like
      ``PARAMETER_SCHEMA["members"]["params"]`` surfaces its ``params`` keys).

    Modules that cannot be imported are skipped (never reported).  Non-string
    keys are ignored so only genuine string-keyed config/schema dicts match.
    """
    results: List[Tuple[str, str, Set[str]]] = []

    for module_name in _collect_imported_modules(tree):
        module = _safe_import(module_name)
        if module is None:
            continue

        for attr_name in dir(module):
            if attr_name.startswith("__"):
                continue
            try:
                value = getattr(module, attr_name)
            except Exception:  # pragma: no cover - defensive
                continue

            if not isinstance(value, dict):
                continue

            _harvest_dict_keysets(
                module_name, attr_name, value, results
            )

    return results


def _harvest_dict_keysets(
    module_name: str,
    root_name: str,
    root: dict,
    results: List[Tuple[str, str, Set[str]]],
) -> None:
    """Add the root dict's key set plus one level of nested dict key sets."""
    top_keys = _string_keys(root)
    if top_keys:
        results.append((module_name, root_name, top_keys))

    for child_key, child_val in root.items():
        if isinstance(child_val, dict):
            child_keys = _string_keys(child_val)
            if child_keys:
                context = f"{root_name}[{child_key!r}]"
                results.append((module_name, context, child_keys))

            # One more level down (e.g. SECTION['params']) — schemas often
            # nest the real key set two levels in.
            for g_key, g_val in child_val.items():
                if isinstance(g_val, dict):
                    g_keys = _string_keys(g_val)
                    if g_keys:
                        g_context = (
                            f"{root_name}[{child_key!r}][{g_key!r}]"
                        )
                        results.append((module_name, g_context, g_keys))


def _string_keys(d: dict) -> Set[str]:
    """Return the subset of *d*'s keys that are strings."""
    return {k for k in d.keys() if isinstance(k, str)}


def _safe_import(module_name: str):
    """Import *module_name*, returning the module or ``None`` on any failure.

    Mirrors the patch-target check's conservatism: a module that cannot be
    imported (optional dep, not on ``sys.path``, import-time error) is a
    non-signal, not a drift report.
    """
    try:
        return importlib.import_module(module_name)
    except Exception as exc:
        logger.debug(
            "Key-set source module '%s' not importable: %s",
            module_name,
            exc,
        )
        return None


# ---------------------------------------------------------------------------
# Matching
# ---------------------------------------------------------------------------

def _best_matching_source(
    literal: Set[str],
    source_keysets: List[Tuple[str, str, Set[str]]],
) -> Optional[Tuple[str, str, Set[str]]]:
    """Pick the source key set that best describes a frozen literal.

    A candidate matches only when its overlap with the literal is at least
    :data:`_MIN_OVERLAP_RATIO` of the *smaller* of the two sets.  Among
    qualifying candidates the one with the largest overlap wins; ties break
    toward the source whose size is closest to the literal (the most specific
    schema).  Returns ``None`` when no candidate overlaps strongly enough.
    """
    best: Optional[Tuple[str, str, Set[str]]] = None
    best_overlap = 0
    best_size_delta = 10**9

    for module_name, context, source_keys in source_keysets:
        if not source_keys:
            continue
        overlap = len(literal & source_keys)
        if overlap == 0:
            continue

        smaller = min(len(literal), len(source_keys))
        if overlap < max(2, smaller * _MIN_OVERLAP_RATIO):
            continue

        size_delta = abs(len(source_keys) - len(literal))
        if (
            overlap > best_overlap
            or (overlap == best_overlap and size_delta < best_size_delta)
        ):
            best = (module_name, context, source_keys)
            best_overlap = overlap
            best_size_delta = size_delta

    return best


def _build_description(
    module_name: str,
    context: str,
    missing: List[str],
    extra: List[str],
) -> str:
    """Compose a human-readable explanation of the drift."""
    parts = [
        (
            f"Test freezes a key set with a hard-coded literal, but the "
            f"schema source '{context}' in module '{module_name}' no longer "
            f"matches it."
        )
    ]
    if missing:
        parts.append(
            f"Source has {len(missing)} key(s) the test literal is missing: "
            f"{missing}. Add them to the frozen set (the schema grew — the "
            f"F1 feature-vs-test drift class)."
        )
    if extra:
        parts.append(
            f"Test literal has {len(extra)} key(s) absent from the source: "
            f"{extra}. The key(s) may have been renamed or removed from the "
            f"schema."
        )
    parts.append(
        "Update the test's expected set in lockstep with the schema "
        "(the Change-With-Tests contract)."
    )
    return " ".join(parts)


# ---------------------------------------------------------------------------
# Shared parse helper
# ---------------------------------------------------------------------------

def _read_and_parse(file_path: str) -> Optional[Tuple[ast.Module, str]]:
    """Read and parse a Python file, returning (tree, source) or None."""
    path = Path(file_path)

    if not path.exists():
        logger.warning("File does not exist: %s", file_path)
        return None

    if path.suffix != ".py":
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
