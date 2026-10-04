"""Consistency-report value types for the environment consistency guard.

Extracted verbatim from ``consistency_guard`` (code-quality L2: split a 965-line
module along its cohesion seam). These two frozen dataclasses are the pure
report/value types the guard produces — no I/O, no checks, no entry points. They
live here so the plane-check functions (``_consistency_checks``) and the guard
facade (``consistency_guard``) can both depend on them without a cycle.

The public import surface is preserved by ``consistency_guard`` re-exporting
``PlaneCheck`` and ``ConsistencyReport`` — import them from either module.
"""

from dataclasses import dataclass

from .app_env import AppEnv


@dataclass(frozen=True)
class PlaneCheck:
    """One plane's consistency verdict against the active APP_ENV.

    Attributes:
        plane: The plane/surface name (e.g., ``"cognito_identity"``,
            ``"pool_registry"``, ``"identity_block"``, ``"client_secret"``,
            ``"half_cutover"``).
        resolved_env: The AppEnv this plane's wiring names, or ``None`` when the
            plane does not resolve to a single environment (e.g., an unregistered
            pool, or a check that is not env-specific). Used for half-cutover
            detection — a plane that names a concrete environment contributes its
            label to the "all planes agree" set.
        ok: Whether this plane's wiring is consistent with the active APP_ENV.
        message: Human-readable description. On a mismatch it names BOTH sides
            (the resolved/expected value and the actual value). Never contains a
            secret value.
    """

    plane: str
    resolved_env: AppEnv | None
    ok: bool
    message: str


@dataclass(frozen=True)
class ConsistencyReport:
    """Aggregate consistency verdict across every checked plane.

    Attributes:
        active_app_env: The active AppEnv the planes are compared against.
        checks: The per-plane verdicts, in check order.
        is_consistent: Derived — ``True`` iff every check is ``ok`` AND every plane
            that names a concrete environment resolves to the SAME environment
            (half-cutover detection). A single disagreeing surface makes the whole
            report inconsistent.
    """

    active_app_env: AppEnv
    checks: list[PlaneCheck]

    @property
    def is_consistent(self) -> bool:
        """``True`` iff all checks pass and all resolved envs agree.

        Two independent conditions must hold:

        1. Every :class:`PlaneCheck` is ``ok``.
        2. Every plane that names a concrete environment (``resolved_env is not
           None``) names the SAME environment — i.e. the set of resolved env labels
           has at most one member (half-cutover detection, Req 4.7 / 7.5).
        """
        if not all(check.ok for check in self.checks):
            return False
        resolved_envs = {
            check.resolved_env
            for check in self.checks
            if check.resolved_env is not None
        }
        return len(resolved_envs) <= 1

    def format_report(self) -> str:
        """Render a per-plane, human-readable report (no secret values)."""
        status = "CONSISTENT" if self.is_consistent else "INCONSISTENT"
        lines = [
            (
                f"Environment consistency report "
                f"(APP_ENV={self.active_app_env.value}): {status}"
            ),
        ]
        for check in self.checks:
            mark = "OK  " if check.ok else "FAIL"
            lines.append(f"  [{mark}] {check.plane}: {check.message}")
        return "\n".join(lines)

    def failing_checks(self) -> list[PlaneCheck]:
        """Return only the checks that did not pass (for diagnostics/logging)."""
        return [check for check in self.checks if not check.ok]
