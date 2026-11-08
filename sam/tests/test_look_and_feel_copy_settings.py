"""
SAM Page Look-and-Feel — Task 5.3: ``LookAndFeelSettingsService.copy_settings`` — the Layer-1
one-time snapshot copy of a Page's look-and-feel VALUES onto another Page (Req 9).

Spec: ``.kiro/specs/Members/15 - sam-page-look-and-feel`` (design C3 / DD-2, Layer 1).

What this asserts (task 5.3 scope — happy path + cross-tenant rejection)
------------------------------------------------------------------------
- ``copy_settings`` reads the source Page's resolved VALUES via the injected reader and issues a
  SINGLE ``SET look_and_feel = :snapshot`` Change-Op on the target via the writer's
  ``copy_look_and_feel`` — overwriting the target (Req 9.1 / 9.3).
- The snapshot carried to the writer equals the source's resolved values at copy time; an absent
  source slice is a valid snapshot (overwrites to "all defaults").
- The copy establishes NO ongoing link: it issues exactly ONE copy op and NO set/remove ops — there
  is nothing wired between source and target to propagate a later change (Req 9.2 / 9.5).
- A source belonging to ANOTHER tenant is REJECTED before any read or write (Req 9.4): no reader and
  no writer call is made, so neither tenant's state is touched.

The reader/writer are in-memory fakes (no boto3, no DynamoDB — pure domain, steering 35/39). This
file is DELIBERATELY SEPARATE from ``test_look_and_feel_settings_service.py`` (task 5.1 get/set and
the task 5.2 property test share that file); task 5.5 adds the remaining copy unit tests, so this
file stays focused on the copy happy path + the cross-tenant rejection.

Validates: Requirements 9.1, 9.2, 9.3, 9.4, 9.5
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
    CrossTenantCopyError,
    LookAndFeelSettingsService,
)

_TENANT = "h-dcn"
_OTHER_TENANT = "t-other"


# ── In-memory fakes (no boto3, no DynamoDB) ─────────────────────────────────────────────


class FakeReader:
    """In-memory resolved-view reader returning a configured VALUES mapping per tenant.

    Also records which tenants it was asked to resolve, so a test can assert the source read is
    scoped to the verified tenant and never reaches another tenant's slice.
    """

    def __init__(self, values_by_tenant=None):
        self._values = dict(values_by_tenant or {})
        self.reads: list[str] = []

    def get_look_and_feel(self, tenant_id):
        self.reads.append(tenant_id)
        return dict(self._values.get(tenant_id, {}))


class RecordingWriter:
    """Records every look-and-feel Change-Op. No boto3."""

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


def _service(*, reader=None, writer=None):
    reader = reader if reader is not None else FakeReader()
    writer = writer if writer is not None else RecordingWriter()
    return LookAndFeelSettingsService(reader, writer), reader, writer


# ── Happy path — one-time snapshot overwrites the target via a single copy op (Req 9.1/9.3) ──


def test_copy_settings_issues_single_copy_op_with_source_snapshot():
    source_values = {
        "color_primary": "#2D5F8A",
        "font_body": "Inter",
        "shadow_style": "subtle",
    }
    svc, reader, writer = _service(reader=FakeReader({_TENANT: source_values}))

    result = svc.copy_settings(
        _TENANT, APPLICATION_FORM_PAGE_ID, APPLICATION_FORM_PAGE_ID
    )

    assert result == {"version": "v-next", "idempotent_replay": False}
    # Exactly ONE op, and it is the whole-slice snapshot overwrite (SET look_and_feel = :snapshot).
    assert writer.calls == [
        {
            "op": "copy",
            "tenant_id": _TENANT,
            "snapshot_values": source_values,
            "client_op_id": None,
        }
    ]


def test_copy_settings_reads_source_scoped_to_verified_tenant():
    svc, reader, _writer = _service(reader=FakeReader({_TENANT: {"base_spacing": "relaxed"}}))
    svc.copy_settings(_TENANT, APPLICATION_FORM_PAGE_ID, APPLICATION_FORM_PAGE_ID)
    # The source read is scoped to the verified tenant only — never another tenant's slice.
    assert reader.reads == [_TENANT]


def test_copy_settings_absent_source_is_a_valid_empty_snapshot():
    # No source values stored → a valid snapshot that overwrites the target to "all defaults".
    svc, _reader, writer = _service(reader=FakeReader())  # nothing seeded
    svc.copy_settings(_TENANT, APPLICATION_FORM_PAGE_ID, APPLICATION_FORM_PAGE_ID)
    assert writer.calls == [
        {
            "op": "copy",
            "tenant_id": _TENANT,
            "snapshot_values": {},
            "client_op_id": None,
        }
    ]


def test_copy_settings_establishes_no_link_only_one_copy_op():
    # No ongoing link (Req 9.2/9.5): the copy issues exactly ONE copy op and NO set/remove ops —
    # nothing is wired between source and target to propagate a later change.
    svc, _reader, writer = _service(reader=FakeReader({_TENANT: {"font_heading": "Inter"}}))
    svc.copy_settings(_TENANT, APPLICATION_FORM_PAGE_ID, APPLICATION_FORM_PAGE_ID)
    ops = [c["op"] for c in writer.calls]
    assert ops == ["copy"]


def test_copy_settings_threads_client_op_id():
    svc, _reader, writer = _service(reader=FakeReader({_TENANT: {"shadow_style": "medium"}}))
    svc.copy_settings(
        _TENANT, APPLICATION_FORM_PAGE_ID, APPLICATION_FORM_PAGE_ID, client_op_id="op-7"
    )
    assert writer.calls[-1]["client_op_id"] == "op-7"


def test_copy_settings_snapshot_is_independent_of_later_source_mutation():
    # The snapshot carried to the writer is a copy, not a live view: mutating the source store
    # afterwards does not alter what was written (one-time snapshot, Req 9.2).
    source_values = {"color_accent": "#F4A261"}
    reader = FakeReader({_TENANT: source_values})
    svc, _reader, writer = _service(reader=reader)

    svc.copy_settings(_TENANT, APPLICATION_FORM_PAGE_ID, APPLICATION_FORM_PAGE_ID)
    source_values["color_accent"] = "#000000"  # mutate the source after the copy

    assert writer.calls[-1]["snapshot_values"] == {"color_accent": "#F4A261"}


# ── Cross-tenant source rejected — no read, no write (Req 9.4) ───────────────────────────


def test_copy_settings_cross_tenant_source_rejected_no_read_no_write():
    svc, reader, writer = _service(
        reader=FakeReader({_TENANT: {"base_spacing": "normal"}, _OTHER_TENANT: {"base_spacing": "relaxed"}})
    )
    with pytest.raises(CrossTenantCopyError):
        svc.copy_settings(
            _TENANT,
            APPLICATION_FORM_PAGE_ID,
            APPLICATION_FORM_PAGE_ID,
            source_tenant_id=_OTHER_TENANT,
        )
    # Neither tenant's state is observed or touched: no reader call, no writer call.
    assert reader.reads == []
    assert writer.calls == []


def test_copy_settings_cross_tenant_error_is_not_a_validation_error():
    # Cross-tenant copy maps to a caller-safe 403 (PermissionError), NOT a 422 validation error.
    svc, _reader, _writer = _service()
    with pytest.raises(CrossTenantCopyError) as exc:
        svc.copy_settings(
            _TENANT,
            APPLICATION_FORM_PAGE_ID,
            APPLICATION_FORM_PAGE_ID,
            source_tenant_id=_OTHER_TENANT,
        )
    assert isinstance(exc.value, PermissionError)
    # Generic message — must not confirm whether the other tenant/page exists.
    assert _OTHER_TENANT not in str(exc.value)


def test_copy_settings_same_source_tenant_explicit_is_permitted():
    # Passing source_tenant_id explicitly equal to the verified tenant is the same-tenant case.
    svc, _reader, writer = _service(reader=FakeReader({_TENANT: {"font_body": "system"}}))
    svc.copy_settings(
        _TENANT,
        APPLICATION_FORM_PAGE_ID,
        APPLICATION_FORM_PAGE_ID,
        source_tenant_id=_TENANT,
    )
    assert writer.calls[-1]["op"] == "copy"
    assert writer.calls[-1]["snapshot_values"] == {"font_body": "system"}
