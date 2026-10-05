"""
Template-contract tests for the Members module's per-environment SAM stack
(test-environment spec, Phase 4 — tasks 21/22/23).

These assert the ENVIRONMENT WIRING of `sam/members/template.yaml` +
`sam/members/samconfig.toml` statically, without a live AWS deploy. The wiring IS
the isolation mechanism, so verifying it here is the honest, deploy-free way to
cover:

  * Task 21 — environment-scoped execution role: the Lambda's inline IAM grants
    DynamoDB access ONLY to the exact table-name parameters (no wildcard table,
    no cross-account), so a TEST stack (resolved to `test_*` tables) can never
    touch the unprefixed PROD tables, and vice-versa.
  * Task 22 — separate TEST API Gateway: TEST and PROD are distinct
    CloudFormation stacks (`test_sam-members` vs `sam-members`), each declaring
    its own `AWS::Serverless::Api`, so each gets its own API Gateway + invoke URL.
  * Task 23 — per-environment Cognito authorizer: the API's authorizer pool is
    the `CognitoUserPoolArn` parameter, which samconfig sets to the TEST pool
    (`eu-west-1_xyrlzfqbl`) for `[test]` and the PROD pool (`eu-west-1_Hdp40eWmu`)
    for `[prod]`.

It also pins the single-knob invariant: the Lambda's APP_ENV is DERIVED from the
`Stage` parameter via the `StageToAppEnv` mapping, so stage / pool / tables /
APP_ENV cannot drift within a deployed stack.

A true cross-prefix IAM DENY / authorizer ACCEPT-REJECT exercise needs a live
deploy (real AWS, gated) and is out of scope for this deploy-free suite.
"""

import os

import pytest
import tomllib
import yaml

_HERE = os.path.dirname(os.path.abspath(__file__))
_MEMBERS_DIR = os.path.normpath(os.path.join(_HERE, "..", "members"))
_TEMPLATE_PATH = os.path.join(_MEMBERS_DIR, "template.yaml")
_SAMCONFIG_PATH = os.path.join(_MEMBERS_DIR, "samconfig.toml")

# Expected per-environment identifiers (PUBLIC — pool ids / app-client ids).
TEST_POOL_ID = "eu-west-1_xyrlzfqbl"
PROD_POOL_ID = "eu-west-1_Hdp40eWmu"
TEST_MEMBERS_TABLE = "test_sam-members"
PROD_MEMBERS_TABLE = "sam-members"
TEST_PROJECTION_TABLE = "test_governance_projection"
PROD_PROJECTION_TABLE = "governance_projection"


class _CfnTag:
    """Opaque marker for a CloudFormation intrinsic (e.g. ``!Ref``, ``!Sub``).

    Captures the tag name and its argument so a test can assert *which* intrinsic
    and *on what* without the loader choking on the custom tags.
    """

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


def _deploy_params(samconfig: dict, env: str) -> dict:
    return samconfig[env]["deploy"]["parameters"]


def _override_map(samconfig: dict, env: str) -> dict:
    """Return the `parameter_overrides` of a config-env as a {key: value} dict."""
    overrides = _deploy_params(samconfig, env)["parameter_overrides"]
    out = {}
    for item in overrides:
        key, _, value = item.partition("=")
        out[key] = value
    return out


# -----------------------------------------------------------------------------
# Single-knob invariant: Stage carries APP_ENV
# -----------------------------------------------------------------------------


def test_stage_parameter_allows_local_test_prod(template):
    """Stage is the single env knob and must allow local, test, and prod."""
    allowed = template["Parameters"]["Stage"]["AllowedValues"]
    assert allowed == ["local", "test", "prod"]


def test_stage_to_app_env_mapping_is_correct(template):
    """local/test resolve to APP_ENV=test; only prod is production (no drift)."""
    mapping = template["Mappings"]["StageToAppEnv"]
    assert mapping["local"]["AppEnv"] == "test"
    assert mapping["test"]["AppEnv"] == "test"
    assert mapping["prod"]["AppEnv"] == "production"


def test_app_env_is_derived_from_stage_via_findinmap(template):
    """The Lambda's APP_ENV is !FindInMap[StageToAppEnv, Stage, AppEnv]."""
    env_vars = template["Resources"]["MembersFunction"]["Properties"]["Environment"][
        "Variables"
    ]
    app_env = env_vars["APP_ENV"]
    assert isinstance(app_env, _CfnTag)
    assert app_env.tag == "FindInMap"
    # [MapName, TopLevelKey, SecondLevelKey]
    assert app_env.value[0] == "StageToAppEnv"
    assert isinstance(app_env.value[1], _CfnTag) and app_env.value[1].tag == "Ref"
    assert app_env.value[1].value == "Stage"
    assert app_env.value[2] == "AppEnv"


def test_members_table_pattern_accepts_test_prefix(template):
    """The members table pattern must accept both sam-members* and test_sam-members*."""
    pattern = template["Parameters"]["MembersTableName"]["AllowedPattern"]
    import re

    assert re.match(pattern, PROD_MEMBERS_TABLE)
    assert re.match(pattern, TEST_MEMBERS_TABLE)
    # A foreign table must NOT match (no accidental widening).
    assert not re.match(pattern, "governance_projection")


# -----------------------------------------------------------------------------
# Task 21 — environment-scoped execution role (no wildcard tables)
# -----------------------------------------------------------------------------


def _iam_statements(template) -> list:
    policies = template["Resources"]["MembersFunction"]["Properties"]["Policies"]
    assert len(policies) == 1, "expected a single inline policy document"
    return policies[0]["Statement"]


def test_iam_scopes_to_table_name_parameters_only(template):
    """Every DynamoDB resource ARN is built from the table-name PARAMETERS.

    The Lambda role therefore follows whatever table names the active config-env
    supplies (test_* for TEST, unprefixed for PROD). There is no `table/*`
    wildcard and no cross-account ARN, so a TEST deploy cannot reach PROD tables.
    """
    referenced_params = set()
    for stmt in _iam_statements(template):
        resources = stmt["Resource"]
        if not isinstance(resources, list):
            resources = [resources]
        for res in resources:
            assert isinstance(res, _CfnTag) and res.tag == "Sub", (
                "every DynamoDB resource ARN must be a !Sub on a table-name param"
            )
            sub = res.value
            # Reject a bare `table/*` wildcard.
            assert "table/*" not in sub, "wildcard table ARN would break env isolation"
            # Pin to this account + region, never cross-account.
            assert "${AWS::AccountId}" in sub
            assert "${Region}" in sub
            if "${MembersTableName}" in sub:
                referenced_params.add("MembersTableName")
            if "${GovernanceProjectionTableName}" in sub:
                referenced_params.add("GovernanceProjectionTableName")
    # Both tables (and ONLY those two) are referenced.
    assert referenced_params == {"MembersTableName", "GovernanceProjectionTableName"}


def test_governance_projection_access_is_read_only(template):
    """The projection is a one-way read; the role must not grant writes to it."""
    write_actions = {
        "dynamodb:PutItem",
        "dynamodb:UpdateItem",
        "dynamodb:DeleteItem",
        "dynamodb:BatchWriteItem",
    }
    for stmt in _iam_statements(template):
        resources = stmt["Resource"]
        if not isinstance(resources, list):
            resources = [resources]
        touches_projection = any(
            isinstance(r, _CfnTag) and "${GovernanceProjectionTableName}" in r.value
            for r in resources
        )
        if touches_projection:
            assert not (set(stmt["Action"]) & write_actions), (
                "projection access must be read-only (Query/GetItem)"
            )


# -----------------------------------------------------------------------------
# Task 22 — the stack owns its own API Gateway (distinct per environment)
# -----------------------------------------------------------------------------


def test_template_declares_its_own_api_gateway(template):
    """Each stack declares an AWS::Serverless::Api, so TEST and PROD each get one."""
    api = template["Resources"]["MembersApi"]
    assert api["Type"] == "AWS::Serverless::Api"
    # The stage name (and hence the invoke URL path) is the Stage knob.
    stage_name = api["Properties"]["StageName"]
    assert isinstance(stage_name, _CfnTag) and stage_name.tag == "Ref"
    assert stage_name.value == "Stage"


def test_api_base_url_output_is_stage_scoped(template):
    """The output invoke URL embeds the API id + Stage, so it differs per env."""
    out = template["Outputs"]["MembersApiBaseUrl"]["Value"]
    assert isinstance(out, _CfnTag) and out.tag == "Sub"
    assert "${MembersApi}" in out.value
    assert "${Stage}" in out.value


# -----------------------------------------------------------------------------
# Task 23 — per-environment Cognito authorizer
# -----------------------------------------------------------------------------


def test_authorizer_pool_is_a_parameter(template):
    """The authorizer validates against the CognitoUserPoolArn parameter."""
    auth = template["Resources"]["MembersApi"]["Properties"]["Auth"]
    assert auth["DefaultAuthorizer"] == "CognitoAuthorizer"
    pool_arn = auth["Authorizers"]["CognitoAuthorizer"]["UserPoolArn"]
    assert isinstance(pool_arn, _CfnTag) and pool_arn.tag == "Ref"
    assert pool_arn.value == "CognitoUserPoolArn"


# -----------------------------------------------------------------------------
# samconfig: the per-environment values that make the stacks disjoint
# -----------------------------------------------------------------------------


def test_test_and_prod_are_distinct_stacks(samconfig):
    """TEST and PROD deploy to different CloudFormation stacks (distinct APIs)."""
    assert _deploy_params(samconfig, "test")["stack_name"] == "test-sam-members"
    assert _deploy_params(samconfig, "prod")["stack_name"] == "sam-members"


def test_test_config_env_is_fully_test_scoped(samconfig):
    """[test] carries Stage=test, test pool, and test_-prefixed tables."""
    o = _override_map(samconfig, "test")
    assert o["Stage"] == "test"
    assert o["MembersTableName"] == TEST_MEMBERS_TABLE
    assert o["GovernanceProjectionTableName"] == TEST_PROJECTION_TABLE
    assert TEST_POOL_ID in o["CognitoUserPoolArn"]
    assert o["MyAdminCognitoPoolLabel"] == "myAdmin-test"


def test_prod_config_env_is_fully_prod_scoped(samconfig):
    """[prod] carries Stage=prod, prod pool, and unprefixed tables."""
    o = _override_map(samconfig, "prod")
    assert o["Stage"] == "prod"
    assert o["MembersTableName"] == PROD_MEMBERS_TABLE
    assert o["GovernanceProjectionTableName"] == PROD_PROJECTION_TABLE
    assert PROD_POOL_ID in o["CognitoUserPoolArn"]
    assert o["MyAdminCognitoPoolLabel"] == "myAdmin"


def test_test_and_prod_do_not_share_any_table(samconfig):
    """No DynamoDB table is shared across environments (user decision)."""
    test_o = _override_map(samconfig, "test")
    prod_o = _override_map(samconfig, "prod")
    assert test_o["MembersTableName"] != prod_o["MembersTableName"]
    assert (
        test_o["GovernanceProjectionTableName"]
        != prod_o["GovernanceProjectionTableName"]
    )


def test_test_and_prod_use_different_pools(samconfig):
    """The authorizer pool differs between TEST and PROD."""
    test_o = _override_map(samconfig, "test")
    prod_o = _override_map(samconfig, "prod")
    assert test_o["CognitoUserPoolArn"] != prod_o["CognitoUserPoolArn"]
    assert TEST_POOL_ID in test_o["CognitoUserPoolArn"]
    assert PROD_POOL_ID in prod_o["CognitoUserPoolArn"]
