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

On top of those two ORIGINAL (blocking) spec-03 checks, this guard carries THREE
ANTI-REINTRODUCTION rules from spec ``03a - enum-vocab-roundtrip-and-no-silent-fallbacks``
(design C8; requirement R2.7). They prevent the retired two-names (``choices`` vs ``options``)
vocabulary paths and the scope ``values``-vs-``options`` divergence from creeping back:

  (a) A ``choices`` VOCABULARY KEY ON THE config#fields WRITE PATH — ``"choices"`` appearing as
      an element of a definition-attribute set/frozenset (the ``FIELD_DEFINITION_ATTRS`` shape)
      or as a dict-literal KEY in a write payload, in a write-surface module
      (``config_fields_crud_service.py`` / ``config_write_service.py``). ``choices`` was retired
      (03a C2) — the write surface accepts only the one canonical ``options`` vocabulary. (The
      one-time ``remove_legacy_choices`` migration op naming ``"choices"`` as a REMOVE PATH
      SEGMENT — a list element — or in a ``"choices" not in stored`` membership check is NOT a
      set element / dict key, so it does not trip this rule.)

  (b) AN ``options or choices`` / ``choices or options`` FALLBACK EXPRESSION in a reader /
      resolver / serializer, OR a read of the stored ``choices`` key as a FALLBACK VOCABULARY
      SOURCE (``spec.get("choices")`` / ``…get("choices")``) in the write-side subset validator.
      This covers the retired ``_serialize_field`` fallback (F9), the ``_public_field_options``
      fallback (F10), and the write-side ``_field_choice_values`` coalesce (F12 — migrated to
      ``options``-only, not allow-listed). NOTE: a ``field.choices`` read that FAILS LOUD (feeds
      an ``UnpropagatedVocabularyError`` raise, the C6 asymmetry boundary) or a legitimate
      bare-value helper is NOT a ``X or Y`` coalesce and is NOT flagged — only the coalesce
      shape and the write-side ``get("choices")`` source read are.

  (d) ``FieldScope.values`` POPULATED INDEPENDENTLY OF ``options`` — a ``FieldScope(values=…)``
      construction (or an assignment to a ``.values`` attribute of a scope object), rather than
      ``values`` being the DERIVED read-only projection ``[o.value for o in options]`` (F7/G2).
      Re-splitting the scope vocabulary into two stored copies is exactly the
      ``FieldScope(values=())`` divergence (bug manifestation #2) the fix removed by construction.

  (Rule (c) — a per-field-KIND AST branch check — was DROPPED by the 03a design: it needed two
  carve-outs → false-positive risk; its invariant is covered by a behavioral test (task 9b),
  not a blocking AST rule.)

**ROLLOUT — rules (a)(b)(d) are REPORT-ONLY in this increment (03a task 10).** They EMIT
findings (visible in the output) but do NOT change the exit code: the flip to BLOCKING is a
separate increment (03a task 12), performed only AFTER the fix (C7 + C1–C6) has landed and the
tree is clean (design G6 — never redden a valid in-flight state on day one). The two ORIGINAL
spec-03 checks (a=raw governance write, b=raw-shape response key) REMAIN BLOCKING.

Detection is AST-based (``ast``), so a comment or docstring that merely MENTIONS
``put_item`` / ``field_overlay`` / ``choices`` does not trip the guard — only real code does.
This mirrors ``sam/tests/test_handler_repository_boundary.py``.

Allow-list discipline (steering 39): a NEW sanctioned site is added to ``ALLOWED_*`` in a
REVIEWED change — NEVER by suppressing the guard (``--no-verify`` is not the path).

Usage::

    python scripts/check_sam_config_crud.py            # full scan of SCAN_DIRS (CI)
    python scripts/check_sam_config_crud.py [path ...]  # check only the given files (hook)

Exit code 0 = clean (blocking checks), 1 = blocking violations found. REPORT-ONLY findings
(the 03a rules a/b/d) are printed but never by themselves cause a non-zero exit this increment.
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
    # 03a anti-reintroduction rules (a)(b)(d) — report-only this increment.
    "VOCAB_KEY",
    "WRITE_PATH_FILES",
    "VOCAB_CONSUMER_DIRS",
    "check_file",
    "check_file_report_only",
    "scan_directory",
    "scan_directory_report_only",
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

# ──────────────────────────────────────────────────────────────────────────────────
# 03a — anti-reintroduction rules (a)(b)(d). REPORT-ONLY this increment (design C8, R2.7):
# these emit findings but do NOT change the exit code. The flip to BLOCKING is 03a task 12.
# ──────────────────────────────────────────────────────────────────────────────────

#: The retired legacy vocabulary attribute name. ``choices`` was the bare value list; the one
#: canonical vocabulary is now ``options`` (rich ``[{value, label?, roles?}]``). Every 03a rule
#: keys off this single token so the three rules stay in lockstep on what "the old name" is.
VOCAB_KEY = "choices"

#: Rule (a) scope — the config#fields WRITE-SURFACE modules. A ``choices`` vocabulary KEY (a
#: definition-attr set element or a write-payload dict key) in one of these is the reintroduction
#: of ``choices`` onto the write path (03a C2, retired). Repo-root-relative POSIX suffixes.
#: NOTE: ``config_fields_crud_service.py`` legitimately contains ``remove_legacy_choices`` (the
#: one-time migration op) which names ``"choices"`` only as a REMOVE PATH SEGMENT (a list element)
#: and in a ``"choices" not in stored`` membership Compare — neither is a Set element or a Dict
#: key, so rule (a) does not flag the sanctioned migration op.
WRITE_PATH_FILES = frozenset(
    {
        "sam/members/domain/config_fields_crud_service.py",
        "sam/members/domain/config_write_service.py",
    }
)

#: Rule (b) scope — the vocabulary CONSUMER layer (readers, resolvers, serializers, and the
#: write-side subset validator) where an ``options or choices`` / ``choices or options`` coalesce
#: or a ``get("choices")`` fallback-source read would reintroduce the two-names fallback
#: (F9/F10/F12). Anchored on the Members domain + repository packages. A ``field.choices`` read
#: that is NOT a coalesce (e.g. the C6 fail-loud ``if field.choices: raise …``, or a bare-value
#: helper) is left alone — rule (b) detects only the two retired SHAPES.
VOCAB_CONSUMER_DIRS = (
    "sam/members/domain/",
    "sam/members/repository/",
)


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


# ──────────────────────────────────────────────────────────────────────────────────
# 03a rule (a) — a ``choices`` vocabulary key on the config#fields WRITE path.
# ──────────────────────────────────────────────────────────────────────────────────


def _is_in_write_path_file(rel: str) -> bool:
    """True if ``rel`` is one of the config#fields WRITE-SURFACE modules rule (a) scans."""
    return _matches_rel(rel, WRITE_PATH_FILES)


def _set_literal_string_elements(tree: ast.AST):
    """Yield (string element, lineno) for every ``{...}`` set / ``frozenset({...})`` element.

    Covers the ``FIELD_DEFINITION_ATTRS = frozenset({...})`` write-definition-attr shape: a
    ``choices`` token re-added as a definition attr is a set element of such a literal. A list or
    tuple is deliberately NOT inspected here — a ``["<map>", "<key>", "choices"]`` REMOVE PATH
    (the sanctioned ``remove_legacy_choices`` op) is a list, so it never trips rule (a).
    """
    for node in ast.walk(tree):
        # Bare set display: {"a", "b"}
        if isinstance(node, ast.Set):
            for elt in node.elts:
                if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                    yield elt.value, elt.lineno
        # frozenset({...}) / set({...}) — the set display rides as the call arg (handled above
        # when ast.walk reaches the inner ast.Set), so no extra handling is needed here.


def _check_write_path_choices(tree: ast.AST, rel: str) -> list[str]:
    """Rule (a): a ``choices`` vocabulary key on the config#fields WRITE path (03a C2).

    Flags ``"choices"`` as (1) an element of a definition-attr SET/frozenset literal (the
    ``FIELD_DEFINITION_ATTRS`` shape) or (2) a dict-literal KEY in a write payload, in a
    write-surface module. A path-segment list element or a membership ``Compare`` is NOT flagged
    (so the sanctioned ``remove_legacy_choices`` migration op is clean).
    """
    if not _is_in_write_path_file(rel):
        return []
    violations: list[str] = []
    seen: set = set()  # (lineno) dedupe so a key present in both a set and a dict is one finding
    for value, lineno in _set_literal_string_elements(tree):
        if value == VOCAB_KEY and lineno not in seen:
            seen.add(lineno)
            violations.append(
                f"{rel}:{lineno}: retired vocabulary key {VOCAB_KEY!r} re-added as a "
                f"definition attribute on the config#fields WRITE path — the write surface "
                f"accepts ONLY the one canonical 'options' vocabulary ('choices' was retired, "
                f"03a C2 / R2.1). [03a rule (a)]"
            )
    for value, lineno in _dict_key_strings(tree):
        if value == VOCAB_KEY and lineno not in seen:
            seen.add(lineno)
            violations.append(
                f"{rel}:{lineno}: retired vocabulary key {VOCAB_KEY!r} as a dict key in a "
                f"config#fields WRITE payload — the write surface persists ONLY 'options' "
                f"('choices' was retired, 03a C2 / R2.1). [03a rule (a)]"
            )
    return violations


# ──────────────────────────────────────────────────────────────────────────────────
# 03a rule (b) — an ``options or choices`` / ``choices or options`` fallback coalesce, or a
# ``get("choices")`` fallback-source read, in the vocabulary consumer layer.
# ──────────────────────────────────────────────────────────────────────────────────


def _is_vocab_consumer_file(rel: str) -> bool:
    """True if ``rel`` is in the reader/resolver/serializer/validator layer rule (b) scans."""
    return any(seg in rel for seg in VOCAB_CONSUMER_DIRS)


def _names_vocab_attr(node: ast.AST, attr: str) -> bool:
    """True if ``node`` reads a ``…choices`` / ``…options`` vocabulary.

    Matches two shapes that denote a vocabulary of name ``attr`` (``choices`` or ``options``):
      * attribute access ``X.<attr>`` (e.g. ``field.choices``, ``field.options``), or
      * a ``.get("<attr>")`` call (e.g. ``spec.get("choices")``, ``spec.get("options")``).
    A bare ``Name`` (local variable ``choices``) is deliberately NOT matched — the retired shapes
    are always a vocabulary READ off a field/spec object, and matching bare names would flag a
    legitimately-named local.
    """
    if isinstance(node, ast.Attribute) and node.attr == attr:
        return True
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "get"
        and len(node.args) >= 1
        and isinstance(node.args[0], ast.Constant)
        and node.args[0].value == attr
    ):
        return True
    return False


def _check_vocab_fallback(tree: ast.AST, rel: str) -> list[str]:
    """Rule (b): the retired ``options``/``choices`` fallback shapes (F9/F10/F12).

    Two detections, both in the consumer layer only:
      (b1) a ``BoolOp(Or)`` whose operands read BOTH an ``options`` vocabulary AND a ``choices``
           vocabulary — the ``options or choices`` / ``choices or options`` coalesce; and
      (b2) a ``…get("choices")`` read as a vocabulary SOURCE — the F12 write-side
           ``spec.get("choices")`` coalesce shape (migrated to ``options``-only).
    A ``field.choices`` attribute read that is NOT part of an ``or`` coalesce (e.g. the C6
    ``if field.choices: raise UnpropagatedVocabularyError(...)`` fail-loud) is NOT flagged — only
    the coalesce and the ``get("choices")`` source read are.
    """
    if not _is_vocab_consumer_file(rel):
        return []
    violations: list[str] = []
    seen: set = set()
    for node in ast.walk(tree):
        # (b1) options-or-choices / choices-or-options coalesce.
        if isinstance(node, ast.BoolOp) and isinstance(node.op, ast.Or):
            has_choices = any(_names_vocab_attr(v, VOCAB_KEY) for v in node.values)
            has_options = any(_names_vocab_attr(v, "options") for v in node.values)
            if has_choices and has_options and node.lineno not in seen:
                seen.add(node.lineno)
                violations.append(
                    f"{rel}:{node.lineno}: retired 'options or choices' / 'choices or options' "
                    f"vocabulary fallback coalesce — read the ONE canonical 'options' the "
                    f"read-assembly seam populates; the legacy 'choices' coalesce is retired "
                    f"(03a F1/F9/F10/F12 / R2.3). [03a rule (b)]"
                )
        # (b2) get("choices") read as a vocabulary SOURCE (the F12 write-side coalesce shape).
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "get"
            and len(node.args) >= 1
            and isinstance(node.args[0], ast.Constant)
            and node.args[0].value == VOCAB_KEY
            and node.lineno not in seen
        ):
            seen.add(node.lineno)
            violations.append(
                f"{rel}:{node.lineno}: read of the retired stored {VOCAB_KEY!r} key as a "
                f"vocabulary source — the subset validator / serializer must read the ONE "
                f"canonical 'options' (F12 migrated to 'options'-only, 03a R2.1). [03a rule (b)]"
            )
    return violations


# ──────────────────────────────────────────────────────────────────────────────────
# 03a rule (d) — ``FieldScope.values`` populated independently of ``options``.
# ──────────────────────────────────────────────────────────────────────────────────


def _check_scope_values_independence(tree: ast.AST, rel: str) -> list[str]:
    """Rule (d): ``FieldScope.values`` populated independently of ``options`` (F7/G2).

    ``FieldScope.values`` must be the DERIVED read-only projection ``[o.value for o in options]``
    — never a stored second copy. Two reintroduction shapes are flagged (consumer layer only):
      * a ``FieldScope(values=…)`` construction (passing ``values`` as its own stored value), and
      * an assignment to a ``.values`` attribute of a scope object (``field.scope.values = …`` /
        ``scope.values = …``), re-splitting the vocabulary into two copies.
    Both are exactly the ``FieldScope(values=())`` divergence the fix removed by construction. The
    read-only ``@property values`` on ``FieldScope`` (its single derivation point) is a function
    def, not a call keyword or an assignment target, so it is NOT flagged.
    """
    if not _is_vocab_consumer_file(rel):
        return []
    violations: list[str] = []
    for node in ast.walk(tree):
        # FieldScope(values=...) — an independent stored vocabulary copy on construction.
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "FieldScope"
        ):
            for kw in node.keywords:
                if kw.arg == "values":
                    violations.append(
                        f"{rel}:{node.lineno}: FieldScope(values=…) populates scope 'values' "
                        f"INDEPENDENTLY of 'options' — 'values' must be the DERIVED projection "
                        f"[o.value for o in options], never a stored second copy (the "
                        f"FieldScope(values=()) divergence, 03a F7/G2 / R2.6). [03a rule (d)]"
                    )
        # <scope>.values = ... — assigning the vocabulary as a stored sibling of options.
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Attribute) and target.attr == "values":
                    violations.append(
                        f"{rel}:{node.lineno}: assignment to scope '.values' populates it "
                        f"INDEPENDENTLY of 'options' — 'values' must be the DERIVED projection "
                        f"[o.value for o in options], never a stored second copy "
                        f"(03a F7/G2 / R2.6). [03a rule (d)]"
                    )
    return violations


def _report_only_findings(tree: ast.AST, rel: str) -> list[str]:
    """Aggregate the 03a REPORT-ONLY rules (a)(b)(d) for one parsed file.

    Kept SEPARATE from :func:`check_file` so the two ORIGINAL spec-03 checks stay blocking while
    these three stay report-only this increment (03a task 10; the flip to blocking is task 12).
    """
    findings: list[str] = []
    findings.extend(_check_write_path_choices(tree, rel))       # (a)
    findings.extend(_check_vocab_fallback(tree, rel))           # (b)
    findings.extend(_check_scope_values_independence(tree, rel))  # (d)
    return findings


def check_file(filepath: Path) -> list[str]:
    """Return the BLOCKING violation messages for a single ``.py`` file (the two spec-03 checks).

    A file that cannot be parsed (syntax error, permission, encoding) yields no violations —
    the guard is a lint, not a compiler, and a genuinely broken file surfaces elsewhere.

    This returns ONLY the blocking spec-03 findings (raw governance write / raw-shape response
    key). The 03a report-only rules (a)(b)(d) are returned by :func:`check_file_report_only`.
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


def check_file_report_only(filepath: Path) -> list[str]:
    """Return the 03a REPORT-ONLY findings (rules a/b/d) for a single ``.py`` file.

    Separate from :func:`check_file` so the three 03a rules emit findings without affecting the
    exit code this increment (design C8 rollout; the flip to blocking is 03a task 12). A file
    that cannot be parsed yields no findings (same lint-not-compiler contract as check_file).
    """
    rel = _rel_posix(filepath)
    try:
        source = filepath.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=rel)
    except (SyntaxError, PermissionError, UnicodeDecodeError, OSError):
        return []
    return _report_only_findings(tree, rel)


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
    """Scan every ``.py`` file under ``root`` and return all BLOCKING violation messages."""
    all_violations: list[str] = []
    for py_file in _iter_py_files(root):
        all_violations.extend(check_file(py_file))
    return all_violations


def scan_directory_report_only(root: Path) -> list[str]:
    """Scan every ``.py`` file under ``root`` and return all 03a REPORT-ONLY findings (a/b/d)."""
    all_findings: list[str] = []
    for py_file in _iter_py_files(root):
        all_findings.extend(check_file_report_only(py_file))
    return all_findings


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
    report_only: list[str] = []

    if paths:
        for arg in paths:
            py_file = Path(arg)
            if not py_file.is_file() or py_file.suffix != ".py":
                continue
            all_violations.extend(check_file(py_file))
            report_only.extend(check_file_report_only(py_file))
    else:
        root = Path(".")
        for scan_dir in SCAN_DIRS:
            dir_path = root / scan_dir
            if not dir_path.is_dir():
                continue
            all_violations.extend(scan_directory(dir_path))
            report_only.extend(scan_directory_report_only(dir_path))

    # 03a rules (a)(b)(d) are REPORT-ONLY this increment (design C8 rollout; the flip to
    # BLOCKING is 03a task 12). Print any findings for visibility, but DO NOT let them change
    # the exit code — only the two original spec-03 checks are blocking today.
    if report_only:
        print(
            f"[REPORT-ONLY] {len(report_only)} anti-reintroduction finding(s) "
            f"(03a rules a/b/d — not yet blocking):\n"
        )
        for f in report_only:
            print(f"  [REPORT-ONLY] {f}")
        print(
            "\nThese findings do NOT fail the build in this increment. They flip to BLOCKING "
            "in 03a task 12, once the fix (C7 + C1-C6) has landed and the tree is clean (G6). "
            "Fix the call site — do NOT suppress the guard; a new sanctioned site is a reviewed "
            "allow-list addition (steering 39).\n"
        )

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

    if report_only:
        print(
            "[OK] No BLOCKING violations (raw governance-table write / raw storage-shape "
            "response key). See the [REPORT-ONLY] 03a findings above — not yet blocking."
        )
    else:
        print(
            "[OK] No raw governance-table writes outside the Change-Op write repository, no "
            "raw storage-shape key in an API response, and no 03a anti-reintroduction findings "
            "(rules a/b/d clean)."
        )
    sys.exit(0)


if __name__ == "__main__":
    main()
