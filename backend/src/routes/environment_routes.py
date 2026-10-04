"""
Environment/health report route (Req 6).

Task 8 (`.kiro/specs/Common/test-environment/first-draft/tasks.md`): expose
``GET /api/environment`` returning the active environment config — the active
``APP_ENV``, Cognito pool labels, MySQL target label, DynamoDB prefix, and SAM API
surface — derived from the Environment_Resolver so it cannot drift (Req 6.5), with all
secret values omitted (Req 6.6).

Design contract (design.md §11 "Health report (Req 6)"): a backend endpoint
(``GET /api/environment``) returns the resolver-derived, non-secret environment report.

**Where the value comes from (non-drift, Req 6.5).** The route prefers the single
:class:`~environment.resolver.ResolvedConfig` the app bootstrap stored on
``app.config["RESOLVED_ENV"]`` (see ``environment/bootstrap.py``), so the report names
exactly the environment every other plane is using. If that config is absent — e.g. a
context where :func:`environment.bootstrap.bootstrap_environment` has not run — the
route derives it directly from ``APP_ENV`` via the central resolver
(``resolve(parse_app_env(os.environ["APP_ENV"]), ENVIRONMENT_DEFINITION)``) rather than
reading any raw per-plane env var, so the value still cannot drift. The report payload
itself is built by the pure :func:`environment.health_report.build_environment_report`,
which omits every secret (Req 6.6).

**Auth.** Like the sibling ``GET /api/status`` health endpoint, this is a public,
unauthenticated endpoint: it leaks only non-secret labels/public identifiers, never a
secret value (Req 6.6).
"""

import logging
import os

from flask import Blueprint, current_app, jsonify
from flask.typing import ResponseReturnValue

from environment.app_env import EnvironmentConfigError, parse_app_env
from environment.bootstrap import RESOLVED_ENV_CONFIG_KEY
from environment.environment_definition import ENVIRONMENT_DEFINITION
from environment.health_report import build_environment_report
from environment.resolver import ResolvedConfig, resolve

logger = logging.getLogger(__name__)

environment_bp = Blueprint("environment", __name__, url_prefix="/api/environment")


def _resolved_config() -> ResolvedConfig:
    """Return the active resolved config, deriving from APP_ENV if not bootstrapped.

    Prefers ``app.config["RESOLVED_ENV"]`` (stored once at startup) so the report names
    the same environment every plane consumes. Falls back to resolving directly from
    ``APP_ENV`` via the central resolver so the value cannot drift (Req 6.5) even when
    the bootstrap hook has not run.

    Raises:
        EnvironmentConfigError: If no resolved config is stored and ``APP_ENV`` is
            unset/unrecognized (fail-fast, no default — Req 1.3).
    """
    resolved = current_app.config.get(RESOLVED_ENV_CONFIG_KEY)
    if isinstance(resolved, ResolvedConfig):
        return resolved
    # No bootstrapped config — derive from APP_ENV via the single resolver so the
    # report still cannot drift (never read raw per-plane env vars here).
    app_env = parse_app_env(os.environ.get("APP_ENV"))
    return resolve(app_env, ENVIRONMENT_DEFINITION)


@environment_bp.route("", methods=["GET"])
@environment_bp.route("/", methods=["GET"])
def get_environment_report() -> ResponseReturnValue:
    """Return the resolver-derived, non-secret environment/health report (Req 6).

    Public endpoint (no authentication) — reports only non-secret labels/identifiers.

    Returns:
        200 with the non-secret environment report (see
        :func:`environment.health_report.build_environment_report`), or 503 with an
        error label if ``APP_ENV`` is unset/unrecognized and no resolved config is
        available (the running unit refused to resolve an environment — Req 1.3).
    """
    try:
        resolved = _resolved_config()
    except EnvironmentConfigError as exc:
        # Log the detail server-side only; do NOT expose the exception text to the
        # (unauthenticated) client — return a stable, non-sensitive error label.
        # (CodeQL: information exposure through an exception.)
        logger.warning(
            "Environment report requested but APP_ENV is unresolved: %s", exc
        )
        return (
            jsonify({"error": "environment_unresolved"}),
            503,
        )

    return jsonify(build_environment_report(resolved))
