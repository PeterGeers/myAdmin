"""
Frontend Scanner — React test analysis
=======================================

Analyses TypeScript/TSX test files for common anti-patterns using regex
pattern matching.  No Node.js dependency is required — all analysis is
done via Python regex on the raw file text.

Detection categories:

1. **Missing MSW handlers** — test files that make HTTP calls (``fetch(``,
   ``axios.get(``, etc.) without setting up MSW (Mock Service Worker)
   handlers via ``setupServer`` or ``http.get/post/put/delete``.
2. **Missing provider wrappers** — test files that import ``render``
   directly from ``@testing-library/react`` instead of the project's
   ``test-utils`` module.
3. **Stale imports** — test files that import components from paths that
   do not correspond to existing files in the frontend source tree.

Only stdlib dependencies are used: ``logging``, ``os``, ``pathlib``,
``re``, ``dataclasses``.

Requirements: 9.1, 9.2, 9.4
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Set

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class FrontendViolation:
    """A single frontend test violation.

    Attributes:
        file_path:       Path to the test file containing the violation.
        line_number:     1-based line number where the violation occurs.
        violation_type:  Category — ``"missing_msw"``, ``"missing_provider"``,
                         or ``"stale_import"``.
        severity:        One of ``"critical"``, ``"high"``, ``"medium"``,
                         ``"low"``.
        description:     Human-readable explanation of the violation.
        suggested_fix:   Recommended remediation.
    """

    file_path: str
    line_number: int
    violation_type: str
    severity: str
    description: str
    suggested_fix: str


VALID_VIOLATION_TYPES = {"missing_msw", "missing_provider", "stale_import"}
VALID_SEVERITIES = {"critical", "high", "medium", "low"}


@dataclass
class FrontendScanReport:
    """Structured output of a frontend scan run.

    Attributes:
        violations:       All detected violations.
        files_scanned:    Number of test files analyzed.
        test_files:       Paths to the test files that were scanned.
    """

    violations: List[FrontendViolation] = field(default_factory=list)
    files_scanned: int = 0
    test_files: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Regex patterns
# ---------------------------------------------------------------------------

# HTTP call patterns that indicate API interaction
_HTTP_CALL_PATTERNS = [
    re.compile(r"""\bfetch\s*\("""),
    re.compile(r"""\baxios\s*\.\s*(get|post|put|delete|patch|head|options)\s*\("""),
    re.compile(r"""\baxios\s*\("""),
    re.compile(r"""\bapi\s*\.\s*(get|post|put|delete|patch)\s*\("""),
]

# MSW setup patterns that indicate proper mocking
_MSW_SETUP_PATTERNS = [
    re.compile(r"""\bsetupServer\b"""),
    re.compile(r"""\bhttp\s*\.\s*(get|post|put|delete|patch|all)\s*\("""),
    re.compile(r"""\brest\s*\.\s*(get|post|put|delete|patch|all)\s*\("""),
    re.compile(r"""\bserver\s*\.\s*(use|listen|resetHandlers|close)\b"""),
    # vi.fn() / vi.mocked() fetch mocking is an acceptable alternative
    re.compile(r"""global\s*\.\s*fetch\s*=\s*vi\s*\.\s*fn\b"""),
    re.compile(r"""\bvi\s*\.\s*mocked\s*\(\s*(global\s*\.\s*)?fetch\s*\)"""),
    re.compile(r"""\bjest\s*\.\s*fn\s*\(\s*\).*fetch"""),
]

# Direct render import from @testing-library/react
_DIRECT_RENDER_IMPORT = re.compile(
    r"""(?:import\s+\{[^}]*\brender\b[^}]*\}\s+from\s+['"]@testing-library/react['"])"""
)

# Proper render import from test-utils
_TEST_UTILS_RENDER_IMPORT = re.compile(
    r"""(?:import\s+\{[^}]*\brender\b[^}]*\}\s+from\s+['"](?:\.\.?/)*(?:@/)?(?:src/)?test-utils['"])"""
)

# Import statement pattern for TypeScript/TSX files
_IMPORT_FROM_PATTERN = re.compile(
    r"""import\s+(?:\{[^}]*\}|\*\s+as\s+\w+|\w+)\s+from\s+['"]([^'"]+)['"]"""
)

# Relative import pattern (starts with . or ..)
_RELATIVE_IMPORT = re.compile(r"""^\.\.?/""")

# Alias import pattern (starts with @/)
_ALIAS_IMPORT = re.compile(r"""^@/""")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

class FrontendScanner:
    """Analyses frontend TypeScript test files for anti-patterns.

    Typical usage::

        scanner = FrontendScanner(source_dir="frontend/src")
        violations = scanner.analyze_file("frontend/src/App.test.tsx")
    """

    def __init__(
        self,
        source_dir: str = "frontend/src",
    ) -> None:
        """
        Args:
            source_dir: Root directory for frontend source files.  Used to
                resolve relative imports and check for stale imports.
        """
        self._source_dir = source_dir
        self._source_files: Optional[Set[str]] = None

    # ------------------------------------------------------------------
    # Public methods
    # ------------------------------------------------------------------

    def analyze_file(self, file_path: str) -> List[FrontendViolation]:
        """Analyze a single frontend test file for violations.

        Args:
            file_path: Path to the ``.test.tsx``, ``.test.ts``, or
                ``.spec.tsx`` file to analyze.

        Returns:
            A list of :class:`FrontendViolation` instances.
        """
        path = Path(file_path)

        if not path.exists():
            logger.warning("File does not exist: %s", file_path)
            return []

        if not _is_test_file(path):
            logger.debug("Skipping non-test file: %s", file_path)
            return []

        try:
            source = path.read_text(encoding="utf-8")
        except (PermissionError, OSError) as exc:
            logger.error("Error reading file %s: %s", file_path, exc)
            return []

        file_str = str(path)
        violations: List[FrontendViolation] = []

        violations.extend(self._detect_missing_msw(source, file_str))
        violations.extend(self._detect_missing_provider(source, file_str))
        violations.extend(
            self._detect_stale_imports(source, file_str, path)
        )

        return violations

    def scan_directory(
        self,
        test_dir: Optional[str] = None,
    ) -> FrontendScanReport:
        """Scan all frontend test files in a directory.

        Args:
            test_dir: Directory to scan.  Defaults to ``self._source_dir``.

        Returns:
            A :class:`FrontendScanReport` with all violations.
        """
        scan_dir = test_dir or self._source_dir
        report = FrontendScanReport()

        test_files = self._collect_test_files(scan_dir)
        report.test_files = test_files
        report.files_scanned = len(test_files)

        for test_file in test_files:
            violations = self.analyze_file(test_file)
            report.violations.extend(violations)

        return report

    # ------------------------------------------------------------------
    # Detection methods
    # ------------------------------------------------------------------

    def _detect_missing_msw(
        self,
        source: str,
        file_path: str,
    ) -> List[FrontendViolation]:
        """Detect HTTP calls without MSW handler setup.

        Flags test files that contain ``fetch(``, ``axios.get(``, etc.
        without a corresponding ``setupServer`` or ``http.get/post/...``
        handler.
        """
        violations: List[FrontendViolation] = []

        # Check if the file has any HTTP call patterns
        http_call_lines: List[int] = []
        source_lines = source.splitlines()

        for line_idx, line in enumerate(source_lines, start=1):
            stripped = line.strip()
            # Skip comments
            if stripped.startswith("//") or stripped.startswith("/*"):
                continue
            for pattern in _HTTP_CALL_PATTERNS:
                if pattern.search(line):
                    http_call_lines.append(line_idx)
                    break

        if not http_call_lines:
            return violations

        # Check if MSW is set up anywhere in the file
        has_msw = any(
            pattern.search(source) for pattern in _MSW_SETUP_PATTERNS
        )

        if not has_msw:
            # Report the first HTTP call line as the violation location
            violations.append(FrontendViolation(
                file_path=file_path,
                line_number=http_call_lines[0],
                violation_type="missing_msw",
                severity="high",
                description=(
                    f"Test file makes HTTP calls (found {len(http_call_lines)} "
                    f"call(s)) without MSW (Mock Service Worker) handler "
                    f"setup. API calls in tests should use MSW handlers "
                    f"via setupServer and http.get/post/put/delete."
                ),
                suggested_fix=(
                    "Add MSW handlers using setupServer() and "
                    "http.get/post/put/delete() from 'msw'. "
                    "See frontend/src/setupTests.ts for examples."
                ),
            ))

        return violations

    def _detect_missing_provider(
        self,
        source: str,
        file_path: str,
    ) -> List[FrontendViolation]:
        """Detect direct render import from @testing-library/react.

        Flags test files that import ``render`` from
        ``@testing-library/react`` instead of the project's ``test-utils``
        module.
        """
        violations: List[FrontendViolation] = []

        source_lines = source.splitlines()

        for line_idx, line in enumerate(source_lines, start=1):
            stripped = line.strip()
            if stripped.startswith("//") or stripped.startswith("/*"):
                continue

            if _DIRECT_RENDER_IMPORT.search(line):
                # Check if test-utils render is also imported (unlikely but
                # possible in transitional code)
                has_test_utils = _TEST_UTILS_RENDER_IMPORT.search(source)
                if not has_test_utils:
                    violations.append(FrontendViolation(
                        file_path=file_path,
                        line_number=line_idx,
                        violation_type="missing_provider",
                        severity="medium",
                        description=(
                            "Test imports 'render' directly from "
                            "'@testing-library/react' instead of the "
                            "project's 'test-utils' module. The test-utils "
                            "render wrapper includes required providers "
                            "(ChakraProvider, I18nextProvider, AuthContext, "
                            "Router)."
                        ),
                        suggested_fix=(
                            "Replace the import with: "
                            "import { render } from '../test-utils' "
                            "(or the appropriate relative path to "
                            "src/test-utils.tsx)."
                        ),
                    ))

        return violations

    def _detect_stale_imports(
        self,
        source: str,
        file_path: str,
        file_path_obj: Path,
    ) -> List[FrontendViolation]:
        """Detect imports from paths that don't exist in the source tree.

        Checks relative imports (``./``, ``../``) and alias imports
        (``@/``) against the actual file system.
        """
        violations: List[FrontendViolation] = []
        source_lines = source.splitlines()

        for line_idx, line in enumerate(source_lines, start=1):
            stripped = line.strip()
            if stripped.startswith("//") or stripped.startswith("/*"):
                continue

            match = _IMPORT_FROM_PATTERN.search(line)
            if not match:
                continue

            import_path = match.group(1)

            # Skip node_modules imports (no dot prefix, no @/ alias)
            if not _RELATIVE_IMPORT.match(import_path) and not _ALIAS_IMPORT.match(import_path):
                continue

            # Resolve the import path to a file system path
            resolved = self._resolve_import_path(
                import_path, file_path_obj
            )

            if resolved is not None and not self._file_exists(resolved):
                violations.append(FrontendViolation(
                    file_path=file_path,
                    line_number=line_idx,
                    violation_type="stale_import",
                    severity="high",
                    description=(
                        f"Import from '{import_path}' does not resolve to "
                        f"an existing file. The component may have been "
                        f"moved or renamed."
                    ),
                    suggested_fix=(
                        f"Update the import path to point to the current "
                        f"location of the module. Searched for: {resolved}"
                    ),
                ))

        return violations

    # ------------------------------------------------------------------
    # Import resolution helpers
    # ------------------------------------------------------------------

    def _resolve_import_path(
        self,
        import_path: str,
        test_file: Path,
    ) -> Optional[str]:
        """Resolve an import path to a file system path.

        Handles:
        - Relative imports: ``./Foo`` → ``<test_dir>/Foo``
        - Alias imports: ``@/components/Foo`` → ``<source_dir>/components/Foo``

        Returns the resolved path (without extension) or ``None`` if the
        import cannot be resolved.
        """
        if _ALIAS_IMPORT.match(import_path):
            # @/path → source_dir/path
            relative = import_path[2:]  # strip "@/"
            return os.path.join(self._source_dir, relative)

        if _RELATIVE_IMPORT.match(import_path):
            # ./path or ../path → resolve relative to test file
            test_dir = test_file.parent
            resolved = (test_dir / import_path).resolve()
            return str(resolved)

        return None

    def _file_exists(self, base_path: str) -> bool:
        """Check if a file exists with any common extension.

        TypeScript imports omit the extension, so we check for:
        ``.tsx``, ``.ts``, ``.jsx``, ``.js``, ``.css``, ``.json``,
        and the path as-is (for directory imports with index files).
        """
        base = Path(base_path)

        # Check exact path
        if base.exists():
            return True

        # Check with common extensions
        for ext in (".tsx", ".ts", ".jsx", ".js", ".css", ".json"):
            if base.with_suffix(ext).exists():
                return True

        # Check for index file in directory
        if base.is_dir():
            for ext in (".tsx", ".ts", ".jsx", ".js"):
                if (base / f"index{ext}").exists():
                    return True

        # Check for index file (base might be a directory path)
        for ext in (".tsx", ".ts", ".jsx", ".js"):
            index_path = base / f"index{ext}"
            if index_path.exists():
                return True

        return False

    # ------------------------------------------------------------------
    # File collection
    # ------------------------------------------------------------------

    @staticmethod
    def _collect_test_files(directory: str) -> List[str]:
        """Collect frontend test files under *directory*."""
        results: List[str] = []
        root = Path(directory)

        if not root.is_dir():
            logger.warning("Directory does not exist: %s", directory)
            return results

        for p in root.rglob("*"):
            if not p.is_file():
                continue
            if _is_test_file(p):
                results.append(str(p))

        return sorted(results)


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------

def _is_test_file(path: Path) -> bool:
    """Return ``True`` if *path* is a frontend test file."""
    name = path.name
    return (
        name.endswith(".test.tsx")
        or name.endswith(".test.ts")
        or name.endswith(".test.jsx")
        or name.endswith(".test.js")
        or name.endswith(".spec.tsx")
        or name.endswith(".spec.ts")
    )
