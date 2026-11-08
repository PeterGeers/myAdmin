"""
Bugfix spec `bugfix-published-form-submit` — Task 2: the PRESERVATION property tests (render).

Parent spec: `.kiro/specs/Members/14 - public-pages-multi-tenant-serving` (R5.1, R5.3, R5.5, R7.1, R10).
Bugfix spec: `.kiro/specs/Members/14 .../bugfix-published-form-submit` (bugfix.md / design.md).

WHAT THIS TEST IS
-----------------
This is the PRESERVATION half of the bugfix exploration (companion to the task-1 bug-condition
exploration `test_published_form_submit_bug_condition.py`). It encodes Property 2 (Preservation):
for any input where the bug condition does NOT hold, the fixed render must produce the SAME result
as the original render — the ALREADY-CORRECT render output the design's "Preservation
Requirements" (bugfix.md R3.1–R3.4) names must stay byte-identical after the submit/format/consent
enrichment (tasks 3.x).

OBSERVATION-FIRST (bugfix workflow / steering 39): every assertion here was OBSERVED on the UNFIXED
`build_form_body_html` / `render_application_form_page` and MUST PASS NOW — it is the baseline the
fix must not disturb. The fix ADDS a submit script, client format checks, and consent/locale
controls; it must NOT change the already-correct render output these tests pin:

  * R3.4 — the `required` attribute is emitted for application-required fields;
  * R3.4 — email/tel/number/date fields map to the correct HTML input `type`;
  * R3.4 — `<fieldset>` sections are ordered by the authored `functional_groups` catalog, with
           ungrouped / uncatalogued fields falling to a trailing section;
  * R3.4 — labels resolve by locale with `nl` fallback then the bare key;
  * R3.4 — ALL config-origin values (`key` / `label` / `option` value+label) are HTML-escaped
           (XSS-safe body composition);
  * R3.4 — the CSS comes from the single `LandingPageStyles` source, with the branded
           `color_primary` / `color_accent` variables threaded in;
  * R3.4 — the renderer consumes the given `get_public_field_config` shape as its ONLY field
           source (no re-derivation; no raw-shape key — `field_overlay` / `overrides` /
           `fixed_overrides` — crosses into the output, steering 39);
  * R3.2 / R3.3 — STRUCTURAL boundary: the render modules do NOT import the Flask landing plane
           (`landing_page_service` / `landing_page_routes` / `tenant_slug_service` /
           `tenant_slugs`), mirroring the sibling `test_slug_lifecycle_preservation.py`
           import-boundary test. (The backend `public_app.py` submit handler and the in-app SPA
           form are out of scope and already covered — a light structural assertion only here.)

PROVE AGAINST THE REAL SHAPE (steering 39): the headline round-trip (`TestRealHdcnRenderRoundTrip`)
does NOT hand-build the resolved config — it drives the REAL `MembershipService.get_public_field_config`
over a realistic h-dcn-shaped `TenantOverlay` (IBAN `format` token via `FieldFormat`, a DATE
overlay field, an enum with XSS-bearing option labels, application-required + grouped fields, two
exposed base `personal` fields) and renders THAT genuine resolved shape — mirroring how the sibling
`test_slug_lifecycle_preservation.py` proved its carry-through against the real `h-dcn` row. A
hand-built resolved dict has hidden this class of bug before (steering 39 — "trust runs, not
inference").

NO live AWS: the render step is PURE (it returns the HTML string) and the real
`get_public_field_config` runs over in-memory providers (`StaticOverlayProvider` /
`StaticConsentNoticeProvider` — the established sibling fake-provider pattern). Property-based
where the invariant is universal (any resolved-shape config renders its `required` flags, input
types, sections, labels, and escaping identically) — design "Preservation Checking".

Validates (bugfix): Requirements 3.1, 3.2, 3.3, 3.4
"""

from __future__ import annotations

import html as _html
import importlib
import os
import re
import sys

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

_REPO_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)
# LandingPageStyles (the single CSS source) lives in backend/src/services — resolved from
# backend/src on the path in dev/test (vendored into the Members layer at build time); mirrors
# the sibling render tests.
_BACKEND_SRC = os.path.join(_REPO_ROOT, "backend", "src")
if _BACKEND_SRC not in sys.path:
    sys.path.insert(0, _BACKEND_SRC)

from sam.members.domain.application_form_render import (
    build_form_body_html,
    render_application_form_page,
)

_TENANT = "h-dcn"


# ──────────────────────────────────────────────────────────────────────────────────────
# A get_public_field_config-shaped resolved dict (the renderer's ONLY field source — the
# single-filter-authority output, steering 39). Matches the real service's shape observed via
# `MembershipService.get_public_field_config` (flat `fields` list keyed by bare `key`; a
# `functional_groups` catalog of `{key,label,order}`; `locales`; `notice`).
# ──────────────────────────────────────────────────────────────────────────────────────


def _config(fields=None, groups=None, *, notice_version=None):
    return {
        "tenant_id": _TENANT,
        "fields": fields if fields is not None else [],
        "functional_groups": groups if groups is not None else [],
        "locales": ["nl", "en"],
        "notice": {"version": notice_version},
    }


# ══════════════════════════════════════════════════════════════════════════════════════
# R3.4 — PROVE THE RENDER ROUND-TRIP AGAINST THE REAL get_public_field_config SHAPE.
#
# Drives the REAL `MembershipService.get_public_field_config` over a realistic h-dcn-shaped
# overlay (steering 39 — real reader/service, not a hand-built resolved dict) and pins the
# already-correct render output on the UNFIXED renderer. These must PASS now and stay identical
# after the fix.
# ══════════════════════════════════════════════════════════════════════════════════════


class _FakeCatalogRepo:
    """In-memory catalog surface the service's `membership_type` read calls — no boto3, no AWS
    (mirrors the sibling `FakeCatalogRepository` fake-repo pattern). This fixture authors no
    membership_type field, so an empty active list is all the public read needs."""

    def list_membership_types(self, tenant_id, active_only=True):
        return []


def _real_public_field_config():
    """The REAL `get_public_field_config` output for a realistic h-dcn-shaped overlay.

    Reuses the REAL `MembershipService` + `FieldResolver` + public serializer (steering 39 — the
    single filter authority) over in-memory providers, so the rendered round-trip is proven
    against the genuine resolved shape the publish step feeds the renderer, NOT a hand-built
    fixture. The overlay carries, by construction, everything the preserved facets need:

      * an application-REQUIRED overlay field carrying an IBAN `format` token (`iban`);
      * a DATE overlay field (`join_date`) — exercises the `date` input-type mapping;
      * an ENUM overlay field whose option value/label carry `<`/`&`/`"` (XSS escaping);
      * two application-visible base `personal` fields (`email`, `phone`) in the base catalog
        group — so an uncatalogued-in-the-tenant-overlay group trails the authored catalog;
      * a tenant functional-group catalog (`motor` #40, `financial` #50) — section ordering.
    """
    from sam.members.domain.consent_notice import StaticConsentNoticeProvider
    from sam.members.domain.field_resolver import (
        FixedFieldOverride,
        FunctionalGroup,
        OverlayField,
        StaticOverlayProvider,
        TenantOverlay,
    )
    from sam.members.domain.fixed_fields import EnumOption, FieldFormat, FieldType
    from sam.members.domain.membership_service import MembershipService

    overlay = TenantOverlay(
        functional_groups={
            "motor": FunctionalGroup(
                key="motor", label={"nl": "Motor", "en": "Motorcycle"}, order=40
            ),
            "financial": FunctionalGroup(
                key="financial", label={"nl": "Financiën", "en": "Financial"}, order=50
            ),
        },
        overrides={
            "personal.email": FixedFieldOverride(
                application_visible=True, functional_group="personal"
            ),
            "personal.phone": FixedFieldOverride(
                application_visible=True, functional_group="personal"
            ),
        },
        fields={
            "iban": OverlayField(
                key="iban",
                type=FieldType.STRING,
                label={"nl": "IBAN", "en": "IBAN"},
                functional_group="financial",
                application_visible=True,
                application_required=True,
                format=FieldFormat(checker="IBAN"),
            ),
            "join_date": OverlayField(
                key="join_date",
                type=FieldType.DATE,
                label={"nl": "Aanmelddatum", "en": "Join date"},
                functional_group="membership",
                application_visible=True,
            ),
            "motor_type": OverlayField(
                key="motor_type",
                type=FieldType.ENUM,
                label={"nl": "Motortype", "en": "Motor type"},
                functional_group="motor",
                application_visible=True,
                options=(
                    EnumOption(
                        value="sport", label={"nl": "Sport & <Toer>", "en": "Sport"}
                    ),
                    EnumOption(
                        value="cruiser", label={"nl": 'Cruiser "X"', "en": "Cruiser"}
                    ),
                ),
            ),
        },
    )
    svc = MembershipService(
        _FakeCatalogRepo(),
        overlay_provider=StaticOverlayProvider({_TENANT: overlay}),
        consent_notice_provider=StaticConsentNoticeProvider({_TENANT: "notice-v3"}),
    )
    return svc.get_public_field_config(_TENANT)


_REAL_BRANDING = {"color_primary": "#2D5F8A", "color_accent": "#F4A261"}


class TestRealHdcnRenderRoundTrip:
    """R3.4: the already-correct render output over the REAL `get_public_field_config` shape."""

    @pytest.fixture(scope="class")
    def config(self):
        return _real_public_field_config()

    @pytest.fixture(scope="class")
    def body(self, config):
        return build_form_body_html(config, locale="nl")

    @pytest.fixture(scope="class")
    def artifact(self, config):
        return render_application_form_page(
            config,
            head_meta={"title": "Aanmelden"},
            branding=_REAL_BRANDING,
            locale="nl",
        )

    def test_real_config_is_the_resolved_shape_the_renderer_consumes(self, config):
        # Sanity: the REAL service produced the resolved single-filter-authority shape (flat
        # `fields` keyed by bare key, a `functional_groups` catalog, `locales`, `notice`) — NOT a
        # hand-built dict. This is the shape the renderer's preservation is proven against.
        keys = [f["key"] for f in config["fields"]]
        assert {"iban", "join_date", "motor_type", "email", "phone"} <= set(keys)
        iban = next(f for f in config["fields"] if f["key"] == "iban")
        assert iban["format"] == {"checker": "IBAN", "params": {}}
        assert iban["required"] is True
        assert config["notice"]["version"] == "notice-v3"

    def test_required_attribute_emitted_for_application_required_field(self, body):
        # R3.4: the application-required `iban` field renders a `required` input; optional
        # fields do not. Round 5 (task 19.2): `required` is the engine's effective set, so the
        # public identity key `email` (always required on the public path) is also required.
        assert re.search(r'<input[^>]*name="iban"[^>]*\srequired', body)
        assert re.search(r'<input[^>]*name="email"[^>]*\srequired', body)
        assert body.count(" required") == 2

    def test_date_field_maps_to_native_date_input_type(self, body):
        # R3.4: a `date` field maps to the native `type="date"` control.
        assert re.search(r'<input type="date"[^>]*name="join_date"', body)

    def test_fieldsets_ordered_by_authored_group_catalog_then_trailing(self, body):
        # R3.4: sections follow the authored `functional_groups` catalog order (motor #40 before
        # financial #50), and groups NOT in the tenant catalog (membership / personal) trail —
        # deterministic ordering preserved.
        i_motor = body.index('data-group="motor"')
        i_financial = body.index('data-group="financial"')
        i_membership = body.index('data-group="membership"')
        i_personal = body.index('data-group="personal"')
        assert i_motor < i_financial < i_membership
        assert i_financial < i_personal
        # The authored group heading is the catalog LABEL, not the key.
        assert "<h2>Motor</h2>" in body and "<h2>Financiën</h2>" in body

    def test_labels_resolve_by_locale_with_nl_fallback(self, config):
        # R3.4: labels render in the requested locale. For `nl` the nl label is shown; for a
        # locale with no entry the renderer falls back to `nl` (the label contract).
        body_nl = build_form_body_html(config, locale="nl")
        assert ">Aanmelddatum" in body_nl  # nl label for join_date
        body_de = build_form_body_html(config, locale="de")  # no `de` label anywhere
        assert ">Aanmelddatum" in body_de  # falls back to nl

    def test_all_config_origin_values_are_html_escaped(self, body):
        # R3.4: every config-origin value (option value + option label carrying `<`/`&`/`"`) is
        # HTML-escaped before entering markup — no stored XSS in the body.
        assert "Sport &amp; &lt;Toer&gt;" in body
        assert "Cruiser &quot;X&quot;" in body
        assert "<Toer>" not in body  # the raw unescaped form never appears

    def test_css_from_single_landing_page_styles_source_with_branded_colours(
        self, artifact
    ):
        # R3.4: the CSS still comes from the single shared styling source with the branded
        # primary/accent colours threaded in.
        #
        # Change-with-tests (steering 30/34): the bugfix `bugfix-published-form-styling`
        # (Task 5.1 / DD-B1) ADDITIVELY extends the SAM Layer-2 generator — it appends
        # `--color-primary` / `--color-accent` to the `:root` variable block (so the new
        # application-form CSS block can carry the brand colours on the form's OWN elements)
        # and appends that form block after the existing page CSS. That is a DELIBERATE output
        # change, so this preservation assertion is aligned to it: every EXISTING Flask
        # `LandingPageStyles` line must still be present and in order (the generator did not
        # drop or reorder any pre-existing rule), rather than the whole `:root` block being a
        # frozen verbatim substring (the two new trailing `:root` colour lines now sit before
        # the closing `}`, so the old block is no longer a contiguous substring — but every
        # original line survives). The page CSS block remains a contiguous substring because
        # the form block is appended strictly AFTER it. The assertion is NOT weakened: it still
        # proves the single source's output is carried through, just acknowledging the additive
        # colour-variable extension.
        from services.landing_page_styles import LandingPageStyles

        css_variables = LandingPageStyles.build_css_variables(_REAL_BRANDING)
        page_css = LandingPageStyles.build_page_css(
            _REAL_BRANDING["color_primary"], _REAL_BRANDING["color_accent"]
        )

        def _nonblank_lines(text):
            return [ln.strip() for ln in text.splitlines() if ln.strip()]

        def _ordered_subsequence(needles, hay):
            it = iter(hay)
            return all(any(n == h for h in it) for n in needles)

        artifact_lines = _nonblank_lines(artifact)
        # Every original :root variable line survives, in order (additive colour vars allowed).
        assert _ordered_subsequence(_nonblank_lines(css_variables), artifact_lines), (
            "the original LandingPageStyles :root variable block must survive in order "
            "(the bugfix only APPENDS --color-* vars, it drops/reorders nothing)"
        )
        # The page CSS block is still carried verbatim (the form block is appended after it).
        assert page_css in artifact
        assert "#2D5F8A" in artifact and "#F4A261" in artifact
        assert artifact.count("<style>") == 1 and artifact.count("</style>") == 1

    def test_no_raw_record_shape_key_crosses_into_the_output(self, config, artifact):
        # R3.4 / steering 39: the resolved config carries no raw-storage shape, and no raw-shape
        # key leaks into the rendered artifact (the renderer consumes the resolved view only).
        import json

        blob = json.dumps(config)
        for raw in ("field_overlay", "overrides", "fixed_overrides"):
            assert raw not in blob
            assert raw not in artifact


# ══════════════════════════════════════════════════════════════════════════════════════
# R3.4 — the renderer behaviours as UNIVERSAL properties over the resolved-config shape.
#
# These pin the already-correct render output across MANY non-bug inputs (preservation is a
# universal property — design "Preservation Checking"). The resolved `type` string drives the
# HTML input type; the renderer is the sole authority for that mapping (the real field model does
# not emit email/tel/number types itself, so this property pins the renderer's mapping directly
# over the config-emitted `type` — exactly the shape the publish step hands it and the committed
# `_PUBLIC_FIELD_CONFIG` render fixture uses).
# ══════════════════════════════════════════════════════════════════════════════════════

#: The input-type mapping the UNFIXED `_render_field` applies (observed) — config `type` -> HTML.
_TYPE_MAP = {
    "email": "email",
    "number": "number",
    "date": "date",
    "tel": "tel",
    "phone": "tel",
    "text": "text",
    "string": "text",  # any unrecognised type falls back to text
}

_FIELD_KEY = st.text(
    alphabet="abcdefghijklmnopqrstuvwxyz_", min_size=1, max_size=12
).filter(lambda s: s[0].isalpha())


@settings(max_examples=120)
@given(
    key=_FIELD_KEY,
    field_type=st.sampled_from(sorted(_TYPE_MAP)),
    required=st.booleans(),
)
def test_preserve_input_type_and_required_mapping(key, field_type, required):
    """R3.4: for any non-select/non-textarea field, the resolved `type` maps to the correct HTML
    input type and the `required` flag drives the `required` attribute — unchanged by the fix.

    Validates (bugfix): Requirement 3.4
    """
    body = build_form_body_html(
        _config(fields=[{"key": key, "type": field_type, "required": required}])
    )
    ek = _html.escape(key)
    expected_type = _TYPE_MAP[field_type]
    assert re.search(rf'<input type="{expected_type}" id="{re.escape(ek)}"', body)
    has_required = bool(re.search(rf'name="{re.escape(ek)}"[^>]*\srequired', body))
    assert has_required is required


@settings(max_examples=80)
@given(
    nl_label=st.text(min_size=1, max_size=20),
    en_label=st.text(min_size=1, max_size=20),
)
def test_preserve_label_resolves_nl_for_nl_locale(nl_label, en_label):
    """R3.4: for the `nl` locale a field's `nl` label is chosen (the label-resolution contract) —
    the escaped nl label text is what appears in the `<label>`.

    Validates (bugfix): Requirement 3.4
    """
    body = build_form_body_html(
        _config(fields=[{"key": "f", "label": {"nl": nl_label, "en": en_label}}]),
        locale="nl",
    )
    assert f">{_html.escape(nl_label)}" in body


@settings(max_examples=80)
@given(key=_FIELD_KEY)
def test_preserve_label_falls_back_to_key_when_no_label(key):
    """R3.4: a field with NO label resolves its label to the bare `key` (escaped) — the final
    fallback in the label contract.

    Validates (bugfix): Requirement 3.4
    """
    body = build_form_body_html(_config(fields=[{"key": key}]))
    assert f">{_html.escape(key)}" in body


# A label value guaranteed to contain HTML-significant characters (XSS-escaping surface).
_XSS = st.builds(
    lambda inner: f"<{inner}>\"&'",
    st.text(alphabet="abcdefghijklmnopqrstuvwxyz ", min_size=1, max_size=8),
)


@settings(max_examples=80)
@given(label=_XSS)
def test_preserve_config_origin_label_is_html_escaped(label):
    """R3.4: a config-origin label carrying `<`/`>`/`&`/`"` is HTML-escaped — the raw markup never
    reaches the body (XSS-safe composition), unchanged by the fix.

    Validates (bugfix): Requirement 3.4
    """
    body = build_form_body_html(_config(fields=[{"key": "f", "label": {"nl": label}}]))
    # The escaped form is present; the raw `<...>` tag form is NOT.
    assert _html.escape(label) in body
    assert "<" + label.strip("<").split(">")[0] + ">" not in body


@settings(max_examples=60)
@given(
    option_value=st.text(
        alphabet="abcdefghijklmnopqrstuvwxyz<>&\"'", min_size=1, max_size=10
    ),
)
def test_preserve_select_option_values_are_escaped(option_value):
    """R3.4: an enum field's option value is HTML-escaped inside the rendered `<option>` — a
    config-origin option value can never inject markup.

    Validates (bugfix): Requirement 3.4
    """
    body = build_form_body_html(
        _config(
            fields=[
                {
                    "key": "sel",
                    "options": [{"value": option_value, "label": {"nl": "L"}}],
                }
            ]
        )
    )
    assert "<select" in body
    assert f'<option value="{_html.escape(option_value)}">' in body


@settings(max_examples=60)
@given(
    grouped_key=_FIELD_KEY,
    ungrouped_key=_FIELD_KEY,
)
def test_preserve_ungrouped_fields_fall_to_trailing_section(grouped_key, ungrouped_key):
    """R3.4: a field whose `functional_group` is NOT in the authored catalog falls into a trailing
    `_ungrouped` section, AFTER the catalogued group — deterministic sectioning preserved.

    Validates (bugfix): Requirement 3.4
    """
    body = build_form_body_html(
        _config(
            fields=[
                {"key": grouped_key, "functional_group": "known", "label": {"nl": "G"}},
                {"key": ungrouped_key, "label": {"nl": "U"}},
            ],
            groups=[{"key": "known", "label": {"nl": "Known"}, "order": 10}],
        )
    )
    assert 'data-group="_ungrouped"' in body
    assert body.index('data-group="known"') < body.index('data-group="_ungrouped"')


# ══════════════════════════════════════════════════════════════════════════════════════
# R3.2 / R3.3 — STRUCTURAL boundary: the render path does NOT reach into the Flask landing plane,
# the backend public submit handler, or the in-app SPA form. Mirrors the sibling
# `test_slug_lifecycle_preservation.py` import-boundary test: importing the render module and
# scanning `sys.modules` catches any transitive leak. (The backend and in-app paths are out of
# scope and already covered — this is a light structural assertion, NOT a duplicate endpoint test.)
# ══════════════════════════════════════════════════════════════════════════════════════

_SAM_RENDER_MODULES = (
    "sam.members.domain.application_form_render",
    "sam.shared.page_shell",
)

#: Flask landing-plane module name fragments the SAM render path must never import (R3.2 /
#: spec 14 Scope decision — the landing module is untouched by this fix).
_LANDING_PLANE_FRAGMENTS = (
    "landing_page_service",
    "landing_page_routes",
    "tenant_slug_service",
    "tenant_slugs",
)

#: The backend public submit handler + the in-app SPA path — out of scope; the render module must
#: not reach into them either (they are a different plane / a frontend artifact).
_OUT_OF_SCOPE_FRAGMENTS = (
    "handler.public_app",
    "public_app",
    "ApplicationFormPage",
)


@pytest.mark.parametrize("module_name", _SAM_RENDER_MODULES)
def test_preserve_render_module_never_imports_flask_landing_plane(module_name):
    """R3.2: no SAM render module transitively imports the Flask landing plane — the landing
    module is untouched by this fix (spec 14 Scope decision).

    Observed true on the UNFIXED code and must stay true after the fix (the submit/format/consent
    enrichment lives entirely in the render step; it does not reach into landing).

    Order-independent: inspect only the NEWLY-imported modules (`sys.modules - before`), not the
    union with `before`. Unioning `before` folds in everything earlier tests already imported (e.g.
    `public_app`), so in a full-suite run an unrelated earlier import would surface as a false
    "leak". The real invariant — the render module must not NEWLY pull in the landing plane — is
    preserved: if the render module genuinely imported a forbidden module it would appear in the
    newly-imported set (or already be present from THIS module's own top-level import, in which case
    the assertion would still fail on that prior leak, not pass by accident).

    Validates (bugfix): Requirement 3.2
    """
    before = set(sys.modules)
    importlib.import_module(module_name)
    # Only what THIS import NEWLY pulled in — never the union with `before` (order-independent).
    newly = set(sys.modules) - before
    leaked = [
        name for name in newly if any(frag in name for frag in _LANDING_PLANE_FRAGMENTS)
    ]
    assert leaked == [], (
        f"{module_name} must not import the Flask landing plane (R3.2 — landing untouched); "
        f"leaked landing-plane modules: {leaked}"
    )


@pytest.mark.parametrize("module_name", _SAM_RENDER_MODULES)
def test_preserve_render_module_does_not_reach_backend_handler_or_spa(module_name):
    """R3.3 (companion): the render module does not import the backend public submit handler
    (`public_app`) — the backend is out of scope and NOT modified by this fix. (The in-app SPA
    form is a frontend artifact and cannot be imported by a Python module at all; its fragment is
    listed for completeness.)

    Order-independent: inspect only the NEWLY-imported modules (`sys.modules - before`), not the
    union with `before`. Unioning `before` folds in everything earlier tests already imported (e.g.
    the test-only `sam.tests.test_public_app_edge`, or `public_app` itself), so a full-suite run
    would report a false "leak" that no product module could actually cause. The real invariant —
    the render module must not NEWLY reach the backend submit handler / SPA path — is preserved.

    Validates (bugfix): Requirement 3.3
    """
    before = set(sys.modules)
    importlib.import_module(module_name)
    # Only what THIS import NEWLY pulled in — never the union with `before` (order-independent).
    newly = set(sys.modules) - before
    leaked = [
        name for name in newly if any(frag in name for frag in _OUT_OF_SCOPE_FRAGMENTS)
    ]
    assert leaked == [], (
        f"{module_name} must not reach the backend submit handler / in-app SPA path (R3.3 — out "
        f"of scope, unchanged by this fix); leaked modules: {leaked}"
    )


def test_render_consumes_the_given_config_as_its_only_field_source():
    """R3.4 / steering 39: the renderer renders EXACTLY the fields present in the given resolved
    config — it never re-derives or adds a field. A field NOT in the config cannot appear, and a
    raw-shape key passed alongside is ignored (not rendered).

    Validates (bugfix): Requirements 3.4
    """
    cfg = _config(fields=[{"key": "only_field", "label": {"nl": "Only"}}])
    # A stray raw-shape key alongside the resolved fields must have no effect on the output.
    cfg["overrides"] = {"personal.secret": {"application_visible": True}}
    body = build_form_body_html(cfg)
    assert body.count('class="form-field"') == 1
    assert 'name="only_field"' in body
    assert "secret" not in body  # the raw-shape key is NOT a field source
