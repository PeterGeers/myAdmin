"""
SAM smoke/unit tests for the spec-14 / D-RENDER plane-neutral shared page shell —
:func:`sam.shared.page_shell.render_page` (task 2.1).

These pin the shell's observable contract and its DEPENDENCY-FREE / PLANE-NEUTRAL guarantee
(R7.1). Output PARITY against a real Flask-shell fixture is the SEPARATE task 2.3; this file is
the minimal land-with-a-smoke-test companion for the extraction (steering 34).

Validates: Requirements R7.1 (plane-neutral, dependency-free shell), R7.3 (shared as a library)
"""

import os
import sys

_REPO_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

# The static-analysis test below (reading the source AST) is what PROVES page_shell needs
# nothing beyond stdlib + typing; the runtime import here goes through the package the same
# way a producer would.
from sam.shared import page_shell


def test_render_page_is_dependency_free_stdlib_only():
    """R7.1: the module imports ONLY stdlib (no Flask/boto3/DB/SAM, no backend/src)."""
    import ast

    # Allowed import roots: pure stdlib only. The guarantee is "no Flask, no boto3, no DB,
    # no SAM-specific/backend imports" — collections/html/typing are all stdlib.
    allowed = {"html", "typing", "collections"}

    src_path = os.path.join(_REPO_ROOT, "sam", "shared", "page_shell.py")
    with open(src_path, encoding="utf-8") as fh:
        tree = ast.parse(fh.read())

    imported_roots = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported_roots.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            # level 0 = absolute; relative imports would have level > 0
            assert node.level == 0, "page_shell must not use relative/package imports"
            if node.module:
                imported_roots.add(node.module.split(".")[0])

    assert imported_roots <= allowed, (
        f"page_shell must stay dependency-free; found extra imports: "
        f"{imported_roots - allowed}"
    )


def test_render_page_composes_head_body_and_css():
    """Happy path: head meta, body fragment, and CSS all land in the composed document."""
    head_meta = {
        "title": "Join Us",
        "description": "Membership application",
        "og_image": "https://cdn.example.org/og.png",
        "canonical": "https://apply.example.org/join",
        "site_name": "Example Org",
    }
    body_html = '<main id="app">FORM BODY</main>'
    css = ":root { --c: #2D5F8A; }\n.btn { color: var(--c); }"

    out = page_shell.render_page(head_meta, body_html, css)

    # Document scaffold
    assert out.startswith("<!DOCTYPE html>")
    assert out.rstrip().endswith("</html>")
    # Head meta (escaped values present in title + OG + Twitter + canonical)
    assert "<title>Join Us</title>" in out
    assert '<meta property="og:title" content="Join Us" />' in out
    assert '<meta name="twitter:title" content="Join Us" />' in out
    assert (
        '<meta property="og:image" content="https://cdn.example.org/og.png" />' in out
    )
    assert '<link rel="canonical" href="https://apply.example.org/join" />' in out
    assert '<meta property="og:site_name" content="Example Org" />' in out
    # CSS lands verbatim inside a single <style> block
    assert css in out
    assert out.count("<style>") == 1 and out.count("</style>") == 1
    # Body fragment lands verbatim inside <body>
    assert body_html in out
    assert "<body>" in out and "</body>" in out


def test_render_page_escapes_head_meta_values():
    """Head-meta values are HTML-escaped (XSS-safe), mirroring the Flask shell."""
    out = page_shell.render_page(
        {"title": "<script>alert(1)</script>", "site_name": 'A & "B"'},
        body_html="<main></main>",
        css="/* none */",
    )
    assert "<script>alert(1)</script>" not in out
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in out
    assert "A &amp; &quot;B&quot;" in out


def test_render_page_font_links_emitted_verbatim_not_escaped():
    """`font_links` is pre-built <link> markup — emitted as-is, not escaped (parity)."""
    links = '<link rel="stylesheet" href="https://fonts.example/css?family=Inter" />'
    out = page_shell.render_page(
        {"title": "x", "font_links": links}, body_html="", css=""
    )
    assert links in out  # verbatim, not escaped into &lt;link ...


def test_render_page_defaults_lang_and_locale_when_absent():
    """Missing `lang`/`og_locale` fall back to the nl / nl_NL defaults (Flask shell parity)."""
    out = page_shell.render_page({}, body_html="", css="")
    assert '<html lang="nl">' in out
    assert '<meta property="og:locale" content="nl_NL" />' in out


def test_render_page_missing_meta_keys_render_empty_not_none():
    """A missing head-meta key renders as an empty attribute value, never the string 'None'."""
    out = page_shell.render_page({}, body_html="<p>hi</p>", css="")
    assert "None" not in out
    assert '<meta name="description" content="" />' in out
    assert "<title></title>" in out
