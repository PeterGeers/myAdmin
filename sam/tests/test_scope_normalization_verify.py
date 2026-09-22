"""
S5d Task 2.4 — tests for the R9.5 **normalization verification**
(``sam.members.migration.scope_normalization_verify`` + its CLI runner
``scripts/aws/verify-member-scope-normalization.py``).

The R9.5 requirement has two clauses, both pinned here:

1. **Every distinct member scope-field value is canonical** (no un-normalized values). The
   check collects the distinct values a tenant's members carry for the scope dimension's
   bound field (h-dcn ``overlay.region``), canonicalizes each with the shared ``scope_canon``,
   and asserts each maps to a member of the dimension's canonical value set. An un-normalizable
   value is SURFACED as an offender (R9.3), never silently kept/dropped — so a normalization
   gap is visible instead of an unexplained empty filter (the s5c bug class).

2. **An exact grant returns the expected NON-EMPTY subset.** ``members_matching_grant`` with
   ``region=["Oost"]`` over a seeded member set returns exactly the Oost members (canonical
   equality via the SAME ``scope_canon`` enforcement uses, R9.6).

Pure + no I/O: the check operates on already-read member records (the CLI supplies the
DynamoDB read). The runner's dimension resolution + exit-code path is exercised with an
in-memory fake repository/reader — no boto3, no AWS.

Validates: Requirements 9.3, 9.5, 9.6
"""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

import pytest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)
_BACKEND_SRC = os.path.join(_REPO_ROOT, "backend", "src")
if _BACKEND_SRC not in sys.path:
    sys.path.insert(0, _BACKEND_SRC)

from sam.members.domain.scope_dimensions import HDCN_SCOPE_CONFIG, ScopeDimension
from sam.members.migration.scope_normalization_verify import (
    members_matching_grant,
    member_scope_value,
    verify_scope_normalization,
)


# The h-dcn region dimension (canonical set Noord/Zuid/Oost/West), the pilot dimension.
REGION_DIM = next(d for d in HDCN_SCOPE_CONFIG if d.key == "region")
TENANT = "h-dcn"


def _member(member_id: str, region=None, *, bucket: str = "overlay") -> dict:
    """A minimal member record carrying its region on the given storage bucket.

    h-dcn's ``region`` is a tenant-added field so it lives at ``overlay.region`` (the default
    here); ``bucket`` lets a test place it flat/top-level to prove the accessor resolves the
    bucket from config (nested-first, flat fallback), never hardcoded.
    """
    record: dict = {"tenant_id": TENANT, "member_id": member_id}
    if region is None:
        return record
    if bucket == "flat":
        record["region"] = region
    else:
        record[bucket] = {"region": region}
    return record


# ---------------------------------------------------------------------------
# member_scope_value — reads the dimension's bound field (bucket resolved from config)
# ---------------------------------------------------------------------------


def test_member_scope_value_reads_overlay_region():
    m = _member("M-1", "Oost")
    assert member_scope_value(m, REGION_DIM) == "Oost"


def test_member_scope_value_flat_fallback():
    # A flat/top-level region still resolves (nested-bucket-first with flat fallback).
    m = _member("M-2", "Noord", bucket="flat")
    assert member_scope_value(m, REGION_DIM) == "Noord"


def test_member_scope_value_absent_is_none():
    assert member_scope_value(_member("M-3"), REGION_DIM) is None


# ---------------------------------------------------------------------------
# R9.5 clause 1 — every distinct value is canonical (no un-normalized values)
# ---------------------------------------------------------------------------


def test_verify_all_canonical_values_passes():
    members = [
        _member("M-1", "Noord"),
        _member("M-2", "Zuid"),
        _member("M-3", "Oost"),
        _member("M-4", "West"),
        _member("M-5", "Oost"),  # a repeat — deduped in the census
    ]
    report = verify_scope_normalization(TENANT, members, REGION_DIM)

    assert report.ok is True
    assert report.offenders == ()
    assert report.members_scanned == 5
    # distinct census is deduped, first-seen order
    assert set(report.distinct_values) == {"Noord", "Zuid", "Oost", "West"}
    assert report.dimension_key == "region"
    assert report.field_key == "region"


def test_verify_canonical_equality_accepts_case_diacritic_separator_variants():
    # These are VARIANT SPELLINGS that canonicalize to a member of the set — R9.6 folds them,
    # so they are NOT offenders (the exact-in-canonical-space contract).
    members = [
        _member("M-1", "oost"),      # case
        _member("M-2", " Noord "),   # surrounding whitespace
        _member("M-3", "ZUID"),      # case
    ]
    report = verify_scope_normalization(TENANT, members, REGION_DIM)
    assert report.ok is True
    assert report.offenders == ()


def test_verify_surfaces_un_normalizable_value_as_offender():
    # "Groningen" has no counterpart in Noord/Zuid/Oost/West → surfaced (R9.3), not hidden.
    members = [
        _member("M-1", "Oost"),
        _member("M-2", "Groningen"),
        _member("M-3", "Noord"),
    ]
    report = verify_scope_normalization(TENANT, members, REGION_DIM)

    assert report.ok is False
    assert report.offenders == ("Groningen",)
    # The valid values are still present in the census (the offender does not hide them).
    assert set(report.distinct_values) == {"Oost", "Groningen", "Noord"}


def test_verify_offenders_are_distinct_and_order_stable():
    members = [
        _member("M-1", "Drenthe"),
        _member("M-2", "Oost"),
        _member("M-3", "Friesland"),
        _member("M-4", "Drenthe"),  # repeat offender — reported once
    ]
    report = verify_scope_normalization(TENANT, members, REGION_DIM)
    assert report.ok is False
    assert report.offenders == ("Drenthe", "Friesland")


def test_verify_absent_or_blank_region_is_not_an_offender():
    # An absent value is a deny-by-default ABSENCE, not an un-normalizable variant.
    members = [
        _member("M-1", "Oost"),
        _member("M-2"),           # no region at all
        _member("M-3", "   "),    # blank → canonicalizes to "" → excluded from the census
    ]
    report = verify_scope_normalization(TENANT, members, REGION_DIM)
    assert report.ok is True
    assert report.offenders == ()
    assert report.distinct_values == ("Oost",)


def test_verify_empty_member_set_passes_vacuously():
    report = verify_scope_normalization(TENANT, [], REGION_DIM)
    assert report.ok is True
    assert report.offenders == ()
    assert report.distinct_values == ()
    assert report.members_scanned == 0


# ---------------------------------------------------------------------------
# R9.5 clause 2 — an exact grant returns the expected NON-EMPTY subset
# ---------------------------------------------------------------------------


def test_exact_grant_returns_expected_non_empty_subset():
    members = [
        _member("M-1", "Oost"),
        _member("M-2", "Noord"),
        _member("M-3", "Oost"),
        _member("M-4", "West"),
    ]
    matched = members_matching_grant(members, ["Oost"], REGION_DIM)

    matched_ids = {m["member_id"] for m in matched}
    assert matched_ids == {"M-1", "M-3"}  # exactly the Oost members — a non-empty subset
    assert len(matched) == 2


def test_exact_grant_matches_by_canonical_equality():
    # A variant-spelled member value still matches an exactly-spelled grant (R9.6).
    members = [_member("M-1", "oost"), _member("M-2", " OOST ")]
    matched = members_matching_grant(members, ["Oost"], REGION_DIM)
    assert {m["member_id"] for m in matched} == {"M-1", "M-2"}


def test_exact_grant_multi_value_grant_returns_union():
    members = [
        _member("M-1", "Oost"),
        _member("M-2", "Noord"),
        _member("M-3", "West"),
    ]
    matched = members_matching_grant(members, ["Oost", "West"], REGION_DIM)
    assert {m["member_id"] for m in matched} == {"M-1", "M-3"}


def test_exact_grant_no_match_returns_empty():
    members = [_member("M-1", "Oost")]
    assert members_matching_grant(members, ["Noord"], REGION_DIM) == []


# ---------------------------------------------------------------------------
# CLI runner — dimension resolution + exit codes (fake repo/reader, no AWS)
# ---------------------------------------------------------------------------

_RUNNER_PATH = (
    Path(__file__).resolve().parents[2]
    / "scripts"
    / "aws"
    / "verify-member-scope-normalization.py"
)


def _load_runner():
    spec = importlib.util.spec_from_file_location(
        "verify_member_scope_normalization", _RUNNER_PATH
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


runner = _load_runner()


class _FakeRepo:
    """A read-only in-memory repository exposing just ``list_members`` (Protocol shape)."""

    def __init__(self, members):
        self._members = list(members)

    def list_members(self, tenant_id, *, filters=None, scope_filter=None):
        # tenant-scoped by construction (the fake only holds one tenant's members)
        return list(self._members)


class _FakeReader:
    """A fake projection reader returning a fixed ScopeConfig for get_scope_config."""

    def __init__(self, config):
        self._config = config

    def get_scope_config(self, tenant_id):
        return self._config


def test_runner_clean_tenant_exits_zero():
    from sam.members.domain.scope_dimensions import ScopeConfig

    repo = _FakeRepo([_member("M-1", "Oost"), _member("M-2", "Noord")])
    reader = _FakeReader(ScopeConfig(tenant_id=TENANT, dimensions=(REGION_DIM,)))
    code = runner.verify(TENANT, region="eu-west-1", repo=repo, reader=reader)
    assert code == 0


def test_runner_un_normalized_tenant_exits_three():
    from sam.members.domain.scope_dimensions import ScopeConfig

    repo = _FakeRepo([_member("M-1", "Oost"), _member("M-2", "Groningen")])
    reader = _FakeReader(ScopeConfig(tenant_id=TENANT, dimensions=(REGION_DIM,)))
    code = runner.verify(TENANT, region="eu-west-1", repo=repo, reader=reader)
    assert code == 3  # R9.3 — un-normalized value surfaced, non-zero exit


def test_runner_falls_back_to_reference_config_when_projection_empty():
    from sam.members.domain.scope_dimensions import ScopeConfig

    # Projection carries NO dimensions → fall back to HDCN_SCOPE_CONFIG for `region`.
    repo = _FakeRepo([_member("M-1", "Oost")])
    empty_reader = _FakeReader(ScopeConfig(tenant_id=TENANT, dimensions=()))
    code = runner.verify(
        TENANT, region="eu-west-1", dimension_key="region", repo=repo, reader=empty_reader
    )
    assert code == 0


def test_runner_unknown_dimension_exits_two():
    from sam.members.domain.scope_dimensions import ScopeConfig

    repo = _FakeRepo([_member("M-1", "Oost")])
    reader = _FakeReader(ScopeConfig(tenant_id=TENANT, dimensions=(REGION_DIM,)))
    code = runner.verify(
        TENANT, region="eu-west-1", dimension_key="no_such_dim", repo=repo, reader=reader
    )
    assert code == 2  # dimension could not be resolved
