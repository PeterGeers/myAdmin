"""
S5d Task 0.3 — cross-plane **``scope_canon`` drift** property test (design Property 4).

Feature: s5d-member-scope-assignment, Property 4: Canonical exactness (cross-plane agreement).

Validates: Requirements 9.6

What this asserts (the two transcriptions never drift)
------------------------------------------------------
``scope_canon`` is the ONE canonicalizer used everywhere a scope value is compared or stored
(design → Components → "Shared canonicalization ``scope_canon``", R9.6, D5). Because the SAM
module (``sam/members``, Lambda) and the Flask/MySQL app (``backend/src``, Railway) are
independently deployed with SEPARATE Python paths — ``backend/src`` does not (and must not) put
``sam`` on its import path — the function is carried as TWO identical transcriptions:

- module plane: ``sam/members/domain/scope_canon.py``
- Flask plane:  ``backend/src/services/scope_canon.py``

(the same cross-plane-transcription pattern as ``members_config_validation.py`` copying the
field-key set rather than importing it). Two independent copies can DRIFT — one edited without
the other — which would silently break enforcement (a member visible on one plane's canon but
denied on the other's). This property guards against that: for ANY input, the two transcriptions
MUST return BYTE-FOR-BYTE identical output.

The property (≥200 generated iterations, ``@settings(max_examples=...)``)
-------------------------------------------------------------------------
For any generated value ``v`` — unicode text, diacritics, mixed case, the separators
space/``-``/``/``, a curated shared vocabulary of realistic region-like values, and
non-string/``None`` degenerate inputs — ``sam_scope_canon(v) == flask_scope_canon(v)`` exactly
(``==`` on ``str``), AND both agree on the exported ``CANONICAL_SEPARATOR`` constant.

Import placement (both planes in ONE test process)
--------------------------------------------------
This test runs under the SAM suite (``sam/pytest.ini``; design → Testing → SAM domain). Both
transcriptions import cleanly in one process because they live under DIFFERENT package paths
(``sam.members.domain.scope_canon`` vs ``services.scope_canon``), so there is no module-name
collision — we add both the repo root and ``backend/src`` to ``sys.path`` (mirrors
``sam/tests/test_scope_grant_deny_props.py`` / ``test_config_roundtrip_props.py``, which already
reach ``services.*`` from the SAM suite). No live AWS, no MySQL — both functions are pure.
"""

import os
import sys

from hypothesis import given, settings
from hypothesis import strategies as st

# repo root on sys.path (mirrors sam/conftest.py) so `sam.members` imports.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

# backend/src on sys.path so the Flask-plane `services.scope_canon` resolves (mirrors
# test_scope_grant_deny_props.py reaching `services.projection_schema` from the SAM suite).
_BACKEND_SRC = os.path.join(_REPO_ROOT, "backend", "src")
if _BACKEND_SRC not in sys.path:
    sys.path.insert(0, _BACKEND_SRC)

# The two transcriptions under distinct qualified names (distinct package paths → no collision).
from sam.members.domain.scope_canon import scope_canon as sam_scope_canon
from sam.members.domain.scope_canon import CANONICAL_SEPARATOR as SAM_SEPARATOR
from services.scope_canon import scope_canon as flask_scope_canon
from services.scope_canon import CANONICAL_SEPARATOR as FLASK_SEPARATOR


# ---------------------------------------------------------------------------
# A curated shared vocabulary of realistic region-like values (and case/diacritic/
# separator variants of them) — the concrete inputs enforcement actually canonicalizes.
# ---------------------------------------------------------------------------

_SHARED_VOCABULARY = [
    # Dutch province / region names with diacritics, hyphens, slashes, spacing.
    "Noord-Holland",
    "Zuid-Holland",
    "Noord Holland",
    "Noord / Holland",
    "Fryslân",
    "FRYSLÂN",
    "fryslÂn",
    "Groningen/Drenthe",
    "Groningen / Drenthe",
    "Groningen-Drenthe",
    "Groningen Drenthe",
    "Overijssel",
    "Gelderland",
    "Noord-Brabant",
    "noord-brabant",
    "NOORD-BRABANT",
    "Zeeland",
    "Utrecht",
    "Curaçao",
    "CURAÇAO",
    "'s-Hertogenbosch",
    "Sint-Michielsgestel",
    # separator / whitespace / casing edge shapes.
    "  Oost  ",
    "Oost",
    "OOST",
    "oOsT",
    "West / Oost",
    "West-Oost",
    "a - b / c",
    "a b c",
    # degenerate / empty-ish.
    "",
    "   ",
    "---",
    "///",
    " / - / ",
    # a compatibility form + a ß (casefold expands to "ss").
    "ﬁnance",   # U+FB01 LATIN SMALL LIGATURE FI — NFKD → "fi"
    "Straße",
    "STRASSE",
]


# ---------------------------------------------------------------------------
# Strategies — cover the full input space the two transcriptions must agree on.
# ---------------------------------------------------------------------------

# The separator chars scope_canon folds (space / - /) plus a mix of unicode letters,
# diacritics, mixed case and whitespace — so generated inputs exercise every step
# (NFKD, mark-stripping, casefold, separator-folding, trim).
_SEPARATORS = " \t\n-/"
_LETTERS_AND_DIACRITICS = (
    "abcdefghijklmnopqrstuvwxyz"
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    "áàâäãåéèêëíìîïóòôöõúùûüñçøæßÿ"
    "ÁÀÂÄÃÅÉÈÊËÍÌÎÏÓÒÔÖÕÚÙÛÜÑÇØÆŸ"
    "0123456789"
)

# A text strategy weighted toward the separators + accented letters this function targets.
_targeted_text = st.text(
    alphabet=st.sampled_from(list(_LETTERS_AND_DIACRITICS + _SEPARATORS)),
    max_size=24,
)

# Arbitrary unicode text (broad coverage, incl. combining marks, exotic scripts, control chars).
_arbitrary_text = st.text(max_size=24)

# The curated realistic vocabulary.
_vocabulary_text = st.sampled_from(_SHARED_VOCABULARY)

# Non-string / None degenerate inputs (both planes must map these to "" identically).
_non_string = st.one_of(
    st.none(),
    st.integers(),
    st.booleans(),
    st.floats(allow_nan=False, allow_infinity=False),
    st.lists(st.text(max_size=3), max_size=3),
    st.binary(max_size=8),
)

# The full generated input space for the drift property.
_any_input = st.one_of(
    _vocabulary_text,
    _targeted_text,
    _arbitrary_text,
    _non_string,
)


# ---------------------------------------------------------------------------
# Property 4 — the two transcriptions produce byte-for-byte identical output (R9.6).
# ---------------------------------------------------------------------------


@settings(max_examples=500)
@given(value=_any_input)
def test_property_scope_canon_planes_agree(value):
    """Feature: s5d-member-scope-assignment, Property 4: Canonical exactness (cross-plane).

    Validates: Requirements 9.6

    For ANY input — unicode text, diacritics, mixed case, the separators space/``-``/``/``, the
    curated region-like vocabulary, and non-string/``None`` degenerate values — the SAM-plane and
    Flask-plane ``scope_canon`` transcriptions return BYTE-FOR-BYTE identical output. Any drift
    between the two copies fails this property.
    """
    sam_out = sam_scope_canon(value)
    flask_out = flask_scope_canon(value)

    # Byte-for-byte identical: same type (str) and same value.
    assert sam_out == flask_out
    assert type(sam_out) is type(flask_out)
    assert isinstance(sam_out, str)


@settings(max_examples=200)
@given(value=_vocabulary_text)
def test_property_scope_canon_planes_agree_on_shared_vocabulary(value):
    """Feature: s5d-member-scope-assignment, Property 4: Canonical exactness (cross-plane).

    Validates: Requirements 9.6

    Focused restatement over ONLY the curated shared vocabulary of realistic region-like values
    (``Noord-Holland``, ``Fryslân``, ``Groningen/Drenthe``, …) — the concrete inputs enforcement
    canonicalizes in production. Both planes agree byte-for-byte on every one.
    """
    assert sam_scope_canon(value) == flask_scope_canon(value)


def test_planes_export_identical_canonical_separator():
    """Validates: Requirements 9.6.

    The exported ``CANONICAL_SEPARATOR`` constant (the single separator both planes fold to)
    must be identical across the two transcriptions — a drift here would diverge every folded
    value.
    """
    assert SAM_SEPARATOR == FLASK_SEPARATOR
