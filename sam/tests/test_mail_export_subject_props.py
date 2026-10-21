"""
Property-based coverage of the WORKER pivot-export SUBJECT rule (members-overview-tweaks
task 6.5). The min-100-iteration companion to the focused unit coverage in
``sam/tests/test_mail_export_naming.py`` (``TestExportSubject``) — it pins the pure
:func:`~sam.members.worker.mail_send_worker._export_subject` helper (added task 6.2) across a
wide input space so the SAM worker's tenant-prefixed ``{Tenant} - {Pivot}`` subject rule cannot
silently drift. Sibling of the FILENAME property suite
(``sam/tests/test_mail_export_naming_props.py``, Property 4) — same generator + oracle shape,
pinning the subject composition instead of the attachment name.

Feature: members-overview-tweaks, Property 5: Email subject prefixes the tenant name before the pivot name

Validates: Requirements 5.3

What this asserts (universally, over varied tenant/pivot name pairs)
-------------------------------------------------------------------
The helper is PURE — it takes a tenant display name + a pivot display name and returns an email
subject — so this suite drives it with generated names carrying spaces, punctuation, unicode,
path separators, control chars, and empty/blank parts (the hostile inputs the
``_sanitize_export_part`` mirror must neutralise). Three universal invariants, each >=100
generated iterations (``@settings(max_examples=200)``):

- ``test_property_non_blank_parts_prefix_tenant_before_pivot`` (R5.3): whenever BOTH parts
  sanitize to something non-blank, the subject is EXACTLY ``{sanitize(tenant)} - {sanitize(pivot)}``,
  it STARTS WITH the sanitized tenant name (leading prefix), and the sanitized pivot name appears
  AFTER the tenant prefix (tenant index < pivot index).
- ``test_property_blank_part_falls_back_to_generic`` (R5.3 error handling): whenever EITHER part
  sanitizes to blank (older in-flight job with no stamped names, or a name that sanitizes to
  nothing), the subject is the safe generic ``DEFAULT_EXPORT_SUBJECT`` ("Member set") — never a
  lopsided ``"Tenant - "`` / ``" - Pivot"``, never a raise.
- ``test_property_matches_independent_oracle`` (R5.3): for ANY input the subject equals the rule
  recomputed independently from the sanitized parts, so the exact composed subject is pinned on
  every generated pair.

No live AWS, no MySQL — the helper is a pure string function. sys.path setup mirrors
``sam/conftest.py`` and the sibling tests so ``sam.members`` imports resolve.
"""

from __future__ import annotations

import os
import sys

from hypothesis import given, settings
from hypothesis import strategies as st

# repo root on sys.path (mirrors sam/conftest.py + the sibling tests) so `sam.members` imports.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from sam.members.worker.mail_send_worker import (  # noqa: E402
    DEFAULT_EXPORT_SUBJECT,
    _export_subject,
    _sanitize_export_part,
)

# ── name-part generator ────────────────────────────────────────────────────────────────
#
# Varied tenant/pivot display names: plain text, spaces, punctuation, unicode, path
# separators (/ \), ASCII control chars, and empty/blank parts — the full hostile input space
# the sanitize rule must neutralise. ``None`` is included so the "no stamped name" (older
# in-flight job) case is exercised alongside strings-that-sanitize-to-blank. Mirrors the
# generator in the sibling filename property suite (task 6.4).
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
        return DEFAULT_EXPORT_SUBJECT
    return f"{t} - {p}"


# ── properties ───────────────────────────────────────────────────────────────────────────


class TestWorkerExportSubjectProperty:
    """Feature: members-overview-tweaks, Property 5: Email subject prefixes the tenant name
    before the pivot name. Validates: Requirements 5.3."""

    @settings(max_examples=200)
    @given(tenant=_NAME_PARTS, pivot=_NAME_PARTS)
    def test_property_non_blank_parts_prefix_tenant_before_pivot(self, tenant, pivot):
        """R5.3: both parts non-blank ⇒ subject is ``{tenant} - {pivot}`` with the tenant as a
        leading prefix and the pivot appearing after it (tenant index < pivot index)."""
        t = _sanitize_export_part(tenant)
        p = _sanitize_export_part(pivot)
        subject = _export_subject(tenant, pivot)
        if t and p:
            # Exact composition: tenant prefix + separator + pivot.
            assert subject == f"{t} - {p}"
            # Leading prefix: the subject starts with the sanitized tenant name.
            assert subject.startswith(t)
            # Ordering: the pivot appears AFTER the tenant prefix. The composed subject places
            # the pivot immediately past the ``{tenant} - `` boundary, so the first occurrence of
            # the pivot sits at/after that boundary and strictly after the leading tenant index.
            pivot_at = subject.index(p, len(t))
            assert subject.index(t) < pivot_at

    @settings(max_examples=200)
    @given(tenant=_NAME_PARTS, pivot=_NAME_PARTS)
    def test_property_blank_part_falls_back_to_generic(self, tenant, pivot):
        """R5.3: either part sanitizes to blank ⇒ the safe generic ``Member set`` fallback."""
        t = _sanitize_export_part(tenant)
        p = _sanitize_export_part(pivot)
        subject = _export_subject(tenant, pivot)
        if not t or not p:
            assert subject == DEFAULT_EXPORT_SUBJECT == "Member set"

    @settings(max_examples=200)
    @given(tenant=_NAME_PARTS, pivot=_NAME_PARTS)
    def test_property_matches_independent_oracle(self, tenant, pivot):
        """R5.3: for ANY input the composed subject equals the independently-recomputed rule, so
        the exact subject (not just the prefix) is pinned on every generated pair."""
        assert _export_subject(tenant, pivot) == _expected(tenant, pivot)
