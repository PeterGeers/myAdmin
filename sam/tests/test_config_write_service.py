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
# (variable overlay) and `overrides` (fixed-field) specs, the three write-time invariants:
#   R8.1a  application_choices ⊆ the field's own resolved choices (options[].value / choices)
#   R8.1b  format is a well-formed {checker, params?} whose checker ∈ field_formats.known_tokens()
#   R8.1c  application_required=False may not relax a PLATFORM-required field
# A violation raises ONE caller-safe ConfigWriteValidationError keyed to the offending field and
# persists NOTHING; a coherent body still writes; a tenant that authors no app attrs writes the
# back-compatible defaults unchanged (R9.2). These exhaustively cover task 1.1's product change.

from sam.members.domain import field_formats

# A platform-required fixed field (fixed_fields: membership.status / .membership_type /
# .joined_date and personal.last_name are required=True). Used for the no-relax invariant.
_PLATFORM_REQUIRED_KEY = "membership.status"
# A platform-OPTIONAL fixed field (required=False) — relaxing it on the form is allowed.
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


def test_validate_application_attributes_subset_from_bare_choices_list_accepted():
    """R8.1a (happy): choices may be declared as a bare string ``choices`` list (not only rich
    ``options``); a subset ⊆ that list writes."""
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
    _service(repo).put_config(_TENANT, "fields", body)
    written = repo.calls[0]["attributes"]["fields"]["region"]
    assert written["application_choices"] == ["Noord", "Zuid"]


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


# ── R8.1c: application_required=False may not relax a platform-required field ─────────────


def test_validate_application_attributes_relax_platform_required_override_raises():
    """R8.1c: application_required=False on a PLATFORM-required fixed field (via overrides) is a
    relax of the platform floor — rejected, keyed to that field, nothing persists."""
    repo = FakeWriteRepository()
    body = {
        "overrides": {
            _PLATFORM_REQUIRED_KEY: {
                "application_visible": True,
                "application_required": False,
            }
        }
    }
    with pytest.raises(ConfigWriteValidationError) as exc:
        _service(repo).put_config(_TENANT, "fields", body)
    assert _PLATFORM_REQUIRED_KEY in str(exc.value)
    assert repo.calls == []


def test_validate_application_attributes_tighten_platform_optional_override_accepted():
    """R8.1c (happy): the public form may TIGHTEN — application_required=True on any field, and
    application_required=False on a platform-OPTIONAL field, both write (only relaxing the platform
    floor is forbidden)."""
    repo = FakeWriteRepository()
    body = {
        "overrides": {
            # tighten a platform-optional field to required-on-the-form: allowed
            _PLATFORM_OPTIONAL_KEY: {"application_required": True},
            # explicitly not-required on a platform-optional field: allowed (no floor to relax)
            "personal.phone": {"application_required": False},
        }
    }
    _service(repo).put_config(_TENANT, "fields", body)
    overrides = repo.calls[0]["attributes"]["overrides"]
    assert overrides[_PLATFORM_OPTIONAL_KEY]["application_required"] is True
    assert overrides["personal.phone"]["application_required"] is False


def test_validate_application_attributes_variable_field_required_false_accepted():
    """R8.1c (happy): a VARIABLE overlay field is never platform-required, so
    application_required=False on it is always allowed."""
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


# ── Collection: every offending field reported in ONE error ───────────────────────────────


def test_validate_application_attributes_collects_all_offending_fields_in_one_error():
    """R8.3: violations across BOTH fields and overrides are collected into ONE error naming every
    offending field (not just the first); nothing persists."""
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
            _PLATFORM_REQUIRED_KEY: {"application_required": False},  # relax
        },
    }
    with pytest.raises(ConfigWriteValidationError) as exc:
        _service(repo).put_config(_TENANT, "fields", body)
    message = str(exc.value)
    assert "overlay.region" in message
    assert "overlay.f" in message
    assert _PLATFORM_REQUIRED_KEY in message
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
    assert set(attrs) == {"fields", "overrides", "functional_groups"}
    # No application_* / format keys injected into a spec that did not author them.
    assert attrs["fields"]["nickname"] == {"key": "nickname", "type": "string"}
    assert attrs["overrides"]["membership.member_number"] == {
        "functional_group": "membership"
    }


class _FakeOverlayReader:
    """A minimal overlay reader exposing get_raw_fields_overlay for merge-on-write tests."""

    def __init__(self, overlay):
        self._overlay = overlay

    def get_raw_fields_overlay(self, tenant_id):
        return self._overlay


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
    # The stored functional_groups survive (body carried [] → preserved).
    assert [g["key"] for g in attrs["functional_groups"]] == ["personal", "motor"]
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


def test_fields_write_non_empty_functional_groups_replace_stored_catalog():
    """A body that DOES carry functional_groups (the field-config editor) replaces the catalog."""
    stored = {
        "fields": {},
        "overrides": {},
        "functional_groups": [{"key": "old", "order": 1}],
    }
    repo = FakeWriteRepository()
    body = {"functional_groups": [{"key": "new", "order": 1}]}
    _service_with_reader(repo, stored).put_config(_TENANT, "fields", body)
    groups = repo.calls[0]["attributes"]["functional_groups"]
    assert [g["key"] for g in groups] == ["new"]


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
