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


def test_put_config_unwired_config_id_raises_before_persist():
    repo = FakeWriteRepository()
    # The `mail` validator is not wired yet (Task 5) — fail loudly, write nothing. (`scope` IS
    # wired as of Task 3.3; `fields` since Task 1.5.)
    with pytest.raises(ValueError):
        _service(repo).put_config(_TENANT, "mail", {})
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
