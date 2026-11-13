"""Item builders and template S3 key helpers.
Part of table_design (task 8).
"""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal
from typing import Any

from ._table_schema import (
    NAME_DOB_KEY_ATTR,
    PARTITION_KEY_ATTR,
    SORT_KEY_ATTR,
    _name_dob_key_from_member,
    analytics_set_sk,
    build_key,
    column_prefs_sk,
    mail_recipient_sk,
    mail_run_sk,
    member_sk,
    membership_type_sk,
    pref_list_sk,
    schedule_sk,
    template_sk,
)


def floats_to_decimal(value: Any) -> Any:
    """Recursively convert every ``float`` in ``value`` to :class:`~decimal.Decimal`.

    DynamoDB (boto3) refuses Python ``float`` — it stores numbers as ``Decimal`` and raises
    ``"Float types are not supported. Use Decimal types instead."`` on a ``put_item`` /
    ``transact_write_items`` that carries one. Source data (e.g. the h-dcn backfill's
    ``overlay.Bedrag`` fee, a JSON float) can therefore reach a write untouched. This helper is
    applied by every item builder below so no write path can hand boto3 a raw float, no matter
    how deeply nested inside ``personal`` / ``membership`` / ``overlay`` / lists it sits.

    ``Decimal(str(f))`` (not ``Decimal(f)``) is used deliberately: converting via the float's
    ``repr`` avoids dragging in binary-float artefacts (e.g. ``Decimal(22.6)`` →
    ``22.6000000000000014...``), so ``22.6`` round-trips as ``Decimal('22.6')``. This mirrors
    the read-side convention (numbers deserialize as ``Decimal`` and ``from_item`` coerces back
    — see ``test_membership_type_catalog.test_from_item_coerces_numeric_order``).

    ``bool`` is intentionally left alone (it is a DynamoDB BOOL, and ``bool`` is a subclass of
    ``int`` so it must not be caught by any numeric branch). ``int`` is already valid and is
    passed through unchanged.

    Args:
        value: Any JSON-ish value — scalar, ``Mapping``, or sequence.

    Returns:
        A new value of the same shape with every ``float`` replaced by an equivalent
        ``Decimal``. Non-float values are returned as-is (dicts/lists are rebuilt).
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, float):
        return Decimal(str(value))
    if isinstance(value, Mapping):
        return {k: floats_to_decimal(v) for k, v in value.items()}
    # Recurse into lists/tuples/sets of values, but never strings/bytes (they are scalars).
    if isinstance(value, (list, tuple)):
        return [floats_to_decimal(v) for v in value]
    return value


def build_member_item(
    tenant_id: str, member_id: str, member: Mapping[str, Any]
) -> dict:
    """Compose the stored DynamoDB item for a member record.

    Stamps the tenant partition key and the ``member#<member_id>`` sort key onto a copy of the
    domain-layer ``member`` payload (fixed base ⊕ overlay + ``scope_values``). The caller's
    ``tenant_id`` (from the verified context) is authoritative — any ``tenant_id`` already on
    the payload is overwritten so a domain-layer mistake can never land a record in the wrong
    partition.

    Args:
        tenant_id: The tenant (partition key).
        member_id: The member id (sort-key id segment).
        member: The domain member payload (``personal`` / ``membership`` / ``scope_values`` /
            ``overlay`` per the design data model).

    Returns:
        A new dict ready for ``put_item`` — the payload plus the primary key attributes.

    Raises:
        ValueError: ``tenant_id`` or ``member_id`` is empty.
    """
    if not member_id:
        raise ValueError("member_id must be non-empty")
    # Deep-copy with float→Decimal coercion so nested payload numbers (e.g. overlay.Bedrag)
    # are DynamoDB-safe before any write path serializes this item.
    item = floats_to_decimal(dict(member))
    item[PARTITION_KEY_ATTR] = tenant_id  # authoritative — overwrite any payload value
    item[SORT_KEY_ATTR] = member_sk(member_id)
    # Keep the bare id addressable without re-parsing the sort key.
    item.setdefault("member_id", member_id)
    # Duplicate-flag GSI key (D25): DERIVE the normalized name+DOB composite from the record's
    # own name parts + birth_date on every write (never trust a client-supplied value — it is
    # recomputed so it can't drift from the stored fields). SPARSE: only set when both a name
    # and a DOB are present; drop any stale value otherwise so a record that LOSES its name/DOB
    # leaves the index. This makes the name+DOB possible-duplicate lookup a cheap indexed read.
    name_dob_key = _name_dob_key_from_member(item)
    if name_dob_key is not None:
        item[NAME_DOB_KEY_ATTR] = name_dob_key
    else:
        item.pop(NAME_DOB_KEY_ATTR, None)
    # Fail-fast if the composed key would be invalid (blank tenant, etc.).
    build_key(tenant_id, item[SORT_KEY_ATTR])
    return item


def build_membership_type_item(
    tenant_id: str, type_code: str, entry: Mapping[str, Any]
) -> dict:
    """Compose the stored DynamoDB item for a Lidmaatschap Beheer catalog entry (C8).

    Stamps the tenant partition key and the ``membershiptype#<type_code>`` sort key onto a
    copy of the domain-layer ``entry`` payload (``label`` / ``active`` / ``order``). The
    caller's ``tenant_id`` and ``type_code`` are authoritative — any values already on the
    payload are overwritten so a domain-layer mistake can never land an entry in the wrong
    partition or under the wrong code.

    Args:
        tenant_id: The tenant (partition key).
        type_code: The catalog entry's code (sort-key id segment; also the member reference).
        entry: The domain entry payload (``label`` / ``active`` / ``order``; see C8).

    Returns:
        A new dict ready for ``put_item`` — the payload plus the primary-key + reference attrs.

    Raises:
        ValueError: ``tenant_id`` or ``type_code`` is empty.
    """
    if not type_code:
        raise ValueError("type_code must be non-empty")
    item = floats_to_decimal(dict(entry))  # DynamoDB-safe numbers (float→Decimal)
    item[PARTITION_KEY_ATTR] = tenant_id  # authoritative — overwrite any payload value
    item[SORT_KEY_ATTR] = membership_type_sk(type_code)
    # Keep the reference code addressable without re-parsing the sort key. (tenant_id is
    # already the partition-key attribute, stamped above.)
    item["type_code"] = type_code
    # Fail-fast if the composed key would be invalid (blank tenant, etc.).
    build_key(tenant_id, item[SORT_KEY_ATTR])
    return item


def build_analytics_set_item(
    tenant_id: str, set_id: str, entry: Mapping[str, Any]
) -> dict:
    """Compose the stored DynamoDB item for an analytics-set entry (F-012).

    Stamps the tenant partition key and the ``analyticsset#<set_id>`` sort key onto a copy of
    the domain-layer ``entry`` payload (``name`` / ``kind`` / ``definition`` / ``created_at`` /
    ``updated_at``). The caller's ``tenant_id`` and ``set_id`` are authoritative — any values
    already on the payload are overwritten so a domain-layer mistake can never land an entry in
    the wrong partition or under the wrong id.

    Args:
        tenant_id: The tenant (partition key).
        set_id: The analytics-set id (sort-key id segment; server-chosen uuid4 hex).
        entry: The domain entry payload (``name`` / ``kind`` / ``definition`` / timestamps).

    Returns:
        A new dict ready for ``put_item`` — the payload plus the primary-key + id attrs.

    Raises:
        ValueError: ``tenant_id`` or ``set_id`` is empty.
    """
    if not set_id:
        raise ValueError("set_id must be non-empty")
    item = floats_to_decimal(dict(entry))  # DynamoDB-safe numbers (float→Decimal)
    item[PARTITION_KEY_ATTR] = tenant_id  # authoritative — overwrite any payload value
    item[SORT_KEY_ATTR] = analytics_set_sk(set_id)
    # Keep the id addressable without re-parsing the sort key.
    item["set_id"] = set_id
    # Fail-fast if the composed key would be invalid (blank tenant, etc.).
    build_key(tenant_id, item[SORT_KEY_ATTR])
    return item


def build_template_item(
    tenant_id: str, template_id: str, entry: Mapping[str, Any]
) -> dict:
    """Compose the stored DynamoDB item for a mail-template METADATA entry (R2).

    Stamps the tenant partition key and the ``template#<template_id>`` sort key onto a copy of
    the domain-layer ``entry`` payload (``name`` / ``languages`` / ``merge_fields`` /
    ``logo_asset_ref`` / ``origin`` / ``created_by`` / timestamps). The caller's ``tenant_id``
    and ``template_id`` are authoritative — any values already on the payload are overwritten so
    a domain-layer mistake can never land an entry in the wrong partition or under the wrong id.

    Only METADATA is stored here. The template body HTML + any logo binary live in S3 under the
    tenant-prefixed layout (see :func:`template_body_s3_key` / :func:`template_logo_s3_key`) and
    are referenced by key — never inlined (400 KB item limit + binary).

    Args:
        tenant_id: The tenant (partition key).
        template_id: The template id (sort-key id segment; server-chosen).
        entry: The domain entry payload (template metadata).

    Returns:
        A new dict ready for ``put_item`` — the payload plus the primary-key + id attrs.

    Raises:
        ValueError: ``tenant_id`` or ``template_id`` is empty.
    """
    if not template_id:
        raise ValueError("template_id must be non-empty")
    item = floats_to_decimal(dict(entry))  # DynamoDB-safe numbers (float→Decimal)
    item[PARTITION_KEY_ATTR] = tenant_id  # authoritative — overwrite any payload value
    item[SORT_KEY_ATTR] = template_sk(template_id)
    # Keep the id addressable without re-parsing the sort key.
    item["template_id"] = template_id
    # Fail-fast if the composed key would be invalid (blank tenant, etc.).
    build_key(tenant_id, item[SORT_KEY_ATTR])
    return item


def build_schedule_item(
    tenant_id: str, schedule_id: str, entry: Mapping[str, Any]
) -> dict:
    """Compose the stored DynamoDB item for a schedule entry (R5).

    Stamps the tenant partition key and the ``schedule#<schedule_id>`` sort key onto a copy of
    the domain-layer ``entry`` payload (``set_id`` / ``cron`` / ``created_by`` / ``enabled`` /
    timestamps). The caller's ``tenant_id`` and ``schedule_id`` are authoritative — any values
    already on the payload are overwritten so a domain-layer mistake can never land an entry in
    the wrong partition or under the wrong id. The tenant is PINNED here (an unattended run has
    no interactive user — R5).

    Args:
        tenant_id: The tenant (partition key).
        schedule_id: The schedule id (sort-key id segment; server-chosen).
        entry: The domain entry payload (schedule metadata).

    Returns:
        A new dict ready for ``put_item`` — the payload plus the primary-key + id attrs.

    Raises:
        ValueError: ``tenant_id`` or ``schedule_id`` is empty.
    """
    if not schedule_id:
        raise ValueError("schedule_id must be non-empty")
    item = floats_to_decimal(dict(entry))  # DynamoDB-safe numbers (float→Decimal)
    item[PARTITION_KEY_ATTR] = tenant_id  # authoritative — overwrite any payload value
    item[SORT_KEY_ATTR] = schedule_sk(schedule_id)
    # Keep the id addressable without re-parsing the sort key.
    item["schedule_id"] = schedule_id
    # Fail-fast if the composed key would be invalid (blank tenant, etc.).
    build_key(tenant_id, item[SORT_KEY_ATTR])
    return item


def build_pref_list_item(tenant_id: str, sub: str, entry: Mapping[str, Any]) -> dict:
    """Compose the stored DynamoDB item for a user's preferred-list entry (R11.2).

    Stamps the tenant partition key and the ``preflist#<sub>`` sort key onto a copy of the
    domain-layer ``entry`` payload (``refs`` / ``updated_at``). The caller's ``tenant_id`` and
    ``sub`` are authoritative — any values already on the payload are overwritten so a
    domain-layer mistake can never land an entry in the wrong partition or under the wrong
    user. ``sub`` is the owner key (user ≠ member — R11.1).

    Args:
        tenant_id: The tenant (partition key).
        sub: The owning user's Cognito ``sub`` (sort-key id segment).
        entry: The domain entry payload (``refs`` list + ``updated_at``).

    Returns:
        A new dict ready for ``put_item`` — the payload plus the primary-key + ``sub`` attr.

    Raises:
        ValueError: ``tenant_id`` or ``sub`` is empty.
    """
    if not sub:
        raise ValueError("sub must be non-empty")
    item = floats_to_decimal(dict(entry))  # DynamoDB-safe numbers (float→Decimal)
    item[PARTITION_KEY_ATTR] = tenant_id  # authoritative — overwrite any payload value
    item[SORT_KEY_ATTR] = pref_list_sk(sub)
    # Keep the owner sub addressable without re-parsing the sort key.
    item["sub"] = sub
    # Fail-fast if the composed key would be invalid (blank tenant, etc.).
    build_key(tenant_id, item[SORT_KEY_ATTR])
    return item


def build_column_prefs_item(tenant_id: str, sub: str, entry: Mapping[str, Any]) -> dict:
    """Compose the stored DynamoDB item for a user's column-preferences entry (R6.2).

    Modeled 1:1 on :func:`build_pref_list_item`. Stamps the tenant partition key and the
    ``colprefs#<sub>`` sort key onto a copy of the domain-layer ``entry`` payload (``columns`` /
    ``updated_at``). The caller's ``tenant_id`` and ``sub`` are authoritative — any values
    already on the payload are overwritten so a domain-layer mistake can never land an entry in
    the wrong partition or under the wrong user. ``sub`` is the owner key (user ≠ member —
    R11.1).

    Args:
        tenant_id: The tenant (partition key).
        sub: The owning user's Cognito ``sub`` (sort-key id segment).
        entry: The domain entry payload (``columns`` list + ``updated_at``).

    Returns:
        A new dict ready for ``put_item`` — the payload plus the primary-key + ``sub`` attr.

    Raises:
        ValueError: ``tenant_id`` or ``sub`` is empty.
    """
    if not sub:
        raise ValueError("sub must be non-empty")
    item = floats_to_decimal(dict(entry))  # DynamoDB-safe numbers (float→Decimal)
    item[PARTITION_KEY_ATTR] = tenant_id  # authoritative — overwrite any payload value
    item[SORT_KEY_ATTR] = column_prefs_sk(sub)
    # Keep the owner sub addressable without re-parsing the sort key.
    item["sub"] = sub
    # Fail-fast if the composed key would be invalid (blank tenant, etc.).
    build_key(tenant_id, item[SORT_KEY_ATTR])
    return item


def build_mail_run_item(tenant_id: str, run_id: str, entry: Mapping[str, Any]) -> dict:
    """Compose the stored DynamoDB item for a send-run status TALLY (R9.1, mail-spec task 3.1).

    Stamps the tenant partition key and the ``mailrun#<run_id>`` sort key onto a copy of the
    ``entry`` payload (``mode`` / ``triggered_by`` / ``recipient_count`` / ``status`` / ``sent`` /
    ``failed`` / timestamps / ``ttl``). The caller's ``tenant_id`` and ``run_id`` are
    authoritative — any values already on the payload are overwritten so a domain-layer mistake
    can never land a run in the wrong partition or under the wrong id (Property 3). Only aggregate
    metadata is stored — never message bodies or member PII.

    Args:
        tenant_id: The tenant (partition key).
        run_id: The logical run id (sort-key id segment).
        entry: The run-tally payload.

    Returns:
        A new dict ready for ``put_item`` — the payload plus the primary-key + ``run_id`` attr.

    Raises:
        ValueError: ``tenant_id`` or ``run_id`` is empty.
    """
    if not run_id:
        raise ValueError("run_id must be non-empty")
    item = floats_to_decimal(dict(entry))  # DynamoDB-safe numbers (float→Decimal)
    item[PARTITION_KEY_ATTR] = tenant_id  # authoritative — overwrite any payload value
    item[SORT_KEY_ATTR] = mail_run_sk(run_id)
    # Keep the id addressable without re-parsing the sort key.
    item["run_id"] = run_id
    # Fail-fast if the composed key would be invalid (blank tenant, etc.).
    build_key(tenant_id, item[SORT_KEY_ATTR])
    return item


def build_mail_recipient_item(
    tenant_id: str, run_id: str, seq: str, entry: Mapping[str, Any]
) -> dict:
    """Compose the stored DynamoDB item for a FAILURE-ONLY recipient sub-record (R9.1/R9.5).

    (mail-spec task 3.1.) Stamps the tenant partition key and the
    ``mailrecipient#<run_id>#<seq>`` sort key onto a copy of the ``entry`` payload (``address`` /
    ``status`` / ``reason`` / ``message_id`` / ``updated_at``). The caller's ``tenant_id`` /
    ``run_id`` / ``seq`` are authoritative — any values already on the payload are overwritten so
    a domain-layer mistake can never land a record in the wrong partition or under the wrong id
    (Property 3). Written ONLY for a failure — a success is counted in the run tally, not stored.

    Args:
        tenant_id: The tenant (partition key).
        run_id: The logical run id (first sort-key id segment; also stored as ``run_id``).
        seq: The per-run failure discriminator (second sort-key id segment).
        entry: The failure payload.

    Returns:
        A new dict ready for ``put_item`` — the payload plus the primary-key + ``run_id`` attr.

    Raises:
        ValueError: ``tenant_id`` / ``run_id`` / ``seq`` is empty.
    """
    if not run_id:
        raise ValueError("run_id must be non-empty")
    if not seq:
        raise ValueError("seq must be non-empty")
    item = floats_to_decimal(dict(entry))  # DynamoDB-safe numbers (float→Decimal)
    item[PARTITION_KEY_ATTR] = tenant_id  # authoritative — overwrite any payload value
    item[SORT_KEY_ATTR] = mail_recipient_sk(run_id, seq)
    # Keep the run id addressable without re-parsing the sort key.
    item["run_id"] = run_id
    # Fail-fast if the composed key would be invalid (blank tenant, etc.).
    build_key(tenant_id, item[SORT_KEY_ATTR])
    return item


# --- S3 body/logo layout for stored templates (R2) -------------------------
#
# The template METADATA lives on-plane (``template#<id>`` above); the body HTML + any logo
# binary live in the shared S3 bucket ``myadmin-shared`` (``infrastructure/s3.tf`` — the
# tenant-prefixed home for invoice/branding/template storage). This module is the SINGLE place
# that assembles the S3 KEY LAYOUT, mirroring how it is the single place the DynamoDB sort-key
# shape is assembled — so the template service, the S3 reader/writer, and any backfill agree on
# one definition instead of each re-deriving the path.
#
# The bucket NAME (``myadmin-shared-<env>``) is environment config resolved elsewhere (e.g. the
# ``S3_SHARED_BUCKET`` env var); this module owns only the KEY (the object path WITHIN the
# bucket). Every key is TENANT-PREFIXED (``<tenant>/templates/...``) per steering 23 — the same
# tenant-prefix convention the invoice/branding storage already uses, so a tenant's objects are
# addressable only under its own prefix (the storage-side counterpart to the DynamoDB
# partition-key isolation).

#: The fixed path segment under a tenant's prefix that groups all template objects. The full
#: key is ``<tenant>/templates/<template_id>/...``.
# Tenant-first key layout: <tenant>/<service-path>/templates/<id>/...
# The service path namespaces the owning (sub)service so one shared bucket can hold many
# services' assets without collision, migration-safe for the Flask->nonprofit consolidation.
TEMPLATE_SERVICE_PATH = "members/mail"
TEMPLATE_S3_PREFIX = "templates"


def _require_s3_segment(name: str, value: str) -> str:
    """Guard an S3-key segment: non-blank and free of ``/`` (which would alter the path).

    A blank ``tenant`` would hoist an object out of its tenant prefix (a cross-tenant storage
    hazard — the S3 counterpart to a blank partition key); a ``/`` in any id segment would
    silently inject extra path levels. Both are refused so a key is never ambiguous.
    """
    if not isinstance(value, str) or not value:
        raise ValueError(f"{name} must be a non-empty string (S3-key segment)")
    if "/" in value:
        raise ValueError(
            f"{name} {value!r} must not contain '/' (it would alter the S3 key path)"
        )
    return value


def template_s3_prefix(tenant: str, template_id: str) -> str:
    """The tenant-prefixed S3 key prefix for one template's objects (R2).

    Returns ``<tenant>/templates/<template_id>`` — the common prefix under which a template's
    body (per language) and logo live. Tenant-prefixed per steering 23 (a tenant's objects are
    addressable only under its own prefix).

    Raises:
        ValueError: ``tenant`` or ``template_id`` is blank or contains ``/``.
    """
    _require_s3_segment("tenant", tenant)
    _require_s3_segment("template_id", template_id)
    return f"{tenant}/{TEMPLATE_SERVICE_PATH}/{TEMPLATE_S3_PREFIX}/{template_id}"


def template_body_s3_key(tenant: str, template_id: str, lang: str) -> str:
    """S3 key for a template's body HTML in a given language (R2).

    Returns ``<tenant>/templates/<template_id>/<lang>.html`` (design §2.2). This is the value a
    language entry's ``s3_body_key`` points at. Tenant-prefixed per steering 23.

    Args:
        tenant: The owning tenant (key prefix = tenancy boundary).
        template_id: The template id.
        lang: The language code (e.g. ``nl`` / ``en``).

    Raises:
        ValueError: Any segment is blank or contains ``/``.
    """
    _require_s3_segment("lang", lang)
    return f"{template_s3_prefix(tenant, template_id)}/{lang}.html"


def template_logo_s3_key(tenant: str, template_id: str, filename: str) -> str:
    """S3 key for a template's logo/image binary (R2).

    Returns ``<tenant>/templates/<template_id>/logo/<filename>`` — a ``logo/`` sub-prefix keeps
    binary assets separate from the per-language HTML bodies. Tenant-prefixed per steering 23.

    Args:
        tenant: The owning tenant (key prefix = tenancy boundary).
        template_id: The template id.
        filename: The logo object's file name (e.g. ``logo.png``).

    Raises:
        ValueError: ``tenant`` / ``template_id`` is blank or contains ``/``, or ``filename`` is
            blank. (A ``filename`` may NOT contain ``/`` either — it is a single object name.)
    """
    _require_s3_segment("filename", filename)
    return f"{template_s3_prefix(tenant, template_id)}/logo/{filename}"


# --- Table-name resolution + resource (fail-fast, reuses the T0 client) ----
