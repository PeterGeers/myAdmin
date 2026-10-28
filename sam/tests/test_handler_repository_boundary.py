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
_REPO_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
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
            if name.startswith(("handler", "router")) or in_handler_pkg:
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
            if node.module and (
                node.module == "boto3" or node.module.startswith("boto3.")
            ):
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
            f"  - {relpath}:\n" + "\n".join(f"      * {v}" for v in violations)
            for relpath, violations in sorted(all_violations.items())
        )
    )


# ════════════════════════════════════════════════════════════════════════════════════
# config#fields foolproof-CRUD boundary (spec 03 Members/03-config-fields-foolproof-crud,
# task 8.3 — R11.4; design "Enforcement"; steering 39 "resolved-view contract").
#
# WHY THIS SECTION EXISTS
# -----------------------
# The original production defect (`.kiro/specs/Members/root-cause-analysis.md`, proven 3×)
# was a PARTIAL whole-record REPLACE of the `config#fields` row that silently truncated the
# functional-group catalog / the field set. Spec 03 makes that STRUCTURALLY impossible: every
# runtime `config#fields` write goes through the Change-Op service
# (`ConfigFieldsCrudService`) → the repository's `apply_ops` PATH `update_item`; the whole-row
# `put_item` REPLACE primitive (`MembersConfigWriteRepository.put_config`) survives ONLY as an
# internal create/migration primitive (C6 `ensure_skeleton` + the LIST→MAP migration) and is
# NEVER reachable from a handler or domain module on the `config#fields` runtime write path
# (R1.5 / R11.1).
#
# This is the import/boundary half of the mechanical enforcement (R11.4): the dedicated CI
# guard (`scripts/check_sam_config_crud.py`, task 8.1 — built in parallel) is the commit-time
# pattern scan; THIS test is the in-suite, AST-based proof that:
#
#   1. No handler/domain module CALLS the whole-row REPLACE primitive `put_config` EXCEPT the
#      ONE sanctioned generic `{scope, mail}` whole-object door — so the config#fields
#      Change-Op service (and any future field-config module) cannot grow a `put_config` call
#      without turning this test red. The generic door is DELIBERATELY excluded from
#      `config#fields` (spec 03 task 7.1): `config#fields` is NOT in its writable set, so even
#      the one allowed caller cannot replace a fields row.
#   2. The `config#fields` Change-Op service uses the `apply_ops` PATH-write contract and NOT
#      the whole-row primitive — a positive + negative pin on that specific module.
#   3. A handler-shaped field-config response built over the REAL committed h-dcn fixture
#      carries NO raw storage-shape key (`field_overlay` / `overrides` / `fixed_overrides` /
#      dotted `{group}.{key}`) — reinforcing task 5.3 at the boundary (steering 39 / R3 / R11.4;
#      the raw storage shape MUST NOT cross the repository boundary into an API response).
#
# The fix for a future failure is to route the write through the Change-Op service (`apply_ops`)
# and serve the resolved Flat_View — NOT to relax this guard or add to the allow-list without a
# reviewed change.
# ════════════════════════════════════════════════════════════════════════════════════

import json as _json

# The whole-row REPLACE primitive this section guards. `put_config` is `MembersConfigWriteRepository`'s
# whole-row `put_item` REPLACE — the C6 create/migration primitive ONLY (R1.5). A handler/domain
# module calling it on a runtime write path is the exact truncation hazard spec 03 kills.
_WHOLE_RECORD_REPLACE_PRIMITIVE = "put_config"

# The ONE sanctioned caller of the whole-row REPLACE primitive outside the repository itself:
# the GENERIC `{scope, mail}` whole-object write door (spec 03 task 7.1 keeps scope/mail on the
# whole-object contract; `config#fields` is DELIBERATELY excluded from its writable set, so this
# door can never replace a fields row). Keyed by repo-relative path so a move is caught.
#
# `config_write_service.py` DEFINES a domain method named `put_config` and delegates to the
# repository's `put_config`; `_dispatch_config.py` calls that domain service on the generic
# `write_config` branch. Both are the generic scope/mail door — allowed. (The per-route dispatch
# body was split BY RESOURCE out of `_dispatch.py` into `_dispatch_{members,analytics,config}.py`
# — code-quality-fixes-2026-10-28 task 4; the `write_config` branch that calls the door lives in
# `_dispatch_config.py` now, so the allow-list points there instead of the former `_dispatch.py`.)
# Any OTHER handler/domain caller (notably the config#fields Change-Op service) is a violation.
# Adding to this set is a REVIEWED change, never a silent widening.
_ALLOWED_WHOLE_RECORD_REPLACE_CALLERS = frozenset(
    {
        os.path.join("sam", "members", "domain", "config_write_service.py"),
        os.path.join("sam", "members", "handler", "_dispatch_config.py"),
    }
)

# The config#fields Change-Op service — the SOLE domain authority for `config#fields` runtime
# writes (design C1). It MUST delegate to `apply_ops` and MUST NOT touch the whole-row primitive.
_CONFIG_FIELDS_CRUD_SERVICE_RELPATH = os.path.join(
    "sam", "members", "domain", "config_fields_crud_service.py"
)

# The sanctioned Change-Op PATH-write contract the field-config service delegates to (task 2.4).
_CHANGE_OP_WRITE_PRIMITIVE = "apply_ops"

# Raw storage-shape keys that MUST NOT cross the repository boundary into an API response
# (steering 39 / R3). `field_overlay` is the wire envelope the drift once served; `overrides` /
# `fixed_overrides` are the fixed-field override map's storage / wire names; a dotted
# `{group}.{key}` is a reconstructed storage key. Serving any of these is the root-cause shape.
_RAW_SHAPE_KEYS = frozenset({"field_overlay", "overrides", "fixed_overrides"})


def _iter_handler_domain_sources():
    """Yield (relpath, abspath) for every SAM handler/router/domain source module.

    Superset of :func:`_iter_handler_router_sources`: the whole-record-replace guard (R11.4)
    scans the DOMAIN layer too, because the `config#fields` Change-Op service and the generic
    config-write service both live under ``sam/**/domain``. Build artefacts under any
    ``.aws-sam`` directory (copies, not the source of truth) are skipped.
    """
    for dirpath, dirnames, filenames in os.walk(_SAM_ROOT):
        dirnames[:] = [
            d for d in dirnames if d not in (".aws-sam", "__pycache__", ".pytest_cache")
        ]
        in_domain_pkg = os.path.basename(dirpath) == "domain"
        in_handler_pkg = os.path.basename(dirpath) == "handler"
        for name in filenames:
            if not name.endswith(".py"):
                continue
            if (
                name.startswith(("handler", "router"))
                or in_handler_pkg
                or in_domain_pkg
            ):
                abspath = os.path.join(dirpath, name)
                relpath = os.path.relpath(abspath, _REPO_ROOT)
                yield relpath, abspath


def _calls_method(source, relpath, method_name):
    """Return the line numbers at which ``x.<method_name>(...)`` is CALLED in ``source``.

    AST-based (like the DynamoDB-call scan above) so a docstring / ``# comment`` that merely
    MENTIONS the method name does not count — only a real attribute CALL
    (``something.put_config(...)``) is a match. This is what distinguishes the generic
    scope/mail door (which genuinely calls ``put_config``) from the many modules whose prose
    references it.
    """
    tree = ast.parse(source, filename=relpath)
    lines = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == method_name
        ):
            lines.append(node.lineno)
    return lines


# ── (1) No handler/domain module calls the whole-row REPLACE primitive except the one door ──


def test_config_fields_crud_service_is_discovered():
    """Sanity: the whole-record-replace guard actually scans the modules that matter.

    Guards against the R11.4 guard passing vacuously (discovery silently finding nothing, or the
    Change-Op service / the allowed generic door being renamed/moved past the scan).
    """
    found = {relpath for relpath, _ in _iter_handler_domain_sources()}
    assert found, (
        "handler/domain discovery found nothing — the R11.4 guard would pass vacuously."
    )
    assert _CONFIG_FIELDS_CRUD_SERVICE_RELPATH in found, (
        f"{_CONFIG_FIELDS_CRUD_SERVICE_RELPATH} not discovered; the config#fields Change-Op "
        f"service must be in scope for the whole-record-replace guard. Found: {sorted(found)}"
    )
    for allowed in _ALLOWED_WHOLE_RECORD_REPLACE_CALLERS:
        assert allowed in found, (
            f"allow-listed whole-record-replace caller {allowed} was not discovered — it may "
            f"have moved; the allow-list is stale. Found: {sorted(found)}"
        )


def test_no_handler_or_domain_calls_the_whole_record_replace_primitive_except_the_generic_door():
    """Only the sanctioned generic {scope, mail} door may call the whole-row REPLACE primitive.

    R11.4 / R1.5: every `config#fields` RUNTIME write goes through the Change-Op service →
    `apply_ops` PATH `update_item`; the whole-row `put_config` REPLACE is an INTERNAL create/
    migration primitive only (C6). A handler/domain module (other than the one generic scope/mail
    door) that calls `put_config` has reintroduced the partial-whole-record-replace truncation
    hazard — route the write through the Change-Op service (`apply_ops`) instead of relaxing this
    guard or widening the allow-list without review.
    """
    offenders = {}
    for relpath, abspath in _iter_handler_domain_sources():
        if relpath in _ALLOWED_WHOLE_RECORD_REPLACE_CALLERS:
            continue
        with open(abspath, "r", encoding="utf-8") as fh:
            source = fh.read()
        hit_lines = _calls_method(source, relpath, _WHOLE_RECORD_REPLACE_PRIMITIVE)
        if hit_lines:
            offenders[relpath] = hit_lines

    assert not offenders, (
        "No SAM handler/domain module may call the whole-row REPLACE primitive "
        f"`{_WHOLE_RECORD_REPLACE_PRIMITIVE}` except the sanctioned generic {{scope, mail}} door "
        f"({sorted(_ALLOWED_WHOLE_RECORD_REPLACE_CALLERS)}). A new caller reintroduces the "
        "partial-whole-record-replace truncation hazard (R11.4 / R1.5 / root-cause-analysis). "
        "Route the write through the Change-Op service (`apply_ops`), do NOT widen the allow-list "
        "without a reviewed change. Offenders:\n"
        + "\n".join(
            f"  - {relpath}: line(s) {lines}"
            for relpath, lines in sorted(offenders.items())
        )
    )


# ── (2) The config#fields Change-Op service uses apply_ops, never the whole-row primitive ──


def test_config_fields_crud_service_uses_change_op_path_not_whole_record_replace():
    """The config#fields Change-Op service delegates to `apply_ops`, never `put_config` (C1/C2).

    Positive + negative pin on the SOLE `config#fields` write authority: it MUST call the
    Change-Op PATH-write contract (`apply_ops`) and MUST NOT call the whole-row REPLACE primitive
    (`put_config`). This is what makes a partial payload structurally unable to truncate the
    catalog (spec 03 root cause) — enforced at the source, not just by convention.
    """
    abspath = os.path.join(_REPO_ROOT, _CONFIG_FIELDS_CRUD_SERVICE_RELPATH)
    with open(abspath, "r", encoding="utf-8") as fh:
        source = fh.read()

    assert _calls_method(
        source, _CONFIG_FIELDS_CRUD_SERVICE_RELPATH, _CHANGE_OP_WRITE_PRIMITIVE
    ), (
        f"{_CONFIG_FIELDS_CRUD_SERVICE_RELPATH} must delegate `config#fields` writes to the "
        f"repository's `{_CHANGE_OP_WRITE_PRIMITIVE}` PATH-write contract (task 2.4) — none found."
    )
    forbidden = _calls_method(
        source, _CONFIG_FIELDS_CRUD_SERVICE_RELPATH, _WHOLE_RECORD_REPLACE_PRIMITIVE
    )
    assert not forbidden, (
        f"{_CONFIG_FIELDS_CRUD_SERVICE_RELPATH} must NOT call the whole-row REPLACE primitive "
        f"`{_WHOLE_RECORD_REPLACE_PRIMITIVE}` (that is the truncation hazard) — found at line(s) "
        f"{forbidden}. Use `{_CHANGE_OP_WRITE_PRIMITIVE}` (R11.4 / R1.5)."
    )


# ── (3) A handler response over the REAL fixture carries no raw storage-shape key ──

_FIXTURE_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "fixtures",
    "hdcn_config_fields_overlay.json",
)


class _BoundaryFakeTable:
    """In-memory DynamoDB Table stand-in (query side) — mirrors the sibling projection-reader
    tests so no AWS / boto3 is touched (steering 39/34). Isolated per partition key."""

    def __init__(self):
        self.store = {}

    def put(self, item):
        from services import projection_schema as schema

        self.store[(item[schema.PARTITION_KEY_ATTR], item[schema.SORT_KEY_ATTR])] = (
            dict(item)
        )

    def query(self, KeyConditionExpression=None):
        expr = KeyConditionExpression.get_expression()
        tenant_id = expr["values"][1]
        return {"Items": [dict(v) for k, v in self.store.items() if k[0] == tenant_id]}


def _collect_raw_shape_keys(payload, trail=""):
    """Walk a JSON-able handler response and return every (json-path, key) that is a raw
    storage-shape key — a literal `_RAW_SHAPE_KEYS` member OR a dotted `{group}.{key}` storage
    key (a reconstructed override path, the shape steering 39 forbids crossing the boundary).

    A dotted key is only flagged as a MAP KEY (a reconstructed storage identity); dotted strings
    that are VALUES (e.g. a label) are not storage keys and are ignored.
    """
    found = []
    if isinstance(payload, dict):
        for key, value in payload.items():
            here = f"{trail}.{key}" if trail else str(key)
            if key in _RAW_SHAPE_KEYS:
                found.append((here, key))
            # A dotted map key is a reconstructed `{group}.{key}` storage identity leaking out.
            if isinstance(key, str) and "." in key and not key.startswith("."):
                found.append((here, key))
            found.extend(_collect_raw_shape_keys(value, here))
    elif isinstance(payload, list):
        for i, item in enumerate(payload):
            found.extend(_collect_raw_shape_keys(item, f"{trail}[{i}]"))
    return found


def _build_field_config_response_over_real_fixture():
    """Build the handler-shaped `GET /members/field-config` response over the REAL h-dcn row.

    Seeds a projection reader with the committed real `config#fields` fixture (the stored
    `fields` / `overrides` / `functional_groups` shape — NOT a hand-built one; spec 11's *trust
    runs, not inference*), composes the SAME `MembershipService.get_field_config` the edge
    serializes, and returns the JSON-roundtripped dict (exactly what the handler `json.dumps`es).
    """
    import sys as _sys

    if _REPO_ROOT not in _sys.path:
        _sys.path.insert(0, _REPO_ROOT)
    _backend_src = os.path.join(_REPO_ROOT, "backend", "src")
    if _backend_src not in _sys.path:
        _sys.path.insert(0, _backend_src)

    from services import projection_schema as schema

    from sam.members.domain.membership_service import MembershipService
    from sam.members.repository.projection_config_reader import MembersProjectionReader

    # Reuse the sibling field-config test's in-memory catalog repo + entry builder so the
    # membership_type REFERENCE options resolve exactly as the real edge composes them (no boto3).
    from sam.tests.test_field_config_endpoint import FakeCatalogRepository, _entry

    with open(_FIXTURE_PATH, encoding="utf-8") as fh:
        overlay = _json.load(fh)
    tenant_id = overlay["tenant_id"]

    table = _BoundaryFakeTable()
    table.put(
        {
            schema.PARTITION_KEY_ATTR: tenant_id,
            schema.SORT_KEY_ATTR: schema.build_sort_key(
                schema.RECORD_TYPE_CONFIG, "fields"
            ),
            "fields": overlay["fields"],
            "overrides": overlay["overrides"],
            "functional_groups": overlay["functional_groups"],
            schema.VERSION_ATTR: 1,
        }
    )
    # The reader (seeded with the REAL overlay row) is the TenantOverlayProvider; the fake catalog
    # repo is the membership-type source. MembershipService.get_field_config composes the resolver
    # + the active catalog into the SAME Flat_View the edge serializes. No boto3 is touched.
    reader = MembersProjectionReader(table=table)
    catalog_repo = FakeCatalogRepository()
    catalog_repo.add_type(tenant_id, _entry(tenant_id, "gewoon", order=10))
    service = MembershipService(catalog_repo, overlay_provider=reader)
    response = service.get_field_config(tenant_id)
    # Round-trip through json exactly as the handler does — a non-serializable value (or a raw
    # key only present pre-serialization) is surfaced the same way the real response would be.
    return _json.loads(_json.dumps(response)), tenant_id


def test_field_config_response_over_real_fixture_carries_no_raw_storage_shape_key():
    """A handler field-config response (over the REAL h-dcn row) exposes NO raw storage shape.

    R11.4 / R3 / steering 39 (reinforcing task 5.3 at the boundary): the raw stored `config#fields`
    overlay shape (`field_overlay` / `overrides` / `fixed_overrides` / dotted `{group}.{key}`
    keys) MUST NOT cross the repository boundary into an API response — serving it was the root
    cause of the partial-overlay-overwrites-full-record drift
    (`.kiro/specs/Members/root-cause-analysis.md`). The frontend reads the resolved Flat_View and
    writes by domain identity (Change-Ops); it never sees or reconstructs a storage key.

    Proven over the ACTUAL committed fixture (the real `overrides` map carries the exact dotted
    keys `personal.gender`, `membership.member_number`, … at rest) — so if the serializer ever
    leaked the stored map, this fails with the leaked path named.
    """
    response, tenant_id = _build_field_config_response_over_real_fixture()

    # Sanity: we built a real, non-trivial Flat_View (so the assertion is not vacuous) and the
    # fixture genuinely contains dotted storage keys that MUST stay inside the repository.
    assert response.get("tenant_id") == tenant_id and response.get("fields"), (
        "expected a populated resolved field-config response over the real fixture"
    )
    with open(_FIXTURE_PATH, encoding="utf-8") as fh:
        raw_overlay = _json.load(fh)
    assert any("." in k for k in raw_overlay["overrides"]), (
        "fixture sanity: the real stored overrides map must carry dotted `{group}.{key}` keys — "
        "those are exactly what must NOT leak into the response"
    )

    leaked = _collect_raw_shape_keys(response)
    assert not leaked, (
        "A field-config handler response MUST NOT carry a raw storage-shape key "
        f"({sorted(_RAW_SHAPE_KEYS)} or a dotted `{{group}}.{{key}}`) — the raw storage shape may "
        "not cross the repository boundary into an API response (steering 39 / R3 / R11.4, "
        "reinforcing task 5.3). Serve the resolved Flat_View and write by domain identity. "
        "Leaked key(s):\n"
        + "\n".join(f"  - at `{path}`: {key!r}" for path, key in sorted(leaked))
    )
