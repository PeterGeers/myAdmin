"""WSGI entry point for production deployment."""

from app import app
from environment.bootstrap import bootstrap_environment

# Wire the single authoritative environment selector (APP_ENV) at the real startup
# boundary — NOT at app-module import time, so the test suite can still import `app`
# without APP_ENV set. On this production WSGI path APP_ENV MUST be set: an unset or
# unrecognized value fail-fasts (EnvironmentConfigError) and refuses to start (Req 1.3).
# This parses APP_ENV, resolves the per-plane config into app.config["RESOLVED_ENV"],
# and runs the fail-fast Consistency_Guard (Phase 1, task 9.1): an inconsistent
# environment raises EnvironmentConfigError and the unit refuses to start.
bootstrap_environment(app)

# Expose app at module level for WSGI servers (both names for compatibility)
application = app

if __name__ == "__main__":
    app.run()
