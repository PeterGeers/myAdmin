"""Unit tests for the SAM-plane application-form slug **format** validator (spec 12 Task 1.1).

:mod:`sam.members.domain.form_slug` replicates the landing ``SLUG_PATTERN`` rules (R4.2) on the
SAM plane so a form slug is validated with the SAME shape contract the landing slug uses, without
importing the Flask-plane ``tenant_slug_service`` (which pulls boto3 / database deps). These pin
the format accept/reject contract; uniqueness is Task 1.2 and is NOT exercised here.
"""

import os
import sys

import pytest

_REPO_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from sam.members.domain import form_slug


@pytest.mark.parametrize(
    "slug",
    [
        "hdcn-application-form",
        "hdcn",
        "abc",  # minimum length (3)
        "a1b2c3",
        "a" * 100,  # maximum length (100)
        "my-club-2026",
    ],
)
def test_validate_slug_format_accepts_wellformed_slugs(slug):
    assert form_slug.validate_slug_format(slug) is None


@pytest.mark.parametrize(
    "slug",
    [
        "",  # blank
        "ab",  # too short
        "a" * 101,  # too long
        "HDCN",  # uppercase
        "Hdcn-Form",  # mixed case
        "-hdcn",  # leading hyphen
        "hdcn-",  # trailing hyphen
        "hd--cn",  # consecutive hyphens
        "hd cn",  # space
        "hd_cn",  # underscore
        "hd.cn",  # dot
        "héllo",  # non-ascii
    ],
)
def test_validate_slug_format_rejects_malformed_slugs(slug):
    error = form_slug.validate_slug_format(slug)
    assert isinstance(error, str) and error  # a non-empty, caller-safe reason


@pytest.mark.parametrize("reserved", sorted(form_slug.RESERVED_SLUGS))
def test_validate_slug_format_rejects_reserved_slugs(reserved):
    error = form_slug.validate_slug_format(reserved)
    assert error is not None
    assert "reserved" in error.lower()


@pytest.mark.parametrize("not_a_string", [123, None, ["hdcn"], {"slug": "hdcn"}])
def test_validate_slug_format_rejects_non_strings(not_a_string):
    assert form_slug.validate_slug_format(not_a_string) == "slug must be a string"


def test_landing_rules_are_replicated_verbatim():
    """R4.2 lock-step guard: the SAM format contract must match the landing authority VERBATIM
    (same regex source, same 3-100 bounds, same reserved set).

    The SAM-plane test environment deliberately BLOCKS importing the Flask-plane
    ``services.tenant_slug_service`` (it transitively imports ``mysql.connector`` and the
    ``sam/tests`` conftest raises on a cross-plane leak), so this pins the landing contract by
    its LITERAL values — copied from ``backend/src/services/tenant_slug_service.py``. Keep the two
    in lock-step: a change to the landing values must update both this expectation and
    ``form_slug`` in the same change (change-with-tests)."""
    # Literal landing contract (source: backend/src/services/tenant_slug_service.py).
    assert form_slug.SLUG_PATTERN.pattern == r"^[a-z0-9]+(?:-[a-z0-9]+)*$"
    assert form_slug.SLUG_MIN_LENGTH == 3
    assert form_slug.SLUG_MAX_LENGTH == 100
    assert form_slug.RESERVED_SLUGS == frozenset(
        {
            "admin",
            "api",
            "www",
            "app",
            "test",
            "staging",
            "landing",
            "public",
            "static",
            "assets",
        }
    )
