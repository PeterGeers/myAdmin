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


# ── The rule resolves the tenant's prefix from its OWN projected `tenant` row (REAL reader) ──


class _FakeProjectionTable:
    """Minimal in-memory boto3 Table stand-in (query side) — mirrors
    ``test_members_projection_reader.FakeTable`` so the REAL ``MembersProjectionReader`` reads a
    seeded projected ``tenant`` row without any AWS/mocking of the reader itself."""

    def __init__(self):
        self._items: list[dict] = []

    def put(self, item: dict) -> None:
        self._items.append(dict(item))

    def query(self, KeyConditionExpression=None):
        expr = KeyConditionExpression.get_expression()
        tenant_id = expr["values"][1]
        from services import projection_schema as schema

        items = [
            dict(i)
            for i in self._items
            if i.get(schema.PARTITION_KEY_ATTR) == tenant_id
        ]
        return {"Items": items}


def _tenant_row(tenant_id, **attrs):
    from services import projection_schema as schema

    item = {
        schema.PARTITION_KEY_ATTR: tenant_id,
        schema.SORT_KEY_ATTR: schema.build_sort_key(schema.RECORD_TYPE_TENANT),
    }
    item.update(attrs)
    return item


def _reader_with(*items):
    from sam.members.repository.projection_config_reader import MembersProjectionReader

    table = _FakeProjectionTable()
    for item in items:
        table.put(item)
    return MembersProjectionReader(table=table)


def test_get_public_prefix_reads_projected_tenant_row():
    # SAM resolves the AUTHENTICATED tenant's prefix off its OWN projected `tenant` row (R2.2) —
    # the additive attribute task 6.2 carries; no call to Flask.
    reader = _reader_with(
        _tenant_row("h-dcn", display_name="HDCN", public_prefix="h-dcn")
    )
    assert reader.get_public_prefix("h-dcn") == "h-dcn"


def test_get_public_prefix_none_when_attribute_omitted():
    # Back-compat (task 6.2 OMITS a NULL/absent prefix): the reader returns None, and the rule
    # then refuses a NEW claim for that prefix-less tenant.
    reader = _reader_with(_tenant_row("h-dcn", display_name="HDCN"))
    assert reader.get_public_prefix("h-dcn") is None


def test_get_public_prefix_none_when_tenant_row_absent():
    # A tenant with no projected `tenant` row at all → None (empty-is-valid, never a raise).
    reader = _reader_with()
    assert reader.get_public_prefix("h-dcn") is None


def test_prefix_ownership_end_to_end_with_real_reader():
    # Prove the SEC-4 rule against the REAL reader-resolved prefix (not a hand-passed literal):
    # tenant h-dcn owns h-dcn-aanmelden; tenant acme cannot borrow it.
    reader = _reader_with(
        _tenant_row("h-dcn", public_prefix="h-dcn"),
        _tenant_row("acme", public_prefix="acme"),
    )
    hdcn_prefix = reader.get_public_prefix("h-dcn")
    acme_prefix = reader.get_public_prefix("acme")
    # h-dcn claiming under its own prefix → allowed.
    assert (
        form_slug.validate_slug_prefix_ownership("h-dcn-aanmelden", hdcn_prefix) is None
    )
    # acme trying to borrow h-dcn's prefix → rejected (T10 / SEC-4), proven against real data.
    assert (
        form_slug.validate_slug_prefix_ownership("h-dcn-aanmelden", acme_prefix)
        is not None
    )


# ── Task 6.4 end-to-end: the BUILDER's emitted row is read back by the READER ──────────
#
# This is the one assertion the Task-6 battery was missing. 6.2's builder tests prove
# `build_projection_items(...).to_dynamodb_item()` EMITS `public_prefix` onto the `tenant`
# row; 6.3's reader tests prove `MembersProjectionReader.get_public_prefix` READS it off a
# HAND-BUILT row. Neither proves the two AGREE on attribute name/shape — the real drift risk
# (builder writes `public_prefix`, reader reads a differently-named/shaped attr and silently
# returns None). Here we feed the builder's ACTUAL emitted item into the REAL reader so the
# write-shape and read-shape are proven to be the same shape, then drive the SEC-4 rule off it.


def _project_tenant_item(administration, *, public_prefix=None):
    """Run the REAL Flask-plane projection builder for one SAM-enabled tenant and return the
    `tenant`-row DynamoDB item it emits (the exact bytes the sync would PUT)."""
    from services.module_registry import MODULE_REGISTRY
    from services.projection_builder import build_projection_items

    # Pick any already-registered SAM-backed module so the projection gate opens, without
    # mutating the shipped registry (read-only lookup).
    sam_module = next(
        name
        for name, entry in MODULE_REGISTRY.items()
        if isinstance(entry, dict) and entry.get("backing", {}).get("kind") == "sam"
    )
    tenant = {"administration": administration}
    if public_prefix is not None:
        tenant["public_prefix"] = public_prefix
    items = build_projection_items(
        tenant, [{"module_name": sam_module, "is_active": True}]
    )
    tenant_item = next(i for i in items if i.sort_key == "tenant").to_dynamodb_item()
    return tenant_item


def test_builder_emitted_tenant_row_is_read_back_by_reader_end_to_end():
    # END-TO-END: the projection builder EMITS the tenant row; the REAL reader READS the prefix
    # back off that SAME emitted item (no hand-built row) — write-shape ≡ read-shape proven.
    hdcn_item = _project_tenant_item("h-dcn", public_prefix="h-dcn")
    acme_item = _project_tenant_item("acme", public_prefix="acme")

    reader = _reader_with(hdcn_item, acme_item)

    # The reader resolves exactly what the builder put — agreement on attribute name AND shape.
    assert reader.get_public_prefix("h-dcn") == "h-dcn"
    assert reader.get_public_prefix("acme") == "acme"

    # Drive the SEC-4 rule off the builder→reader-resolved prefix (full path, not a literal).
    assert (
        form_slug.validate_slug_prefix_ownership(
            "h-dcn-aanmelden", reader.get_public_prefix("h-dcn")
        )
        is None
    )
    # T10 / SEC-4 through the full path: acme cannot borrow h-dcn's prefixed namespace.
    assert (
        form_slug.validate_slug_prefix_ownership(
            "h-dcn-aanmelden", reader.get_public_prefix("acme")
        )
        is not None
    )


def test_builder_omitted_prefix_is_read_back_as_none_end_to_end():
    # Back-compat END-TO-END: when the source `public_prefix` is NULL the builder OMITS the
    # attribute; the reader reads the SAME emitted row back as None (no bogus null-typed attr),
    # and the SEC-4 rule then refuses a NEW claim for that prefix-less tenant.
    item = _project_tenant_item("h-dcn", public_prefix=None)
    assert "public_prefix" not in item  # builder omitted it (write-shape)

    reader = _reader_with(item)
    assert (
        reader.get_public_prefix("h-dcn") is None
    )  # read-shape agrees: absence → None

    error = form_slug.validate_slug_prefix_ownership(
        "h-dcn-aanmelden", reader.get_public_prefix("h-dcn")
    )
    assert isinstance(error, str) and error
    assert "public prefix" in error.lower()
