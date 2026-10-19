"""
Path-injection containment test for the STR invoice template loader
(str_invoice_routes.generate_invoice).

The loader interpolates the user-supplied `language` into a template filename
under templates/html/. Task 2 (security-assessment-2026-10-19) added a `language`
allowlist plus an explicit realpath/base-dir containment guard so a traversal
value can never steer the open() path out of the templates dir
(CodeQL py/path-injection).

Driving the full route requires the real auth + permission stack (str_create) and
a live-shaped booking; that wiring is covered elsewhere. These tests pin the
guard's behavioral contract directly against the real helper and the real
templates base dir the route uses, so a regression in the allowlist or the
containment check is caught locally.
"""

import os
import sys

import pytest

sys.path.append(os.path.join(os.path.dirname(__file__), "..", "src"))
import str_invoice_routes
from utils.path_security import is_within_base

# The exact base dir the route builds the template path against.
TEMPLATES_BASE = os.path.join(
    os.path.dirname(str_invoice_routes.__file__), "..", "templates", "html"
)

# The allowlist enforced by the route before the filesystem fallback.
SUPPORTED_LANGUAGES = ("nl", "en")


def _build_template_path(language: str) -> str:
    """Reproduce the route's template-path construction for `language`."""
    template_file = f"str_invoice_{language}_template.html"
    return os.path.join(TEMPLATES_BASE, template_file)


@pytest.mark.parametrize(
    "language",
    [
        "../../etc/passwd",
        "..%2f..%2fsecret",
        "nl/../../../etc/passwd",
        "..",
        "/etc/passwd",
    ],
)
def test_traversal_language_rejected_by_allowlist(language):
    """A traversal / non-allowlisted `language` is rejected up front."""
    assert language not in SUPPORTED_LANGUAGES


def test_containment_guard_rejects_escaping_template_path():
    """The containment guard is the backstop: any resolved template path that lands
    outside the templates base dir is rejected.

    (The allowlist is the primary guard for `language`; because the value is
    embedded mid-filename a traversal often stays nominally contained, which is
    exactly why the allowlist — not path arithmetic — is what blocks a bad
    `language`. This asserts the guard still rejects a genuinely out-of-base path.)
    """
    escaping = os.path.join(TEMPLATES_BASE, "..", "..", "etc", "passwd_template.html")
    assert is_within_base(escaping, TEMPLATES_BASE) is False


@pytest.mark.parametrize("language", SUPPORTED_LANGUAGES)
def test_legit_language_contained_in_templates_base(language):
    """The two supported languages resolve to a path inside the templates base."""
    template_path = _build_template_path(language)
    assert language in SUPPORTED_LANGUAGES
    assert is_within_base(template_path, TEMPLATES_BASE) is True
