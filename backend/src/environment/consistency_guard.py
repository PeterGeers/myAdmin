"""
Consistency_Guard — verify every plane's resolved wiring matches the active APP_ENV.

S3 / T2 — Implement the cross-plane consistency guard (fail-fast as of Phase 1 /
task 9.1; report-only in Phase 0).

The Consistency_Guard is the verification component described in design.md §5. It
compares every observable plane's resolved wiring against the single active
``APP_ENV`` and reports an inconsistency whenever any surface disagrees — rather than
letting a mismatch surface later as a silent 401 or a cross-environment call.

Design contract (see `.kiro/specs/Common/test-environment/first-draft/design.md` §5):

- Two dataclasses: :class:`PlaneCheck` (one surface's verdict) and
  :class:`ConsistencyReport` (the aggregate, with derived ``is_consistent``).
- Two entry points: a **startup hook** called from app bootstrap, and a **check CLI**
  (``python -m environment.check`` — see ``check.py``).
- Half-cutover detection (Req 4.7, 7.5): collect each plane's resolved env label and
  fail if the set has more than one member.

Error-handling style mirrors ``auth/pool_registry.py`` (fail-fast, no silent
fallback). Messages name the mismatched surface AND both sides of a mismatch.

**Modes.** :func:`run_consistency_guard` with ``strict=False`` (report-only) LOGS
inconsistencies via the standard logger but does NOT raise or block.
:func:`consistency_guard_startup_hook` now uses ``strict=True`` (Phase 1 / task 9.1):
an inconsistency raises :class:`EnvironmentConfigError` and the Flask unit refuses to
start. Report-only mode (``strict=False``) remains available for the ``check`` CLI
and diagnostics.

**Security (Req 6.6).** The guard never prints secret VALUES. The client-secret check
asserts emptiness without echoing any secret; only non-secret labels/identifiers
(pool ids, pool labels, URLs) appear in messages.

**Extension points.** Only the checks whose inputs exist in Phase 0 are implemented
here (Cognito identity, pool-registry membership, identity block, client-secret,
half-cutover) plus the MySQL target-isolation check (task 12.4) and the Flask API
base URL check (task 13.1). The SAM API base URL, SAM authorizer pool and DynamoDB
prefix checks are added by later tasks — clearly-marked TODOs below reference those
task numbers so they slot in cleanly.
"""

import logging
import os
from collections.abc import Mapping

from ._consistency_checks import (
    _check_client_secret,
    _check_cognito_pool_registered,
    _check_dynamodb_prefix,
    _check_flask_api_base_url,
    _check_frontend_pool_vs_registry,
    _check_identity_block,
    _check_mysql_target,
    _check_sam_api_base_url,
    _check_sam_authorizer_pool,
)

# Re-export the report value types and the per-plane checks from their extracted
# home modules so the public import surface of ``consistency_guard`` is byte-stable
# (code-quality L2 split). Callers and tests that do
# ``from environment.consistency_guard import PlaneCheck`` /
# ``import _check_mysql_target`` keep working unchanged, and
# ``patch("environment.consistency_guard._load_registered_issuers")`` still resolves
# because that name is defined below in this module.
from ._consistency_report import ConsistencyReport, PlaneCheck
from .app_env import AppEnv, EnvironmentConfigError
from .environment_definition import ENVIRONMENT_DEFINITION, EnvironmentDefinition
from .resolver import resolve

__all__ = [
    "ConsistencyReport",
    "PlaneCheck",
    "build_consistency_report",
    "consistency_guard_startup_hook",
    "run_consistency_guard",
]

logger = logging.getLogger(__name__)


def build_consistency_report(
    app_env: AppEnv,
    *,
    definition: EnvironmentDefinition = ENVIRONMENT_DEFINITION,
    environ: Mapping[str, str] | None = None,
    registered_issuers: list[str] | None = None,
) -> ConsistencyReport:
    """Build a :class:`ConsistencyReport` for the active APP_ENV.

    This is the pure-logic core of the guard: it resolves the configuration for
    ``app_env`` and runs each Phase-0 plane check, returning the aggregate report.
    It performs NO I/O beyond reading the injected ``environ`` mapping — it does not
    touch AWS, the database, or raise on inconsistency (the startup hook / CLI decide
    what to do with the verdict).

    Args:
        app_env: The active environment selector.
        definition: The Environment_Definition source of truth (injectable for tests;
            defaults to the committed :data:`ENVIRONMENT_DEFINITION`).
        environ: Environment mapping for the identity-block and client-secret checks
            (defaults to :data:`os.environ`). Injectable for tests.
        registered_issuers: The Pool_Registry's registered issuers. When ``None``,
            the registry is loaded from the environment via
            :func:`auth.pool_registry.load_pool_registry`; a registry-load failure is
            captured as a failing ``pool_registry`` check rather than propagated, so
            the guard can still report the other planes in report-only mode.

    Returns:
        A :class:`ConsistencyReport` with one :class:`PlaneCheck` per surface.
    """
    env = os.environ if environ is None else environ
    resolved = resolve(app_env, definition)

    checks: list[PlaneCheck] = []

    # Cognito identity resolves from APP_ENV by construction (resolver guarantees it);
    # record it so the report explicitly states the resolved pool for this env.
    checks.append(
        PlaneCheck(
            plane="cognito_identity",
            resolved_env=resolved.app_env,
            ok=True,
            message=(
                f"resolved Cognito pool '{resolved.cognito.pool_id}' "
                f"({resolved.cognito.pool_label}) for APP_ENV="
                f"{resolved.app_env.value}"
            ),
        )
    )

    # Pool-registry membership (Req 4.1, 4.2).
    if registered_issuers is None:
        registered_issuers = _load_registered_issuers()
        if registered_issuers is None:
            checks.append(
                PlaneCheck(
                    plane="pool_registry",
                    resolved_env=None,
                    ok=False,
                    message=(
                        "could not load the Pool_Registry (COGNITO_POOL_KEYS "
                        "unconfigured or incomplete); cannot verify that the "
                        f"resolved pool '{resolved.cognito.pool_id}' is registered"
                    ),
                )
            )
            registered_issuers = []
        else:
            checks.append(_check_cognito_pool_registered(resolved, registered_issuers))
    else:
        checks.append(_check_cognito_pool_registered(resolved, registered_issuers))

    # Frontend-selected pool vs backend registry (Req 4.2). Framed from the
    # frontend-selected side: the pool the frontend build for this APP_ENV selects
    # (the same resolved pool id, since both read the committed definition) must be
    # registered among the backend's issuers. `registered_issuers` is now resolved
    # (either injected, loaded, or [] when the registry could not be loaded).
    checks.append(_check_frontend_pool_vs_registry(resolved, registered_issuers))

    # Identity block (Req 4.3, 7.2).
    checks.append(_check_identity_block(resolved, env))

    # Test pool => empty client secret (Req 7.3, 8.4).
    checks.append(_check_client_secret(resolved, env))

    # MySQL plane: resolved TEST target must differ from PRODUCTION target in
    # identity + credentials (task 12.4; Req 9.3, 9.5, 9.6). Contributes
    # resolved_env so it joins the half-cutover set below.
    checks.append(_check_mysql_target(resolved, definition))

    # Flask API base URL the frontend calls matches APP_ENV (task 13.1; Req 21.5,
    # 21.6). The active resolved Flask URL must equal the definition's URL for the
    # active env, and the TEST/PROD URLs must differ. Contributes resolved_env so
    # it joins the half-cutover set below.
    checks.append(_check_flask_api_base_url(resolved, definition))

    # SAM plane (task 24). The SAM compute/data plane is resolved from APP_ENV just
    # like the other planes, so the guard verifies the running backend's resolved
    # view of the SAM edge agrees with APP_ENV:
    #   * authorizer pool (Req 14.4, 14.5) — the API Gateway Cognito authorizer pool;
    #   * API base URL (Req 4.4, 14.4) — the invoke URL clients call (placeholder-
    #     tolerant until the stack is first deployed);
    #   * DynamoDB table prefix (Req 10.2, 19.4) — the `test_`/`""` data-plane boundary.
    # Each contributes resolved_env so it participates in the half-cutover set below.
    checks.append(_check_sam_authorizer_pool(resolved, definition))
    checks.append(_check_sam_api_base_url(resolved, definition))
    checks.append(_check_dynamodb_prefix(resolved, definition))

    return ConsistencyReport(active_app_env=app_env, checks=checks)


def _load_registered_issuers() -> list[str] | None:
    """Load the Pool_Registry's registered issuers, or ``None`` on failure.

    Isolated so the guard degrades gracefully in report-only mode: a
    misconfigured/absent registry becomes a reportable finding, not a crash. The
    import is local to avoid a hard import-time dependency on the auth package for
    callers that inject ``registered_issuers`` directly (e.g. unit tests).
    """
    try:
        from auth.pool_registry import PoolRegistryError, load_pool_registry
    except ImportError:  # pragma: no cover - defensive, auth pkg should be importable
        return None
    try:
        registry = load_pool_registry()
    except PoolRegistryError:
        return None
    return registry.issuers()


def run_consistency_guard(
    app_env: AppEnv,
    *,
    strict: bool = False,
    definition: EnvironmentDefinition = ENVIRONMENT_DEFINITION,
    environ: Mapping[str, str] | None = None,
    registered_issuers: list[str] | None = None,
) -> ConsistencyReport:
    """Run the guard and act on the verdict according to ``strict``.

    This is the single behavioural entry point shared by the startup hook and the
    ``check`` CLI. The ``strict`` flag is the one-line Phase-0→Phase-1 switch:

    - ``strict=False`` (Phase 0, report-only): on an inconsistency it LOGS the full
      report at ``WARNING`` and the failing checks, but returns normally and does
      NOT raise. The app still starts (no behaviour change).
    - ``strict=True`` (Phase 1 / task 9.1): on an inconsistency it raises
      :class:`EnvironmentConfigError` naming the mismatched surface(s) and both
      sides, so the running unit refuses to start.

    Args:
        app_env: The active environment selector.
        strict: Whether to raise on inconsistency (``True``) or only log (``False``).
        definition: Environment_Definition source of truth (injectable for tests).
        environ: Environment mapping (defaults to :data:`os.environ`).
        registered_issuers: Injectable Pool_Registry issuers (loaded if ``None``).

    Returns:
        The :class:`ConsistencyReport`.

    Raises:
        EnvironmentConfigError: Only when ``strict=True`` and the report is
            inconsistent.
    """
    report = build_consistency_report(
        app_env,
        definition=definition,
        environ=environ,
        registered_issuers=registered_issuers,
    )

    if report.is_consistent:
        logger.info(
            "Environment consistency guard: all planes agree (APP_ENV=%s)",
            app_env.value,
        )
        return report

    # Inconsistent.
    failing = report.failing_checks()
    failing_summary = (
        "; ".join(f"{check.plane}: {check.message}" for check in failing)
        or "half-cutover: planes resolve to more than one environment"
    )

    if strict:
        raise EnvironmentConfigError(
            f"Environment consistency check failed for APP_ENV="
            f"{app_env.value}. {failing_summary}"
        )

    # Report-only: log loudly but do not block.
    logger.warning(
        "Environment consistency guard found inconsistencies (report-only; "
        "APP_ENV=%s):\n%s",
        app_env.value,
        report.format_report(),
    )
    return report


def consistency_guard_startup_hook(
    app_env: AppEnv,
    *,
    environ: Mapping[str, str] | None = None,
) -> ConsistencyReport:
    """App-bootstrap hook — runs the guard in FAIL-FAST mode (Phase 1, task 9.1).

    Call this from the Flask app bootstrap after the active ``APP_ENV`` is parsed.
    On an inconsistency it raises :class:`EnvironmentConfigError` naming the
    mismatched surface(s) and both sides, so the running unit refuses to start
    rather than letting the drift surface later as a silent 401 or a
    cross-environment call. A CONSISTENT environment returns normally.

    This is the Phase-0→Phase-1 flip (task 9.1): the hook now passes
    ``strict=True`` to :func:`run_consistency_guard`. It only runs on the real
    startup paths (``wsgi.py`` / ``app.py`` ``__main__``), never at import time, so
    importing the app for tests still never triggers the parse or the guard (see
    ``bootstrap.py`` module docstring).

    Args:
        app_env: The active environment selector (already parsed from ``APP_ENV``).
        environ: Environment mapping (defaults to :data:`os.environ`).

    Returns:
        The :class:`ConsistencyReport` (also logged) when the environment is
        consistent.

    Raises:
        EnvironmentConfigError: When the report is inconsistent — the unit refuses
            to start.
    """
    return run_consistency_guard(app_env, strict=True, environ=environ)
