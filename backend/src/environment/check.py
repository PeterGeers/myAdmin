"""
`check` CLI — print the per-plane Consistency_Guard report.

S3 / T2.4 — Runnable as ``python -m environment.check``.

This command reads the active ``APP_ENV``, runs the Consistency_Guard, and prints a
per-plane :class:`~environment.consistency_guard.ConsistencyReport`.

**Exit codes (Req 4.5, 4.6 — task 9.3).** The command exits NON-ZERO on any
inconsistency and ``0`` when every plane agrees:

- ``0`` — the report is consistent (every plane agrees with the active APP_ENV).
- ``1`` — the report is inconsistent (at least one plane disagrees, or a
  half-cutover was detected). The per-plane report is still printed so the failing
  surface is visible.
- ``2`` — ``APP_ENV`` is unset/unrecognized (a hard configuration error that
  predates this spec's guard semantics — an unparseable APP_ENV cannot even be
  compared).

Secrets (Req 6.6): the printed report contains only non-secret labels/identifiers;
the underlying guard never includes secret values.

Usage::

    APP_ENV=test python -m environment.check
"""

import os
import sys

from .app_env import EnvironmentConfigError, parse_app_env
from .consistency_guard import build_consistency_report


def main(argv: list[str] | None = None) -> int:
    """Entry point for ``python -m environment.check``.

    Reads ``APP_ENV`` from the environment, builds the consistency report, prints
    it, and returns an exit code.

    Returns ``0`` when the report is consistent, ``1`` when it is inconsistent
    (Req 4.5, 4.6), and ``2`` when ``APP_ENV`` itself is unset/unrecognized — the
    resolver fail-fast error is printed in that case (an unparseable APP_ENV is a
    hard configuration error that predates this spec's guard semantics).

    Args:
        argv: Unused for now (reserved for future flags such as ``--strict``).

    Returns:
        Process exit code: ``0`` if consistent, ``1`` if inconsistent, ``2`` if
        ``APP_ENV`` is unset/unrecognized.
    """
    raw_app_env = os.environ.get("APP_ENV")
    try:
        app_env = parse_app_env(raw_app_env)
    except EnvironmentConfigError as exc:
        print(f"environment check: {exc}", file=sys.stderr)
        return 2

    report = build_consistency_report(app_env)
    print(report.format_report())

    # Exit non-zero on any inconsistency so the command is usable as a CI/preflight
    # gate (Req 4.5, 4.6). The verdict already accounts for failing checks AND
    # half-cutover; a consistent report exits 0.
    return 0 if report.is_consistent else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
