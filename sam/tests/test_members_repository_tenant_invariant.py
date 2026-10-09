"""
Security-assessment-2026-09-26 M2 (risk S1) — the tenant-isolation INVARIANT test.

Context / decision (path b)
---------------------------
Tenant isolation on the SAM Members plane rests on TWO possible controls:

  1. STRUCTURAL — the repository (the sole DynamoDB touch-point, design C6) always pins the
     ``tenant_id`` partition key on every read/write, so a caller literally cannot address
     another tenant's partition (Property 1). This is deployed today.
  2. IAM ``dynamodb:LeadingKeys`` — a credential-level backstop. This is a documented PLAN
     ONLY (:data:`sam.members.repository.table_design.LEADING_KEYS_IAM_POLICY_PLAN`); it is
     NOT attached to the Members Lambda, which runs as a single shared principal with no
     per-tenant ``PrincipalTag``. Deploying it would need per-request session tagging (a
     live-IAM change), out of scope for the M2 task runner.

Because the IAM backstop is undeployed, the STRUCTURAL control is the whole of tenancy today.
This module is the STRONG COMPENSATING CONTROL the M2 task requires: it fails if ANY
repository read/write path can issue a DynamoDB operation that omits the ``tenant_id``
partition-key condition, and it fails if any ``.scan()`` (which is NOT partition-scoped) ever
appears in the SAM Members plane. It is deliberately exhaustive over the public repository
surface — a new unscoped method, or a slip to ``.scan()``, breaks the build.

This complements ``test_members_repository.py`` (behavioural round-trips): here we assert the
*mechanism* — the exact key every call carries — not just observable isolation.

Validates: Requirements — security-assessment-2026-09-26 M2 (risk S1); design Property 1 (C6).
"""

from __future__ import annotations

import ast
import inspect
import os
import sys

import pytest

# repo root + backend/src on sys.path (mirrors test_members_repository.py) so
# `sam.members...` and its `services.dynamodb_client` dependency both import.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)
_BACKEND_SRC = os.path.join(_REPO_ROOT, "backend", "src")
if _BACKEND_SRC not in sys.path:
    sys.path.insert(0, _BACKEND_SRC)

from sam.members.domain.analytics_set import AnalyticsSetEntry
from sam.members.domain.column_preferences import ColumnPreferences
from sam.members.domain.membership_type_catalog import MembershipTypeEntry
from sam.members.domain.preferred_list import PreferredList
from sam.members.domain.schedule import ScheduleEntry
from sam.members.domain.template import TemplateEntry, TemplateLanguage
from sam.members.repository import members_repository as repo_mod
from sam.members.repository import table_design as td
from sam.members.repository.members_repository import DynamoDbMembersRepository

TENANT = "tenant-a"


# ---------------------------------------------------------------------------
# A recording fake that captures the EXACT key/condition of every DynamoDB call
# the repository issues, then lets us assert each one pins the tenant partition.
# ---------------------------------------------------------------------------


class RecordingTable:
    """In-memory DynamoDB table stand-in that RECORDS every call for later assertion.

    Unlike a plain fake, this one keeps a structured log of every ``get_item`` /
    ``put_item`` / ``delete_item`` / ``query`` so the test can inspect the tenant partition
    key that each carried. It intentionally has NO ``scan`` method: any repository slip to
    ``.scan()`` raises ``AttributeError`` and fails the test loudly.
    """

    def __init__(self, name="test_members"):
        self.name = name
        self.store: dict[tuple, dict] = {}
        self.calls: list[dict] = []
        self.meta = _FakeMeta(_RecordingClient(self))

    # -- reads -------------------------------------------------------------
    def get_item(self, Key=None):
        self.calls.append({"op": "get_item", "pk": Key.get(td.PARTITION_KEY_ATTR), "key": Key})
        item = self.store.get((Key[td.PARTITION_KEY_ATTR], Key[td.SORT_KEY_ATTR]))
        return {"Item": dict(item)} if item is not None else {}

    def query(self, KeyConditionExpression=None, ExclusiveStartKey=None):
        pk, sk_prefix = _walk_condition(KeyConditionExpression)
        self.calls.append({"op": "query", "pk": pk, "sk_prefix": sk_prefix})
        items = [
            dict(v)
            for k, v in self.store.items()
            if k[0] == pk and (sk_prefix is None or k[1].startswith(sk_prefix))
        ]
        return {"Items": items}

    # -- writes ------------------------------------------------------------
    def put_item(self, Item=None):
        self.calls.append({"op": "put_item", "pk": Item.get(td.PARTITION_KEY_ATTR), "item": Item})
        self.store[(Item[td.PARTITION_KEY_ATTR], Item[td.SORT_KEY_ATTR])] = dict(Item)
        return {}

    def delete_item(self, Key=None):
        self.calls.append({"op": "delete_item", "pk": Key.get(td.PARTITION_KEY_ATTR), "key": Key})
        self.store.pop((Key[td.PARTITION_KEY_ATTR], Key[td.SORT_KEY_ATTR]), None)
        return {}

    # NOTE: deliberately NO `scan` method — a repository `.scan()` would AttributeError.


class _FakeMeta:
    def __init__(self, client):
        self.client = client


class _RecordingClient:
    def __init__(self, table: RecordingTable):
        self._table = table


def _walk_condition(condition):
    """Extract ``(tenant_id, sk_prefix|None)`` from a boto3 Key condition (eq / begins_with)."""
    expr = condition.get_expression()
    op = expr["operator"]
    values = expr["values"]
    if op == "AND":
        pk = None
        sk_prefix = None
        for sub in values:
            t, p = _walk_condition(sub)
            pk = pk if t is None else t
            sk_prefix = sk_prefix if p is None else p
        return pk, sk_prefix
    if op == "=":
        attr = values[0].name
        if attr == td.PARTITION_KEY_ATTR:
            return values[1], None
        return None, None
    if op == "begins_with":
        return None, values[1]
    return None, None  # pragma: no cover


@pytest.fixture()
def table() -> RecordingTable:
    return RecordingTable()


@pytest.fixture()
def repo(table) -> DynamoDbMembersRepository:
    return DynamoDbMembersRepository(table=table, client=table.meta.client)


def _member(member_id: str, number="1001") -> dict:
    return {
        "member_id": member_id,
        "personal": {"first_name": "Alex", "email": f"{member_id}@x.com"},
        "membership": {"member_number": number, "status": "active"},
    }


def _mtype(type_code: str) -> MembershipTypeEntry:
    return MembershipTypeEntry(
        tenant_id=TENANT, type_code=type_code, label={"nl": type_code}, active=True, order=0
    )


def _aset(set_id: str) -> AnalyticsSetEntry:
    return AnalyticsSetEntry(
        tenant_id=TENANT,
        set_id=set_id,
        name="A set",
        kind="list",
        definition={"data_source": "members", "group_columns": [], "aggregate_measures": []},
        created_at="2024-01-01T00:00:00+00:00",
        updated_at="2024-01-01T00:00:00+00:00",
    )


def _pref(sub: str) -> PreferredList:
    return PreferredList(
        tenant_id=TENANT,
        sub=sub,
        refs=["preset:jubilees"],
        updated_at="2024-01-01T00:00:00+00:00",
    )


def _colprefs(sub: str) -> ColumnPreferences:
    return ColumnPreferences(
        tenant_id=TENANT,
        sub=sub,
        columns=["years_member"],
        updated_at="2024-01-01T00:00:00+00:00",
    )


def _schedule(schedule_id: str) -> ScheduleEntry:
    return ScheduleEntry(
        tenant_id=TENANT,
        schedule_id=schedule_id,
        set_id="set-1",
        cron="cron(0 8 1 * ? *)",
        created_by="sub-1",
        enabled=True,
        created_at="2024-01-01T00:00:00+00:00",
        updated_at="2024-01-01T00:00:00+00:00",
    )


def _template(template_id: str) -> TemplateEntry:
    return TemplateEntry(
        tenant_id=TENANT,
        template_id=template_id,
        name="A template",
        languages={
            "nl": TemplateLanguage(
                subject="Dag {{first_name}}",
                s3_body_key=f"{TENANT}/templates/{template_id}/nl.html",
            )
        },
        merge_fields=["first_name"],
        created_at="2024-01-01T00:00:00+00:00",
        updated_at="2024-01-01T00:00:00+00:00",
    )


# Every read/write path on the public repository surface, as a callable driven with a fixed
# tenant. Keeping this list exhaustive is the point: if a new method is added it should be
# added here too (see the completeness test below, which fails on an untested public method).
def _all_repository_operations(repo: DynamoDbMembersRepository):
    return {
        "get_member": lambda: repo.get_member(TENANT, "M-1"),
        "list_members": lambda: repo.list_members(TENANT),
        "save_member": lambda: repo.save_member(TENANT, _member("M-1")),
        "delete_member": lambda: repo.delete_member(TENANT, "M-1"),
        "get_membership": lambda: repo.get_membership(TENANT, "M-1", "MS-1"),
        "list_memberships": lambda: repo.list_memberships(TENANT, "M-1"),
        "save_membership": lambda: repo.save_membership(
            TENANT, "M-1", {"membership_id": "MS-1", "status": "active"}
        ),
        "delete_membership": lambda: repo.delete_membership(TENANT, "M-1", "MS-1"),
        "save_delegates": lambda: repo.save_delegates(TENANT, "M-1", [{"email": "d@x.com"}]),
        "list_member_delegates": lambda: repo.list_member_delegates(TENANT, "M-1"),
        "list_member_payments": lambda: repo.list_member_payments(TENANT, "M-1"),
        "list_membership_types": lambda: repo.list_membership_types(TENANT),
        "get_membership_type": lambda: repo.get_membership_type(TENANT, "erelid"),
        "save_membership_type": lambda: repo.save_membership_type(TENANT, _mtype("erelid")),
        "deactivate_membership_type": lambda: (
            repo.save_membership_type(TENANT, _mtype("erelid")),
            repo.deactivate_membership_type(TENANT, "erelid"),
        ),
        "get_analytics_set": lambda: repo.get_analytics_set(TENANT, "set-1"),
        "list_analytics_sets": lambda: repo.list_analytics_sets(TENANT),
        "save_analytics_set": lambda: repo.save_analytics_set(TENANT, _aset("set-1")),
        "delete_analytics_set": lambda: repo.delete_analytics_set(TENANT, "set-1"),
        "get_template": lambda: repo.get_template(TENANT, "t-1"),
        "list_templates": lambda: repo.list_templates(TENANT),
        "save_template": lambda: repo.save_template(TENANT, _template("t-1")),
        "delete_template": lambda: repo.delete_template(TENANT, "t-1"),
        "get_schedule": lambda: repo.get_schedule(TENANT, "sch-1"),
        "list_schedules": lambda: repo.list_schedules(TENANT),
        "save_schedule": lambda: repo.save_schedule(TENANT, _schedule("sch-1")),
        "delete_schedule": lambda: repo.delete_schedule(TENANT, "sch-1"),
        "get_preferred_list": lambda: repo.get_preferred_list(TENANT, "sub-1"),
        "save_preferred_list": lambda: repo.save_preferred_list(TENANT, _pref("sub-1")),
        "get_column_preferences": lambda: repo.get_column_preferences(TENANT, "sub-1"),
        "save_column_preferences": lambda: repo.save_column_preferences(
            TENANT, _colprefs("sub-1")
        ),
        "create_mail_run": lambda: repo.create_mail_run(
            TENANT, "run-1", mode="per_recipient", triggered_by="sub-1", recipient_count=3
        ),
        "update_mail_run_status": lambda: (
            repo.create_mail_run(
                TENANT, "run-1", mode="per_recipient", triggered_by="sub-1", recipient_count=3
            ),
            repo.update_mail_run_status(TENANT, "run-1", "sending"),
        ),
        "increment_mail_run_counts": lambda: (
            repo.create_mail_run(
                TENANT, "run-1", mode="per_recipient", triggered_by="sub-1", recipient_count=3
            ),
            repo.increment_mail_run_counts(TENANT, "run-1", sent=1),
        ),
        "record_mail_failure": lambda: (
            repo.create_mail_run(
                TENANT, "run-1", mode="per_recipient", triggered_by="sub-1", recipient_count=3
            ),
            repo.record_mail_failure(TENANT, "run-1", address="x@y.com", reason="MessageRejected"),
        ),
        "get_mail_run": lambda: repo.get_mail_run(TENANT, "run-1"),
        "list_mail_run_failures": lambda: repo.list_mail_run_failures(TENANT, "run-1"),
        "list_mail_runs": lambda: repo.list_mail_runs(TENANT),
        "delete_mail_run": lambda: (
            repo.create_mail_run(
                TENANT, "run-1", mode="per_recipient", triggered_by="sub-1", recipient_count=3
            ),
            repo.record_mail_failure(TENANT, "run-1", address="x@y.com"),
            repo.delete_mail_run(TENANT, "run-1"),
        ),
    }


# ---------------------------------------------------------------------------
# 1. Every read/write DynamoDB call pins the tenant partition key.
# ---------------------------------------------------------------------------


class TestEveryOperationPinsTheTenantPartition:
    @pytest.mark.parametrize(
        "op_name",
        [
            "get_member",
            "list_members",
            "save_member",
            "delete_member",
            "get_membership",
            "list_memberships",
            "save_membership",
            "delete_membership",
            "save_delegates",
            "list_member_delegates",
            "list_member_payments",
            "list_membership_types",
            "get_membership_type",
            "save_membership_type",
            "deactivate_membership_type",
            "get_analytics_set",
            "list_analytics_sets",
            "save_analytics_set",
            "delete_analytics_set",
            "get_template",
            "list_templates",
            "save_template",
            "delete_template",
            "get_schedule",
            "list_schedules",
            "save_schedule",
            "delete_schedule",
            "get_preferred_list",
            "save_preferred_list",
            "get_column_preferences",
            "save_column_preferences",
            "create_mail_run",
            "update_mail_run_status",
            "increment_mail_run_counts",
            "record_mail_failure",
            "get_mail_run",
            "list_mail_run_failures",
            "list_mail_runs",
            "delete_mail_run",
        ],
    )
    def test_operation_only_touches_the_callers_tenant_partition(self, repo, table, op_name):
        ops = _all_repository_operations(repo)
        ops[op_name]()
        # At least one DynamoDB call must have been issued...
        assert table.calls, f"{op_name} issued no DynamoDB call"
        # ...and EVERY call it issued must carry the caller's tenant as the partition key.
        for call in table.calls:
            assert call["pk"] == TENANT, (
                f"{op_name} issued a {call['op']} whose partition key was {call['pk']!r}, "
                f"not the caller's tenant {TENANT!r} — tenant isolation would leak"
            )

    def test_no_call_ever_uses_the_scan_operation(self, repo, table):
        # The RecordingTable has no `scan` — a slip would AttributeError. Belt-and-suspenders:
        # drive every op and assert none recorded a scan.
        for run in _all_repository_operations(repo).values():
            run()
        assert not any(c["op"] == "scan" for c in table.calls)


# ---------------------------------------------------------------------------
# 2. A second tenant's data is structurally invisible (the observable payoff).
# ---------------------------------------------------------------------------


class TestCrossTenantIsInvisible:
    def test_reads_never_return_another_tenants_records(self, repo):
        repo.save_member("tenant-a", _member("M-1"))
        repo.save_membership("tenant-a", "M-1", {"membership_id": "MS-1"})
        repo.save_membership_type("tenant-a", _mtype("erelid"))
        # Same ids, different tenant — all must come back empty / None.
        assert repo.get_member("tenant-b", "M-1") is None
        assert list(repo.list_members("tenant-b")) == []
        assert repo.get_membership("tenant-b", "M-1", "MS-1") is None
        assert list(repo.list_memberships("tenant-b", "M-1")) == []
        assert repo.get_membership_type("tenant-b", "erelid") is None
        assert list(repo.list_membership_types("tenant-b")) == []

    def test_blank_tenant_is_refused_on_every_write_and_read(self, repo):
        for run in (
            lambda: repo.get_member("", "M-1"),
            lambda: repo.list_members(""),
            lambda: repo.save_member("", _member("M-1")),
            lambda: repo.delete_member("", "M-1"),
            lambda: repo.save_membership_type("", _mtype("erelid")),
        ):
            with pytest.raises(ValueError):
                run()


# ---------------------------------------------------------------------------
# 3. Static guards: no `.scan(` and no untested public repository method.
# ---------------------------------------------------------------------------


class TestStaticSurfaceGuards:
    def test_repository_source_never_calls_scan(self):
        # `.scan()` is NOT partition-scoped and would read across tenants — it must never
        # appear in the sole DynamoDB touch-point.
        source = inspect.getsource(repo_mod)
        tree = ast.parse(source)
        scan_calls = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Attribute) and node.attr == "scan"
        ]
        assert not scan_calls, "repository must not use DynamoDB .scan() (reads across tenants)"

    def test_every_public_repository_method_is_covered_by_the_invariant(self, repo):
        # Completeness guard: if a new public method is added to the repository, it MUST be
        # added to _all_repository_operations (and thus PK-checked). This fails the build if a
        # new persistence path ships without a tenant-partition assertion.
        covered = set(_all_repository_operations(repo).keys())
        public = {
            name
            for name in dir(DynamoDbMembersRepository)
            if not name.startswith("_")
            and callable(getattr(DynamoDbMembersRepository, name))
            and not isinstance(
                inspect.getattr_static(DynamoDbMembersRepository, name), property
            )
        }
        missing = public - covered
        assert not missing, (
            f"new public repository method(s) {sorted(missing)} are not exercised by the "
            f"tenant-partition invariant — add them to _all_repository_operations"
        )


# ---------------------------------------------------------------------------
# 4. Docs/plan honesty: LeadingKeys is a PLAN, and the shape stays agreed.
# ---------------------------------------------------------------------------


class TestLeadingKeysIsDocumentedAsPlanOnly:
    def test_plan_docstring_marks_it_undeployed(self):
        # Guard against silently re-claiming enforcement: the module must keep saying so.
        module_src = inspect.getsource(td)
        assert "NOT DEPLOYED" in module_src
        assert "structural" in module_src.lower()

    def test_plan_shape_is_still_the_agreed_tenant_scoped_condition(self):
        plan = td.LEADING_KEYS_IAM_POLICY_PLAN
        condition = plan["Statement"][0]["Condition"]["ForAllValues:StringEquals"]
        assert condition["dynamodb:LeadingKeys"] == ["${aws:PrincipalTag/tenant_id}"]
