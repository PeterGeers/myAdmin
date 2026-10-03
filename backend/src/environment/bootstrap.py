"""
App-bootstrap wiring for the single authoritative environment selector (`APP_ENV`).

S3 / T3.1 + T3.5 — Wire `APP_ENV` into the Flask backend bootstrap: read the active
selector, resolve the per-plane configuration, store it where the app can reach it,
and run the Consistency_Guard (fail-fast as of Phase 1 / task 9.1) alongside the
existing startup checks.

Design contract (see `.kiro/specs/Common/test-environment/first-draft/design.md` and
Requirements 1.3-1.6, 2.1, 2.3):

- `APP_ENV` is read ONCE at startup via :func:`environment.app_env.parse_app_env`,
  which fail-fasts (raises :class:`EnvironmentConfigError`) when the value is unset or
  unrecognized — an unset `APP_ENV` must refuse to start (Req 1.3), with no silent
  default.
- The resolved :class:`~environment.resolver.ResolvedConfig` is stored on
  ``app.config["RESOLVED_ENV"]`` so every plane can consume the single resolved
  configuration (Req 2.1, 2.3) rather than re-deriving the environment.
- The Consistency_Guard startup hook runs in FAIL-FAST mode (Phase 1, task 9.1): on
  an inconsistency it raises :class:`EnvironmentConfigError` so the unit refuses to
  start; a consistent environment starts normally.

**Why a separate bootstrap function instead of module-import-time parsing.** The Flask
``app`` object in ``app.py`` is created at module import, and the unit-test suite
imports ``app``/blueprints without setting ``APP_ENV`` (see
``backend/tests/*/conftest.py``, which seed ``DB_*``/``COGNITO_*`` but not
``APP_ENV``). Parsing ``APP_ENV`` at import time would make the fail-fast fire during
test collection and break every import of the app module. So the parse lives in this
explicitly-invoked function, called only on the REAL startup paths (``wsgi.py`` for the
production WSGI server and the ``if __name__ == "__main__"`` dev-server block in
``app.py``). Importing ``app`` for tests therefore never triggers the parse; running
the server does. This mirrors a ``create_app()`` factory call path using the existing
module-level ``app`` object.

Security (Req 6.6 / design): the parse and guard log only non-secret labels/identifiers
(the resolved environment name, pool ids/labels, URLs) — never secret values.
"""

import logging
import os
from collections.abc import Mapping
from typing import Optional

from .app_env import AppEnv, parse_app_env
from .consistency_guard import consistency_guard_startup_hook
from .environment_definition import ENVIRONMENT_DEFINITION
from .resolver import ResolvedConfig, resolve

logger = logging.getLogger(__name__)

#: The ``app.config`` key under which the resolved per-plane configuration is stored.
RESOLVED_ENV_CONFIG_KEY = "RESOLVED_ENV"

#: The ``app.config`` key under which the active :class:`AppEnv` is stored.
APP_ENV_CONFIG_KEY = "APP_ENV"


def bootstrap_environment(
    app,
    *,
    environ: Optional[Mapping[str, str]] = None,
    run_guard: bool = True,
) -> ResolvedConfig:
    """Read ``APP_ENV``, resolve per-plane config, and run the fail-fast guard.

    Call this once from the real startup path (NOT at module import — see module
    docstring). It performs the three Phase-0 wiring steps:

    1. Parse ``APP_ENV`` via :func:`parse_app_env` (fail-fast on unset/unknown —
       Req 1.3). An unset/unrecognized value raises
       :class:`~environment.app_env.EnvironmentConfigError`, so the unit refuses to
       start rather than silently defaulting.
    2. Resolve the single per-plane :class:`ResolvedConfig` from the active env via
       the central :func:`resolve` (Req 2.1), and store both the resolved config and
       the active :class:`AppEnv` on ``app.config`` so every plane can read the one
       resolved configuration (Req 2.3).
    3. Run the Consistency_Guard startup hook in FAIL-FAST mode (Phase 1, task 9.1):
       on an inconsistency it raises :class:`EnvironmentConfigError` so the unit
       refuses to start; a consistent environment starts normally.

    Args:
        app: The Flask application (anything exposing a dict-like ``.config``).
        environ: Environment mapping to read ``APP_ENV`` (and, via the guard, the
            identity block) from. Defaults to :data:`os.environ`. Injectable for
            tests.
        run_guard: Whether to run the Consistency_Guard. Defaults to ``True``; tests
            that only assert resolution wiring may pass ``False``.

    Returns:
        The resolved :class:`ResolvedConfig` (also stored on ``app.config``).

    Raises:
        EnvironmentConfigError: If ``APP_ENV`` is unset or not a recognized value
            (fail-fast, no default — Req 1.3), or if ``run_guard`` is ``True`` and
            the Consistency_Guard finds the active environment inconsistent (task
            9.1 fail-fast).
    """
    env = os.environ if environ is None else environ

    # Step 1 — fail-fast parse (Req 1.3). parse_app_env raises EnvironmentConfigError
    # on unset/unknown, which propagates and refuses to start the unit.
    app_env: AppEnv = parse_app_env(env.get("APP_ENV"))

    # Step 2 — resolve once and store for all planes to consume (Req 2.1, 2.3).
    resolved = resolve(app_env, ENVIRONMENT_DEFINITION)
    app.config[APP_ENV_CONFIG_KEY] = app_env
    app.config[RESOLVED_ENV_CONFIG_KEY] = resolved

    logger.info(
        "Environment bootstrap: APP_ENV=%s resolved (cognito pool '%s' [%s], "
        "mysql target '%s', dynamodb prefix '%s')",
        app_env.value,
        resolved.cognito.pool_id,
        resolved.cognito.pool_label,
        resolved.mysql.target_label,
        resolved.dynamodb_prefix or "<none>",
    )

    # Step 3 — fail-fast Consistency_Guard (Phase 1, task 9.1): raises
    # EnvironmentConfigError on an inconsistency so the unit refuses to start.
    if run_guard:
        consistency_guard_startup_hook(app_env, environ=env)

    return resolved
