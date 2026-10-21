"""
Unit tests for the SAM config-write **domain service** (spec 02, Task 1.5).

Covers the ``fields`` AND ``scope`` branches of
:class:`sam.members.domain.config_write_service.ConfigWriteService`: the per-``configId``
body-validation seam, the no-``default_page_size`` rule (R7.2), verbatim per-field ``scope``
preservation (R7.3), the ``config#scope`` ``{dimensions:[…]}`` shape with empty=tenant-wide
(Task 3.3 / R8.1/R8.5), the row-level version stamp (R6.1), and delegation to the repository seam
with ``(tenant_id, config_id, attributes, version)``. The domain contains no boto3, so these tests
use an in-memory fake repository — no AWS, no DynamoDB. (``mail`` is wired in its own step, Task 5.)
"""

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

from sam.members.domain.config_write_service import (
    ConfigWriteService,
    ConfigWriteValidationError,
)

_TENANT = "h-dcn"


class FakeWriteRepository:
    """In-memory stand-in for ``MembersConfigWriteRepository`` — records the put, no I/O."""

    def __init__(self):
        self.calls = []

    def put_config(self, tenant_id, config_id, attributes, version):
        item = {
            "tenant_id": tenant_id,
            "config_id": config_id,
            "version": version,
            **attributes,
        }
        self.calls.append(
            {
                "tenant_id": tenant_id,
                "config_id": config_id,
                "attributes": attributes,
                "version": version,
            }
        )
        return item


def _service(repo=None, version="2026-10-12T00:00:00+00:00"):
    return ConfigWriteService(repo or FakeWriteRepository(), version_fn=lambda: version)


# ── happy path: shape + stamp + delegate ────────────────────────────────────────────────


def test_put_config_fields_delegates_shaped_attributes_and_version():
    repo = FakeWriteRepository()
    svc = _service(repo, version="2026-10-12T09:00:00+00:00")
    body = {
        "fields": {"nickname": {"key": "nickname", "type": "string"}},
        "overrides": {"membership.member_number": {"visible": False}},
        "functional_groups": [
            {"key": "contact", "label": {"en": "Contact"}, "order": 1}
        ],
    }

    result = svc.put_config(_TENANT, "fields", body)

    assert result == {
        "success": True,
        "configId": "fields",
        "version": "2026-10-12T09:00:00+00:00",
    }
    assert len(repo.calls) == 1
    call = repo.calls[0]
    assert call["tenant_id"] == _TENANT
    assert call["config_id"] == "fields"
    assert call["version"] == "2026-10-12T09:00:00+00:00"
    assert set(call["attributes"]) == {"fields", "overrides", "functional_groups"}


def test_put_config_fields_empty_body_authors_empty_containers():
    repo = FakeWriteRepository()
    _service(repo).put_config(_TENANT, "fields", {})
    assert repo.calls[0]["attributes"] == {
        "fields": {},
        "overrides": {},
        "functional_groups": [],
    }


# ── R7.2: default_page_size is RETIRED — never authored ──────────────────────────────────


def test_put_config_fields_never_authors_default_page_size():
    repo = FakeWriteRepository()
    body = {"fields": {}, "overrides": {}, "default_page_size": 100}
    _service(repo).put_config(_TENANT, "fields", body)
    assert "default_page_size" not in repo.calls[0]["attributes"]


# ── R7.3: per-field scope preserved verbatim ─────────────────────────────────────────────


def test_put_config_fields_preserves_per_field_scope_verbatim():
    repo = FakeWriteRepository()
    scope = {
        "enabled": True,
        "values": ["Noord", "Zuid"],
        "required_for": ["Members_CRUD"],
    }
    body = {"fields": {"region": {"key": "region", "type": "enum", "scope": scope}}}

    _service(repo).put_config(_TENANT, "fields", body)

    written = repo.calls[0]["attributes"]["fields"]["region"]["scope"]
    assert written == scope


def test_put_config_fields_preserves_override_scope_verbatim():
    repo = FakeWriteRepository()
    scope = {"enabled": True, "values": ["A"]}
    body = {"overrides": {"membership.member_number": {"scope": scope}}}

    _service(repo).put_config(_TENANT, "fields", body)

    written = repo.calls[0]["attributes"]["overrides"]["membership.member_number"][
        "scope"
    ]
    assert written == scope


# ── validation: malformed body raises a caller-safe ConfigWriteValidationError ────────────


@pytest.mark.parametrize(
    "body",
    [
        {"fields": []},
        {"fields": {"x": "not-a-mapping"}},
        {"overrides": "nope"},
        {"functional_groups": {"not": "a-list"}},
        {"functional_groups": [{"label": {"en": "no key"}}]},
        {"functional_groups": [{"key": "  "}]},
    ],
)
def test_put_config_fields_malformed_body_raises_validation_error(body):
    repo = FakeWriteRepository()
    with pytest.raises(ConfigWriteValidationError):
        _service(repo).put_config(_TENANT, "fields", body)
    assert repo.calls == []  # nothing persisted on a validation failure


def test_put_config_all_three_sam_owned_ids_are_wired():
    """All three closed-set ids have a wired validator now: fields (1.5), scope (3.3), mail (5.1).
    None reaches the defensive 'no validator wired' branch — each writes its own shaped row."""
    for config_id in ("fields", "scope", "mail"):
        repo = FakeWriteRepository()
        _service(repo).put_config(_TENANT, config_id, {})
        assert repo.calls[0]["config_id"] == config_id


def test_put_config_truly_unknown_id_raises_before_persist():
    """Defense in depth: an id with NO wired validator (the edge rejects these first, so this is
    unreachable in normal flow) still fails loudly and writes nothing."""
    repo = FakeWriteRepository()
    with pytest.raises(ValueError):
        _service(repo).put_config(_TENANT, "views", {})
    assert repo.calls == []


# ── version stamp: monotonic via the real minter ─────────────────────────────────────────


def test_put_config_uses_injected_version_and_is_monotonic():
    repo = FakeWriteRepository()
    stamps = iter(["2026-01-01T00:00:00+00:00", "2026-01-02T00:00:00+00:00"])
    svc = ConfigWriteService(repo, version_fn=lambda: next(stamps))

    svc.put_config(_TENANT, "fields", {})
    svc.put_config(_TENANT, "fields", {})

    v1, v2 = repo.calls[0]["version"], repo.calls[1]["version"]
    assert v1 < v2  # a later write yields a lexicographically-greater stamp


# ── fixed_overrides INPUT ALIAS → canonical overrides (data-loss regression, findings.md) ──
#
# The frontend field_overlay object (and the legacy Flask build_config_fields_row builder) author
# the fixed-field override map under the key ``fixed_overrides``, while the SAM row's canonical
# attribute — what MembersProjectionReader.get_overlay reads — is ``overrides``. A live TEST save
# proved that an alias-only body silently persisted ZERO overrides, wiping membership.status /
# personal.* (the config#fields data-loss bug). The write service now accepts the alias and
# normalizes it to ``overrides``; these pin that contract.


def test_put_config_fields_accepts_fixed_overrides_alias():
    """A body authoring fixed-field overrides under ``fixed_overrides`` writes them to ``overrides``."""
    repo = FakeWriteRepository()
    body = {
        "fields": {"motor_brand": {"type": "string"}},
        "fixed_overrides": {
            "membership.status": {"type": "enum", "functional_group": "membership"},
            "personal.first_name": {"required": True},
        },
    }

    _service(repo).put_config(_TENANT, "fields", body)

    attrs = repo.calls[0]["attributes"]
    assert set(attrs["overrides"]) == {"membership.status", "personal.first_name"}
    # The alias key is NOT carried onto the stored row — only the canonical ``overrides`` is.
    assert "fixed_overrides" not in attrs


def test_put_config_fields_canonical_overrides_wins_over_alias():
    """If a body carries BOTH keys, the canonical ``overrides`` wins and the alias is ignored."""
    repo = FakeWriteRepository()
    body = {
        "overrides": {"membership.status": {"type": "enum"}},
        "fixed_overrides": {"personal.city": {"functional_group": "address"}},
    }

    _service(repo).put_config(_TENANT, "fields", body)

    assert set(repo.calls[0]["attributes"]["overrides"]) == {"membership.status"}


def test_put_config_fields_alias_preserves_override_scope_verbatim():
    """A per-override ``scope`` rides through the alias verbatim (R7.3)."""
    repo = FakeWriteRepository()
    scope = {"enabled": True, "values": ["A"]}
    body = {"fixed_overrides": {"membership.region": {"scope": scope}}}

    _service(repo).put_config(_TENANT, "fields", body)

    assert (
        repo.calls[0]["attributes"]["overrides"]["membership.region"]["scope"] == scope
    )


# ── config#scope branch (Task 3.3 / R8) — the service path PUT /members/config/scope relies on ──
#
# These exercise the FULL service validator seam for `scope` (not the repository-direct round-trip
# of test_scope_equivalence_props.py): a well-shaped `{dimensions:[…]}` body is shaped + stamped +
# delegated; empty/absent dimensions author a tenant-wide row; a malformed body raises a caller-safe
# ConfigWriteValidationError and persists nothing. Without the wired validator (the gap found in
# the task-3 reconciliation) PUT /members/config/scope 500s — these pin it working end-to-service.


def test_put_config_scope_delegates_shaped_dimensions_and_version():
    repo = FakeWriteRepository()
    svc = _service(repo, version="2026-10-20T09:00:00+00:00")
    dim = {
        "key": "region",
        "field": "region",
        "enabled": True,
        "values": ["Noord", "Zuid"],
        "label": {"nl": "Regio", "en": "Region"},
        "required_for": ["Members_CRUD"],
    }

    result = svc.put_config(_TENANT, "scope", {"dimensions": [dim]})

    assert result == {
        "success": True,
        "configId": "scope",
        "version": "2026-10-20T09:00:00+00:00",
    }
    assert len(repo.calls) == 1
    call = repo.calls[0]
    assert call["config_id"] == "scope"
    # The dimension spec rides through verbatim — the reader maps it onto a ScopeDimension 1:1.
    assert call["attributes"] == {"dimensions": [dim]}


def test_put_config_scope_empty_dimensions_is_tenant_wide():
    """R8.5/R1.6: an empty (or absent) dimensions list authors a valid tenant-wide row."""
    repo = FakeWriteRepository()
    _service(repo).put_config(_TENANT, "scope", {"dimensions": []})
    assert repo.calls[0]["attributes"] == {"dimensions": []}

    repo2 = FakeWriteRepository()
    _service(repo2).put_config(_TENANT, "scope", {})  # absent → []
    assert repo2.calls[0]["attributes"] == {"dimensions": []}


def test_put_config_scope_never_authors_wildcard_or_multivalued():
    """s5d clean break (R8.1): the service passes specs through, never adding all_wildcard /
    multi_valued keys the resolver long ago removed."""
    repo = FakeWriteRepository()
    _service(repo).put_config(
        _TENANT, "scope", {"dimensions": [{"key": "region", "values": ["A"]}]}
    )
    written = repo.calls[0]["attributes"]["dimensions"][0]
    assert "all_wildcard" not in written
    assert "multi_valued" not in written


@pytest.mark.parametrize(
    "body",
    [
        {"dimensions": "not-a-list"},
        {"dimensions": {"not": "a-list"}},
        {"dimensions": ["not-a-mapping"]},
        {"dimensions": [{"key": "region"}, 123]},
        "not-an-object",
        123,
    ],
)
def test_put_config_scope_malformed_body_raises_validation_error(body):
    repo = FakeWriteRepository()
    with pytest.raises(ConfigWriteValidationError):
        _service(repo).put_config(_TENANT, "scope", body)
    assert repo.calls == []  # nothing persisted on a validation failure


# ── config#mail branch (Task 5.1 / Requirement 9) — the service path PUT /members/config/mail ──
#
# Shape + fail-closed discipline for the mail scalars the reader's accessors read back:
# mail_enabled / mail_certified / application_scope_copy (bool, only explicit True), mail_local_part
# (default noreply), mail_domain (NO safe default — omit when blank), mail_reply_to_default (NEW,
# optional — omit when blank), consent_notice (well-formed shape or omit). Mirrors the Flask
# build_config_mail_row so writer and builder cannot drift.


def test_put_config_mail_shapes_the_reader_attributes_and_stamps_version():
    repo = FakeWriteRepository()
    svc = _service(repo, version="2026-10-20T11:00:00+00:00")
    body = {
        "mail_enabled": True,
        "mail_certified": True,
        "application_scope_copy": True,
        "mail_domain": "h-dcn.nl",
        "mail_local_part": "info",
        "mail_reply_to_default": "reply@h-dcn.nl",
    }

    result = svc.put_config(_TENANT, "mail", body)

    assert result == {
        "success": True,
        "configId": "mail",
        "version": "2026-10-20T11:00:00+00:00",
    }
    attrs = repo.calls[0]["attributes"]
    assert attrs["mail_enabled"] is True
    assert attrs["mail_certified"] is True
    assert attrs["application_scope_copy"] is True
    assert attrs["mail_domain"] == "h-dcn.nl"
    assert attrs["mail_local_part"] == "info"
    assert attrs["mail_reply_to_default"] == "reply@h-dcn.nl"


def test_put_config_mail_gates_are_fail_closed():
    """Only an explicit boolean True opens a gate — truthy non-True collapses to False (R0/R5.2)."""
    repo = FakeWriteRepository()
    body = {
        "mail_enabled": "true",
        "mail_certified": 1,
        "application_scope_copy": "yes",
    }
    _service(repo).put_config(_TENANT, "mail", body)
    attrs = repo.calls[0]["attributes"]
    assert attrs["mail_enabled"] is False
    assert attrs["mail_certified"] is False
    assert attrs["application_scope_copy"] is False


def test_put_config_mail_empty_body_is_fail_closed_defaults():
    """An empty body authors fail-closed gates + the noreply local-part, no domain/reply-to."""
    repo = FakeWriteRepository()
    _service(repo).put_config(_TENANT, "mail", {})
    attrs = repo.calls[0]["attributes"]
    assert attrs["mail_enabled"] is False
    assert attrs["mail_certified"] is False
    assert attrs["mail_local_part"] == "noreply"
    assert "mail_domain" not in attrs
    assert "mail_reply_to_default" not in attrs
    assert "consent_notice" not in attrs


def test_put_config_mail_domain_omitted_when_blank_no_safe_default():
    """R4.2: a blank/non-string domain is OMITTED (never a guessed host) — reader → None."""
    for bad in ("", "   ", None, 123):
        repo = FakeWriteRepository()
        _service(repo).put_config(_TENANT, "mail", {"mail_domain": bad})
        assert "mail_domain" not in repo.calls[0]["attributes"]


def test_put_config_mail_reply_to_default_omitted_when_blank():
    """mail_reply_to_default is optional — omitted when blank so the send path falls back to From."""
    for bad in ("", "  ", None):
        repo = FakeWriteRepository()
        _service(repo).put_config(_TENANT, "mail", {"mail_reply_to_default": bad})
        assert "mail_reply_to_default" not in repo.calls[0]["attributes"]


def test_put_config_mail_local_part_defaults_to_noreply_when_blank():
    for bad in ("", "   ", None, 5):
        repo = FakeWriteRepository()
        _service(repo).put_config(_TENANT, "mail", {"mail_local_part": bad})
        assert repo.calls[0]["attributes"]["mail_local_part"] == "noreply"


def test_put_config_mail_consent_notice_shaped_when_well_formed():
    repo = FakeWriteRepository()
    notice = {"version": "v1", "text": {"nl": "Akkoord", "en": "Consent", "de": "  "}}
    _service(repo).put_config(_TENANT, "mail", {"consent_notice": notice})
    written = repo.calls[0]["attributes"]["consent_notice"]
    # Blank locale dropped; well-formed version + non-blank locales kept.
    assert written == {"version": "v1", "text": {"nl": "Akkoord", "en": "Consent"}}


def test_put_config_mail_consent_notice_omitted_when_malformed():
    """A malformed consent notice (no version, blank text, non-mapping) is OMITTED (R12.1)."""
    for bad in (
        {"text": {"nl": "x"}},  # no version
        {"version": "v1"},  # no text
        {"version": "v1", "text": {}},  # empty text
        {"version": "  ", "text": {"nl": "x"}},  # blank version
        {"version": True, "text": {"nl": "x"}},  # bool version rejected
        "not-a-mapping",
    ):
        repo = FakeWriteRepository()
        _service(repo).put_config(_TENANT, "mail", {"consent_notice": bad})
        assert "consent_notice" not in repo.calls[0]["attributes"]


def test_put_config_mail_non_object_body_raises_validation_error():
    repo = FakeWriteRepository()
    with pytest.raises(ConfigWriteValidationError):
        _service(repo).put_config(_TENANT, "mail", "not-an-object")
    assert repo.calls == []
