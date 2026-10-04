"""
APP_ENV selector (fail-fast, no defaults, no dangerous fallback).

S3 / T1.2 — Define the closed enum and parser for the single authoritative environment
selector.

The Environment_Resolver (T1.4) reads the active environment solely from `APP_ENV`,
which must be one of the recognized values `production` or `test`. An unset or
unrecognized value causes the running unit to refuse to start — this is the
fail-fast, no-dangerous-default philosophy that matches the existing discipline in
`auth/pool_registry.py` and `auth/test_pool_config.py` (missing var ⇒ raise, never
a silent fallback).

Design contract (see `.kiro/specs/Common/test-environment/first-draft/design.md`):

- `APP_ENV` is a closed enum, not a boolean.
- Recognized values: `production`, `test`.
- Unset/unknown ⇒ refuse to start with an error naming the bad value and the
  recognized set — same message shape as `PoolRegistryError`.
- The parser strips whitespace and is case-sensitive (must match the enum literals
  exactly).
- No default is ever substituted (no-dangerous-fallbacks guardrail).
"""

import enum


class AppEnv(enum.Enum):
    """The closed set of recognized environment values.

    Use the enum members (`AppEnv.PRODUCTION`, `AppEnv.TEST`) rather than raw
    strings for type safety. The string values are the canonical environment
    names read from `APP_ENV`.
    """

    PRODUCTION = "production"
    TEST = "test"


class EnvironmentConfigError(RuntimeError):
    """Raised when `APP_ENV` is unset/unrecognized or a plane's resolved wiring is
    impossible.

    Fail loudly — never default to an environment (no-dangerous-fallbacks). This
    error class is a sibling of `PoolRegistryError` and `TestPoolConfigError` in
    the fail-fast configuration-error family.
    """


def parse_app_env(raw: str | None) -> AppEnv:
    """Parse a raw `APP_ENV` value into a validated `AppEnv` member.

    Fail-fast validation: if `raw` is `None`, empty, or not a recognized value,
    raises `EnvironmentConfigError` with a message naming the bad value (if any)
    and the recognized values. No default is ever substituted.

    Args:
        raw: The raw `APP_ENV` string (as read from the environment). May be
            `None` if the variable is unset.

    Returns:
        The corresponding `AppEnv` member (`PRODUCTION` or `TEST`).

    Raises:
        EnvironmentConfigError: `raw` is `None`, blank, or not one of the
            recognized values `"production"`, `"test"`.
    """
    if raw is None or raw.strip() == "":
        raise EnvironmentConfigError(
            "APP_ENV is unset. It must be one of: 'production', 'test'. "
            "There is no default (no-dangerous-fallbacks)."
        )

    # Strip surrounding whitespace; the enum comparison is case-sensitive.
    cleaned = raw.strip()
    try:
        return AppEnv(cleaned)
    except ValueError:
        raise EnvironmentConfigError(
            f"APP_ENV='{raw}' is not recognized. It must be one of: "
            f"'production', 'test'."
        )
