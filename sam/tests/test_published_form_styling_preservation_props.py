"""
Bugfix spec `bugfix-published-form-styling` — Task 3: the PRESERVATION property tests.

Property 2 (Preservation). Observation-first: every assertion below was OBSERVED on the CURRENT
(pre-fix) code and MUST PASS NOW, so the look-and-feel styling fix (Phases 1–5: an application-form
CSS block + `:root` colour vars, a logo/heading renderer, the three new `logo`/`header_title`/
`columns` attributes, and the no-reload editor) cannot regress the behaviours it is NOT meant to
touch. These are the baseline-to-preserve tests — they are expected to PASS on unfixed code.

The fix is ADDITIVE to the Layer-2 generator (new rules / new `:root` colour variables / new
supported attributes) and to the renderer (a logo + heading emitted only when supplied). These
tests pin everything AROUND that change:

  * LANDING_CLASSES_BYTE_IDENTICAL (3.7) — the key regression guard for Option 1: every existing
    SAM landing-page CSS rule (`.hero`/`.cta`/`.btn`/`.pricing-card`/the gallery+faq grids/…) is
    emitted UNCHANGED and in order, so a future SAM landing page is unaffected by the
    application-form styling added here. Asserted VERBATIM against a snapshot captured from the
    current generator (`fixtures/landing_classes_styling_bugfix_snapshot.json`).
  * SUBMIT_CONTRACT_UNCHANGED (3.1 / 3.2) — the applicant submit markup (the `.application-form`
    POST form, the slug/api-base `data-*` attributes, the locale selector, the consent control
    bound to `notice.version`, the per-field `data-format` tokens, the submit button and status
    region) and the embedded submit `<script>` (the `/public/members/{slug}/applications` endpoint
    template, the preventDefault submit, the EMAIL/IBAN checks) are emitted UNCHANGED for the same
    public field config, across many generated configs.
  * DEFAULTS_PUBLISH_WITHOUT_FAILING (3.3) — a tenant with NO (or partial) resolved settings
    publishes/renders without failing, using the SAM-owned Layer-2 defaults.
  * SEVEN_ATTRIBUTE_LAYER2_UNCHANGED (3.4) — the existing seven supported attributes remain
    supported, default identically, and their Layer-2 output (the existing `:root` variable lines,
    the existing page-CSS rules, and the font `<link>` tags) is preserved; a key OUTSIDE the
    supported set is still rejected. (The fix extends the set to ten — a deliberate, documented
    extension — so the guard is "existing seven preserved / additions allowed", not a frozen
    whole-string.)

Validates (bugfix): Requirements 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7

Property-based (Hypothesis ≥100 iterations) over generated settings/configs, plus fixed golden
snapshots observed on the current generator. No boto3 / no AWS — pure render-path functions and
in-memory publish seams.
"""

from __future__ import annotations

import json
import os
import sys

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for _p in (_REPO_ROOT, os.path.join(_REPO_ROOT, "backend", "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from sam.members.domain.application_form_render import (  # noqa: E402
    build_form_body_html,
    render_application_form_page,
)
from sam.members.domain.application_publish import ApplicationPublishService  # noqa: E402
from sam.members.domain.application_readiness import (  # noqa: E402
    StaticMailReadinessProvider,
)
from sam.shared.page_styles import (  # noqa: E402
    SUPPORTED_ATTRIBUTES,
    PageStyles,
    UnsupportedAttributeError,
    _build_page_css,
    render_page_styles,
)

_FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")
_LANDING_SNAPSHOT = os.path.join(
    _FIXTURES, "landing_classes_styling_bugfix_snapshot.json"
)
_LAYER2_GOLDEN = os.path.join(_FIXTURES, "layer2_seven_attribute_golden.json")

# The exactly-seven supported attributes as they exist TODAY (the baseline the fix extends to ten).
# Pinned here so the preservation guard is explicit about the set it preserves.
_SEVEN = frozenset(
    {
        "color_primary",
        "color_accent",
        "font_heading",
        "font_body",
        "base_spacing",
        "border_radius_global",
        "shadow_style",
    }
)


def _load(path: str) -> dict:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _rule_lines(css: str) -> list[str]:
    return [ln.strip() for ln in css.splitlines() if ln.strip()]


def _is_ordered_subsequence(needles: list[str], hay: list[str]) -> bool:
    """True iff every needle appears in hay, in order (additions between them are allowed)."""
    it = iter(hay)
    return all(any(n == h for h in it) for n in needles)


# ══════════════════════════════════════════════════════════════════════════════════════
# LANDING_CLASSES_BYTE_IDENTICAL — Requirement 3.7 (the key Option-1 regression guard)
# ══════════════════════════════════════════════════════════════════════════════════════


def test_landing_class_rules_emitted_byte_identical():
    """Every existing landing-class rule is emitted VERBATIM in the generated page CSS.

    The snapshot was captured from the CURRENT generator for the fixed brand colours it records.
    Each landing rule (`.hero`/`.cta`/`.btn`/`.pricing-card`/the gallery+faq grids/…) must appear
    byte-identical — character-for-character — in `_build_page_css`. The fix adds an application-form
    block and `:root` colour variables; it must not alter, reorder, or drop any landing rule (3.7).

    Validates (bugfix): Requirement 3.7
    """
    snap = _load(_LANDING_SNAPSHOT)
    page_css = _build_page_css(snap["color_primary"], snap["color_accent"])

    for rule in snap["landing_rules"]:
        assert rule in page_css, (
            "LANDING_CLASSES_BYTE_IDENTICAL (3.7): the existing landing-class rule was NOT emitted "
            f"byte-identical after the fix — a future SAM landing page would be perturbed: {rule!r}"
        )

    # And they stay in the SAME ORDER (no reshuffling of the landing block).
    assert _is_ordered_subsequence(snap["landing_rules"], _rule_lines(page_css)), (
        "LANDING_CLASSES_BYTE_IDENTICAL (3.7): the landing-class rules must stay in their original "
        "order in the generated page CSS."
    )


# Value pools per attribute (known vocabularies + arbitrary-but-safe tokens) so the property
# exercises the recognised-value, default-fallback, and sanitiser branches of the generator.
_COLORS = st.sampled_from(["#2D5F8A", "#F4A261", "#C01030", "#0A7E3F", "#fff", "#000000"])
_FONTS = st.sampled_from(["system", "Inter", "Lora", "Roboto", "Open Sans"])
_SPACINGS = st.sampled_from(["compact", "normal", "relaxed"])
_RADII = st.sampled_from(["sharp", "rounded", "pill"])
_SHADOWS = st.sampled_from(["none", "subtle", "medium", "dramatic"])


def _seven_settings_strategy():
    """Any subset of the seven supported attributes with valid values (empty mapping reachable)."""
    return st.fixed_dictionaries(
        {},
        optional={
            "color_primary": _COLORS,
            "color_accent": _COLORS,
            "font_heading": _FONTS,
            "font_body": _FONTS,
            "base_spacing": _SPACINGS,
            "border_radius_global": _RADII,
            "shadow_style": _SHADOWS,
        },
    )


@settings(max_examples=150)
@given(values=_seven_settings_strategy())
def test_landing_rules_present_for_any_seven_attribute_settings(values):
    """For ANY settings over the seven attributes, every landing selector is still emitted.

    A weaker-but-broad guard complementing the verbatim snapshot: no matter which of the seven
    attributes a tenant authors, the full landing-class vocabulary is always present in the page CSS
    (the fix never drops a landing selector). The colour-inlined rules are covered byte-for-byte by
    the snapshot test above at fixed colours; here we pin the selector set is complete for all
    settings.

    Validates (bugfix): Requirement 3.7
    """
    page_css = render_page_styles(values).page_css
    for selector in (
        ".hero",
        ".hero-text",
        ".about",
        ".gallery-grid-3",
        ".gallery-grid-4",
        ".gallery-masonry",
        ".carousel",
        ".cta",
        ".faq",
        ".faq-grid",
        ".testimonials",
        ".testimonial-cards",
        ".contact",
        ".pricing-grid",
        ".pricing-card",
        "footer",
    ):
        assert selector in page_css, (
            f"LANDING_CLASSES (3.7): landing selector {selector!r} must stay present for any "
            f"seven-attribute settings. values={values!r}"
        )


# ══════════════════════════════════════════════════════════════════════════════════════
# SUBMIT_CONTRACT_UNCHANGED — Requirements 3.1 / 3.2 (applicant markup + submit script)
# ══════════════════════════════════════════════════════════════════════════════════════

_SLUG = "hdcn-application-form"
_API_BASE = "https://api.jabaki.nl"


def _public_field_config(fields, groups, *, locales, notice_version):
    return {
        "tenant_id": "h-dcn",
        "fields": fields,
        "functional_groups": groups,
        "locales": locales,
        "notice": {"version": notice_version, "text": {"nl": "Ik ga akkoord"}}
        if notice_version
        else {"version": None},
    }


_FIELD_KEY = st.text(
    alphabet="abcdefghijklmnopqrstuvwxyz_", min_size=2, max_size=14
).filter(lambda s: s[0] != "_")
_FIELD_TYPE = st.sampled_from(["text", "email", "number", "date", "textarea"])
_CHECKER = st.sampled_from([None, "EMAIL", "IBAN"])


@st.composite
def _config_strategy(draw):
    n = draw(st.integers(min_value=0, max_value=4))
    keys = draw(
        st.lists(_FIELD_KEY, min_size=n, max_size=n, unique=True)
    )
    fields = []
    for key in keys:
        field = {
            "key": key,
            "type": draw(_FIELD_TYPE),
            "required": draw(st.booleans()),
            "functional_group": "personal",
            "label": {"nl": key.capitalize()},
        }
        checker = draw(_CHECKER)
        if checker:
            field["format"] = {"checker": checker}
        fields.append(field)
    groups = (
        [{"key": "personal", "label": {"nl": "Persoonlijk"}}] if fields else []
    )
    locales = draw(
        st.lists(st.sampled_from(["nl", "en", "fr", "de"]), min_size=1, max_size=4, unique=True)
    )
    notice_version = draw(st.sampled_from([None, "v1", "2024-05"]))
    return _public_field_config(
        fields, groups, locales=locales, notice_version=notice_version
    )


@settings(max_examples=150, suppress_health_check=[HealthCheck.too_slow])
@given(config=_config_strategy())
def test_submit_contract_markup_and_script_unchanged(config):
    """The applicant submit markup + the embedded submit script are emitted unchanged.

    For any public field config, `build_form_body_html` emits the SAME submit contract the fix must
    not touch: the `.application-form` POST form carrying the slug / api-base as HTML-escaped
    `data-*` attributes, the submit button, the aria-live status region, the embedded submit script,
    and the `/public/members/{slug}/applications` endpoint template with the client-side EMAIL/IBAN
    checks. The locale selector always renders (first locale selected); the consent control renders
    IFF the config carries a notice version. Per-field `data-format` tokens survive for formatted
    fields. None of this changes when the fix adds logo/heading/colours/grid to the page.

    Validates (bugfix): Requirements 3.1, 3.2
    """
    body = build_form_body_html(config, slug=_SLUG, public_api_base=_API_BASE)

    # The embedded submit <script> references control selectors (e.g. `[name="consent"]`) and
    # documents the consent-wrapper markup in comments, so those strings appear in `body` even when
    # no consent control renders. Assertions about rendered MARKUP therefore run against the body
    # with the script stripped; assertions about the SCRIPT run against the full body.
    assert "<script>" in body and "</script>" in body
    _script_start = body.index("<script>")
    _script_end = body.index("</script>") + len("</script>")
    markup = body[:_script_start] + body[_script_end:]

    # The POST submit form + its publish-time plumbing (3.1) — byte-exact markers.
    assert '<form class="application-form" method="post" novalidate ' in body
    assert f'data-slug="{_SLUG}"' in body
    assert f'data-api-base="{_API_BASE}"' in body
    assert '<button type="submit">Verstuur</button>' in body
    assert '<div class="form-status" role="status" aria-live="polite"></div>' in body

    # The embedded submit script + the exact endpoint contract (3.1).
    assert "/public/members/{slug}/applications" in body
    assert "event.preventDefault();" in body
    assert "EMAIL_RE" in body and "ibanMod97" in body

    # The locale selector is always present in the MARKUP, first locale selected (3.2).
    assert '<select id="locale" name="locale">' in markup
    first_locale = config["locales"][0]
    assert f'<option value="{first_locale}" selected>{first_locale}</option>' in markup

    # Consent control present IFF a notice version exists (3.2) — degrade-to-nothing otherwise.
    # (Checked against `markup` — the script references `[name="consent"]`/the wrapper in comments.)
    version = config["notice"].get("version")
    if version:
        assert f'data-notice-version="{version}"' in markup
        assert '<div class="form-meta-field" data-field="consent">' in markup
        assert '<input type="checkbox" id="consent" name="consent"' in markup
    else:
        assert "data-notice-version=" not in markup
        assert '<div class="form-meta-field" data-field="consent">' not in markup
        assert '<input type="checkbox" id="consent" name="consent"' not in markup

    # Each applicant-visible field renders its control in the MARKUP; a formatted field exposes its
    # checker token as an HTML-escaped `data-format` attribute (3.2) — never interpolated into JS.
    for field in config["fields"]:
        assert f'data-field="{field["key"]}"' in markup
        checker = (field.get("format") or {}).get("checker")
        if checker:
            assert f'data-format="{checker}"' in markup


@settings(max_examples=120, suppress_health_check=[HealthCheck.too_slow])
@given(config=_config_strategy())
def test_submit_contract_field_count_matches_config(config):
    """Exactly the config's applicant-visible fields render — no leakage, no drops (3.2).

    The published body renders ONE `form-field` wrapper per config field (the single filter
    authority's output), plus the submit-contract meta controls (locale, and consent when a notice
    exists) in a distinct `_meta` section. The fix must not add or drop an applicant field.

    Validates (bugfix): Requirement 3.2
    """
    body = build_form_body_html(config, slug=_SLUG, public_api_base=_API_BASE)
    assert body.count('class="form-field"') == len(config["fields"])
    # The submit button appears exactly once (no duplicate submit wiring introduced).
    assert body.count('<button type="submit">Verstuur</button>') == 1


# ══════════════════════════════════════════════════════════════════════════════════════
# DEFAULTS_PUBLISH_WITHOUT_FAILING — Requirement 3.3
# ══════════════════════════════════════════════════════════════════════════════════════

_TENANT = "h-dcn"


class _FakeSlugReader:
    def get_form_slug(self, tenant_id):
        return _SLUG


class _FakeFieldConfigReader:
    def __init__(self, config):
        self._config = config

    def get_public_field_config(self, tenant_id):
        return dict(self._config, tenant_id=tenant_id)


class _FakeLookAndFeelReader:
    def __init__(self, values):
        self._values = dict(values)

    def get_look_and_feel(self, tenant_id):
        return self._values


class _CapturingArtifactWriter:
    def __init__(self):
        self.index_html = None
        self.form_json = None

    def publish_artifacts(self, slug, *, index_html, form_json):
        self.index_html = index_html
        self.form_json = form_json


@pytest.fixture(autouse=True)
def _set_public_api_base_env(monkeypatch):
    """The publish render step resolves PUBLIC_API_BASE_URL fail-fast (no default)."""
    monkeypatch.setenv("PUBLIC_API_BASE_URL", _API_BASE)


@settings(
    max_examples=100,
    suppress_health_check=[HealthCheck.function_scoped_fixture, HealthCheck.too_slow],
)
@given(
    # A tenant on NO settings ({}) or an arbitrary SUBSET of the seven — both must publish fine.
    values=_seven_settings_strategy()
)
def test_defaults_or_partial_settings_publish_without_failing(values):
    """A tenant with no / partial resolved settings publishes successfully using Layer-2 defaults.

    Injecting a (capturing) artifact writer makes `publish()` a real, successful publish; the empty
    and partial mappings resolve absent attributes to the SAM-owned defaults inside the generator,
    so no publish fails for lack of settings (3.3). The baked artifact is produced.

    Validates (bugfix): Requirement 3.3
    """
    writer = _CapturingArtifactWriter()
    svc = ApplicationPublishService(
        slug_reader=_FakeSlugReader(),
        readiness_provider=StaticMailReadinessProvider({_TENANT: (True, "h-dcn.nl")}),
        field_config_reader=_FakeFieldConfigReader(
            {
                "fields": [{"key": "f0"}],
                "functional_groups": [],
                "locales": ["nl", "en"],
                "notice": {"version": None},
            }
        ),
        look_and_feel_reader=_FakeLookAndFeelReader(values),
        artifact_writer=writer,
    )

    result = svc.publish(_TENANT)
    assert result["success"] is True, (
        f"DEFAULTS_PUBLISH_WITHOUT_FAILING (3.3): publish must succeed for resolved values "
        f"{values!r} (defaults fill the rest)."
    )
    assert writer.index_html is not None


def test_render_with_no_branding_uses_defaults_without_failing():
    """`render_application_form_page` with no branding renders using Layer-2 defaults (3.3)."""
    html = render_application_form_page(
        {"fields": [], "functional_groups": [], "locales": ["nl"], "notice": {"version": None}},
        head_meta={"title": "Aanmelden"},
        branding=None,
        slug=_SLUG,
        public_api_base=_API_BASE,
    )
    # The default Layer-2 output is baked (same as render_page_styles({})).
    default_styles = render_page_styles({})
    assert default_styles.css_variables in html
    assert default_styles.page_css in html


# ══════════════════════════════════════════════════════════════════════════════════════
# SEVEN_ATTRIBUTE_LAYER2_UNCHANGED — Requirement 3.4
# ══════════════════════════════════════════════════════════════════════════════════════


# The two new values-only attributes the bugfix adds (the documented extension of the seven).
# (The earlier ``columns`` attribute was later removed — the form grid is now fully width-driven.)
_NEW_TWO = frozenset({"logo", "header_title"})
# The full post-fix supported set — the seven original attributes plus the two new ones.
_NINE = _SEVEN | _NEW_TWO


def test_seven_attributes_still_supported_today():
    """The seven original attributes stay supported, and the set is now EXACTLY the nine.

    The seven original attributes MUST remain supported (the preservation intent — this is the
    subsequence/subset guard that must never weaken). The bugfix extends the set via a
    deliberate, documented extension (bugfix 3.4): `logo` / `header_title` (the earlier `columns`
    attribute was later removed — the form grid is now fully width-driven). This baseline
    assertion — the ONE place the deliberate extension changes the exact-equality baseline — is
    aligned to the new nine-set (change-with-tests for a deliberate behavior change); the
    preservation intent (the seven remain a subset) is kept, not weakened.

    Validates (bugfix): Requirement 3.4
    """
    assert _SEVEN <= set(SUPPORTED_ATTRIBUTES), (
        "SEVEN_ATTRIBUTE_LAYER2_UNCHANGED (3.4): the seven existing attributes must stay supported."
    )
    # Post-fix the set is EXACTLY the nine — the original seven plus the documented extension.
    assert set(SUPPORTED_ATTRIBUTES) == _NINE, (
        "SUPPORTED_ATTRIBUTES must be exactly the nine: the original seven plus the deliberate, "
        "documented bugfix extension (logo / header_title). Anything else is drift."
    )


def test_seven_attribute_layer2_output_preserved_against_golden():
    """The seven-attribute Layer-2 output (vars/page-css/font-links) is preserved vs the golden.

    The golden was captured from the CURRENT generator for a full seven-attribute mapping and the
    empty (defaults) mapping. The fix is ADDITIVE (new `:root` colour vars, a new application-form
    block, new attributes), so every existing variable line and page-CSS rule must survive in order
    (ordered-subsequence), and the font `<link>` tags — untouched by this fix — stay byte-identical.

    Validates (bugfix): Requirement 3.4
    """
    golden = _load(_LAYER2_GOLDEN)
    for name, case in golden.items():
        produced = render_page_styles(case["settings"])
        assert _is_ordered_subsequence(
            _rule_lines(case["css_variables"]), _rule_lines(produced.css_variables)
        ), f"SEVEN_ATTRIBUTE (3.4): existing :root variable lines dropped/changed for {name!r}."
        assert _is_ordered_subsequence(
            _rule_lines(case["page_css"]), _rule_lines(produced.page_css)
        ), f"SEVEN_ATTRIBUTE (3.4): existing page-CSS rules dropped/changed for {name!r}."
        assert produced.font_links == case["font_links"], (
            f"SEVEN_ATTRIBUTE (3.4): font <link> tags must stay byte-identical for {name!r} "
            "(the fix does not touch font-link emission)."
        )


@settings(max_examples=120)
@given(values=_seven_settings_strategy())
def test_seven_attribute_render_is_pagestyles_and_deterministic(values):
    """For any seven-attribute settings, the generator returns a deterministic `PageStyles` (3.4).

    Determinism + the `PageStyles` contract for the existing attributes is preserved: identical
    values produce identical output and the render never fails for a valid seven-attribute mapping.

    Validates (bugfix): Requirement 3.4
    """
    first = render_page_styles(values)
    assert isinstance(first, PageStyles)
    assert first == render_page_styles(dict(values))


def test_key_outside_supported_set_still_rejected():
    """A key outside the supported set is still rejected (3.4) — reject-on-unsupported preserved.

    `totally_unknown_attr` is outside BOTH the seven and the fix's ten, so it must raise regardless
    of the extension — the reject-on-unsupported contract the fix must preserve.

    Validates (bugfix): Requirement 3.4
    """
    with pytest.raises(UnsupportedAttributeError):
        render_page_styles({"totally_unknown_attr": "x"})
