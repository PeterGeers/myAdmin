"""Table schema: constants, sort-key builders and the name-DOB GSI.
Part of table_design (task 8).
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

# --- Config (fail-fast, reuses the T0 client) ------------------------------

#: The Members table-name env var. The value is the full SAM-plane table name —
#: ``sam-members`` (prod) / ``sam-members-test`` (test/dev), the ``sam-`` prefix convention
#: with the environment as a *suffix* — so this module never synthesizes a name: it refuses
#: to guess (no-dangerous-fallback, mirrors ``PROJECTION_TABLE_ENV_VAR``).
MEMBERS_TABLE_ENV_VAR = "MEMBERS_TABLE"


# --- Key schema attribute names (canonical) --------------------------------

#: Partition-key attribute name. Its value is the ``tenant_id`` — the tenancy boundary. Making
#: the tenant the partition key means a query cannot address more than one tenant's partition,
#: so cross-tenant reads are structurally unaddressable (Property 1). This structural pinning
#: is the ONLY tenancy control deployed today: the repository is the sole DynamoDB touch-point
#: and every read/write is keyed by this attribute (there is no ``.scan()`` anywhere).
#:
#: IAM ``dynamodb:LeadingKeys`` (see :data:`LEADING_KEYS_IAM_POLICY_PLAN`) would add a
#: *credential*-level backstop over this structural isolation — but it is a PLAN, NOT deployed
#: (risk S1 / security-assessment-2026-09-26 M2). The Members Lambda runs as a single shared
#: principal with NO per-tenant ``PrincipalTag``, so the ``LeadingKeys`` condition would not
#: constrain anything as-is; deploying it needs per-request session tagging (a live-IAM change
#: out of scope for that task). Do NOT read this attribute's isolation as IAM-enforced today.
PARTITION_KEY_ATTR = "tenant_id"

#: Sort-key attribute name. Holds the ``record_type#id`` composite value (see below).
SORT_KEY_ATTR = "sk"

#: Separator that joins the sort-key segments into the sort-key value.
SORT_KEY_SEPARATOR = "#"


# --- Duplicate-flag GSI (D25, application-app task 2.5) --------------------
#
# The public applicant intake flags a POSSIBLE existing-member duplicate on NAME + DATE OF
# BIRTH (both required, R6.1a — a stronger "same person" key than a reused email). The lookup
# is a cheap INDEXED read, never a public-endpoint partition scan (R3a.8): a Global Secondary
# Index keyed on the SAME ``tenant_id`` partition key (so the index stays tenant-scoped —
# Property 1, LeadingKeys) with a NORMALIZED ``name+dob`` composite as its range key.
#
# The index is SPARSE: ``build_member_item`` writes the :data:`NAME_DOB_KEY_ATTR` attribute
# only when BOTH a usable name AND a birth date are present (:func:`normalize_name_dob_key`
# returns ``None`` otherwise). A member missing either simply does not appear in the index —
# which is exactly right: the name+DOB match requires both, so an un-indexable record can
# never be a match and need not be queried. The GSI is NOT a uniqueness constraint (DynamoDB
# GSIs can't enforce one) — correct, since the flag never blocks a write (R3a.5/R3a.7).

#: GSI name for the name+DOB duplicate-flag lookup (D25). Hash key = :data:`PARTITION_KEY_ATTR`
#: (``tenant_id`` — the index stays inside the tenant, Property 1); range key =
#: :data:`NAME_DOB_KEY_ATTR` (the normalized ``name+dob`` composite).
NAME_DOB_GSI_INDEX_NAME = "name_dob_index"

#: Item attribute holding the normalized ``name+dob`` composite that backs
#: :data:`NAME_DOB_GSI_INDEX_NAME`. Written by :func:`build_member_item` ONLY when
#: :func:`normalize_name_dob_key` yields a non-``None`` key (sparse index). Derived, never
#: client-supplied — it is recomputed from the record's own name parts + ``birth_date`` on
#: every write so it cannot drift from the stored fields.
NAME_DOB_KEY_ATTR = "name_dob_key"

#: Separator joining the normalized name and the canonical DOB in the composite key. A ``|``
#: (not ``#``) so the composite is visibly distinct from the ``record_type#id`` sort-key
#: convention and never collides with a date's own separators.
_NAME_DOB_SEPARATOR = "|"

#: Collapses any run of Unicode whitespace to a single space (name normalization).
_WHITESPACE_RUN = re.compile(r"\s+")


# --- Record-type tokens (leading segments of the SK value) -----------------

RECORD_TYPE_MEMBER = "member"
RECORD_TYPE_MEMBERSHIP = "membership"
RECORD_TYPE_DELEGATES = "delegates"
RECORD_TYPE_PAYMENT = "payment"
# s5k: the ``counter#`` (atomic per-tenant counter) and ``membernum#`` (member-number
# uniqueness guard) record types were REMOVED — member numbering is no longer generated or
# guarded (``member_number`` is a plain optional string). See spec s5k.
#: Lidmaatschap Beheer catalog entry (design C8). A ``membershiptype#<type_code>`` item is one
#: membership type the tenant offers; the member record's ``membership.membership_type``
#: references its ``type_code``. Lives in the tenant partition like every other entity.
RECORD_TYPE_MEMBERSHIP_TYPE = "membershiptype"

#: Analytics-set entity (F-012). An ``analyticsset#<set_id>`` item is one member
#: analytics-set (saved pivot/list definition) the tenant owns; the ``set_id`` is a
#: server-chosen uuid4 hex. Lives in the tenant partition like every other entity.
RECORD_TYPE_ANALYTICS_SET = "analyticsset"

#: A user's PREFERRED LIST of analytics sets (R11.2 layer 2). One item per user, keyed by the
#: user's Cognito ``sub`` (NOT a member_id — user ≠ member, R11.1). SK ``preflist#<sub>``. Holds
#: an ordered list of tagged references (``preset:<key>`` / ``set:<id>``) into the tenant-shared
#: set library. Private to the user; lives in the tenant partition like every other entity.
RECORD_TYPE_PREF_LIST = "preflist"

#: A stored mail TEMPLATE (R2). A ``template#<template_id>`` item holds the template METADATA
#: (name, per-language subjects + S3 body-key refs, merge fields, optional logo asset ref,
#: origin, attribution) on-plane; the body HTML + logo binaries live in S3 ``myadmin-shared``
#: (never inline — a DynamoDB item caps at 400 KB and must not carry binaries). Written
#: module-agnostic (no member-specific logic) so the whole template store can extract to
#: ``sam/shared/templates/`` on a second consumer (steering 35 rule of three). Lives in the
#: tenant partition like every other entity (isolation is structural — the PK is tenant_id).
RECORD_TYPE_TEMPLATE = "template"

#: A stored SCHEDULE (R5). A ``schedule#<schedule_id>`` item holds the recurring-run metadata
#: for a saved analytics-set + its delivery block (``set_id`` + the EventBridge Scheduler
#: ``cron`` expression + ``created_by`` + ``enabled``). The tenant is PINNED here because an
#: unattended run has no interactive user (R5). The entity is storage-only — the "the set must
#: have a delivery block" rule is a SERVICE/route gate (task 5.2), not a storage concern. Lives
#: in the tenant partition like every other entity (isolation is structural — the PK is
#: tenant_id).
RECORD_TYPE_SCHEDULE = "schedule"

#: A user's chosen OVERVIEW COLUMNS (session-columns spec R6.2). One item per user, keyed by the
#: user's Cognito ``sub`` (NOT a member_id — user ≠ member, R11.1). SK ``colprefs#<sub>`` (mirrors
#: ``preflist#<sub>``). Holds an ordered list of field keys (references into the field config)
#: the user surfaces as columns. Private to the user; lives in the tenant partition like every
#: other entity (isolation is structural — the PK is pinned to tenant_id).
RECORD_TYPE_COLUMN_PREFS = "colprefs"

#: A **mail-sent idempotency marker** (R4, pivot-output-actions task 4.3). A
#: ``mailsent#<job_id>`` item records that the worker already SENT the send job with that
#: stable ``job_id`` (design §4.2 — SQS is at-least-once, so a redelivery of the same job must
#: be a no-op, not a second send). The worker writes it with a conditional
#: ``attribute_not_exists`` put BEFORE sending — a redelivery's put fails the condition, the
#: worker sees the marker, and it skips the send. Metadata-only (job id + run id + a timestamp +
#: a TTL) — never message bodies or member PII. Lives in the tenant partition like every other
#: entity (the PK is tenant_id — a marker can only ever match within its own tenant).
RECORD_TYPE_MAIL_SENT = "mailsent"

#: A **send-run status TALLY** (R9.1, mail-spec task 3.1). A ``mailrun#<run_id>`` item holds the
#: AGGREGATED status of one logical send run — ``mode`` / ``triggered_by`` / ``recipient_count`` /
#: ``status`` (``queued`` → ``sending`` → ``completed``) / ``sent`` / ``failed`` + timestamps. The
#: enqueue path writes it at ``queued`` with the recipient count; the worker advances the status
#: and increments ``sent`` / ``failed`` as it processes jobs. Successful recipients are only
#: COUNTED here (no per-recipient row) — the design's "summary tally + FAILURE-ONLY sub-records"
#: decision. Carries a ``ttl`` epoch attribute (DynamoDB TTL, default 90 days). Lives in the tenant
#: partition like every other entity (the PK is tenant_id — a run only ever matches within its own
#: tenant; Property 3).
RECORD_TYPE_MAIL_RUN = "mailrun"

#: A **FAILURE-ONLY per-recipient sub-record** (R9.1/R9.5, mail-spec task 3.1). A
#: ``mailrecipient#<run_id>#<n>`` item is written ONLY for a FAILURE of a send run — a send-time
#: reject / no-address / a LATE async bounce / complaint (R8.4). It carries ``run_id`` /
#: ``address`` / ``status`` (``failed`` / ``bounced`` / ``complaint``) / ``reason`` /
#: ``message_id`` / ``updated_at``. Successes are NOT stored (they are counted in the run tally).
#: The ``<n>`` segment is a per-run FAILURE sequence / discriminator so two failures of a run never
#: collide. Carries a ``ttl`` epoch attribute (default 90 days). Lives in the tenant partition like
#: every other entity (the PK is tenant_id — Property 3).
RECORD_TYPE_MAIL_RECIPIENT = "mailrecipient"

#: A **public-application SESSION de-dup marker** (R3a, application-app task 2.1). An
#: ``appsession#<session_key>`` item records the ``member_id`` the FIRST submit of a public
#: application form session created, so a resend within the same fill-in session resolves to that
#: same record and UPDATES it rather than inserting a second one (R3a.1-R3a.3). It is the public
#: intake's analogue of the mail worker's ``mailsent#<job_id>`` idempotency marker: the repository
#: writes it with a CONDITIONAL ``attribute_not_exists`` put, so a near-simultaneous double submit
#: (impatient click / retry) races to a SINGLE create -- the first put wins, the rest read the
#: existing marker and update the mapped member. Carries the session key, the mapped ``member_id``,
#: a timestamp, and a ``ttl`` epoch (stale sessions expire). Metadata only -- never form field
#: values / applicant PII. Lives in the tenant partition like every other entity (the PK is
#: tenant_id -- a session marker can only ever match within its own tenant; Property 1).
RECORD_TYPE_APP_SESSION = "appsession"


# --- Sort-key composition / parsing ----------------------------------------


def build_sort_key(*segments: str) -> str:
    """Join sort-key ``segments`` into the composite value stored under :data:`SORT_KEY_ATTR`.

    This is the *only* place the ``#``-join convention is applied, so the repository, the
    Step-4 provisioning, and the backfill cannot diverge on the format. Prefer the typed
    helpers (:func:`member_sk`, :func:`membership_sk`, ...) over calling this directly.

    Args:
        *segments: One or more non-empty segments (e.g. ``("member", member_id)``).

    Returns:
        The composite sort-key string.

    Raises:
        ValueError: No segments were given, or a segment is empty / contains the separator
            (which would make the key ambiguous to parse).
    """
    if not segments:
        raise ValueError("at least one sort-key segment is required")
    for segment in segments:
        if segment is None or segment == "":
            raise ValueError(f"sort-key segments must be non-empty: {segments!r}")
        if SORT_KEY_SEPARATOR in segment:
            raise ValueError(
                f"sort-key segment {segment!r} must not contain the separator "
                f"{SORT_KEY_SEPARATOR!r} (it would make the key ambiguous)"
            )
    return SORT_KEY_SEPARATOR.join(segments)


def split_sort_key(sort_key_value: str) -> tuple[str, ...]:
    """Split a sort-key value back into its segments (inverse of :func:`build_sort_key`).

    Args:
        sort_key_value: The composite value stored under :data:`SORT_KEY_ATTR`.

    Returns:
        The tuple of segments, e.g. ``("member", "M-1", "membership", "MS-9")``.

    Raises:
        ValueError: The value is empty.
    """
    if not sort_key_value:
        raise ValueError("sort-key value must be a non-empty string")
    return tuple(sort_key_value.split(SORT_KEY_SEPARATOR))


# --- Name+DOB normalization + GSI definition (D25, duplicate flag) ---------


def _normalize_name_part(value: Any) -> str:
    """Trim + collapse-whitespace + casefold one name part (``""`` for an absent/blank part).

    ``casefold`` (not ``lower``) so case differences across locales fold consistently; internal
    whitespace runs collapse to a single space so ``"van  der"`` and ``"van der"`` agree.
    """
    if value is None:
        return ""
    text = _WHITESPACE_RUN.sub(" ", str(value).strip())
    return text.casefold()


def normalize_name_dob_key(
    first_name: Any,
    name_infix: Any,
    last_name: Any,
    birth_date: Any,
) -> str | None:
    """Build the normalized ``name+dob`` composite key for the duplicate-flag GSI (D25).

    Normalization (pinned here — design §12 left the exact shape to the build):

    - **Name:** the three name parts (``first_name`` + ``name_infix`` + ``last_name``) are each
      trimmed, internal-whitespace-collapsed, and case-folded, then joined with a single space
      in that fixed order (``"sam van der berg"``). The order is canonical so two records with
      the same parts always produce the same key.
    - **DOB:** ``birth_date`` is trimmed. The platform stores it as an ISO ``YYYY-MM-DD`` string
      (``fixed_fields`` / ``calculated_fields._parse_iso_date``), so it is already canonical; we
      only strip surrounding whitespace rather than re-parse (a malformed value still keys
      consistently and simply won't match a well-formed one — the flag never blocks).
    - **Composite:** ``"<name>|<dob>"``.

    Returns ``None`` when EITHER the combined name is empty OR the DOB is blank — the match
    signal requires BOTH (R6.1a). A ``None`` key means the record is NOT written into the sparse
    index (it can never be a name+DOB match, so it need not be indexed or queried).
    """
    name = " ".join(
        part
        for part in (
            _normalize_name_part(first_name),
            _normalize_name_part(name_infix),
            _normalize_name_part(last_name),
        )
        if part
    )
    dob = "" if birth_date is None else str(birth_date).strip()
    if not name or not dob:
        return None
    return f"{name}{_NAME_DOB_SEPARATOR}{dob}"


def _name_dob_key_from_member(member: Mapping[str, Any]) -> str | None:
    """Derive the normalized name+DOB key from a member payload's ``personal`` bucket.

    Reads ``personal.{first_name, name_infix, last_name, birth_date}`` (the platform's fixed
    name/DOB fields) and runs :func:`normalize_name_dob_key`. Tolerant of a missing/odd-shaped
    ``personal`` bucket (returns ``None`` — un-indexable, never raises on a write path).
    """
    personal = member.get("personal")
    if not isinstance(personal, Mapping):
        return None
    return normalize_name_dob_key(
        personal.get("first_name"),
        personal.get("name_infix"),
        personal.get("last_name"),
        personal.get("birth_date"),
    )


def name_dob_gsi_attribute_definition() -> dict:
    """The AttributeDefinition the GSI range key needs (``name_dob_key``, type ``S``).

    The table's PK ``tenant_id`` is ALREADY defined for the base table; a GSI only needs the
    NEW key attribute declared. Returned separately so the provisioner can append exactly this
    one definition without re-declaring the base keys.
    """
    return {"AttributeName": NAME_DOB_KEY_ATTR, "AttributeType": "S"}


def name_dob_gsi_definition() -> dict:
    """The ``GlobalSecondaryIndexes`` entry for the name+DOB duplicate-flag GSI (D25).

    Hash key = ``tenant_id`` (the base PK — the index stays tenant-scoped, Property 1); range
    key = ``name_dob_key`` (the normalized composite). ``ALL`` projection so the duplicate
    check can read the matched member's id/fields from the index alone (no base-table follow-up
    read on the public path). No provisioned throughput block — the table is PAY_PER_REQUEST, so
    the GSI inherits on-demand billing.
    """
    return {
        "IndexName": NAME_DOB_GSI_INDEX_NAME,
        "KeySchema": [
            {"AttributeName": PARTITION_KEY_ATTR, "KeyType": "HASH"},
            {"AttributeName": NAME_DOB_KEY_ATTR, "KeyType": "RANGE"},
        ],
        "Projection": {"ProjectionType": "ALL"},
    }


# --- Typed SK builders (one per access pattern) ----------------------------


def member_sk(member_id: str) -> str:
    """SK for a member record: ``member#<member_id>``."""
    return build_sort_key(RECORD_TYPE_MEMBER, member_id)


def membership_sk(member_id: str, membership_id: str) -> str:
    """SK for a membership of a member: ``member#<member_id>#membership#<membership_id>``."""
    return build_sort_key(
        RECORD_TYPE_MEMBER, member_id, RECORD_TYPE_MEMBERSHIP, membership_id
    )


def delegates_sk(member_id: str) -> str:
    """SK for a member's delegate set (a single item): ``member#<member_id>#delegates``."""
    return build_sort_key(RECORD_TYPE_MEMBER, member_id, RECORD_TYPE_DELEGATES)


def payment_sk(member_id: str, payment_id: str) -> str:
    """SK for a member-scoped payment: ``member#<member_id>#payment#<payment_id>``."""
    return build_sort_key(
        RECORD_TYPE_MEMBER, member_id, RECORD_TYPE_PAYMENT, payment_id
    )


def membership_type_sk(type_code: str) -> str:
    """SK for a Lidmaatschap Beheer catalog entry: ``membershiptype#<type_code>`` (C8)."""
    return build_sort_key(RECORD_TYPE_MEMBERSHIP_TYPE, type_code)


def analytics_set_sk(set_id: str) -> str:
    """SK for an analytics-set entry: ``analyticsset#<set_id>`` (F-012)."""
    return build_sort_key(RECORD_TYPE_ANALYTICS_SET, set_id)


def template_sk(template_id: str) -> str:
    """SK for a stored mail-template entry: ``template#<template_id>`` (R2)."""
    return build_sort_key(RECORD_TYPE_TEMPLATE, template_id)


def schedule_sk(schedule_id: str) -> str:
    """SK for a stored schedule entry: ``schedule#<schedule_id>`` (R5)."""
    return build_sort_key(RECORD_TYPE_SCHEDULE, schedule_id)


def pref_list_sk(sub: str) -> str:
    """SK for a user's preferred-list entry: ``preflist#<sub>`` (R11.2).

    Keyed by the user's Cognito ``sub`` (the authenticated principal — user ≠ member, R11.1),
    one item per user. ``sub`` must be non-blank and contain no key separator (an opaque
    Cognito sub never does).
    """
    return build_sort_key(RECORD_TYPE_PREF_LIST, sub)


def column_prefs_sk(sub: str) -> str:
    """SK for a user's column-preferences entry: ``colprefs#<sub>`` (session-columns R6.2).

    Mirrors :func:`pref_list_sk`. Keyed by the user's Cognito ``sub`` (the authenticated
    principal — user ≠ member, R11.1), one item per user. ``sub`` must be non-blank and contain
    no key separator (an opaque Cognito sub never does).
    """
    return build_sort_key(RECORD_TYPE_COLUMN_PREFS, sub)


def mail_sent_marker_sk(job_id: str) -> str:
    """SK for a mail-sent idempotency marker: ``mailsent#<job_id>`` (R4, task 4.3).

    ``job_id`` is the stable idempotency id the execute-and-deliver service derives for one
    send job (design §4.2). The worker conditionally puts this marker (``attribute_not_exists``)
    before sending, so an at-least-once SQS redelivery of the same job finds the marker and
    skips a second send. ``job_id`` must be non-blank and contain no key separator (the
    service's SHA-256 hex id never does).
    """
    return build_sort_key(RECORD_TYPE_MAIL_SENT, job_id)


def app_session_sk(session_key: str) -> str:
    """SK for a public-application session de-dup marker: ``appsession#<session_key>`` (R3a).

    ``session_key`` is the stable id the public form mints on first render and sends on every
    submit of that fill-in session (R3a.1). The repository conditionally puts this marker
    (``attribute_not_exists``) on the first submit so a near-simultaneous resend of the SAME
    session finds the marker and UPDATES the member it mapped instead of creating a second
    record (R3a.2/R3a.3) — the public-intake analogue of the mail worker's ``mailsent#<job_id>``
    dedupe. ``session_key`` must be non-blank and contain no key separator (a uuid4-style id the
    form mints never does).
    """
    return build_sort_key(RECORD_TYPE_APP_SESSION, session_key)


def mail_run_sk(run_id: str) -> str:
    """SK for a send-run status tally: ``mailrun#<run_id>`` (R9.1, mail-spec task 3.1).

    ``run_id`` is the caller-supplied id for ONE logical send run (the deliver route / the
    scheduler mints it; shared by every job of a ``per_recipient`` fan-out — see
    ``execute_and_deliver.DeliveryOutcome.run_id``). It must be non-blank and contain no key
    separator (a scheduled run id like ``schedule:<id>:<ts>`` would — so callers that fold a
    composite into the SK must sanitize; the service's own run ids do not carry ``#``).
    """
    return build_sort_key(RECORD_TYPE_MAIL_RUN, run_id)


def mail_recipient_sk(run_id: str, seq: str) -> str:
    """SK for a FAILURE-ONLY per-recipient sub-record: ``mailrecipient#<run_id>#<seq>``.

    (R9.1/R9.5, mail-spec task 3.1.) ``seq`` is a per-run FAILURE discriminator so two failures
    of the same run never collide — the repository derives it from the failure count (or a late
    bounce's own ordinal). Both segments must be non-blank and contain no key separator.
    """
    return build_sort_key(RECORD_TYPE_MAIL_RECIPIENT, run_id, seq)


def mail_recipient_sk_prefix(run_id: str) -> str:
    """The SK prefix that selects every FAILURE sub-record of one run (R9.1).

    ``mailrecipient#<run_id>`` is a prefix of every ``mailrecipient#<run_id>#<seq>`` item, so a
    single ``begins_with`` Query inside the tenant partition fetches all of a run's failures
    (still tenant-scoped — the partition key is fixed; Property 3). ``run_id`` must be non-blank
    and contain no key separator.
    """
    return build_sort_key(RECORD_TYPE_MAIL_RECIPIENT, run_id)


def member_sk_prefix(member_id: str) -> str:
    """The SK prefix that selects a member and everything hanging off it.

    ``member#<member_id>`` is a prefix of the member item's own SK *and* of its memberships,
    delegates, and payments — so a single ``begins_with`` Query inside the tenant partition
    fetches the member and all its children (still tenant-scoped: the partition key is fixed).
    """
    return build_sort_key(RECORD_TYPE_MEMBER, member_id)


# --- Full-key + item builders ----------------------------------------------


def build_key(tenant_id: str, sort_key_value: str) -> dict[str, str]:
    """Build a full DynamoDB primary key dict for a Members item.

    Args:
        tenant_id: The tenant (partition key). Must be non-empty — a blank tenant would be a
            cross-tenant hazard (Property 1).
        sort_key_value: The composite sort-key value (see the ``*_sk`` builders).

    Returns:
        ``{PARTITION_KEY_ATTR: tenant_id, SORT_KEY_ATTR: sort_key_value}`` — the shape boto3
        expects for ``get_item`` / ``put_item`` / ``update_item`` keys.

    Raises:
        ValueError: ``tenant_id`` or ``sort_key_value`` is empty.
    """
    if not tenant_id:
        raise ValueError(
            "tenant_id (partition key) must be non-empty — a blank tenant is a "
            "cross-tenant hazard (Property 1)"
        )
    if not sort_key_value:
        raise ValueError("sort_key_value (sort key) must be non-empty")
    return {PARTITION_KEY_ATTR: tenant_id, SORT_KEY_ATTR: sort_key_value}
