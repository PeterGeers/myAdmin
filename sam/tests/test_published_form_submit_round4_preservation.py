"""
Bugfix spec `bugfix-published-form-submit` - Round 4, Task 14: the PRESERVATION property tests.
Property 8 (Preservation, Round 4). Observation-first: every assertion was OBSERVED on the CURRENT
(pre-Round-4-fix) code and MUST PASS NOW. The Round-4 fix (tasks 15.x) splits the slug-marker IAM
statement and routes OPTIONS to the public Lambda; it must NOT change:
  * R12.1 - the authenticated `MembersApi` `Cors` block and `MembersFunction` IAM statements;
  * R12.2 - real GET/POST per-origin CORS (foreign origin never echoed, never `*`; static baseline
            echoed exactly);
  * R12.3 - every `MembersPublicFunction` IAM statement other than the slug-marker one(s), and the
            slug-marker least-privilege UNION (GetObject + ListBucket only, `_slugs/*` / bucket ARN);
  * R12.4 - the public stage throttle (`MethodSettings`) and usage plan.
Deliberately NOT asserted: OPTIONS behaviour (task 15.2 changes it) and the `PublicReadSlugMarkers`
statement itself (task 15.1 splits it).
Validates (bugfix): Requirements 12.1, 12.2, 12.3, 12.4, 12.5
"""

from __future__ import annotations

import json

import pytest
import yaml
from hypothesis import given, settings
from hypothesis import strategies as st

from sam.members.handler import public_app
from sam.tests.test_public_api_stack_contract import (
    _TEMPLATE_PATH,
    _CfnLoader,
    _CfnTag,
)
from sam.tests.test_public_app_edge import _proxy_event
from sam.tests.test_published_form_submit_round3_preservation import (
    _BASELINE,
    _SLUG,
    _VALID_BODY,
    _acao,
    _edge,
    _post,
    _ready_service,
)

_FOREIGN = "https://evil.jabaki.nl"
_OBJ_ARN = "!Sub arn:aws:s3:::${LandingPagesBucket}/_slugs/*"
_BUCKET_ARN = "!Sub arn:aws:s3:::${LandingPagesBucket}"


def _norm(x):
    """Normalise a loaded template node to plain JSON-comparable data (CFN tags -> '!Tag value')."""
    if isinstance(x, _CfnTag):
        if isinstance(x.value, str):
            return f"!{x.tag} {x.value}"
        return f"!{x.tag} " + json.dumps(_norm(x.value), sort_keys=True)
    if isinstance(x, dict):
        return {k: _norm(v) for k, v in x.items()}
    if isinstance(x, list):
        return [_norm(v) for v in x]
    return x


@pytest.fixture(scope="module")
def tpl() -> dict:
    with open(_TEMPLATE_PATH, "rb") as fh:
        return yaml.load(fh, Loader=_CfnLoader)


def _statements(tpl, fn):
    out = {}
    for pol in tpl["Resources"][fn]["Properties"]["Policies"]:
        for stmt in pol["Statement"]:
            out[stmt["Sid"]] = _norm(stmt)
    return out


def _snap(stmt):
    """Sid-level snapshot: Effect / Action / Resource (order-insensitive) + Condition."""
    return {
        "Effect": stmt["Effect"],
        "Action": sorted(stmt["Action"]),
        "Resource": sorted(stmt["Resource"]),
        "Condition": stmt.get("Condition"),
    }


_GOV = "!Sub arn:aws:dynamodb:${Region}:${AWS::AccountId}:table/${GovernanceProjectionTableName}"
_MEMBERS = "!Sub arn:aws:dynamodb:${Region}:${AWS::AccountId}:table/${MembersTableName}"
_LP = "!Sub arn:aws:s3:::${LandingPagesBucket}"

_MEMBERS_FUNCTION_SNAPSHOT = {
    "MembersReadGovernanceProjection": {
        "Effect": "Allow",
        "Action": ["dynamodb:GetItem", "dynamodb:Query"],
        "Resource": [_GOV],
        "Condition": None,
    },
    "MembersWriteGovernanceProjectionConfig": {
        "Effect": "Allow",
        "Action": ["dynamodb:PutItem", "dynamodb:UpdateItem"],
        "Resource": [_GOV],
        "Condition": None,
    },
    "MembersCrudMembersTable": {
        "Effect": "Allow",
        "Action": sorted(
            [
                "dynamodb:Query",
                "dynamodb:GetItem",
                "dynamodb:BatchGetItem",
                "dynamodb:PutItem",
                "dynamodb:UpdateItem",
                "dynamodb:DeleteItem",
                "dynamodb:BatchWriteItem",
            ]
        ),
        "Resource": sorted([_MEMBERS, _MEMBERS + "/index/*"]),
        "Condition": None,
    },
    "MembersTemplateBodiesS3": {
        "Effect": "Allow",
        "Action": ["s3:DeleteObject", "s3:GetObject", "s3:PutObject"],
        "Resource": ["!Sub arn:aws:s3:::${SharedBucketName}/*/members/mail/*"],
        "Condition": None,
    },
    "MembersSendViaSes": {
        "Effect": "Allow",
        "Action": ["ses:SendEmail", "ses:SendRawEmail"],
        "Resource": sorted(
            [
                "!Sub arn:aws:ses:${Region}:${AWS::AccountId}:identity/${MailSenderDomain}",
                "!Sub arn:aws:ses:${Region}:${AWS::AccountId}:configuration-set/${SesConfigurationSet}",
            ]
        ),
        "Condition": {
            "StringEquals": {"ses:FromAddress": "!Sub noreply@${MailSenderDomain}"}
        },
    },
    "MembersEnqueueMailSend": {
        "Effect": "Allow",
        "Action": ["sqs:SendMessage"],
        "Resource": ["!GetAtt MailSendQueue.Arn"],
        "Condition": None,
    },
    "MembersManageSchedules": {
        "Effect": "Allow",
        "Action": sorted(
            [
                "scheduler:CreateSchedule",
                "scheduler:UpdateSchedule",
                "scheduler:DeleteSchedule",
                "scheduler:GetSchedule",
            ]
        ),
        "Resource": [
            "!Sub arn:aws:scheduler:${Region}:${AWS::AccountId}:schedule/${SchedulerGroupName}/*"
        ],
        "Condition": None,
    },
    "MembersPassSchedulerExecutionRole": {
        "Effect": "Allow",
        "Action": ["iam:PassRole"],
        "Resource": ["!GetAtt MembersSchedulerExecutionRole.Arn"],
        "Condition": {
            "StringEquals": {"iam:PassedToService": "scheduler.amazonaws.com"}
        },
    },
    "MembersPublishPublicPages": {
        "Effect": "Allow",
        "Action": ["s3:DeleteObject", "s3:GetObject", "s3:PutObject"],
        "Resource": sorted(
            [_LP + "/_slugs/*", _LP + "/*/index.html", _LP + "/*/form.json"]
        ),
        "Condition": None,
    },
    "MembersListPublicPages": {
        "Effect": "Allow",
        "Action": ["s3:ListBucket"],
        "Resource": [_LP],
        "Condition": {
            "StringLike": {"s3:prefix": ["_slugs/*", "*/index.html", "*/form.json"]}
        },
    },
    "MembersInvalidatePublicPages": {
        "Effect": "Allow",
        "Action": ["cloudfront:CreateInvalidation"],
        "Resource": [
            "!Sub arn:aws:cloudfront::${AWS::AccountId}:distribution/${CloudFrontPublicPagesDistributionId}"
        ],
        "Condition": None,
    },
}

_PUBLIC_OTHER_SNAPSHOT = {
    "PublicReadGovernanceProjection": {
        "Effect": "Allow",
        "Action": ["dynamodb:GetItem", "dynamodb:Query"],
        "Resource": [_GOV],
        "Condition": None,
    },
    "PublicWriteMembersTable": {
        "Effect": "Allow",
        "Action": sorted(
            [
                "dynamodb:Query",
                "dynamodb:GetItem",
                "dynamodb:BatchGetItem",
                "dynamodb:PutItem",
                "dynamodb:UpdateItem",
            ]
        ),
        "Resource": sorted([_MEMBERS, _MEMBERS + "/index/*"]),
        "Condition": None,
    },
    "PublicEnqueueMailSend": {
        "Effect": "Allow",
        "Action": ["sqs:SendMessage"],
        "Resource": ["!GetAtt MailSendQueue.Arn"],
        "Condition": None,
    },
}

# Slug-marker statement Sids: the current single one, and the names the 15.1 split will use.
_SLUG_MARKER_SIDS = {
    "PublicReadSlugMarkers",
    "PublicReadSlugMarkerObjects",
    "PublicListSlugMarkers",
}


# --- R12.1 - authenticated API CORS + MembersFunction IAM -----------------------------------
def test_preserve_members_api_cors_block_exact(tpl):
    cors = _norm(tpl["Resources"]["MembersApi"]["Properties"]["Cors"])
    assert cors == {
        "AllowMethods": "'GET,POST,PUT,PATCH,DELETE,OPTIONS'",
        "AllowHeaders": "'Content-Type,Authorization,X-Tenant,X-Language'",
        "AllowOrigin": "'*'",
    }


def test_preserve_members_function_iam_statements_exact(tpl):
    got = {sid: _snap(s) for sid, s in _statements(tpl, "MembersFunction").items()}
    assert got == _MEMBERS_FUNCTION_SNAPSHOT


# --- R12.3 - public function IAM -----------------------------------------------------------
def test_preserve_public_other_iam_statements_exact(tpl):
    others = {
        sid: _snap(s)
        for sid, s in _statements(tpl, "MembersPublicFunction").items()
        if sid not in _SLUG_MARKER_SIDS
    }
    assert others == _PUBLIC_OTHER_SNAPSHOT


def test_preserve_slug_marker_s3_union_is_least_privilege(tpl):
    """Holds before AND after the 15.1 split: the union of S3 actions/resources is unchanged."""
    s3 = [
        s
        for s in _statements(tpl, "MembersPublicFunction").values()
        if any(a.startswith("s3:") for a in s["Action"])
    ]
    assert s3, "public function must keep its slug-marker S3 read"
    actions = {a for s in s3 for a in s["Action"]}
    assert actions == {"s3:GetObject", "s3:ListBucket"}  # no Put/Delete
    resources = {r for s in s3 for r in s["Resource"]}
    assert resources <= {
        _OBJ_ARN,
        _BUCKET_ARN,
    }  # no bucket-wide object ARN, nothing else
    get_res = {r for s in s3 if "s3:GetObject" in s["Action"] for r in s["Resource"]}
    list_res = {r for s in s3 if "s3:ListBucket" in s["Action"] for r in s["Resource"]}
    assert _OBJ_ARN in get_res
    assert _BUCKET_ARN in list_res
    # ListBucket stays prefix-scoped to _slugs/*.
    for s in s3:
        if "s3:ListBucket" in s["Action"]:
            assert s["Condition"] == {"StringLike": {"s3:prefix": ["_slugs/*"]}}


# --- R12.4 - public stage throttle + usage plan --------------------------------------------
def test_preserve_public_stage_throttle_and_usage_plan(tpl):
    res = tpl["Resources"]
    ms = _norm(res["MembersPublicApi"]["Properties"]["MethodSettings"])
    assert ms == [
        {
            "HttpMethod": "*",
            "ResourcePath": "/*",
            "ThrottlingRateLimit": "!Ref PublicApiThrottleRateLimit",
            "ThrottlingBurstLimit": "!Ref PublicApiThrottleBurstLimit",
        }
    ]
    plan = res["MembersPublicApiUsagePlan"]
    assert plan["Type"] == "AWS::ApiGateway::UsagePlan"
    props = _norm(plan["Properties"])
    assert props["Throttle"] == {
        "RateLimit": "!Ref PublicApiThrottleRateLimit",
        "BurstLimit": "!Ref PublicApiThrottleBurstLimit",
    }
    assert props["ApiStages"] == [
        {"ApiId": "!Ref MembersPublicApi", "Stage": "!Ref Stage"}
    ]


# --- R12.2 - real GET / POST per-origin CORS -----------------------------------------------
def _get(origin):
    return public_app.handler(
        _proxy_event(
            "GET", f"/public/members/{_SLUG}/field-config", headers={"Origin": origin}
        )
    )


def test_preserve_foreign_origin_never_acao_on_get_and_post():
    with _edge(_ready_service()):
        for resp in (_get(_FOREIGN), _post(_FOREIGN, _VALID_BODY)):
            acao = _acao(resp)
            assert acao is None or acao == _BASELINE
            assert acao != "*" and acao != _FOREIGN


def test_preserve_static_baseline_origin_echoed_exactly_on_get_and_post():
    with _edge(_ready_service()):
        assert _acao(_get(_BASELINE)) == _BASELINE
        assert _acao(_post(_BASELINE, _VALID_BODY)) == _BASELINE


@settings(max_examples=40, deadline=None)
@given(
    sub=st.text(
        alphabet="abcdefghijklmnopqrstuvwxyz0123456789-", min_size=1, max_size=12
    ).filter(lambda s: s not in (_SLUG, "aanmelden-test")),
    apex=st.sampled_from(["jabaki.nl", "example.com", "evil.net"]),
    method=st.sampled_from(["GET", "POST"]),
)
def test_preserve_random_foreign_origin_never_echoed_nor_wildcard(sub, apex, method):
    origin = f"https://{sub}.{apex}"
    with _edge(_ready_service()):
        resp = _get(origin) if method == "GET" else _post(origin, _VALID_BODY)
    acao = _acao(resp)
    assert acao != "*" and acao != origin
