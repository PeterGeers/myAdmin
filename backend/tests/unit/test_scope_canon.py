"""Unit tests for the shared ``scope_canon`` canonicalizer (tenant-scoping).

``scope_canon`` is the ONE canonical form used wherever a scope value is compared
or stored. Enforcement is exact-equality on the canonical form (never partial /
prefix / fuzzy), so these tests focus on:

- the happy path (an ordinary value canonicalizes to its lowercased, trimmed form),
- the fold rules (diacritic-fold, casefold, separator-fold) that make equivalent
  spellings collapse to one string,
- cross-tenant isolation: two genuinely different scope values must NOT collide
  on their canonical form, and a canonical value must not match by prefix/substring,
- the deny-by-default edge: a non-string / ``None`` canonicalizes to ``""`` which
  never equals a real granted value.
"""

import pytest

from services.scope_canon import CANONICAL_SEPARATOR, scope_canon


class TestScopeCanonHappyPath:
    """Ordinary values canonicalize predictably."""

    def test_simple_value_is_lowercased_and_trimmed(self):
        assert scope_canon("  Amsterdam  ") == "amsterdam"

    def test_already_canonical_value_is_idempotent(self):
        once = scope_canon("noord holland")
        assert once == "noord holland"
        assert scope_canon(once) == once

    def test_empty_string_canonicalizes_to_empty(self):
        assert scope_canon("") == ""

    def test_whitespace_only_canonicalizes_to_empty(self):
        assert scope_canon("   \t  ") == ""


class TestScopeCanonFolds:
    """Diacritic / case / separator variants collapse to one canonical form."""

    @pytest.mark.parametrize(
        "variant",
        [
            "Noord Holland",
            "noord-holland",
            "Noord / Holland",
            "NOORD   HOLLAND",
            "noord\tholland",
        ],
    )
    def test_separator_and_case_variants_fold_to_one_form(self, variant):
        """space / '-' / '/' runs + case all collapse to 'noord holland'."""
        assert scope_canon(variant) == "noord holland"

    def test_diacritics_are_folded(self):
        """Combining marks are stripped (é -> e), so accented spellings match."""
        assert scope_canon("Zélande") == scope_canon("Zelande")
        assert scope_canon("Zélande") == "zelande"

    def test_casefold_handles_sharp_s(self):
        """casefold is more aggressive than lower(): ß -> ss."""
        assert scope_canon("Straße") == "strasse"

    def test_separator_run_folds_to_single_canonical_separator(self):
        result = scope_canon("a---b")
        assert result == f"a{CANONICAL_SEPARATOR}b"
        assert "  " not in result


class TestScopeCanonCrossTenantIsolation:
    """Different scope values must not collide; matching is exact, not fuzzy."""

    def test_distinct_values_do_not_canonicalize_equal(self):
        """Two different regions stay distinct after canonicalization."""
        assert scope_canon("Noord-Holland") != scope_canon("Zuid-Holland")

    def test_prefix_does_not_match_full_value(self):
        """Exact-equality: a prefix is not equal to the full canonical value."""
        full = scope_canon("Noord-Holland")
        prefix = scope_canon("Noord")
        assert prefix != full
        # And the deny-by-default: a prefix is not a substring-match surrogate.
        assert not full.startswith(prefix + "x")

    def test_substring_variant_does_not_collapse_into_another_scope(self):
        assert scope_canon("Holland") != scope_canon("Noord Holland")


class TestScopeCanonDenyByDefaultEdges:
    """Absent / unusable values canonicalize to '' (never match a real grant)."""

    @pytest.mark.parametrize("bad", [None, 123, 4.5, ["list"], {"a": 1}, object()])
    def test_non_string_canonicalizes_to_empty(self, bad):
        assert scope_canon(bad) == ""

    def test_empty_canonical_never_equals_a_real_value(self):
        """The '' from a missing value must not match any real granted scope."""
        granted = scope_canon("Noord-Holland")
        absent = scope_canon(None)
        assert absent == ""
        assert absent != granted
