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


# ---------------------------------------------------------------------------
# SEC-4 prefix-ownership rule (spec 14 Task 6.3 / R2.3, R2.5, R10.4)
#
# validate_slug_prefix_ownership is the SEPARATE, tenant-scoped squatting guard that the
# Task-1 uniqueness gate (tenant-AGNOSTIC) cannot provide. These pin T9 (prefix required),
# T10 (can't borrow another tenant's prefix), T11 (grandfathering incl. uppercase legacy),
# that format/reserved runs BEFORE the prefix check, and that the rule resolves the
# authenticated tenant's prefix from its OWN projected `tenant` row (the REAL reader, not a
# mock — SAM reads its own projection, never calls Flask / ADR 0005).
# ---------------------------------------------------------------------------

_BACKEND_SRC = os.path.join(_REPO_ROOT, "backend", "src")
if _BACKEND_SRC not in sys.path:
    sys.path.insert(0, _BACKEND_SRC)


# ── T9 — prefix required ─────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "slug",
    [
        "h-dcn",  # exactly the prefix
        "h-dcn-aanmelden",  # {prefix}-{suffix}
        "h-dcn-clubdag",
    ],
)
def test_prefix_ownership_accepts_tenant_own_prefix(slug):
    # T9: a slug that IS the prefix or {prefix}-{suffix} is owned by the tenant → allowed.
    assert form_slug.validate_slug_prefix_ownership(slug, "h-dcn") is None


@pytest.mark.parametrize(
    "slug",
    [
        "aanmelden",  # a bare popular name — no tenant prefix (the land-grab R2 prevents)
        "clubdag",
        "apply",
    ],
)
def test_prefix_ownership_rejects_prefixless_popular_slug(slug):
    # T9: a slug with NO tenant prefix is rejected (caller-safe, names the required prefix).
    error = form_slug.validate_slug_prefix_ownership(slug, "h-dcn")
    assert isinstance(error, str) and error
    assert "h-dcn" in error


def test_prefix_ownership_rejects_prefix_without_segment_boundary():
    # The prefix must match as a WHOLE leading SEGMENT — `h-dcn2` only shares a textual prefix
    # with `h-dcn` and must NOT be let through (a bare startswith would be a squatting hole).
    error = form_slug.validate_slug_prefix_ownership("h-dcn2", "h-dcn")
    assert isinstance(error, str) and error


# ── T10 — can't borrow another tenant's prefix (SEC-4) ─────────────────────────────────


def test_prefix_ownership_rejects_borrowing_another_tenants_prefix():
    # T10 / SEC-4: tenant `acme` (prefix "acme") trying to claim a slug under tenant `h-dcn`'s
    # prefix is rejected — the whole point the tenant-AGNOSTIC uniqueness gate cannot enforce.
    error = form_slug.validate_slug_prefix_ownership("h-dcn-foo", "acme")
    assert isinstance(error, str) and error
    assert (
        "acme" in error
    )  # names the AUTHENTICATED tenant's own prefix, not the borrowed one


# ── T11 — grandfathering (live / legacy incl. uppercase) ───────────────────────────────


@pytest.mark.parametrize(
    "slug",
    [
        "GoodwinSolutions",  # uppercase legacy — would fail SLUG_PATTERN and the prefix rule
        "PeterPrive",
        "aanmelden",  # a prefix-less live slug predating the prefix rule
        "someothertenant-page",  # live slug that does not match this tenant's prefix
    ],
)
def test_prefix_ownership_grandfathers_live_legacy_slugs(slug):
    # T11 (R2.5): an already-live slug for the SAME owner is let through UNCHANGED regardless of
    # prefix / case — the rule applies to NEW claims only; established slugs are never force-renamed.
    assert (
        form_slug.validate_slug_prefix_ownership(slug, "h-dcn", is_grandfathered=True)
        is None
    )


def test_prefix_ownership_grandfathers_even_with_no_tenant_prefix():
    # A prefix-less tenant's established slug still grandfathers (the short-circuit runs before
    # the prefix lookup) — a prefix-less tenant is not hard-broken.
    assert (
        form_slug.validate_slug_prefix_ownership(
            "legacy-slug", None, is_grandfathered=True
        )
        is None
    )


# ── Prefix-less tenant: a NEW claim is refused (no squatting a fresh prefixed slug) ────


@pytest.mark.parametrize("missing_prefix", [None, "", "   "])
def test_prefix_ownership_rejects_new_claim_when_tenant_has_no_prefix(missing_prefix):
    # Back-compat (task 6.2 omits a NULL prefix): a prefix-less tenant cannot prove ownership of a
    # prefixed namespace, so a NEW claim is refused — but its established slugs grandfather (above).
    error = form_slug.validate_slug_prefix_ownership("anything", missing_prefix)
    assert isinstance(error, str) and error
    assert "public prefix" in error.lower()


# ── Format/reserved runs BEFORE the prefix check (ordering, R2.6) ──────────────────────


def test_format_validation_runs_before_prefix_check():
    # R2.6: format/reserved is the FIRST gate. A malformed slug is rejected by validate_slug_format
    # regardless of prefix, so the claim path never reaches the prefix rule for garbage input.
    assert form_slug.validate_slug_format("Acme!") is not None  # format rejects first
    assert form_slug.validate_slug_format("admin") is not None  # reserved rejects first
    # A well-formed, tenant-owned slug passes BOTH gates in the claim-path order.
    assert form_slug.validate_slug_format("h-dcn-aanmelden") is None
    assert form_slug.validate_slug_prefix_ownership("h-dcn-aanmelden", "h-dcn") is None


# NOTE: the former “REAL reader reads the prefix off the projected `tenant` row” block
# (and the builder→reader end-to-end prefix tests) were REMOVED with the Flask prefix feature.
# The slug prefix is now SAM-owned on the config#fields row: authored via
# ConfigFieldsCrudService.set_public_prefix and read via MembersProjectionReader.get_public_prefix
# OFF config#fields — NOT the projected tenant row (the tenants.public_prefix column + its
# projection passthrough were dropped). The read-back is now covered by
# test_members_projection_reader.py::TestGetPublicPrefix. The pure SEC-4 string rule above
# (validate_slug_prefix_ownership) is unchanged — only the SOURCE of the prefix moved planes.
