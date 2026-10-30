"""
spec 12 (Application Form Serving Redesign) task 5.3 — the SAM half of the CLIENT↔SERVER
filter-parity PIN.

Task 5.2 deleted the server preview endpoint (``POST /members/application-preview``); the
builder's in-browser preview now reproduces the server's applicant-facing SELECTION entirely in
the browser via the pure ``buildPreviewConfig`` filter (task 5.1,
``frontend/.../applicationPreviewFilter.ts``). This test is the SAM side of the pin that stops the
two filters silently drifting now the endpoint is gone (R3.2 / R9.2):

  the SAME canonical fixture input, fed to the REAL server authority
  (:meth:`MembershipService.get_public_field_config`), must — after a plane-neutral normalization —
  produce the SAME ``expected`` applicant-facing selection the frontend parity test asserts
  ``buildPreviewConfig`` produces.

The ONE canonical fixture lives at ``sam/tests/fixtures/application_form_filter_parity.json``; the
frontend test root carries a byte-identical vendored copy. ``test_the_two_fixture_copies_are_byte_identical``
is the DRIFT GUARD: if either copy is edited without mirroring the other, it fails — so "both planes
compare against the SAME expected output" is enforced, not merely asserted by convention.

The server filter is the AUTHORITY (R5.2); if the two ever diverge the CLIENT is reconciled to the
server, never this assertion weakened.

Validates: Requirements R3.2, R9.2
"""

from __future__ import annotations

import json
import os
import sys

import pytest

_REPO_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from sam.members.domain.consent_notice import StaticConsentNoticeProvider
from sam.members.domain.field_resolver import (
    FieldFormat,
    FixedFieldOverride,
    OverlayField,
    StaticOverlayProvider,
    TenantOverlay,
)
from sam.members.domain.fixed_fields import EnumOption, FieldType
from sam.members.domain.membership_service import MembershipService

from sam.tests.test_field_config_endpoint import FakeCatalogRepository, _entry

# ── the ONE canonical fixture + its frontend vendored twin ────────────────────────────

_SAM_FIXTURE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "fixtures",
    "application_form_filter_parity.json",
)
_FRONTEND_FIXTURE = os.path.join(
    _REPO_ROOT,
    "frontend",
    "src",
    "components",
    "TenantAdmin",
    "MembersConfig",
    "__tests__",
    "fixtures",
    "application_form_filter_parity.json",
)

with open(_SAM_FIXTURE, encoding="utf-8") as _fh:
    FIXTURE = json.load(_fh)

TENANT = FIXTURE["tenant_id"]


# ── build the REAL server filter from the canonical fixture input ─────────────────────

_TYPE_BY_NAME = {t.value: t for t in FieldType}


def _field_type(name: str) -> FieldType:
    """The ``FieldType`` for a plane-neutral fixture type token (`string`/`enum`/`reference`…)."""
    return _TYPE_BY_NAME[name]


def _overlay_from_fixture() -> TenantOverlay:
    """Rebuild the tenant overlay that, resolved over the fixed base, yields the fixture fields.

    Every ``overlay``-group fixture field becomes a tenant-added :class:`OverlayField`; the one
    ``membership.membership_type`` field is a fixed-field OVERRIDE carrying ONLY the application
    attributes (its label/type/order/group come from the platform registry).
    """
    overrides: dict[str, FixedFieldOverride] = {}
    fields: dict[str, OverlayField] = {}

    for rf in FIXTURE["input"]["resolved_fields"]:
        key = rf["key"]
        group = rf["group"]
        app_choices = (
            tuple(rf["application_choices"])
            if rf.get("application_choices") is not None
            else None
        )
        fmt = (
            FieldFormat(
                checker=rf["format"]["checker"], params=rf["format"].get("params", {})
            )
            if rf.get("format")
            else None
        )

        if group == "membership" and key == "membership_type":
            # 03b CONTRACT (Task 10.5): membership_type owns its vocabulary as the field's OWN
            # inline options (the catalog is retired). The fixture's resolved membership_type
            # field carries those rich options directly — fold them onto the override so the
            # server's public read resolves the vocabulary from the field, then narrows it by the
            # application subset. Each option's `allowed` rides through (oudlid → allowed:false).
            mt_opts = tuple(
                EnumOption(
                    value=o["value"],
                    label=dict(o["label"]),
                    allowed=o.get("allowed", True),
                    order=o.get("order"),
                )
                for o in (rf.get("options") or ())
            )
            overrides[f"{group}.{key}"] = FixedFieldOverride(
                application_visible=rf.get("application_visible"),
                application_required=rf.get("application_required"),
                application_choices=app_choices,
                options=mt_opts or None,
                format=fmt,
            )
            continue

        # A tenant-added overlay field. The plane-neutral fixture carries an enum's choice list
        # under `options`: BARE strings model a bare-`choices` enum (the server returns a bare
        # subsetted value list), RICH `{value,label}` dicts model a rich-option enum (the server
        # returns `{value,label}`). Map each to the native overlay representation.
        choices = None
        options = None
        raw_opts = rf.get("options")
        if raw_opts is not None:
            if all(isinstance(o, str) for o in raw_opts):
                choices = tuple(raw_opts)
            else:
                options = tuple(
                    EnumOption(value=o["value"], label=dict(o["label"]))
                    for o in raw_opts
                )
        elif rf.get("choices") is not None:
            choices = tuple(rf["choices"])

        fields[key] = OverlayField(
            key=key,
            type=_field_type(rf["type"]),
            label=dict(rf["label"]),
            functional_group=rf.get("functional_group"),
            order=int(rf.get("order", 0)),
            choices=choices,
            options=options,
            show_when=rf.get("show_when"),
            application_visible=bool(rf.get("application_visible", False)),
            application_required=bool(rf.get("application_required", False)),
            application_choices=app_choices,
            format=fmt,
        )

    return TenantOverlay(overrides=overrides, fields=fields)


def _service() -> MembershipService:
    repo = FakeCatalogRepository()
    for entry in FIXTURE["membership_type_catalog"]:
        repo.add_type(
            TENANT,
            _entry(
                TENANT,
                entry["type_code"],
                label=dict(entry["label"]),
                active=bool(entry["active"]),
                order=int(entry["order"]),
            ),
        )
    return MembershipService(
        repo,
        overlay_provider=StaticOverlayProvider({TENANT: _overlay_from_fixture()}),
        consent_notice_provider=StaticConsentNoticeProvider(
            {TENANT: FIXTURE["consent_notice_version"]}
        ),
    )


# ── normalization: the SERVER public schema → the plane-neutral `expected` shape ──────


def _norm_options(raw) -> list | None:
    """Coerce a server ``options`` value to the canonical ``[{value,label{nl,en}}]`` | ``None``.

    The server emits ``None`` for a non-choice field, a BARE value list for a bare-``choices`` enum
    (``["m","l"]``), or rich ``{value,label[,order]}`` dicts for rich enums / the membership-type
    catalog feed. The frontend filter always emits rich ``{value,label{nl,en}}``; a bare value is
    mirrored to both locales (exactly like the client's string→label fallback), so the two compare
    like-for-like.
    """
    if raw is None:
        return None
    out = []
    for o in raw:
        if isinstance(o, str):
            out.append({"value": o, "label": {"nl": o, "en": o}})
        else:
            out.append({"value": o["value"], "label": dict(o["label"])})
    return out


def _normalize_server_field(f: dict) -> dict:
    """Project one SERVER public field to the plane-neutral `expected` field shape."""
    norm = {
        # The server emits bare `key` + `group`; the canonical shape is the dotted key the
        # renderer/submit key by (the frontend filter already emits this).
        "key": f"{f['group']}.{f['key']}",
        "type": f["type"],
        "label": dict(f["label"]),
        "functional_group": f["functional_group"],
        "order": int(f["order"]),
        "required": bool(f["required"]),
        "options": _norm_options(f.get("options")),
    }
    if f.get("show_when") is not None:
        norm["show_when"] = dict(f["show_when"])
    if f.get("format") is not None:
        norm["format"] = {
            "checker": f["format"]["checker"],
            "params": dict(f["format"].get("params", {})),
        }
    return norm


def _normalize_server_schema(schema: dict) -> dict:
    return {
        "locales": list(schema["locales"]),
        "fields": [_normalize_server_field(f) for f in schema["fields"]],
    }


# ── tests ─────────────────────────────────────────────────────────────────────────────


def test_the_two_fixture_copies_are_byte_identical():
    """DRIFT GUARD: the canonical SAM fixture and the frontend vendored copy are byte-for-byte
    identical, so both planes provably compare against the SAME `expected` output (R3.2)."""
    with open(_SAM_FIXTURE, "rb") as a, open(_FRONTEND_FIXTURE, "rb") as b:
        assert a.read() == b.read(), (
            "The canonical SAM parity fixture and its frontend vendored copy have drifted. "
            "Edit one and mirror the EXACT bytes to the other: "
            f"{_SAM_FIXTURE} <-> {_FRONTEND_FIXTURE}"
        )


def test_server_filter_matches_the_canonical_expected_selection():
    """The REAL server authority, fed the canonical input, produces the SAME applicant-facing
    selection the frontend parity test pins ``buildPreviewConfig`` to (R3.2 / R9.2)."""
    schema = _service().get_public_field_config(TENANT)
    assert _normalize_server_schema(schema) == FIXTURE["expected"]


def test_server_locales_match_the_expected_applicant_locales():
    """The applicant locale selector the server serves equals the fixture's (and the client's)."""
    schema = _service().get_public_field_config(TENANT)
    assert list(schema["locales"]) == FIXTURE["expected"]["locales"]
