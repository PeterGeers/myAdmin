"""
Bugfix spec `bugfix-slug-lifecycle` — Task 2: the PRESERVATION property tests (backend).

Parent spec: `.kiro/specs/Members/14 - public-pages-multi-tenant-serving` (R1.2, R2.1, R2.3, R4).
Bugfix spec: `.kiro/specs/Members/14 .../bugfix-slug-lifecycle` (bugfix.md / design.md).

WHAT THIS TEST IS
-----------------
This is the PRESERVATION half of the bugfix exploration (companion to the task-1 bug-condition
exploration `test_slug_lifecycle_bug_condition.py`). It encodes Property 2 (Preservation): for any
input where the bug condition does NOT hold, the fixed system must produce the SAME result as the
original system.

OBSERVATION-FIRST (bugfix workflow / steering 39): these assertions were OBSERVED on the UNFIXED
code and MUST PASS NOW — they are the baseline the fix (tasks 3.x) must not disturb. They pin the
four unchanged behaviours the design's "Preservation Requirements" name (bugfix.md R3.1–R3.4):

  * R3.1 already-slugged publish/claim — a tenant with a valid stored `config#fields.slug`
         publishes/claims IDENTICALLY (`ApplicationPublishService` + `get_form_slug` +
         `S3SlugMarkerStore.claim`), and the publish gate no longer refuses `no_slug`.
  * R3.3 non-slug config writes — a `config#fields` Change-Op (`set_field_application`) and a
         `config#mail` write round-trip unchanged (the slug-author path is ADDITIVE).
  * R3.4 publish-state carry-through — a `config#fields` row's existing `published_at` /
         `published_version` is carried through a (hypothetical) slug change, proven against the
         REAL `h-dcn` `config#fields` row (steering 39), NOT a hand-built fixture.
  * R3.2 Flask landing plane — `/api/landing/slug` / `landing_page_service.py` / `tenant_slugs`
         live on the OTHER plane and are NOT modified by this fix. Observed here as a STRUCTURAL
         boundary: the SAM slug lifecycle surfaces never import the Flask landing module.

NO live AWS: the publish/claim path uses the REAL `S3SlugMarkerStore` over a conditional-honouring
in-memory fake S3 client (the sibling `test_application_publish_dispatch.py` pattern — real claim
semantics, never a trivially-succeeding mock); the config round-trips use in-memory `FakeTable`
stand-ins (the sibling projection-reader/write-repository pattern). Property-based because
preservation is a UNIVERSAL property across many non-buggy inputs (any already-valid prefixed slug,
any non-slug config write) — design "Preservation Checking".

Validates (bugfix): Requirements 3.1, 3.2, 3.3, 3.4
"""

from __future__ import annotations

import importlib
import io
import json
import os
import sys

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

_REPO_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)
_BACKEND_SRC = os.path.join(_REPO_ROOT, "backend", "src")
if _BACKEND_SRC not in sys.path:
    sys.path.insert(0, _BACKEND_SRC)

from services import projection_schema as schema

from sam.members.domain.application_publish import (
    FORM_OWNER_KIND,
    FORM_OWNER_PLANE,
    FORM_RESOURCE_REF,
    PUBLIC_API_BASE_ENV_VAR,
    ApplicationPublishService,
    PublishNotReady,
    PublishPipelineNotWired,
)
from sam.members.domain.application_readiness import StaticMailReadinessProvider
from sam.members.domain.config_fields_crud_service import ConfigFieldsCrudService
from sam.members.domain.config_write_service import ConfigWriteService
from sam.members.repository.projection_config_reader import MembersProjectionReader
from sam.members.repository.projection_config_write_repository import (
    REMOVE,
    SET,
    MembersConfigWriteRepository,
)
from sam.members.repository.slug_marker_store import S3SlugMarkerStore

#: The verified real-data tenant (bugfix.md Examples).
_TENANT = "h-dcn"
_CLAIM_BUCKET = "myadmin-public-pages-test"

_FIXTURE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "fixtures",
    "hdcn_config_fields_overlay.json",
)


def _load_real_overlay() -> dict:
    with open(_FIXTURE, encoding="utf-8") as f:
        return json.load(f)


#: The publish-time public API base baked into the rendered artifact. Change-with-tests
#: (steering 34/39): the bugfix `bugfix-published-form-submit` Task 3.1 inserted a fail-fast
#: `resolve_public_api_base()` (reads `PUBLIC_API_BASE_URL`, NO silent default) into the SHARED
#: `ApplicationPublishService.publish()` render path. The two R3.1 preservation tests below call
#: `publish(_TENANT)` and now need this env set to reach their expected `PublishPipelineNotWired`
#: raise rather than fail-fast on the missing env. Mirrors the `_set_public_api_base_env` autouse
#: fixture in the sibling `test_application_publish_dispatch.py`.
_PUBLIC_API_BASE = "https://api.jabaki.nl"


@pytest.fixture(autouse=True)
def _set_public_api_base_env(monkeypatch):
    """Set the publish-time `PUBLIC_API_BASE_URL` for every test in this module (bugfix Task 3.1).

    The shared publish render step now resolves the public API base from this env var fail-fast
    (no silent default), so the already-slugged publish-path preservation tests require it to be
    set to exercise their intended `PublishPipelineNotWired` path. This is the legitimate
    change-with-tests update the shared-path change requires; the assertions below are unchanged.
    """
    monkeypatch.setenv(PUBLIC_API_BASE_ENV_VAR, _PUBLIC_API_BASE)


# ══════════════════════════════════════════════════════════════════════════════════════
# In-memory seams (no boto3 / no AWS) — mirror the established sibling test patterns.
# ══════════════════════════════════════════════════════════════════════════════════════


class _FakeClientError(Exception):
    """Stand-in for botocore's ClientError with the ``.response`` shape the store reads
    (mirrors ``test_application_publish_dispatch.py``)."""

    def __init__(self, code, status, message="boom"):
        self.response = {
            "Error": {"Code": code, "Message": message},
            "ResponseMetadata": {"HTTPStatusCode": status},
        }
        super().__init__(f"{code}: {message}")


class _ConditionalFakeS3:
    """In-memory S3 client that HONOURS ``If-None-Match: *`` + get/delete — so the REAL
    ``S3SlugMarkerStore.claim`` exercises its real idempotent/clobber logic (NOT a mock)."""

    def __init__(self):
        self.objects: dict[tuple, dict] = {}
        self.put_calls: list[dict] = []

    def put_object(
        self, *, Bucket, Key, Body, ContentType=None, Metadata=None, IfNoneMatch=None
    ):
        self.put_calls.append({"Key": Key, "IfNoneMatch": IfNoneMatch})
        key = (Bucket, Key)
        if IfNoneMatch == "*" and key in self.objects:
            raise _FakeClientError("PreconditionFailed", 412, "object exists")
        self.objects[key] = {
            "body": Body
            if isinstance(Body, (bytes, bytearray))
            else str(Body).encode("utf-8"),
            "meta": dict(Metadata or {}),
        }
        return {}

    def get_object(self, *, Bucket, Key):
        key = (Bucket, Key)
        if key not in self.objects:
            raise _FakeClientError("NoSuchKey", 404, "missing")
        obj = self.objects[key]
        return {"Body": io.BytesIO(obj["body"]), "Metadata": dict(obj["meta"])}

    def delete_object(self, *, Bucket, Key):
        self.objects.pop((Bucket, Key), None)
        return {}


class FakeSlugReader:
    """In-memory ``FormSlugReader`` — returns a configured stored slug."""

    def __init__(self, slug):
        self._slug = slug

    def get_form_slug(self, tenant_id):
        return self._slug


class FakeFieldConfigReader:
    """In-memory ``PublicFieldConfigReader`` — a schema with ``n`` on-form fields."""

    def __init__(self, on_form_field_count):
        self._n = on_form_field_count

    def get_public_field_config(self, tenant_id):
        return {
            "tenant_id": tenant_id,
            "fields": [{"key": f"f{i}"} for i in range(self._n)],
            "locales": ["nl", "en"],
        }


class FakePrefixReader:
    """In-memory ``PublicPrefixReader`` — returns a configured public prefix."""

    def __init__(self, prefix):
        self._prefix = prefix

    def get_public_prefix(self, tenant_id):
        return self._prefix


class FakeConfigTable:
    """In-memory DynamoDB Table stand-in supporting BOTH the reader's ``query`` and the write
    repository's ``put_item`` / ``update_item`` over one partition-keyed store.

    Mirrors the sibling ``FakeTable`` / ``RecordingFakeTable`` fakes (no boto3, no AWS). It is just
    rich enough to let the REAL reader + REAL write service round-trip a ``config#fields`` row,
    which is what the publish-state carry-through observation (R3.4) requires against the real
    ``h-dcn`` row.
    """

    def __init__(self):
        self.store: dict[tuple, dict] = {}

    def put(self, item: dict) -> None:
        self.store[(item[schema.PARTITION_KEY_ATTR], item[schema.SORT_KEY_ATTR])] = (
            dict(item)
        )

    # reader side -----------------------------------------------------------------------
    def query(self, KeyConditionExpression=None, ConsistentRead=None):
        tenant_id = KeyConditionExpression.get_expression()["values"][1]
        return {"Items": [dict(v) for k, v in self.store.items() if k[0] == tenant_id]}

    # write side (whole-record put_config primitive) ------------------------------------
    def put_item(self, Item=None):
        self.store[(Item[schema.PARTITION_KEY_ATTR], Item[schema.SORT_KEY_ATTR])] = (
            dict(Item)
        )
        return {}


class RecordingFakeRepository:
    """Records every ``apply_ops`` call so a test can assert the emitted identity Change-Ops
    (mirrors ``test_config_fields_crud_service.py``). No boto3, no update_item."""

    def __init__(self):
        self.calls: list[dict] = []

    def apply_ops(self, *, tenant_id, config_id, ops, base_version, client_op_id=None):
        self.calls.append(
            {
                "tenant_id": tenant_id,
                "config_id": config_id,
                "ops": list(ops),
                "base_version": base_version,
                "client_op_id": client_op_id,
            }
        )
        return {"version": "v-next", "idempotent_replay": False}

    @property
    def last(self) -> dict:
        assert self.calls, "apply_ops was never called"
        return self.calls[-1]


class FakeCrudReader:
    """Reader for the Change-Op placement/version mechanics (mirrors the sibling CRUD test's
    ``FakeReader``) — serves a canned WIRE overlay + the control-plane version read."""

    def __init__(self, row=None):
        self._row = row

    def get_raw_fields_overlay(self, tenant_id, *, consistent_read=False):
        if not self._row:
            return {}
        return {k: v for k, v in self._row.items() if k != "version"}

    def get_config_fields_version(self, tenant_id, *, consistent_read=False):
        if not self._row:
            return (False, None)
        return (True, self._row.get("version"))


class RecordingWriteRepo:
    """In-memory ``MembersConfigWriteRepository`` stand-in recording ``put_config`` calls
    (mirrors ``test_config_write_service.py``)."""

    def __init__(self):
        self.calls: list[dict] = []

    def put_config(self, tenant_id, config_id, attributes, version):
        self.calls.append(
            {
                "tenant_id": tenant_id,
                "config_id": config_id,
                "attributes": attributes,
                "version": version,
            }
        )
        return {"tenant_id": tenant_id, "config_id": config_id, **attributes}


# ══════════════════════════════════════════════════════════════════════════════════════
# Strategies — valid, non-bug-condition inputs (an already-authored, prefix-owned slug; a
# non-slug application toggle; valid mail scalars).
# ══════════════════════════════════════════════════════════════════════════════════════

#: A tenant public prefix (lowercase/charset the slug format allows), used as the slug stem.
_PREFIX = st.text(
    alphabet="abcdefghijklmnopqrstuvwxyz0123456789", min_size=3, max_size=12
).filter(lambda s: s[0].isalpha())

#: A slug TAIL segment joined under the prefix (so the slug is prefix-owned, SEC-4 grandfathered).
_TAIL = st.text(
    alphabet="abcdefghijklmnopqrstuvwxyz0123456789", min_size=1, max_size=10
)


@st.composite
def _prefixed_slug(draw):
    """An already-authored, well-formed slug that sits UNDER the tenant's own public prefix.

    This is the NON-bug input for R3.1: a tenant that already OWNS a valid stored slug. The slug is
    ``{prefix}-{tail}`` so it starts with the tenant prefix (SEC-4 prefix-ownership passes), and
    uses only the lowercase/charset the shared ``validate_slug_format`` accepts.
    """
    prefix = draw(_PREFIX)
    tail = draw(_TAIL)
    return prefix, f"{prefix}-{tail}"


# ══════════════════════════════════════════════════════════════════════════════════════
# R3.1 — already-slugged publish gate + `_slugs/{slug}` claim behave exactly as today.
#
# OBSERVED on the UNFIXED code: a tenant with a valid stored slug + certified sender + an on-form
# field PASSES the readiness gate (the NO_SLUG refusal does NOT apply), the publish path CLAIMS
# `_slugs/{slug}` for the SAM owner body, and a same-owner re-publish is idempotent. The fix is
# ADDITIVE (a new author path) and must leave every one of these unchanged.
# ══════════════════════════════════════════════════════════════════════════════════════


def _publish_service(
    slug, prefix, *, store=None, fields=1, certified=True, domain="h-dcn.nl"
):
    """A publish service wired exactly like the Task-8.1 shape: REAL marker store (over the
    conditional fake) + prefix reader, so the claim step is active."""
    marker_store = (
        store
        if store is not None
        else S3SlugMarkerStore(client=_ConditionalFakeS3(), bucket=_CLAIM_BUCKET)
    )
    svc = ApplicationPublishService(
        slug_reader=FakeSlugReader(slug),
        readiness_provider=StaticMailReadinessProvider({_TENANT: (certified, domain)}),
        field_config_reader=FakeFieldConfigReader(fields),
        slug_marker_store=marker_store,
        prefix_reader=FakePrefixReader(prefix),
    )
    return svc, marker_store


@settings(max_examples=80)
@given(data=_prefixed_slug())
def test_preserve_already_slugged_publish_passes_gate_and_claims_marker(data):
    """R3.1: an already-slugged tenant's publish gate + `_slugs/{slug}` claim are unchanged.

    For ANY already-authored prefix-owned slug, the readiness gate passes (NO_SLUG never applies),
    the publish path renders + CLAIMS the marker with the SAM owner body, then reaches the still-
    dormant live-write seam. This is the preserved path — the fix must not alter it.

    Validates (bugfix): Requirement 3.1
    """
    prefix, slug = data
    svc, store = _publish_service(slug, prefix)

    # A fully-ready, already-slugged tenant reaches the dormant live-write seam (gate passed,
    # render + claim ran) — the NO_SLUG refusal does NOT apply (that is the bug-condition tenant).
    with pytest.raises(PublishPipelineNotWired) as exc:
        svc.publish(_TENANT)
    assert exc.value.slug == slug

    # The marker was claimed for the SAM form owner body — identical to today's claim-at-publish.
    marker = store.resolve(slug)
    assert marker is not None
    assert marker.owner_plane == FORM_OWNER_PLANE == "sam"
    assert marker.kind == FORM_OWNER_KIND == "application_form"
    assert marker.tenant_id == _TENANT
    assert marker.resource_ref == FORM_RESOURCE_REF == "config#fields"


@settings(max_examples=80)
@given(data=_prefixed_slug())
def test_preserve_already_slugged_same_owner_republish_is_idempotent(data):
    """R3.1: a same-owner re-publish of an already-stored slug is idempotent (no conflict), with
    exactly ONE marker left in place — the unchanged claim idempotency.

    Validates (bugfix): Requirement 3.1
    """
    prefix, slug = data
    svc, store = _publish_service(slug, prefix)

    with pytest.raises(PublishPipelineNotWired):
        svc.publish(_TENANT)
    with pytest.raises(PublishPipelineNotWired):
        svc.publish(_TENANT)  # idempotent re-claim, NOT a conflict

    marker = store.resolve(slug)
    assert marker is not None and marker.tenant_id == _TENANT
    # Exactly one control-plane marker object — no duplicate / clobber.
    markers = [k for (_b, k) in store._client.objects if k.startswith("_slugs/")]
    assert markers == [f"_slugs/{slug}"]


def test_preserve_get_form_slug_reads_stored_slug_unchanged():
    """R3.1: `MembersProjectionReader.get_form_slug` reads a stored `config#fields.slug` back
    verbatim (trimmed) — the SAM forward read the publish gate relies on is unchanged.

    Validates (bugfix): Requirement 3.1
    """
    table = FakeConfigTable()
    table.put(
        {
            schema.PARTITION_KEY_ATTR: _TENANT,
            schema.SORT_KEY_ATTR: schema.build_sort_key(
                schema.RECORD_TYPE_CONFIG, "fields"
            ),
            "fields": {},
            "overrides": {},
            "slug": "  hdcn-aanmelden  ",
            schema.VERSION_ATTR: 1,
        }
    )
    assert (
        MembersProjectionReader(table=table).get_form_slug(_TENANT) == "hdcn-aanmelden"
    )


# ══════════════════════════════════════════════════════════════════════════════════════
# R3.3 — non-slug `config#fields` Change-Op (`set_field_application`) + `config#mail` write
# round-trip unchanged. The slug-author path is ADDITIVE; these existing writes must behave
# exactly as observed on the UNFIXED code.
# ══════════════════════════════════════════════════════════════════════════════════════

#: The four application attributes `set_field_application` owns (disjoint surface).
_APP_ATTR_KEYS = ("application_visible", "application_required")


@settings(max_examples=80)
@given(
    visible=st.booleans(),
    required=st.booleans(),
)
def test_preserve_set_field_application_emits_identity_change_op(visible, required):
    """R3.3: a non-slug `config#fields` Change-Op (`set_field_application` on a base field) emits
    a SINGLE identity-addressed `SET overrides.<dotted>.<attr>` op per attribute — never a whole-
    record replace, never a slug op. Observed unchanged on the UNFIXED code.

    `membership.status` is a base field → it is placed under the `overrides` map by its dotted key.

    Validates (bugfix): Requirement 3.3
    """
    repo = RecordingFakeRepository()
    # A reader whose row already has the override entry → placement chooses the UPDATE (per-aspect)
    # verb, so each attribute becomes its own scoped SET op (the identity Change-Op contract).
    row = {
        "fields": {},
        "fixed_overrides": {"membership.status": {}},
        "functional_groups": {},
        "version": "v-1",
    }
    svc = ConfigFieldsCrudService(repo, reader=FakeCrudReader(row))

    svc.set_field_application(
        _TENANT,
        "status",
        {"application_visible": visible, "application_required": required},
    )

    call = repo.last
    assert call["tenant_id"] == _TENANT
    assert call["config_id"] == "fields"
    # Every emitted op is a scoped SET addressing ONE identity path under `overrides` — no whole-
    # record replace, no `slug` path, no path outside this field's override entry.
    for op in call["ops"]:
        assert op["action"] == SET
        assert op["path"][0] == "overrides"
        assert op["path"][1] == "membership.status"
        assert op["path"][2] in ("application_visible", "application_required")
    paths = {op["path"][2]: op["value"] for op in call["ops"]}
    assert paths == {"application_visible": visible, "application_required": required}


def test_preserve_set_field_application_rejects_definition_attr_unchanged():
    """R3.3: the disjointness barrier is unchanged — `set_field_application` still REJECTS a
    definition attribute (the fix adds a slug op elsewhere, it does not widen this surface).

    Validates (bugfix): Requirement 3.3
    """
    from sam.members.domain.config_fields_crud_service import ConfigFieldsCrudError

    repo = RecordingFakeRepository()
    svc = ConfigFieldsCrudService(repo)
    with pytest.raises(ConfigFieldsCrudError):
        svc.set_field_application(_TENANT, "status", {"label": {"en": "X"}})
    assert repo.calls == []  # nothing written on a surface violation


@settings(max_examples=80)
@given(
    mail_enabled=st.booleans(),
    mail_certified=st.booleans(),
    domain=st.sampled_from(["h-dcn.nl", "example.org", "acme.test"]),
    local_part=st.sampled_from(["noreply", "info", "aanmelden"]),
)
def test_preserve_config_mail_write_round_trips_unchanged(
    mail_enabled, mail_certified, domain, local_part
):
    """R3.3: a `config#mail` write round-trips through `ConfigWriteService` unchanged — the slug
    author path does not touch the mail validator. Observed on the UNFIXED code.

    Validates (bugfix): Requirement 3.3
    """
    repo = RecordingWriteRepo()
    svc = ConfigWriteService(repo, version_fn=lambda: "v-mail")
    result = svc.put_config(
        _TENANT,
        "mail",
        {
            "mail_enabled": mail_enabled,
            "mail_certified": mail_certified,
            "mail_domain": domain,
            "mail_local_part": local_part,
        },
    )

    assert result == {"success": True, "configId": "mail", "version": "v-mail"}
    attrs = repo.calls[0]["attributes"]
    # Fail-closed gates preserve only an explicit boolean; the fixtures already pass booleans.
    assert attrs["mail_enabled"] is mail_enabled
    assert attrs["mail_certified"] is mail_certified
    assert attrs["mail_domain"] == domain
    assert attrs["mail_local_part"] == local_part
    # A mail write never authors a slug or any config#fields overlay slice.
    assert "slug" not in attrs
    assert "fields" not in attrs


# ══════════════════════════════════════════════════════════════════════════════════════
# R3.4 — publish-state (`published_at` / `published_version`) is carried through a fields write
# (the current carry-through contract), proven against the REAL `h-dcn` `config#fields` row
# (steering 39), NOT a hand-built fixture.
#
# OBSERVED on the UNFIXED code: `ConfigWriteService._author_form_slug` reads the current stored row
# and CARRIES `published_at` / `published_version` through on every fields save (publish owns them,
# never a plain save). A (hypothetical) slug change in the body therefore leaves publish-state
# untouched. This is the carry-through the fix must preserve.
# ══════════════════════════════════════════════════════════════════════════════════════


def _seed_real_hdcn_row(
    table: FakeConfigTable, *, slug, published_at, published_version
):
    """Seed the shared fake table with the REAL h-dcn `config#fields` overlay PLUS slug +
    publish-state (steering 39 — real row, not a hand-built fixture)."""
    overlay = _load_real_overlay()
    item = {
        schema.PARTITION_KEY_ATTR: overlay["tenant_id"],
        schema.SORT_KEY_ATTR: schema.build_sort_key(
            schema.RECORD_TYPE_CONFIG, "fields"
        ),
        "fields": overlay["fields"],
        "overrides": overlay["overrides"],
        "functional_groups": overlay["functional_groups"],
        schema.VERSION_ATTR: 1,
    }
    if slug is not None:
        item["slug"] = slug
    if published_at is not None:
        item["published_at"] = published_at
    if published_version is not None:
        item["published_version"] = published_version
    table.put(item)


def _write_service_over(table: FakeConfigTable) -> ConfigWriteService:
    """A REAL `ConfigWriteService` wired to a REAL reader + REAL write repository over the shared
    fake table, so a fields write genuinely round-trips (read current → merge → put)."""
    repo = MembersConfigWriteRepository(table=table)
    return ConfigWriteService(
        repo,
        version_fn=lambda: "2026-11-01T00:00:00+00:00",
        overlay_reader_factory=lambda: MembersProjectionReader(table=table),
    )


def test_preserve_published_state_carried_through_slug_change_real_hdcn_row():
    """R3.4: a (hypothetical) slug change on the REAL h-dcn row leaves the existing
    `published_at` / `published_version` untouched — the current carry-through contract.

    Round-trip against the REAL `h-dcn` `config#fields` row (steering 39): seed it with a stored
    slug + publish-state, write a NEW slug through the fields body, then read the row back and
    assert publish-state is carried through BYTE-UNCHANGED while the slug updated.

    Validates (bugfix): Requirement 3.4
    """
    table = FakeConfigTable()
    _seed_real_hdcn_row(
        table,
        slug="hdcn-aanmelden",
        published_at="2026-10-01T12:00:00+00:00",
        published_version="2026-10-01T12:00:00+00:00",
    )
    svc = _write_service_over(table)

    # A fields write carrying a DIFFERENT slug (the hypothetical change) — no publish-state in body.
    svc.put_config(_TENANT, "fields", {"slug": "hdcn-inschrijven"})

    stored = table.store[
        (_TENANT, schema.build_sort_key(schema.RECORD_TYPE_CONFIG, "fields"))
    ]
    # The slug changed as authored ...
    assert stored["slug"] == "hdcn-inschrijven"
    # ... but publish-state is carried through UNCHANGED (publish owns it, a fields save never
    # fabricates or wipes it).
    assert stored["published_at"] == "2026-10-01T12:00:00+00:00"
    assert stored["published_version"] == "2026-10-01T12:00:00+00:00"
    # And the real overlay slices survived the merge-on-write (no truncation) — a spot-check of the
    # real row's known fields/overrides.
    assert "payment_method" in stored["fields"]
    assert "personal.email" in stored["overrides"]


def test_preserve_never_published_row_carries_none_publish_state_real_hdcn_row():
    """R3.4: on the REAL h-dcn row with NO publish-state (the verified `h-dcn` state — never
    published), a fields write carries `published_*` through as `None` — it never fabricates them.

    Validates (bugfix): Requirement 3.4
    """
    table = FakeConfigTable()
    _seed_real_hdcn_row(table, slug=None, published_at=None, published_version=None)
    svc = _write_service_over(table)

    svc.put_config(_TENANT, "fields", {"slug": "hdcn-aanmelden"})

    stored = table.store[
        (_TENANT, schema.build_sort_key(schema.RECORD_TYPE_CONFIG, "fields"))
    ]
    assert stored["slug"] == "hdcn-aanmelden"
    # Never-published → carried through as None, NOT fabricated.
    assert stored["published_at"] is None
    assert stored["published_version"] is None


def test_preserve_fields_save_without_slug_key_leaves_stored_slug_untouched_real_hdcn_row():
    """R3.4 (companion): a non-slug fields save (body OMITS `slug`) carries the stored slug AND
    publish-state through untouched — the additive slug path does not disturb a plain fields save.

    Validates (bugfix): Requirements 3.3, 3.4
    """
    table = FakeConfigTable()
    _seed_real_hdcn_row(
        table,
        slug="hdcn-aanmelden",
        published_at="2026-10-01T12:00:00+00:00",
        published_version="2026-10-01T12:00:00+00:00",
    )
    svc = _write_service_over(table)

    # A plain fields save that does NOT carry a slug key (e.g. a field-config edit).
    svc.put_config(_TENANT, "fields", {"fields": {}, "overrides": {}})

    stored = table.store[
        (_TENANT, schema.build_sort_key(schema.RECORD_TYPE_CONFIG, "fields"))
    ]
    # Slug carried through unchanged (body omitted it), publish-state carried through unchanged.
    assert stored["slug"] == "hdcn-aanmelden"
    assert stored["published_at"] == "2026-10-01T12:00:00+00:00"
    assert stored["published_version"] == "2026-10-01T12:00:00+00:00"


# ══════════════════════════════════════════════════════════════════════════════════════
# R3.2 — the Flask landing plane is NOT modified by this fix. Observed as a STRUCTURAL boundary:
# the SAM slug-lifecycle surfaces (publish service, slug marker store, config CRUD/write services)
# never import the Flask landing module. The landing module lives on the OTHER plane; a SAM import
# of it would be a cross-plane leak AND a sign the fix reached into landing.
# ══════════════════════════════════════════════════════════════════════════════════════

_SAM_SLUG_LIFECYCLE_MODULES = (
    "sam.members.domain.application_publish",
    "sam.members.domain.config_fields_crud_service",
    "sam.members.domain.config_write_service",
    "sam.members.domain.form_slug",
    "sam.members.repository.slug_marker_store",
    "sam.members.repository.projection_config_reader",
)

#: Flask landing-plane module name fragments the SAM slug lifecycle must never import (R3.2 /
#: spec 14 Scope decision — the landing module is untouched).
_LANDING_PLANE_FRAGMENTS = (
    "landing_page_service",
    "landing_page_routes",
    "tenant_slug_service",
    "tenant_slugs",
)


@pytest.mark.parametrize("module_name", _SAM_SLUG_LIFECYCLE_MODULES)
def test_preserve_sam_slug_lifecycle_never_imports_flask_landing_plane(module_name):
    """R3.2: no SAM slug-lifecycle module transitively imports the Flask landing plane — the
    landing module (`/api/landing/slug`, `landing_page_service.py`, `tenant_slugs`) is untouched.

    Observed on the UNFIXED code (true today) and must stay true after the fix: the SAM author/
    display/gate path sources the slug from SAM state, never from the Flask plane. Importing the
    module and scanning `sys.modules` for a landing-plane module catches any transitive leak.

    Validates (bugfix): Requirement 3.2
    """
    before = set(sys.modules)
    importlib.import_module(module_name)
    # Inspect everything loaded (the target + anything it pulled in).
    loaded = set(sys.modules) | before
    leaked = [
        name
        for name in loaded
        if any(frag in name for frag in _LANDING_PLANE_FRAGMENTS)
    ]
    assert leaked == [], (
        f"{module_name} must not import the Flask landing plane (R3.2 — landing untouched); "
        f"leaked landing-plane modules: {leaked}"
    )
