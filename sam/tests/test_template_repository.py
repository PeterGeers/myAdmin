"""
SAM pytest — repository round-trip of the ``template#`` record type (R2, task 2.2).

Phase 2 testing (tasks.md): "... repository round-trip of ``template#``." These pin the
:class:`DynamoDbMembersRepository` template methods (``save`` / ``get`` / ``list`` /
``delete``) over an in-memory fake DynamoDB table (the ``FakeDynamoTable`` pattern from
``test_members_repository.py`` — no moto, no live AWS), covering:

- a ``save`` → ``get`` → ``list`` → ``delete`` round-trip that preserves the full
  :class:`TemplateEntry` metadata (``to_item`` / ``from_item`` are faithful through the store);
- structural tenant isolation (Property 1) — a second tenant's identically-id'd template is
  invisible, and a cross-tenant write is refused;
- the ``template#<id>`` key shape (the stored item carries the composite sort key).

Validates: Requirements R2 (Property 1)
"""

from __future__ import annotations

import os
import sys

import pytest

_REPO_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)
_BACKEND_SRC = os.path.join(_REPO_ROOT, "backend", "src")
if _BACKEND_SRC not in sys.path:
    sys.path.insert(0, _BACKEND_SRC)

from sam.members.domain.template import TemplateEntry, TemplateLanguage
from sam.members.repository import table_design as td
from sam.members.repository.members_repository import DynamoDbMembersRepository

# ---------------------------------------------------------------------------
# In-memory fake DynamoDB table (the surface the repository uses for templates)
# ---------------------------------------------------------------------------


def _pk(item):
    return item[td.PARTITION_KEY_ATTR]


def _sk(item):
    return item[td.SORT_KEY_ATTR]


class FakeDynamoTable:
    """In-memory stand-in: ``get_item`` / ``put_item`` / ``delete_item`` / ``query``.

    ``query`` honours a partition-key ``eq`` + optional sort-key ``begins_with`` and returns
    ONLY the matching tenant's items, so cross-tenant items are structurally unreturnable —
    the same isolation a real table + IAM ``LeadingKeys`` enforce.
    """

    def __init__(self, name="test_members"):
        self.name = name
        self.store: dict[tuple, dict] = {}

    def get_item(self, Key=None):
        item = self.store.get((Key[td.PARTITION_KEY_ATTR], Key[td.SORT_KEY_ATTR]))
        return {"Item": dict(item)} if item is not None else {}

    def put_item(self, Item=None):
        self.store[(_pk(Item), _sk(Item))] = dict(Item)
        return {}

    def delete_item(self, Key=None):
        self.store.pop((Key[td.PARTITION_KEY_ATTR], Key[td.SORT_KEY_ATTR]), None)
        return {}

    def query(self, KeyConditionExpression=None, ExclusiveStartKey=None):
        tenant_id, sk_prefix = _walk_condition(KeyConditionExpression)
        items = [
            dict(v)
            for k, v in self.store.items()
            if k[0] == tenant_id and (sk_prefix is None or k[1].startswith(sk_prefix))
        ]
        return {"Items": items}


def _walk_condition(condition):
    expr = condition.get_expression()
    op = expr["operator"]
    values = expr["values"]
    if op == "AND":
        tenant_id = None
        sk_prefix = None
        for sub in values:
            t, p = _walk_condition(sub)
            tenant_id = tenant_id if t is None else t
            sk_prefix = sk_prefix if p is None else p
        return tenant_id, sk_prefix
    if op == "=":
        attr = values[0].name
        if attr == td.PARTITION_KEY_ATTR:
            return values[1], None
        return None, None
    if op == "begins_with":
        return None, values[1]
    return None, None  # pragma: no cover


@pytest.fixture()
def table() -> FakeDynamoTable:
    return FakeDynamoTable()


@pytest.fixture()
def repo(table) -> DynamoDbMembersRepository:
    return DynamoDbMembersRepository(table=table)


def _entry(tenant_id="h-dcn", template_id="t1", name="Welcome"):
    return TemplateEntry(
        tenant_id=tenant_id,
        template_id=template_id,
        name=name,
        languages={
            "nl": TemplateLanguage(
                subject="Dag {{first_name}}",
                s3_body_key=f"{tenant_id}/templates/{template_id}/nl.html",
            ),
            "en": TemplateLanguage(
                subject="Hi {{first_name}}",
                s3_body_key=f"{tenant_id}/templates/{template_id}/en.html",
            ),
        },
        merge_fields=["first_name"],
        logo_asset_ref="logo-9",
        origin="user",
        created_by="sub-1",
        created_at="2024-01-01T00:00:00+00:00",
        updated_at="2024-01-01T00:00:00+00:00",
    )


class TestTemplateRepositoryRoundTrip:
    def test_save_get_roundtrip_preserves_metadata(self, repo):
        repo.save_template("h-dcn", _entry())
        got = repo.get_template("h-dcn", "t1")
        assert got == _entry()  # full metadata survives to_item/from_item through the store

    def test_get_absent_returns_none(self, repo):
        assert repo.get_template("h-dcn", "missing") is None

    def test_stored_item_has_template_sort_key(self, repo, table):
        repo.save_template("h-dcn", _entry())
        stored = table.store[("h-dcn", td.template_sk("t1"))]
        assert stored[td.SORT_KEY_ATTR] == "template#t1"
        assert stored["template_id"] == "t1"

    def test_list_sorted_by_name(self, repo):
        repo.save_template("h-dcn", _entry(template_id="a", name="Zeta"))
        repo.save_template("h-dcn", _entry(template_id="b", name="Alpha"))
        names = [e.name for e in repo.list_templates("h-dcn")]
        assert names == ["Alpha", "Zeta"]

    def test_list_excludes_non_template_items(self, repo, table):
        # A sibling record type in the same partition must not surface in list_templates.
        repo.save_template("h-dcn", _entry())
        table.put_item(
            Item={
                td.PARTITION_KEY_ATTR: "h-dcn",
                td.SORT_KEY_ATTR: td.analytics_set_sk("set-1"),
                "set_id": "set-1",
            }
        )
        ids = [e.template_id for e in repo.list_templates("h-dcn")]
        assert ids == ["t1"]

    def test_delete_removes_the_item(self, repo):
        repo.save_template("h-dcn", _entry())
        repo.delete_template("h-dcn", "t1")
        assert repo.get_template("h-dcn", "t1") is None


class TestTemplateRepositoryTenantIsolation:
    def test_second_tenant_same_id_is_invisible(self, repo):
        repo.save_template("h-dcn", _entry(tenant_id="h-dcn", template_id="t1", name="A"))
        repo.save_template("other", _entry(tenant_id="other", template_id="t1", name="B"))
        # Each tenant sees only its own template of the shared id.
        assert repo.get_template("h-dcn", "t1").name == "A"
        assert repo.get_template("other", "t1").name == "B"
        assert [e.name for e in repo.list_templates("h-dcn")] == ["A"]
        assert [e.name for e in repo.list_templates("other")] == ["B"]

    def test_cross_tenant_write_is_refused(self, repo):
        # An entry bound to a different tenant than the caller must be rejected (Property 1).
        with pytest.raises(ValueError):
            repo.save_template("h-dcn", _entry(tenant_id="other", template_id="t1"))

    def test_blank_tenant_is_refused(self, repo):
        with pytest.raises(ValueError):
            repo.get_template("", "t1")
