"""
SAM pytest for the :class:`TenantDirectory` slug resolver (application-app Task 1.2; R2.1–R2.3,
R1a.4; design §1/§2/§3, seam a) — the storage-agnostic PUBLIC-edge resolver that turns a public
path slug into an allow-listed canonical ``tenant_id``, or a UNIFORM, non-probeable not-found.

Phase 1 testing (tasks.md 1.4): "unknown slug → 404 indistinguishable from no-endpoint". These
drive the resolver through its one required port — a static :class:`TenantSlugReader` fake
mirroring the thin slug→``tenant_id`` projection (D19) — with NO AWS/boto3 and NO CloudFront KVS.
Covered:

- allow-list hit — a carried slug resolves to the canonical tenant it names (R2.1/R2.2);
- verify-before-trust — a slug NOT on the allow-list resolves to not-found and NEVER invents a
  tenant (R2.3);
- non-probeable by construction (R1a.4) — unknown, forged/garbage, blank, whitespace-only, and
  oversized slugs ALL collapse to the SAME ``ResolveFailure.NOT_FOUND`` outcome, so the outcome
  carries no signal a caller could use as an enumeration oracle;
- normalization — trim + case-fold so ``HDCN`` / `` hdcn `` name the same tenant as ``hdcn``
  (the slug is a case-insensitive DNS host label — D19);
- malformed input is accepted, never raised (a non-string / blank slug → not-found, no exception),
  and a blank/oversized slug is rejected WITHOUT consulting the reader;
- a fail-safe reader answer (``None`` / ``""`` / non-string) is treated as no-match;
- tenancy — the resolution is bounded to the queried slug (one slug never resolves to another's
  tenant);
- the :class:`TenantResolution` "exactly one of tenant_id / failure" invariant;
- Property (R2.3/R1a.4): across arbitrary slugs, a tenant is resolved IFF the reader carries a
  concrete mapping for the normalized slug — every other input is the one uniform not-found.

Validates: Requirements R2.1, R2.2, R2.3, R1a.4
"""

from __future__ import annotations

import os
import sys

import pytest
from hypothesis import given
from hypothesis import strategies as st

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from sam.members.domain.tenant_directory import (
    MAX_SLUG_LENGTH,
    ResolveFailure,
    TenantDirectory,
    TenantResolution,
)

SLUG = "hdcn"
TENANT = "h-dcn"
OTHER_SLUG = "other-club"
OTHER_TENANT = "other-club-tenant"


# ── fake slug reader (the one injected port) ────────────────────────────────────────────


class FakeTenantSlugReader:
    """A static :class:`TenantSlugReader` mirroring the thin slug→``tenant_id`` projection (D19).

    Holds a ``{normalized_slug: tenant_id}`` allow-list and answers ``resolve_slug`` from it with
    the SAME fail-safe / empty-is-valid contract the real reader applies: an unknown slug → ``None``
    (no match), NEVER a raise and NEVER a guessed tenant. It RECORDS every slug it was asked for so
    a test can assert the resolver normalized the input and keyed strictly off it. Keys are stored
    already-normalized (lower-case) — the resolver normalizes before the reader is consulted.
    """

    def __init__(self):
        self._allow_list: dict[str, str] = {}
        self.seen_slugs: list[str] = []

    def put(self, slug: str, tenant_id: str) -> None:
        self._allow_list[slug.strip().lower()] = tenant_id

    def resolve_slug(self, slug: str) -> str | None:
        self.seen_slugs.append(slug)
        return self._allow_list.get(slug)


@pytest.fixture()
def reader() -> FakeTenantSlugReader:
    return FakeTenantSlugReader()


@pytest.fixture()
def directory(reader) -> TenantDirectory:
    return TenantDirectory(reader)


# ── allow-list hit (R2.1 / R2.2) ────────────────────────────────────────────────────────


def test_resolve_allow_listed_slug_returns_canonical_tenant(reader, directory):
    reader.put(SLUG, TENANT)

    result = directory.resolve(SLUG)

    assert result.ok is True
    assert result.failure is None
    assert result.tenant_id == TENANT


# ── verify-before-trust: unknown / forged → not-found, never invented (R2.3) ─────────────


def test_resolve_unknown_slug_returns_not_found(reader, directory):
    # A well-formed slug the allow-list does not carry → not-found; no tenant is invented.
    reader.put(SLUG, TENANT)

    result = directory.resolve("not-a-real-tenant")

    assert result.ok is False
    assert result.tenant_id is None
    assert result.failure is ResolveFailure.NOT_FOUND


def test_resolve_forged_garbage_slug_returns_not_found(reader, directory):
    reader.put(SLUG, TENANT)

    result = directory.resolve("'; DROP TABLE members; --")

    assert result.ok is False
    assert result.failure is ResolveFailure.NOT_FOUND


def test_resolve_against_empty_allow_list_is_not_found(directory):
    # An empty/unreachable-as-empty backing store resolves every slug to not-found (fail-safe).
    result = directory.resolve(SLUG)

    assert result.ok is False
    assert result.failure is ResolveFailure.NOT_FOUND


# ── non-probeable: unknown / malformed / blank / oversized all collapse identically (R1a.4) ─


def test_unknown_and_malformed_slugs_yield_an_identical_not_found_outcome(reader, directory):
    reader.put(SLUG, TENANT)

    outcomes = [
        directory.resolve("unknown-but-well-formed"),  # unknown
        directory.resolve("!!garbage!!"),  # forged/garbage
        directory.resolve(""),  # blank
        directory.resolve("   "),  # whitespace-only
        directory.resolve("x" * (MAX_SLUG_LENGTH + 1)),  # oversized
        directory.resolve(None),  # non-string
        directory.resolve(12345),  # non-string
    ]

    # Every rejection is byte-for-byte the same outcome — no field distinguishes them, so a
    # caller mapping them to HTTP cannot tell real-but-unknown from garbage (no enumeration oracle).
    for outcome in outcomes:
        assert outcome.ok is False
        assert outcome.tenant_id is None
        assert outcome.failure is ResolveFailure.NOT_FOUND
        assert outcome == outcomes[0]


def test_blank_and_oversized_slugs_do_not_consult_the_reader(reader, directory):
    # A cheap guard: blank / whitespace / oversized / non-string are rejected WITHOUT a read,
    # so no garbage key is ever handed to the backing store.
    directory.resolve("")
    directory.resolve("   ")
    directory.resolve("x" * (MAX_SLUG_LENGTH + 1))
    directory.resolve(None)

    assert reader.seen_slugs == []


# ── normalization: trim + case-fold (slug is a case-insensitive DNS host label — D19) ────


def test_resolve_is_case_insensitive(reader, directory):
    reader.put(SLUG, TENANT)  # stored lower-case

    assert directory.resolve("HDCN").tenant_id == TENANT
    assert directory.resolve("HdCn").tenant_id == TENANT


def test_resolve_trims_surrounding_whitespace(reader, directory):
    reader.put(SLUG, TENANT)

    assert directory.resolve("  hdcn  ").tenant_id == TENANT


def test_reader_is_consulted_with_the_normalized_slug(reader, directory):
    reader.put(SLUG, TENANT)

    directory.resolve("  HDCN  ")

    # The reader only ever sees the trimmed + case-folded form, so it and the projection agree.
    assert reader.seen_slugs == ["hdcn"]


def test_max_length_slug_is_consulted_not_rejected(reader, directory):
    # A slug EXACTLY at the cap is a valid length and IS looked up (boundary is inclusive).
    boundary_slug = "a" * MAX_SLUG_LENGTH
    reader.put(boundary_slug, TENANT)

    assert directory.resolve(boundary_slug).tenant_id == TENANT


# ── fail-safe reader answers are treated as no-match (never a hostless tenant) ───────────


@pytest.mark.parametrize("bad_answer", [None, "", 0, False, 123])
def test_resolve_treats_non_string_or_empty_reader_answer_as_not_found(bad_answer):
    class BadReader:
        def resolve_slug(self, slug):  # noqa: ARG002
            return bad_answer

    result = TenantDirectory(BadReader()).resolve(SLUG)

    assert result.ok is False
    assert result.failure is ResolveFailure.NOT_FOUND


# ── tenancy — bounded to the queried slug (one slug never resolves to another's tenant) ──


def test_resolve_is_bounded_to_the_queried_slug(reader, directory):
    reader.put(SLUG, TENANT)
    reader.put(OTHER_SLUG, OTHER_TENANT)

    assert directory.resolve(SLUG).tenant_id == TENANT
    assert directory.resolve(OTHER_SLUG).tenant_id == OTHER_TENANT


# ── TenantResolution invariant (exactly one of tenant_id / failure) ──────────────────────


def test_tenant_resolution_rejects_both_tenant_and_failure():
    with pytest.raises(ValueError):
        TenantResolution(tenant_id=TENANT, failure=ResolveFailure.NOT_FOUND)


def test_tenant_resolution_rejects_neither_tenant_nor_failure():
    with pytest.raises(ValueError):
        TenantResolution(tenant_id=None, failure=None)


# ── Property (R2.3 / R1a.4): resolve IFF the allow-list carries the normalized slug ──────
#
# **Validates: Requirements 2.2, 2.3** (design Property 2 — verify-before-trust)

# Slugs the generator may probe: a couple of allow-listed ones plus arbitrary other text.
_SEEDED = {"hdcn": "h-dcn", "zktk": "zktk-tenant"}


@given(
    probe=st.one_of(
        st.sampled_from(list(_SEEDED)),  # exact allow-listed slugs
        st.sampled_from([s.upper() for s in _SEEDED]),  # case variants (must still hit)
        st.text(max_size=80),  # arbitrary text (overwhelmingly misses)
    )
)
def test_resolves_iff_normalized_slug_is_on_the_allow_list(probe):
    """A tenant is resolved IFF the reader carries a concrete mapping for the NORMALIZED slug.

    The gate opens only on explicit allow-list truth across the whole input space — no unknown /
    malformed / blank / oversized slug ever yields a tenant (verify-before-trust, R2.3), and
    every miss is the ONE uniform not-found (non-probeable, R1a.4). A hit always returns exactly
    the canonical tenant the allow-list maps the normalized slug to (never a guessed one).
    """
    reader = FakeTenantSlugReader()
    for slug, tenant_id in _SEEDED.items():
        reader.put(slug, tenant_id)

    result = TenantDirectory(reader).resolve(probe)

    normalized = probe.strip().lower()
    expected_tenant = (
        _SEEDED.get(normalized) if normalized and len(normalized) <= MAX_SLUG_LENGTH else None
    )

    if expected_tenant is not None:
        assert result.ok is True
        assert result.tenant_id == expected_tenant
        assert result.failure is None
    else:
        assert result.ok is False
        assert result.tenant_id is None
        assert result.failure is ResolveFailure.NOT_FOUND
