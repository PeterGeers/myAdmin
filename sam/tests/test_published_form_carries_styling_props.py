"""
SAM property-based test — a successful publish carries styling DERIVED from the tenant's
resolved look-and-feel values (spec 15, task 7.5).

Feature: sam-page-look-and-feel, Property 11: For any tenant with resolved
Look_And_Feel_Settings values, a successful publish SHALL carry styling produced by Layer 2
from exactly those values (and from defaults where a tenant has none).

Validates: Requirements 5.1, 5.2, 5.4

What this asserts
-----------------
Task 7.2 wired ``ApplicationPublishService.publish`` to resolve the verified tenant's SAM-owned
``Look_And_Feel_Settings`` VALUES through the injected :class:`LookAndFeelSettingsReader`, run
them through Layer 2 (``render_page_styles``) via ``branding=`` on the renderer, and bake the
generated CSS into the published ``{slug}/index.html`` artifact. The shared, plane-neutral
``page_shell.render_page`` emits that CSS VERBATIM inside the single ``<style>`` block, so the
published artifact's styling is *exactly* what Layer 2 produces for the resolved values.

The property therefore checks, over arbitrary valid resolved values: a SUCCESSFUL publish (an
artifact IS written) carries the Layer-2 ``css_variables`` + ``page_css`` for EXACTLY those
resolved values — and, where a tenant resolves to no values (an empty slice), the Layer-2
DEFAULTS. This is the Req 5.1/5.2/5.4 contract: the published form reflects the resolved values
(and defaults where there are none).

In-memory fakes (no boto3, no AWS)
----------------------------------
Modelled entirely with in-memory seams, reusing the publish service's fake-seam shape:

- a reader that returns the generated resolved values (``FakeLookAndFeelReader``-style);
- an **artifact writer** that CAPTURES the published ``index_html`` — injecting a
  ``PublicPageArtifactWriter`` is what makes ``publish()`` a *successful* publish (without one
  the live write stays dormant and the seam raises ``PublishPipelineNotWired``), so capturing
  the artifact is the honest way to assert "the published form carries ...".

Genuine (non-tautological) strategy
-----------------------------------
The strategy generates only VALID settings mappings over the seven supported attributes
(unsupported-key rejection is Property 5, not this one). Each attribute is optional, so a
generated tenant ranges from ``{}`` (resolves to Layer-2 defaults — the "where a tenant has
none" clause) through partial to the full seven, and the enum-like attributes draw from BOTH
their known value set AND free text so the known-value, default-fallback, and sanitiser paths
are all exercised. The expected styling is computed from an INDEPENDENT ``render_page_styles``
call on the SAME resolved values, so a pass means the baked styling genuinely corresponds to the
resolved values — not that two identical constants were compared.
"""

import os
import sys

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

# repo root on sys.path (mirrors sam/conftest.py) so `sam.*` imports resolve.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)
_BACKEND_SRC = os.path.join(_REPO_ROOT, "backend", "src")
if _BACKEND_SRC not in sys.path:
    sys.path.insert(0, _BACKEND_SRC)

from sam.members.domain.application_publish import ApplicationPublishService
from sam.members.domain.application_readiness import StaticMailReadinessProvider
from sam.shared.page_styles import render_page_styles

_TENANT = "h-dcn"
_SLUG = "hdcn-application-form"
_PUBLIC_API_BASE = "https://api.jabaki.nl"


# ── In-memory seams (no boto3, no AWS) ────────────────────────────────────────────────


class _FakeSlugReader:
    """In-memory ``FormSlugReader`` — returns a fixed, well-formed slug."""

    def get_form_slug(self, tenant_id):
        return _SLUG


class _FakeFieldConfigReader:
    """In-memory ``PublicFieldConfigReader`` — one on-form field (passes the readiness gate)."""

    def get_public_field_config(self, tenant_id):
        return {
            "tenant_id": tenant_id,
            "fields": [{"key": "f0"}],
            "functional_groups": [],
            "locales": ["nl", "en"],
            "notice": {"version": None},
        }


class _FakeLookAndFeelReader:
    """In-memory ``LookAndFeelSettingsReader`` — returns the configured resolved VALUES."""

    def __init__(self, values):
        self._values = dict(values)

    def get_look_and_feel(self, tenant_id):
        return self._values


class _CapturingArtifactWriter:
    """In-memory ``PublicPageArtifactWriter`` — captures the published ``index_html``.

    Injecting a writer is what turns ``publish()`` into a SUCCESSFUL publish (an artifact is
    written) rather than the dormant ``PublishPipelineNotWired`` seam, so the captured artifact
    is the thing the property asserts over. No S3 / no CloudFront.
    """

    def __init__(self):
        self.index_html = None
        self.form_json = None

    def publish_artifacts(self, slug, *, index_html, form_json):
        self.index_html = index_html
        self.form_json = form_json


def _publish_with_resolved_values(values):
    """Run a SUCCESSFUL publish for a tenant whose resolved values are ``values``.

    Returns the ``_CapturingArtifactWriter`` so the test can inspect the baked artifact.
    """
    writer = _CapturingArtifactWriter()
    svc = ApplicationPublishService(
        slug_reader=_FakeSlugReader(),
        readiness_provider=StaticMailReadinessProvider({_TENANT: (True, "h-dcn.nl")}),
        field_config_reader=_FakeFieldConfigReader(),
        look_and_feel_reader=_FakeLookAndFeelReader(values),
        artifact_writer=writer,
    )
    result = svc.publish(_TENANT)
    assert result["success"] is True  # a successful publish (the property's precondition)
    return writer


# ── Strategy over valid resolved Look_And_Feel_Settings values ────────────────────────

# Known "good" values per attribute (exercise the recognised-value lookup branches) alongside
# free text (exercise the default-fallback / sanitiser branches).
_COLORS = ["#2D5F8A", "#F4A261", "#112233", "#fff", "#000000", "rebeccapurple"]
_FONTS = ["system", "Inter", "Lora", "Roboto", "Open Sans", "Playfair Display"]
_SPACINGS = ["compact", "normal", "relaxed"]
_RADII = ["sharp", "rounded", "pill"]
_SHADOWS = ["none", "subtle", "medium", "dramatic"]


def _value_strategy(known):
    return st.one_of(st.sampled_from(known), st.text(max_size=20))


def _settings_strategy():
    """A valid resolved values mapping: any subset of the seven supported keys.

    ``{}`` (all keys omitted) models a tenant that resolved to NO values — the "defaults where a
    tenant has none" clause of the property.
    """
    return st.fixed_dictionaries(
        {},
        optional={
            "color_primary": _value_strategy(_COLORS),
            "color_accent": _value_strategy(_COLORS),
            "font_heading": _value_strategy(_FONTS),
            "font_body": _value_strategy(_FONTS),
            "base_spacing": _value_strategy(_SPACINGS),
            "border_radius_global": _value_strategy(_RADII),
            "shadow_style": _value_strategy(_SHADOWS),
        },
    )


@pytest.fixture(autouse=True)
def _set_public_api_base_env(monkeypatch):
    """The publish render step resolves ``PUBLIC_API_BASE_URL`` fail-fast (no default)."""
    monkeypatch.setenv("PUBLIC_API_BASE_URL", _PUBLIC_API_BASE)


@settings(max_examples=150, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(values=_settings_strategy())
def test_published_form_carries_styling_derived_from_resolved_values(values):
    """Property 11: a successful publish carries Layer-2 styling for EXACTLY the resolved
    values (and Layer-2 defaults where the tenant resolved to none). Req 5.1/5.2/5.4."""
    writer = _publish_with_resolved_values(values)

    # The published artifact exists (a SUCCESSFUL publish — the property's precondition).
    assert writer.index_html is not None

    # Layer 2's output for EXACTLY the resolved values (independent call on the same mapping).
    # Absent/omitted attributes resolve to the SAM-owned defaults inside render_page_styles, so
    # a `{}` tenant yields the defaults — the "where a tenant has none" clause.
    expected = render_page_styles(dict(values))

    # `page_shell.render_page` bakes the CSS verbatim as `css_variables + "\n" + page_css`
    # inside the single <style> block, so the published form carries EXACTLY that styling.
    expected_css_block = f"{expected.css_variables}\n{expected.page_css}"
    assert expected_css_block in writer.index_html

    # And the brand colours the resolved values produce are present in the baked artifact
    # (the observable "styling derived from the values" — Req 5.2), via the page CSS Layer 2
    # generated from those values.
    assert expected.page_css in writer.index_html
    assert expected.css_variables in writer.index_html
