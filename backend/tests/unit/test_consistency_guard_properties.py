"""
Property-based tests for the Consistency_Guard verdict logic.

Uses Hypothesis to verify correctness properties from the design document.
Feature: test-environment
Reference: .kiro/specs/Common/test-environment/first-draft/design.md

Covers Properties 7-8 (Phase 0 — report-only consistency guard):

- Property 7: The guard is consistent iff every resolved surface matches the active
    APP_ENV.
    For ANY active APP_ENV, any identity-block mapping, and any set of registered
    issuers, build_consistency_report().is_consistent is True IFF every Phase-0
    surface agrees with the active APP_ENV:
      (a) the resolved pool is registered,
      (b) the identity block is either unset or names exactly the resolved
          pool/client,
      (c) the resolved test pool has an empty client secret, and
      (d) no half-cutover (all planes that name a concrete env agree).
    The oracle below recomputes the expected verdict independently from the
    generated inputs and asserts equality with the report's derived verdict — it
    does NOT call the guard internals to decide the expected answer.
    Validates: Requirements 4.1, 4.2, 4.3, 4.4, 4.6, 14.4, 14.5, 21.5, 21.6

- Property 8: Half-cutover is always detected.
    For ANY assignment of a per-plane resolved environment to each plane, a
    ConsistencyReport is consistent iff all planes that name a concrete environment
    name the SAME one (and all checks are ok); if any subset resolves to one
    environment while another subset resolves to the other, the report is
    inconsistent. This validates the resolved-env-set logic in
    ConsistencyReport.is_consistent directly.
    Validates: Requirements 4.7, 7.5

All env access goes through injected mappings and injected registered issuers — no
real AWS, DB, or os.environ mutation. The committed ENVIRONMENT_DEFINITION is used so
the resolved pool/client ids are the real TEST/PROD identifiers; strategies draw the
identity-block and registry values around those.
"""

import pytest
from hypothesis import given, settings, strategies as st

from environment.app_env import AppEnv
from environment.consistency_guard import (
    ConsistencyReport,
    PlaneCheck,
    build_consistency_report,
)
from environment.environment_definition import (
    ENVIRONMENT_DEFINITION,
    PROD_CLIENT_ID,
    PROD_POOL_ID,
    TEST_CLIENT_ID,
    TEST_POOL_ID,
)
from environment.resolver import resolve


# Issuer strings embedding the pool ids, mirroring Cognito's issuer URL shape.
TEST_ISSUER = f"https://cognito-idp.eu-west-1.amazonaws.com/{TEST_POOL_ID}"
PROD_ISSUER = f"https://cognito-idp.eu-west-1.amazonaws.com/{PROD_POOL_ID}"

# An issuer that embeds neither pool id — a genuinely unrelated registry entry.
UNRELATED_ISSUER = "https://cognito-idp.eu-west-1.amazonaws.com/eu-west-1_unrelated0"

# A pool id that is neither the TEST nor the PROD pool.
OTHER_POOL_ID = "eu-west-1_otherPool9"
# A client id that is neither the TEST nor the PROD client.
OTHER_CLIENT_ID = "other-client-id-xyz"

# A non-empty secret value used to exercise the test-pool empty-secret rule. The
# oracle only needs its (non-)emptiness, not its content.
NONEMPTY_SECRET = "a-non-empty-secret"


# ---------------------------------------------------------------------------
# Generators for Property 7
# ---------------------------------------------------------------------------

app_env_st = st.sampled_from(list(AppEnv))

# A registered-issuers list drawn from {TEST_ISSUER, PROD_ISSUER, UNRELATED_ISSUER},
# possibly empty, possibly with repeats — the guard only cares about membership.
registered_issuers_st = st.lists(
    st.sampled_from([TEST_ISSUER, PROD_ISSUER, UNRELATED_ISSUER]),
    min_size=0,
    max_size=4,
)

# Pool id for the identity block: unset (None), the TEST pool, the PROD pool, or an
# unrelated pool. "Unset" is distinguished from "present" so the oracle can apply the
# "unset => consistent" rule.
identity_pool_st = st.sampled_from([None, TEST_POOL_ID, PROD_POOL_ID, OTHER_POOL_ID])

# Client id for the identity block: same shape as the pool id.
identity_client_st = st.sampled_from(
    [None, TEST_CLIENT_ID, PROD_CLIENT_ID, OTHER_CLIENT_ID]
)

# Client secret: unset (None), empty string, or a non-empty value.
client_secret_st = st.sampled_from([None, "", NONEMPTY_SECRET])


def _build_environ(
    pool: object, client: object, secret: object
) -> dict:
    """Assemble an identity-block mapping, omitting keys whose value is None.

    Omission models a genuinely unset env var (the guard's `.get()` returns None),
    which the oracle treats differently from an empty/explicit value.
    """
    env: dict = {}
    if pool is not None:
        env["COGNITO_USER_POOL_ID"] = pool
    if client is not None:
        env["COGNITO_CLIENT_ID"] = client
    if secret is not None:
        env["COGNITO_CLIENT_SECRET"] = secret
    return env


def _expected_consistent(
    app_env: AppEnv,
    registered_issuers: list,
    pool: object,
    client: object,
    secret: object,
) -> bool:
    """Independently recompute the expected is_consistent verdict (the oracle).

    This mirrors the DESIGN contract (Property 7), not the guard's code path. It
    conjoins the individual Phase-0 plane conditions:

      (a) pool_registry: the resolved pool id appears in some registered issuer.
      (b) identity_block: for each of pool/client, the env value is unset (absent)
          OR exactly equals the resolved value. A set-but-wrong value fails.
      (c) client_secret: when APP_ENV is TEST, the client secret must be
          empty/unset; the rule does not apply to PRODUCTION.
      (d) half-cutover: in Phase 0 every passing plane carries the active env, and
          a failing identity_block/pool_registry contributes no concrete env label,
          so once (a)-(c) hold there is never more than one resolved env. Thus for
          the implemented surfaces the half-cutover condition is implied by (a)-(c)
          and adds no extra way to be inconsistent here (it is exercised directly
          by Property 8 instead).
    """
    resolved = resolve(app_env, ENVIRONMENT_DEFINITION)
    expected_pool = resolved.cognito.pool_id
    expected_client = resolved.cognito.client_id

    # (a) pool registered?
    pool_registered = any(expected_pool in issuer for issuer in registered_issuers)

    # (b) identity block unset-or-matching?
    pool_ok = (pool is None) or (str(pool).strip() == "") or (pool == expected_pool)
    client_ok = (
        (client is None)
        or (str(client).strip() == "")
        or (client == expected_client)
    )
    identity_ok = pool_ok and client_ok

    # (c) test pool => empty secret.
    if app_env == AppEnv.TEST:
        secret_ok = (secret is None) or (str(secret).strip() == "")
    else:
        secret_ok = True

    return pool_registered and identity_ok and secret_ok


# ---------------------------------------------------------------------------
# Property 7: guard consistency soundness (no false positives/negatives)
# Feature: test-environment, Property 7: guard consistent iff every surface matches
# Validates: Requirements 4.1, 4.2, 4.3, 4.4, 4.6, 14.4, 14.5, 21.5, 21.6
# ---------------------------------------------------------------------------

class TestProperty7GuardConsistencySoundness:
    """build_consistency_report().is_consistent equals the independent oracle."""

    @given(
        app_env=app_env_st,
        registered_issuers=registered_issuers_st,
        pool=identity_pool_st,
        client=identity_client_st,
        secret=client_secret_st,
    )
    @settings(max_examples=400)
    def test_build_report_verdict_matches_independent_oracle(
        self,
        app_env: AppEnv,
        registered_issuers: list,
        pool: object,
        client: object,
        secret: object,
    ) -> None:
        """The derived verdict equals the conjunction of the plane conditions.

        For ANY generated combination of (app_env, identity block, registered
        issuers), the report's is_consistent must exactly match the oracle — no
        false positives (reporting consistent when a surface disagrees) and no
        false negatives (reporting inconsistent when all surfaces agree).
        """
        environ = _build_environ(pool, client, secret)
        report = build_consistency_report(
            app_env,
            definition=ENVIRONMENT_DEFINITION,
            environ=environ,
            registered_issuers=registered_issuers,
        )
        expected = _expected_consistent(
            app_env, registered_issuers, pool, client, secret
        )
        assert report.is_consistent is expected

    @given(
        app_env=app_env_st,
        registered_issuers=registered_issuers_st,
        pool=identity_pool_st,
        client=identity_client_st,
        secret=client_secret_st,
    )
    @settings(max_examples=200)
    def test_build_report_inconsistent_names_a_failing_surface(
        self,
        app_env: AppEnv,
        registered_issuers: list,
        pool: object,
        client: object,
        secret: object,
    ) -> None:
        """Whenever the report is inconsistent, at least one plane names the mismatch.

        Property 7 requires the detail to name the mismatched surface. An
        inconsistent verdict in Phase 0 is always driven by a failing PlaneCheck
        (pool_registry / identity_block / client_secret), so failing_checks() must
        be non-empty and every failing check must carry a non-empty message.
        """
        environ = _build_environ(pool, client, secret)
        report = build_consistency_report(
            app_env,
            definition=ENVIRONMENT_DEFINITION,
            environ=environ,
            registered_issuers=registered_issuers,
        )
        if not report.is_consistent:
            failing = report.failing_checks()
            assert failing, "inconsistent report must have at least one failing check"
            assert all(c.message.strip() for c in failing)


# ---------------------------------------------------------------------------
# Generators for Property 8
# ---------------------------------------------------------------------------

# A per-plane resolved env: a concrete environment, or None (env-agnostic plane).
plane_resolved_env_st = st.sampled_from([AppEnv.TEST, AppEnv.PRODUCTION, None])


@st.composite
def _ok_plane_checks_st(draw) -> list:
    """A list of all-ok PlaneChecks with arbitrary per-plane resolved envs.

    Property 8 isolates the half-cutover (resolved-env-set) logic, so every check
    is `ok=True`; only the resolved_env labels vary. This lets the test attribute
    any inconsistency purely to env disagreement, not to a failing check.
    """
    envs = draw(st.lists(plane_resolved_env_st, min_size=1, max_size=6))
    return [
        PlaneCheck(plane=f"plane_{i}", resolved_env=env, ok=True, message="ok")
        for i, env in enumerate(envs)
    ]


def _concrete_envs(checks: list) -> set:
    """The set of concrete (non-None) resolved envs named across the checks."""
    return {c.resolved_env for c in checks if c.resolved_env is not None}


# ---------------------------------------------------------------------------
# Property 8: half-cutover is always detected
# Feature: test-environment, Property 8: half-cutover is always detected
# Validates: Requirements 4.7, 7.5
# ---------------------------------------------------------------------------

class TestProperty8HalfCutoverDetection:
    """is_consistent is True iff all concrete-env planes agree (given all ok)."""

    @given(active_env=app_env_st, checks=_ok_plane_checks_st())
    @settings(max_examples=400)
    def test_report_consistent_iff_concrete_envs_agree(
        self, active_env: AppEnv, checks: list
    ) -> None:
        """With all checks ok, consistency holds iff the resolved-env set is unanimous.

        If two planes name DIFFERENT concrete environments the report must be
        inconsistent; if all concrete-env planes agree (or none name a concrete
        env) it must be consistent. This asserts the resolved-env-set logic
        directly.
        """
        report = ConsistencyReport(active_app_env=active_env, checks=checks)
        distinct_envs = _concrete_envs(checks)
        expected_consistent = len(distinct_envs) <= 1
        assert report.is_consistent is expected_consistent

    @given(active_env=app_env_st, checks=_ok_plane_checks_st())
    @settings(max_examples=200)
    def test_report_with_mixed_concrete_envs_is_always_inconsistent(
        self, active_env: AppEnv, checks: list
    ) -> None:
        """Any plane naming TEST while another names PRODUCTION => inconsistent.

        Guards the "half-cutover is ALWAYS detected" direction explicitly: if both
        concrete environments appear among the planes, the verdict is False even
        though every individual check is ok.
        """
        if _concrete_envs(checks) == {AppEnv.TEST, AppEnv.PRODUCTION}:
            report = ConsistencyReport(active_app_env=active_env, checks=checks)
            assert report.is_consistent is False

    @given(
        active_env=app_env_st,
        concrete_env=st.sampled_from([AppEnv.TEST, AppEnv.PRODUCTION]),
        n_concrete=st.integers(min_value=1, max_value=4),
        n_agnostic=st.integers(min_value=0, max_value=3),
    )
    @settings(max_examples=200)
    def test_report_unanimous_concrete_env_with_agnostic_planes_is_consistent(
        self,
        active_env: AppEnv,
        concrete_env: AppEnv,
        n_concrete: int,
        n_agnostic: int,
    ) -> None:
        """All concrete planes naming one env, plus any None planes => consistent.

        Env-agnostic planes (resolved_env=None) never contribute to the half-cutover
        set, so a unanimous concrete env with any number of None planes stays
        consistent.
        """
        checks = [
            PlaneCheck(f"c{i}", concrete_env, True, "ok") for i in range(n_concrete)
        ] + [PlaneCheck(f"a{i}", None, True, "ok") for i in range(n_agnostic)]
        report = ConsistencyReport(active_app_env=active_env, checks=checks)
        assert report.is_consistent is True
