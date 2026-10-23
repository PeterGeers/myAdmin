"""
Template-contract tests for the SEPARATE public application-intake API (application-app Task 1.3;
D27, R1/R2/R10.4; design §1/§3/§11a row (a)).

These assert the ROUTE / API / CORS wiring of ``sam/members/template.yaml`` +
``sam/members/samconfig.toml`` STATICALLY (no live AWS deploy — the wiring IS the isolation
mechanism). Task 1.3 is the route/API/CORS half of the public edge; the detailed least-privilege
IAM + API Gateway throttle/usage plan are task 7.1 and are deliberately NOT asserted here.

Covered:
  * D27 — a SEPARATE ``AWS::Serverless::Api`` (``MembersPublicApi``) with NO ``Auth`` /
    ``DefaultAuthorizer`` at all, distinct from the authenticated ``MembersApi`` (which KEEPS its
    Cognito ``DefaultAuthorizer`` — untouched blast-radius isolation).
  * The public Lambda (``MembersPublicFunction``) points at ``handler/public_app.handler`` (NOT the
    authenticated ``app.handler``), reuses the single ``MembersLayer``, and carries the single-knob
    APP_ENV.
  * Exactly the TWO public routes are registered — ``GET …/{tenant_slug}/field-config`` and
    ``POST …/{tenant_slug}/applications`` — on the public API only, never on ``MembersApi``.
  * CORS (R10.4) — the public API does NOT advertise a `'*'` origin (fail-closed), unlike the
    token-gated ``MembersApi``; the public edge's CORS allow-list + slug projection are wired as
    env vars from parameters, supplied per env in samconfig.
"""

import os

import pytest
import tomllib
import yaml

_HERE = os.path.dirname(os.path.abspath(__file__))
_MEMBERS_DIR = os.path.normpath(os.path.join(_HERE, "..", "members"))
_TEMPLATE_PATH = os.path.join(_MEMBERS_DIR, "template.yaml")
_SAMCONFIG_PATH = os.path.join(_MEMBERS_DIR, "samconfig.toml")


class _CfnTag:
    """Opaque marker for a CloudFormation intrinsic (``!Ref`` / ``!Sub`` / ``!Select`` / …)."""

    def __init__(self, tag: str, value):
        self.tag = tag
        self.value = value

    def __repr__(self):  # pragma: no cover - debugging aid
        return f"_CfnTag({self.tag!r}, {self.value!r})"


class _CfnLoader(yaml.SafeLoader):
    """SafeLoader that tolerates CloudFormation ``!Ref`` / ``!Sub`` / … tags."""


def _cfn_multi_constructor(loader, tag_suffix, node):
    if isinstance(node, yaml.ScalarNode):
        value = loader.construct_scalar(node)
    elif isinstance(node, yaml.SequenceNode):
        value = loader.construct_sequence(node)
    else:
        value = loader.construct_mapping(node)
    return _CfnTag(tag_suffix, value)


_CfnLoader.add_multi_constructor("!", _cfn_multi_constructor)


@pytest.fixture(scope="module")
def template() -> dict:
    with open(_TEMPLATE_PATH, "rb") as fh:
        return yaml.load(fh, Loader=_CfnLoader)


@pytest.fixture(scope="module")
def samconfig() -> dict:
    with open(_SAMCONFIG_PATH, "rb") as fh:
        return tomllib.load(fh)


def _override_map(samconfig: dict, env: str) -> dict:
    overrides = samconfig[env]["deploy"]["parameters"]["parameter_overrides"]
    out = {}
    for item in overrides:
        key, _, value = item.partition("=")
        out[key] = value
    return out


# -----------------------------------------------------------------------------
# D27 — a SEPARATE public API with NO DefaultAuthorizer
# -----------------------------------------------------------------------------


def test_public_api_is_a_separate_serverless_api(template):
    api = template["Resources"]["MembersPublicApi"]
    assert api["Type"] == "AWS::Serverless::Api"
    # Distinct from the authenticated API resource.
    assert "MembersApi" in template["Resources"]
    assert api is not template["Resources"]["MembersApi"]


def test_public_api_has_no_default_authorizer(template):
    """The whole point of D27: the public API carries NO Auth block / DefaultAuthorizer."""
    props = template["Resources"]["MembersPublicApi"]["Properties"]
    assert "Auth" not in props, "the public API must NOT declare any authorizer (D27)"


def test_authenticated_api_keeps_its_cognito_authorizer(template):
    """The authenticated MembersApi is UNTOUCHED — it still gates on the Cognito authorizer."""
    auth = template["Resources"]["MembersApi"]["Properties"]["Auth"]
    assert auth["DefaultAuthorizer"] == "CognitoAuthorizer"


def test_public_api_stage_is_the_stage_knob(template):
    stage_name = template["Resources"]["MembersPublicApi"]["Properties"]["StageName"]
    assert isinstance(stage_name, _CfnTag) and stage_name.tag == "Ref"
    assert stage_name.value == "Stage"


# -----------------------------------------------------------------------------
# The public Lambda — the token-less edge entrypoint
# -----------------------------------------------------------------------------


def test_public_function_points_at_public_app_handler(template):
    """The public fn routes to handler/public_app.handler — NOT the authenticated app.handler."""
    fn = template["Resources"]["MembersPublicFunction"]
    assert fn["Type"] == "AWS::Serverless::Function"
    assert fn["Properties"]["Handler"] == "sam.members.handler.public_app.handler"
    # It must NOT be the authenticated edge entrypoint.
    assert fn["Properties"]["Handler"] != "sam.members.handler.app.handler"


def test_public_function_is_named_per_stage(template):
    name = template["Resources"]["MembersPublicFunction"]["Properties"]["FunctionName"]
    assert isinstance(name, _CfnTag) and name.tag == "Sub"
    assert name.value == "members-public-${Stage}"


def test_public_function_reuses_the_members_layer(template):
    layers = template["Resources"]["MembersPublicFunction"]["Properties"]["Layers"]
    assert len(layers) == 1
    assert isinstance(layers[0], _CfnTag) and layers[0].tag == "Ref"
    assert layers[0].value == "MembersLayer"


def test_public_function_app_env_is_derived_from_stage(template):
    env_vars = template["Resources"]["MembersPublicFunction"]["Properties"][
        "Environment"
    ]["Variables"]
    app_env = env_vars["APP_ENV"]
    assert isinstance(app_env, _CfnTag) and app_env.tag == "FindInMap"
    assert app_env.value[0] == "StageToAppEnv"
    assert isinstance(app_env.value[1], _CfnTag) and app_env.value[1].value == "Stage"
    assert app_env.value[2] == "AppEnv"


def test_public_function_wires_cors_env_from_params(template):
    """The public edge's CORS allow-list is an env var fed from a parameter."""
    env_vars = template["Resources"]["MembersPublicFunction"]["Properties"][
        "Environment"
    ]["Variables"]
    origins = env_vars["PUBLIC_FORM_ALLOWED_ORIGINS"]
    assert isinstance(origins, _CfnTag) and origins.tag == "Ref"
    assert origins.value == "PublicFormAllowedOrigins"


def test_public_function_no_longer_carries_the_slug_map_env_task_7_1(template):
    """Task 7.1 (R7.3): `PUBLIC_TENANT_SLUG_MAP` is REMOVED — the edge resolves slug→tenant_id

    from the `_slugs/{slug}` bucket marker (OQ4, task 1.4), not an env projection. No stale env
    var may remain (and the CI `--parameter-overrides` footgun that blanked it, D7, is closed).
    """
    env_vars = template["Resources"]["MembersPublicFunction"]["Properties"][
        "Environment"
    ]["Variables"]
    assert "PUBLIC_TENANT_SLUG_MAP" not in env_vars


def test_public_function_now_carries_least_privilege_iam_task_7_1(template):
    """Task 7.1 ADDS the least-privilege IAM the task-1.3 wiring deferred — Policies now present."""
    props = template["Resources"]["MembersPublicFunction"]["Properties"]
    assert "Policies" in props, (
        "task 7.1 wires the public fn's least-privilege IAM (R10.5)"
    )


# -----------------------------------------------------------------------------
# Exactly the TWO public routes, on the public API only
# -----------------------------------------------------------------------------


def _public_api_events(template) -> dict:
    return template["Resources"]["MembersPublicFunction"]["Properties"]["Events"]


def test_public_function_registers_exactly_the_two_public_routes(template):
    events = _public_api_events(template)
    api_events = {
        name: e["Properties"] for name, e in events.items() if e["Type"] == "Api"
    }
    routes = {(p["Method"], p["Path"]) for p in api_events.values()}
    assert routes == {
        ("GET", "/public/members/{tenant_slug}/field-config"),
        ("POST", "/public/members/{tenant_slug}/applications"),
    }


def test_public_routes_are_bound_to_the_public_api_only(template):
    """Every public-fn route targets MembersPublicApi — never the authenticated MembersApi."""
    for e in _public_api_events(template).values():
        if e["Type"] != "Api":
            continue
        rest_api = e["Properties"]["RestApiId"]
        assert isinstance(rest_api, _CfnTag) and rest_api.tag == "Ref"
        assert rest_api.value == "MembersPublicApi"


def test_authenticated_function_does_not_serve_the_public_routes(template):
    """The authenticated MembersFunction keeps its ANY /{proxy+} catch-all, bound to MembersApi."""
    events = template["Resources"]["MembersFunction"]["Properties"]["Events"]
    for e in events.values():
        if e["Type"] != "Api":
            continue
        rest_api = e["Properties"]["RestApiId"]
        assert isinstance(rest_api, _CfnTag) and rest_api.value == "MembersApi"
        # No /public/ route is registered on the authenticated function.
        assert "/public/" not in e["Properties"]["Path"]


# -----------------------------------------------------------------------------
# CORS (R10.4) — the public API does not advertise a wildcard
# -----------------------------------------------------------------------------


def test_public_api_cors_is_not_a_wildcard(template):
    """R10.4: the public POST must not be callable cross-origin from any site — no `'*'` origin."""
    cors = template["Resources"]["MembersPublicApi"]["Properties"]["Cors"]
    allow_origin = cors["AllowOrigin"]
    # The authenticated API answers `'*'` (token-gated); the public one must NOT.
    assert allow_origin != "'*'"
    # It is derived from the first configured form origin (a !Sub over a !Select/!Split), never a
    # literal wildcard.
    assert isinstance(allow_origin, _CfnTag) and allow_origin.tag == "Sub"


def test_authenticated_api_cors_is_still_wildcard(template):
    """Regression guard: the authenticated API's token-gated `'*'` CORS is untouched."""
    cors = template["Resources"]["MembersApi"]["Properties"]["Cors"]
    assert cors["AllowOrigin"] == "'*'"


# -----------------------------------------------------------------------------
# Parameters + per-env samconfig wiring
# -----------------------------------------------------------------------------


def test_public_form_origin_param_exists_with_failclosed_default(template):
    params = template["Parameters"]
    # Empty default is fail-closed (no `*` origin) — never a dangerous default.
    assert params["PublicFormAllowedOrigins"]["Default"] == ""


def test_public_tenant_slug_map_param_is_removed_task_7_1(template):
    """Task 7.1 (R7.3): the `PublicTenantSlugMap` parameter is gone — slug→tenant_id is now

    DATA-backed (`_slugs/{slug}` bucket marker, OQ4), so no parameter is needed and the
    `--parameter-overrides` replace-not-merge footgun (D7 / decision 1a) can no longer blank it.
    """
    assert "PublicTenantSlugMap" not in template["Parameters"]


def test_samconfig_supplies_public_form_origin_per_env(samconfig):
    """Both envs supply a concrete (non-wildcard) form origin."""
    for env in ("test", "prod"):
        overrides = _override_map(samconfig, env)
        origin = overrides.get("PublicFormAllowedOrigins", "")
        assert origin.strip() != "", (
            f"{env}: public form origin must be supplied (no `*`)"
        )
        assert "*" not in origin


def test_samconfig_no_longer_supplies_the_slug_map_per_env_task_7_1(samconfig):
    """Task 7.1 (R7.3): neither env carries a `PublicTenantSlugMap` override any more — the slug

    is DATA on `config#fields` + the `_slugs/{slug}` bucket marker (OQ4), not a samconfig param.
    """
    for env in ("test", "prod"):
        overrides = _override_map(samconfig, env)
        assert "PublicTenantSlugMap" not in overrides, (
            f"{env}: PublicTenantSlugMap must be removed from samconfig (task 7.1)"
        )


def test_public_api_outputs_a_distinct_invoke_url(template):
    out = template["Outputs"]["MembersPublicApiBaseUrl"]["Value"]
    assert isinstance(out, _CfnTag) and out.tag == "Sub"
    assert "${MembersPublicApi}" in out.value
    assert "${Stage}" in out.value
