"""Per-plane consistency checks for the environment consistency guard.

Extracted verbatim from ``consistency_guard`` (code-quality L2: split a 965-line
module along its cohesion seam). Each ``_check_*`` function is a pure
``(resolved, ...) -> PlaneCheck`` verdict for one observable plane — no I/O beyond
reading the injected ``environ`` mapping, no raising, no report assembly. The guard
facade (``consistency_guard``) orchestrates these into a ``ConsistencyReport``.

The public import surface is preserved by ``consistency_guard`` re-exporting every
``_check_*`` name, so existing imports (and the test suite, which imports several of
these directly from ``environment.consistency_guard``) keep working unchanged.
"""

from collections.abc import Mapping

from ._consistency_report import PlaneCheck
from .app_env import AppEnv
from .environment_definition import EnvironmentDefinition
from .resolver import ResolvedConfig, resolve


def _check_cognito_pool_registered(
    resolved: ResolvedConfig, registered_issuers: list[str]
) -> PlaneCheck:
    """The active resolved Cognito pool must be present in the Pool_Registry.

    Req 4.1, 4.2: the pool required by the active environment must be registered;
    on a mismatch the message names BOTH the resolved pool and the registered
    pools (all non-secret identifiers).

    The pool is matched by its id appearing in any registered issuer string (the
    Cognito issuer URL embeds the pool id, e.g.
    ``https://cognito-idp.<region>.amazonaws.com/<pool_id>``). This keeps the check
    robust whether the registry exposes raw pool ids or full issuer URLs.
    """
    pool_id = resolved.cognito.pool_id
    is_registered = any(pool_id in issuer for issuer in registered_issuers)
    if is_registered:
        return PlaneCheck(
            plane="pool_registry",
            resolved_env=resolved.app_env,
            ok=True,
            message=(
                f"resolved pool '{pool_id}' ({resolved.cognito.pool_label}) is "
                f"registered in the Pool_Registry"
            ),
        )
    registered = ", ".join(registered_issuers) if registered_issuers else "<none>"
    return PlaneCheck(
        plane="pool_registry",
        # resolved_env left None: an unregistered pool is a membership failure,
        # not evidence that this plane names a *different* environment, so it must
        # not be counted as a half-cutover signal.
        resolved_env=None,
        ok=False,
        message=(
            f"resolved Cognito pool '{pool_id}' ({resolved.cognito.pool_label}) is "
            f"NOT registered in the Pool_Registry. Registered issuers: {registered}"
        ),
    )


def _check_frontend_pool_vs_registry(
    resolved: ResolvedConfig, registered_issuers: list[str]
) -> PlaneCheck:
    """The frontend-selected Cognito pool must be present in the backend registry.

    Req 4.2: the pool the FRONTEND build selects for this APP_ENV must be one the
    backend accepts. The frontend and backend read the SAME committed
    Environment_Definition, so the backend can compute exactly which pool the
    frontend build for the active APP_ENV would select — it is the same
    ``cognito.pool_id`` the resolver already produces (the frontend
    ``aws-exports`` selects its pool from the resolved APP_ENV, not from hostname,
    per task 5). This check frames the comparison from the frontend-selected side:
    it asserts that frontend-selected pool is registered among the backend's
    issuers, and on a mismatch names BOTH the frontend-selected pool and the
    registered pools.

    This is intentionally a DISTINCT check from ``pool_registry`` even though both
    resolve to the same pool id today: the two checks guard different seams. The
    ``pool_registry`` check (Req 4.1) answers "does the backend's own resolved pool
    live in its registry"; this check (Req 4.2) answers "does the pool the frontend
    build hands the backend live in that registry" — framed from the frontend's
    perspective so a future divergence between the two selection paths (e.g. a
    frontend pinned to a stale definition) surfaces as its own named failure rather
    than hiding behind the backend-side check.

    The pool is matched by its id appearing in any registered issuer string (the
    Cognito issuer URL embeds the pool id), mirroring
    :func:`_check_cognito_pool_registered`.
    """
    frontend_pool_id = resolved.cognito.pool_id  # same definition the frontend reads
    is_registered = any(frontend_pool_id in issuer for issuer in registered_issuers)
    if is_registered:
        return PlaneCheck(
            plane="frontend_pool_vs_registry",
            resolved_env=resolved.app_env,
            ok=True,
            message=(
                f"frontend-selected pool '{frontend_pool_id}' "
                f"({resolved.cognito.pool_label}) for APP_ENV="
                f"{resolved.app_env.value} is registered in the backend "
                f"Pool_Registry"
            ),
        )
    registered = ", ".join(registered_issuers) if registered_issuers else "<none>"
    return PlaneCheck(
        plane="frontend_pool_vs_registry",
        # resolved_env left None: an unregistered pool is a membership failure, not
        # evidence this plane names a *different* environment, so it must not be
        # counted as a half-cutover signal (mirrors _check_cognito_pool_registered).
        resolved_env=None,
        ok=False,
        message=(
            f"frontend-selected Cognito pool '{frontend_pool_id}' "
            f"({resolved.cognito.pool_label}) for APP_ENV="
            f"{resolved.app_env.value} is NOT registered in the backend "
            f"Pool_Registry. Registered issuers: {registered}"
        ),
    )


def _check_identity_block(
    resolved: ResolvedConfig, environ: Mapping[str, str]
) -> PlaneCheck:
    """The identity block env vars must name the resolved pool/client.

    Req 4.3, 7.2: ``COGNITO_USER_POOL_ID`` / ``COGNITO_CLIENT_ID`` must match the
    pool/client that the active APP_ENV resolves to. On a mismatch the message names
    both the resolved and the actual (env) values (all non-secret identifiers).
    """
    expected_pool = resolved.cognito.pool_id
    expected_client = resolved.cognito.client_id
    actual_pool = (environ.get("COGNITO_USER_POOL_ID") or "").strip()
    actual_client = (environ.get("COGNITO_CLIENT_ID") or "").strip()

    mismatches = []
    if actual_pool and actual_pool != expected_pool:
        mismatches.append(
            f"COGNITO_USER_POOL_ID='{actual_pool}' but APP_ENV resolves to "
            f"'{expected_pool}'"
        )
    if actual_client and actual_client != expected_client:
        mismatches.append(
            f"COGNITO_CLIENT_ID='{actual_client}' but APP_ENV resolves to "
            f"'{expected_client}'"
        )

    if mismatches:
        return PlaneCheck(
            plane="identity_block",
            # A set identity block that names a different pool is a genuine
            # "this plane resolves elsewhere" signal, but we cannot map an
            # arbitrary pool id back to an AppEnv here, so flag the failure
            # without contributing a (possibly wrong) env label.
            resolved_env=None,
            ok=False,
            message="; ".join(mismatches),
        )

    # When the identity block is unset we treat it as consistent (nothing to
    # contradict) — fail-fast on *conflict*, not on absence, in report-only phase.
    if not actual_pool and not actual_client:
        detail = "identity block (COGNITO_USER_POOL_ID/CLIENT_ID) is unset"
    else:
        detail = (
            f"identity block names pool '{expected_pool}' / client "
            f"'{expected_client}', matching APP_ENV"
        )
    return PlaneCheck(
        plane="identity_block",
        resolved_env=resolved.app_env,
        ok=True,
        message=detail,
    )


def _check_client_secret(
    resolved: ResolvedConfig, environ: Mapping[str, str]
) -> PlaneCheck:
    """The test pool must have an empty client secret.

    Req 7.3, 8.4: when the resolved pool is the test pool, ``COGNITO_CLIENT_SECRET``
    must be empty (the test app-client has no secret).

    Security (Req 6.6): this asserts emptiness only — it NEVER echoes the secret
    value. On failure it reports that a non-empty secret is set, not what it is.
    """
    if resolved.app_env != AppEnv.TEST:
        return PlaneCheck(
            plane="client_secret",
            resolved_env=resolved.app_env,
            ok=True,
            message=(
                "client-secret emptiness check applies to the test pool only; "
                "APP_ENV is production"
            ),
        )

    secret = environ.get("COGNITO_CLIENT_SECRET")
    secret_is_empty = secret is None or secret.strip() == ""
    if secret_is_empty:
        return PlaneCheck(
            plane="client_secret",
            resolved_env=resolved.app_env,
            ok=True,
            message="test pool has an empty COGNITO_CLIENT_SECRET as required",
        )
    return PlaneCheck(
        plane="client_secret",
        resolved_env=resolved.app_env,
        ok=False,
        # Non-secret message: assert the violation without revealing the value.
        message=(
            "resolved pool is the test pool but COGNITO_CLIENT_SECRET is non-empty; "
            "the test app-client has no secret, so it must be empty"
        ),
    )


def _check_mysql_target(
    resolved: ResolvedConfig, definition: EnvironmentDefinition
) -> PlaneCheck:
    """The resolved TEST MySQL target must differ from the resolved PRODUCTION one.

    Req 9.3, 9.5, 9.6: the MySQL plane isolates TEST from PRODUCTION by being
    SEPARATE resolved targets with SEPARATE credentials — the boundary is enforced
    by distinct targets, not assumed from physical hosting. So even if the two
    targets were later co-hosted, they must still name different connection
    identities/credentials. This check compares the TWO resolved targets from the
    definition and fails if the active (TEST) connection would resolve to the
    SAME target+credentials as PRODUCTION (Req 9.5), or if either schema is not
    ``finance`` (Req 9.2).

    The comparison is over the resolved connection REFERENCES (``host_ref``,
    ``port_ref``, ``user_ref``, ``password_ref``) plus ``target_label`` — the
    non-secret identity of each target. Secret VALUES are never read or echoed
    (Req 6.6): two targets that merely share a password_ref ENV-VAR NAME are
    treated as sharing credentials, which is the stricter, safe reading.

    The check contributes ``resolved_env`` so it participates in half-cutover
    detection like the other plane checks.
    """
    test_target = resolve(AppEnv.TEST, definition).mysql
    prod_target = resolve(AppEnv.PRODUCTION, definition).mysql

    def _identity(t) -> tuple:
        return (t.host_ref, t.port_ref, t.user_ref, t.password_ref)

    # Req 9.2: schema must be `finance` for both environments.
    bad_schema = [
        f"{label} schema is '{schema}', expected 'finance'"
        for label, schema in (
            ("TEST", test_target.schema),
            ("PRODUCTION", prod_target.schema),
        )
        if schema != "finance"
    ]
    if bad_schema:
        return PlaneCheck(
            plane="mysql_target",
            resolved_env=resolved.app_env,
            ok=False,
            message="; ".join(bad_schema),
        )

    # Req 9.5/9.6: the two resolved targets must be distinct in identity+credentials.
    if _identity(test_target) == _identity(prod_target):
        return PlaneCheck(
            plane="mysql_target",
            resolved_env=resolved.app_env,
            ok=False,
            message=(
                "resolved TEST MySQL target is NOT isolated from the resolved "
                "PRODUCTION target: both resolve to the same connection identity "
                f"(host_ref='{test_target.host_ref}', port_ref="
                f"'{test_target.port_ref}', user_ref='{test_target.user_ref}', "
                f"password_ref='{test_target.password_ref}'). The TEST and "
                "PRODUCTION targets must be separate targets with separate "
                "credentials (schema 'finance' for both)"
            ),
        )

    # Req 9.3: the ACTIVE resolved target must be the one the active APP_ENV
    # declares — i.e. APP_ENV=test resolves to the TEST target (not PROD) and
    # vice-versa. Since TEST≠PROD is already asserted above, comparing the active
    # resolved identity to the expected-env target catches a resolver that handed
    # back the wrong environment's connection for the active APP_ENV.
    active_target = resolved.mysql
    expected_target = test_target if resolved.app_env == AppEnv.TEST else prod_target
    other_target = prod_target if resolved.app_env == AppEnv.TEST else test_target
    if _identity(active_target) != _identity(expected_target):
        return PlaneCheck(
            plane="mysql_target",
            # The active target names the other environment's connection — a genuine
            # "this plane resolves elsewhere" signal, but we flag it as a failure
            # rather than contributing a (wrong) env label to the half-cutover set.
            resolved_env=None,
            ok=False,
            message=(
                f"resolved MySQL target for APP_ENV={resolved.app_env.value} does "
                f"not match the {expected_target.target_label} target declared in "
                f"the Environment_Definition: active resolves to host_ref="
                f"'{active_target.host_ref}', user_ref='{active_target.user_ref}' "
                f"but APP_ENV={resolved.app_env.value} expects host_ref="
                f"'{expected_target.host_ref}', user_ref='{expected_target.user_ref}'"
            ),
        )

    return PlaneCheck(
        plane="mysql_target",
        resolved_env=resolved.app_env,
        ok=True,
        message=(
            f"resolved MySQL target '{active_target.target_label}' (schema "
            f"'{active_target.schema}', host_ref='{active_target.host_ref}') for "
            f"APP_ENV={resolved.app_env.value} matches the active env and is "
            f"isolated from the {other_target.target_label} target by a distinct "
            "connection identity and credentials"
        ),
    )


def _check_flask_api_base_url(
    resolved: ResolvedConfig, definition: EnvironmentDefinition
) -> PlaneCheck:
    """The resolved Flask API base URL the frontend calls must match APP_ENV.

    Req 21.5, 21.6: the Flask API base URL the Frontend_Plane calls is resolved
    from ``APP_ENV`` (parallel to the SAM API base URL). The guard verifies the
    active resolved URL is the one the Environment_Definition declares for the
    active env, and that the TEST and PRODUCTION Flask URLs differ — so a frontend
    built for one env calling a backend started for the other surfaces as a
    half-cutover (their resolved URLs disagree).

    Both the frontend and backend read the SAME committed Environment_Definition,
    so the backend can compute the expected Flask URL for the active APP_ENV and
    assert the resolved value equals the definition's value for that env (and
    differs from the other env's). On a mismatch the message names BOTH sides —
    the resolved/active URL and the expected (or other-env) URL. Flask API base
    URLs are non-secret, so they appear in messages (Req 6.6 is satisfied: no
    secret VALUE is read or echoed).

    Contributes ``resolved_env`` so it participates in half-cutover detection like
    the other plane checks.
    """
    test_url = resolve(AppEnv.TEST, definition).flask_api_base_url
    prod_url = resolve(AppEnv.PRODUCTION, definition).flask_api_base_url

    expected_url = test_url if resolved.app_env == AppEnv.TEST else prod_url
    other_env = "PRODUCTION" if resolved.app_env == AppEnv.TEST else "TEST"
    other_url = prod_url if resolved.app_env == AppEnv.TEST else test_url
    active_url = resolved.flask_api_base_url

    # Req 21.5/21.6: the TEST and PROD resolved Flask URLs must differ, otherwise
    # the frontend cannot be told apart per-environment and the boundary collapses.
    if test_url == prod_url:
        return PlaneCheck(
            plane="flask_api_base_url",
            resolved_env=resolved.app_env,
            ok=False,
            message=(
                "resolved TEST and PRODUCTION Flask API base URLs are identical "
                f"('{test_url}'); the Frontend_Plane cannot be isolated per "
                "environment. The two environments must resolve to distinct Flask "
                "API base URLs"
            ),
        )

    # The active resolved URL must be the one declared for the active APP_ENV.
    if active_url != expected_url:
        return PlaneCheck(
            plane="flask_api_base_url",
            # Names the other env's URL — a "resolves elsewhere" signal, flagged as
            # a failure rather than contributing a wrong env label to the cutover set.
            resolved_env=None,
            ok=False,
            message=(
                f"resolved Flask API base URL for APP_ENV={resolved.app_env.value} "
                f"is '{active_url}', but APP_ENV={resolved.app_env.value} expects "
                f"'{expected_url}'"
                + (f" (that is the {other_env} URL)" if active_url == other_url else "")
            ),
        )

    return PlaneCheck(
        plane="flask_api_base_url",
        resolved_env=resolved.app_env,
        ok=True,
        message=(
            f"resolved Flask API base URL '{active_url}' matches APP_ENV="
            f"{resolved.app_env.value} and differs from the {other_env} URL "
            f"'{other_url}'"
        ),
    )


def _check_sam_authorizer_pool(
    resolved: ResolvedConfig, definition: EnvironmentDefinition
) -> PlaneCheck:
    """The SAM API's Cognito authorizer pool must match the active APP_ENV.

    Req 14.4, 14.5: the SAM compute plane fronts its API Gateway with a Cognito
    authorizer whose pool is resolved from ``APP_ENV``. A TEST deploy must authorize
    against the test pool and a PRODUCTION deploy against Pool A, so a token minted
    by the wrong pool is rejected at the edge rather than silently accepted.

    The guard compares the active resolved authorizer pool to the one the
    Environment_Definition declares for the active env, and asserts the TEST and
    PRODUCTION authorizer pools differ (otherwise the SAM edge cannot tell the
    environments apart). Pool ids are non-secret, so they appear in messages.

    IMPORTANT: the SAM authorizer pool and the identity-plane Cognito pool are the
    SAME pool per environment by design (the SAM API and the Flask backend trust the
    same pool), so this check also surfaces a drift between the two planes — if the
    SAM authorizer were ever pointed at a different pool than the identity plane for
    the same env, the resolved values would disagree here.

    Contributes ``resolved_env`` so it joins the half-cutover set.
    """
    test_pool = resolve(AppEnv.TEST, definition).sam.authorizer_pool_id
    prod_pool = resolve(AppEnv.PRODUCTION, definition).sam.authorizer_pool_id

    expected_pool = test_pool if resolved.app_env == AppEnv.TEST else prod_pool
    other_env = "PRODUCTION" if resolved.app_env == AppEnv.TEST else "TEST"
    other_pool = prod_pool if resolved.app_env == AppEnv.TEST else test_pool
    active_pool = resolved.sam.authorizer_pool_id

    if test_pool == prod_pool:
        return PlaneCheck(
            plane="sam_authorizer_pool",
            resolved_env=resolved.app_env,
            ok=False,
            message=(
                "resolved TEST and PRODUCTION SAM authorizer pools are identical "
                f"('{test_pool}'); the SAM API edge cannot distinguish environments. "
                "The two environments must authorize against distinct Cognito pools"
            ),
        )

    if active_pool != expected_pool:
        return PlaneCheck(
            plane="sam_authorizer_pool",
            # Names the other env's pool — a "resolves elsewhere" signal; flagged as
            # a failure rather than contributing a wrong env label to the cutover set.
            resolved_env=None,
            ok=False,
            message=(
                f"resolved SAM authorizer pool for APP_ENV={resolved.app_env.value} "
                f"is '{active_pool}', but APP_ENV={resolved.app_env.value} expects "
                f"'{expected_pool}'"
                + (
                    f" (that is the {other_env} pool)"
                    if active_pool == other_pool
                    else ""
                )
            ),
        )

    return PlaneCheck(
        plane="sam_authorizer_pool",
        resolved_env=resolved.app_env,
        ok=True,
        message=(
            f"resolved SAM authorizer pool '{active_pool}' matches APP_ENV="
            f"{resolved.app_env.value} and differs from the {other_env} pool "
            f"'{other_pool}'"
        ),
    )


def _check_sam_api_base_url(
    resolved: ResolvedConfig, definition: EnvironmentDefinition
) -> PlaneCheck:
    """The SAM API base URL clients call must match the active APP_ENV.

    Req 4.4, 14.4: the SAM API base URL (the API Gateway invoke URL the frontend +
    health report use) is resolved from ``APP_ENV``. The guard asserts the active
    resolved URL is the one the Environment_Definition declares for the active env,
    and that the TEST and PRODUCTION SAM URLs differ — so a client built for one env
    calling the other env's SAM API surfaces as a half-cutover.

    PLACEHOLDER TOLERANCE: before the TEST/PROD SAM stacks are first deployed, the
    definition records a PLACEHOLDER invoke URL (``...PLACEHOLDER_<ENV>_API...``).
    A placeholder is NOT yet an observable endpoint, so this check treats a
    still-placeholder active URL as "not yet deployed" and passes WITHOUT asserting a
    concrete match — it only requires that the TEST and PRODUCTION URLs are distinct
    (which the placeholders already are). Once a real URL is recorded the full
    active==expected assertion applies. This mirrors the frontend
    EnvironmentIndicator's ``isObservableSamUrl`` suppression and keeps the guard from
    failing a correctly-wired-but-not-yet-deployed TEST stack.

    SAM API URLs are non-secret, so they appear in messages. Contributes
    ``resolved_env`` so it joins the half-cutover set.
    """
    test_url = resolve(AppEnv.TEST, definition).sam.api_base_url
    prod_url = resolve(AppEnv.PRODUCTION, definition).sam.api_base_url

    expected_url = test_url if resolved.app_env == AppEnv.TEST else prod_url
    other_env = "PRODUCTION" if resolved.app_env == AppEnv.TEST else "TEST"
    other_url = prod_url if resolved.app_env == AppEnv.TEST else test_url
    active_url = resolved.sam.api_base_url

    # The TEST and PROD SAM URLs must differ regardless of deploy state.
    if test_url == prod_url:
        return PlaneCheck(
            plane="sam_api_base_url",
            resolved_env=resolved.app_env,
            ok=False,
            message=(
                "resolved TEST and PRODUCTION SAM API base URLs are identical "
                f"('{test_url}'); clients cannot be isolated per environment. The "
                "two environments must resolve to distinct SAM API base URLs"
            ),
        )

    # Placeholder (not-yet-deployed) tolerance: a placeholder is not observable, so
    # do not assert a concrete active==expected match yet (the stack is wired but not
    # deployed). The distinctness check above still holds.
    if "PLACEHOLDER" in active_url.upper():
        return PlaneCheck(
            plane="sam_api_base_url",
            resolved_env=resolved.app_env,
            ok=True,
            message=(
                f"resolved SAM API base URL for APP_ENV={resolved.app_env.value} is "
                f"a placeholder ('{active_url}') — the SAM stack for this env is "
                "wired but not yet deployed; distinctness from the "
                f"{other_env} URL is satisfied"
            ),
        )

    if active_url != expected_url:
        return PlaneCheck(
            plane="sam_api_base_url",
            # Names the other env's URL — flagged as a failure rather than
            # contributing a wrong env label to the cutover set.
            resolved_env=None,
            ok=False,
            message=(
                f"resolved SAM API base URL for APP_ENV={resolved.app_env.value} is "
                f"'{active_url}', but APP_ENV={resolved.app_env.value} expects "
                f"'{expected_url}'"
                + (f" (that is the {other_env} URL)" if active_url == other_url else "")
            ),
        )

    return PlaneCheck(
        plane="sam_api_base_url",
        resolved_env=resolved.app_env,
        ok=True,
        message=(
            f"resolved SAM API base URL '{active_url}' matches APP_ENV="
            f"{resolved.app_env.value} and differs from the {other_env} URL "
            f"'{other_url}'"
        ),
    )


def _check_dynamodb_prefix(
    resolved: ResolvedConfig, definition: EnvironmentDefinition
) -> PlaneCheck:
    """The DynamoDB table prefix must match the active APP_ENV.

    Req 10.2, 19.4: the SAM data plane isolates environments by a per-env table
    prefix — ``test_`` for TEST and the empty prefix for PRODUCTION — so no table is
    shared across environments. The guard asserts the active resolved prefix is the
    one the Environment_Definition declares for the active env (TEST -> ``test_``,
    PRODUCTION -> ``""``), and that the two env prefixes differ (otherwise the data
    plane cannot be separated).

    This is the backend-startup counterpart to the SAM template contract test: the
    template scopes IAM to ``test_``-prefixed ARNs for the TEST stack, and this check
    verifies the RUNNING backend's resolved view of that same boundary agrees with
    APP_ENV. Prefixes are non-secret. Contributes ``resolved_env`` for the
    half-cutover set.
    """
    test_prefix = resolve(AppEnv.TEST, definition).sam.table_prefix
    prod_prefix = resolve(AppEnv.PRODUCTION, definition).sam.table_prefix

    expected_prefix = test_prefix if resolved.app_env == AppEnv.TEST else prod_prefix
    active_prefix = resolved.sam.table_prefix

    # TEST and PROD prefixes must differ, else the data plane cannot be isolated.
    if test_prefix == prod_prefix:
        return PlaneCheck(
            plane="dynamodb_prefix",
            resolved_env=resolved.app_env,
            ok=False,
            message=(
                "resolved TEST and PRODUCTION DynamoDB table prefixes are identical "
                f"('{test_prefix or '<empty>'}'); the SAM data plane cannot be "
                "isolated per environment. TEST must use a distinct table prefix"
            ),
        )

    if active_prefix != expected_prefix:
        return PlaneCheck(
            plane="dynamodb_prefix",
            resolved_env=None,
            ok=False,
            message=(
                f"resolved DynamoDB table prefix for APP_ENV={resolved.app_env.value}"
                f" is '{active_prefix or '<empty>'}', but APP_ENV="
                f"{resolved.app_env.value} expects '{expected_prefix or '<empty>'}'"
            ),
        )

    return PlaneCheck(
        plane="dynamodb_prefix",
        resolved_env=resolved.app_env,
        ok=True,
        message=(
            f"resolved DynamoDB table prefix '{active_prefix or '<empty>'}' matches "
            f"APP_ENV={resolved.app_env.value}"
        ),
    )
