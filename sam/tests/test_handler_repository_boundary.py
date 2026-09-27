"""
Handler->repository boundary guard for the SAM / Lambda plane
(spec security-assessment-2026-09-26, task L3 — guards risk S3 / attack path AP-S2).

WHY THIS EXISTS
---------------
The SAM plane's multi-tenant isolation is *structural*: the repository is the SOLE
DynamoDB touch-point, and every op it performs is ``tenant_id``-PK scoped (no
``.scan()``, ``_require_tenant`` guard). Handlers and routers hold NO boto3 and never
touch DynamoDB directly — they go through the repository, so tenant scoping cannot be
bypassed by construction (assessment: "AP-S2 — Bypass the repository to skip tenant
scoping (BLOCKED, structural)").

That guarantee is only as durable as the discipline behind it. A future handler that
grew a direct ``boto3.resource('dynamodb')`` + ``.query()`` (or worse, ``.scan()``)
would reintroduce the exact cross-tenant risk the repository boundary exists to prevent
— and, because the deployed IAM has no ``dynamodb:LeadingKeys`` backstop (risk S1), a
bug above the repository would NOT be caught by an IAM condition. Isolation rests on the
code staying correct.

This test is that discipline, mechanised. It statically scans every
``sam/**/handler*.py`` and ``sam/**/router*.py`` source module (via the ``ast`` module —
so comments and docstrings that merely *mention* boto3/DynamoDB do not trip it) and
fails, naming the offending file, if a handler/router:
  * imports boto3 (``import boto3`` / ``from boto3 ...``), or
  * makes a direct DynamoDB call (``.Table(``, ``.query(``, ``.scan(``, ``.put_item(``,
    ``.get_item(``, ``.update_item(``, ``.delete_item(``, ``.batch_write_item(``), or
  * resolves a DynamoDB resource/client (``boto3.resource('dynamodb')`` /
    ``boto3.client('dynamodb')``).

It passes on the current tree (the repository is the sole DynamoDB touch-point today).
The fix for a future failure is to move the DynamoDB access DOWN into the repository —
NOT to relax this guard.
"""

import ast
import os

# Repo root = two levels up from this file (sam/tests/ -> sam/ -> repo root).
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_SAM_ROOT = os.path.join(_REPO_ROOT, "sam")

# Method names that, when called as an attribute (``x.query(...)``), are direct
# DynamoDB table/client operations. The repository is the only layer allowed to make
# these; a handler/router must not.
_DYNAMODB_CALL_METHODS = frozenset(
    {
        "Table",
        "query",
        "scan",
        "put_item",
        "get_item",
        "update_item",
        "delete_item",
        "batch_write_item",
    }
)


def _iter_handler_router_sources():
    """Yield (relpath, abspath) for every SAM handler*/router* source module.

    Discovers ``sam/**/handler*.py`` and ``sam/**/router*.py`` (a bare ``handler.py``
    like ``sam/pretokengen/handler.py`` and package handlers like
    ``sam/members/handler/app.py`` / ``router.py`` alike). Build artefacts under any
    ``.aws-sam`` directory are skipped — they are copies of the source, not the source
    of truth, and would produce duplicate/noise findings.
    """
    for dirpath, dirnames, filenames in os.walk(_SAM_ROOT):
        # Prune vendored build output and caches in-place so os.walk never descends.
        dirnames[:] = [
            d for d in dirnames if d not in (".aws-sam", "__pycache__", ".pytest_cache")
        ]
        for name in filenames:
            if not name.endswith(".py"):
                continue
            # A module is in scope if its filename starts with handler/router, OR it
            # lives inside a ``handler`` package directory (e.g. handler/app.py).
            in_handler_pkg = os.path.basename(dirpath) == "handler"
            if name.startswith("handler") or name.startswith("router") or in_handler_pkg:
                abspath = os.path.join(dirpath, name)
                relpath = os.path.relpath(abspath, _REPO_ROOT)
                yield relpath, abspath


def _scan_module_for_violations(relpath, source):
    """Return a list of human-readable violation strings for one module's source.

    Uses ``ast`` so only real code counts — a docstring or ``# comment`` that mentions
    boto3 or ``.query(`` is ignored (the Members ``_json_default`` docstring, which
    references "boto3's resource client", must NOT trip this guard).
    """
    violations = []
    tree = ast.parse(source, filename=relpath)

    for node in ast.walk(tree):
        # 1) import boto3  /  import boto3 as b
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "boto3" or alias.name.startswith("boto3."):
                    violations.append(
                        f"line {node.lineno}: imports boto3 (`import {alias.name}`)"
                    )

        # 2) from boto3 import ...  /  from boto3.dynamodb import ...
        elif isinstance(node, ast.ImportFrom):
            if node.module and (node.module == "boto3" or node.module.startswith("boto3.")):
                violations.append(
                    f"line {node.lineno}: imports boto3 (`from {node.module} import ...`)"
                )

        # 3) Attribute calls: x.query(...), x.scan(...), x.Table(...), etc., plus the
        #    boto3.resource('dynamodb') / boto3.client('dynamodb') resolvers.
        elif isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Attribute):
                attr = func.attr
                # boto3.resource('dynamodb') / boto3.client('dynamodb')
                if attr in ("resource", "client") and _is_boto3_dynamodb(func, node):
                    violations.append(
                        f"line {node.lineno}: resolves a DynamoDB {attr} "
                        f"(`boto3.{attr}('dynamodb')`)"
                    )
                elif attr in _DYNAMODB_CALL_METHODS:
                    violations.append(
                        f"line {node.lineno}: direct DynamoDB call (`.{attr}(`)"
                    )

    return violations


def _is_boto3_dynamodb(func_attr, call_node):
    """True if this is ``boto3.resource('dynamodb')`` / ``boto3.client('dynamodb')``.

    Requires BOTH the receiver to be the ``boto3`` name AND the first positional arg to
    be the literal ``"dynamodb"`` — so an unrelated ``foo.resource("s3")`` is not a
    false positive. (The import-boto3 rule above already blocks the ``boto3`` name from
    existing in a handler at all, but this keeps the DynamoDB-specific message precise.)
    """
    receiver = func_attr.value
    if not (isinstance(receiver, ast.Name) and receiver.id == "boto3"):
        return False
    if not call_node.args:
        return False
    first = call_node.args[0]
    return isinstance(first, ast.Constant) and first.value == "dynamodb"


def test_handler_router_sources_are_discovered():
    """Sanity: discovery finds the known SAM handler/router modules.

    Guards against the guard passing vacuously (e.g. if discovery silently found nothing
    because the tree moved). If SAM handlers exist, we must be scanning them.
    """
    found = {relpath for relpath, _ in _iter_handler_router_sources()}
    assert found, (
        "Expected to discover at least one SAM handler/router module under sam/, "
        "but found none — the boundary guard would pass vacuously."
    )
    # The two known handler entry points must be in scope (fail loudly if a rename or
    # move slipped them past discovery).
    assert any(p.endswith(os.path.join("pretokengen", "handler.py")) for p in found), (
        f"pretokengen/handler.py not discovered; found: {sorted(found)}"
    )
    assert any(
        p.endswith(os.path.join("members", "handler", "app.py")) for p in found
    ), f"members/handler/app.py not discovered; found: {sorted(found)}"


def test_no_handler_or_router_touches_dynamodb_directly():
    """No SAM handler/router may import boto3 or call DynamoDB directly (task L3, AP-S2).

    The repository must remain the SOLE DynamoDB touch-point. If this fails, a
    handler/router has grown a direct boto3 import or DynamoDB call — move that access
    down into the repository rather than relaxing this guard.
    """
    all_violations = {}
    for relpath, abspath in _iter_handler_router_sources():
        with open(abspath, "r", encoding="utf-8") as fh:
            source = fh.read()
        module_violations = _scan_module_for_violations(relpath, source)
        if module_violations:
            all_violations[relpath] = module_violations

    assert not all_violations, (
        "SAM handler/router modules must NOT touch DynamoDB directly — the repository is "
        "the sole DynamoDB touch-point (guards risk S3 / attack path AP-S2). Move the "
        "offending access down into the repository. Offenders:\n"
        + "\n".join(
            f"  - {relpath}:\n"
            + "\n".join(f"      * {v}" for v in violations)
            for relpath, violations in sorted(all_violations.items())
        )
    )
