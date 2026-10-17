"""
Template-contract tests for the public application-intake edge's ABUSE HARDENING + IAM
(application-app Task 7.1; R10.1, R10.4, R10.5, D17, D27; design §13/§11a row (a)/(e)).

Task 1.3 wired the SEPARATE public API + public Lambda (route/CORS only — asserted in
``test_public_api_stack_contract.py``) and DEFERRED the least-privilege IAM + the API Gateway
throttle/usage plan to THIS task. These assert that deferred wiring STATICALLY against
``sam/members/template.yaml`` + ``sam/members/samconfig.toml`` (the wiring IS the control — no
live AWS deploy).

Covered:
  * R10.1 / D17 — the public API carries an API Gateway stage THROTTLE (rate + burst) AND a
    USAGE PLAN bound to its stage; both from per-env params, supplied per env in samconfig.
  * R10.4 / D17 — NO WAF: the template provisions no ``AWS::WAFv2`` / WebACL association on the
    public surface (the abuse controls are the throttle + the handler's honeypot/payload cap +
    the fail-closed CORS — a WAF is the deferred "easy add-on").
  * R10.5 — the public fn's IAM is EXACTLY the three scoped grants (members-table write,
    projection READ, queue enqueue), each on an EXACT ARN — no wildcard table, no cross-account,
    no stray action (no DeleteItem, no SES, no scheduler, no PassRole).
  * Worker reuse (task 7.1 item 3) — the application job kinds are processed by the EXISTING
    ``MailWorkerFunction`` (NOT a duplicated 2nd consumer); its IAM already covers the SES send
    (verified-domain identity + ``ses:FromAddress`` condition) AND the projection READ the app
    job kinds need (config#mail / config#scope).
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
    """Opaque marker for a CloudFormation intrinsic (``!Ref`` / ``!Sub`` / ``!GetAtt`` / …)."""

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


def _statements(resource: dict) -> list[dict]:
    """The flattened IAM statements of a function's inline Policies."""
    stmts: list[dict] = []
    for policy in resource["Properties"].get("Policies", []):
        stmts.extend(policy["Statement"])
    return stmts


def _by_sid(resource: dict) -> dict[str, dict]:
    return {s["Sid"]: s for s in _statements(resource) if "Sid" in s}


# -----------------------------------------------------------------------------
# R10.1 / D17 — API Gateway throttle + usage plan on the PUBLIC API
# -----------------------------------------------------------------------------


def test_public_api_has_a_stage_throttle_bound_to_params(template):
    """R10.1: the public API's stage throttle caps rate + burst across every method/path."""
    settings = template["Resources"]["MembersPublicApi"]["Properties"]["MethodSettings"]
    # The wildcard method/path so the cap applies to BOTH public routes.
    wildcard = [m for m in settings if m.get("HttpMethod") == "*" and m.get("ResourcePath") == "/*"]
    assert wildcard, "a wildcard MethodSettings entry must throttle every method/path (R10.1)"
    m = wildcard[0]
    rate = m["ThrottlingRateLimit"]
    burst = m["ThrottlingBurstLimit"]
    assert isinstance(rate, _CfnTag) and rate.tag == "Ref" and rate.value == "PublicApiThrottleRateLimit"
    assert isinstance(burst, _CfnTag) and burst.tag == "Ref" and burst.value == "PublicApiThrottleBurstLimit"


def test_usage_plan_exists_and_is_bound_to_the_public_api_stage(template):
    """R10.1: a usage plan carries the same rate/burst, bound to the PUBLIC api's stage only."""
    plans = {
        name: r
        for name, r in template["Resources"].items()
        if r["Type"] == "AWS::ApiGateway::UsagePlan"
    }
    assert plans, "task 7.1 must declare an API Gateway usage plan for the public API (R10.1)"
    [(_, plan)] = plans.items()
    props = plan["Properties"]
    # Bound to the public API, never the authenticated MembersApi.
    api_stages = props["ApiStages"]
    assert len(api_stages) == 1
    api_id = api_stages[0]["ApiId"]
    assert isinstance(api_id, _CfnTag) and api_id.tag == "Ref" and api_id.value == "MembersPublicApi"
    # Same rate/burst knobs as the stage throttle.
    throttle = props["Throttle"]
    assert throttle["RateLimit"].value == "PublicApiThrottleRateLimit"
    assert throttle["BurstLimit"].value == "PublicApiThrottleBurstLimit"


def test_usage_plan_is_not_bound_to_the_authenticated_api(template):
    """The usage plan throttles the PUBLIC surface only — never the token-gated MembersApi."""
    for r in template["Resources"].values():
        if r["Type"] != "AWS::ApiGateway::UsagePlan":
            continue
        for stage in r["Properties"]["ApiStages"]:
            api_id = stage["ApiId"]
            assert not (isinstance(api_id, _CfnTag) and api_id.value == "MembersApi")


def test_throttle_params_have_fail_safe_low_defaults(template):
    """A bare deploy is BOUNDED (not unlimited): low integer defaults with sane min/max."""
    params = template["Parameters"]
    rate = params["PublicApiThrottleRateLimit"]
    burst = params["PublicApiThrottleBurstLimit"]
    assert rate["Type"] == "Number" and burst["Type"] == "Number"
    assert rate["Default"] <= 100 and burst["Default"] <= 200  # low = bounded, not unlimited
    assert rate["MinValue"] >= 1 and burst["MinValue"] >= 1


def test_samconfig_supplies_throttle_per_env(samconfig):
    """Both envs pin a concrete rate + burst (config, steering 36/43)."""
    for env in ("test", "prod"):
        overrides = _override_map(samconfig, env)
        assert int(overrides["PublicApiThrottleRateLimit"]) >= 1
        assert int(overrides["PublicApiThrottleBurstLimit"]) >= 1


# -----------------------------------------------------------------------------
# R10.4 / D17 — NO WAF on the public surface
# -----------------------------------------------------------------------------


def test_no_waf_is_provisioned_d17(template):
    """D17/R10.4: NO WAF in v1 — no WebACL / association anywhere in the template."""
    waf_types = {
        "AWS::WAFv2::WebACL",
        "AWS::WAFv2::WebACLAssociation",
        "AWS::WAF::WebACL",
        "AWS::WAFRegional::WebACL",
    }
    offenders = [
        name for name, r in template["Resources"].items() if r["Type"] in waf_types
    ]
    assert offenders == [], f"D17: no WAF must be provisioned (found {offenders})"


# -----------------------------------------------------------------------------
# R10.5 — the public fn's IAM is EXACTLY the three scoped grants, no wildcard
# -----------------------------------------------------------------------------


def test_public_fn_iam_is_exactly_the_three_scoped_grants(template):
    """R10.5: members-table write + projection read + queue enqueue — and nothing else."""
    sids = set(_by_sid(template["Resources"]["MembersPublicFunction"]).keys())
    assert sids == {
        "PublicWriteMembersTable",
        "PublicReadGovernanceProjection",
        "PublicEnqueueMailSend",
    }


def test_public_fn_members_table_grant_is_scoped_and_write_capable(template):
    stmt = _by_sid(template["Resources"]["MembersPublicFunction"])["PublicWriteMembersTable"]
    actions = set(stmt["Action"])
    # The create_application spine: create (PutItem + the appsession conditional put), update
    # (same-session resubmit), query (name+dob GSI + appsession read), reads.
    assert {"dynamodb:PutItem", "dynamodb:UpdateItem", "dynamodb:Query", "dynamodb:GetItem"} <= actions
    # The public path never deletes (D23) or batch-writes — those actions must be absent.
    assert "dynamodb:DeleteItem" not in actions
    assert "dynamodb:BatchWriteItem" not in actions
    # Scoped to the EXACT members-table ARN + its /index/* (the name_dob_index GSI). No wildcard.
    resources = stmt["Resource"]
    subs = [r.value for r in resources if isinstance(r, _CfnTag) and r.tag == "Sub"]
    assert any("table/${MembersTableName}" in s and "/index/" not in s for s in subs)
    assert any(s.endswith("table/${MembersTableName}/index/*") for s in subs)
    # No cross-account / wildcard table (every ARN pins this account + the named table).
    for s in subs:
        assert "${AWS::AccountId}" in s
        assert "table/*" not in s


def test_public_fn_projection_grant_is_read_only_and_scoped(template):
    stmt = _by_sid(template["Resources"]["MembersPublicFunction"])["PublicReadGovernanceProjection"]
    actions = set(stmt["Action"])
    # READ-ONLY — one-way projection (ADR 0005). No write of any kind.
    assert actions == {"dynamodb:Query", "dynamodb:GetItem"}
    assert not any(a.startswith("dynamodb:Put") or a.startswith("dynamodb:Update")
                   or a.startswith("dynamodb:Delete") or a.startswith("dynamodb:BatchWrite")
                   for a in actions)
    [res] = stmt["Resource"]
    assert isinstance(res, _CfnTag) and res.tag == "Sub"
    assert "table/${GovernanceProjectionTableName}" in res.value
    assert "${AWS::AccountId}" in res.value


def test_public_fn_enqueue_grant_is_sendmessage_only_on_exact_queue(template):
    stmt = _by_sid(template["Resources"]["MembersPublicFunction"])["PublicEnqueueMailSend"]
    # Producer only — SendMessage, never Receive/Delete (that is the worker).
    assert stmt["Action"] == ["sqs:SendMessage"]
    [res] = stmt["Resource"]
    assert isinstance(res, _CfnTag) and res.tag == "GetAtt"
    # The EXACT main queue ARN (never the DLQ).
    assert res.value in ("MailSendQueue.Arn", ["MailSendQueue", "Arn"])


def test_public_fn_has_no_ses_scheduler_or_passrole(template):
    """R10.5: the public edge does NOT send SES (the worker does), manage schedules, or PassRole."""
    for stmt in _statements(template["Resources"]["MembersPublicFunction"]):
        for action in stmt["Action"]:
            assert not action.startswith("ses:")
            assert not action.startswith("scheduler:")
            assert action != "iam:PassRole"
            assert not action.startswith("s3:")  # the public edge touches no template bodies


def test_public_fn_wires_mail_send_queue_url_matching_the_grant(template):
    """The producer env var + the SendMessage grant point at the SAME queue (cannot disagree)."""
    env_vars = template["Resources"]["MembersPublicFunction"]["Properties"]["Environment"]["Variables"]
    url = env_vars["MAIL_SEND_QUEUE_URL"]
    assert isinstance(url, _CfnTag) and url.tag == "Ref" and url.value == "MailSendQueue"


# -----------------------------------------------------------------------------
# Worker reuse (task 7.1 item 3) — the app job kinds reuse the EXISTING worker
# -----------------------------------------------------------------------------


def test_app_job_kinds_reuse_the_single_existing_mail_worker(template):
    """Item 3: NO duplicated 2nd consumer — the one MailWorkerFunction drains the one queue."""
    workers = {
        name: r
        for name, r in template["Resources"].items()
        if r["Type"] == "AWS::Serverless::Function"
        and r["Properties"].get("Handler") == "sam.members.worker.app.handler"
    }
    assert set(workers) == {"MailWorkerFunction"}, "exactly one mail-send worker — no duplicate"
    # It consumes exactly the one MailSendQueue (the queue the public edge enqueues to).
    events = template["Resources"]["MailWorkerFunction"]["Properties"]["Events"]
    sqs_sources = [e for e in events.values() if e["Type"] == "SQS"]
    assert len(sqs_sources) == 1
    queue = sqs_sources[0]["Properties"]["Queue"]
    assert isinstance(queue, _CfnTag) and queue.tag == "GetAtt"
    assert queue.value in ("MailSendQueue.Arn", ["MailSendQueue", "Arn"])


def test_worker_iam_covers_ses_send_for_app_job_kinds(template):
    """Item 3: the worker's SES grant (used by the app job kinds) is scoped + condition-pinned."""
    stmt = _by_sid(template["Resources"]["MailWorkerFunction"])["MailWorkerSendViaSes"]
    actions = set(stmt["Action"])
    assert {"ses:SendEmail", "ses:SendRawEmail"} <= actions
    assert "ses:SendBulkEmail" not in actions  # per-recipient individual sends, least privilege
    # Scoped to the verified tenant DOMAIN identity (never identity/*).
    subs = [r.value for r in stmt["Resource"] if isinstance(r, _CfnTag) and r.tag == "Sub"]
    assert any("identity/${MailSenderDomain}" in s for s in subs)
    assert not any(s.rstrip("'").endswith("identity/*") for s in subs)
    # ses:FromAddress condition pins the local part to noreply@<domain>.
    cond = stmt["Condition"]["StringEquals"]["ses:FromAddress"]
    assert isinstance(cond, _CfnTag) and cond.tag == "Sub"
    assert cond.value == "noreply@${MailSenderDomain}"


def test_worker_iam_covers_projection_read_for_app_job_kinds(template):
    """Item 3: the app job kinds read config#mail / config#scope — the worker reads the projection."""
    stmt = _by_sid(template["Resources"]["MailWorkerFunction"])["MailWorkerReadGovernanceProjection"]
    assert set(stmt["Action"]) == {"dynamodb:Query", "dynamodb:GetItem"}
    [res] = stmt["Resource"]
    assert isinstance(res, _CfnTag) and res.tag == "Sub"
    assert "table/${GovernanceProjectionTableName}" in res.value
