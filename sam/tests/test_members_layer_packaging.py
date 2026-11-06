"""
Spec 15 (SAM Page Look-and-Feel) task 2 — Layer-2 packaging assertion (DD-1).

Task 1.1 relocated the CSS-generation logic to the SAM-owned home
``sam/shared/page_styles/`` (the ONE Layer-2 ``render_page_styles`` generator). Task 2
removes the old Flask-plane vendoring from the Members Lambda layer build: the former
``cp .../landing_page_styles.py`` line in ``sam/members/layer/Makefile`` is gone, and the
SAM-owned ``sam/shared/page_styles/`` ships the same least-surface way the layer already
packages the rest of ``sam/shared/`` — i.e. for free via the wholesale ``sam/shared/``
rsync, with NO per-module ``cp`` of its own.

These are BUILD assertions against the Makefile recipe (steering 39 change-with-tests):
they pin the packaging CONTRACT without running the slow pip-install build, so a future
edit that re-adds the Flask ``cp`` — or that stops shipping the SAM-owned generator — fails
here instead of silently regressing Req 3.1 (no Flask-plane module as source of truth, not
even as a build-time vendored copy).

Validates: Requirements 3.1
"""

from __future__ import annotations

import os

_REPO_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
_MAKEFILE = os.path.join(_REPO_ROOT, "sam", "members", "layer", "Makefile")
_PAGE_STYLES_DIR = os.path.join(_REPO_ROOT, "sam", "shared", "page_styles")


def _makefile_text() -> str:
    with open(_MAKEFILE, encoding="utf-8") as fh:
        return fh.read()


def _recipe_lines() -> list[str]:
    """The Makefile's executed recipe lines (tab-indented), comments/blank lines dropped.

    A recipe line in a Makefile is prefixed with a hard TAB. Comment lines (``#`` after
    optional leading whitespace) are NOT executed, so they are excluded — a ``cp`` named
    only in a comment must not count as "the build copies it".
    """
    lines: list[str] = []
    for raw in _makefile_text().splitlines():
        if not raw.startswith("\t"):
            continue
        stripped = raw.lstrip("\t")
        if stripped.lstrip().startswith("#"):
            continue
        lines.append(stripped)
    return lines


# ── the layer no longer vendors the Flask-plane module (Req 3.1) ──────────────────────


def test_layer_build_does_not_vendor_the_flask_landing_page_styles_module():
    """No executed recipe line copies the Flask ``landing_page_styles.py`` into the layer.

    Req 3.1 forbids the Flask-plane module as the source of truth, including as a
    build-time vendored copy. The former ``cp "$(SERVICES)/landing_page_styles.py" ...``
    recipe line MUST be gone (a mention in an explanatory comment is fine — it documents
    the removal — so we scan only executed recipe lines, not comments).
    """
    offending = [
        line for line in _recipe_lines() if "landing_page_styles" in line
    ]
    assert offending == [], (
        "The Members layer build must not vendor the Flask-plane "
        "landing_page_styles.py (Req 3.1); found executed recipe line(s): "
        f"{offending!r}"
    )


def test_services_shim_docstring_no_longer_lists_landing_page_styles():
    """The generated ``services/__init__.py`` shim must not advertise the removed module.

    The shim's docstring enumerates exactly which ``services.*`` files ship in the layer.
    After task 2 it lists only ``dynamodb_client`` / ``projection_schema`` — not the
    removed ``landing_page_styles``.
    """
    printf_lines = [
        line for line in _recipe_lines() if "services/__init__.py" in line
    ]
    assert printf_lines, "expected a recipe line generating services/__init__.py"
    assert not any("landing_page_styles" in line for line in printf_lines), (
        "the services shim docstring must not list the removed landing_page_styles module"
    )


# ── the SAM-owned page_styles ships via the existing sam/shared/ rsync ────────────────


def test_sam_owned_page_styles_is_the_layer_css_source_on_disk():
    """``sam/shared/page_styles/`` exists as the SAM-owned Layer-2 CSS generator.

    This is the home task 1.1 created and the home task 2 relies on shipping. It must be a
    real package directory with an ``__init__.py`` exposing ``render_page_styles`` — the one
    reusable Layer-2 function that replaces the Flask ``LandingPageStyles`` CSS source.
    """
    init_py = os.path.join(_PAGE_STYLES_DIR, "__init__.py")
    assert os.path.isdir(_PAGE_STYLES_DIR), (
        "sam/shared/page_styles/ must exist as the SAM-owned Layer-2 CSS generator "
        "(spec 15 / DD-1, task 1.1)"
    )
    assert os.path.isfile(init_py), "sam/shared/page_styles/__init__.py must exist"
    with open(init_py, encoding="utf-8") as fh:
        text = fh.read()
    assert "def render_page_styles(" in text, (
        "sam/shared/page_styles must expose the reusable render_page_styles() generator"
    )


def test_layer_packages_sam_shared_wholesale_so_page_styles_ships_for_free():
    """The layer rsyncs ``sam/shared/`` wholesale, so ``page_styles/`` ships with NO extra cp.

    Task 2 requires packaging the SAM-owned generator "the same least-surface way the layer
    already packages ``sam/shared/``". That way is the single wholesale ``rsync`` of
    ``$(SAM_SRC)/shared/`` into ``python/sam/shared/`` — a subdirectory like ``page_styles``
    is carried by it automatically. We assert that rsync line is present and that its
    excludes do NOT drop ``page_styles`` (the only excludes are ``.aws-sam`` / ``__pycache__``
    / ``tests`` — none of which is ``page_styles``).
    """
    recipe = _recipe_lines()
    # The rsync recipe spans a line-continuation; join the whole recipe to inspect it.
    joined = "\n".join(recipe)
    assert "rsync" in joined and "$(SAM_SRC)/shared/" in joined, (
        "the layer must rsync sam/shared/ wholesale into python/sam/shared/"
    )
    # find the rsync invocation that targets python/sam/shared/
    assert "python/sam/shared/" in joined, (
        "the sam/shared/ rsync must target python/sam/shared/ in the layer"
    )
    # none of the rsync excludes may drop the page_styles package
    assert "--exclude 'page_styles'" not in joined, (
        "page_styles must not be excluded from the sam/shared/ rsync — it is the "
        "SAM-owned CSS source the layer must ship"
    )
    # sanity: the SAM-owned package is a plain subdir of sam/shared (so the wholesale
    # rsync carries it) and is not named one of the excluded dirs.
    assert os.path.basename(_PAGE_STYLES_DIR) not in {
        ".aws-sam",
        "__pycache__",
        "tests",
    }
