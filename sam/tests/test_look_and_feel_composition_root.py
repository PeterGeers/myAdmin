"""
Spec 15 (SAM Page Look-and-Feel) Task 9 — composition-root wiring (design C6).

These pin the single composition root (``sam/members/handler/_dispatch_services.py``) wiring the
REAL look-and-feel seams, WITHOUT touching live AWS. Per the lazy/fail-fast accessor pattern every
accessor builds its service over repositories whose AWS resource resolves lazily on first real
call, so merely BUILDING a service (what these tests do) touches no boto3 / DynamoDB / S3.

What this task maps to here (design C6 / C4 / C3):

- **Publish path resolves REAL tenant values (C4 / Req 5.1):** ``get_application_publish_service()``
  injects a ``look_and_feel_reader`` into ``ApplicationPublishService`` — the SAME DynamoDB-backed
  ``MembersProjectionReader`` already wired as the slug / readiness / prefix reader — so the publish
  path resolves the stored ``look_and_feel`` slice and feeds it through Layer 2 into the renderer's
  ``branding=`` (closing the Req 5 defect). Its ``get_look_and_feel`` satisfies the
  ``LookAndFeelSettingsReader`` Protocol.
- **Layer-1 authoring service built with real seams (C3 / Req 8.1):** the new
  ``get_look_and_feel_settings_service()`` builds a ``LookAndFeelSettingsService`` over the real
  resolved-view reader (``MembersProjectionReader``) and the real Change-Op writer (the shared
  ``ConfigFieldsCrudService`` whose ``set_look_and_feel`` / ``remove_look_and_feel`` /
  ``copy_look_and_feel`` adapters satisfy ``LookAndFeelSettingsWriter``).
- **Lazy / warm-reuse / patchable (the accessor contract):** each accessor builds its service ONCE
  (module-global warm-reuse) and is replaceable by tests via the module-global / accessor patch —
  the documented injection seam the rest of the suite uses.

Validates: Requirements 5.1, 8.1 (spec 15)
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

from sam.members.domain.application_publish import ApplicationPublishService
from sam.members.domain.look_and_feel_settings_service import (
    LookAndFeelSettingsReader,
    LookAndFeelSettingsService,
    LookAndFeelSettingsWriter,
)
from sam.members.handler import _dispatch_services as dispatch_services
from sam.members.repository.projection_config_reader import MembersProjectionReader


@pytest.fixture(autouse=True)
def _reset_module_globals():
    """Reset the warm-reuse module globals around each test so builds are observed fresh.

    The accessors cache the built service in a module-global (``None`` until first use). A test
    that builds one would otherwise serve a stale (or another test's) instance to the next. Reset
    before AND after so each test observes a cold build and leaves no residue.
    """
    names = (
        "_APPLICATION_PUBLISH_SERVICE",
        "_LOOK_AND_FEEL_SETTINGS_SERVICE",
        "_CONFIG_FIELDS_CRUD_SERVICE",
    )
    for name in names:
        setattr(dispatch_services, name, None)
    yield
    for name in names:
        setattr(dispatch_services, name, None)


# ── Publish path gets the real look-and-feel reader (C4 / Req 5.1) ────────────────────


def test_publish_service_injects_look_and_feel_reader():
    """The publish service is built WITH a look_and_feel_reader (the Req 5 Layer-3 wiring).

    Building the service touches no AWS (the reader's table resolves lazily on first Query). The
    injected reader must be present (so publish resolves real stored values, not the renderer's
    fallback defaults) and be the DynamoDB-backed ``MembersProjectionReader`` whose
    ``get_look_and_feel`` satisfies the ``LookAndFeelSettingsReader`` Protocol.
    """
    service = dispatch_services.get_application_publish_service()

    assert isinstance(service, ApplicationPublishService)
    reader = service._look_and_feel_reader
    assert reader is not None, "publish must inject a look_and_feel_reader (Req 5.1)"
    assert isinstance(reader, MembersProjectionReader)
    # Satisfies the publish-side reader Protocol (duck-typed resolved-view read).
    assert callable(getattr(reader, "get_look_and_feel", None))


def test_publish_service_reuses_the_single_projection_reader():
    """The look_and_feel reader is the SAME reader used for slug / readiness / prefix.

    C6 reuses the ONE ``MembersProjectionReader`` the composition root already builds for the
    publish service's other read seams — so publish stays on a single resolved-view read and the
    wiring adds no new AWS egress.
    """
    service = dispatch_services.get_application_publish_service()

    assert service._look_and_feel_reader is service._slug_reader
    assert service._look_and_feel_reader is service._readiness
    assert service._look_and_feel_reader is service._prefix_reader


def test_publish_service_is_warm_reused():
    """The accessor builds the publish service once and reuses it on a warm invocation."""
    first = dispatch_services.get_application_publish_service()
    second = dispatch_services.get_application_publish_service()
    assert first is second


# ── Layer-1 authoring service built with the real reader + writer (C3 / Req 8.1) ──────


def test_look_and_feel_settings_service_built_with_real_seams():
    """The new accessor builds a LookAndFeelSettingsService over the real reader + writer.

    Building touches no AWS (both seams resolve their table lazily). The reader is the DynamoDB
    ``MembersProjectionReader`` (``get_look_and_feel`` → ``LookAndFeelSettingsReader``); the writer
    is the shared ``ConfigFieldsCrudService`` whose ``set_look_and_feel`` / ``remove_look_and_feel``
    / ``copy_look_and_feel`` adapters satisfy ``LookAndFeelSettingsWriter``.
    """
    service = dispatch_services.get_look_and_feel_settings_service()

    assert isinstance(service, LookAndFeelSettingsService)

    reader = service._reader
    writer = service._writer
    assert isinstance(reader, MembersProjectionReader)
    # Structural (Protocol) satisfaction of both injected seams — the real adapters, not fakes.
    assert isinstance(reader, LookAndFeelSettingsReader)
    assert isinstance(writer, LookAndFeelSettingsWriter)
    for method in ("set_look_and_feel", "remove_look_and_feel", "copy_look_and_feel"):
        assert callable(getattr(writer, method, None))


def test_look_and_feel_settings_service_writer_is_the_shared_crud_service():
    """The writer is the SAME shared config#fields Change-Op service the root builds once.

    Reusing ``get_config_fields_crud_service`` means the authoring write rides the existing
    version-conditional, path-scoped ``apply_ops`` Change-Op contract (and the shared
    ``StaleVersionError`` 409 path) — never a new write seam.
    """
    service = dispatch_services.get_look_and_feel_settings_service()
    assert service._writer is dispatch_services.get_config_fields_crud_service()


def test_look_and_feel_settings_service_is_warm_reused():
    """The accessor builds the settings service once and reuses it on a warm invocation."""
    first = dispatch_services.get_look_and_feel_settings_service()
    second = dispatch_services.get_look_and_feel_settings_service()
    assert first is second


def test_look_and_feel_settings_service_is_patchable(monkeypatch):
    """Tests can replace the accessor's result with an in-memory fake (the injection seam).

    The edge/dispatch resolves the service through this accessor, so patching the name routes the
    authoring path to a fake over in-memory seams — no AWS touched (the Static*Provider pattern).
    """
    sentinel = object()
    monkeypatch.setattr(
        dispatch_services, "get_look_and_feel_settings_service", lambda: sentinel
    )
    assert dispatch_services.get_look_and_feel_settings_service() is sentinel
