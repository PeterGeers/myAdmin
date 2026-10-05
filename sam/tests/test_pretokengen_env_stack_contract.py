"""
Template-contract tests for the PreTokenGen module's per-environment SAM stack
(test-environment spec, Phase 4).

Like the members contract test, these assert the ENVIRONMENT WIRING of
`sam/pretokengen/template.yaml` + `sam/pretokengen/samconfig.toml` statically
(no live AWS deploy). The PreTokenGen Lambda has NO API Gateway (it is
Cognito-invoked), so there is no authorizer/API assertion here; the environment
boundary for this module is:

  * its own projection table per environment (TEST reads
    `test_governance_projection`, PROD reads `governance_projection` — no shared
    projection, because a projection can deviate over time);
  * its own distinct CloudFormation stack (`test_pretokengen` vs
    `pretokengen-prod`), so a deploy of one cannot replace the other;
  * the cross-account Cognito invoke permission scoped to the per-env pool
    (TEST: myAdmin-test `eu-west-1_xyrlzfqbl`; PROD: Pool A `eu-west-1_Hdp40eWmu`);
  * APP_ENV DERIVED from the Stage knob via the StageToAppEnv mapping, so the
    stage / pool / projection / APP_ENV cannot drift.

The IAM read is scoped to the projection-table PARAMETER's exact ARN, so the
TEST role (resolved to `test_governance_projection`) cannot read the prod table.
"""

import os

import pytest
import tomllib
import yaml

_HERE = os.path.dirname(os.path.abspath(__file__))
_PTG_DIR = os.path.normpath(os.path.join(_HERE, "..", "pretokengen"))
_TEMPLATE_PATH = os.path.join(_PTG_DIR, "template.yaml")
_SAMCONFIG_PATH = os.path.join(_PTG_DIR, "samconfig.toml")

TEST_POOL_ID = "eu-west-1_xyrlzfqbl"
PROD_POOL_ID = "eu-west-1_Hdp40eWmu"
TEST_PROJECTION_TABLE = "test_governance_projection"
PROD_PROJECTION_TABLE = "governance_projection"


class _CfnTag:
    """Opaque marker for a CloudFormation intrinsic (e.g. ``!Ref``, ``!Sub``)."""

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
# Single-knob invariant: Stage carries APP_ENV
# -----------------------------------------------------------------------------


def test_stage_to_app_env_mapping_is_correct(template):
    mapping = template["Mappings"]["StageToAppEnv"]
    assert mapping["local"]["AppEnv"] == "test"
    assert mapping["test"]["AppEnv"] == "test"
    assert mapping["prod"]["AppEnv"] == "production"


def test_app_env_is_derived_from_stage_via_findinmap(template):
    env_vars = template["Resources"]["PreTokenGenFunction"]["Properties"][
        "Environment"
    ]["Variables"]
    app_env = env_vars["APP_ENV"]
    assert isinstance(app_env, _CfnTag) and app_env.tag == "FindInMap"
    assert app_env.value[0] == "StageToAppEnv"
    assert isinstance(app_env.value[1], _CfnTag) and app_env.value[1].tag == "Ref"
    assert app_env.value[1].value == "Stage"
    assert app_env.value[2] == "AppEnv"


# -----------------------------------------------------------------------------
# Projection isolation: IAM scoped to the table-name parameter (no wildcard)
# -----------------------------------------------------------------------------


def test_iam_read_is_scoped_to_projection_parameter(template):
    """The role's DynamoDB read is scoped to the projection-table PARAMETER ARN.

    So the TEST role (resolved to `test_governance_projection`) cannot read the
    prod `governance_projection` table, and vice-versa. No wildcard, same account.
    """
    policies = template["Resources"]["PreTokenGenFunction"]["Properties"]["Policies"]
    assert len(policies) == 1
    statements = policies[0]["Statement"]
    for stmt in statements:
        # Read-only: only Query on the projection.
        assert set(stmt["Action"]) == {"dynamodb:Query"}
        resources = stmt["Resource"]
        if not isinstance(resources, list):
            resources = [resources]
        for res in resources:
            assert isinstance(res, _CfnTag) and res.tag == "Sub"
            assert "${GovernanceProjectionTableName}" in res.value
            assert "table/*" not in res.value
            assert "${AWS::AccountId}" in res.value
            assert "${Region}" in res.value


# -----------------------------------------------------------------------------
# Cross-account invoke permission is per-environment
# -----------------------------------------------------------------------------


def test_invoke_permission_pool_is_a_parameter(template):
    perm = template["Resources"]["PreTokenGenCognitoInvokePermission"]["Properties"]
    assert perm["Principal"] == "cognito-idp.amazonaws.com"
    source = perm["SourceArn"]
    assert isinstance(source, _CfnTag) and source.tag == "Sub"
    assert "${CognitoUserPoolId}" in source.value
    assert "${CognitoAccountId}" in source.value


# -----------------------------------------------------------------------------
# samconfig: per-environment isolation (no shared projection, distinct stacks)
# -----------------------------------------------------------------------------


def test_test_and_prod_are_distinct_stacks(samconfig):
    assert samconfig["test"]["deploy"]["parameters"]["stack_name"] == "test-pretokengen"
    assert samconfig["prod"]["deploy"]["parameters"]["stack_name"] == "pretokengen-prod"


def test_test_reads_its_own_projection_not_prod(samconfig):
    """Phase 4 fix: TEST must NOT share the prod projection table."""
    test_o = _override_map(samconfig, "test")
    prod_o = _override_map(samconfig, "prod")
    assert test_o["GovernanceProjectionTableName"] == TEST_PROJECTION_TABLE
    assert prod_o["GovernanceProjectionTableName"] == PROD_PROJECTION_TABLE
    assert (
        test_o["GovernanceProjectionTableName"]
        != prod_o["GovernanceProjectionTableName"]
    )


def test_test_and_prod_use_different_pools(samconfig):
    test_o = _override_map(samconfig, "test")
    prod_o = _override_map(samconfig, "prod")
    assert test_o["CognitoUserPoolId"] == TEST_POOL_ID
    assert prod_o["CognitoUserPoolId"] == PROD_POOL_ID


def test_stage_matches_config_env(samconfig):
    assert _override_map(samconfig, "test")["Stage"] == "test"
    assert _override_map(samconfig, "prod")["Stage"] == "prod"
