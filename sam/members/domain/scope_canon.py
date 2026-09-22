"""
S5d Task 0.2 — the shared ``scope_canon`` canonicalizer (module plane).

This module owns the ONE canonical form used everywhere a scope value is compared or
stored (design → Components → "Shared canonicalization ``scope_canon``", R9.6, D5,
Property 4 "Canonical exactness"). A scope value (a member's field value, or a granted
value in ``user_tenant_scope``) is reduced to a canonical string so that enforcement is
**exact-equality on the canonical form** — never partial, prefix, or fuzzy matching
(R3.5). The same function normalizes on write, so stored member values and grants share
one vocabulary.

The canonicalization steps (in order):

1. ``unicodedata.normalize("NFKD")`` — decompose so a base letter and its combining
   diacritic become separate code points (and compatibility forms decompose too).
2. Strip combining marks (Unicode category ``Mn``) — the diacritic-fold: ``é`` → ``e``,
   ``ü`` → ``u``, ``ø`` is NOT decomposed by NFKD so it is left as-is (there is no
   combining form to strip — this is expected and consistent across planes).
3. ``str.casefold()`` — aggressive, locale-independent lowercasing (``ß`` → ``ss``).
4. Fold separators — every run of space / ``-`` / ``/`` (and surrounding whitespace)
   collapses to ONE canonical separator (a single space). So ``"Noord Holland"``,
   ``"Noord-Holland"`` and ``"Noord / Holland"`` all canonicalize to ``"noord holland"``.
5. Trim — strip leading/trailing whitespace.

This is a PURE function: same input → same output, no I/O, no globals mutated. The
Flask/MySQL plane carries an IDENTICAL transcription
(``backend/src/services/scope_canon.py``) because the two planes share no Python path
(same pattern as ``members_config_validation.py`` transcribing the field-key set); a
cross-plane property test (task 0.3) asserts the two agree byte-for-byte.
"""

from __future__ import annotations

import re
import unicodedata

__all__ = ["scope_canon", "CANONICAL_SEPARATOR"]

#: The single separator every space / ``-`` / ``/`` run folds to.
CANONICAL_SEPARATOR = " "

#: A run of any separator char (space, ``-``, ``/``) or surrounding whitespace.
_SEPARATOR_RUN = re.compile(r"[\s\-/]+")


def scope_canon(value: object) -> str:
    """Return the canonical form of a scope value for exact-equality comparison.

    NFKD normalize → strip combining marks (diacritic-fold) → casefold → fold separators
    (space / ``-`` / ``/`` → one canonical separator) → trim. Pure and deterministic.

    A non-string (or ``None``) yields ``""`` — an absent/unusable value canonicalizes to
    the empty string, which never matches a real granted value (deny-by-default holds).
    """
    if not isinstance(value, str):
        return ""

    # 1. NFKD normalize (decompose base + combining diacritic / compatibility forms).
    decomposed = unicodedata.normalize("NFKD", value)

    # 2. Strip combining marks (category "Mn") — the diacritic-fold.
    without_marks = "".join(
        ch for ch in decomposed if unicodedata.category(ch) != "Mn"
    )

    # 3. Casefold (locale-independent aggressive lowercasing).
    folded = without_marks.casefold()

    # 4. Fold every separator run (space / - / /) to the one canonical separator.
    separators_folded = _SEPARATOR_RUN.sub(CANONICAL_SEPARATOR, folded)

    # 5. Trim leading/trailing whitespace.
    return separators_folded.strip()
