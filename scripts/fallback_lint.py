#!/usr/bin/env python3
"""
Guard-rail lint for catalogued MASKING fallback anti-patterns.

Broadens the s5f R4.3 grep guard (AST-based env/symbol scan) into a reusable
lint over the three planes (Frontend SPA, Flask Backend, SAM Edge). Each of the
8 catalogued MASKING instances is encoded as a named rule. Python source is
scanned with comments + docstrings MASKED out (so removal-documenting prose does
NOT trip a rule), mirroring the s5f guard's docstring exclusion. TS/JS source has
line/block comments stripped.

Green-on-clean: this lint passes on the current (remediated) codebase and fails
only when an anti-pattern is RE-INTRODUCED.

Usage:
  python3 scripts/fallback_lint.py
  python3 scripts/fallback_lint.py --paths backend/src sam --json
  python3 scripts/fallback_lint.py --fail-on-warnings
"""

from __future__ import annotations

import argparse
import ast
import fnmatch
import io
import json
import re
import sys
import tokenize
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class LintIssue:
    rule_id: str
    severity: str
    file: str
    line: int
    column: int
    message: str
    pattern: str


@dataclass
class LintResult:
    issues: list = field(default_factory=list)
    files_scanned: int = 0

    def add_issue(self, issue):
        self.issues.append(issue)

    def has_errors(self):
        return any(i.severity == "error" for i in self.issues)

    def to_json(self):
        return {
            "issues": [
                {
                    "rule_id": i.rule_id,
                    "severity": i.severity,
                    "file": i.file,
                    "line": i.line,
                    "column": i.column,
                    "message": i.message,
                    "pattern": i.pattern,
                }
                for i in self.issues
            ],
            "files_scanned": self.files_scanned,
            "error_count": sum(1 for i in self.issues if i.severity == "error"),
            "warning_count": sum(1 for i in self.issues if i.severity == "warning"),
        }


def _blank_span(chars, sr, sc, er, ec):
    for r in range(sr, er + 1):
        idx = r - 1
        if idx < 0 or idx >= len(chars):
            continue
        line = chars[idx]
        start = sc if r == sr else 0
        end = ec if r == er else len(line)
        for c in range(start, min(end, len(line))):
            if line[c] not in ("\n", "\r"):
                line[c] = " "


def _docstring_spans(tree):
    spans = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = getattr(node, "body", None)
            if body and isinstance(body[0], ast.Expr):
                val = body[0].value
                if isinstance(val, ast.Constant) and isinstance(val.value, str):
                    spans.append((val.lineno, val.col_offset, val.end_lineno, val.end_col_offset))
    return spans


def _comment_spans(source):
    spans = []
    try:
        for tok in tokenize.generate_tokens(io.StringIO(source).readline):
            if tok.type == tokenize.COMMENT:
                spans.append((tok.start[0], tok.start[1], tok.end[0], tok.end[1]))
    except (tokenize.TokenError, IndentationError):
        pass
    return spans


def mask_python(source):
    """Return ``source`` with comments + docstrings blanked to spaces (newlines kept)."""
    lines = source.splitlines(keepends=True)
    chars = [list(line) for line in lines]
    for span in _comment_spans(source):
        _blank_span(chars, *span)
    try:
        tree = ast.parse(source)
    except SyntaxError:
        tree = None
    if tree is not None:
        for span in _docstring_spans(tree):
            _blank_span(chars, *span)
    return "".join("".join(line) for line in chars)


def strip_js_comments(source):
    """Return ``source`` with // and /* */ comments blanked (strings preserved)."""
    out = list(source)
    i, n = 0, len(source)
    in_line = in_block = False
    quote = None
    esc = False
    while i < n:
        ch = source[i]
        if in_line:
            if ch == "\n":
                in_line = False
            else:
                out[i] = " "
            i += 1
            continue
        if in_block:
            if ch == "*" and i + 1 < n and source[i + 1] == "/":
                out[i] = out[i + 1] = " "
                i += 2
                in_block = False
                continue
            if ch != "\n":
                out[i] = " "
            i += 1
            continue
        if quote:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == quote:
                quote = None
            i += 1
            continue
        if ch in ("'", '"', "`"):
            quote = ch
            i += 1
            continue
        if ch == "/" and i + 1 < n and source[i + 1] == "/":
            in_line = True
            out[i] = out[i + 1] = " "
            i += 2
            continue
        if ch == "/" and i + 1 < n and source[i + 1] == "*":
            in_block = True
            out[i] = out[i + 1] = " "
            i += 2
            continue
        i += 1
    return "".join(out)


# ──────────────────────────────────────────────────────────────────────
# Rule catalogue — one rule per catalogued MASKING instance
# (deliverable-1-audit-table.md). Each rule encodes a REGRESSION signature
# that is GREEN on the current (remediated) code and fires only if the
# anti-pattern is re-introduced.
# ──────────────────────────────────────────────────────────────────────
RULES = [
    {
        "id": "MASK-01",
        "name": "Frontend localhost fallback for Members API base URL",
        "description": "Members API base URL resolves to localhost/127.0.0.1 instead of failing loud",
        "severity": "error",
        "planes": ["frontend"],
        "file_extensions": [".ts", ".tsx", ".js", ".jsx"],
        "patterns": [
            r"VITE_MEMBERS_API_BASE_URL[^\n]{0,60}(?:localhost|127\.0\.0\.1)",
            r"(?:localhost|127\.0\.0\.1)[^\n]{0,60}VITE_MEMBERS_API_BASE_URL",
        ],
    },
    {
        "id": "MASK-02",
        "name": "Frontend auth guest fallback",
        "description": "Frontend auth provides a guest/anonymous session instead of failing closed",
        "severity": "error",
        "planes": ["frontend"],
        "file_extensions": [".ts", ".tsx"],
        "file_globs": ["*authService.ts", "*AuthContext.tsx", "*authContext.tsx"],
        "patterns": [r"\bguest\b"],
    },
    {
        "id": "MASK-03",
        "name": "Role resolution falls back to JWT cognito:groups",
        "description": "Role resolution reads cognito:groups (two sources of truth) instead of MySQL-authoritative roles",
        "severity": "error",
        "planes": ["backend", "frontend"],
        "file_extensions": [".py", ".ts", ".tsx"],
        "file_globs": ["*/role_cache.py", "*authService.ts", "*AuthContext.tsx"],
        "patterns": [r"cognito:groups[^?\n]{0,3}\]"],
    },
    {
        "id": "MASK-04",
        "name": "Tenant resolver defaults to the first tenant",
        "description": "A tenant resolver RETURNS the first tenant instead of denying a multi-tenant user with no explicit selection",
        "severity": "error",
        "planes": ["backend"],
        "file_extensions": [".py"],
        "patterns": [
            r"return\s+tenants\s*\[\s*0\s*\]",
            r"return\s+tenant_keys\s*\[\s*0\s*\]",
        ],
        "guard_regex": r"len\(\s*(?:tenants|tenant_keys)\s*\)\s*==\s*1",
        "guard_window": 4,
    },
    {
        "id": "MASK-05",
        "name": "Hardcoded AWS access key in source",
        "description": "A literal AWS access key id is committed instead of using AWS_PROFILE / IAM roles",
        "severity": "error",
        "planes": ["backend", "sam"],
        "file_extensions": [".py", ".sh", ".yml", ".yaml", ".toml", ".env"],
        "patterns": [r"(?:AKIA|ASIA)[0-9A-Z]{16}"],
    },
    {
        "id": "MASK-06",
        "name": "SAM edge tenant fallback symbols",
        "description": "The removed local-dev tenant fallback / env constant reappears in SAM live code",
        "severity": "error",
        "planes": ["sam"],
        "file_extensions": [".py"],
        "patterns": [
            r"_local_dev_tenant_fallback",
            r"_LOCAL_TENANT_ID_ENV",
            r"MEMBERS_LOCAL_TENANT_ID",
        ],
    },
    {
        "id": "MASK-07",
        "name": "SAM edge raw role# projection handling (staleness review)",
        "description": "Raw role# projection-key handling in the SAM edge warrants the stale-role# reconcile review (Deliverable #2)",
        "severity": "warning",
        "planes": ["sam"],
        "file_extensions": [".py"],
        "patterns": [r"role#"],
    },
    {
        "id": "MASK-08",
        "name": "Cross-plane env-variable inconsistency (owned by config-promotion spec)",
        "description": "Cross-plane env drift is NOT mechanically greppable here; owned by .kiro/specs/myBacklog/config-promotion-inconsistency-across-planes.md",
        "severity": "warning",
        "planes": [],
        "file_extensions": [".py"],
        "patterns": [],
    },
]


def _parts(path):
    return path.as_posix().lower().split("/")


def should_check_plane(path, plane):
    parts = _parts(path)
    if plane == "frontend":
        return "frontend" in parts and "src" in parts
    if plane == "backend":
        return "backend" in parts and "src" in parts
    if plane == "sam":
        return "sam" in parts
    return False


def _is_excluded(path):
    p = path.as_posix().lower()
    if "/tests/" in p or "/test/" in p or "/__tests__/" in p:
        return True
    if "/.aws-sam/" in p or "/node_modules/" in p or "/__pycache__/" in p:
        return True
    name = path.name.lower()
    if name.startswith("test_"):
        return True
    for suffix in (".test.ts", ".test.tsx", ".spec.ts", ".spec.tsx",
                   ".test.js", ".test.jsx", ".spec.js", ".spec.jsx"):
        if name.endswith(suffix):
            return True
    return False


def _matches_globs(path, globs):
    if not globs:
        return True
    posix = path.as_posix()
    base = path.name
    return any(fnmatch.fnmatch(posix, g) or fnmatch.fnmatch(base, g.lstrip("*/")) for g in globs)


def _rule_code_text(path, raw):
    """Return the code-only text for a file (comments/docstrings masked)."""
    if path.suffix == ".py":
        return mask_python(raw)
    return strip_js_comments(raw)


def scan_file(path, raw, rule, result):
    code = _rule_code_text(path, raw)
    lines = code.splitlines()
    guard = rule.get("guard_regex")
    window = rule.get("guard_window", 4)
    guard_re = re.compile(guard) if guard else None

    for idx, line in enumerate(lines):
        for pattern in rule["patterns"]:
            m = re.search(pattern, line, re.IGNORECASE)
            if not m:
                continue
            if guard_re is not None:
                start = max(0, idx - window)
                context = "\n".join(lines[start:idx + 1])
                if guard_re.search(context):
                    continue
            result.add_issue(
                LintIssue(
                    rule_id=rule["id"],
                    severity=rule["severity"],
                    file=path.as_posix(),
                    line=idx + 1,
                    column=m.start(),
                    message=rule["description"],
                    pattern=pattern,
                )
            )


def run_lint(paths=None):
    """Run all rules across the given roots (default: the three planes)."""
    result = LintResult()
    roots = [Path(p) for p in paths] if paths else [
        Path("frontend/src"), Path("backend/src"), Path("sam")
    ]

    exts = set()
    for rule in RULES:
        exts.update(rule.get("file_extensions", []))

    files = set()
    for root in roots:
        if not root.exists():
            continue
        for ext in exts:
            for f in root.rglob(f"*{ext}"):
                if f.is_file() and not _is_excluded(f):
                    files.add(f)

    result.files_scanned = len(files)
    for path in sorted(files):
        for rule in RULES:
            if not rule.get("patterns"):
                continue
            if path.suffix not in rule.get("file_extensions", []):
                continue
            if not any(should_check_plane(path, pl) for pl in rule.get("planes", [])):
                continue
            if not _matches_globs(path, rule.get("file_globs")):
                continue
            try:
                raw = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            scan_file(path, raw, rule, result)
    return result


def main():
    parser = argparse.ArgumentParser(
        description="Guard-rail lint for catalogued MASKING fallback anti-patterns"
    )
    parser.add_argument(
        "--paths", nargs="+",
        help="Paths to scan (default: frontend/src, backend/src, sam)",
    )
    parser.add_argument(
        "--fail-on-warnings", action="store_true",
        help="Exit non-zero on warnings too (CI strict mode)",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON")
    args = parser.parse_args()

    result = run_lint(args.paths)

    if args.json:
        print(json.dumps(result.to_json(), indent=2))
    elif not result.issues:
        print("OK: no MASKING fallback anti-patterns detected "
              f"({result.files_scanned} files scanned)")
    else:
        for issue in result.issues:
            marker = "ERROR" if issue.severity == "error" else "WARN"
            print(f"{marker} [{issue.rule_id}] {issue.file}:{issue.line}:{issue.column}")
            print(f"    {issue.message}")
            print(f"    Pattern: {issue.pattern}\n")
        errors = sum(1 for i in result.issues if i.severity == "error")
        warns = sum(1 for i in result.issues if i.severity == "warning")
        print(f"Scanned {result.files_scanned} files - Errors: {errors}, Warnings: {warns}")

    if result.has_errors() or (args.fail_on_warnings and result.issues):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
