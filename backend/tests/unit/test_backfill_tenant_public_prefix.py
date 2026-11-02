"""
Unit tests for the tenants.public_prefix backfill derivation (spec 14 R2).

Covers the derivation contract: slug-safe ([a-z0-9-]), length window [3, 20],
the documented ``vandenheuvelhoveniers`` -> short-form example, global
uniqueness with deterministic collision resolution, and determinism (a re-run
produces the identical mapping). Pure-function tests — no DB.

Requirements: Spec 14 R2.1, R2.3
"""

import re

import pytest

from migrations.backfill_tenant_public_prefix import (
    MAX_LEN,
    MIN_LEN,
    derive_base_prefix,
    derive_unique_prefixes,
)

SLUG_RE = re.compile(r"^[a-z0-9-]+$")


def _is_slug_safe(value):
    return (
        bool(SLUG_RE.match(value))
        and not value.startswith("-")
        and not value.endswith("-")
    )


class TestDeriveBasePrefix:
    def test_short_name_used_as_is(self):
        assert derive_base_prefix("h-dcn") == "h-dcn"

    def test_long_name_documented_short_form(self):
        # The spec's worked example.
        assert derive_base_prefix("vandenheuvelhoveniers") == "vdh"

    def test_camelcase_long_name_is_shortened_within_window(self):
        prefix = derive_base_prefix("GoodwinSolutions")
        assert _is_slug_safe(prefix)
        assert MIN_LEN <= len(prefix) <= MAX_LEN

    @pytest.mark.parametrize(
        "name",
        [
            "GoodwinSolutions",
            "PeterPrive",
            "myAdmin",
            "InterimManagement",
            "kimengerbrand",
            "kimgeers",
            "vandenheuvelhoveniers",
            "h-dcn",
            "s3test_str",
            "s3test_full",
            "s3test_hdcn",
            "A very long administration name that exceeds twenty chars",
        ],
    )
    def test_derivation_is_slug_safe_and_within_length(self, name):
        prefix = derive_base_prefix(name)
        assert _is_slug_safe(prefix), f"{name!r} -> {prefix!r} not slug-safe"
        assert MIN_LEN <= len(prefix) <= MAX_LEN, f"{name!r} -> {prefix!r} length"

    def test_none_raises(self):
        with pytest.raises(ValueError):
            derive_base_prefix(None)


class TestDeriveUniquePrefixes:
    def test_all_existing_tenants_get_unique_slug_safe_values(self):
        # Mirrors the live local-Docker tenants table (11 rows).
        tenants = [
            {"id": 1, "administration": "GoodwinSolutions"},
            {"id": 2, "administration": "PeterPrive"},
            {"id": 3, "administration": "myAdmin"},
            {"id": 4, "administration": "InterimManagement"},
            {"id": 5, "administration": "kimengerbrand"},
            {"id": 6, "administration": "kimgeers"},
            {"id": 7, "administration": "vandenheuvelhoveniers"},
            {"id": 8, "administration": "h-dcn"},
            {"id": 9, "administration": "s3test_str"},
            {"id": 10, "administration": "s3test_full"},
            {"id": 11, "administration": "s3test_hdcn"},
        ]
        result = derive_unique_prefixes(tenants)

        assert len(result) == len(tenants)
        values = list(result.values())
        assert len(set(values)) == len(values), f"collision in {values}"
        for v in values:
            assert _is_slug_safe(v)
            assert MIN_LEN <= len(v) <= MAX_LEN
        # The documented example still resolves to its short form.
        assert result[7] == "vdh"

    def test_collisions_resolved_deterministically(self):
        # Two names that slugify identically must not collide.
        tenants = [
            {"id": 1, "administration": "Acme Club"},
            {"id": 2, "administration": "acme-club"},
            {"id": 3, "administration": "ACME!CLUB"},
        ]
        result = derive_unique_prefixes(tenants)
        values = list(result.values())
        assert len(set(values)) == 3, f"expected unique, got {values}"
        # Lowest id keeps the base; later ids get stable numbered suffixes.
        assert result[1] == "acme-club"
        assert result[2] == "acme-club-2"
        assert result[3] == "acme-club-3"

    def test_deterministic_across_runs(self):
        tenants = [
            {"id": 3, "administration": "myAdmin"},
            {"id": 1, "administration": "GoodwinSolutions"},
            {"id": 7, "administration": "vandenheuvelhoveniers"},
        ]
        first = derive_unique_prefixes(tenants)
        second = derive_unique_prefixes(list(reversed(tenants)))
        assert first == second
