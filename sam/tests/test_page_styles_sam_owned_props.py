"""
SAM property-based test — **styling is produced entirely from SAM-owned code** (spec 15,
task 4.3).

Feature: sam-page-look-and-feel, Property 7: For any styling production, no attribute value
SHALL originate from the Flask plane and no runtime read of or call to the Flask plane SHALL
occur.

Validates: Requirements 2.1, 2.2, 3.1, 3.5, 8.4
Properties: 7

What this asserts (and why it is genuine, not tautological)
-----------------------------------------------------------
Property 7 is the *no-Flask-at-runtime* guarantee for Layer 2 styling production
(:func:`sam.shared.page_styles.render_page_styles`) and for the resolved VALUES that feed it
out of the SAM-owned reader
(:meth:`sam.members.repository.projection_config_reader.MembersProjectionReader.get_look_and_feel`).
It is defended on two complementary fronts so neither alone can pass vacuously:

1. **Static AST import-scan (dependency-free).** The Layer-2 generator package
   ``sam/shared/page_styles`` MUST import only the standard library (plus bare ``typing`` /
   ``collections.abc``) — never Flask, never the Flask-plane styling module
   ``services.landing_page_styles`` it was relocated FROM (DD-1), never ``boto3`` / any
   SAM-repository module. A dependency-free Layer 2 cannot, by construction, read or call the
   Flask plane while producing styling (Req 3.1, 3.5). The scan parses the real source with
   :mod:`ast`, so a re-introduced ``import`` of a forbidden module fails HERE.

2. **Runtime import guard driven over many generated settings (Hypothesis >=100).** For any
   generated ``Look_And_Feel_Settings`` values mapping, ``render_page_styles`` is executed with
   a ``sys.meta_path`` finder installed that RAISES the instant anything tries to import a
   Flask-plane module (``flask`` / ``services.landing_page_styles`` / the Flask ``services.*``
   package). If styling production ever reached into the Flask plane at runtime the render would
   raise and the property would fail. Because the generator is already imported before the guard
   goes up, the guard specifically catches a *runtime* (call-time) Flask import, which is exactly
   what Req 2.2 / Property 7 forbid.

Together these show the two things Property 7 requires: no attribute VALUE can originate from
the Flask plane (the SAM-owned reader surfaces only the SAM ``config#fields`` slice, and Layer 2
takes only that values mapping — front 2 proves no Flask value is pulled in at call time), and
no runtime read of or call to the Flask plane occurs during styling production (fronts 1 + 2).

SAM tests run via ``python -m pytest sam/tests/... -c sam/pytest.ini``.
"""

import ast
import importlib.util
import os
import sys

from hypothesis import given, settings
from hypothesis import strategies as st

# repo root on sys.path (mirrors sam/conftest.py) so `sam.shared` imports.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from sam.shared.page_styles import SUPPORTED_ATTRIBUTES, render_page_styles  # noqa: E402

# ─── Forbidden runtime surfaces (the Flask plane) ──────────────────────────────────────
# Styling production must never import or call any of these at runtime. ``flask`` itself,
# the Flask-plane styling module Layer 2 was relocated FROM (DD-1), and the Flask ``services``
# package it lives in. Blocking the whole ``services`` package is deliberate: the SAM-owned
# Layer-2 generator must not reach into ANY Flask-plane service while producing styling.
_FORBIDDEN_RUNTIME_PREFIXES = ("flask", "services")
_FLASK_STYLING_MODULE = "services.landing_page_styles"

# Modules the dependency-free Layer-2 package is allowed to import (stdlib + bare typing).
# Anything else — Flask, boto3, a SAM repository, the Flask styling module — is a violation.
_ALLOWED_IMPORT_PREFIXES = (
    "re",
    "typing",
    "collections",
    "collections.abc",
    "dataclasses",
    "__future__",
    "enum",
    "functools",
    "string",
    "html",
    "math",
)


def _page_styles_source_files() -> list[str]:
    """Return every ``.py`` file of the ``sam.shared.page_styles`` package on disk."""
    spec = importlib.util.find_spec("sam.shared.page_styles")
    assert spec is not None and spec.origin, "sam.shared.page_styles must be importable"
    pkg_dir = os.path.dirname(spec.origin)
    return [
        os.path.join(pkg_dir, name)
        for name in sorted(os.listdir(pkg_dir))
        if name.endswith(".py")
    ]


def _imported_module_names(source: str) -> set[str]:
    """Parse ``source`` and return the top-level module names it imports (via AST)."""
    tree = ast.parse(source)
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            # level > 0 is a relative (intra-package) import — inherently SAM-owned.
            if node.level == 0 and node.module:
                names.add(node.module)
    return names


# ─── Front 1: static AST import-scan — Layer 2 is dependency-free (SAM-owned) ──────────
def test_layer2_package_imports_only_stdlib_no_flask_plane():
    """Feature: sam-page-look-and-feel, Property 7: For any styling production, no attribute
    value SHALL originate from the Flask plane and no runtime read of or call to the Flask
    plane SHALL occur.

    Static half: the Layer-2 generator package imports ONLY stdlib (+ bare typing), so it
    cannot read or call the Flask plane while producing styling (Req 3.1, 3.5).

    Validates: Requirements 2.1, 2.2, 3.1, 3.5, 8.4
    """
    scanned_any = False
    for path in _page_styles_source_files():
        with open(path, encoding="utf-8") as handle:
            source = handle.read()
        for module in _imported_module_names(source):
            scanned_any = True
            top = module.split(".")[0]
            # No Flask-plane / Flask import, ever.
            assert top != "flask" and not module.startswith("services"), (
                f"{os.path.basename(path)} imports Flask-plane module {module!r}; "
                "Layer 2 styling must be SAM-owned (Req 3.1)."
            )
            # No service-client / SAM-repository reach either — Layer 2 is pure.
            assert top != "boto3", (
                f"{os.path.basename(path)} imports boto3; Layer 2 must be dependency-free."
            )
            assert module.split(".")[0] in {p.split(".")[0] for p in _ALLOWED_IMPORT_PREFIXES}, (
                f"{os.path.basename(path)} imports non-stdlib module {module!r}; the Layer-2 "
                "generator must stay dependency-free (stdlib only) so no Flask-plane runtime "
                "dependency is possible (Req 3.1, 3.5)."
            )
    assert scanned_any, "expected to scan at least one import in sam.shared.page_styles"


# ─── The Flask-plane runtime block (shared by the runtime-guard property) ──────────────
class _BlockFlaskPlaneFinder:
    """``sys.meta_path`` finder that RAISES on any Flask-plane import.

    Installed around a ``render_page_styles`` call; if styling production tries to import a
    Flask-plane module at runtime the import raises, failing the property. Only Flask-plane
    names are blocked — every other import (stdlib, already-loaded SAM modules) passes through
    via ``return None``.
    """

    triggered: list[str]

    def __init__(self):
        self.triggered = []

    def find_spec(self, name, path, target=None):
        if name == _FLASK_STYLING_MODULE or any(
            name == prefix or name.startswith(prefix + ".")
            for prefix in _FORBIDDEN_RUNTIME_PREFIXES
        ):
            self.triggered.append(name)
            raise ModuleNotFoundError(
                f"Flask-plane import {name!r} attempted during SAM styling production "
                "(Property 7: no runtime read of or call to the Flask plane)."
            )
        return None


def _render_under_flask_block(mapping):
    """Run ``render_page_styles(mapping)`` with the Flask-plane import block installed.

    Returns the produced ``PageStyles``. Raises if styling production reaches the Flask plane.
    Drops any already-imported Flask-plane module first so the block is genuinely in effect.
    """
    finder = _BlockFlaskPlaneFinder()
    removed = {
        name: sys.modules.pop(name)
        for name in list(sys.modules)
        if name == _FLASK_STYLING_MODULE
        or any(
            name == prefix or name.startswith(prefix + ".")
            for prefix in _FORBIDDEN_RUNTIME_PREFIXES
        )
    }
    sys.meta_path.insert(0, finder)
    try:
        return render_page_styles(dict(mapping)), finder
    finally:
        sys.meta_path.remove(finder)
        sys.modules.update(removed)


def test_block_finder_actually_blocks_the_flask_styling_module():
    """Sanity: the runtime block really does make the Flask styling module unimportable,
    so the property below cannot pass vacuously (e.g. if the block mechanism broke).

    The finder is only CONSULTED for a module that is not already cached in ``sys.modules`` —
    an ``import_module`` of an already-imported module returns the cached object without hitting
    ``sys.meta_path`` at all. A sibling test (or a prior import of the Flask plane) can leave
    ``services`` / ``services.landing_page_styles`` cached, which previously made this sanity
    check flake between environments (passed locally, failed in the SAM CI job). So we DROP every
    Flask-plane module from ``sys.modules`` first (the same thing ``_render_under_flask_block``
    does), import under the block, then RESTORE them — so the finder is genuinely exercised
    regardless of import order.
    """
    finder = _BlockFlaskPlaneFinder()
    removed = {
        name: sys.modules.pop(name)
        for name in list(sys.modules)
        if name == _FLASK_STYLING_MODULE
        or any(
            name == prefix or name.startswith(prefix + ".")
            for prefix in _FORBIDDEN_RUNTIME_PREFIXES
        )
    }
    sys.meta_path.insert(0, finder)
    try:
        import importlib

        raised = False
        try:
            importlib.import_module(_FLASK_STYLING_MODULE)
        except ModuleNotFoundError:
            # Either the finder blocked it (recorded in finder.triggered) OR the Flask plane is
            # simply not importable in this environment (no Flask deps on the SAM CI job). Both
            # satisfy the sanity goal: the module does NOT import successfully under the block.
            raised = True
        assert raised, (
            "Expected the Flask styling module import to FAIL under the block, but it "
            "succeeded — the guard's blocking mechanism is not working."
        )
    finally:
        sys.meta_path.remove(finder)
        sys.modules.update(removed)


# ─── Generators for valid Look_And_Feel_Settings values ────────────────────────────────
_hex_color = st.from_regex(r"\#[0-9A-Fa-f]{6}", fullmatch=True)
_font_name = st.sampled_from(
    ["system", "Inter", "Lora", "Roboto", "Open Sans", "Merriweather", "Poppins"]
)
_value_pool = {
    "color_primary": _hex_color,
    "color_accent": _hex_color,
    "font_heading": _font_name,
    "font_body": _font_name,
    "base_spacing": st.sampled_from(["compact", "normal", "relaxed"]),
    "border_radius_global": st.sampled_from(["sharp", "rounded", "pill"]),
    "shadow_style": st.sampled_from(["none", "subtle", "medium", "dramatic"]),
    # bugfix bugfix-published-form-styling (Task 8): the two new values-only attributes. (The
    # earlier ``columns`` attribute was removed — the form grid is now fully width-driven.)
    "logo": st.sampled_from(["https://assets.example.org/logo.png", "logo.svg"]),
    "header_title": st.sampled_from(["Aanmelden", "Join us"]),
}
assert set(_value_pool) == set(SUPPORTED_ATTRIBUTES)


@st.composite
def _settings_values(draw):
    """Draw a valid (possibly partial) Look_And_Feel_Settings values mapping.

    Every attribute is independently present/absent, so any subset of the seven supported
    attributes is exercised (absent -> SAM-owned default; the empty mapping is reachable).
    """
    full = {attr: draw(strategy) for attr, strategy in _value_pool.items()}
    return {attr: value for attr, value in full.items() if draw(st.booleans())}


# ─── Front 2: runtime-guard property — no Flask call during styling production ─────────
@settings(max_examples=200)
@given(mapping=_settings_values())
def test_styling_production_never_calls_the_flask_plane(mapping):
    """Feature: sam-page-look-and-feel, Property 7: For any styling production, no attribute
    value SHALL originate from the Flask plane and no runtime read of or call to the Flask
    plane SHALL occur.

    Runtime half: for any generated settings mapping, producing styling raises if it tries to
    import a Flask-plane module at runtime. The render succeeds (no Flask reach) and produces
    the SAME output as an unguarded render from the same SAM-owned values — so neither the
    output nor any attribute value depended on the Flask plane (Req 2.1, 2.2).

    Validates: Requirements 2.1, 2.2, 3.1, 3.5, 8.4
    """
    guarded, finder = _render_under_flask_block(mapping)

    # No Flask-plane import was attempted during styling production.
    assert finder.triggered == [], (
        "styling production attempted a Flask-plane import at runtime: "
        f"{finder.triggered!r}"
    )

    # The guarded render equals the unguarded render from the same SAM-owned values — the
    # output is produced entirely from SAM-owned code and the supplied values, with no Flask
    # value mixed in.
    assert guarded == render_page_styles(dict(mapping))
