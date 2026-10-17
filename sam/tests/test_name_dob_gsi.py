"""
application-app task 2.5 — tests for the name+DOB duplicate-flag GSI (D25).

These pin the table-shape half of the flag (the service-level flag behaviour lives in
``test_create_application_duplicate_flag.py``):

- :func:`sam.members.repository.table_design.normalize_name_dob_key` — the EXACT key
  normalization pinned in the build (trim + collapse-whitespace + casefold the three name parts,
  canonical order, ``<name>|<dob>`` composite; ``None`` when name OR dob is missing — both are
  required, R6.1a).
- :func:`build_member_item` writes the ``name_dob_key`` attribute ONLY when both a name and a
  DOB are present (SPARSE index), derived from the record's own fields (never client-trusted),
  and DROPS a stale value when the record loses its name/DOB.
- :func:`name_dob_gsi_definition` / :func:`name_dob_gsi_attribute_definition` — the GSI shape the
  provisioner/template reference: HASH ``tenant_id`` (tenant-scoped, Property 1), RANGE
  ``name_dob_key``.
- :meth:`DynamoDbMembersRepository.query_by_name_dob` — the cheap INDEXED read (not a scan),
  tenant-pinned.

Validates: Requirements R3a.5, R3a.6, R3a.8, R6.1a
"""

from __future__ import annotations

import os
import sys

import pytest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)
_BACKEND_SRC = os.path.join(_REPO_ROOT, "backend", "src")
if _BACKEND_SRC not in sys.path:
    sys.path.insert(0, _BACKEND_SRC)

from sam.members.repository import table_design as td
from sam.members.repository.members_repository import DynamoDbMembersRepository


# ---------------------------------------------------------------------------
# 1. normalize_name_dob_key — the exact normalization (design §12, pinned here)
# ---------------------------------------------------------------------------


class TestNormalizeNameDobKey:
    def test_combines_name_parts_in_canonical_order_with_the_dob(self):
        key = td.normalize_name_dob_key("Sam", "van der", "Berg", "1990-05-01")
        assert key == "sam van der berg|1990-05-01"

    def test_is_case_insensitive(self):
        assert td.normalize_name_dob_key(
            "SAM", "VAN DER", "BERG", "1990-05-01"
        ) == td.normalize_name_dob_key("sam", "van der", "berg", "1990-05-01")

    def test_trims_and_collapses_internal_whitespace(self):
        # Leading/trailing trimmed; a double-space infix collapses to one.
        assert td.normalize_name_dob_key(
            "  Sam ", "van  der", " Berg ", " 1990-05-01 "
        ) == "sam van der berg|1990-05-01"

    def test_optional_name_infix_absent_is_skipped(self):
        # tussenvoegsel is optional — an absent infix simply drops out of the join.
        assert td.normalize_name_dob_key("Sam", "", "Berg", "1990-05-01") == "sam berg|1990-05-01"
        assert td.normalize_name_dob_key("Sam", None, "Berg", "1990-05-01") == "sam berg|1990-05-01"

    def test_none_when_name_missing(self):
        # No usable name → un-indexable → None (name is half the match signal, R6.1a).
        assert td.normalize_name_dob_key("", "", "", "1990-05-01") is None
        assert td.normalize_name_dob_key(None, None, None, "1990-05-01") is None

    def test_none_when_dob_missing(self):
        # No DOB → un-indexable → None (DOB is the other half, R6.1a).
        assert td.normalize_name_dob_key("Sam", "", "Berg", "") is None
        assert td.normalize_name_dob_key("Sam", "", "Berg", None) is None

    def test_first_name_only_is_enough_name(self):
        # last_name is the usual anchor but any single present part yields a usable name.
        assert td.normalize_name_dob_key("Sam", None, None, "1990-05-01") == "sam|1990-05-01"

    def test_distinct_people_produce_distinct_keys(self):
        a = td.normalize_name_dob_key("Sam", None, "Berg", "1990-05-01")
        b = td.normalize_name_dob_key("Sam", None, "Berg", "1991-05-01")  # different DOB
        c = td.normalize_name_dob_key("Sem", None, "Berg", "1990-05-01")  # different name
        assert a != b
        assert a != c


# ---------------------------------------------------------------------------
# 2. build_member_item writes the sparse name_dob_key attribute (derived, never trusted)
# ---------------------------------------------------------------------------


class TestBuildMemberItemWritesKey:
    def test_key_attr_is_written_when_name_and_dob_present(self):
        member = {
            "personal": {"first_name": "Sam", "last_name": "Berg", "birth_date": "1990-05-01"},
        }
        item = td.build_member_item("t1", "m1", member)
        assert item[td.NAME_DOB_KEY_ATTR] == "sam berg|1990-05-01"

    def test_key_attr_is_absent_when_dob_missing(self):
        # Sparse: no DOB → the record is NOT indexed (no name_dob_key attribute at all).
        member = {"personal": {"first_name": "Sam", "last_name": "Berg"}}
        item = td.build_member_item("t1", "m1", member)
        assert td.NAME_DOB_KEY_ATTR not in item

    def test_key_attr_is_absent_when_name_missing(self):
        member = {"personal": {"birth_date": "1990-05-01"}}
        item = td.build_member_item("t1", "m1", member)
        assert td.NAME_DOB_KEY_ATTR not in item

    def test_key_attr_is_derived_not_client_trusted(self):
        # A hand-crafted payload carrying a bogus name_dob_key is OVERWRITTEN with the value
        # derived from the record's own fields (verify-before-trust).
        member = {
            "personal": {"first_name": "Sam", "last_name": "Berg", "birth_date": "1990-05-01"},
            td.NAME_DOB_KEY_ATTR: "attacker|supplied",
        }
        item = td.build_member_item("t1", "m1", member)
        assert item[td.NAME_DOB_KEY_ATTR] == "sam berg|1990-05-01"

    def test_stale_key_attr_is_dropped_when_record_loses_name_or_dob(self):
        # A record that no longer has a usable name/DOB must leave the index (no stale key).
        member = {
            "personal": {"first_name": "Sam", "last_name": "Berg"},  # DOB removed
            td.NAME_DOB_KEY_ATTR: "sam berg|1990-05-01",  # stale value from a prior write
        }
        item = td.build_member_item("t1", "m1", member)
        assert td.NAME_DOB_KEY_ATTR not in item

    def test_missing_personal_bucket_is_tolerated(self):
        item = td.build_member_item("t1", "m1", {"membership": {"status": "application"}})
        assert td.NAME_DOB_KEY_ATTR not in item


# ---------------------------------------------------------------------------
# 3. GSI definition shape (what the provisioner/template reference)
# ---------------------------------------------------------------------------


class TestGsiDefinition:
    def test_index_name_and_key_schema_are_tenant_scoped(self):
        gsi = td.name_dob_gsi_definition()
        assert gsi["IndexName"] == td.NAME_DOB_GSI_INDEX_NAME == "name_dob_index"
        # HASH is tenant_id so the index can NEVER address more than one tenant (Property 1).
        assert gsi["KeySchema"][0] == {"AttributeName": td.PARTITION_KEY_ATTR, "KeyType": "HASH"}
        assert gsi["KeySchema"][1] == {"AttributeName": td.NAME_DOB_KEY_ATTR, "KeyType": "RANGE"}
        assert gsi["Projection"] == {"ProjectionType": "ALL"}

    def test_attribute_definition_declares_only_the_new_range_key(self):
        assert td.name_dob_gsi_attribute_definition() == {
            "AttributeName": td.NAME_DOB_KEY_ATTR,
            "AttributeType": "S",
        }

    def test_constants_are_exported(self):
        assert "NAME_DOB_GSI_INDEX_NAME" in td.__all__
        assert "NAME_DOB_KEY_ATTR" in td.__all__
        assert "normalize_name_dob_key" in td.__all__
        assert "name_dob_gsi_definition" in td.__all__


# ---------------------------------------------------------------------------
# 4. query_by_name_dob — a tenant-pinned INDEXED read over the GSI (not a scan)
# ---------------------------------------------------------------------------


class _FakeGsiTable:
    """A fake Table whose ``query`` honours IndexName + the (tenant_id, name_dob_key) key."""

    def __init__(self, items):
        self.name = "test_members"
        self._items = list(items)
        self.query_calls: list[dict] = []

    def query(self, **kwargs):
        self.query_calls.append(kwargs)
        assert kwargs["IndexName"] == td.NAME_DOB_GSI_INDEX_NAME
        # The boto3 Key condition object isn't introspected here; the fixture pre-filters the
        # items by the key the test set up, so we return what matches the fixture's intent.
        return {"Items": list(self._items)}


class TestQueryByNameDob:
    def test_queries_the_gsi_by_index_name(self):
        table = _FakeGsiTable(
            items=[{"member_id": "m1", td.NAME_DOB_KEY_ATTR: "sam berg|1990-05-01"}]
        )
        repo = DynamoDbMembersRepository(table=table)
        result = repo.query_by_name_dob("t1", "sam berg|1990-05-01")
        assert len(table.query_calls) == 1
        assert table.query_calls[0]["IndexName"] == td.NAME_DOB_GSI_INDEX_NAME
        assert result[0]["member_id"] == "m1"

    def test_empty_key_short_circuits_without_a_query(self):
        table = _FakeGsiTable(items=[])
        repo = DynamoDbMembersRepository(table=table)
        assert repo.query_by_name_dob("t1", "") == []
        assert table.query_calls == []  # no key → no index read at all

    def test_requires_a_tenant(self):
        repo = DynamoDbMembersRepository(table=_FakeGsiTable(items=[]))
        with pytest.raises(ValueError):
            repo.query_by_name_dob("", "sam berg|1990-05-01")
