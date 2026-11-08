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
    wildcard = [
        m
        for m in settings
        if m.get("HttpMethod") == "*" and m.get("ResourcePath") == "/*"
    ]
    assert wildcard, (
        "a wildcard MethodSettings entry must throttle every method/path (R10.1)"
    )
    m = wildcard[0]
    rate = m["ThrottlingRateLimit"]
    burst = m["ThrottlingBurstLimit"]
    assert (
        isinstance(rate, _CfnTag)
        and rate.tag == "Ref"
        and rate.value == "PublicApiThrottleRateLimit"
    )
    assert (
        isinstance(burst, _CfnTag)
        and burst.tag == "Ref"
        and burst.value == "PublicApiThrottleBurstLimit"
    )


def test_usage_plan_exists_and_is_bound_to_the_public_api_stage(template):
    """R10.1: a usage plan carries the same rate/burst, bound to the PUBLIC api's stage only."""
    plans = {
        name: r
        for name, r in template["Resources"].items()
        if r["Type"] == "AWS::ApiGateway::UsagePlan"
    }
    assert plans, (
        "task 7.1 must declare an API Gateway usage plan for the public API (R10.1)"
    )
    [(_, plan)] = plans.items()
    props = plan["Properties"]
    # Bound to the public API, never the authenticated MembersApi.
    api_stages = props["ApiStages"]
    assert len(api_stages) == 1
    api_id = api_stages[0]["ApiId"]
    assert (
        isinstance(api_id, _CfnTag)
        and api_id.tag == "Ref"
        and api_id.value == "MembersPublicApi"
    )
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
    assert (
        rate["Default"] <= 100 and burst["Default"] <= 200
    )  # low = bounded, not unlimited
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


def test_public_fn_iam_is_exactly_the_four_scoped_grants(template):
    """R10.5: members-table write + projection read + queue enqueue + slug-marker READ — and
    nothing else. The slug-marker READ (`PublicReadSlugMarkers`) is the SAM-plane half of SEC-8
    (spec 14 Task 9.2) that was missing — the public edge resolves `_slugs/{slug}` markers, so
    the live Task-9.4 e2e surfaced the deployed public fn 500ing (AccessDenied on s3:ListBucket)
    with no S3 grant at all. EXACT-set assertion — the public edge gains the scoped READ and
    nothing wider (no S3 write, no new account/action)."""
    sids = set(_by_sid(template["Resources"]["MembersPublicFunction"]).keys())
    assert sids == {
        "PublicWriteMembersTable",
        "PublicReadGovernanceProjection",
        "PublicEnqueueMailSend",
        "PublicReadSlugMarkers",
        "PublicListSlugMarkers",
    }


def test_public_fn_slug_marker_grant_is_scoped_read_only_no_write(template):
    """Spec 14 Task 9.2 (SEC-8, SAM half): the public edge READS slug markers least-privilege —
    GetObject on `_slugs/*` + ListBucket prefix-conditioned to `_slugs/*` (so a MISSING marker is
    a clean NoSuchKey/404, not AccessDenied → enumeration-safe), ARNs from `${LandingPagesBucket}`,
    and NO PutObject/DeleteObject on the public edge (claiming/renaming is the authenticated fn)."""
    stmts = _by_sid(template["Resources"]["MembersPublicFunction"])
    get_stmt = stmts["PublicReadSlugMarkers"]
    stmt = stmts["PublicListSlugMarkers"]
    # TWO statements: the s3:prefix Condition has no meaning for GetObject (IAM would deny it),
    # so GetObject is its own condition-free statement and ListBucket carries the Condition.
    assert set(get_stmt["Action"]) == {"s3:GetObject"}
    assert "Condition" not in get_stmt
    assert set(stmt["Action"]) == {"s3:ListBucket"}
    actions = set(get_stmt["Action"]) | set(stmt["Action"])
    # No WRITE on the public edge — it only resolves markers, never claims/renames them.
    assert "s3:PutObject" not in actions
    assert "s3:DeleteObject" not in actions
    # ARNs built from the LandingPagesBucket param — never a hardcode.
    subs = [
        r.value
        for r in get_stmt["Resource"] + stmt["Resource"]
        if isinstance(r, _CfnTag) and r.tag == "Sub"
    ]
    assert [r.value for r in get_stmt["Resource"]] == [
        "arn:aws:s3:::${LandingPagesBucket}/_slugs/*"
    ]
    assert [r.value for r in stmt["Resource"]] == ["arn:aws:s3:::${LandingPagesBucket}"]
    # GetObject is object-scoped to the `_slugs/*` marker prefix.
    assert any(s == "arn:aws:s3:::${LandingPagesBucket}/_slugs/*" for s in subs)
    # ListBucket targets the bucket itself (object-prefix lives in the Condition, not the ARN).
    assert any(s == "arn:aws:s3:::${LandingPagesBucket}" for s in subs)
    # No hardcoded bucket name, no cross-account.
    for s in subs:
        assert "myadmin-public-pages" not in s
    # The ListBucket enumeration is prefix-conditioned to `_slugs/*` (enumeration-safe, no
    # bucket-wide list).
    prefixes = stmt["Condition"]["StringLike"]["s3:prefix"]
    assert "_slugs/*" in (prefixes if isinstance(prefixes, list) else [prefixes])


def test_public_fn_members_table_grant_is_scoped_and_write_capable(template):
    stmt = _by_sid(template["Resources"]["MembersPublicFunction"])[
        "PublicWriteMembersTable"
    ]
    actions = set(stmt["Action"])
    # The create_application spine: create (PutItem + the appsession conditional put), update
    # (same-session resubmit), query (name+dob GSI + appsession read), reads.
    assert {
        "dynamodb:PutItem",
        "dynamodb:UpdateItem",
        "dynamodb:Query",
        "dynamodb:GetItem",
    } <= actions
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
    stmt = _by_sid(template["Resources"]["MembersPublicFunction"])[
        "PublicReadGovernanceProjection"
    ]
    actions = set(stmt["Action"])
    # READ-ONLY — one-way projection (ADR 0005). No write of any kind.
    assert actions == {"dynamodb:Query", "dynamodb:GetItem"}
    assert not any(
        a.startswith("dynamodb:Put")
        or a.startswith("dynamodb:Update")
        or a.startswith("dynamodb:Delete")
        or a.startswith("dynamodb:BatchWrite")
        for a in actions
    )
    [res] = stmt["Resource"]
    assert isinstance(res, _CfnTag) and res.tag == "Sub"
    assert "table/${GovernanceProjectionTableName}" in res.value
    assert "${AWS::AccountId}" in res.value


def test_public_fn_enqueue_grant_is_sendmessage_only_on_exact_queue(template):
    stmt = _by_sid(template["Resources"]["MembersPublicFunction"])[
        "PublicEnqueueMailSend"
    ]
    # Producer only — SendMessage, never Receive/Delete (that is the worker).
    assert stmt["Action"] == ["sqs:SendMessage"]
    [res] = stmt["Resource"]
    assert isinstance(res, _CfnTag) and res.tag == "GetAtt"
    # The EXACT main queue ARN (never the DLQ).
    assert res.value in ("MailSendQueue.Arn", ["MailSendQueue", "Arn"])


def test_public_fn_has_no_ses_scheduler_passrole_or_s3_write(template):
    """R10.5 (tightened for spec 14 Task 9.2): the public edge does NOT send SES (the worker does),
    manage schedules, or PassRole. It MAY now hold the scoped `_slugs/*` S3 READ (GetObject +
    prefix-conditioned ListBucket — SEC-8 slug resolution), but still NO S3 WRITE (no
    PutObject/DeleteObject — claiming/renaming markers is the authenticated MembersFunction)."""
    for stmt in _statements(template["Resources"]["MembersPublicFunction"]):
        for action in stmt["Action"]:
            assert not action.startswith("ses:")
            assert not action.startswith("scheduler:")
            assert action != "iam:PassRole"
            # The only S3 the public edge may hold is the scoped marker READ — never a write.
            assert action not in ("s3:PutObject", "s3:DeleteObject")
            if action.startswith("s3:"):
                assert action in ("s3:GetObject", "s3:ListBucket")


def test_public_fn_wires_mail_send_queue_url_matching_the_grant(template):
    """The producer env var + the SendMessage grant point at the SAME queue (cannot disagree)."""
    env_vars = template["Resources"]["MembersPublicFunction"]["Properties"][
        "Environment"
    ]["Variables"]
    url = env_vars["MAIL_SEND_QUEUE_URL"]
    assert (
        isinstance(url, _CfnTag) and url.tag == "Ref" and url.value == "MailSendQueue"
    )


# -----------------------------------------------------------------------------
# Spec 14 Task 9.2 (SEC-8, SAM half) — the AUTHENTICATED publish fn's public-pages grant
# -----------------------------------------------------------------------------


def test_members_fn_publish_s3_grant_is_scoped_to_markers_and_served_artifacts(
    template,
):
    """The publish route CLAIMS slugs (`_slugs/*` marker PutObject, rename DeleteObject) and writes
    the served artifacts (`{slug}/index.html` + `{slug}/form.json`) — scoped to those prefixes,
    never bucket-root `*` alone (mirrors the SEC-8 scoping Task 9.2 chose). GetObject is included
    for idempotent read-before-write; least-privilege, no `s3:*`."""
    stmt = _by_sid(template["Resources"]["MembersFunction"])[
        "MembersPublishPublicPages"
    ]
    actions = set(stmt["Action"])
    assert actions == {"s3:GetObject", "s3:PutObject", "s3:DeleteObject"}
    # Never a blanket wildcard.
    assert "s3:*" not in actions
    subs = [
        r.value for r in stmt["Resource"] if isinstance(r, _CfnTag) and r.tag == "Sub"
    ]
    # Markers: the `_slugs/*` prefix the claim/rename writes.
    assert any(s == "arn:aws:s3:::${LandingPagesBucket}/_slugs/*" for s in subs)
    # Served artifacts: the two exact filenames under any `{slug}/` — tighter than bucket-root `*`.
    assert any(s == "arn:aws:s3:::${LandingPagesBucket}/*/index.html" for s in subs)
    assert any(s == "arn:aws:s3:::${LandingPagesBucket}/*/form.json" for s in subs)
    # NOT a bucket-root `/*` object grant on its own (that would be bucket-wide, defeating SEC-8).
    assert not any(s == "arn:aws:s3:::${LandingPagesBucket}/*" for s in subs)
    # No hardcoded bucket name.
    for s in subs:
        assert "myadmin-public-pages" not in s


def test_members_fn_publish_listbucket_is_prefix_conditioned(template):
    """The publish ListBucket is `s3:prefix`-conditioned to the marker + served prefixes — never a
    bucket-wide list — so a missing marker/artifact is a clean NoSuchKey, enumeration-safe."""
    stmt = _by_sid(template["Resources"]["MembersFunction"])["MembersListPublicPages"]
    assert stmt["Action"] == ["s3:ListBucket"] or set(stmt["Action"]) == {
        "s3:ListBucket"
    }
    [res] = stmt["Resource"]
    assert isinstance(res, _CfnTag) and res.tag == "Sub"
    assert res.value == "arn:aws:s3:::${LandingPagesBucket}"
    prefixes = stmt["Condition"]["StringLike"]["s3:prefix"]
    prefixes = prefixes if isinstance(prefixes, list) else [prefixes]
    assert "_slugs/*" in prefixes
    # The served-artifact prefixes are covered too (so the list stays scoped, not bucket-wide).
    assert any(p.endswith("index.html") for p in prefixes)
    assert any(p.endswith("form.json") for p in prefixes)


def test_members_fn_publish_cloudfront_invalidation_is_scoped_to_the_one_distribution(
    template,
):
    """Best-effort CloudFront invalidation (Task 9.1): `cloudfront:CreateInvalidation` ONLY, on
    EXACTLY the `${CloudFrontPublicPagesDistributionId}` distribution ARN (in the nonprofit account
    where the distribution lives, so this grant can actually invalidate). Least-privilege — no
    wildcard distribution, no other CloudFront action."""
    stmt = _by_sid(template["Resources"]["MembersFunction"])[
        "MembersInvalidatePublicPages"
    ]
    assert stmt["Action"] == ["cloudfront:CreateInvalidation"] or set(
        stmt["Action"]
    ) == {"cloudfront:CreateInvalidation"}
    [res] = stmt["Resource"]
    assert isinstance(res, _CfnTag) and res.tag == "Sub"
    assert res.value == (
        "arn:aws:cloudfront::${AWS::AccountId}:distribution/"
        "${CloudFrontPublicPagesDistributionId}"
    )


def test_members_fn_publish_grant_is_least_privilege_no_s3_star(template):
    """No `s3:*` / `cloudfront:*` blanket anywhere in the publish grants — least-privilege (SEC-8)."""
    publish_sids = (
        "MembersPublishPublicPages",
        "MembersListPublicPages",
        "MembersInvalidatePublicPages",
    )
    by_sid = _by_sid(template["Resources"]["MembersFunction"])
    for sid in publish_sids:
        for action in by_sid[sid]["Action"]:
            assert action not in ("s3:*", "cloudfront:*")
            assert not action.endswith(":*")


# -----------------------------------------------------------------------------
# Public-pages hosting env (spec 14 Task 9) — the slug-marker + artifact stores'
# fail-fast bucket/distribution MUST be wired into BOTH functions' Environment.
# Regression: the live Task-9.4 e2e surfaced a deployed `members-public-*` 500ing on
# every public GET/POST {slug} because LANDING_PAGES_BUCKET was never set (the slug
# marker store's `require_env('LANDING_PAGES_BUCKET')` failed fast). These assert the
# wiring so that regression is caught statically here next time.
# -----------------------------------------------------------------------------

#: The exact env KEY strings — MUST match the repository code constants
#: (slug_marker_store.LANDING_PAGES_BUCKET_ENV_VAR /
#: public_page_artifact_store.CLOUDFRONT_DISTRIBUTION_ENV_VAR).
_LANDING_PAGES_BUCKET_ENV = "LANDING_PAGES_BUCKET"
_CLOUDFRONT_DISTRIBUTION_ENV = "CLOUDFRONT_PUBLIC_PAGES_DISTRIBUTION_ID"


@pytest.mark.parametrize("fn_name", ["MembersPublicFunction", "MembersFunction"])
def test_function_wires_public_pages_hosting_env_from_params(template, fn_name):
    """Task 9: both the served public edge AND the authenticated publish fn carry the
    slug-marker bucket + CloudFront distribution env vars, bound to the new params (`!Ref`)."""
    env_vars = template["Resources"][fn_name]["Properties"]["Environment"]["Variables"]

    bucket = env_vars[_LANDING_PAGES_BUCKET_ENV]
    assert (
        isinstance(bucket, _CfnTag)
        and bucket.tag == "Ref"
        and bucket.value == "LandingPagesBucket"
    )

    dist = env_vars[_CLOUDFRONT_DISTRIBUTION_ENV]
    assert (
        isinstance(dist, _CfnTag)
        and dist.tag == "Ref"
        and dist.value == "CloudFrontPublicPagesDistributionId"
    )


def test_public_pages_hosting_params_are_fail_fast_no_default(template):
    """The two hosting params have NO default (house fail-fast pattern — a blank value must
    break the deploy, never silently target the wrong bucket; steering 23)."""
    params = template["Parameters"]
    for name in ("LandingPagesBucket", "CloudFrontPublicPagesDistributionId"):
        assert params[name]["Type"] == "String"
        assert "Default" not in params[name], f"{name} must be fail-fast (no default)"


def test_samconfig_supplies_public_pages_hosting_per_env(samconfig):
    """Both envs pin the shared nonprofit bucket + distribution (same TEST/prod value, D7)."""
    for env in ("test", "prod"):
        overrides = _override_map(samconfig, env)
        assert (
            overrides["LandingPagesBucket"]
            == "myadmin-public-pages-nonprofit-506221081911"
        )
        assert overrides["CloudFrontPublicPagesDistributionId"] == "E3GLUX3TWBIJG"


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
    assert set(workers) == {"MailWorkerFunction"}, (
        "exactly one mail-send worker — no duplicate"
    )
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
    assert (
        "ses:SendBulkEmail" not in actions
    )  # per-recipient individual sends, least privilege
    # Scoped to the verified tenant DOMAIN identity (never identity/*).
    subs = [
        r.value for r in stmt["Resource"] if isinstance(r, _CfnTag) and r.tag == "Sub"
    ]
    assert any("identity/${MailSenderDomain}" in s for s in subs)
    assert not any(s.rstrip("'").endswith("identity/*") for s in subs)
    # ses:FromAddress condition pins the local part to noreply@<domain>.
    cond = stmt["Condition"]["StringEquals"]["ses:FromAddress"]
    assert isinstance(cond, _CfnTag) and cond.tag == "Sub"
    assert cond.value == "noreply@${MailSenderDomain}"


def test_worker_iam_covers_projection_read_for_app_job_kinds(template):
    """Item 3: the app job kinds read config#mail / config#scope — the worker reads the projection."""
    stmt = _by_sid(template["Resources"]["MailWorkerFunction"])[
        "MailWorkerReadGovernanceProjection"
    ]
    assert set(stmt["Action"]) == {"dynamodb:Query", "dynamodb:GetItem"}
    [res] = stmt["Resource"]
    assert isinstance(res, _CfnTag) and res.tag == "Sub"
    assert "table/${GovernanceProjectionTableName}" in res.value
