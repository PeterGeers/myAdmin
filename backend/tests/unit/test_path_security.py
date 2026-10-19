"""
Unit tests for the shared path-containment guard (utils.path_security).

This is the single helper that every path-injection sink in Task 2
(security-assessment-2026-10-19) funnels through — file-cleanup, the docs
route in app.py, the STR invoice template loader, and the sysadmin test-tool
upload. The tests pin the containment contract: realpath canonicalization,
traversal rejection, sibling-prefix rejection, and fail-closed behavior
(CodeQL py/path-injection).
"""

import os
import sys
import tempfile

import pytest

sys.path.append(os.path.join(os.path.dirname(__file__), "..", "src"))
from utils.path_security import is_within_base


@pytest.fixture
def base_dir():
    with tempfile.TemporaryDirectory() as d:
        yield os.path.realpath(d)


class TestIsWithinBase:
    def test_accepts_direct_child(self, base_dir):
        assert is_within_base(os.path.join(base_dir, "file.txt"), base_dir) is True

    def test_accepts_nested_child(self, base_dir):
        nested = os.path.join(base_dir, "a", "b", "c.txt")
        assert is_within_base(nested, base_dir) is True

    def test_accepts_base_itself(self, base_dir):
        assert is_within_base(base_dir, base_dir) is True

    def test_rejects_parent_traversal(self, base_dir):
        escaping = os.path.join(base_dir, "..", "..", "etc", "passwd")
        assert is_within_base(escaping, base_dir) is False

    def test_rejects_embedded_traversal(self, base_dir):
        escaping = os.path.join(base_dir, "sub", "..", "..", "secret")
        assert is_within_base(escaping, base_dir) is False

    def test_rejects_sibling_prefix(self, base_dir):
        """A sibling dir sharing a name prefix must NOT satisfy containment."""
        sibling = base_dir + "_evil"
        assert is_within_base(os.path.join(sibling, "x"), base_dir) is False

    def test_rejects_unrelated_absolute_path(self, base_dir):
        assert is_within_base("/etc/passwd", base_dir) is False

    def test_accepts_when_in_any_of_multiple_bases(self, base_dir):
        with tempfile.TemporaryDirectory() as other:
            other = os.path.realpath(other)
            candidate = os.path.join(other, "f")
            assert is_within_base(candidate, base_dir, other) is True

    def test_fail_closed_on_empty_candidate(self, base_dir):
        assert is_within_base("", base_dir) is False

    def test_fail_closed_on_no_bases(self, base_dir):
        assert is_within_base(os.path.join(base_dir, "f")) is False


class TestTemplatePathContainment:
    """Reproduces the STR-invoice / docs-route construction: a user-influenced
    segment joined onto a fixed base, then containment-checked. A traversal
    segment must be rejected before the open()/send sink."""

    def test_legit_language_segment_contained(self, base_dir):
        for language in ("nl", "en"):
            template = os.path.join(base_dir, f"str_invoice_{language}_template.html")
            assert is_within_base(template, base_dir) is True

    def test_traversal_segment_escapes_base(self, base_dir):
        # If an attacker-controlled segment contained traversal, the join escapes
        # the templates base and containment rejects it.
        malicious = os.path.join(base_dir, "..", "..", "etc", "passwd")
        assert is_within_base(malicious, base_dir) is False


if __name__ == "__main__":
    pytest.main([__file__])
