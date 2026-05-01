"""
Import Analyzer — Python import parsing via AST
================================================

Parses Python files using the ``ast`` module to extract all ``import`` and
``from ... import`` statements.  Resolves relative imports to absolute module
paths and returns structured information about each import.

This module is consumed by :class:`DependencyMapper` to establish
source-to-test relationships via import analysis.

Only stdlib dependencies are used: ``ast``, ``os``, ``pathlib``, ``logging``.
"""

from __future__ import annotations

import ast
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class ImportInfo:
    """Structured representation of a single import statement.

    Attributes:
        module_name: The module being imported (e.g. ``os.path``).
        imported_names: Specific names imported via ``from ... import``
            (empty list for plain ``import`` statements).
        is_relative: ``True`` when the import uses relative syntax
            (``from . import`` or ``from ..pkg import``).
        resolved_path: Absolute module path after resolving relative
            imports, or ``None`` when resolution is not possible.
        line_number: Source line where the import appears.
    """

    module_name: str
    imported_names: List[str] = field(default_factory=list)
    is_relative: bool = False
    resolved_path: Optional[str] = None
    line_number: int = 0


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def analyze_file(file_path: str | Path) -> List[ImportInfo]:
    """Analyze a single Python file and return all its imports.

    Args:
        file_path: Path to the ``.py`` file to analyze.

    Returns:
        A list of :class:`ImportInfo` objects, one per import statement.
        Returns an empty list when the file cannot be read or parsed.
    """
    file_path = Path(file_path)

    if not file_path.exists():
        logger.warning("File does not exist: %s", file_path)
        return []

    try:
        source = file_path.read_text(encoding="utf-8")
    except PermissionError:
        logger.error("Permission denied reading file: %s", file_path)
        return []
    except OSError as exc:
        logger.error("OS error reading file %s: %s", file_path, exc)
        return []

    try:
        tree = ast.parse(source, filename=str(file_path))
    except SyntaxError as exc:
        logger.warning(
            "Syntax error in %s (line %s): %s — skipping file",
            file_path,
            exc.lineno,
            exc.msg,
        )
        return []

    package_name = _infer_package(file_path)
    imports: List[ImportInfo] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(_process_import(node))
        elif isinstance(node, ast.ImportFrom):
            imports.extend(
                _process_import_from(node, package_name, file_path)
            )

    return imports


def resolve_relative_import(
    module: Optional[str],
    level: int,
    package: str,
) -> Optional[str]:
    """Resolve a relative import to an absolute module path.

    Args:
        module: The module part after the dots (e.g. ``utils`` in
            ``from .utils import helper``).  May be ``None`` for bare
            ``from . import name`` statements.
        level: Number of leading dots (1 = current package, 2 = parent, …).
        package: Dotted package name of the file containing the import
            (e.g. ``backend.src.services``).

    Returns:
        The resolved absolute module path, or ``None`` when the level
        exceeds the package depth.

    Examples:
        >>> resolve_relative_import("utils", 1, "backend.src.services")
        'backend.src.services.utils'
        >>> resolve_relative_import(None, 1, "backend.src.services")
        'backend.src.services'
        >>> resolve_relative_import("helpers", 2, "backend.src.services")
        'backend.src.helpers'
    """
    if level <= 0:
        # Not a relative import — nothing to resolve.
        return module

    parts = package.split(".") if package else []

    # level == 1 → stay in current package
    # level == 2 → go up one level, etc.
    steps_up = level - 1
    if steps_up > len(parts):
        logger.warning(
            "Relative import level %d exceeds package depth for '%s'",
            level,
            package,
        )
        return None

    if steps_up > 0:
        base_parts = parts[:-steps_up]
    else:
        base_parts = parts

    if module:
        base_parts.append(module)

    return ".".join(base_parts) if base_parts else None


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _process_import(node: ast.Import) -> List[ImportInfo]:
    """Handle a plain ``import foo, bar.baz`` statement."""
    results: List[ImportInfo] = []
    for alias in node.names:
        results.append(
            ImportInfo(
                module_name=alias.name,
                imported_names=[],
                is_relative=False,
                resolved_path=alias.name,
                line_number=node.lineno,
            )
        )
    return results


def _process_import_from(
    node: ast.ImportFrom,
    package_name: str,
    file_path: Path,
) -> List[ImportInfo]:
    """Handle a ``from foo import bar`` or ``from .foo import bar`` statement."""
    level = node.level or 0
    is_relative = level > 0
    module = node.module  # may be None for ``from . import x``

    imported_names = [alias.name for alias in (node.names or [])]

    if is_relative:
        resolved = resolve_relative_import(module, level, package_name)
    else:
        resolved = module

    return [
        ImportInfo(
            module_name=module or "",
            imported_names=imported_names,
            is_relative=is_relative,
            resolved_path=resolved,
            line_number=node.lineno,
        )
    ]


def _infer_package(file_path: Path) -> str:
    """Infer the dotted package name for *file_path*.

    Walks up the directory tree while ``__init__.py`` files are present to
    determine the package hierarchy.  The file's own stem is **not** included
    (matching how Python resolves relative imports — the *package* of
    ``backend/src/services/year_end_service.py`` is ``backend.src.services``).

    Returns:
        Dotted package string, or an empty string when the file is not
        inside a package.
    """
    file_path = file_path.resolve()
    parts: list[str] = []
    current = file_path.parent

    while (current / "__init__.py").exists():
        parts.append(current.name)
        parent = current.parent
        if parent == current:
            # Reached filesystem root.
            break
        current = parent

    parts.reverse()
    return ".".join(parts)
