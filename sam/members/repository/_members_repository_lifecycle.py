"""Delete/claim lifecycle operations.

Part of DynamoDbMembersRepository (task 6).
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

from botocore.exceptions import ClientError

from sam.members.repository import table_design as td

from ._members_repository_shared import APP_SESSION_TTL_SECONDS


class MembersLifecycleMixin:
    """Delete/claim lifecycle operations."""

    def delete_member(self, tenant_id: str, member_id: str) -> None:
        """Delete a member record.

        s5k: a single ``DeleteItem`` of the member record. There is no ``membernum#`` guard to
        release (the uniqueness-guard mechanism was removed — see spec s5k), so no transaction is
        needed. (Memberships/delegates/payments are removed by the domain layer's higher-level
        flows / Step 5.)
        """
        self._require_tenant(tenant_id)
        self.table.delete_item(Key=td.build_key(tenant_id, td.member_sk(member_id)))

    def claim_application_session(
        self, tenant_id: str, session_key: str, member_id: str
    ) -> bool:
        """Claim an application session for ``member_id`` iff unclaimed; True iff THIS call claimed.

        A CONDITIONAL ``PutItem`` with ``attribute_not_exists(<sort key>)`` so only the FIRST
        submit of a ``session_key`` creates the ``appsession#<session_key>`` marker (``True`` →
        created / this call owns the create); a concurrent/later resend fails the condition
        (``False`` → already claimed → the caller reads the mapped member and updates it). This
        is the conditional-write that resolves a double-submit race to a single record (R3a.3).
        """
        self._require_tenant(tenant_id)
        if not session_key or not member_id:
            raise ValueError(
                "application-session claim requires a non-empty session_key and member_id"
            )
        now = datetime.now(timezone.utc)
        item: dict[str, Any] = {
            td.PARTITION_KEY_ATTR: tenant_id,
            td.SORT_KEY_ATTR: td.app_session_sk(session_key),
            "session_key": session_key,
            "member_id": member_id,
            "created_at": now.isoformat(),
            "ttl": int(now.timestamp()) + APP_SESSION_TTL_SECONDS,
        }
        try:
            self.table.put_item(
                Item=td.floats_to_decimal(item),
                ConditionExpression=f"attribute_not_exists({td.SORT_KEY_ATTR})",
            )
            return True
        except ClientError as exc:
            code = ""
            response = getattr(exc, "response", None)
            if isinstance(response, Mapping):
                error = response.get("Error")
                if isinstance(error, Mapping):
                    code = str(error.get("Code", ""))
            if code == "ConditionalCheckFailedException":
                return False  # session already claimed → resend → caller updates that record
            raise

    def delete_membership(
        self, tenant_id: str, member_id: str, membership_id: str
    ) -> None:
        self._require_tenant(tenant_id)
        self.table.delete_item(
            Key=td.build_key(tenant_id, td.membership_sk(member_id, membership_id))
        )

    def delete_analytics_set(self, tenant_id: str, set_id: str) -> None:
        """Hard-delete an analytics-set (F-012 — no referencing records to orphan)."""
        self._require_tenant(tenant_id)
        self.table.delete_item(Key=td.build_key(tenant_id, td.analytics_set_sk(set_id)))

    def delete_template(self, tenant_id: str, template_id: str) -> None:
        """Hard-delete a template's metadata item for ``tenant_id``.

        Deletes only the ``template#<template_id>`` metadata item; the service is responsible
        for cleaning up the template's S3 body/logo objects through its body-store seam.
        """
        self._require_tenant(tenant_id)
        self.table.delete_item(Key=td.build_key(tenant_id, td.template_sk(template_id)))

    def delete_schedule(self, tenant_id: str, schedule_id: str) -> None:
        """Hard-delete a schedule for ``tenant_id`` (no referencing records to orphan)."""
        self._require_tenant(tenant_id)
        self.table.delete_item(Key=td.build_key(tenant_id, td.schedule_sk(schedule_id)))

    def delete_mail_run(self, tenant_id: str, run_id: str) -> None:
        """Manual-delete a run tally AND all its FAILURE sub-records (R9 retention; tenant-pinned).

        Deletes the ``mailrun#<run_id>`` tally and every ``mailrecipient#<run_id>#…`` failure
        sub-record so a manual delete leaves no orphaned failures behind (the complement to the
        TTL auto-cleanup). Every delete is keyed by ``tenant_id`` (Property 3).
        """
        self._require_tenant(tenant_id)
        if not run_id:
            raise ValueError("run_id must be non-empty")
        for failure in self.list_mail_run_failures(tenant_id, run_id):
            sk = failure.get(td.SORT_KEY_ATTR)
            if sk:
                self.table.delete_item(Key=td.build_key(tenant_id, sk))
        self.table.delete_item(Key=td.build_key(tenant_id, td.mail_run_sk(run_id)))
