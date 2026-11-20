"""Unit tests for scripts/fallback_lint.py (Deliverable #6 — guard-rail lint).

These pin the reusable MASKING-fallback lint that broadens the s5f R4.3 grep
-guard (see .kiro/specs/Common/Frameworks/fallback-patterns/). They assert the
lint is GREEN on the remediated repo and FLAGS each catalogued anti-pattern when
re-introduced, while NOT tripping on docstrings/comments or the legitimate
single-tenant ``len(...) == 1`` degenerate case.
"""

import importlib.util
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_ROOT = Path(__file__).resolve().parents[3]
_SCRIPT = _ROOT / "scripts" / "fallback_lint.py"


def _load_lint_module():
    import sys

    spec = importlib.util.spec_from_file_location("fallback_lint", _SCRIPT)
    module = importlib.util.module_from_spec(spec)
    # Register before exec so @dataclass can resolve the module via sys.modules.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


fallback_lint = _load_lint_module()


def _write(root: Path, rel: str, content: str) -> None:
    target = root / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")


def _rule_ids(root: Path) -> set:
    result = fallback_lint.run_lint([str(root)])
    return {i.rule_id for i in result.issues}


def test_lint_is_green_on_remediated_repo():
    roots = [
        str(_ROOT / "frontend" / "src"),
        str(_ROOT / "backend" / "src"),
        str(_ROOT / "sam"),
    ]
    result = fallback_lint.run_lint(roots)
    errors = [
        f"{i.rule_id} {i.file}:{i.line} pattern={i.pattern}"
        for i in result.issues
        if i.severity == "error"
    ]
    assert result.has_errors() is False, errors


def test_flags_frontend_localhost_members_base_url(tmp_path):
    _write(
        tmp_path,
        "frontend/src/bad.ts",
        "const u = import.meta.env.VITE_MEMBERS_API_BASE_URL || 'http://localhost:3000';\n",
    )
    assert "MASK-01" in _rule_ids(tmp_path)


def test_flags_backend_cognito_groups_role_read(tmp_path):
    _write(
        tmp_path,
        "backend/src/auth/role_cache.py",
        "def f(payload):\n    return payload['cognito:groups']\n",
    )
    assert "MASK-03" in _rule_ids(tmp_path)


def test_flags_unguarded_first_tenant_return(tmp_path):
    _write(
        tmp_path,
        "backend/src/auth/tenant_context.py",
        "def get(tenants):\n    return tenants[0]\n",
    )
    assert "MASK-04" in _rule_ids(tmp_path)


def test_allows_guarded_single_tenant_return(tmp_path):
    _write(
        tmp_path,
        "backend/src/auth/tenant_context.py",
        "def get(tenants):\n    if len(tenants) == 1:\n        return tenants[0]\n    return None\n",
    )
    assert "MASK-04" not in _rule_ids(tmp_path)


def test_flags_reintroduced_sam_tenant_fallback_symbol(tmp_path):
    _write(
        tmp_path,
        "sam/members/handler/app.py",
        "def _local_dev_tenant_fallback():\n    pass\n",
    )
    assert "MASK-06" in _rule_ids(tmp_path)


def test_ignores_docstring_and_comment_mentions(tmp_path):
    _write(
        tmp_path,
        "sam/members/handler/doc.py",
        'def f():\n    """Documents MEMBERS_LOCAL_TENANT_ID removal."""\n    return 1\n',
    )
    _write(
        tmp_path,
        "sam/members/handler/comment.py",
        "def g():\n    # no MEMBERS_LOCAL_TENANT_ID fallback\n    return 1\n",
    )
    assert "MASK-06" not in _rule_ids(tmp_path)


def test_flags_hardcoded_aws_access_key(tmp_path):
    _write(
        tmp_path,
        "sam/members/handler/key.py",
        "KEY = 'AKIAABCDEFGHIJKLMNOP'\n",
    )
    assert "MASK-05" in _rule_ids(tmp_path)
