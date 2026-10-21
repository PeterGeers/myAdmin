"""
Property-based coverage of the WORKER pivot-export FILENAME rule (members-overview-tweaks
task 6.4). The min-100-iteration companion to the focused unit coverage in
``sam/tests/test_mail_export_naming.py`` — it pins the pure
:func:`~sam.members.worker.mail_send_worker._export_file_name` helper (added task 6.2) across a
wide input space so the SAM worker's ``{Tenant}-{Pivot}.csv`` rule cannot silently drift from
the frontend mirror (``frontend/src/utils/csvExport.ts``, Property 3).

Feature: members-overview-tweaks, Property 4: Worker attachment filename follows the tenant-pivot rule

Validates: Requirements 5.2, 5.5

What this asserts (universally, over varied tenant/pivot name pairs)
-------------------------------------------------------------------
The helper is PURE — it takes a tenant display name + a pivot display name and returns a
filename — so this suite drives it with generated names carrying spaces, punctuation, unicode,
path separators, control chars, and empty/blank parts (the hostile inputs the ``_sanitize_export_part``
mirror must neutralise). Three universal invariants, each ≥100 generated iterations
(``@settings(max_examples=100)``):

- ``test_property_non_blank_parts_follow_tenant_pivot_rule`` (R5.2/R5.5): whenever BOTH parts
  sanitize to something non-blank, the result is EXACTLY ``{sanitize(tenant)}-{sanitize(pivot)}.csv``.
- ``test_property_blank_part_falls_back_to_generic`` (R5.5 error handling): whenever EITHER part
  sanitizes to blank (older in-flight job with no stamped names, or a name that sanitizes to
  nothing), the result is the safe generic ``export.csv`` — never a malformed ``-.csv``, never a
  raise.
- ``test_property_always_csv_and_never_the_old_fixed_name`` (R5.5): for ANY input the result
  ALWAYS ends in ``.csv`` and is NEVER the old fixed ``members.csv``.

No live AWS, no MySQL — the helper is a pure string function. sys.path setup mirrors
``sam/conftest.py`` and the sibling unit test so ``sam.members`` imports resolve.
"""

from __future__ import annotations

import os
import sys

from hypothesis import given, settings
from hypothesis import strategies as st

# repo root on sys.path (mirrors sam/conftest.py + the sibling unit test) so `sam.members` imports.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from sam.members.worker.mail_send_worker import (  # noqa: E402
    DEFAULT_EXPORT_FILENAME,
    _export_file_name,
    _sanitize_export_part,
)

# ── name-part generator ────────────────────────────────────────────────────────────────
#
# Varied tenant/pivot display names: plain text, spaces, punctuation, unicode, path
# separators (/ \), ASCII control chars, and empty/blank parts — the full hostile input space
# the sanitize rule must neutralise. ``None`` is included so the "no stamped name" (older
# in-flight job) case is exercised alongside strings-that-sanitize-to-blank.
_NAME_PARTS = st.one_of(
    st.none(),
    st.just(""),
    st.just("   "),
    st.text(),  # arbitrary unicode incl. control chars, separators, punctuation
    st.text(
        alphabet=st.characters(
            whitelist_categories=("Lu", "Ll", "Nd", "Zs", "Po", "Sm"),
        ),
    ),
    # deliberately path-separator / control-char heavy inputs so the strip is well exercised
    st.text(alphabet="abc /\\\t\n\r\x00\x07.-_123 áéîöü"),
)


def _expected(tenant, pivot) -> str:
    """The rule, recomputed independently from the sanitized parts (the oracle)."""
    t = _sanitize_export_part(tenant)
    p = _sanitize_export_part(pivot)
    if not t or not p:
        return DEFAULT_EXPORT_FILENAME
    return f"{t}-{p}.csv"


# ── properties ───────────────────────────────────────────────────────────────────────────


class TestWorkerExportFilenameProperty:
    """Feature: members-overview-tweaks, Property 4: Worker attachment filename follows the
    tenant-pivot rule. Validates: Requirements 5.2, 5.5."""

    @settings(max_examples=200)
    @given(tenant=_NAME_PARTS, pivot=_NAME_PARTS)
    def test_property_non_blank_parts_follow_tenant_pivot_rule(self, tenant, pivot):
        """R5.2/R5.5: both parts non-blank ⇒ exactly ``{sanitize(tenant)}-{sanitize(pivot)}.csv``."""
        t = _sanitize_export_part(tenant)
        p = _sanitize_export_part(pivot)
        result = _export_file_name(tenant, pivot)
        if t and p:
            assert result == f"{t}-{p}.csv"

    @settings(max_examples=200)
    @given(tenant=_NAME_PARTS, pivot=_NAME_PARTS)
    def test_property_blank_part_falls_back_to_generic(self, tenant, pivot):
        """R5.5: either part sanitizes to blank ⇒ the safe generic ``export.csv`` fallback."""
        t = _sanitize_export_part(tenant)
        p = _sanitize_export_part(pivot)
        result = _export_file_name(tenant, pivot)
        if not t or not p:
            assert result == DEFAULT_EXPORT_FILENAME == "export.csv"

    @settings(max_examples=200)
    @given(tenant=_NAME_PARTS, pivot=_NAME_PARTS)
    def test_property_always_csv_and_never_the_old_fixed_name(self, tenant, pivot):
        """R5.5: for ANY input the result ends in ``.csv`` and is NEVER the old ``members.csv``.

        Also cross-checks the full rule against an independent oracle so the exact composed name
        (not just its suffix) is pinned on every generated pair.
        """
        result = _export_file_name(tenant, pivot)
        assert result.endswith(".csv")
        assert result != "members.csv"
        assert result == _expected(tenant, pivot)
