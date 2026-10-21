"""
SAM pytest for the WORKER export-naming helpers (members-overview-tweaks task 6.2, R5.2/5.3/5.5).

Pins the pure ``{Tenant_Name}-{Pivot_Name}`` naming rule the worker owns —
:func:`~sam.members.worker.mail_send_worker._export_file_name` /
:func:`~sam.members.worker.mail_send_worker._export_subject` and their shared
:func:`~sam.members.worker.mail_send_worker._sanitize_export_part` — the Python MIRROR of the
frontend rule in ``frontend/src/utils/csvExport.ts``. These are the sanitize + backward-compat
fallback helpers ONLY; task 6.3 threads them into ``_build_attachment`` / ``_render_to_fixed``
(and task 6.4/6.5 add the min-100-iteration property tests). This file is the focused unit
coverage of the rule in isolation: the ``{Tenant}-{Pivot}.csv`` / ``{Tenant} - {Pivot}`` shape,
the sanitize of path separators / control chars / whitespace, and the degrade-to-generic
fallback for an older in-flight job that carries no stamped names.

Validates: Requirements 5.2, 5.3, 5.5
"""

from __future__ import annotations

import os
import sys

import pytest

_REPO_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from sam.members.worker.mail_send_worker import (
    DEFAULT_EXPORT_FILENAME,
    DEFAULT_EXPORT_SUBJECT,
    _export_file_name,
    _export_subject,
    _sanitize_export_part,
)

pytestmark = pytest.mark.unit


# ── _sanitize_export_part ──────────────────────────────────────────────────────────────


class TestSanitizeExportPart:
    def test_sanitize_plain_name_unchanged(self):
        assert _sanitize_export_part("Acme Foundation") == "Acme Foundation"

    def test_sanitize_strips_path_separators(self):
        assert _sanitize_export_part("a/b\\c") == "abc"

    def test_sanitize_strips_control_chars(self):
        assert _sanitize_export_part("na\x00me\x07") == "name"

    def test_sanitize_collapses_whitespace_runs_to_single_space(self):
        assert _sanitize_export_part("foo\t\tbar\n\nbaz") == "foo bar baz"

    def test_sanitize_trims_edges(self):
        assert _sanitize_export_part("   edge   ") == "edge"

    def test_sanitize_none_is_empty(self):
        assert _sanitize_export_part(None) == ""

    def test_sanitize_blank_is_empty(self):
        assert _sanitize_export_part("   ") == ""


# ── _export_file_name ──────────────────────────────────────────────────────────────────


class TestExportFileName:
    def test_file_name_follows_tenant_pivot_rule(self):
        assert _export_file_name("Acme", "Members 2026") == "Acme-Members 2026.csv"

    def test_file_name_sanitizes_both_parts(self):
        assert _export_file_name("a/b", "c\\d") == "ab-cd.csv"

    def test_file_name_always_ends_in_csv(self):
        assert _export_file_name("Tenant", "Pivot").endswith(".csv")

    def test_file_name_never_the_old_fixed_members_csv(self):
        assert _export_file_name("Tenant", "Pivot") != "members.csv"

    def test_file_name_is_deterministic(self):
        assert _export_file_name("Tenant", "Pivot") == _export_file_name("Tenant", "Pivot")

    @pytest.mark.parametrize(
        "tenant,pivot",
        [
            ("", "Pivot"),      # missing tenant (older in-flight job)
            ("Tenant", ""),     # missing pivot
            ("", ""),           # both missing
            ("   ", "Pivot"),   # tenant sanitizes to blank
            (None, None),       # neither stamped
            ("///", "Pivot"),   # tenant sanitizes to empty after strip
        ],
    )
    def test_file_name_falls_back_to_generic_when_a_part_is_blank(self, tenant, pivot):
        # Backward-compat: degrade to a safe generic name rather than emit ``-.csv`` or raise.
        assert _export_file_name(tenant, pivot) == DEFAULT_EXPORT_FILENAME == "export.csv"


# ── _export_subject ────────────────────────────────────────────────────────────────────


class TestExportSubject:
    def test_subject_prefixes_tenant_before_pivot(self):
        subject = _export_subject("Acme", "Members 2026")
        assert subject == "Acme - Members 2026"
        assert subject.startswith("Acme")
        assert subject.index("Acme") < subject.index("Members 2026")

    def test_subject_sanitizes_both_parts(self):
        assert _export_subject("a/b", "c\\d") == "ab - cd"

    @pytest.mark.parametrize(
        "tenant,pivot",
        [
            ("", "Pivot"),
            ("Tenant", ""),
            ("", ""),
            (None, None),
            ("   ", "   "),
        ],
    )
    def test_subject_falls_back_to_generic_when_a_part_is_blank(self, tenant, pivot):
        assert _export_subject(tenant, pivot) == DEFAULT_EXPORT_SUBJECT == "Member set"
