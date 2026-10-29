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
        # LIST→MAP migration (spec 03, design C6): a legacy LIST body is still accepted on the wire
        # and normalized to the canonical MAP the reader now dual-reads (review Must-fix #4).
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
    # The three overlay slices PLUS the spec-12 form-slug attributes (slug + publish-state),
    # authored on every fields write (Task 1.1 / R4.2).
    assert set(call["attributes"]) == {
        "fields",
        "overrides",
        "functional_groups",
        "slug",
        "published_at",
        "published_version",
    }
    # No slug/publish-state in the body + no reader → all three carry through as None.
    assert call["attributes"]["slug"] is None
    assert call["attributes"]["published_at"] is None
    assert call["attributes"]["published_version"] is None
    # functional_groups is AUTHORED as a MAP keyed by group key (spec 03, design C6 / D2a) even
    # when the body arrives as a legacy LIST — a write never regresses a row to the LIST shape.
    assert call["attributes"]["functional_groups"] == {
        "contact": {"key": "contact", "label": {"en": "Contact"}, "order": 1}
    }


def test_put_config_fields_empty_body_authors_empty_containers():
    repo = FakeWriteRepository()
    _service(repo).put_config(_TENANT, "fields", {})
    assert repo.calls[0]["attributes"] == {
        "fields": {},
        "overrides": {},
        # Empty catalog is a MAP now (spec 03, design C6): `{}`, not `[]`.
        "functional_groups": {},
        # spec 12 Task 1.1: slug + publish-state default to None when absent and no reader wired.
        "slug": None,
        "published_at": None,
        "published_version": None,
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
        # functional_groups: a scalar is not a valid catalog shape (neither MAP nor LIST).
        {"functional_groups": "not-a-catalog"},
        # MAP shape (spec 03): an entry that is not an object is malformed.
        {"functional_groups": {"contact": "not-an-object"}},
        # LIST shape (legacy, still accepted): a keyless / blank-key entry is malformed.
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


def test_put_config_mail_consent_notice_intended_but_malformed_raises_validation_error():
    """R8.2: an INTENDED-but-malformed consent notice (key present and non-empty, but no version,
    blank text, or non-mapping) is REJECTED fail-loud rather than silently omitted — an admin's
    broken notice surfaces instead of vanishing."""
    for bad in (
        {"text": {"nl": "x"}},  # no version
        {"version": "v1"},  # no text
        {"version": "v1", "text": {}},  # empty text
        {"version": "  ", "text": {"nl": "x"}},  # blank version
        {"version": True, "text": {"nl": "x"}},  # bool version rejected
        {"version": "v1", "text": {"nl": "  ", "en": ""}},  # all-blank locale text
        "not-a-mapping",
    ):
        repo = FakeWriteRepository()
        with pytest.raises(ConfigWriteValidationError):
            _service(repo).put_config(_TENANT, "mail", {"consent_notice": bad})
        assert repo.calls == []  # nothing persisted on a validation failure


def test_put_config_mail_absent_consent_notice_writes_nothing_back_compatible():
    """R8.2: a truly ABSENT notice (key omitted, or an empty/falsey value carrying no authoring
    intent) writes nothing and does NOT raise — back-compatible with the pre-R8.2 behavior."""
    for absent in (
        {},  # key omitted entirely
        {"consent_notice": None},
        {"consent_notice": {}},  # empty mapping = no intent
        {"consent_notice": ""},
    ):
        repo = FakeWriteRepository()
        _service(repo).put_config(_TENANT, "mail", absent)
        assert "consent_notice" not in repo.calls[0]["attributes"]


def test_put_config_mail_embed_origins_shaped_when_well_formed():
    """R5.2: a list of non-blank origin strings is trimmed + de-duplicated (order preserved) and
    stored as the ONE `application_embed_origins` list that later feeds BOTH frame-ancestors and
    the SAM public API CORS."""
    repo = FakeWriteRepository()
    body = {
        "application_embed_origins": [
            "https://aanmelden.jabaki.nl",
            "  https://members.h-dcn.nl  ",  # trimmed
            "https://aanmelden.jabaki.nl",  # duplicate dropped
        ]
    }
    _service(repo).put_config(_TENANT, "mail", body)
    assert repo.calls[0]["attributes"]["application_embed_origins"] == [
        "https://aanmelden.jabaki.nl",
        "https://members.h-dcn.nl",
    ]


def test_put_config_mail_embed_origins_accepts_confirmed_v1_targets():
    """R5.2/R9.2: the two CONFIRMED v1 external embed targets — a Google Site
    (`https://sites.google.com`) and the h-dcn event portal (`https://portal.h-dcn.nl`) — are
    accepted verbatim (order preserved) by the write path, the one list that then feeds BOTH the
    CloudFront frame-ancestors KVS and the SAM public-API CORS."""
    repo = FakeWriteRepository()
    body = {
        "application_embed_origins": [
            "https://sites.google.com",
            "https://portal.h-dcn.nl",
        ]
    }
    _service(repo).put_config(_TENANT, "mail", body)
    assert repo.calls[0]["attributes"]["application_embed_origins"] == [
        "https://sites.google.com",
        "https://portal.h-dcn.nl",
    ]


def test_put_config_mail_embed_origins_absent_or_empty_writes_nothing_back_compatible():
    """R5.2: absent / empty origins is back-compatible (standalone, no embed) — writes nothing and
    does NOT raise, mirroring mail_domain / mail_reply_to_default omission."""
    for absent in (
        {},  # key omitted entirely
        {"application_embed_origins": None},
        {"application_embed_origins": []},
    ):
        repo = FakeWriteRepository()
        _service(repo).put_config(_TENANT, "mail", absent)
        assert "application_embed_origins" not in repo.calls[0]["attributes"]


def test_put_config_mail_embed_origins_malformed_raises_validation_error():
    """R5.2/R8: a malformed embed-origins list (non-list, or a non-string / blank-only entry) is
    REJECTED fail-loud rather than silently becoming 'standalone' — nothing is persisted."""
    for bad in (
        "https://one-origin",  # non-list
        {"a": "b"},  # non-list mapping
        ["https://ok", ""],  # blank entry
        ["https://ok", "   "],  # blank-only entry
        ["https://ok", 123],  # non-string entry
        ["https://ok", None],  # None entry
    ):
        repo = FakeWriteRepository()
        with pytest.raises(ConfigWriteValidationError):
            _service(repo).put_config(
                _TENANT, "mail", {"application_embed_origins": bad}
            )
        assert repo.calls == []  # nothing persisted on a validation failure


def test_put_config_mail_non_object_body_raises_validation_error():
    repo = FakeWriteRepository()
    with pytest.raises(ConfigWriteValidationError):
        _service(repo).put_config(_TENANT, "mail", "not-an-object")
    assert repo.calls == []


# ── Per-field APPLICATION-attribute hardening (Task 1.1 / Task 1.4 / Requirement 8) ──────
#
# The SAM write path is now the AUTHORITATIVE author of the four per-field application
# attributes (the Flask `_validate_application_attrs` guard is off the authoring path, R8.4).
# `_validate_fields_body` → `_validate_application_attributes` re-checks, over BOTH `fields`
# (variable overlay) and `overrides` (fixed-field) specs, the remaining write-time invariants:
#   R8.1a  application_choices ⊆ the field's own resolved choices (options[].value / choices)
#   R8.1b  format is a well-formed {checker, params?} whose checker ∈ field_formats.known_tokens()
# A violation raises ONE caller-safe ConfigWriteValidationError keyed to the offending field and
# persists NOTHING; a coherent body still writes; a tenant that authors no app attrs writes the
# back-compatible defaults unchanged (R9.2).
#
# The former R8.1c no-relax invariant (application_required=False could not relax a PLATFORM-
# required field) was a Hardcoded_Binding that OVERRULED the admin and is REMOVED (03b Req 1.1/1.4):
# the admin now freely sets application-requiredness for ANY field. The tests below assert the
# removal — a relax on a platform-required field now WRITES.

from sam.members.domain import field_formats

# A platform-required fixed field (fixed_fields: membership.status / .membership_type /
# .joined_date and personal.last_name are required=True). After 03b Req 1 a relax on it is allowed.
_PLATFORM_REQUIRED_KEY = "membership.status"
# A platform-OPTIONAL fixed field (required=False).
_PLATFORM_OPTIONAL_KEY = "personal.first_name"


def _enum_field_spec(values, **extra):
    """A variable overlay enum field declaring ``values`` as its own choices (via ``options``)."""
    return {
        "key": extra.pop("key", "region"),
        "type": "enum",
        "options": [{"value": v, "label": {"en": v}} for v in values],
        **extra,
    }


# ── R8.1a: application_choices ⊆ the field's own choices ──────────────────────────────────


def test_validate_application_attributes_subset_not_in_choices_raises_and_persists_nothing():
    """R8.1a: an application_choices entry that is not one of the field's own choices is rejected,
    keyed to the offending field, and nothing is persisted."""
    repo = FakeWriteRepository()
    body = {
        "fields": {
            "region": _enum_field_spec(
                ["Noord", "Zuid"], application_choices=["Noord", "Oost"]
            )
        }
    }
    with pytest.raises(ConfigWriteValidationError) as exc:
        _service(repo).put_config(_TENANT, "fields", body)
    # Keyed to the offending field (dotted overlay form) and names the bad value (R8.3).
    assert "overlay.region" in str(exc.value)
    assert "Oost" in str(exc.value)
    assert repo.calls == []


def test_validate_application_attributes_subset_on_field_without_choices_raises():
    """R8.1a: a subset on a field that declares NO choices (not an enum / value-less) is a write
    error — you cannot subset a field that has no choice vocabulary."""
    repo = FakeWriteRepository()
    body = {
        "fields": {
            "nickname": {
                "key": "nickname",
                "type": "string",
                "application_choices": ["anything"],
            }
        }
    }
    with pytest.raises(ConfigWriteValidationError) as exc:
        _service(repo).put_config(_TENANT, "fields", body)
    assert "overlay.nickname" in str(exc.value)
    assert repo.calls == []


def test_validate_application_attributes_non_list_subset_raises():
    """R8.1a: a present application_choices that is not a list is rejected."""
    repo = FakeWriteRepository()
    body = {
        "fields": {"region": _enum_field_spec(["Noord"], application_choices="Noord")}
    }
    with pytest.raises(ConfigWriteValidationError) as exc:
        _service(repo).put_config(_TENANT, "fields", body)
    assert "overlay.region" in str(exc.value)
    assert "must be a list" in str(exc.value)
    assert repo.calls == []


def test_validate_application_attributes_subset_vocabulary_read_from_options_only():
    """R8.1a / F12 (03a C2): the subset-validation vocabulary is read from the ONE canonical
    ``options`` list ONLY — a subset ⊆ the field's ``options`` writes.

    The retired bare-``choices`` fallback is covered by the companion test below; here the happy
    path confirms ``options`` is the single source the subset validates against."""
    repo = FakeWriteRepository()
    body = {
        "fields": {
            "region": _enum_field_spec(
                ["Noord", "Zuid", "Oost"], application_choices=["Noord", "Zuid"]
            )
        }
    }
    _service(repo).put_config(_TENANT, "fields", body)
    written = repo.calls[0]["attributes"]["fields"]["region"]
    assert written["application_choices"] == ["Noord", "Zuid"]


def test_validate_application_attributes_bare_choices_no_longer_supplies_subset_vocabulary():
    """F12 (03a C2, N2): the write-side subset validator reads ``options`` ONLY — the legacy
    ``options or choices`` coalesce is RETIRED. A field declaring its vocabulary under the bare
    ``choices`` name (no ``options``) now resolves NO usable subset vocabulary, so an
    ``application_choices`` subset on it is a write error (you cannot subset a field that has no
    ``options``) — exactly the "no silent fallback" behaviour 03a enforces. C7 migrates any live
    bare-``choices`` row into ``options`` and C2 drops ``choices`` on the write, so this path is
    dead for real data."""
    repo = FakeWriteRepository()
    body = {
        "fields": {
            "region": {
                "key": "region",
                "type": "enum",
                "choices": ["Noord", "Zuid", "Oost"],
                "application_choices": ["Noord", "Zuid"],
            }
        }
    }
    with pytest.raises(ConfigWriteValidationError) as exc:
        _service(repo).put_config(_TENANT, "fields", body)
    assert "overlay.region" in str(exc.value)
    assert repo.calls == []


# ── R8.1b: format must be a well-formed {checker, params?} with a known checker ───────────


def test_validate_application_attributes_unknown_checker_raises_and_persists_nothing():
    """R8.1b: a format.checker that is not a platform-known token is rejected, keyed to the field;
    the error names the known token set and nothing persists."""
    repo = FakeWriteRepository()
    body = {
        "fields": {
            "iban_field": {
                "key": "iban_field",
                "type": "string",
                "format": {"checker": "PHONE"},
            }
        }
    }
    with pytest.raises(ConfigWriteValidationError) as exc:
        _service(repo).put_config(_TENANT, "fields", body)
    assert "overlay.iban_field" in str(exc.value)
    assert "PHONE" in str(exc.value)
    assert repo.calls == []


@pytest.mark.parametrize(
    "bad_format",
    [
        "EMAIL",  # a bare token string, not a {checker,...} mapping
        [],  # non-mapping
        {},  # missing checker
        {"checker": ""},  # empty checker
        {"checker": None},  # non-string checker
        {"params": {"x": 1}},  # params but no checker
    ],
)
def test_validate_application_attributes_malformed_format_raises(bad_format):
    """R8.1b: a format that is not a well-formed {checker, params?} object (non-mapping, missing or
    empty/non-string checker) is rejected and nothing persists."""
    repo = FakeWriteRepository()
    body = {"fields": {"f": {"key": "f", "type": "string", "format": bad_format}}}
    with pytest.raises(ConfigWriteValidationError):
        _service(repo).put_config(_TENANT, "fields", body)
    assert repo.calls == []


def test_validate_application_attributes_known_checker_accepted():
    """R8.1b (happy): every platform-known token (EMAIL, IBAN, …) is accepted and written verbatim,
    including its params — the test derives the token set from the registry so a new token is
    covered automatically."""
    for token in sorted(field_formats.known_tokens()):
        repo = FakeWriteRepository()
        fmt = {"checker": token, "params": {"strict": True}}
        body = {"fields": {"f": {"key": "f", "type": "string", "format": fmt}}}
        _service(repo).put_config(_TENANT, "fields", body)
        assert repo.calls[0]["attributes"]["fields"]["f"]["format"] == fmt


# ── 03b Req 1: the no-relax binding is REMOVED — a relax now WRITES ───────────────────────


def test_validate_application_attributes_relax_platform_required_override_now_writes():
    """03b Req 1.1/1.4: application_required=False on a PLATFORM-required fixed field (via
    overrides) is NO LONGER rejected — the former no-relax Hardcoded_Binding overruled the admin
    and is removed, so the admin freely turns it off and the write persists verbatim."""
    repo = FakeWriteRepository()
    body = {
        "overrides": {
            _PLATFORM_REQUIRED_KEY: {
                "application_visible": True,
                "application_required": False,
            }
        }
    }
    _service(repo).put_config(_TENANT, "fields", body)
    overrides = repo.calls[0]["attributes"]["overrides"]
    assert overrides[_PLATFORM_REQUIRED_KEY]["application_required"] is False


def test_validate_application_attributes_tighten_platform_optional_override_accepted():
    """The admin may set application-requiredness either way on any field (03b Req 1):
    application_required=True on one field and =False on another both write."""
    repo = FakeWriteRepository()
    body = {
        "overrides": {
            _PLATFORM_OPTIONAL_KEY: {"application_required": True},
            "personal.phone": {"application_required": False},
        }
    }
    _service(repo).put_config(_TENANT, "fields", body)
    overrides = repo.calls[0]["attributes"]["overrides"]
    assert overrides[_PLATFORM_OPTIONAL_KEY]["application_required"] is True
    assert overrides["personal.phone"]["application_required"] is False


def test_validate_application_attributes_variable_field_required_false_accepted():
    """A VARIABLE overlay field's application_required=False writes (03b Req 1 — no binding)."""
    repo = FakeWriteRepository()
    body = {
        "fields": {
            "nickname": {
                "key": "nickname",
                "type": "string",
                "application_required": False,
            }
        }
    }
    _service(repo).put_config(_TENANT, "fields", body)
    assert (
        repo.calls[0]["attributes"]["fields"]["nickname"]["application_required"]
        is False
    )


# ── Property 3 (Task 3.2): the admin is AUTHORITATIVE at the write seam too ───────────────
#
# Req 1.1/1.2/1.4 + design Property 3: "For any field other than member_id, no save is rejected
# on a cross-field binding the admin did not author." The single-field relax above
# (`test_validate_application_attributes_relax_platform_required_override_now_writes`) is ONE
# instance; these lock the guarantee HOLISTICALLY at the config-write seam:
#   - application_required=False is accepted on EVERY platform-required fixed field at once;
#   - Req 1.3: the write seam enforces NO requiredness floor of its own — the only intrinsic
#     invariant is member_id (the system UUID, not a tenant config field, so it never reaches this
#     seam). A tenant may relax the application-requiredness of every configurable required field.

# The platform-required fixed fields (required=True in the registry) authored via overrides. Read
# from the registry so a future base required-ness change is covered automatically.
from sam.members.domain.fixed_fields import FIXED_FIELDS as _FIXED_FIELDS

_ALL_PLATFORM_REQUIRED_DOTTED = tuple(
    f.dotted_key() for f in _FIXED_FIELDS if f.required
)


def test_option_relax_application_required_on_every_platform_required_field_writes():
    """Property 3 (Req 1.1/1.2/1.4): a SINGLE write setting application_required=False on EVERY
    platform-required fixed field (last_name, status, membership_type, joined_date) is accepted —
    no field retains a hardcoded no-relax binding. The write persists the explicit False for each,
    and `membership.membership_type` (a required reference) keeps a valid option set so the
    R3.4a well-formedness rule is satisfied while it is relaxed (that rule is orthogonal to the
    removed no-relax binding)."""
    assert _ALL_PLATFORM_REQUIRED_DOTTED  # guard: the registry still has required fixed fields
    repo = FakeWriteRepository()
    overrides = {}
    for dotted in _ALL_PLATFORM_REQUIRED_DOTTED:
        spec = {"application_visible": True, "application_required": False}
        # membership_type is a required enum reference — keep ≥1 allowed option (R3.4a) so the
        # write is rejected ONLY if a no-relax binding were (wrongly) still present, never on the
        # orthogonal option-integrity rule.
        if dotted == "membership.membership_type":
            spec["options"] = [{"value": "gewoon_lid", "label": {"en": "Member"}}]
        overrides[dotted] = spec
    _service(repo).put_config(_TENANT, "fields", {"overrides": overrides})
    written = repo.calls[0]["attributes"]["overrides"]
    for dotted in _ALL_PLATFORM_REQUIRED_DOTTED:
        assert written[dotted]["application_required"] is False, (
            f"the write seam rejected or dropped a relax on {dotted!r} — a no-relax "
            f"Hardcoded_Binding has been re-introduced (03b Req 1)"
        )


def test_option_admin_sets_application_requiredness_both_ways_in_one_write():
    """Req 1 (both axes): in one coherent write the admin tightens one field (optional→required)
    and relaxes another platform-required field (required→optional); both persist verbatim — the
    write seam obeys the admin's authored requiredness, imposing none of its own (Req 1.3)."""
    repo = FakeWriteRepository()
    body = {
        "overrides": {
            _PLATFORM_OPTIONAL_KEY: {
                "application_visible": True,
                "application_required": True,  # tighten a platform-OPTIONAL field
            },
            _PLATFORM_REQUIRED_KEY: {
                "application_visible": True,
                "application_required": False,  # relax a platform-REQUIRED field
            },
        }
    }
    _service(repo).put_config(_TENANT, "fields", body)
    overrides = repo.calls[0]["attributes"]["overrides"]
    assert overrides[_PLATFORM_OPTIONAL_KEY]["application_required"] is True
    assert overrides[_PLATFORM_REQUIRED_KEY]["application_required"] is False


# ── Collection: every offending field reported in ONE error ───────────────────────────────


def test_validate_application_attributes_collects_all_offending_fields_in_one_error():
    """R8.3: violations across BOTH fields and overrides are collected into ONE error naming every
    offending field (not just the first); nothing persists. (The no-relax binding is gone — 03b
    Req 1 — so the collected violations are the remaining well-formedness ones: bad subset / bad
    checker on a variable field and a malformed format on an override.)"""
    repo = FakeWriteRepository()
    body = {
        "fields": {
            "region": _enum_field_spec(
                ["Noord"], application_choices=["Oost"]
            ),  # bad subset
            "f": {
                "key": "f",
                "type": "string",
                "format": {"checker": "NOPE"},
            },  # bad checker
        },
        "overrides": {
            _PLATFORM_OPTIONAL_KEY: {"format": {"checker": "ALSO_NOPE"}},  # bad checker
        },
    }
    with pytest.raises(ConfigWriteValidationError) as exc:
        _service(repo).put_config(_TENANT, "fields", body)
    message = str(exc.value)
    assert "overlay.region" in message
    assert "overlay.f" in message
    assert _PLATFORM_OPTIONAL_KEY in message
    assert repo.calls == []


# ── Happy path: a coherent config#fields body still writes (R9.2) ─────────────────────────


def test_validate_application_attributes_coherent_body_writes_all_four_attributes():
    """R9.2 (happy): a coherent body — a valid enum subset, a known checker, a valid tighten, and
    application_visible — writes through unchanged (one object, one save)."""
    repo = FakeWriteRepository()
    body = {
        "fields": {
            "region": _enum_field_spec(
                ["Noord", "Zuid", "Oost"],
                application_visible=True,
                application_required=True,
                application_choices=["Noord", "Zuid"],
            ),
            "contact_email": {
                "key": "contact_email",
                "type": "string",
                "application_visible": True,
                "format": {"checker": field_formats.EMAIL},
            },
        },
        "overrides": {
            _PLATFORM_OPTIONAL_KEY: {
                "application_visible": True,
                "application_required": True,  # tighten a platform-optional field: allowed
            }
        },
    }
    result = _service(repo).put_config(_TENANT, "fields", body)
    assert result["success"] is True
    assert len(repo.calls) == 1
    attrs = repo.calls[0]["attributes"]
    region = attrs["fields"]["region"]
    assert region["application_visible"] is True
    assert region["application_required"] is True
    assert region["application_choices"] == ["Noord", "Zuid"]
    assert attrs["fields"]["contact_email"]["format"] == {"checker": "EMAIL"}
    assert attrs["overrides"][_PLATFORM_OPTIONAL_KEY]["application_required"] is True


def test_validate_application_attributes_unauthored_tenant_writes_back_compatible_defaults():
    """R9.2 (back-compat): a tenant that authors NO application attributes writes exactly the
    pre-R8 shape — the three reader attributes, every field spec verbatim, no app-attr keys
    injected. The hardening is inert for a tenant that does not opt in."""
    repo = FakeWriteRepository()
    body = {
        "fields": {"nickname": {"key": "nickname", "type": "string"}},
        "overrides": {"membership.member_number": {"functional_group": "membership"}},
        "functional_groups": [{"key": "contact", "order": 1}],
    }
    _service(repo).put_config(_TENANT, "fields", body)
    attrs = repo.calls[0]["attributes"]
    # The three reader overlay attributes PLUS the spec-12 form-slug attributes (slug +
    # publish-state), authored on every fields write (Task 1.1); all three default to None for a
    # tenant that authored no slug and has no reader wired. The pre-R8 app-attr inertness is
    # unchanged for the overlay slices below.
    assert set(attrs) == {
        "fields",
        "overrides",
        "functional_groups",
        "slug",
        "published_at",
        "published_version",
    }
    assert attrs["slug"] is None
    assert attrs["published_at"] is None
    assert attrs["published_version"] is None
    # No application_* / format keys injected into a spec that did not author them.
    assert attrs["fields"]["nickname"] == {"key": "nickname", "type": "string"}
    assert attrs["overrides"]["membership.member_number"] == {
        "functional_group": "membership"
    }


class _FakeOverlayReader:
    """A minimal overlay reader exposing get_raw_fields_overlay for merge-on-write tests.

    Mirrors the REAL :class:`MembersProjectionReader.get_raw_fields_overlay` dual-read (spec 03,
    design C6 / review Must-fix #4): ``functional_groups`` is served as a MAP keyed by group key
    regardless of whether the seeded stored overlay uses the legacy LIST or the new MAP shape, so
    these merge tests exercise the same normalized input the service sees in production.
    """

    def __init__(self, overlay):
        self._overlay = dict(overlay)

    def get_raw_fields_overlay(self, tenant_id):
        raw = dict(self._overlay)
        raw["functional_groups"] = _normalize_groups(raw.get("functional_groups"))
        return raw


def _normalize_groups(raw) -> dict:
    """Test-side mirror of the reader's LIST-or-MAP → MAP normalizer (keyed by group key)."""
    if isinstance(raw, dict):
        out = {}
        for gkey, entry in raw.items():
            if isinstance(entry, dict) and gkey:
                e = dict(entry)
                e.setdefault("key", str(gkey))
                out[str(e.get("key") or gkey)] = e
        return out
    if isinstance(raw, (list, tuple)):
        return {str(e["key"]): dict(e) for e in raw if isinstance(e, dict) and e.get("key")}
    return {}


def _service_with_reader(repo, overlay, version="2026-10-22T00:00:00+00:00"):
    return ConfigWriteService(
        repo, version_fn=lambda: version, overlay_reader=_FakeOverlayReader(overlay)
    )


# ── config#fields MERGE-ON-WRITE + alias precedence (bugfix) ─────────────────────────────
#
# A config#fields PUT carries only the slice the client authors, but the repository put REPLACES
# the whole row. The Application Form Builder sends ONLY application-attribute toggles (under the
# `fixed_overrides` alias) with empty `fields`/`functional_groups`. Two bugs this pins:
#   1. alias precedence — a present-but-empty `overrides` must NOT shadow a populated
#      `fixed_overrides` (that dropped every base-field toggle);
#   2. merge-on-write — a partial body must MERGE onto the stored row, never wipe the omitted
#      slices (fields / functional_groups / other overrides).


def test_fields_write_alias_precedence_empty_overrides_does_not_shadow_fixed_overrides():
    """Bug 1: body with `overrides: {}` + populated `fixed_overrides` persists the overrides."""
    repo = FakeWriteRepository()
    body = {
        "fields": {},
        "overrides": {},  # present but EMPTY — must not shadow the alias
        "functional_groups": [],
        "fixed_overrides": {
            "personal.city": {"application_visible": True},
            "membership.status": {"application_visible": True},
        },
    }
    # No reader → legacy path, but the alias precedence fix still applies.
    _service(repo).put_config(_TENANT, "fields", body)
    overrides = repo.calls[0]["attributes"]["overrides"]
    assert overrides["personal.city"]["application_visible"] is True
    assert overrides["membership.status"]["application_visible"] is True


def test_fields_write_merges_partial_body_onto_stored_row_preserving_omitted_slices():
    """Bug 2: a partial body (only base toggles, empty fields/groups) MERGES onto the stored row —
    the tenant's existing fields + functional_groups are PRESERVED, not wiped."""
    stored = {
        "fields": {
            "motor_type": {"key": "motor_type", "type": "string"},
            "magazine_pref": {"key": "magazine_pref", "type": "enum"},
        },
        "overrides": {"personal.first_name": {"label": {"en": "First"}}},
        "functional_groups": [
            {"key": "personal", "order": 1},
            {"key": "motor", "order": 2},
        ],
    }
    repo = FakeWriteRepository()
    body = {
        "fields": {},
        "overrides": {},
        "functional_groups": [],
        "fixed_overrides": {"personal.city": {"application_visible": True}},
    }
    _service_with_reader(repo, stored).put_config(_TENANT, "fields", body)
    attrs = repo.calls[0]["attributes"]
    # The two stored tenant fields survive (body carried empty fields → preserved).
    assert set(attrs["fields"]) == {"motor_type", "magazine_pref"}
    # The stored functional_groups survive (body carried no groups → preserved). The catalog is a
    # MAP now (spec 03, design C6), merged per key — an empty body can never truncate it.
    assert set(attrs["functional_groups"]) == {"personal", "motor"}
    assert attrs["functional_groups"]["motor"]["order"] == 2
    # The pre-existing override survives AND the new base toggle is merged in.
    assert attrs["overrides"]["personal.first_name"]["label"] == {"en": "First"}
    assert attrs["overrides"]["personal.city"]["application_visible"] is True


def test_fields_write_incoming_entry_replaces_stored_entry_for_the_same_key():
    """A toggle on a key the stored row already has REPLACES that entry (merge, per-key)."""
    stored = {
        "fields": {},
        "fixed_overrides": {"personal.city": {"application_visible": True}},
        "functional_groups": [],
    }
    repo = FakeWriteRepository()
    # Toggle it OFF: the builder writes an attr-stripped/empty spec for the key.
    body = {
        "fields": {},
        "functional_groups": [],
        "fixed_overrides": {"personal.city": {}},
    }
    _service_with_reader(repo, stored).put_config(_TENANT, "fields", body)
    city = repo.calls[0]["attributes"]["overrides"]["personal.city"]
    assert city.get("application_visible") is None  # toggle-off cleared the attribute


def test_fields_write_partial_functional_groups_merge_per_key_never_truncate_catalog():
    """LIST→MAP migration (spec 03, design C6 / D2a): the catalog is a MAP merged PER KEY, so a
    body carrying ONE group ADDS/UPDATES that key and PRESERVES every other stored group — the
    structural fix for the occurrence-3 truncation (the old LIST path replaced the whole catalog,
    truncating 6→1). A partial groups payload can no longer wipe the catalog."""
    stored = {
        "fields": {},
        "overrides": {},
        "functional_groups": [
            {"key": "old", "order": 1},
            {"key": "keep_me", "order": 2},
        ],
    }
    repo = FakeWriteRepository()
    # The configurator edits ONE group; the body carries only that group.
    body = {"functional_groups": [{"key": "old", "label": {"en": "Renamed"}, "order": 9}]}
    _service_with_reader(repo, stored).put_config(_TENANT, "fields", body)
    groups = repo.calls[0]["attributes"]["functional_groups"]
    # MAP keyed by group key; the edited group is updated, the untouched group SURVIVES.
    assert set(groups) == {"old", "keep_me"}
    assert groups["old"]["label"] == {"en": "Renamed"}
    assert groups["old"]["order"] == 9
    assert groups["keep_me"]["order"] == 2


def test_fields_write_adding_a_new_group_preserves_existing_catalog():
    """Adding a brand-new group merges it in alongside the stored groups (no replace)."""
    stored = {
        "fields": {},
        "overrides": {},
        "functional_groups": [{"key": "personal", "order": 1}],
    }
    repo = FakeWriteRepository()
    body = {"functional_groups": [{"key": "motor", "order": 2}]}
    _service_with_reader(repo, stored).put_config(_TENANT, "fields", body)
    groups = repo.calls[0]["attributes"]["functional_groups"]
    assert set(groups) == {"personal", "motor"}


def test_fields_write_without_reader_is_legacy_replace():
    """No overlay reader (older wiring / unit default) → the body is written as-is (replace)."""
    repo = FakeWriteRepository()
    body = {
        "fields": {"x": {"key": "x", "type": "string"}},
        "overrides": {},
        "functional_groups": [],
    }
    _service(repo).put_config(_TENANT, "fields", body)
    assert set(repo.calls[0]["attributes"]["fields"]) == {"x"}


# ── config#fields FORM SLUG + publish-state (spec 12 Task 1.1 / R4.2, design §Data Models) ──────
#
# The application form carries its OWN public slug on the config#fields row (NOT in Flask
# tenant_slugs, D1), plus publish-state metadata (published_at / published_version) owned by the
# publish path (Task 2.2). This task adds the FIELD + FORMAT validation only:
#   * a well-formed slug (landing SLUG_PATTERN rules) is authored onto the row;
#   * a malformed slug is rejected fail-loud with the caller-safe ConfigWriteValidationError;
#   * a plain fields save never fabricates or wipes publish-state — it carries it through;
#   * an omitted slug carries the stored slug; an explicit null clears it.
# UNIQUENESS is NOT checked here (that is the Task-1.2 _slugs/{slug} marker).


def test_fields_write_accepts_and_stores_a_wellformed_slug():
    repo = FakeWriteRepository()
    body = {"fields": {}, "slug": "hdcn-application-form"}
    _service(repo).put_config(_TENANT, "fields", body)
    assert repo.calls[0]["attributes"]["slug"] == "hdcn-application-form"


def test_fields_write_allows_slug_name_differing_from_tenant():
    """R4.4: the slug STRING is independent of the tenant NAME — a NAME != tenant is allowed."""
    repo = FakeWriteRepository()
    body = {"fields": {}, "slug": "totally-different-name"}
    _service(repo).put_config(_TENANT, "fields", body)
    assert repo.calls[0]["attributes"]["slug"] == "totally-different-name"


@pytest.mark.parametrize(
    "bad_slug",
    [
        "",  # blank
        "ab",  # too short (< 3)
        "a" * 101,  # too long (> 100)
        "HDCN",  # uppercase
        "-hdcn",  # leading hyphen
        "hdcn-",  # trailing hyphen
        "hd--cn",  # consecutive hyphens
        "hd cn",  # space
        "hd_cn",  # underscore (not allowed)
        "héllo",  # non-ascii
        "admin",  # reserved
        "api",  # reserved
        123,  # not a string
    ],
)
def test_fields_write_rejects_malformed_slug_fail_loud(bad_slug):
    repo = FakeWriteRepository()
    with pytest.raises(ConfigWriteValidationError):
        _service(repo).put_config(_TENANT, "fields", {"fields": {}, "slug": bad_slug})
    assert repo.calls == []  # nothing persisted on a validation failure


def test_fields_write_malformed_slug_error_is_caller_safe():
    """The rejection message names the slug problem (caller-safe), leaking no internals (R8)."""
    repo = FakeWriteRepository()
    with pytest.raises(ConfigWriteValidationError) as exc:
        _service(repo).put_config(_TENANT, "fields", {"fields": {}, "slug": "Bad Slug"})
    assert "slug" in str(exc.value).lower()


def test_fields_write_explicit_null_slug_clears_it():
    repo = FakeWriteRepository()
    stored = {
        "fields": {},
        "fixed_overrides": {},
        "functional_groups": [],
        "slug": "old-slug",
    }
    _service_with_reader(repo, stored).put_config(
        _TENANT, "fields", {"fields": {}, "slug": None}
    )
    assert repo.calls[0]["attributes"]["slug"] is None


def test_fields_write_omitting_slug_carries_the_stored_slug_through():
    """A fields save that does NOT carry a slug preserves the stored one (no accidental wipe)."""
    repo = FakeWriteRepository()
    stored = {
        "fields": {},
        "fixed_overrides": {},
        "functional_groups": [],
        "slug": "hdcn-application-form",
    }
    body = {"fixed_overrides": {"personal.city": {"application_visible": True}}}
    _service_with_reader(repo, stored).put_config(_TENANT, "fields", body)
    assert repo.calls[0]["attributes"]["slug"] == "hdcn-application-form"


def test_fields_write_never_authors_publish_state_from_the_body():
    """published_at / published_version are publish-owned (Task 2.2) — a body can't forge them."""
    repo = FakeWriteRepository()
    body = {
        "fields": {},
        "slug": "hdcn-application-form",
        "published_at": "2099-01-01T00:00:00+00:00",  # forged — must be ignored
        "published_version": 999,  # forged — must be ignored
    }
    _service(repo).put_config(_TENANT, "fields", body)
    attrs = repo.calls[0]["attributes"]
    # No reader + a never-published row → carried-through publish-state is None, NOT the forged body.
    assert attrs["published_at"] is None
    assert attrs["published_version"] is None


def test_fields_write_carries_stored_publish_state_through_on_a_plain_save():
    """A plain fields save preserves the publish-state the publish path previously wrote."""
    repo = FakeWriteRepository()
    stored = {
        "fields": {},
        "fixed_overrides": {},
        "functional_groups": [],
        "slug": "hdcn-application-form",
        "published_at": "2026-10-23T12:00:00+00:00",
        "published_version": 3,
    }
    body = {"fixed_overrides": {"personal.city": {"application_visible": True}}}
    _service_with_reader(repo, stored).put_config(_TENANT, "fields", body)
    attrs = repo.calls[0]["attributes"]
    assert attrs["published_at"] == "2026-10-23T12:00:00+00:00"
    assert attrs["published_version"] == 3


# ── Option-integrity write-seam (03b Task 1.2 / Requirements 3.2a, 3.4a) ─────────────────
#
# The unified enum model hangs a field's vocabulary off its OWN `options`, so the config-write
# seam is the authoritative place to keep that vocabulary well-formed. `_validate_fields_body`
# → `_validate_option_integrity` enforces two rules over the MERGED field/override specs, BEFORE
# the row is written, keyed to the offending field:
#   R3.4a  a REQUIRED enum, or one OFF the application form (application_visible falsey → the form
#          supplies a default), must keep >=1 option with `allowed:true` (an absent `allowed`
#          reads as true). A write that would zero the allowed set is rejected.
#   R3.2a  an option `value` present in the CURRENT stored options but ABSENT from the new set has
#          been removed/renamed; if a member still references it the write is REJECTED with a
#          caller-safe message naming the option (the admin may instead set it `allowed:false`).
#          "Referenced by a member" is observed via the injected `usage_probe` (storage-agnostic);
#          no probe wired → the leg does not block (member save BU-2 is the backstop).


class _OptionUsageProbe:
    """Option-level probe exposing option_in_use(tenant_id, field_key, value) -> bool.

    The preferred shape for the write seam: a set of (field_key, value) pairs a member still
    references. Mirrors the storage-agnostic probe contract shared with the delete-field guard —
    the domain never queries the members table itself (steering 35/39).
    """

    def __init__(self, in_use=()):
        self._in_use = set(in_use)

    def option_in_use(self, tenant_id, field_key, value):
        return (field_key, value) in self._in_use


class _FieldUsageProbe:
    """The richer field_usage(tenant_id, field_key) probe (delete-field guard shape) reporting the
    per-value usage under a ``values`` collection — the write seam reads membership of it."""

    def __init__(self, used_values_by_field):
        self._by_field = {k: set(v) for k, v in used_values_by_field.items()}

    def field_usage(self, tenant_id, field_key):
        return {"member_data": True, "values": self._by_field.get(field_key, set())}


def _service_with_reader_and_probe(repo, overlay, probe, version="2026-11-01T00:00:00+00:00"):
    return ConfigWriteService(
        repo,
        version_fn=lambda: version,
        overlay_reader=_FakeOverlayReader(overlay),
        usage_probe=probe,
    )


def _membership_type_options(*specs):
    """Build a membership.membership_type override spec carrying the given option specs.

    Each spec is a dict merged onto a {value,label} base, so a test can set allowed/order per
    option. The override is a platform-REQUIRED reference field (membership.membership_type is
    required=True in the registry), so the R3.4a required-enum rule applies to it.
    """
    options = []
    for s in specs:
        opt = {"value": s["value"], "label": s.get("label", {"en": s["value"]})}
        if "allowed" in s:
            opt["allowed"] = s["allowed"]
        if "order" in s:
            opt["order"] = s["order"]
        options.append(opt)
    return {"membership.membership_type": {"options": options}}


# ── R3.4a: a required / off-form enum must keep >=1 allowed:true option ───────────────────


def test_option_integrity_required_enum_with_zero_allowed_options_rejected():
    """R3.4a: a platform-required enum (membership_type) whose every option is allowed:false is
    rejected — the form would have no default / no selectable value; nothing persists."""
    repo = FakeWriteRepository()
    body = {
        "overrides": _membership_type_options(
            {"value": "gewoon_lid", "allowed": False},
            {"value": "erelid", "allowed": False},
        )
    }
    with pytest.raises(ConfigWriteValidationError) as exc:
        _service(repo).put_config(_TENANT, "fields", body)
    assert "membership.membership_type" in str(exc.value)
    assert "allowed:true" in str(exc.value)
    assert repo.calls == []


def test_option_integrity_off_form_variable_enum_with_zero_allowed_options_rejected():
    """R3.4a: a VARIABLE enum that is OFF the application form (application_visible not True) with
    zero allowed options is rejected — the form supplies a default from the options."""
    repo = FakeWriteRepository()
    body = {
        "fields": {
            "shirt_size": {
                "key": "shirt_size",
                "type": "enum",
                # off the form (no application_visible) → a default is supplied from options
                "options": [
                    {"value": "s", "allowed": False},
                    {"value": "m", "allowed": False},
                ],
            }
        }
    }
    with pytest.raises(ConfigWriteValidationError) as exc:
        _service(repo).put_config(_TENANT, "fields", body)
    assert "overlay.shirt_size" in str(exc.value)
    assert repo.calls == []


def test_option_integrity_at_least_one_allowed_option_writes():
    """R3.4a (happy): a required enum keeping >=1 allowed option writes — a retired (allowed:false)
    option ALONGSIDE allowed ones is fine (grandfathering), options persist verbatim."""
    repo = FakeWriteRepository()
    body = {
        "overrides": _membership_type_options(
            {"value": "gewoon_lid", "allowed": True, "order": 10},
            {"value": "erelid", "allowed": False, "order": 20},  # retired but present
        )
    }
    _service(repo).put_config(_TENANT, "fields", body)
    opts = repo.calls[0]["attributes"]["overrides"]["membership.membership_type"][
        "options"
    ]
    assert [o["value"] for o in opts] == ["gewoon_lid", "erelid"]
    assert opts[1]["allowed"] is False


def test_option_integrity_absent_allowed_counts_as_allowed():
    """R3.4a (back-compat): an option with NO `allowed` key reads as allowed:true, so an all-
    absent-allowed required enum satisfies the rule and writes."""
    repo = FakeWriteRepository()
    body = {
        "overrides": {
            "membership.membership_type": {
                "options": [{"value": "gewoon_lid", "label": {"en": "Member"}}]
            }
        }
    }
    _service(repo).put_config(_TENANT, "fields", body)
    assert repo.calls  # persisted


def test_option_integrity_on_form_optional_enum_may_have_zero_allowed():
    """R3.4a applies ONLY to required / off-form enums: a platform-OPTIONAL variable enum that is
    ON the form (application_visible=True) and not required is NOT subject to the >=1-allowed rule
    (the admin controls its vocabulary directly, no default is auto-supplied)."""
    repo = FakeWriteRepository()
    body = {
        "fields": {
            "nickname_style": {
                "key": "nickname_style",
                "type": "enum",
                "application_visible": True,
                "options": [{"value": "formal", "allowed": False}],
            }
        }
    }
    _service(repo).put_config(_TENANT, "fields", body)
    assert repo.calls  # not rejected


def test_option_integrity_non_enum_field_without_options_is_unaffected():
    """A plain string field (no options) is never subject to the option-integrity rules."""
    repo = FakeWriteRepository()
    body = {"fields": {"nickname": {"key": "nickname", "type": "string"}}}
    _service(repo).put_config(_TENANT, "fields", body)
    assert repo.calls


# ── R3.2a: an in-use option value cannot vanish / be renamed ──────────────────────────────


def test_option_integrity_in_use_option_removed_is_rejected():
    """R3.2a: dropping an option `value` a member still references is rejected with a caller-safe
    message naming the option; the admin must set it allowed:false instead. Nothing persists."""
    stored = {
        "fields": {},
        "fixed_overrides": _membership_type_options(
            {"value": "gewoon_lid", "order": 10},
            {"value": "erelid", "order": 20},
        ),
        "functional_groups": [],
    }
    # A member still references `erelid`.
    probe = _OptionUsageProbe(in_use={("membership_type", "erelid")})
    repo = FakeWriteRepository()
    # The write drops `erelid` from the options entirely (not retire — DELETE).
    body = {"overrides": _membership_type_options({"value": "gewoon_lid", "order": 10})}
    with pytest.raises(ConfigWriteValidationError) as exc:
        _service_with_reader_and_probe(repo, stored, probe).put_config(
            _TENANT, "fields", body
        )
    msg = str(exc.value)
    assert "erelid" in msg
    assert "allowed:false" in msg  # names the safe alternative
    assert repo.calls == []


def test_option_integrity_in_use_option_renamed_is_rejected():
    """R3.2a: RENAMING an in-use option's value (old value gone, new value added) is a removal of
    the old value from the member's perspective — rejected."""
    stored = {
        "fields": {},
        "fixed_overrides": _membership_type_options({"value": "erelid", "order": 20}),
        "functional_groups": [],
    }
    probe = _OptionUsageProbe(in_use={("membership_type", "erelid")})
    repo = FakeWriteRepository()
    body = {
        "overrides": _membership_type_options(
            {"value": "gewoon_lid", "order": 10},  # erelid renamed to gewoon_lid
        )
    }
    with pytest.raises(ConfigWriteValidationError) as exc:
        _service_with_reader_and_probe(repo, stored, probe).put_config(
            _TENANT, "fields", body
        )
    assert "erelid" in str(exc.value)
    assert repo.calls == []


def test_option_integrity_in_use_option_may_be_retired_allowed_false():
    """R3.2a (happy): an in-use option may be RETIRED (allowed:false) — the value is still present
    in the options, so grandfathering is preserved and the write succeeds."""
    stored = {
        "fields": {},
        "fixed_overrides": _membership_type_options(
            {"value": "gewoon_lid", "order": 10},
            {"value": "erelid", "order": 20},
        ),
        "functional_groups": [],
    }
    probe = _OptionUsageProbe(in_use={("membership_type", "erelid")})
    repo = FakeWriteRepository()
    body = {
        "overrides": _membership_type_options(
            {"value": "gewoon_lid", "allowed": True, "order": 10},
            {"value": "erelid", "allowed": False, "order": 20},  # retired, still present
        )
    }
    _service_with_reader_and_probe(repo, stored, probe).put_config(
        _TENANT, "fields", body
    )
    opts = repo.calls[0]["attributes"]["overrides"]["membership.membership_type"][
        "options"
    ]
    assert {o["value"]: o.get("allowed", True) for o in opts} == {
        "gewoon_lid": True,
        "erelid": False,
    }


def test_option_integrity_in_use_option_may_be_relabelled():
    """R3.2a (happy): relabelling an in-use option (same value, new label) is always allowed — the
    value is unchanged, only the per-language label differs."""
    stored = {
        "fields": {},
        "fixed_overrides": _membership_type_options(
            {"value": "gewoon_lid", "order": 10},
            {"value": "erelid", "order": 20},
        ),
        "functional_groups": [],
    }
    probe = _OptionUsageProbe(in_use={("membership_type", "erelid")})
    repo = FakeWriteRepository()
    body = {
        "overrides": {
            "membership.membership_type": {
                "options": [
                    {"value": "gewoon_lid", "label": {"en": "Member"}},
                    {"value": "erelid", "label": {"en": "Honorary (renamed label)"}},
                ]
            }
        }
    }
    _service_with_reader_and_probe(repo, stored, probe).put_config(
        _TENANT, "fields", body
    )
    opts = repo.calls[0]["attributes"]["overrides"]["membership.membership_type"][
        "options"
    ]
    assert opts[1]["label"] == {"en": "Honorary (renamed label)"}


def test_option_integrity_not_in_use_option_may_be_removed():
    """R3.2a: an option NOT referenced by any member may be deleted freely — no block."""
    stored = {
        "fields": {},
        "fixed_overrides": _membership_type_options(
            {"value": "gewoon_lid", "order": 10},
            {"value": "sponsor", "order": 60},  # zero members (design tally)
        ),
        "functional_groups": [],
    }
    probe = _OptionUsageProbe(in_use=set())  # nobody references anything
    repo = FakeWriteRepository()
    body = {"overrides": _membership_type_options({"value": "gewoon_lid", "order": 10})}
    _service_with_reader_and_probe(repo, stored, probe).put_config(
        _TENANT, "fields", body
    )
    opts = repo.calls[0]["attributes"]["overrides"]["membership.membership_type"][
        "options"
    ]
    assert [o["value"] for o in opts] == ["gewoon_lid"]


def test_option_integrity_removal_without_probe_does_not_block():
    """With no usage_probe wired the in-use leg is unobservable and does NOT block — the write
    proceeds (production always wires a probe; member save BU-2 is the backstop)."""
    stored = {
        "fields": {},
        "fixed_overrides": _membership_type_options(
            {"value": "gewoon_lid", "order": 10},
            {"value": "erelid", "order": 20},
        ),
        "functional_groups": [],
    }
    repo = FakeWriteRepository()
    body = {"overrides": _membership_type_options({"value": "gewoon_lid", "order": 10})}
    # reader wired (so current options are read) but NO probe → in-use unobservable.
    _service_with_reader(repo, stored).put_config(_TENANT, "fields", body)
    assert repo.calls  # not blocked


def test_option_integrity_accepts_richer_field_usage_probe_shape():
    """The richer field_usage(...) probe shape (delete-field guard) is honoured: an in-use value
    reported under `values` blocks its removal just like the option-level probe."""
    stored = {
        "fields": {},
        "fixed_overrides": _membership_type_options(
            {"value": "gewoon_lid", "order": 10},
            {"value": "erelid", "order": 20},
        ),
        "functional_groups": [],
    }
    probe = _FieldUsageProbe({"membership_type": ["erelid"]})
    repo = FakeWriteRepository()
    body = {"overrides": _membership_type_options({"value": "gewoon_lid", "order": 10})}
    with pytest.raises(ConfigWriteValidationError) as exc:
        _service_with_reader_and_probe(repo, stored, probe).put_config(
            _TENANT, "fields", body
        )
    assert "erelid" in str(exc.value)
    assert repo.calls == []


# ── Property 1 / Property 2 — read→write→read over the REAL config#fields fixture (03b 1.3) ──
#
# Steering 39 (non-negotiable): prove the round-trip against REAL data, not a hand-built fixture.
# The real stored h-dcn `config#fields` overlay is committed at
# `sam/tests/fixtures/hdcn_config_fields_overlay.json` (captured from `test_governance_projection`);
# its `membership.membership_type` override carries the real on-form flag but NO inline options yet
# (the vocabulary still lives in the `membershiptype#<code>` catalog — the fold is Task 7.2). The
# real POST-FOLD membership_type vocabulary — the 7 h-dcn Lidmaatschap-Beheer values with their
# {nl,en} labels + role gates, `erelid` retired (allowed:false) — is committed at
# `backend/tests/fixtures/hdcn_membership_type_options.json` (the authoritative values from
# scripts/onboarding/members/h-dcn/ONBOARDING.md; reused/extended by the Task 7.1 real-row fixture).
#
# These two properties (design §Correctness Properties) exercise the ACTUAL write service seam:
#   Property 1 — No orphaned reference: after the collapse, every stored
#     `membership.membership_type` value a member holds resolves to a written field option.
#   Property 2 — Grandfather preserved: a member holding `erelid` (allowed:false) round-trips —
#     the option stays present (allowed:false) across read→write→read, so the value is retained,
#     readable, and absent from the picker; an in-use probe on it does not block the retire write.

import json as _json

_REAL_OVERLAY_FIXTURE = os.path.join(
    _REPO_ROOT, "sam", "tests", "fixtures", "hdcn_config_fields_overlay.json"
)
_REAL_MT_OPTIONS_FIXTURE = os.path.join(
    _REPO_ROOT, "backend", "tests", "fixtures", "hdcn_membership_type_options.json"
)


def _load_real_overlay_row():
    """The REAL stored h-dcn `config#fields` overlay (fields / overrides / functional_groups)."""
    with open(_REAL_OVERLAY_FIXTURE, encoding="utf-8") as f:
        return _json.load(f)


def _load_real_membership_type_options():
    """The REAL post-fold h-dcn membership_type options (incl. erelid=allowed:false)."""
    with open(_REAL_MT_OPTIONS_FIXTURE, encoding="utf-8") as f:
        return _json.load(f)["options"]


def _real_stored_row_with_folded_membership_type():
    """The real overlay row with the real membership_type options folded onto its override — i.e.
    the shape the EXPAND migration (Task 7.2) produces, used as the CURRENT stored row the write
    seam diffs against and merges onto."""
    overlay = _load_real_overlay_row()
    options = _load_real_membership_type_options()
    overrides = dict(overlay["overrides"])
    mt = dict(overrides["membership.membership_type"])
    mt["options"] = [dict(o) for o in options]
    overrides["membership.membership_type"] = mt
    return {
        "fields": overlay["fields"],
        "overrides": overrides,
        "functional_groups": overlay["functional_groups"],
    }


# The real stored member membership_type values the design migration-safety proof maps (the 6
# values members actually hold in the live h-dcn population; `erelid` is the retired-but-held one,
# `sponsor` has zero members in the tally so is not in this set).
_REAL_MEMBER_MEMBERSHIP_TYPE_VALUES = [
    "gewoon_lid",
    "gezins_lid",
    "donateur",
    "gezins_donateur",
    "erelid",
    "overig",
]


def test_fixture_sanity_real_membership_type_options_include_retired_erelid():
    """Guard the real-row fixture itself: it carries the 7 real h-dcn values and `erelid` is the
    one retired (allowed:false) option — the shape Property 1/2 depend on (steering 39: a wrong
    fixture once hid this exact class of bug)."""
    options = _load_real_membership_type_options()
    by_value = {o["value"]: o for o in options}
    assert set(by_value) == {
        "gewoon_lid",
        "gezins_lid",
        "donateur",
        "gezins_donateur",
        "erelid",
        "sponsor",
        "overig",
    }
    # erelid is retired; every other value is allowed (absent allowed reads true).
    assert by_value["erelid"].get("allowed") is False
    assert all(
        by_value[v].get("allowed", True) is True for v in by_value if v != "erelid"
    )
    # Every stored member value resolves to a fixture option (no orphan at the fixture level).
    assert set(_REAL_MEMBER_MEMBERSHIP_TYPE_VALUES).issubset(set(by_value))


def test_property1_no_orphaned_reference_roundtrip_over_real_fixture():
    """Property 1 (Validates: Requirements 3.1, 3.2a, 3.4a): read→write→read of the REAL
    membership_type options preserves EVERY option, so every stored member reference still
    resolves to a written option — no member is orphaned by the collapse.

    read  — the real post-fold stored row (current options).
    write — a config#fields PUT re-authoring the same options (an idempotent re-save, the shape
            the authoring surface emits) through the real ConfigWriteService seam.
    read  — the persisted attributes; assert the option set is intact and covers all member refs.
    """
    stored = _real_stored_row_with_folded_membership_type()
    options = _load_real_membership_type_options()
    repo = FakeWriteRepository()
    # No member reference is being removed/renamed → the write succeeds even with a probe that
    # reports every member value as in use (Property 1 is about non-orphaning, not blocking).
    probe = _OptionUsageProbe(
        in_use={("membership_type", v) for v in _REAL_MEMBER_MEMBERSHIP_TYPE_VALUES}
    )
    body = {"overrides": {"membership.membership_type": {"options": [dict(o) for o in options]}}}

    _service_with_reader_and_probe(repo, stored, probe).put_config(_TENANT, "fields", body)

    written = repo.calls[0]["attributes"]["overrides"]["membership.membership_type"][
        "options"
    ]
    written_values = {o["value"] for o in written}
    # read→write→read preserved the full option vocabulary verbatim (order + values).
    assert [o["value"] for o in written] == [o["value"] for o in options]
    # Every stored member membership_type value resolves to a written option — zero orphans.
    orphaned = [v for v in _REAL_MEMBER_MEMBERSHIP_TYPE_VALUES if v not in written_values]
    assert orphaned == [], f"stored member values orphaned by the collapse: {orphaned}"


def test_property2_grandfather_preserved_roundtrip_over_real_fixture():
    """Property 2 (Validates: Requirements 3.1, 3.2): a member holding the RETIRED `erelid`
    (allowed:false) round-trips — the option is retained across read→write→read (readable,
    grandfathered) and stays allowed:false (absent from the picker). The in-use probe on `erelid`
    does NOT block the retire-in-place write (retire ≠ remove)."""
    stored = _real_stored_row_with_folded_membership_type()
    options = _load_real_membership_type_options()
    # A real member still holds the retired `erelid` value.
    probe = _OptionUsageProbe(in_use={("membership_type", "erelid")})
    repo = FakeWriteRepository()
    body = {"overrides": {"membership.membership_type": {"options": [dict(o) for o in options]}}}

    _service_with_reader_and_probe(repo, stored, probe).put_config(_TENANT, "fields", body)

    written = repo.calls[0]["attributes"]["overrides"]["membership.membership_type"][
        "options"
    ]
    by_value = {o["value"]: o for o in written}
    # The retired value is RETAINED (grandfathered), not wiped — readable on a subsequent read.
    assert "erelid" in by_value
    # ...and it stays retired (allowed:false) → hidden from the picker for new/changed records.
    assert by_value["erelid"].get("allowed") is False
    # ...while every still-active value remains selectable (allowed truthy / absent).
    assert by_value["gewoon_lid"].get("allowed", True) is True


def test_property2_grandfather_toggle_both_ways_over_real_fixture():
    """Property 2 (Req 3.2): the retired/active state is freely toggleable BOTH ways. Reactivating
    the in-use retired `erelid` (allowed:false → true) round-trips, and re-retiring it
    (true → false) round-trips — neither is blocked (the value never leaves the option set)."""
    options = _load_real_membership_type_options()

    # (a) reactivate erelid: allowed:false → true
    stored_retired = _real_stored_row_with_folded_membership_type()
    reactivated = [dict(o) for o in options]
    next(o for o in reactivated if o["value"] == "erelid")["allowed"] = True
    repo_a = FakeWriteRepository()
    probe = _OptionUsageProbe(in_use={("membership_type", "erelid")})
    _service_with_reader_and_probe(repo_a, stored_retired, probe).put_config(
        _TENANT, "fields", {"overrides": {"membership.membership_type": {"options": reactivated}}}
    )
    written_a = {
        o["value"]: o
        for o in repo_a.calls[0]["attributes"]["overrides"]["membership.membership_type"][
            "options"
        ]
    }
    assert written_a["erelid"].get("allowed") is True

    # (b) re-retire erelid from an all-active stored row: allowed:true → false
    stored_active = _real_stored_row_with_folded_membership_type()
    for o in stored_active["overrides"]["membership.membership_type"]["options"]:
        if o["value"] == "erelid":
            o["allowed"] = True
    repo_b = FakeWriteRepository()
    _service_with_reader_and_probe(repo_b, stored_active, probe).put_config(
        _TENANT, "fields", {"overrides": {"membership.membership_type": {"options": [dict(o) for o in options]}}}
    )
    written_b = {
        o["value"]: o
        for o in repo_b.calls[0]["attributes"]["overrides"]["membership.membership_type"][
            "options"
        ]
    }
    assert written_b["erelid"].get("allowed") is False
