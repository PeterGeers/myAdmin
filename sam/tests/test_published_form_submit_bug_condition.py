"""
Bugfix spec `bugfix-published-form-submit` — Task 1: the bug-condition EXPLORATION test.

Parent spec: `.kiro/specs/Members/14 - public-pages-multi-tenant-serving` (R5.1, R5.3, R5.5, R7.1, R10).
Bugfix spec: `.kiro/specs/Members/14 .../bugfix-published-form-submit` (bugfix.md / design.md).

WHAT THIS TEST IS
-----------------
This is the EXPLORATION test for Property 1 (Bug Condition) — the PUBLISHED static application
form that renders and is styled but is a DEAD END for applicants. It ENCODES THE EXPECTED (fixed)
behaviour, so on the UNFIXED code it MUST FAIL — that failure is the counterexample proving the
bug exists (bugfix workflow). After the fix (tasks 3.x) the SAME assertions PASS unchanged,
validating the fix.

It is a SCOPED property-based test (scoped-PBT): the generated input space is deliberately
constrained to a REPRESENTATIVE public field config — one that carries a `format`-constrained
field (`format = {"checker": "IBAN"}`), a non-empty `locales` list, and a `notice.version` — so
every generated case exercises all three facets of `isBugCondition` (design Formal Specification):

  * SUBMIT         — does the published artifact `preventDefault` the native submit and POST the
                     backend JSON shape to `POST /public/members/{slug}/applications`?  (defect A)
  * FORMAT         — for the IBAN field, does the artifact wire a client-side IBAN check?  (defect B)
  * CONSENT_LOCALE — does the artifact render a consent control bound to `notice.version` AND a
                     locale selector from `locales`?  (defect B consequence)

On the UNFIXED render all three are ABSENT, so each facet assertion FAILS — the failure IS the
counterexample proving the published form is unusable.

NO live AWS: the render step is PURE (it returns the HTML string). The exploration runs offline
against `render_application_form_page` / `build_form_body_html` over an in-memory
`get_public_field_config`-shaped config (steering 39 — the renderer's only field source), with a
realistic shape (IBAN format token, locales, notice) mirroring the real `h-dcn` schema.

Validates (bugfix): Requirements 1.1, 1.2, 1.3, 1.4, 1.5
"""

from __future__ import annotations

import os
import re
import sys

from hypothesis import given, settings
from hypothesis import strategies as st

_REPO_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)
# LandingPageStyles lives in backend/src/services (vendored into the Members layer at build);
# the dev/test run resolves it from backend/src on the path (mirrors the sibling render test).
_BACKEND_SRC = os.path.join(_REPO_ROOT, "backend", "src")
if _BACKEND_SRC not in sys.path:
    sys.path.insert(0, _BACKEND_SRC)

from sam.members.domain.application_form_render import (  # noqa: E402
    build_form_body_html,
    render_application_form_page,
)

#: The verified real-data tenant whose published form is the dead end (bugfix.md Examples).
_SLUG = "hdcn-aanmelden"

#: The backend public submit endpoint the published artifact MUST call (design Property 1 / R5.5).
#: A fixed artifact references this path (with the slug substituted) inside its submit script.
_SUBMIT_PATH_RE = re.compile(
    r"/public/members/[^/\"'\s]+/applications", re.IGNORECASE
)


# ── The scoped input space: a REPRESENTATIVE public field config ──────────────────────
#
# Every generated config carries (by construction) the three things that make all three facets
# live at once: a `format={"checker":"IBAN"}` field, a non-empty `locales`, and a `notice.version`.
# The only variation is cosmetic (extra plain fields, label text, which locales, the version
# string) so the property holds across a representative slice, not a single hand-built fixture.


def _iban_field():
    """The IBAN `format`-constrained field — the FORMAT facet's subject (bugfix.md Examples)."""
    return {
        "key": "iban",
        "type": "text",
        "label": {"nl": "IBAN", "en": "IBAN"},
        "required": True,
        # The token `_serialize_public_field` already emits under payload["format"] (design):
        "format": {"checker": "IBAN", "params": {}},
    }


_PLAIN_FIELD = st.fixed_dictionaries(
    {
        "key": st.sampled_from(["first_name", "last_name", "email", "phone", "city"]),
        "type": st.sampled_from(["text", "email", "tel"]),
        "label": st.just({"nl": "Veld", "en": "Field"}),
    }
)


@st.composite
def _public_field_configs(draw):
    """A representative `get_public_field_config`-shaped config (steering 39 — single source).

    Guaranteed to carry the IBAN format field, a non-empty `locales`, and a `notice.version` so
    every draw exercises SUBMIT + FORMAT + CONSENT_LOCALE at once.
    """
    extras = draw(st.lists(_PLAIN_FIELD, min_size=0, max_size=3, unique_by=lambda f: f["key"]))
    locales = draw(
        st.lists(st.sampled_from(["nl", "en", "de", "fr"]), min_size=1, max_size=4, unique=True)
    )
    version = draw(st.sampled_from(["v1", "2024-01", "3", "notice-7"]))
    return {
        "tenant_id": "h-dcn",
        # The IBAN field is always present; plain fields vary. All come from the whitelist.
        "fields": [_iban_field(), *extras],
        "functional_groups": [],
        "locales": locales,
        "notice": {"version": version},
    }


def _render(config):
    """Render the published artifact the way the publish step does today (unfixed signature).

    Uses the current `render_application_form_page` entry point over the config — no slug/api_base
    parameters exist on the unfixed signature (their absence is defect A/1.5). The assertions below
    encode the FIXED behaviour, so they fail against this unfixed artifact.
    """
    return render_application_form_page(
        config,
        head_meta={
            "title": "Aanmelden",
            "canonical": f"https://{_SLUG}.jabaki.nl/apply",
        },
    )


# ══════════════════════════════════════════════════════════════════════════════════════
# FACET: SUBMIT — defect A / bugfix 1.1, 1.2, 1.5 (and 1.4's submit consequence).
#
# EXPECTED (fixed) behaviour: the published artifact `preventDefault`s the native submit and sends
# a JSON request to `POST /public/members/{slug}/applications` (design Property 1 / R2.1). On the
# UNFIXED render the body is a bare `<form ... method="post">` with NO embedded submit <script>,
# NO preventDefault, and NO reference to the backend path — a submit would native-POST to /apply
# and 404. So these assertions FAIL now; the failure IS the counterexample.
# ══════════════════════════════════════════════════════════════════════════════════════


@settings(max_examples=25)
@given(config=_public_field_configs())
def test_submit_published_artifact_prevents_native_post_and_posts_json_to_backend(config):
    artifact = _render(config)
    body = build_form_body_html(config)

    # Documented root-cause fact (the buggy shape we observe): the unfixed body IS a bare
    # method="post" form with a submit button and no action. (Not asserted as the property — it is
    # the current defect; pinning it in the message documents the counterexample.)
    bare_native_form = bool(
        re.search(r'<form[^>]*method="post"', body, re.IGNORECASE)
    )

    has_prevent_default = "preventDefault" in artifact
    has_submit_script = "<script" in artifact and (
        "fetch(" in artifact or "XMLHttpRequest" in artifact
    )
    targets_backend = bool(_SUBMIT_PATH_RE.search(artifact))

    assert has_prevent_default and has_submit_script and targets_backend, (
        "BUG (SUBMIT facet): the PUBLISHED artifact does not wire a working backend submit. "
        f"Observed on unfixed render of slug {_SLUG!r}: "
        f"bare native method=post form={bare_native_form}, preventDefault={has_prevent_default}, "
        f"submit <script> with fetch/XHR={has_submit_script}, "
        f"POST /public/members/{{slug}}/applications reference={targets_backend}. "
        "Counterexample: an applicant clicks Verstuur -> the browser native-POSTs form-urlencoded "
        f"to https://{_SLUG}.jabaki.nl/apply -> 404 Not Found; the backend endpoint is never called "
        "and the application is lost."
    )


# ══════════════════════════════════════════════════════════════════════════════════════
# FACET: FORMAT — defect B / bugfix 1.3.
#
# EXPECTED (fixed) behaviour: the IBAN `format`-constrained field wires a client-side IBAN check
# (mirroring the field_formats IBAN checker). On the UNFIXED render `_render_field` ignores the
# `format` token entirely, so the IBAN field is a plain <input> with no client check — this FAILS.
# ══════════════════════════════════════════════════════════════════════════════════════


@settings(max_examples=25)
@given(config=_public_field_configs())
def test_format_published_artifact_wires_client_side_iban_check_for_the_iban_field(config):
    artifact = _render(config)

    # A fixed artifact references the IBAN checker semantics for the `iban` field: either the
    # checker token or an IBAN client-check routine the submit script runs. The unfixed render
    # carries NONE of these (the field render reads only key/type/label/required/options).
    mentions_iban_checker = "IBAN" in artifact or "iban" in artifact.lower()
    wires_iban_check = mentions_iban_checker and (
        "<script" in artifact
        and ("format" in artifact or "checker" in artifact or "mod97" in artifact.lower())
    )

    assert wires_iban_check, (
        "BUG (FORMAT facet): the PUBLISHED artifact does NOT run a client-side IBAN check for the "
        "format-constrained `iban` field. The public field config emits "
        "format={'checker':'IBAN'} but `_render_field` ignores the token, so the published page "
        f"renders the IBAN input as a plain field with no check. Counterexample: on slug {_SLUG!r} "
        "an applicant types an IBAN with a bad checksum -> the page accepts it with no feedback "
        "(no client IBAN validation wired)."
    )


# ══════════════════════════════════════════════════════════════════════════════════════
# FACET: CONSENT_LOCALE — defect B consequence / bugfix 1.4.
#
# EXPECTED (fixed) behaviour: the artifact renders a consent control bound to `notice.version` AND
# a locale selector from `locales` (both REQUIRED by the backend submit). On the UNFIXED render
# `build_form_body_html` emits NEITHER — so even a correctly-posted body would be hard-rejected by
# the backend for missing consent. These assertions FAIL now.
# ══════════════════════════════════════════════════════════════════════════════════════


@settings(max_examples=25)
@given(config=_public_field_configs())
def test_consent_locale_published_artifact_renders_consent_bound_to_notice_and_locale_selector(
    config,
):
    artifact = _render(config)
    notice_version = str(config["notice"]["version"])
    locales = config["locales"]

    # Consent: a control bound to the notice version (a checkbox that carries the version so the
    # submit script can stamp `consent`). The unfixed render has no consent control at all.
    renders_consent = ("consent" in artifact.lower()) and (notice_version in artifact)

    # Locale selector: a <select>/control exposing the config's `locales`. The unfixed render has
    # no locale selector — the applicant cannot pick a locale the backend requires on submit.
    renders_locale_selector = ("locale" in artifact.lower() or "lang" in artifact.lower()) and all(
        loc in artifact for loc in locales
    )

    assert renders_consent and renders_locale_selector, (
        "BUG (CONSENT_LOCALE facet): the PUBLISHED artifact renders NEITHER a consent control "
        f"bound to notice.version={notice_version!r} NOR a locale selector from locales={locales!r}. "
        f"Observed on unfixed render of slug {_SLUG!r}: consent control bound to version="
        f"{renders_consent}, locale selector exposing locales={renders_locale_selector}. "
        "Counterexample: the config exposes notice.version and locales, but the published page "
        "shows no consent checkbox and no locale selector, so even a correctly-posted body is "
        "hard-rejected by the backend for missing consent."
    )
