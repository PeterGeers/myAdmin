"""
SAM pytest for :class:`EnvTenantSlugReader` (application-app Task 1.3; D19/R2; design §11a
"Slug→tenant resolver" row) — the concrete, env-backed thin PROJECTION of the landing-page slug
mapping that satisfies the storage-agnostic
:class:`sam.members.domain.tenant_directory.TenantSlugReader` Protocol the Task-1.2 resolver
depends on.

These pin the reader's observable contract WITHOUT AWS / boto3 / the CloudFront KVS (it reads the
projection from the ``PUBLIC_TENANT_SLUG_MAP`` env var):

- allow-list hit — a seeded ``<slug>:<tenant_id>`` pair resolves to its canonical tenant (R2.1/R2.2);
- fail-safe / empty-is-valid (R2.3/R1a.4) — an unknown slug, an empty / unset map, and a malformed
  pair all return ``None`` (no match), NEVER a raise and NEVER a guessed tenant;
- the reader satisfies the :class:`TenantSlugReader` Protocol (so it drops into
  :class:`TenantDirectory` by duck-typing);
- resolved at CALL time — a changed env is honoured without a module reload;
- case-folded keys so a mapping authored with stray case/whitespace still matches the resolver's
  already-normalized lookup (the two cannot drift);
- end-to-end through :class:`TenantDirectory` — the reader + resolver together give the full
  verify-before-trust, non-probeable behaviour the edge relies on.

Validates: Requirements R2.1, R2.2, R2.3, R1a.4
"""

from __future__ import annotations

import os
import sys

import pytest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from sam.members.domain.tenant_directory import (
    ResolveFailure,
    TenantDirectory,
    TenantSlugReader,
)
from sam.members.repository.tenant_slug_reader import SLUG_MAP_ENV, EnvTenantSlugReader


@pytest.fixture()
def reader() -> EnvTenantSlugReader:
    return EnvTenantSlugReader()


# ── allow-list hit (R2.1 / R2.2) ────────────────────────────────────────────────────────


def test_resolve_slug_seeded_pair_returns_tenant(reader, monkeypatch):
    monkeypatch.setenv(SLUG_MAP_ENV, "hdcn:h-dcn,zktk:zktk-tenant")

    assert reader.resolve_slug("hdcn") == "h-dcn"
    assert reader.resolve_slug("zktk") == "zktk-tenant"


def test_resolve_slug_is_bounded_to_the_queried_slug(reader, monkeypatch):
    # One slug never resolves to another's tenant.
    monkeypatch.setenv(SLUG_MAP_ENV, "hdcn:h-dcn,zktk:zktk-tenant")

    assert reader.resolve_slug("hdcn") != reader.resolve_slug("zktk")


# ── fail-safe / empty-is-valid (R2.3 / R1a.4) ────────────────────────────────────────────


def test_unknown_slug_returns_none(reader, monkeypatch):
    monkeypatch.setenv(SLUG_MAP_ENV, "hdcn:h-dcn")

    assert reader.resolve_slug("not-a-tenant") is None


def test_unset_map_returns_none_for_every_slug(reader, monkeypatch):
    monkeypatch.delenv(SLUG_MAP_ENV, raising=False)

    assert reader.resolve_slug("hdcn") is None


def test_blank_map_returns_none(reader, monkeypatch):
    monkeypatch.setenv(SLUG_MAP_ENV, "   ")

    assert reader.resolve_slug("hdcn") is None


@pytest.mark.parametrize(
    "malformed",
    [
        "no-colon-here",  # no separator at all
        ":orphan-tenant",  # missing slug
        "orphan-slug:",  # missing tenant
        ",, ,",  # only separators / blanks
    ],
)
def test_malformed_pairs_are_skipped_not_raised(reader, monkeypatch, malformed):
    # A malformed projection degrades to a smaller/empty allow-list — never a crash on a public
    # request. The one well-formed slug is unaffected.
    monkeypatch.setenv(SLUG_MAP_ENV, f"{malformed},hdcn:h-dcn")

    assert reader.resolve_slug("hdcn") == "h-dcn"
    assert reader.resolve_slug("orphan-slug") is None
    assert reader.resolve_slug("no-colon-here") is None


def test_non_string_slug_is_none(reader, monkeypatch):
    monkeypatch.setenv(SLUG_MAP_ENV, "hdcn:h-dcn")

    assert reader.resolve_slug(None) is None  # type: ignore[arg-type]
    assert reader.resolve_slug("") is None


# ── resolved at call time + case-folded keys ─────────────────────────────────────────────


def test_map_is_resolved_at_call_time(reader, monkeypatch):
    # No module reload: a changed env is honoured on the next call.
    monkeypatch.setenv(SLUG_MAP_ENV, "hdcn:first-tenant")
    assert reader.resolve_slug("hdcn") == "first-tenant"

    monkeypatch.setenv(SLUG_MAP_ENV, "hdcn:second-tenant")
    assert reader.resolve_slug("hdcn") == "second-tenant"


def test_map_keys_are_case_folded(reader, monkeypatch):
    # A mapping authored with stray case still matches the resolver's normalized (lower-cased)
    # lookup, so reader and resolver cannot drift.
    monkeypatch.setenv(SLUG_MAP_ENV, "HDCN : h-dcn")

    assert reader.resolve_slug("hdcn") == "h-dcn"


# ── satisfies the Protocol + works end-to-end through TenantDirectory ────────────────────


def test_reader_satisfies_the_tenant_slug_reader_protocol(reader):
    assert isinstance(reader, TenantSlugReader)


def test_end_to_end_through_the_resolver(monkeypatch):
    # The whole seam the public edge wires (task 1.3): EnvTenantSlugReader behind TenantDirectory.
    monkeypatch.setenv(SLUG_MAP_ENV, "hdcn:h-dcn")
    directory = TenantDirectory(EnvTenantSlugReader())

    hit = directory.resolve("HDCN")  # case-insensitive at the resolver
    assert hit.ok is True
    assert hit.tenant_id == "h-dcn"

    miss = directory.resolve("not-a-tenant")
    assert miss.ok is False
    assert miss.failure is ResolveFailure.NOT_FOUND
