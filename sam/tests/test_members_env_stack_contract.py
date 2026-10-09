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


def _is_dynamodb_statement(stmt: dict) -> bool:
    """True when a policy statement grants ONLY DynamoDB actions.

    The role also carries non-DynamoDB send-path grants (SES `identity/<addr>` ARN,
    task 0.5; SQS `!GetAtt MailSendQueue.Arn`, task 4.2) whose Resources are
    legitimately NOT `!Sub`-on-table-name — they are scoped by their own service's
    exact-ARN discipline. This test's real intent is the DynamoDB-table isolation
    guarantee, so it scopes to the DynamoDB statements only.
    """
    actions = stmt["Action"]
    if not isinstance(actions, list):
        actions = [actions]
    return bool(actions) and all(a.startswith("dynamodb:") for a in actions)


def test_iam_scopes_to_table_name_parameters_only(template):
    """Every DynamoDB resource ARN is built from the table-name PARAMETERS.

    The Lambda role therefore follows whatever table names the active config-env
    supplies (test_* for TEST, unprefixed for PROD). There is no `table/*`
    wildcard and no cross-account ARN, so a TEST deploy cannot reach PROD tables.

    Scoped to the DynamoDB statements (the `MembersReadGovernanceProjection` +
    `MembersCrudMembersTable` SIDs). The role's SES/SQS send-path statements use
    their own service's exact-ARN scoping (an SES `identity/<address>` ARN and the
    `!GetAtt MailSendQueue.Arn`), which are legitimately not `!Sub`-on-table-name —
    they are covered by their own grants' least-privilege scoping, not this
    table-isolation check.
    """
    dynamodb_statements = [
        s for s in _iam_statements(template) if _is_dynamodb_statement(s)
    ]
    assert dynamodb_statements, "expected at least one DynamoDB-scoped IAM statement"

    referenced_params = set()
    for stmt in dynamodb_statements:
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
# Task 4.4 (pivot-output-actions, R4) — the mail-send worker: the queue CONSUMER
# -----------------------------------------------------------------------------
# The worker Lambda (`MailWorkerFunction`) drains `MailSendQueue` → SES. Its role is
# DISTINCT from the producer edge's (`MembersFunction`): it CONSUMES the queue (never
# SendMessage), SENDS via SES (it is the SES caller), and READS the DynamoDB tables it
# renders/audits from. These assertions pin that CONSUMER-side wiring so the template and
# the worker role cannot drift — same exact-ARN table-isolation guarantee the edge has,
# plus the bounded-concurrency drain under the SES rate.


def _actions_list(stmt: dict) -> list:
    actions = stmt["Action"]
    return actions if isinstance(actions, list) else [actions]


def _worker_statements(template) -> list:
    policies = template["Resources"]["MailWorkerFunction"]["Properties"]["Policies"]
    assert len(policies) == 1, "expected a single inline policy document on the worker"
    return policies[0]["Statement"]


def _worker_resources(stmt: dict) -> list:
    resources = stmt["Resource"]
    return resources if isinstance(resources, list) else [resources]


def test_worker_function_is_named_per_stage(template):
    """The worker follows the `members-<thing>-${Stage}` per-env naming precedent."""
    fn = template["Resources"]["MailWorkerFunction"]
    assert fn["Type"] == "AWS::Serverless::Function"
    name = fn["Properties"]["FunctionName"]
    assert isinstance(name, _CfnTag) and name.tag == "Sub"
    assert name.value == "members-mail-worker-${Stage}"


def test_worker_reuses_the_members_layer(template):
    """The worker reuses the single vendored MembersLayer (no second layer)."""
    layers = template["Resources"]["MailWorkerFunction"]["Properties"]["Layers"]
    assert len(layers) == 1
    assert isinstance(layers[0], _CfnTag) and layers[0].tag == "Ref"
    assert layers[0].value == "MembersLayer"


def test_worker_app_env_is_derived_from_stage(template):
    """The worker's APP_ENV is !FindInMap[StageToAppEnv, Stage, AppEnv] — no drift."""
    env_vars = template["Resources"]["MailWorkerFunction"]["Properties"]["Environment"][
        "Variables"
    ]
    app_env = env_vars["APP_ENV"]
    assert isinstance(app_env, _CfnTag) and app_env.tag == "FindInMap"
    assert app_env.value[0] == "StageToAppEnv"
    assert isinstance(app_env.value[1], _CfnTag) and app_env.value[1].value == "Stage"
    assert app_env.value[2] == "AppEnv"


def test_worker_dynamodb_resources_scope_to_table_name_params_only(template):
    """The worker's DynamoDB ARNs are !Sub-on-table-name — no wildcard, no cross-account.

    The same env-isolation guarantee the edge has: a TEST worker (resolved to `test_*`
    tables) can never reach the unprefixed PROD tables. SES/SQS statements use their own
    service's exact-ARN scoping, so this check is scoped to the DynamoDB statements.
    """
    dynamodb_statements = [
        s for s in _worker_statements(template) if _is_dynamodb_statement(s)
    ]
    assert dynamodb_statements, "expected worker DynamoDB-scoped IAM statement(s)"

    referenced_params = set()
    for stmt in dynamodb_statements:
        for res in _worker_resources(stmt):
            assert isinstance(res, _CfnTag) and res.tag == "Sub", (
                "every worker DynamoDB resource ARN must be a !Sub on a table-name param"
            )
            sub = res.value
            assert "table/*" not in sub, "wildcard table ARN would break env isolation"
            assert "${AWS::AccountId}" in sub
            assert "${Region}" in sub
            if "${MembersTableName}" in sub:
                referenced_params.add("MembersTableName")
            if "${GovernanceProjectionTableName}" in sub:
                referenced_params.add("GovernanceProjectionTableName")
    assert referenced_params == {"MembersTableName", "GovernanceProjectionTableName"}


def test_worker_projection_access_is_read_only(template):
    """The worker reads the projection one-way too; no writes to it."""
    write_actions = {
        "dynamodb:PutItem",
        "dynamodb:UpdateItem",
        "dynamodb:DeleteItem",
        "dynamodb:BatchWriteItem",
    }
    for stmt in _worker_statements(template):
        touches_projection = any(
            isinstance(r, _CfnTag) and "${GovernanceProjectionTableName}" in r.value
            for r in _worker_resources(stmt)
        )
        if touches_projection:
            assert not (set(_actions_list(stmt)) & write_actions), (
                "worker projection access must be read-only (Query/GetItem)"
            )


def test_worker_consumes_queue_but_never_sends(template):
    """The worker's SQS grant is Receive/Delete/GetQueueAttributes on the EXACT queue ARN.

    This is the CONSUMER grant — distinct from the producer's SendMessage. The worker must
    NOT be able to enqueue (no sqs:SendMessage anywhere in its role), and the DLQ redrive is
    handled by the queue's RedrivePolicy, not a worker grant.
    """
    sqs_statements = [
        s
        for s in _worker_statements(template)
        if any(a.startswith("sqs:") for a in _actions_list(s))
    ]
    assert len(sqs_statements) == 1, "expected exactly one SQS statement on the worker"
    stmt = sqs_statements[0]
    actions = set(_actions_list(stmt))
    assert actions == {
        "sqs:ReceiveMessage",
        "sqs:DeleteMessage",
        "sqs:GetQueueAttributes",
    }
    assert "sqs:SendMessage" not in actions, "the worker must never enqueue"
    # Scoped to the exact MailSendQueue ARN via !GetAtt (not a wildcard, not the DLQ).
    resources = _worker_resources(stmt)
    assert len(resources) == 1
    res = resources[0]
    assert isinstance(res, _CfnTag) and res.tag == "GetAtt"
    assert res.value in ("MailSendQueue.Arn", ["MailSendQueue", "Arn"])


def _ses_send_statement(statements: list) -> dict:
    """Return the single SES send statement from a role's statement list."""
    ses_statements = [
        s for s in statements if any(a.startswith("ses:") for a in _actions_list(s))
    ]
    assert len(ses_statements) == 1, "expected exactly one SES send statement on the role"
    return ses_statements[0]


def _assert_ses_scoped_to_tenant_domain(stmt: dict) -> None:
    """Assert an SES send statement is scoped to the verified tenant DOMAIN identity + noreply@.

    The per-tenant sender model (mail-spec R4.1/R4.2, task 4.2 — NO `jabaki.nl` substitute):
    the From is `noreply@<tenant-domain>`, so the grant must be scoped to the verified tenant
    DOMAIN identity (`identity/<domain>`, which SES authorizes `*@<domain>` against) and the
    `ses:FromAddress` Condition must pin exactly `noreply@<domain>`. It must NOT be scoped to a
    single hardcoded address identity (the removed `support@jabaki.nl` assumption), and never a
    wildcard identity.
    """
    assert set(_actions_list(stmt)) == {"ses:SendEmail", "ses:SendRawEmail"}
    assert "ses:SendBulkEmail" not in _actions_list(stmt)  # least privilege (no bulk)
    # Resource = the verified tenant DOMAIN-identity ARN (from MailSenderDomain), not an address.
    resources = stmt["Resource"]
    if not isinstance(resources, list):
        resources = [resources]
    assert len(resources) == 1
    res = resources[0]
    assert isinstance(res, _CfnTag) and res.tag == "Sub"
    assert "identity/${MailSenderDomain}" in res.value
    assert "identity/*" not in res.value, "a wildcard identity would re-open the foreign-sender risk"
    # Regression guard (R4.2): the old single-address jabaki.nl assumption must be gone.
    assert "SesSenderEmail" not in res.value
    assert "jabaki" not in res.value
    # Condition pins ses:FromAddress to EXACTLY noreply@<domain> (the fixed-generic R4.1 sender).
    from_addr = stmt["Condition"]["StringEquals"]["ses:FromAddress"]
    assert isinstance(from_addr, _CfnTag) and from_addr.tag == "Sub"
    assert from_addr.value == "noreply@${MailSenderDomain}"


def test_edge_ses_send_is_scoped_to_the_tenant_domain(template):
    """The edge (producer) SES grant sends as the per-tenant noreply@<tenant-domain>, not jabaki.nl."""
    _assert_ses_scoped_to_tenant_domain(_ses_send_statement(_iam_statements(template)))


def test_worker_ses_send_is_scoped_to_the_tenant_domain(template):
    """The worker's SES grant mirrors the edge: send-only, scoped to the verified tenant domain."""
    _assert_ses_scoped_to_tenant_domain(_ses_send_statement(_worker_statements(template)))


def test_no_jabaki_substitute_sender_in_the_stack(template, samconfig):
    """R4.2 regression guard: no `SesSenderEmail` param / `SES_SENDER_EMAIL` env / jabaki sender.

    The per-tenant model composes `noreply@<tenant-domain>` at send time; the single global
    sender (and the `support@jabaki.nl` substitute it carried) must be absent from both the
    template parameters/env and the samconfig overrides.
    """
    assert "SesSenderEmail" not in template["Parameters"], "the single-address sender param is removed"
    assert "MailSenderDomain" in template["Parameters"], "the per-tenant domain param replaces it"
    # No Lambda injects the dead SES_SENDER_EMAIL env var any more.
    for fn in ("MembersFunction", "MailWorkerFunction"):
        env = template["Resources"][fn]["Properties"]["Environment"]["Variables"]
        assert "SES_SENDER_EMAIL" not in env, f"{fn} must not inject the dead SES_SENDER_EMAIL"
    # samconfig supplies the verified tenant domain, not a jabaki address.
    for env_name in ("test", "prod"):
        overrides = _override_map(samconfig, env_name)
        assert "SesSenderEmail" not in overrides
        assert overrides.get("MailSenderDomain", "").strip() != ""
        assert "jabaki" not in overrides.get("MailSenderDomain", "")


def test_worker_event_source_drains_queue_with_bounded_concurrency(template):
    """The worker consumes MailSendQueue with a BOUNDED MaximumConcurrency (SES rate)."""
    events = template["Resources"]["MailWorkerFunction"]["Properties"]["Events"]
    sqs_events = [e for e in events.values() if e["Type"] == "SQS"]
    assert len(sqs_events) == 1, "expected one SQS event source on the worker"
    props = sqs_events[0]["Properties"]
    queue = props["Queue"]
    assert isinstance(queue, _CfnTag) and queue.tag == "GetAtt"
    assert queue.value in ("MailSendQueue.Arn", ["MailSendQueue", "Arn"])
    # Bounded drain: MaximumConcurrency is the per-env MailWorkerMaxConcurrency parameter.
    max_conc = props["ScalingConfig"]["MaximumConcurrency"]
    assert isinstance(max_conc, _CfnTag) and max_conc.tag == "Ref"
    assert max_conc.value == "MailWorkerMaxConcurrency"


def test_worker_concurrency_param_is_bounded_and_per_env(template, samconfig):
    """MailWorkerMaxConcurrency is a bounded Number param, set per env in samconfig."""
    param = template["Parameters"]["MailWorkerMaxConcurrency"]
    assert param["Type"] == "Number"
    assert param["MinValue"] >= 2  # the SQS MaximumConcurrency floor
    # Per-env values: TEST drains slower than PROD (shared SES budget).
    test_conc = int(_override_map(samconfig, "test")["MailWorkerMaxConcurrency"])
    prod_conc = int(_override_map(samconfig, "prod")["MailWorkerMaxConcurrency"])
    assert param["MinValue"] <= test_conc <= param["MaxValue"]
    assert param["MinValue"] <= prod_conc <= param["MaxValue"]
    assert test_conc <= prod_conc


# -----------------------------------------------------------------------------
# Task 5.3 (pivot-output-actions, R5) — EventBridge Scheduler plumbing
# -----------------------------------------------------------------------------
# Schedules are DYNAMIC (one EventBridge schedule per `schedule#<id>` record, created at
# runtime by task 5.2 via the Scheduler API) — so the template declares only the FIXED
# plumbing: the schedule-group, the dedicated trigger Lambda EventBridge invokes, the role
# EventBridge Scheduler assumes to invoke it, and the Members function's scheduler:* +
# iam:PassRole grant scoped to EXACTLY that group + role. These assertions pin that static
# wiring so the template and the scheduler-API port cannot drift — same exact-ARN discipline
# the edge/worker have (steering 23).


def _members_statements(template) -> list:
    """The MembersFunction inline policy statements (shared by the scheduler-grant tests)."""
    return _iam_statements(template)


def _statement_by_sid(statements: list, sid: str) -> dict:
    matches = [s for s in statements if s.get("Sid") == sid]
    assert len(matches) == 1, f"expected exactly one statement with Sid {sid!r}"
    return matches[0]


def test_schedule_group_is_named_per_env(template):
    """The schedule-group is an AWS::Scheduler::ScheduleGroup named by the per-env param."""
    group = template["Resources"]["MembersScheduleGroup"]
    assert group["Type"] == "AWS::Scheduler::ScheduleGroup"
    name = group["Properties"]["Name"]
    assert isinstance(name, _CfnTag) and name.tag == "Ref"
    assert name.value == "SchedulerGroupName"


def test_scheduler_group_name_param_is_bounded_and_per_env(template, samconfig):
    """SchedulerGroupName is pattern-bounded and set per env (members-schedules[-test])."""
    import re

    param = template["Parameters"]["SchedulerGroupName"]
    pattern = param["AllowedPattern"]
    assert re.match(pattern, "members-schedules")
    assert re.match(pattern, "members-schedules-test")
    assert not re.match(pattern, "something-else")
    assert "Default" not in param, "no default — fail-fast per steering 23"
    test_group = _override_map(samconfig, "test")["SchedulerGroupName"]
    prod_group = _override_map(samconfig, "prod")["SchedulerGroupName"]
    assert test_group == "members-schedules-test"
    assert prod_group == "members-schedules"


def test_scheduler_trigger_function_is_named_per_stage(template):
    """The scheduler-trigger follows the `members-<thing>-${Stage}` per-env naming precedent."""
    fn = template["Resources"]["MembersSchedulerTriggerFunction"]
    assert fn["Type"] == "AWS::Serverless::Function"
    name = fn["Properties"]["FunctionName"]
    assert isinstance(name, _CfnTag) and name.tag == "Sub"
    assert name.value == "members-scheduler-trigger-${Stage}"


def test_scheduler_trigger_reuses_the_members_layer(template):
    """The trigger reuses the single vendored MembersLayer (no second layer)."""
    layers = template["Resources"]["MembersSchedulerTriggerFunction"]["Properties"][
        "Layers"
    ]
    assert len(layers) == 1
    assert isinstance(layers[0], _CfnTag) and layers[0].tag == "Ref"
    assert layers[0].value == "MembersLayer"


def test_scheduler_trigger_handler_points_at_the_dedicated_entrypoint(template):
    """The trigger's Handler is the dedicated scheduler_app entrypoint (distinct event shape)."""
    handler = template["Resources"]["MembersSchedulerTriggerFunction"]["Properties"][
        "Handler"
    ]
    assert handler == "sam.members.handler.scheduler_app.handler"


def _trigger_statements(template) -> list:
    policies = template["Resources"]["MembersSchedulerTriggerFunction"]["Properties"][
        "Policies"
    ]
    assert len(policies) == 1, "expected a single inline policy on the trigger"
    return policies[0]["Statement"]


def test_scheduler_trigger_is_producer_only(template):
    """The trigger ENQUEUES (SendMessage on the exact queue) and never consumes / sends SES.

    It reuses the deliver path (resolve set + rows, enqueue) so it is a PRODUCER like the HTTP
    edge: DynamoDB read on the members table + SQS SendMessage on the exact queue ARN. It must
    NOT send via SES (the worker does) and must NOT manage schedules (the HTTP edge does).
    """
    statements = _trigger_statements(template)
    actions = {a for s in statements for a in _actions_list(s)}
    # Producer SQS: SendMessage only, never Receive/Delete.
    assert "sqs:SendMessage" in actions
    assert "sqs:ReceiveMessage" not in actions
    assert "sqs:DeleteMessage" not in actions
    # No SES on the trigger (the worker is the SES caller).
    assert not any(a.startswith("ses:") for a in actions)
    # No scheduler management on the trigger (the HTTP edge's task-5.2 path manages schedules).
    assert not any(a.startswith("scheduler:") for a in actions)
    assert "iam:PassRole" not in actions

    sqs_stmt = _statement_by_sid(statements, "SchedulerTriggerEnqueueMailSend")
    res = _worker_resources(sqs_stmt)[0]
    assert isinstance(res, _CfnTag) and res.tag == "GetAtt"
    assert res.value in ("MailSendQueue.Arn", ["MailSendQueue", "Arn"])


def test_scheduler_trigger_dynamodb_scopes_to_table_name_param(template):
    """The trigger's DynamoDB ARNs are !Sub-on-table-name — same env-isolation guarantee."""
    dynamodb_statements = [
        s for s in _trigger_statements(template) if _is_dynamodb_statement(s)
    ]
    assert dynamodb_statements, "expected a trigger DynamoDB-scoped statement"
    for stmt in dynamodb_statements:
        for res in _worker_resources(stmt):
            assert isinstance(res, _CfnTag) and res.tag == "Sub"
            assert "table/*" not in res.value
            assert "${AWS::AccountId}" in res.value
            assert "${Region}" in res.value
            assert "${MembersTableName}" in res.value


def test_scheduler_execution_role_trusts_only_the_scheduler_service(template):
    """The execution role is assumable ONLY by scheduler.amazonaws.com, SourceAccount-guarded."""
    role = template["Resources"]["MembersSchedulerExecutionRole"]
    assert role["Type"] == "AWS::IAM::Role"
    trust = role["Properties"]["AssumeRolePolicyDocument"]["Statement"]
    assert len(trust) == 1
    stmt = trust[0]
    assert stmt["Effect"] == "Allow"
    assert stmt["Principal"]["Service"] == "scheduler.amazonaws.com"
    assert stmt["Action"] == "sts:AssumeRole"
    # Confused-deputy guard: only THIS account's scheduler may assume it.
    source_account = stmt["Condition"]["StringEquals"]["aws:SourceAccount"]
    assert isinstance(source_account, _CfnTag) and source_account.tag == "Ref"
    assert source_account.value == "AWS::AccountId"


def test_scheduler_execution_role_invokes_only_the_trigger(template):
    """The execution role may ONLY lambda:InvokeFunction the exact trigger ARN (no wildcard)."""
    policies = template["Resources"]["MembersSchedulerExecutionRole"]["Properties"][
        "Policies"
    ]
    assert len(policies) == 1
    statements = policies[0]["PolicyDocument"]["Statement"]
    assert len(statements) == 1
    stmt = statements[0]
    assert set(_actions_list(stmt)) == {"lambda:InvokeFunction"}
    res = _worker_resources(stmt)[0]
    assert isinstance(res, _CfnTag) and res.tag == "GetAtt"
    assert res.value in (
        "MembersSchedulerTriggerFunction.Arn",
        ["MembersSchedulerTriggerFunction", "Arn"],
    )


def test_members_function_manages_schedules_scoped_to_the_group(template):
    """The Members function's scheduler:* grant is scoped to the group's schedule/<group>/* ARN."""
    stmt = _statement_by_sid(_members_statements(template), "MembersManageSchedules")
    actions = set(_actions_list(stmt))
    assert actions == {
        "scheduler:CreateSchedule",
        "scheduler:UpdateSchedule",
        "scheduler:DeleteSchedule",
        "scheduler:GetSchedule",
    }
    # No account-wide ListSchedules; the record store (DynamoDB) is the system of record.
    assert "scheduler:ListSchedules" not in actions
    res = stmt["Resource"]
    if isinstance(res, list):
        assert len(res) == 1
        res = res[0]
    assert isinstance(res, _CfnTag) and res.tag == "Sub"
    assert "schedule/${SchedulerGroupName}/*" in res.value
    assert "${AWS::AccountId}" in res.value
    assert "${Region}" in res.value


def test_members_function_passrole_is_scoped_to_exactly_the_execution_role(template):
    """iam:PassRole is scoped to EXACTLY the execution role ARN + the scheduler service."""
    stmt = _statement_by_sid(
        _members_statements(template), "MembersPassSchedulerExecutionRole"
    )
    assert set(_actions_list(stmt)) == {"iam:PassRole"}
    res = stmt["Resource"]
    if isinstance(res, list):
        assert len(res) == 1
        res = res[0]
    assert isinstance(res, _CfnTag) and res.tag == "GetAtt"
    assert res.value in (
        "MembersSchedulerExecutionRole.Arn",
        ["MembersSchedulerExecutionRole", "Arn"],
    )
    # Conditioned so the role can ONLY be passed to EventBridge Scheduler.
    passed_to = stmt["Condition"]["StringEquals"]["iam:PassedToService"]
    assert passed_to == "scheduler.amazonaws.com"


def test_members_function_wires_scheduler_env(template):
    """The Members function carries the scheduler port's three fail-fast env vars."""
    env_vars = template["Resources"]["MembersFunction"]["Properties"]["Environment"][
        "Variables"
    ]
    target = env_vars["SCHEDULER_TARGET_FUNCTION_ARN"]
    assert isinstance(target, _CfnTag) and target.tag == "GetAtt"
    assert target.value in (
        "MembersSchedulerTriggerFunction.Arn",
        ["MembersSchedulerTriggerFunction", "Arn"],
    )
    role = env_vars["SCHEDULER_EXECUTION_ROLE_ARN"]
    assert isinstance(role, _CfnTag) and role.tag == "GetAtt"
    assert role.value in (
        "MembersSchedulerExecutionRole.Arn",
        ["MembersSchedulerExecutionRole", "Arn"],
    )
    group = env_vars["SCHEDULER_GROUP_NAME"]
    assert isinstance(group, _CfnTag) and group.tag == "Ref"
    assert group.value == "SchedulerGroupName"


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


# -----------------------------------------------------------------------------
# Task 5.1 (mail spec, R8.4/R9.5) — SES configuration set -> SNS event destination
# -----------------------------------------------------------------------------
# POST-SEND outcome detection (R8.4): a message SES accepts can later bounce / be marked a
# complaint. That outcome is only observable via an SES CONFIGURATION SET whose EVENT
# DESTINATION publishes bounce/complaint/delivery events to a notification sink. The Members
# plane OWNS its own config set + SNS topic in nonprofit-deploy (R9.5, rule 5a) — distinct
# from the Flask `infrastructure/ses.tf` `myadmin-emails` set, which lives in the PERSONAL
# account. These assertions pin that wiring statically (deploy-free) so the template and the
# task-5.2 ingestion handler cannot drift:
#   * the config set the send-path attaches is the SAME set that owns the event destination;
#   * the event destination forwards exactly bounce/complaint/delivery to the SNS topic;
#   * the topic policy lets ONLY SES in THIS account publish (confused-deputy guarded);
#   * the topic ARN is a discoverable Output so task 5.2 can subscribe its handler;
#   * the config-set / topic names are per-env (members-emails[-test] / feedback[-test]).


def test_ses_configuration_set_name_is_the_attached_set(template):
    """The owned config set's Name == !Ref SesConfigurationSet (the value the sender attaches).

    "The set the sender attaches" (SES_CONFIGURATION_SET env var on both Lambdas) and "the set
    that owns the SNS event destination" MUST be the same set, or feedback silently never flows.
    """
    cfg = template["Resources"]["MembersSesConfigurationSet"]
    assert cfg["Type"] == "AWS::SES::ConfigurationSet"
    name = cfg["Properties"]["Name"]
    assert isinstance(name, _CfnTag) and name.tag == "Ref"
    assert name.value == "SesConfigurationSet"
    # Both Lambdas inject that SAME param as SES_CONFIGURATION_SET (sender attaches == owner).
    for fn in ("MembersFunction", "MailWorkerFunction"):
        env = template["Resources"][fn]["Properties"]["Environment"]["Variables"]
        cfg_env = env["SES_CONFIGURATION_SET"]
        assert isinstance(cfg_env, _CfnTag) and cfg_env.tag == "Ref"
        assert cfg_env.value == "SesConfigurationSet"


def test_ses_config_set_param_is_per_env_owned_not_the_flask_set(template, samconfig):
    """SesConfigurationSet is the per-env OWNED name (members-emails[-test]), not jabaki/myadmin.

    Regression guard: the Members plane owns its own set in nonprofit-deploy; it must NOT point
    at the Flask-side `myadmin-emails` (a different account) any more.
    """
    import re

    param = template["Parameters"]["SesConfigurationSet"]
    pattern = param["AllowedPattern"]
    assert re.match(pattern, "members-emails")
    assert re.match(pattern, "members-emails-test")
    assert not re.match(pattern, "myadmin-emails")
    assert "Default" not in param, "no default — fail-fast per steering 23"
    test_set = _override_map(samconfig, "test")["SesConfigurationSet"]
    prod_set = _override_map(samconfig, "prod")["SesConfigurationSet"]
    assert test_set == "members-emails-test"
    assert prod_set == "members-emails"
    for env_name in ("test", "prod"):
        assert "myadmin-emails" not in _override_map(samconfig, env_name)["SesConfigurationSet"]


def test_ses_event_destination_publishes_bounce_complaint_delivery_to_sns(template):
    """The event destination forwards exactly bounce/complaint/delivery to the feedback topic."""
    dest = template["Resources"]["MembersSesEventDestination"]
    assert dest["Type"] == "AWS::SES::ConfigurationSetEventDestination"
    props = dest["Properties"]
    # Attached to the SAME config set resource (not a dangling name string).
    cfg_name = props["ConfigurationSetName"]
    assert isinstance(cfg_name, _CfnTag) and cfg_name.tag == "Ref"
    assert cfg_name.value == "MembersSesConfigurationSet"
    event = props["EventDestination"]
    assert event["Enabled"] is True
    # Exactly the three POST-SEND outcome types the design (R8.4/R9.5) records — least surface.
    assert set(event["MatchingEventTypes"]) == {"bounce", "complaint", "delivery"}
    # Published to the Members feedback SNS topic (the account-level sink, R9.5).
    topic_arn = event["SnsDestination"]["TopicARN"]
    assert isinstance(topic_arn, _CfnTag) and topic_arn.tag == "Ref"
    assert topic_arn.value == "MembersMailFeedbackTopic"


def test_feedback_topic_is_named_per_env(template, samconfig):
    """The SNS feedback topic is named by the per-env MailFeedbackTopicName param (fail-fast)."""
    import re

    topic = template["Resources"]["MembersMailFeedbackTopic"]
    assert topic["Type"] == "AWS::SNS::Topic"
    name = topic["Properties"]["TopicName"]
    assert isinstance(name, _CfnTag) and name.tag == "Ref"
    assert name.value == "MailFeedbackTopicName"

    param = template["Parameters"]["MailFeedbackTopicName"]
    pattern = param["AllowedPattern"]
    assert re.match(pattern, "members-mail-feedback")
    assert re.match(pattern, "members-mail-feedback-test")
    assert not re.match(pattern, "something-else")
    assert "Default" not in param, "no default — fail-fast per steering 23"
    assert _override_map(samconfig, "test")["MailFeedbackTopicName"] == "members-mail-feedback-test"
    assert _override_map(samconfig, "prod")["MailFeedbackTopicName"] == "members-mail-feedback"


def test_feedback_topic_policy_allows_only_ses_in_this_account(template):
    """The topic policy grants sns:Publish to ONLY ses.amazonaws.com, SourceAccount-guarded."""
    policy = template["Resources"]["MembersMailFeedbackTopicPolicy"]
    assert policy["Type"] == "AWS::SNS::TopicPolicy"
    # Scoped to exactly the feedback topic.
    topics = policy["Properties"]["Topics"]
    assert len(topics) == 1
    assert isinstance(topics[0], _CfnTag) and topics[0].tag == "Ref"
    assert topics[0].value == "MembersMailFeedbackTopic"
    statements = policy["Properties"]["PolicyDocument"]["Statement"]
    assert len(statements) == 1
    stmt = statements[0]
    assert stmt["Effect"] == "Allow"
    assert stmt["Principal"]["Service"] == "ses.amazonaws.com"
    assert set(_actions_list(stmt)) == {"sns:Publish"}
    # Resource is the exact topic; publish is confined to the one topic.
    res = stmt["Resource"]
    assert isinstance(res, _CfnTag) and res.tag == "Ref"
    assert res.value == "MembersMailFeedbackTopic"
    # Confused-deputy guard: only THIS account's SES may publish.
    source_account = stmt["Condition"]["StringEquals"]["AWS:SourceAccount"]
    assert isinstance(source_account, _CfnTag) and source_account.tag == "Ref"
    assert source_account.value == "AWS::AccountId"


def test_feedback_topic_arn_is_a_discoverable_output(template):
    """The feedback topic ARN is an Output so the task-5.2 handler can subscribe to it."""
    out = template["Outputs"]["MailFeedbackTopicArn"]["Value"]
    assert isinstance(out, _CfnTag) and out.tag == "Ref"
    assert out.value == "MembersMailFeedbackTopic"
    # The owned config-set name is also surfaced for operator/handler discovery.
    cfg_out = template["Outputs"]["SesConfigurationSetName"]["Value"]
    assert isinstance(cfg_out, _CfnTag) and cfg_out.tag == "Ref"
    assert cfg_out.value == "MembersSesConfigurationSet"


# -----------------------------------------------------------------------------
# Task 5.2 (pivot-output-actions mail, R8.4/R9.5) — the SES-feedback ingestion Lambda
# -----------------------------------------------------------------------------
# The CONSUMER of the SES -> SNS feedback pipeline task 5.1 wired: MailFeedbackFunction is
# SUBSCRIBED to MembersMailFeedbackTopic (the subscription task 5.1 explicitly left to 5.2) and
# routes each bounce/complaint/delivery back to the Members store by the stamped ms_tenant/ms_run
# message tags (R9.5). Its role is DISTINCT + least-privilege: it WRITES the mailrun/mailrecipient
# status records on the members table (and reads them to compute the tally delta), and does NOT
# send SES, touch SQS, read the projection, or manage schedules. These assertions pin that wiring.


def _feedback_statements(template) -> list:
    policies = template["Resources"]["MailFeedbackFunction"]["Properties"]["Policies"]
    assert len(policies) == 1, "expected a single inline policy on the feedback function"
    return policies[0]["Statement"]


def test_feedback_function_is_named_per_stage(template):
    """The ingestion Lambda follows the `members-<thing>-${Stage}` per-env naming precedent."""
    fn = template["Resources"]["MailFeedbackFunction"]
    assert fn["Type"] == "AWS::Serverless::Function"
    name = fn["Properties"]["FunctionName"]
    assert isinstance(name, _CfnTag) and name.tag == "Sub"
    assert name.value == "members-mail-feedback-${Stage}"


def test_feedback_function_reuses_the_members_layer(template):
    """The ingestion Lambda reuses the single vendored MembersLayer (no second layer)."""
    layers = template["Resources"]["MailFeedbackFunction"]["Properties"]["Layers"]
    assert len(layers) == 1
    assert isinstance(layers[0], _CfnTag) and layers[0].tag == "Ref"
    assert layers[0].value == "MembersLayer"


def test_feedback_function_handler_points_at_the_ingestion_entrypoint(template):
    """The Handler is the dedicated task-5.2 SNS ingestion entrypoint."""
    handler = template["Resources"]["MailFeedbackFunction"]["Properties"]["Handler"]
    assert handler == "sam.members.worker.mail_feedback_app.handler"


def test_feedback_function_app_env_is_derived_from_stage(template):
    """APP_ENV is !FindInMap[StageToAppEnv, Stage, AppEnv] — no drift from the edge/worker."""
    env_vars = template["Resources"]["MailFeedbackFunction"]["Properties"]["Environment"][
        "Variables"
    ]
    app_env = env_vars["APP_ENV"]
    assert isinstance(app_env, _CfnTag) and app_env.tag == "FindInMap"
    assert app_env.value[0] == "StageToAppEnv"
    assert isinstance(app_env.value[1], _CfnTag) and app_env.value[1].value == "Stage"
    assert app_env.value[2] == "AppEnv"


def test_feedback_function_subscribes_to_the_feedback_topic(template):
    """The ingestion Lambda has an SNS event source on exactly the task-5.1 feedback topic.

    SAM turns this into the AWS::SNS::Subscription (+ SNS invoke permission) task 5.1 deferred to
    5.2 — the only consumer wired to MembersMailFeedbackTopic.
    """
    events = template["Resources"]["MailFeedbackFunction"]["Properties"]["Events"]
    sns_events = [e for e in events.values() if e["Type"] == "SNS"]
    assert len(sns_events) == 1, "expected exactly one SNS event source on the ingestion Lambda"
    topic = sns_events[0]["Properties"]["Topic"]
    assert isinstance(topic, _CfnTag) and topic.tag == "Ref"
    assert topic.value == "MembersMailFeedbackTopic"


def test_feedback_function_writes_status_records_scoped_to_the_members_table(template):
    """The ingestion role's DynamoDB ARNs are !Sub-on-members-table — no wildcard, no cross-account.

    It needs read+write ONLY on the members table (the mailrun#/mailrecipient# records): GetItem +
    Query (the tally / existing failures) and PutItem/UpdateItem (the new sub-record + adjusted
    tally). Same env-isolation guarantee the edge/worker have.
    """
    dynamodb_statements = [
        s for s in _feedback_statements(template) if _is_dynamodb_statement(s)
    ]
    assert dynamodb_statements, "expected feedback DynamoDB-scoped IAM statement(s)"

    referenced_params = set()
    for stmt in dynamodb_statements:
        for res in _worker_resources(stmt):
            assert isinstance(res, _CfnTag) and res.tag == "Sub", (
                "every feedback DynamoDB resource ARN must be a !Sub on a table-name param"
            )
            sub = res.value
            assert "table/*" not in sub, "wildcard table ARN would break env isolation"
            assert "${AWS::AccountId}" in sub
            assert "${Region}" in sub
            if "${MembersTableName}" in sub:
                referenced_params.add("MembersTableName")
            if "${GovernanceProjectionTableName}" in sub:
                referenced_params.add("GovernanceProjectionTableName")
    # ONLY the members table — the ingestion path reads tenant/run from the SES tag, not the
    # projection, so the projection must NOT be in its grant (least privilege).
    assert referenced_params == {"MembersTableName"}


def test_feedback_function_has_no_ses_sqs_or_scheduler_grants(template):
    """Least privilege: the ingestion role sends no SES, touches no SQS, manages no schedules."""
    actions = {a for s in _feedback_statements(template) for a in _actions_list(s)}
    assert not any(a.startswith("ses:") for a in actions), "ingestion must not send SES"
    assert not any(a.startswith("sqs:") for a in actions), "ingestion must not touch SQS"
    assert not any(a.startswith("scheduler:") for a in actions), "ingestion manages no schedules"
    assert "iam:PassRole" not in actions
    # And it never writes to (or reads) the projection.
    for stmt in _feedback_statements(template):
        for res in _worker_resources(stmt):
            if isinstance(res, _CfnTag):
                assert "${GovernanceProjectionTableName}" not in res.value


def test_feedback_function_arn_is_a_discoverable_output(template):
    """The ingestion Lambda ARN is surfaced as an Output (operator discovery)."""
    out = template["Outputs"]["MailFeedbackFunctionArn"]["Value"]
    assert isinstance(out, _CfnTag) and out.tag == "GetAtt"
    assert out.value in ("MailFeedbackFunction.Arn", ["MailFeedbackFunction", "Arn"])
