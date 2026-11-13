"""
S5 Task 1.4 — the tenant-scoped **table design** for the Members module (design C6 + data
models, R3.1 / Property 1 / Property 6).

This module is the **single source of truth** for the Members module's DynamoDB key shape:
the partition/sort key attribute names, the record-type tokens, the sort-key composition /
parsing, and the item builders. It mirrors the S3 projection's ``projection_schema`` pattern
(one place assembles/parses the ``record_type#id`` composite) so the repository
(:mod:`sam.members.repository.members_repository`), Step-4 provisioning, and the Step-4
backfill all agree on one definition instead of each re-deriving keys.

Single-table design (design "New tenant-scoped tables", data models)
--------------------------------------------------------------------
Every Members entity for a tenant lives in **one** table, partitioned by ``tenant_id`` so a
query cannot address more than one tenant's partition — cross-tenant reads are structurally
unaddressable (Property 1). The sort key is a ``record_type#id`` composite that groups a
member and everything hanging off it (memberships, delegates, payments) under access
patterns that never leave the tenant partition::

    Table: sam-members                    (sam-members-test in test/dev; PAY_PER_REQUEST)
      PK  tenant_id                        -- partition key = tenancy boundary (structural)
      SK  record_type#id                   -- see the record-type tokens below
      attrs: personal{}, membership{}, scope_values{}, overlay{}, ...

      SK values (all within one tenant partition):
        member#<member_id>                              -- the member record (fixed ⊕ overlay)
        member#<member_id>#membership#<membership_id>   -- a membership of that member
        member#<member_id>#delegates                    -- the member's delegate set (single item)
        member#<member_id>#payment#<payment_id>         -- a member-scoped payment
        membershiptype#<type_code>                      -- Lidmaatschap Beheer catalog entry

Member numbering (s5k)
----------------------
``member_number`` (Lidnummer) is a plain OPTIONAL string the caller/import supplies — it is
NOT auto-generated and NOT guarded for uniqueness. The former ``counter#<name>`` (atomic
counter) and ``membernum#<member_number>`` (uniqueness guard) record types were REMOVED; a
duplicate member number is a data-quality concern, not a write-time conflict (see spec s5k).
``save_member`` / ``delete_member`` are single-item ``PutItem`` / ``DeleteItem``.

Config + fail-fast (mirrors ``services.dynamodb_client`` / ``projection_schema``)
---------------------------------------------------------------------------------
The table name is resolved from ``MEMBERS_TABLE`` (``sam-members`` in prod, ``sam-members-test``
in test/dev — the SAM-plane ``sam-`` prefix convention, env as a *suffix*, see
``23-aws-accounts.md`` / ``35-sam-module-architecture-sam.md``) — a missing/blank var raises
rather than defaulting, so nothing can silently point at the wrong table or at production.
This module never synthesizes the name; it takes it verbatim from the env var. The client
points at the local
``dynamodb-local`` container only when ``AWS_ENDPOINT_URL_DYNAMODB`` is set (Step-4 / local),
and at real AWS otherwise. Both concerns reuse the T0 fail-fast client
(:mod:`services.dynamodb_client`), so the no-dangerous-fallback discipline lives in one place.

Scope of THIS module: the **key shape + item builders + table-name resolution**. It is
storage-shape only — no business rules (those are the domain layer), and it does not itself
open a connection until the repository asks for the table resource. Provisioning the physical
table (PAY_PER_REQUEST, retain, managed outside CloudFormation) is Step 4 (task 4.0).
"""

from __future__ import annotations

from services.dynamodb_client import get_dynamodb_resource, require_env

__all__ = [
    "LEADING_KEYS_IAM_POLICY_PLAN",
    "MEMBERS_TABLE_ENV_VAR",
    "NAME_DOB_GSI_INDEX_NAME",
    "NAME_DOB_KEY_ATTR",
    "PARTITION_KEY_ATTR",
    "RECORD_TYPE_ANALYTICS_SET",
    "RECORD_TYPE_APP_SESSION",
    "RECORD_TYPE_COLUMN_PREFS",
    "RECORD_TYPE_DELEGATES",
    "RECORD_TYPE_MAIL_RECIPIENT",
    "RECORD_TYPE_MAIL_RUN",
    "RECORD_TYPE_MAIL_SENT",
    "RECORD_TYPE_MEMBER",
    "RECORD_TYPE_MEMBERSHIP",
    "RECORD_TYPE_MEMBERSHIP_TYPE",
    "RECORD_TYPE_PAYMENT",
    "RECORD_TYPE_PREF_LIST",
    "RECORD_TYPE_SCHEDULE",
    "RECORD_TYPE_TEMPLATE",
    "SORT_KEY_ATTR",
    "SORT_KEY_SEPARATOR",
    "TEMPLATE_S3_PREFIX",
    "analytics_set_sk",
    "app_session_sk",
    "build_analytics_set_item",
    "build_column_prefs_item",
    "build_key",
    "build_mail_recipient_item",
    "build_mail_run_item",
    "build_member_item",
    "build_membership_type_item",
    "build_pref_list_item",
    "build_schedule_item",
    "build_sort_key",
    "build_template_item",
    "column_prefs_sk",
    "delegates_sk",
    "floats_to_decimal",
    "get_members_table_resource",
    "leading_keys_iam_policy_json",
    "mail_recipient_sk",
    "mail_recipient_sk_prefix",
    "mail_run_sk",
    "mail_sent_marker_sk",
    "member_sk",
    "member_sk_prefix",
    "membership_sk",
    "membership_type_sk",
    "name_dob_gsi_attribute_definition",
    "name_dob_gsi_definition",
    "normalize_name_dob_key",
    "payment_sk",
    "pref_list_sk",
    "resolve_members_table_name",
    "schedule_sk",
    "split_sort_key",
    "template_body_s3_key",
    "template_logo_s3_key",
    "template_s3_prefix",
    "template_sk",
]

from ._table_items import (  # noqa: F401 (surface compat)
    TEMPLATE_S3_PREFIX,
    TEMPLATE_SERVICE_PATH,
    _require_s3_segment,
    build_analytics_set_item,
    build_column_prefs_item,
    build_mail_recipient_item,
    build_mail_run_item,
    build_member_item,
    build_membership_type_item,
    build_pref_list_item,
    build_schedule_item,
    build_template_item,
    floats_to_decimal,
    template_body_s3_key,
    template_logo_s3_key,
    template_s3_prefix,
)
from ._table_schema import (  # noqa: F401 (surface compat)
    _NAME_DOB_SEPARATOR,
    _WHITESPACE_RUN,
    MEMBERS_TABLE_ENV_VAR,
    NAME_DOB_GSI_INDEX_NAME,
    NAME_DOB_KEY_ATTR,
    PARTITION_KEY_ATTR,
    RECORD_TYPE_ANALYTICS_SET,
    RECORD_TYPE_APP_SESSION,
    RECORD_TYPE_COLUMN_PREFS,
    RECORD_TYPE_DELEGATES,
    RECORD_TYPE_MAIL_RECIPIENT,
    RECORD_TYPE_MAIL_RUN,
    RECORD_TYPE_MAIL_SENT,
    RECORD_TYPE_MEMBER,
    RECORD_TYPE_MEMBERSHIP,
    RECORD_TYPE_MEMBERSHIP_TYPE,
    RECORD_TYPE_PAYMENT,
    RECORD_TYPE_PREF_LIST,
    RECORD_TYPE_SCHEDULE,
    RECORD_TYPE_TEMPLATE,
    SORT_KEY_ATTR,
    SORT_KEY_SEPARATOR,
    _name_dob_key_from_member,
    _normalize_name_part,
    analytics_set_sk,
    app_session_sk,
    build_key,
    build_sort_key,
    column_prefs_sk,
    delegates_sk,
    mail_recipient_sk,
    mail_recipient_sk_prefix,
    mail_run_sk,
    mail_sent_marker_sk,
    member_sk,
    member_sk_prefix,
    membership_sk,
    membership_type_sk,
    name_dob_gsi_attribute_definition,
    name_dob_gsi_definition,
    normalize_name_dob_key,
    payment_sk,
    pref_list_sk,
    schedule_sk,
    split_sort_key,
    template_sk,
)


def resolve_members_table_name() -> str:
    """Return the Members table name from ``MEMBERS_TABLE``, or fail fast.

    Reuses the T0 fail-fast client (:func:`services.dynamodb_client.require_env`) so the
    no-dangerous-fallback discipline lives in one place. The env value is the full table
    name (``sam-members`` prod / ``sam-members-test`` test/dev — ``sam-`` prefix, env as a
    suffix), so this does not synthesize any prefix.

    Raises:
        services.dynamodb_client.DynamoDBConfigError: ``MEMBERS_TABLE`` is missing/blank.
    """
    return require_env(MEMBERS_TABLE_ENV_VAR)


def get_members_table_resource(*, region: str | None = None):
    """Return the boto3 Table handle for the Members table (fail-fast).

    Points at the local ``dynamodb-local`` container only when ``AWS_ENDPOINT_URL_DYNAMODB``
    is set (Step-4 / local); otherwise real AWS. The region comes from ``AWS_REGION`` unless
    passed explicitly.

    Args:
        region: Optional region override; otherwise ``AWS_REGION`` is required.

    Raises:
        services.dynamodb_client.DynamoDBConfigError: A required env var (table name or
            region) is missing/blank.
    """
    table_name = resolve_members_table_name()
    resource = get_dynamodb_resource(region=region)
    return resource.Table(table_name)


# --- IAM LeadingKeys policy plan (NOT deployed — see status note) ----------

#: IAM policy *plan* for tenant-scoped access to the Members table using
#: ``dynamodb:LeadingKeys``. The partition key already makes cross-tenant reads unaddressable
#: (correctness, Property 1); this condition would ADDITIONALLY restrict a caller's
#: *credentials* to their own partition (defense in depth), mirroring the S3 projection plan.
#:
#: STATUS — NOT DEPLOYED (risk S1 / security-assessment-2026-09-26 M2). This is a plan only,
#: for TWO reasons that both have to be resolved before it enforces anything:
#:
#:   1. It is not attached to the Members Lambda. ``sam/members/template.yaml``
#:      (``MembersFunction.Policies``) grants table-scoped DynamoDB actions with NO
#:      ``LeadingKeys`` condition. So today isolation is STRUCTURAL-ONLY: it rests entirely on
#:      the repository always pinning the ``tenant_id`` partition key (which it does — every
#:      read/write is keyed, and there is no ``.scan()``).
#:   2. The ``${aws:PrincipalTag/tenant_id}`` placeholder needs a per-request ``tenant_id``
#:      principal tag to resolve to. The Lambda runs as a SINGLE SHARED principal with no
#:      per-tenant ``PrincipalTag``, so even if attached the condition would match nothing
#:      meaningful (the tag would be empty/constant, not the caller's tenant). Making it real
#:      requires per-request scoped credentials / session tagging — a larger, live-IAM change
#:      in the ``nonprofit-deploy`` account, deliberately out of scope for the M2 task runner.
#:
#: So: do NOT claim ``LeadingKeys`` enforcement anywhere while this is undeployed. The strong
#: compensating control today is the repository-invariant test in
#: ``sam/tests/test_members_repository_tenant_invariant.py`` (asserts every read/write pins the
#: ``tenant_id`` partition key and that no ``.scan()`` is used). Binding a principal to its
#: tenant is the Step-4 IAM decision, captured here so the repository and provisioning build
#: against one agreed shape.
LEADING_KEYS_IAM_POLICY_PLAN: dict = {
    "Version": "2012-10-17",
    "Statement": [
        {
            "Sid": "TenantScopedMembersAccess",
            "Effect": "Allow",
            "Action": [
                "dynamodb:GetItem",
                "dynamodb:BatchGetItem",
                "dynamodb:Query",
                "dynamodb:PutItem",
                "dynamodb:UpdateItem",
                "dynamodb:DeleteItem",
                "dynamodb:TransactWriteItems",
            ],
            "Resource": "arn:aws:dynamodb:*:*:table/${MEMBERS_TABLE}",
            "Condition": {
                "ForAllValues:StringEquals": {
                    # LeadingKeys == the partition-key values a caller may touch — WOULD bind
                    # a caller to its own tenant (defense in depth over the PK isolation) IF
                    # deployed with a per-request ``tenant_id`` PrincipalTag. Not deployed today
                    # (single shared principal, no such tag) — see the STATUS note above.
                    "dynamodb:LeadingKeys": ["${aws:PrincipalTag/tenant_id}"]
                }
            },
        }
    ],
}


def leading_keys_iam_policy_json() -> str:
    """Return the LeadingKeys IAM policy *plan* as a formatted JSON string (for Step-4 / docs).

    NOTE: this is the UNDEPLOYED plan (see :data:`LEADING_KEYS_IAM_POLICY_PLAN` status note) —
    it is not attached to any principal today. Emitting it (e.g. in a provisioning reminder)
    must not be read as evidence that ``LeadingKeys`` is enforced.
    """
    import json

    return json.dumps(LEADING_KEYS_IAM_POLICY_PLAN, indent=2)
