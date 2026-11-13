"""Get/list/query operations for every aggregate family.

Part of DynamoDbMembersRepository (task 6).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from sam.members.domain.analytics_set import AnalyticsSetEntry
from sam.members.domain.column_preferences import ColumnPreferences
from sam.members.domain.membership_type_catalog import MembershipTypeEntry
from sam.members.domain.preferred_list import PreferredList
from sam.members.domain.schedule import ScheduleEntry
from sam.members.domain.template import TemplateEntry
from sam.members.repository import table_design as td

from ._members_repository_shared import Delegate, Member, Membership, Payment


class MembersReadMixin:
    """Get/list/query operations for every aggregate family."""

    def get_member(self, tenant_id: str, member_id: str) -> Member | None:
        self._require_tenant(tenant_id)
        response = self.table.get_item(
            Key=td.build_key(tenant_id, td.member_sk(member_id))
        )
        return response.get("Item")

    def list_members(
        self,
        tenant_id: str,
        *,
        filters: Mapping[str, Any] | None = None,
    ) -> Sequence[Member]:
        """List the tenant's member records (SK ``member#<id>`` exactly, not their children).

        Isolation is structural: the query pins ``tenant_id`` as the partition key. Scope
        narrowing (the caller's ``allowed_scopes``) is a **domain-layer** concern applied on
        top of this call (a scoped user stays inside their tenant); this method surfaces the
        tenant's members and leaves narrowing to the caller. Child items
        (memberships/delegates/payments/counters/guards) are excluded by shape.
        """
        self._require_tenant(tenant_id)
        members: list[dict] = []
        # A member *record* SK has exactly two segments: ("member", <member_id>). We query
        # every ``member#...`` item in the partition and keep only the bare records (child
        # items — memberships/delegates/payments — share the ``member#`` prefix but have more
        # segments), so a list never leaks a member's sub-entities.
        prefix = td.RECORD_TYPE_MEMBER + td.SORT_KEY_SEPARATOR
        for item in self._query_prefix(tenant_id, prefix):
            segments = td.split_sort_key(item.get(td.SORT_KEY_ATTR, ""))
            if len(segments) == 2 and segments[0] == td.RECORD_TYPE_MEMBER:
                members.append(item)
        return members

    def list_members_page(
        self,
        tenant_id: str,
        *,
        limit: int | None = None,
        start_key: Mapping[str, Any] | None = None,
        filters: Mapping[str, Any] | None = None,
    ) -> tuple[list[Member], dict[str, Any] | None]:
        """Return up to ``limit`` of the tenant's MEMBER records + the resume cursor (Req 25).

        The cursor-paging read path (distinct from :meth:`list_members`, which drains the whole
        partition). ``limit`` means **returned bare member records**, not raw partition items:

        - ``limit`` set (a fixed Rows_Per_Page option 50/100/250/500, R25.2) → the page carries
          up to ``limit`` bare ``member#<id>`` records. The partition interleaves member records
          with their child items (memberships/delegates/payments share the ``member#`` prefix),
          so a single DynamoDB Query ``Limit=limit`` would bound RAW items and under-return
          members once children are mixed in. To make ``limit`` mean member rows, this LOOPS the
          Query over ``LastEvaluatedKey``, collecting bare member records, until it has ``limit``
          of them or the partition is exhausted.
        - ``limit`` ``None`` (the ``Max`` option, R25.3) → no member cap; one ~1 MB Query page's
          members are returned (the natural DynamoDB page boundary, not a full drain).

        Returns ``(members, last_evaluated_key)``. ``last_evaluated_key`` is an HONEST resume key
        for the NEXT page — positioned at the LAST member record returned (so the next page
        continues right after it, skipping that member's trailing children), or ``None`` when the
        partition was exhausted (the final page → the caller surfaces "no next page",
        R25.5/R25.6). ``start_key`` resumes a prior page (the decoded ``ExclusiveStartKey``); it
        is already tenant-checked by the cursor codec before it reaches here, and every Query
        pins ``tenant_id`` as the partition key, so a page can never cross tenants (Property 1).
        """
        self._require_tenant(tenant_id)
        from boto3.dynamodb.conditions import Key

        prefix = td.RECORD_TYPE_MEMBER + td.SORT_KEY_SEPARATOR
        condition = Key(td.PARTITION_KEY_ATTR).eq(tenant_id) & Key(
            td.SORT_KEY_ATTR
        ).begins_with(prefix)

        members: list[dict] = []
        last_member_key: dict[str, Any] | None = None
        exclusive_start: Mapping[str, Any] | None = (
            dict(start_key) if start_key else None
        )

        while True:
            kwargs: dict[str, Any] = {"KeyConditionExpression": condition}
            if exclusive_start:
                kwargs["ExclusiveStartKey"] = dict(exclusive_start)
            # Cap the RAW Query at the number of members still wanted — a lower bound on the raw
            # items needed. Child items interleaved in the window mean we may still have to make
            # another Query to top up, which the LastEvaluatedKey loop below handles.
            if limit is not None:
                remaining = limit - len(members)
                kwargs["Limit"] = remaining

            response = self.table.query(**kwargs)

            for item in response.get("Items", []) or []:
                segments = td.split_sort_key(item.get(td.SORT_KEY_ATTR, ""))
                if len(segments) == 2 and segments[0] == td.RECORD_TYPE_MEMBER:
                    members.append(item)
                    last_member_key = {
                        td.PARTITION_KEY_ATTR: item[td.PARTITION_KEY_ATTR],
                        td.SORT_KEY_ATTR: item[td.SORT_KEY_ATTR],
                    }
                    if limit is not None and len(members) >= limit:
                        # We have a full page of members. The honest next-page cursor resumes
                        # right AFTER this member record (skipping its trailing children), so the
                        # next page starts at the following member — never re-returning this one
                        # and never losing one. ``None`` only if this was truly the last item.
                        raw_last = response.get("LastEvaluatedKey") or None
                        next_key = last_member_key if raw_last is not None else None
                        return members, next_key

            raw_last = response.get("LastEvaluatedKey") or None
            if raw_last is None:
                # Partition exhausted: fewer than ``limit`` members exist (or ``limit`` is None).
                return members, None
            # More raw items remain but we have not yet collected ``limit`` members — continue the
            # Query from DynamoDB's own resume position to top up the page (the multi-Query walk).
            exclusive_start = raw_last
            if limit is None:
                # ``Max`` is ONE ~1 MB Query page; do not drain the whole partition.
                return members, raw_last

    def get_application_session_member(
        self, tenant_id: str, session_key: str
    ) -> str | None:
        """Return the ``member_id`` a session mapped to, or ``None`` if the session is unclaimed.

        A single ``get_item`` on ``appsession#<session_key>`` within the tenant partition
        (isolation is structural — the partition key is pinned to ``tenant_id``; Property 1). A
        resend uses this to resolve the record to UPDATE instead of inserting a second one
        (R3a.2).
        """
        self._require_tenant(tenant_id)
        if not session_key:
            return None
        response = self.table.get_item(
            Key=td.build_key(tenant_id, td.app_session_sk(session_key))
        )
        item = response.get("Item")
        if item is None:
            return None
        member_id = item.get("member_id")
        return str(member_id) if member_id else None

    def query_by_name_dob(self, tenant_id: str, name_dob_key: str) -> Sequence[Member]:
        """Query the ``name_dob_index`` GSI for members matching a normalized name+DOB key.

        A cheap INDEXED read (D25), NOT a partition scan (R3a.8). The GSI hashes on
        ``tenant_id`` and ranges on ``name_dob_key``, so the query pins the tenant (Property 1)
        and matches the exact composite. Returns the matching member items (``ALL`` projection,
        so the caller reads their fields straight off the index). Paginates via
        ``LastEvaluatedKey``. An empty ``name_dob_key`` (an un-indexable record) yields ``[]``
        without a query — it can never match.
        """
        from boto3.dynamodb.conditions import Key

        self._require_tenant(tenant_id)
        if not name_dob_key:
            return []

        condition = Key(td.PARTITION_KEY_ATTR).eq(tenant_id) & Key(
            td.NAME_DOB_KEY_ATTR
        ).eq(name_dob_key)

        items: list[dict] = []
        kwargs: dict = {
            "IndexName": td.NAME_DOB_GSI_INDEX_NAME,
            "KeyConditionExpression": condition,
        }
        while True:
            response = self.table.query(**kwargs)
            items.extend(response.get("Items", []) or [])
            last = response.get("LastEvaluatedKey")
            if not last:
                break
            kwargs["ExclusiveStartKey"] = last
        return items

    def get_membership(
        self, tenant_id: str, member_id: str, membership_id: str
    ) -> Membership | None:
        self._require_tenant(tenant_id)
        response = self.table.get_item(
            Key=td.build_key(tenant_id, td.membership_sk(member_id, membership_id))
        )
        return response.get("Item")

    def list_memberships(self, tenant_id: str, member_id: str) -> Sequence[Membership]:
        self._require_tenant(tenant_id)
        prefix = td.build_sort_key(
            td.RECORD_TYPE_MEMBER, member_id, td.RECORD_TYPE_MEMBERSHIP
        )
        return self._query_prefix(tenant_id, prefix)

    def list_member_delegates(
        self, tenant_id: str, member_id: str
    ) -> Sequence[Delegate]:
        """Return a member's stored delegate set (empty list when none exists).

        The delegate set is a single item under the member (``member#<id>#delegates``); this
        reads it within the tenant partition (isolation is structural — Property 1) and
        returns its ``delegates`` list, or ``[]`` when the member has no delegate item yet.
        """
        self._require_tenant(tenant_id)
        response = self.table.get_item(
            Key=td.build_key(tenant_id, td.delegates_sk(member_id))
        )
        item = response.get("Item")
        if not item:
            return []
        delegates = item.get("delegates")
        return list(delegates) if isinstance(delegates, (list, tuple)) else []

    def list_member_payments(self, tenant_id: str, member_id: str) -> Sequence[Payment]:
        self._require_tenant(tenant_id)
        prefix = td.build_sort_key(
            td.RECORD_TYPE_MEMBER, member_id, td.RECORD_TYPE_PAYMENT
        )
        return self._query_prefix(tenant_id, prefix)

    def list_membership_types(
        self, tenant_id: str, *, active_only: bool = False
    ) -> Sequence[MembershipTypeEntry]:
        """List the tenant's membership-type catalog entries, presentation-ordered.

        Queries the ``membershiptype#`` sub-tree of the tenant partition (isolation is
        structural — the partition key is pinned to ``tenant_id``), rebuilds each stored item
        into a :class:`MembershipTypeEntry`, optionally drops soft-deleted entries, and sorts
        by ``(order, type_code)`` so the dropdown/management view render deterministically.
        """
        self._require_tenant(tenant_id)
        prefix = td.RECORD_TYPE_MEMBERSHIP_TYPE + td.SORT_KEY_SEPARATOR
        entries = [
            MembershipTypeEntry.from_item(item)
            for item in self._query_prefix(tenant_id, prefix)
        ]
        if active_only:
            entries = [e for e in entries if e.active]
        entries.sort(key=lambda e: e.sort_order_key())
        return entries

    def get_membership_type(
        self, tenant_id: str, type_code: str
    ) -> MembershipTypeEntry | None:
        self._require_tenant(tenant_id)
        response = self.table.get_item(
            Key=td.build_key(tenant_id, td.membership_type_sk(type_code))
        )
        item = response.get("Item")
        return MembershipTypeEntry.from_item(item) if item is not None else None

    def get_analytics_set(
        self, tenant_id: str, set_id: str
    ) -> AnalyticsSetEntry | None:
        self._require_tenant(tenant_id)
        response = self.table.get_item(
            Key=td.build_key(tenant_id, td.analytics_set_sk(set_id))
        )
        item = response.get("Item")
        return AnalyticsSetEntry.from_item(item) if item is not None else None

    def list_analytics_sets(self, tenant_id: str) -> Sequence[AnalyticsSetEntry]:
        """List the tenant's analytics-set entries, sorted by ``(name, set_id)``.

        Queries the ``analyticsset#`` sub-tree of the tenant partition (isolation is
        structural — the partition key is pinned to ``tenant_id``), rebuilds each stored item
        into an :class:`AnalyticsSetEntry`, and sorts by ``(name, set_id)`` so the list renders
        deterministically.
        """
        self._require_tenant(tenant_id)
        prefix = td.RECORD_TYPE_ANALYTICS_SET + td.SORT_KEY_SEPARATOR
        entries = [
            AnalyticsSetEntry.from_item(item)
            for item in self._query_prefix(tenant_id, prefix)
        ]
        entries.sort(key=lambda e: e.sort_order_key())
        return entries

    def get_template(self, tenant_id: str, template_id: str) -> TemplateEntry | None:
        """Return the template ``template_id`` for ``tenant_id``, or ``None`` if absent.

        A single ``get_item`` on ``template#<template_id>`` within the tenant partition
        (isolation is structural — the partition key is pinned to ``tenant_id``).
        """
        self._require_tenant(tenant_id)
        response = self.table.get_item(
            Key=td.build_key(tenant_id, td.template_sk(template_id))
        )
        item = response.get("Item")
        return TemplateEntry.from_item(item) if item is not None else None

    def list_templates(self, tenant_id: str) -> Sequence[TemplateEntry]:
        """List the tenant's template entries, sorted by ``(name, template_id)``.

        Queries the ``template#`` sub-tree of the tenant partition (isolation is structural —
        the partition key is pinned to ``tenant_id``), rebuilds each stored item into a
        :class:`TemplateEntry`, and sorts by ``(name, template_id)`` so the list renders
        deterministically.
        """
        self._require_tenant(tenant_id)
        prefix = td.RECORD_TYPE_TEMPLATE + td.SORT_KEY_SEPARATOR
        entries = [
            TemplateEntry.from_item(item)
            for item in self._query_prefix(tenant_id, prefix)
        ]
        entries.sort(key=lambda e: e.sort_order_key())
        return entries

    def get_schedule(self, tenant_id: str, schedule_id: str) -> ScheduleEntry | None:
        """Return the schedule ``schedule_id`` for ``tenant_id``, or ``None`` if absent.

        A single ``get_item`` on ``schedule#<schedule_id>`` within the tenant partition
        (isolation is structural — the partition key is pinned to ``tenant_id``).
        """
        self._require_tenant(tenant_id)
        response = self.table.get_item(
            Key=td.build_key(tenant_id, td.schedule_sk(schedule_id))
        )
        item = response.get("Item")
        return ScheduleEntry.from_item(item) if item is not None else None

    def list_schedules(self, tenant_id: str) -> Sequence[ScheduleEntry]:
        """List the tenant's schedule entries, sorted by ``(set_id, schedule_id)``.

        Queries the ``schedule#`` sub-tree of the tenant partition (isolation is structural —
        the partition key is pinned to ``tenant_id``), rebuilds each stored item into a
        :class:`ScheduleEntry`, and sorts by ``(set_id, schedule_id)`` so the list renders
        deterministically.
        """
        self._require_tenant(tenant_id)
        prefix = td.RECORD_TYPE_SCHEDULE + td.SORT_KEY_SEPARATOR
        entries = [
            ScheduleEntry.from_item(item)
            for item in self._query_prefix(tenant_id, prefix)
        ]
        entries.sort(key=lambda e: e.sort_order_key())
        return entries

    def get_preferred_list(self, tenant_id: str, sub: str) -> PreferredList | None:
        """Return user ``sub``'s preferred list for ``tenant_id``, or ``None`` if unset.

        A single ``get_item`` on ``preflist#<sub>`` within the tenant partition (isolation is
        structural — the partition key is pinned to ``tenant_id``). A missing item → ``None``
        (the domain treats that as an empty list — empty-is-valid, R11).
        """
        self._require_tenant(tenant_id)
        if not sub:
            return None
        response = self.table.get_item(
            Key=td.build_key(tenant_id, td.pref_list_sk(sub))
        )
        item = response.get("Item")
        return PreferredList.from_item(item) if item is not None else None

    def get_column_preferences(
        self, tenant_id: str, sub: str
    ) -> ColumnPreferences | None:
        """Return user ``sub``'s column preferences for ``tenant_id``, or ``None`` if unset.

        A single ``get_item`` on ``colprefs#<sub>`` within the tenant partition (isolation is
        structural — the partition key is pinned to ``tenant_id``). A missing item → ``None``
        (the domain treats that as an empty column set — empty-is-valid, R6.4).
        """
        self._require_tenant(tenant_id)
        if not sub:
            return None
        response = self.table.get_item(
            Key=td.build_key(tenant_id, td.column_prefs_sk(sub))
        )
        item = response.get("Item")
        return ColumnPreferences.from_item(item) if item is not None else None

    def get_mail_run(self, tenant_id: str, run_id: str) -> Mapping[str, Any] | None:
        """Return the ``mailrun#<run_id>`` tally for ``tenant_id``, or ``None`` if absent.

        A single ``get_item`` within the tenant partition (isolation is structural — the
        partition key is pinned to ``tenant_id``; Property 3).
        """
        self._require_tenant(tenant_id)
        if not run_id:
            return None
        response = self.table.get_item(
            Key=td.build_key(tenant_id, td.mail_run_sk(run_id))
        )
        return response.get("Item")

    def list_mail_run_failures(
        self, tenant_id: str, run_id: str
    ) -> Sequence[Mapping[str, Any]]:
        """List a run's FAILURE sub-records (``mailrecipient#<run_id>#…``), tenant-pinned.

        A ``begins_with`` query on the run's failure prefix inside the tenant partition
        (isolation is structural — Property 3). An empty list when the run had no failures
        (the common case — successes are only counted in the tally, not stored).
        """
        self._require_tenant(tenant_id)
        if not run_id:
            return []
        prefix = td.mail_recipient_sk_prefix(run_id) + td.SORT_KEY_SEPARATOR
        return self._query_prefix(tenant_id, prefix)

    def list_mail_runs(self, tenant_id: str) -> Sequence[Mapping[str, Any]]:
        """List the tenant's send-run tallies, NEWEST FIRST (feeds the R9 status/history route).

        Queries the ``mailrun#`` sub-tree of the tenant partition (isolation is structural — the
        partition key is pinned to ``tenant_id``; Property 3) and sorts by ``created_at``
        descending so the history view shows the most recent runs first. Returns only the TALLY
        items (the ``mailrecipient#`` failures live under a different record-type prefix, so they
        are never swept in here).
        """
        self._require_tenant(tenant_id)
        prefix = td.RECORD_TYPE_MAIL_RUN + td.SORT_KEY_SEPARATOR
        runs = list(self._query_prefix(tenant_id, prefix))
        runs.sort(key=lambda r: str(r.get("created_at", "")), reverse=True)
        return runs
