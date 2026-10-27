"""CI/pre-commit guard: foolproof ``config#fields`` CRUD on the SAM plane (R11.2).

Sibling to the Flask ``backend/scripts/check_db_imports.py`` /
``check_raw_connection.py`` AST guards — this is the SAM / DynamoDB counterpart that
mechanically enforces the Change-Op write contract (steering
``39-backend-data-access-sam-dynamodb.md`` → "Enforcement"; spec
``.kiro/specs/Members/03 - config-fields-foolproof-crud/`` requirement R11.2; ADR 0009).

It fails the build on EITHER of two reintroductions of the proven
partial-overlay-overwrites-full-record defect (root-cause-analysis.md):

  (a) A RAW GOVERNANCE-TABLE WRITE OUTSIDE THE CHANGE-OP WRITE REPOSITORY — a
      ``.put_item(`` / ``.update_item(`` / ``.delete_item(`` call in a ``sam/**`` PRODUCT
      module that writes the GOVERNANCE PROJECTION table, other than the two sanctioned
      sites (the Change-Op write repository
      ``sam/members/repository/projection_config_write_repository.py`` and the one-time C6
      LIST->MAP migration ``sam/members/migration/functional_groups_list_to_map.py``). The
      whole-record ``put_item`` replace must stay an INTERNAL primitive only those sites
      build the item with — a new raw write anywhere else is exactly how a whole-record
      replace would sneak back onto the client-reachable path (R1.5 / R11.1 / R11.2a).

      The check is TABLE-SCOPED, not "every DynamoDB write": it fires only in a module that
      resolves the governance projection table (``get_projection_table_resource`` /
      ``resolve_projection_table_name`` / the ``GOVERNANCE_PROJECTION_TABLE`` env var). A
      module that writes a DIFFERENT aggregate (the ``sam-members`` members table via
      ``members_repository``, the mail-send tables, template bodies, …) is NOT the governance
      table and is left alone. Test modules (``sam/tests/**``) are also out of scope — they
      legitimately SEED the local-DynamoDB projection table with fixtures (steering 42),
      which is test setup, not a product write path.

  (b) A RAW STORAGE-SHAPE KEY IN AN API RESPONSE — a ``field_overlay`` / ``overrides`` /
      ``fixed_overrides`` / dotted ``{group}.{key}`` key appearing as a DICT-LITERAL KEY in
      the handler/response-shaping layer (``sam/**/handler/**``, ``sam/**/app.py`` /
      ``routes.py`` / ``router*.py``). Reads must serve the resolved Flat_View; the raw
      two-map/dotted-key layout must never cross the repository boundary into a response or
      the frontend (steering 39 resolved-view contract; R2.3 / R11.2b).

Detection is AST-based (``ast``), so a comment or docstring that merely MENTIONS
``put_item`` or ``field_overlay`` does not trip the guard — only real code does. This
mirrors ``sam/tests/test_handler_repository_boundary.py``.

Allow-list discipline (steering 39): a NEW sanctioned site is added to ``ALLOWED_*`` in a
REVIEWED change — NEVER by suppressing the guard (``--no-verify`` is not the path).

Usage::

    python scripts/check_sam_config_crud.py            # full scan of SCAN_DIRS (CI)
    python scripts/check_sam_config_crud.py [path ...]  # check only the given files (hook)

Exit code 0 = clean, 1 = violations found.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

__all__ = [
    "RAW_WRITE_METHODS",
    "RAW_SHAPE_KEYS",
    "RAW_WRITE_ALLOWED_FILES",
    "RESPONSE_SHAPE_ALLOWED_FILES",
    "SCAN_DIRS",
    "EXCLUDED_DIRS",
    "check_file",
    "scan_directory",
    "main",
]

# ──────────────────────────────────────────────────────────────────────────────────
# (a) Raw governance-table write methods — banned outside the Change-Op write repository.
# ──────────────────────────────────────────────────────────────────────────────────

#: The three DynamoDB write verbs that mutate a whole item / path. Only the sanctioned
#: Change-Op write repository may call them; everywhere else a raw write is a bypass of the
#: Change-Op contract (R11.2a). A ``.query(`` / ``.get_item(`` READ is NOT banned here — the
#: handler/router→repository boundary test (``test_handler_repository_boundary.py``) already
#: covers reads; this guard is specifically the whole-record-WRITE escape hatch.
RAW_WRITE_METHODS = frozenset({"put_item", "update_item", "delete_item"})

#: The sanctioned governance-table writers — the ONLY product files permitted to issue a raw
#: write on the governance projection table. Keyed as repo-root-relative POSIX paths:
#:   * the Change-Op write repository (``MembersConfigWriteRepository``) — ``put_item`` is its
#:     C6 create/migration primitive (``put_config`` / ``ensure_skeleton``) and ``update_item``
#:     is the runtime Change-Op path (``apply_ops``); and
#:   * the one-time C6 LIST->MAP migration backfill (design C6 / task 2.0), which is the OTHER
#:     sanctioned whole-row ``put_item`` (R1.5 explicitly keeps the migration as a primitive).
#: No other product module may write the governance table directly. A new sanctioned writer is
#: a REVIEWED addition here — never a guard suppression (steering 39).
RAW_WRITE_ALLOWED_FILES = frozenset(
    {
        "sam/members/repository/projection_config_write_repository.py",
        "sam/members/migration/functional_groups_list_to_map.py",
    }
)

#: Markers that identify a module as a GOVERNANCE-PROJECTION writer — the table-scope anchor
#: for check (a). A raw write is only flagged when the SAME module references one of these (it
#: resolves the governance projection table), so a module that writes a different aggregate
#: (members table, mail tables, template bodies) is never a false positive. The env-var name
#: and the two shared resolver helpers are the single source the real writers use (steering 39
#: fail-fast resource resolution), so matching on them tracks the real writers precisely.
_GOVERNANCE_TABLE_MARKERS = (
    "GOVERNANCE_PROJECTION_TABLE",
    "get_projection_table_resource",
    "resolve_projection_table_name",
)

# ──────────────────────────────────────────────────────────────────────────────────
# (b) Raw storage-shape keys — banned in an API response (handler/response-shaping layer).
# ──────────────────────────────────────────────────────────────────────────────────

#: The raw ``config#fields`` STORAGE-shape keys that must never cross the repository
#: boundary into an API response (steering 39; R2.3). ``field_overlay`` is the legacy
#: whole-overlay wrapper; ``overrides`` / ``fixed_overrides`` are the two storage maps; a
#: dotted ``{group}.{key}`` is the physical override key — all INTERNAL to the repository.
#: Reads serve the resolved Flat_View (bare-``key`` fields) instead.
RAW_SHAPE_KEYS = frozenset({"field_overlay", "overrides", "fixed_overrides"})

#: Files in the response-shaping layer that LEGITIMATELY name the raw-shape keys — not to
#: emit them, but to REJECT a cached old-SPA-bundle write body that still carries them (the
#: Task 5.3a stale-client guard). They reference the keys as frozenset MEMBERS / membership
#: checks, never as response dict-literal keys, so the dict-key detector does not flag them
#: today; they are allow-listed as belt-and-suspenders so a future defensive mention of the
#: shape (e.g. in an error payload naming the offending keys) does not false-positive. Keyed
#: as repo-root-relative POSIX paths. A new entry is a REVIEWED addition, never a suppression.
RESPONSE_SHAPE_ALLOWED_FILES = frozenset(
    {
        "sam/members/handler/_dispatch.py",
        "sam/members/handler/routes.py",
    }
)

#: Directory names skipped during a full scan (mirrors the Flask guards + the SAM boundary
#: test's prune of build output). ``.aws-sam`` holds COPIES of the source (build artefacts),
#: not the source of truth — scanning it would double-count every finding.
EXCLUDED_DIRS = frozenset(
    {
        ".venv",
        "venv",
        "env",
        ".env",
        "node_modules",
        ".git",
        "__pycache__",
        ".hypothesis",
        ".tox",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".aws-sam",
    }
)

#: The tree this guard scans in full-scan (CI) mode — the SAM plane only (R11.2 is a
#: SAM-plane rule; the Flask DB-access guards cover ``backend/``).
SCAN_DIRS = ("sam",)


def _rel_posix(filepath: Path) -> str:
    """POSIX path key for a scanned file.

    Normalises to forward slashes. In full-scan / hook mode the path is already
    repo-root-relative (``sam/...``); an absolute path (how a single file is sometimes
    supplied, and how tests construct fixtures under a temp root) is left absolute here and
    matched against the ``sam/...`` allow-list entries by SUFFIX (see :func:`_matches_rel`),
    so allow-list membership is independent of where the repo root sits.
    """
    rel = filepath.as_posix().replace("\\", "/")
    if rel.startswith("./"):
        rel = rel[2:]
    return rel


def _matches_rel(rel: str, candidates) -> bool:
    """True if ``rel`` is (or ends with) one of the repo-root-relative ``candidates``.

    A full scan yields ``rel == "sam/..."`` (exact match); an absolute path yields
    ``rel == "/abs/.../sam/..."`` (suffix match on ``/sam/...``). Matching on the
    ``sam/...``-anchored suffix makes the allow-lists robust to the path form without ever
    matching a mere basename (the leading ``/`` on the suffix prevents ``.../x_sam/...``
    style false positives).
    """
    for cand in candidates:
        if rel == cand or rel.endswith("/" + cand):
            return True
    return False


def _is_response_shaping_file(rel: str) -> bool:
    """True if ``rel`` is in the handler/response-shaping layer that check (b) scans.

    Scope: the Members handler package (``sam/**/handler/**``) and the top-level edge
    modules (``app.py`` / ``routes.py`` / ``router*.py``) anywhere under ``sam/``. The
    repository layer is deliberately OUT of scope for (b) — a repository legitimately shapes
    the stored item with ``fields`` / ``overrides`` dict keys; (b) only guards what crosses
    OUT to a response.
    """
    parts = rel.split("/")
    name = parts[-1]
    if "handler" in parts[:-1]:
        return True
    if name in ("app.py", "routes.py"):
        return True
    if name.startswith("router") and name.endswith(".py"):
        return True
    return False


def _dict_key_strings(tree: ast.AST):
    """Yield (string-literal dict key, lineno) for every ``{...}`` / ``dict(key=...)`` key.

    Only STRING-LITERAL keys of a dict display (``ast.Dict``) are yielded — a computed key,
    a variable, or a frozenset/list element is NOT a dict key and is ignored, which is what
    keeps the stale-bundle ``frozenset({...})`` membership sets (and every docstring mention)
    from tripping the guard.
    """
    for node in ast.walk(tree):
        if isinstance(node, ast.Dict):
            for key in node.keys:
                # ``key is None`` is ``**spread`` in a dict display — skip it.
                if isinstance(key, ast.Constant) and isinstance(key.value, str):
                    yield key.value, key.lineno


def _is_test_module(rel: str) -> bool:
    """True if ``rel`` is a SAM test module (``sam/tests/**``).

    Test modules legitimately seed the local-DynamoDB projection table with real fixtures
    (steering 42) — that is test setup, not a product write path — so check (a) skips them.
    Anchored on the ``sam/tests/`` segment so it holds for both a repo-root-relative and an
    absolute path.
    """
    return "sam/tests/" in rel


def _references_governance_table(source: str) -> bool:
    """True if the module's source mentions a governance-projection table marker.

    A cheap, robust substring test over the raw source: the real governance writers all
    resolve the table via ``get_projection_table_resource`` / ``resolve_projection_table_name``
    or name ``GOVERNANCE_PROJECTION_TABLE``. A module that writes a different aggregate does not,
    so it is not a governance writer and its raw writes are out of scope for check (a). A mere
    docstring mention is acceptable over-inclusion here — the write-method + allow-list gates
    still decide a finding, and a module that only TALKS about the table but never writes it has
    no ``put_item``/``update_item``/``delete_item`` call to flag.
    """
    return any(marker in source for marker in _GOVERNANCE_TABLE_MARKERS)


def _check_raw_writes(tree: ast.AST, rel: str, source: str) -> list[str]:
    """Return violation messages for raw governance-table writes outside the write repo (a).

    Table-scoped: fires only in a non-test module that references the governance projection
    table (see :func:`_references_governance_table`) and is not an allow-listed sanctioned
    writer. A write on a different aggregate (members/mail/template tables) is never flagged.
    """
    if _matches_rel(rel, RAW_WRITE_ALLOWED_FILES):
        return []
    if _is_test_module(rel):
        return []
    if not _references_governance_table(source):
        return []
    violations: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            method = node.func.attr
            if method in RAW_WRITE_METHODS:
                violations.append(
                    f"{rel}:{node.lineno}: raw '.{method}(' governance-table write outside "
                    f"the Change-Op write repository — whole-record writes must go through "
                    f"MembersConfigWriteRepository.apply_ops (Change-Op path) or the sanctioned "
                    f"create/migration primitive (put_config/ensure_skeleton). See steering 39 "
                    f"'Change-Op write contract' / R11.2a."
                )
    return violations


def _check_response_shape(tree: ast.AST, rel: str) -> list[str]:
    """Return violation messages for a raw storage-shape key in a response dict (b)."""
    if not _is_response_shaping_file(rel):
        return []
    if _matches_rel(rel, RESPONSE_SHAPE_ALLOWED_FILES):
        return []
    violations: list[str] = []
    for key_value, lineno in _dict_key_strings(tree):
        if key_value in RAW_SHAPE_KEYS:
            violations.append(
                f"{rel}:{lineno}: raw storage-shape key {key_value!r} in a response dict — "
                f"the raw two-map/dotted-key layout must not cross the repository boundary; "
                f"serve the resolved Flat_View instead (steering 39 resolved-view contract / "
                f"R2.3 / R11.2b)."
            )
        elif _is_dotted_group_key(key_value):
            violations.append(
                f"{rel}:{lineno}: raw dotted '{{group}}.{{key}}' storage key {key_value!r} in a "
                f"response dict — the physical override key is INTERNAL to the repository; serve "
                f"the resolved bare-'key' Flat_View instead (steering 39 / R2.3 / R11.2b)."
            )
    return violations


def _is_dotted_group_key(value: str) -> bool:
    """True if ``value`` looks like a physical dotted override key ``{group}.{key}``.

    A conservative shape match: exactly ONE dot separating two non-empty identifier-like
    segments (e.g. ``personal.gender``, ``membership.status``). This deliberately does NOT
    match a dotted MACHINE CODE (``errors.api.staleClient`` has two dots) or a filename
    (``app.py`` — ``py`` is a segment but the preceding token is a module, and these never
    appear as a RESPONSE dict key; the response layer keys on domain identities). Keeping it
    to a single dot + identifier segments avoids false positives on i18n/error codes while
    still catching the ``{group}.{key}`` overlay shape the frontend must never reconstruct.
    """
    if value.count(".") != 1:
        return False
    left, right = value.split(".", 1)
    if not left or not right:
        return False
    return left.isidentifier() and right.isidentifier()


def check_file(filepath: Path) -> list[str]:
    """Return the list of violation messages for a single ``.py`` file (both checks).

    A file that cannot be parsed (syntax error, permission, encoding) yields no violations —
    the guard is a lint, not a compiler, and a genuinely broken file surfaces elsewhere.
    """
    rel = _rel_posix(filepath)
    try:
        source = filepath.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=rel)
    except (SyntaxError, PermissionError, UnicodeDecodeError, OSError):
        return []

    violations: list[str] = []
    violations.extend(_check_raw_writes(tree, rel, source))
    violations.extend(_check_response_shape(tree, rel))
    return violations


def _iter_py_files(root: Path, excluded_dirs=EXCLUDED_DIRS):
    """Yield ``.py`` files under ``root``, skipping ``excluded_dirs`` (recursively)."""
    for entry in sorted(root.iterdir()):
        if entry.is_dir():
            if entry.name in excluded_dirs:
                continue
            yield from _iter_py_files(entry, excluded_dirs)
        elif entry.is_file() and entry.suffix == ".py":
            yield entry


def scan_directory(root: Path) -> list[str]:
    """Scan every ``.py`` file under ``root`` and return all violation messages."""
    all_violations: list[str] = []
    for py_file in _iter_py_files(root):
        all_violations.extend(check_file(py_file))
    return all_violations


def main(argv=None) -> int:
    """CLI entry point.

    With no path arguments, scans :data:`SCAN_DIRS` (full-scan / CI). With one or more path
    arguments, checks only those files (single-file / pre-commit-hook mode). Returns the exit
    code (0 clean, 1 violations) AND calls ``sys.exit`` so the shell sees it.

    Args:
        argv: Optional explicit argument list. ``None`` (the CLI default) falls back to
            ``sys.argv[1:]``; tests pass an explicit list (``main([])`` full-scan,
            ``main(['path.py'])`` single-file) so pytest's own argv never leaks in.
    """
    paths = sys.argv[1:] if argv is None else argv
    all_violations: list[str] = []

    if paths:
        for arg in paths:
            py_file = Path(arg)
            if not py_file.is_file() or py_file.suffix != ".py":
                continue
            all_violations.extend(check_file(py_file))
    else:
        root = Path(".")
        for scan_dir in SCAN_DIRS:
            dir_path = root / scan_dir
            if not dir_path.is_dir():
                continue
            all_violations.extend(scan_directory(dir_path))

    if all_violations:
        print(f"Found {len(all_violations)} config#fields CRUD guard violation(s):\n")
        for v in all_violations:
            print(f"  [FAIL] {v}")
        print(
            "\nThe config#fields write path is Change-Op only: raw governance-table writes "
            "live solely in MembersConfigWriteRepository, and no raw storage shape "
            "(field_overlay / overrides / fixed_overrides / dotted {group}.{key}) may appear "
            "in an API response. Fix the call site / response shape — do NOT suppress the "
            "guard. A new sanctioned site is a reviewed allow-list addition (steering 39)."
        )
        sys.exit(1)

    print(
        "[OK] No raw governance-table writes outside the Change-Op write repository, and no "
        "raw storage-shape key in an API response."
    )
    sys.exit(0)


if __name__ == "__main__":
    main()
