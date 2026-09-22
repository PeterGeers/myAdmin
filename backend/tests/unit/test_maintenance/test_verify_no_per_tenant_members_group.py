"""
Unit tests for the R6.4 check in
``backend/scripts/maintenance/verify_no_per_tenant_members_group.py``.

s5c task 0.5 / requirement R6.4 (component C-UNWIND): assert that the verify
script correctly (a) accepts the three GLOBAL Members roles
(``Members_CRUD`` / ``Members_Read`` / ``Members_Export``) and (b) FLAGS any
per-tenant ``Members_*`` variant (e.g. ``Members_CRUD_hdcn``).

The script's classification logic is pure and AWS-free once the boto3 client is
replaced with a fake, so these tests never touch AWS. The fake pool contents
mirror what the live pools (``eu-west-1_xyrlzfqbl`` test, ``eu-west-1_Hdp40eWmu``
prod Pool A) actually return, plus injected offenders for the negative cases.
"""

import importlib.util
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Load the maintenance script by path (no __init__.py under scripts/maintenance)
# ---------------------------------------------------------------------------
_SCRIPT_PATH = (
    Path(__file__).resolve().parents[3]
    / "scripts"
    / "maintenance"
    / "verify_no_per_tenant_members_group.py"
)


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "verify_no_per_tenant_members_group", _SCRIPT_PATH
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


verify = _load_module()


# ---------------------------------------------------------------------------
# Fake Cognito client — returns a scripted group list, paginated like boto3.
# ---------------------------------------------------------------------------
class _FakeCognitoClient:
    def __init__(self, group_names, *, error=None, page_size=None):
        self._groups = [{"GroupName": n} for n in group_names]
        self._error = error
        self._page_size = page_size

    def list_groups(self, **kwargs):
        if self._error is not None:
            raise self._error
        if self._page_size is None:
            return {"Groups": self._groups}
        # Emulate pagination: hand out one page per NextToken step.
        start = int(kwargs.get("NextToken", "0"))
        end = start + self._page_size
        page = self._groups[start:end]
        resp = {"Groups": page}
        if end < len(self._groups):
            resp["NextToken"] = str(end)
        return resp


# Real-world group set observed on BOTH live pools (the three globals only).
_GLOBALS = ["Members_CRUD", "Members_Read", "Members_Export"]
_OTHER_MODULE_ROLES = [
    "Finance_CRUD", "Finance_Read", "Finance_Export",
    "STR_CRUD", "STR_Read", "STR_Export",
    "ZZP_CRUD", "ZZP_Read", "ZZP_Export",
    "Tenant_Admin", "SysAdmin",
]


# ---------------------------------------------------------------------------
# The three globals + non-Members roles => clean (matches live pools).
# ---------------------------------------------------------------------------
def test_check_pool_three_globals_only_is_clean():
    client = _FakeCognitoClient(_GLOBALS + _OTHER_MODULE_ROLES)
    offenders, globals_present, error = verify.check_pool(client, "eu-west-1_xyrlzfqbl")
    assert error is None
    assert offenders == []
    assert sorted(globals_present) == sorted(_GLOBALS)


def test_check_pool_no_members_groups_at_all_is_clean():
    client = _FakeCognitoClient(_OTHER_MODULE_ROLES)
    offenders, globals_present, error = verify.check_pool(client, "pool-x")
    assert error is None
    assert offenders == []
    assert globals_present == []


# ---------------------------------------------------------------------------
# Per-tenant variants => flagged as offenders (the actual R6.4 violation).
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "offender",
    [
        "Members_CRUD_hdcn",
        "hdcn_Members_CRUD",
        "Members_h-dcn",
        "Members_CRUD_tenant123",
        "members_read_hdcn",  # lower-case still "looks like" a Members group
    ],
)
def test_check_pool_per_tenant_variant_is_flagged(offender):
    client = _FakeCognitoClient(_GLOBALS + [offender])
    offenders, _globals, error = verify.check_pool(client, "pool-y")
    assert error is None
    assert offender in offenders


def test_check_pool_multiple_offenders_all_reported():
    bad = ["Members_CRUD_hdcn", "Members_Read_acme"]
    client = _FakeCognitoClient(_GLOBALS + bad)
    offenders, _globals, error = verify.check_pool(client, "pool-z")
    assert sorted(offenders) == sorted(bad)


# ---------------------------------------------------------------------------
# Pagination is honoured (offender only visible on a later page).
# ---------------------------------------------------------------------------
def test_check_pool_paginates_and_finds_offender_on_later_page():
    names = _GLOBALS + _OTHER_MODULE_ROLES + ["Members_CRUD_hdcn"]
    client = _FakeCognitoClient(names, page_size=2)
    offenders, globals_present, error = verify.check_pool(client, "pool-paged")
    assert error is None
    assert offenders == ["Members_CRUD_hdcn"]
    assert sorted(globals_present) == sorted(_GLOBALS)


# ---------------------------------------------------------------------------
# An inspection error is surfaced softly (returns the error, no crash).
# ---------------------------------------------------------------------------
def test_check_pool_inspection_error_is_soft():
    client = _FakeCognitoClient([], error=RuntimeError("access denied"))
    offenders, globals_present, error = verify.check_pool(client, "pool-err")
    assert offenders == []
    assert globals_present == []
    assert "access denied" in error


# ---------------------------------------------------------------------------
# The allowed-set is exactly the three globals (guards against drift).
# ---------------------------------------------------------------------------
def test_global_members_roles_are_exactly_the_three():
    assert verify.GLOBAL_MEMBERS_ROLES == {
        "Members_CRUD",
        "Members_Read",
        "Members_Export",
    }
