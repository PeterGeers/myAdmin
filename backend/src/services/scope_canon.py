"""
S5d Task 0.2 — the shared ``scope_canon`` canonicalizer (Flask/MySQL plane transcription).

This is the Flask-plane copy of the ONE canonical form used everywhere a scope value is
compared or stored (design → Components → "Shared canonicalization ``scope_canon``", R9.6,
D5, Property 4 "Canonical exactness"). It normalizes a scope value — a member's field
value on write/import (R9.2), a granted value validated at authoring (R4.2), and the R9.5
verification check — to a canonical string so enforcement is **exact-equality on the
canonical form**, never partial/prefix/fuzzy (R3.5).

Cross-plane reuse decision (same rationale as ``members_config_validation.py``)
-------------------------------------------------------------------------------
The module-plane home is ``sam/members/domain/scope_canon.py``. We do NOT import it here:
the Flask/MySQL app (``backend/src``, Railway) and the SAM module (``sam/members``, Lambda)
are independently deployed and packaged with SEPARATE Python paths — ``backend/src`` does
not (and must not) place ``sam`` on its import path. So, exactly as
``members_config_validation.py`` transcribes the SAM-domain field-key set rather than
importing it, this file is an IDENTICAL transcription of the module-plane
``scope_canon``. A cross-plane property test (task 0.3) asserts the two produce byte-for-
byte identical output over a shared vocabulary, guarding against drift.

The canonicalization steps (in order):

1. ``unicodedata.normalize("NFKD")`` — decompose base letter + combining diacritic (and
   compatibility forms).
2. Strip combining marks (Unicode category ``Mn``) — the diacritic-fold (``é`` → ``e``).
3. ``str.casefold()`` — locale-independent aggressive lowercasing (``ß`` → ``ss``).
4. Fold separators — every run of space / ``-`` / ``/`` (and surrounding whitespace)
   collapses to ONE canonical separator, so ``"Noord Holland"`` / ``"Noord-Holland"`` /
   ``"Noord / Holland"`` all become ``"noord holland"``.
5. Trim — strip leading/trailing whitespace.

Pure function: same input → same output, no I/O, no globals mutated.
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
