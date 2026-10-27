"""
SAM pytest for the FORWARD application-form slug reader (spec 12 Task 1.3 / R4; design C3) —
:meth:`sam.members.repository.projection_config_reader.MembersProjectionReader.get_form_slug`.

The forward half of the slug mapping (tenant → slug) resolved by the NORMAL ``tenant_id``-pinned
``config#fields`` partition read. (The REVERSE lookup slug → ``tenant_id`` is the ``_slugs/{slug}``
bucket marker — ``test_slug_marker_store.py`` — NOT a slug-keyed item on this ``tenant_id``-PK
table.)

Pinned WITHOUT AWS via the same in-memory ``FakeTable`` the sibling projection-reader tests use:

- a stored ``slug`` on ``config#fields`` reads back verbatim (trimmed);
- a missing ``config#fields`` row, a missing ``slug`` attribute, or a blank / non-string value all
  degrade to ``None`` (the tenant has no public form address yet) — never a raise, never a guess;
- tenant isolation: the reader only answers the queried partition's slug.

Validates: Requirements R4.4
"""

from __future__ import annotations

import os
import sys

_REPO_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

_BACKEND_SRC = os.path.join(_REPO_ROOT, "backend", "src")
if _BACKEND_SRC not in sys.path:
    sys.path.insert(0, _BACKEND_SRC)

from services import projection_schema as schema

from sam.members.repository.projection_config_reader import MembersProjectionReader


class FakeTable:
    """In-memory stand-in for a boto3 DynamoDB Table (query side only), per-partition isolated."""

    def __init__(self):
        self.store: dict[tuple, dict] = {}

    def put(self, item: dict) -> None:
        self.store[(item[schema.PARTITION_KEY_ATTR], item[schema.SORT_KEY_ATTR])] = (
            dict(item)
        )

    def query(self, KeyConditionExpression=None):
        expr = KeyConditionExpression.get_expression()
        tenant_id = expr["values"][1]
        return {"Items": [dict(v) for k, v in self.store.items() if k[0] == tenant_id]}


def _config_fields_item(tenant_id, *, slug=None, version=1):
    item = {
        schema.PARTITION_KEY_ATTR: tenant_id,
        schema.SORT_KEY_ATTR: schema.build_sort_key(
            schema.RECORD_TYPE_CONFIG, "fields"
        ),
        "fields": {},
        "overrides": {},
        schema.VERSION_ATTR: version,
    }
    if slug is not None:
        item["slug"] = slug
    return item


def test_get_form_slug_returns_stored_slug():
    table = FakeTable()
    table.put(_config_fields_item("h-dcn", slug="hdcn-application-form"))

    reader = MembersProjectionReader(table=table)
    assert reader.get_form_slug("h-dcn") == "hdcn-application-form"


def test_get_form_slug_trims_stored_value():
    table = FakeTable()
    table.put(_config_fields_item("h-dcn", slug="  hdcn-application-form  "))

    reader = MembersProjectionReader(table=table)
    assert reader.get_form_slug("h-dcn") == "hdcn-application-form"


def test_get_form_slug_missing_row_returns_none():
    # No config#fields row at all → the tenant has no public form address yet.
    reader = MembersProjectionReader(table=FakeTable())
    assert reader.get_form_slug("h-dcn") is None


def test_get_form_slug_absent_attribute_returns_none():
    table = FakeTable()
    table.put(
        _config_fields_item("h-dcn")
    )  # config#fields present but no slug authored

    reader = MembersProjectionReader(table=table)
    assert reader.get_form_slug("h-dcn") is None


def test_get_form_slug_blank_value_returns_none():
    table = FakeTable()
    table.put(_config_fields_item("h-dcn", slug="   "))

    reader = MembersProjectionReader(table=table)
    assert reader.get_form_slug("h-dcn") is None


def test_get_form_slug_non_string_value_returns_none():
    table = FakeTable()
    table.put(_config_fields_item("h-dcn", slug=12345))

    reader = MembersProjectionReader(table=table)
    assert reader.get_form_slug("h-dcn") is None


def test_get_form_slug_is_tenant_isolated():
    table = FakeTable()
    table.put(_config_fields_item("h-dcn", slug="hdcn-application-form"))
    table.put(_config_fields_item("zktk-tenant", slug="zktk-application-form"))

    reader = MembersProjectionReader(table=table)
    assert reader.get_form_slug("h-dcn") == "hdcn-application-form"
    assert reader.get_form_slug("zktk-tenant") == "zktk-application-form"
