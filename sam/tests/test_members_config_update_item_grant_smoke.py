"""Unit tests for the deployed-stage IAM-grant smoke test's PURE helpers (spec 03 task 8.6).

These run LOCALLY with NO AWS — they cover only the pure logic of
``scripts/smoke/members_config_update_item_grant_smoke.py`` (target/identity guards, the
update-expression plan, the fresh-deploy cutoff, timestamp parsing, and that the sentinel
sort key is built the SAME way the real ``projection_schema`` builds a ``config#*`` key).

The AWS-touching path (STS whoami, assume-role, the real ``update_item``) is NEVER exercised
here — it only runs against a deployed stack via the script's runbook. This is the
change-with-tests pairing for the script's pure helpers (steering 34 / 39).
"""

from __future__ import annotations

import datetime as _dt
import importlib.util
import os
import sys

import pytest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _load_smoke_module():
    """Import the smoke script by path (the module name is valid, but load it standalone)."""
    path = os.path.join(
        _REPO_ROOT, "scripts", "smoke", "members_config_update_item_grant_smoke.py"
    )
    spec = importlib.util.spec_from_file_location(
        "members_config_update_item_grant_smoke", path
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["members_config_update_item_grant_smoke"] = module
    spec.loader.exec_module(module)
    return module


smoke = _load_smoke_module()


# ---------------------------------------------------------------------------
# build_sentinel_sort_key — must match the REAL schema's config SK construction
# ---------------------------------------------------------------------------


def test_sentinel_sort_key_shape():
    # Not the real config#fields key — a dedicated sentinel id.
    assert smoke.build_sentinel_sort_key() == "config#__smoketest__"
    assert smoke.build_sentinel_sort_key() != "config#fields"


def test_sentinel_sort_key_uses_same_record_type_and_separator_as_schema():
    """The sentinel key is built exactly as projection_schema builds a config#<id> key.

    Guards against drift: if the schema ever changed the ``config`` record type or the ``#``
    separator, this test fails and the script must be updated in the same change.
    """
    from services import projection_schema as schema

    expected = schema.build_sort_key(schema.RECORD_TYPE_CONFIG, "__smoketest__")
    assert smoke.build_sentinel_sort_key() == expected
    # And the REAL fields key the isolation scan filters on is config#fields.
    assert (
        schema.build_sort_key(schema.RECORD_TYPE_CONFIG, schema.CONFIG_ID_FIELDS)
        == "config#fields"
    )


# ---------------------------------------------------------------------------
# assert_test_target — defense-in-depth prod guard
# ---------------------------------------------------------------------------


def test_assert_test_target_allows_test_prefixed_table():
    smoke.assert_test_target("test_governance_projection", allow_prod=False)  # no raise


def test_assert_test_target_refuses_prod_table_without_override():
    with pytest.raises(smoke.NotTestTargetError):
        smoke.assert_test_target("governance_projection", allow_prod=False)


def test_assert_test_target_allows_prod_table_with_explicit_override():
    smoke.assert_test_target("governance_projection", allow_prod=True)  # no raise


# ---------------------------------------------------------------------------
# assert_expected_identity — the steering-41 override-ranking trap guard
# ---------------------------------------------------------------------------


def test_assert_expected_identity_accepts_data_account_role():
    arn = "arn:aws:sts::506221081911:assumed-role/NonprofitDeployRole/session"
    smoke.assert_expected_identity(arn, "506221081911")  # no raise


def test_assert_expected_identity_rejects_wrong_account():
    # The personal account — the classic override-ranking trap symptom.
    arn = "arn:aws:sts::344561557829:assumed-role/SomethingElse/session"
    with pytest.raises(smoke.SmokeError):
        smoke.assert_expected_identity(arn, "344561557829")


def test_assert_expected_identity_rejects_right_account_wrong_role():
    arn = "arn:aws:sts::506221081911:assumed-role/SomeOtherRole/session"
    with pytest.raises(smoke.SmokeError):
        smoke.assert_expected_identity(arn, "506221081911")


# ---------------------------------------------------------------------------
# parse_deployed_after / assert_fresh_deploy — the stale-stack guard
# ---------------------------------------------------------------------------


def test_parse_deployed_after_valid():
    dt = smoke.parse_deployed_after("2026-10-24")
    assert dt.year == 2026 and dt.month == 10 and dt.day == 24
    assert dt.tzinfo is not None  # UTC-aware


def test_parse_deployed_after_invalid_raises():
    with pytest.raises(smoke.SmokeError):
        smoke.parse_deployed_after("not-a-date")


def test_assert_fresh_deploy_accepts_newer_deploy():
    cutoff = smoke.parse_deployed_after("2026-10-24")
    newer = _dt.datetime(2026, 10, 25, tzinfo=_dt.timezone.utc)
    smoke.assert_fresh_deploy(newer, cutoff)  # no raise


def test_assert_fresh_deploy_refuses_stale_deploy():
    cutoff = smoke.parse_deployed_after("2026-10-24")
    # The OLD TEST stack: last updated 2026-10-23, before the spec.
    stale = _dt.datetime(2026, 10, 23, 12, 0, 0, tzinfo=_dt.timezone.utc)
    with pytest.raises(smoke.SmokeError):
        smoke.assert_fresh_deploy(stale, cutoff)


# ---------------------------------------------------------------------------
# build_update_plan — mirrors the Change-Op repo's SET + version-conditional write
# ---------------------------------------------------------------------------


def test_build_update_plan_sets_probe_and_version():
    plan = smoke.build_update_plan("config#__smoketest__", "2026-10-25T00:00:00.000000Z")
    # A SET expression that bumps version in the same op (the repo's pattern).
    assert "SET" in plan["UpdateExpression"]
    assert "#version" in plan["UpdateExpression"]
    assert "#probe" in plan["UpdateExpression"]
    # First-write / no-row version guard (design D5 case iii).
    assert plan["ConditionExpression"] == "attribute_not_exists(#sk)"
    assert plan["ExpressionAttributeNames"]["#version"] == "version"
    assert plan["ExpressionAttributeNames"]["#sk"] == "sk"
    assert plan["ExpressionAttributeValues"][":version"] == "2026-10-25T00:00:00.000000Z"


def test_build_update_plan_is_ready_to_splat_into_update_item():
    """The plan dict carries exactly the keyword args update_item expects (no extras)."""
    plan = smoke.build_update_plan("config#__smoketest__", "v1")
    assert set(plan) == {
        "UpdateExpression",
        "ConditionExpression",
        "ExpressionAttributeNames",
        "ExpressionAttributeValues",
    }


# ---------------------------------------------------------------------------
# _parse_lambda_timestamp — Lambda's LastModified formats
# ---------------------------------------------------------------------------


def test_parse_lambda_timestamp_offset_form():
    dt = smoke._parse_lambda_timestamp("2026-10-23T12:34:56.000+0000")
    assert dt.year == 2026 and dt.hour == 12 and dt.minute == 34
    assert dt.tzinfo is not None


def test_parse_lambda_timestamp_z_form():
    dt = smoke._parse_lambda_timestamp("2026-10-23T12:34:56Z")
    assert dt.year == 2026 and dt.tzinfo is not None
