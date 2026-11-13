"""Shared key/query/TTL helpers used by the mixins.

Part of DynamoDbMembersRepository (task 6).
"""

from __future__ import annotations

from datetime import datetime, timezone

from sam.members.repository import table_design as td


class MembersQueriesMixin:
    """Shared key/query/TTL helpers used by the mixins."""

    @staticmethod
    def _require_tenant(tenant_id: str) -> None:
        """Guard: no operation is allowed without an explicit tenant (Property 1)."""
        if not tenant_id:
            raise ValueError(
                "tenant_id is required — every Members operation is tenant-scoped "
                "(no cross-tenant access, Property 1)"
            )

    def _query_prefix(self, tenant_id: str, sk_prefix: str) -> list[dict]:
        """Query one tenant partition for items whose SK begins with ``sk_prefix``.

        The partition key is pinned to ``tenant_id`` (isolation) and the sort-key
        ``begins_with`` narrows to the requested sub-tree — still entirely inside the tenant's
        partition. Paginates via ``LastEvaluatedKey`` so large members are fully returned.
        """
        from boto3.dynamodb.conditions import Key

        condition = Key(td.PARTITION_KEY_ATTR).eq(tenant_id) & Key(
            td.SORT_KEY_ATTR
        ).begins_with(sk_prefix)

        items: list[dict] = []
        kwargs: dict = {"KeyConditionExpression": condition}
        while True:
            response = self.table.query(**kwargs)
            items.extend(response.get("Items", []) or [])
            last = response.get("LastEvaluatedKey")
            if not last:
                break
            kwargs["ExclusiveStartKey"] = last
        return items

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _ttl_epoch() -> int:
        """The DynamoDB TTL epoch (default 90 days from now) for a send-run status record."""
        from sam.members.repository.members_repository import MAIL_RUN_TTL_SECONDS

        return int(datetime.now(timezone.utc).timestamp()) + MAIL_RUN_TTL_SECONDS
