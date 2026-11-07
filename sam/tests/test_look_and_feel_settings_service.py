"""
SAM Page Look-and-Feel — Task 5.1: the Layer-1 authoring service
``LookAndFeelSettingsService`` (get / set), with an injected resolved-view reader and a Change-Op
writer.

Spec: ``.kiro/specs/Members/15 - sam-page-look-and-feel`` (design C3 / DD-2, Layer 1).

What this asserts
-----------------
- ``get_settings`` is a tenant-scoped resolved-view read of the stored VALUES; an absent slice/key
  resolves to an empty mapping (Layer 2 then applies its own defaults — Req 2.4 / 3.3 / 4.4 / 5.4).
- ``set_setting`` VALIDATES the attribute against the exactly-seven supported set (Req 3.4) and the
  value against its permitted set (Req 4.5) BEFORE any write; an invalid attribute/value is
  REJECTED and NO Change-Op is issued — the stored values are left unchanged by construction
  (Req 4.5). A valid change issues exactly ONE scoped Change-Op via the injected writer (Req 8.1).
- The permitted enum sets stay in lock-step with the Layer-2 generator's own lookup maps
  (``sam/shared/page_styles``), so a value the service accepts is a value the generator renders
  meaningfully.
- ``page_id`` is a forward-looking seam resolving today to the application form; an unknown id is
  rejected rather than silently routed.

The writer is a small in-memory fake that RECORDS the look-and-feel ops (no boto3, no DynamoDB —
this service is pure domain, steering 35/39). The reader is an in-memory fake returning a configured
resolved mapping. ``copy_settings`` (Req 9) is task 5.3 and is NOT exercised here.

Validates: Requirements 2.3, 3.4, 4.1, 4.5, 8.1, 8.3
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
_BACKEND_SRC = os.path.join(_REPO_ROOT, "backend", "src")
if _BACKEND_SRC not in sys.path:
    sys.path.insert(0, _BACKEND_SRC)

from sam.members.domain.look_and_feel_settings_service import (
    APPLICATION_FORM_PAGE_ID,
    LookAndFeelSettingsReader,
    LookAndFeelSettingsService,
    LookAndFeelSettingsWriter,
    LookAndFeelValidationError,
)
from sam.shared import page_styles
from sam.shared.page_styles import SUPPORTED_ATTRIBUTES

_TENANT = "h-dcn"


# ── In-memory fakes (no boto3, no DynamoDB) ─────────────────────────────────────────────


class FakeReader:
    """In-memory resolved-view reader returning a configured VALUES mapping per tenant."""

    def __init__(self, values_by_tenant=None):
        self._values = dict(values_by_tenant or {})

    def get_look_and_feel(self, tenant_id):
        return dict(self._values.get(tenant_id, {}))


class RecordingWriter:
    """Records every look-and-feel Change-Op (mirrors the sibling CRUD test fakes). No boto3."""

    def __init__(self):
        self.calls: list[dict] = []

    def set_look_and_feel(self, tenant_id, attribute, value, *, client_op_id=None):
        self.calls.append(
            {
                "op": "set",
                "tenant_id": tenant_id,
                "attribute": attribute,
                "value": value,
                "client_op_id": client_op_id,
            }
        )
        return {"version": "v-next", "idempotent_replay": False}

    def remove_look_and_feel(self, tenant_id, attribute, *, client_op_id=None):
        self.calls.append(
            {
                "op": "remove",
                "tenant_id": tenant_id,
                "attribute": attribute,
                "client_op_id": client_op_id,
            }
        )
        return {"version": "v-next", "idempotent_replay": False}

    def copy_look_and_feel(self, tenant_id, snapshot_values, *, client_op_id=None):
        self.calls.append(
            {
                "op": "copy",
                "tenant_id": tenant_id,
                "snapshot_values": dict(snapshot_values),
                "client_op_id": client_op_id,
            }
        )
        return {"version": "v-next", "idempotent_replay": False}

    @property
    def last(self) -> dict:
        assert self.calls, "no look-and-feel op was ever recorded"
        return self.calls[-1]


def _service(*, reader=None, writer=None):
    reader = reader if reader is not None else FakeReader()
    writer = writer if writer is not None else RecordingWriter()
    return LookAndFeelSettingsService(reader, writer), reader, writer


# ── The injected seams conform to their Protocols ───────────────────────────────────────


def test_fakes_conform_to_injected_protocols():
    assert isinstance(FakeReader(), LookAndFeelSettingsReader)
    assert isinstance(RecordingWriter(), LookAndFeelSettingsWriter)


# ── get_settings — resolved-view read; absent → empty (defaults) ────────────────────────


def test_get_settings_returns_resolved_values():
    stored = {"color_primary": "#2D5F8A", "shadow_style": "medium"}
    svc, _reader, _writer = _service(reader=FakeReader({_TENANT: stored}))
    assert svc.get_settings(_TENANT, APPLICATION_FORM_PAGE_ID) == stored


def test_get_settings_absent_tenant_resolves_to_empty_mapping():
    svc, _reader, _writer = _service(reader=FakeReader())  # nothing seeded
    assert svc.get_settings("unconfigured") == {}


def test_get_settings_page_id_defaults_to_application_form():
    stored = {"base_spacing": "relaxed"}
    svc, _reader, _writer = _service(reader=FakeReader({_TENANT: stored}))
    # page_id omitted → defaults to the application form (the one SAM-owned page today).
    assert svc.get_settings(_TENANT) == stored


def test_get_settings_does_not_write():
    svc, _reader, writer = _service(reader=FakeReader({_TENANT: {"font_body": "Inter"}}))
    svc.get_settings(_TENANT)
    assert writer.calls == [], "a read must never issue a Change-Op"


# ── set_setting — a VALID change issues exactly one scoped Change-Op ─────────────────────


def test_set_setting_valid_enum_issues_single_set_op():
    svc, _reader, writer = _service()
    result = svc.set_setting(_TENANT, APPLICATION_FORM_PAGE_ID, "base_spacing", "relaxed")

    assert result == {"version": "v-next", "idempotent_replay": False}
    assert writer.calls == [
        {
            "op": "set",
            "tenant_id": _TENANT,
            "attribute": "base_spacing",
            "value": "relaxed",
            "client_op_id": None,
        }
    ]


def test_set_setting_valid_colour_issues_single_set_op():
    svc, _reader, writer = _service()
    svc.set_setting(_TENANT, APPLICATION_FORM_PAGE_ID, "color_primary", "#2D5F8A")
    assert writer.last["op"] == "set"
    assert writer.last["attribute"] == "color_primary"
    assert writer.last["value"] == "#2D5F8A"


def test_set_setting_valid_font_system_is_permitted():
    svc, _reader, writer = _service()
    svc.set_setting(_TENANT, APPLICATION_FORM_PAGE_ID, "font_heading", "system")
    assert writer.last["op"] == "set"
    svc.set_setting(_TENANT, APPLICATION_FORM_PAGE_ID, "font_body", "Inter")
    assert writer.last["value"] == "Inter"


def test_set_setting_threads_client_op_id():
    svc, _reader, writer = _service()
    svc.set_setting(
        _TENANT, APPLICATION_FORM_PAGE_ID, "shadow_style", "subtle", client_op_id="op-1"
    )
    assert writer.last["client_op_id"] == "op-1"


def test_set_setting_none_value_clears_via_remove_op():
    # The steering-39 clear-vs-unchanged contract: an explicit None REMOVEs (revert to default).
    svc, _reader, writer = _service()
    svc.set_setting(_TENANT, APPLICATION_FORM_PAGE_ID, "color_accent", None)
    assert writer.last == {
        "op": "remove",
        "tenant_id": _TENANT,
        "attribute": "color_accent",
        "client_op_id": None,
    }


# ── set_setting — UNSUPPORTED attribute rejected, NO write (Req 3.4) ─────────────────────


def test_set_setting_unsupported_attribute_rejected_no_write():
    svc, _reader, writer = _service()
    with pytest.raises(LookAndFeelValidationError) as exc:
        svc.set_setting(_TENANT, APPLICATION_FORM_PAGE_ID, "background_image", "x.png")
    # The rejected attribute is named (caller-safe), and NO Change-Op was issued.
    assert "background_image" in str(exc.value)
    assert writer.calls == [], "an unsupported attribute must not reach the writer"


def test_set_setting_non_string_attribute_rejected_no_write():
    svc, _reader, writer = _service()
    with pytest.raises(LookAndFeelValidationError):
        svc.set_setting(_TENANT, APPLICATION_FORM_PAGE_ID, 123, "whatever")
    assert writer.calls == []


# ── set_setting — INVALID value rejected, stored values unchanged (Req 4.5) ──────────────


@pytest.mark.parametrize(
    "attribute,bad_value",
    [
        ("base_spacing", "huge"),
        ("border_radius_global", "square"),
        ("shadow_style", "glow"),
        ("color_primary", "not-a-colour"),
        ("color_accent", "#12"),  # wrong hex length
        ("color_primary", 123),  # non-string
        ("font_heading", "bad{font}"),  # unsafe characters
        ("font_body", ""),  # blank
    ],
)
def test_set_setting_invalid_value_rejected_no_write(attribute, bad_value):
    svc, _reader, writer = _service()
    with pytest.raises(LookAndFeelValidationError) as exc:
        svc.set_setting(_TENANT, APPLICATION_FORM_PAGE_ID, attribute, bad_value)
    # The rejected attribute is identified (Req 4.5), and NO Change-Op was issued → stored
    # values are unchanged by construction.
    assert attribute in str(exc.value)
    assert writer.calls == [], "an invalid value must not reach the writer"


def test_invalid_value_leaves_resolved_read_unchanged():
    # A rejected set does not perturb what a subsequent get resolves (stored values preserved).
    stored = {"base_spacing": "normal"}
    reader = FakeReader({_TENANT: stored})
    svc, _reader, writer = _service(reader=reader)

    with pytest.raises(LookAndFeelValidationError):
        svc.set_setting(_TENANT, APPLICATION_FORM_PAGE_ID, "base_spacing", "huge")

    assert writer.calls == []
    assert svc.get_settings(_TENANT) == stored


# ── page_id seam — unknown id rejected, never silently routed ────────────────────────────


def test_unknown_page_id_rejected_on_get():
    svc, _reader, _writer = _service()
    with pytest.raises(LookAndFeelValidationError):
        svc.get_settings(_TENANT, "landing_page")


def test_unknown_page_id_rejected_on_set_no_write():
    svc, _reader, writer = _service()
    with pytest.raises(LookAndFeelValidationError):
        svc.set_setting(_TENANT, "landing_page", "base_spacing", "normal")
    assert writer.calls == []


# ── Parity: permitted enum sets stay in lock-step with the Layer-2 generator's maps ──────


def test_permitted_enum_sets_match_generator_lookup_maps():
    from sam.members.domain.look_and_feel_settings_service import _PERMITTED_VALUES

    assert _PERMITTED_VALUES["base_spacing"] == frozenset(page_styles._SPACING_MAP)
    assert _PERMITTED_VALUES["border_radius_global"] == frozenset(
        page_styles._GLOBAL_RADIUS_MAP
    )
    assert _PERMITTED_VALUES["shadow_style"] == frozenset(page_styles._SHADOW_MAP)


def test_every_supported_attribute_has_a_permitted_value_rule():
    # Every attribute the SERVICE validates must be accepted for SOME value (so a valid author
    # never trips the defensive "no permitted-value rule" guard) — and, after the bugfix
    # ``bugfix-published-form-styling`` Task 10, the SERVICE validates EXACTLY the nine the
    # GENERATOR's ``SUPPORTED_ATTRIBUTES`` supports: the original seven plus ``logo`` /
    # ``header_title`` (the earlier ``columns`` attribute was removed — the form grid is now
    # fully width-driven, so a column count is no longer a settable attribute).
    from sam.members.domain.look_and_feel_settings_service import (
        _COLOUR_ATTRIBUTES,
        _FONT_ATTRIBUTES,
        _HEADER_TITLE_ATTRIBUTE,
        _LOGO_ATTRIBUTE,
        _PERMITTED_VALUES,
    )

    service_validated = (
        set(_PERMITTED_VALUES)
        | set(_COLOUR_ATTRIBUTES)
        | set(_FONT_ATTRIBUTES)
        | {_LOGO_ATTRIBUTE, _HEADER_TITLE_ATTRIBUTE}
    )
    # Task 10: the service now validates the FULL generator set — no attribute is left without a
    # permitted-value rule (no gap that would trip the defensive guard for a valid author).
    assert service_validated == set(SUPPORTED_ATTRIBUTES)

    svc, _reader, writer = _service()
    valid_by_attr = {
        "color_primary": "#2D5F8A",
        "color_accent": "#F4A261",
        "font_heading": "system",
        "font_body": "Inter",
        "base_spacing": "normal",
        "border_radius_global": "rounded",
        "shadow_style": "subtle",
        # The bugfix extension (Task 10) — one valid value per new attribute.
        "logo": "https://assets.example.org/logo.png",
        "header_title": "Membership application",
    }
    assert set(valid_by_attr) == service_validated
    for attr, value in valid_by_attr.items():
        svc.set_setting(_TENANT, APPLICATION_FORM_PAGE_ID, attr, value)
    assert len(writer.calls) == len(service_validated)


# ── set_setting — the TWO NEW attributes (bugfix Task 10): valid values accepted ──────


@pytest.mark.parametrize(
    "attribute,value",
    [
        ("logo", "https://assets.example.org/brand/logo.png"),
        ("logo", "/assets/logo.svg"),  # site-relative reference
        ("header_title", "Apply to join"),
        ("header_title", "x" * 200),  # exactly the length ceiling
    ],
)
def test_set_setting_new_attribute_valid_value_issues_single_set_op(attribute, value):
    svc, _reader, writer = _service()
    result = svc.set_setting(_TENANT, APPLICATION_FORM_PAGE_ID, attribute, value)
    assert result == {"version": "v-next", "idempotent_replay": False}
    assert len(writer.calls) == 1, "a valid set must issue exactly ONE scoped Change-Op"
    assert writer.last["op"] == "set"
    assert writer.last["attribute"] == attribute
    assert writer.last["value"] == value


# ── set_setting — the TWO NEW attributes: out-of-range rejected, stored values unchanged ──


@pytest.mark.parametrize(
    "attribute,bad_value",
    [
        # logo — a well-formed URL/asset reference; malformed / injection-shaped rejected.
        ("logo", "javascript:alert(1)"),
        ("logo", "data:image/png;base64,AAAA"),
        ("logo", 'url("evil")'),
        ("logo", "ftp://example.org/logo.png"),  # unsupported scheme
        ("logo", "logo.png"),  # not absolute/site-relative
        ("logo", "https://example.org/a b.png"),  # whitespace
        ("logo", "https://example.org/<svg>"),  # angle brackets
        ("logo", 123),  # non-string
        ("logo", "https://example.org/" + "a" * 2048),  # over length
        # header_title — length-bounded non-blank text; blank / over-length / non-string rejected.
        ("header_title", ""),  # blank
        ("header_title", "   "),  # whitespace only
        ("header_title", "x" * 201),  # over the length ceiling
        ("header_title", 42),  # non-string
    ],
)
def test_set_setting_new_attribute_invalid_value_rejected_no_write(attribute, bad_value):
    svc, _reader, writer = _service()
    with pytest.raises(LookAndFeelValidationError) as exc:
        svc.set_setting(_TENANT, APPLICATION_FORM_PAGE_ID, attribute, bad_value)
    # The rejected attribute is identified (caller-safe), and NO Change-Op was issued → stored
    # values are unchanged by construction (Req 4.5 / bugfix 3.4).
    assert attribute in str(exc.value)
    assert writer.calls == [], "an out-of-range value must not reach the writer"


def test_new_attribute_invalid_value_leaves_resolved_read_unchanged():
    # A rejected set of a NEW attribute does not perturb what a subsequent get resolves.
    stored = {"logo": "https://assets.example.org/logo.png", "header_title": "Keep me", "color_primary": "#2D5F8A"}
    reader = FakeReader({_TENANT: stored})
    svc, _reader, writer = _service(reader=reader)

    with pytest.raises(LookAndFeelValidationError):
        svc.set_setting(_TENANT, APPLICATION_FORM_PAGE_ID, "logo", "javascript:alert(1)")

    assert writer.calls == []
    assert svc.get_settings(_TENANT) == stored


def test_set_setting_new_attribute_none_value_clears_via_remove_op():
    # The steering-39 clear-vs-unchanged contract applies to the new attributes too: an explicit
    # None REMOVEs (revert to the Layer-2 default) with NO value validation.
    svc, _reader, writer = _service()
    svc.set_setting(_TENANT, APPLICATION_FORM_PAGE_ID, "logo", None)
    assert writer.last == {
        "op": "remove",
        "tenant_id": _TENANT,
        "attribute": "logo",
        "client_op_id": None,
    }

