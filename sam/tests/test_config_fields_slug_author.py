"""
bugfix-slug-lifecycle Task 3.1 — unit tests for the SAM slug-author Change-Op.

Parent spec: `.kiro/specs/Members/14 - public-pages-multi-tenant-serving`.
Bugfix spec: `.kiro/specs/Members/14 .../bugfix-slug-lifecycle` (design.md §Fix Implementation).

What this asserts (the task-3.1 backend domain op `ConfigFieldsCrudService.set_form_slug`)
------------------------------------------------------------------------------------------
The MISSING client-reachable SAM slug WRITE (defect B). The op must, for a VALID authored slug:
format/reserved-validate (R2.3) → SEC-4 prefix-ownership-validate → claim `_slugs/{slug}` for the
SAM form owner → persist `config#fields.slug` via a SINGLE identity Change-Op (`SET slug`), NEVER a
whole-record replace, carrying `published_*` through by construction (the op names only `slug`).

- format/reserved rejection → `SlugAuthorRejected` (no claim, no write);
- prefix-ownership rejection → `SlugAuthorRejected` (no claim, no write);
- grandfathered same-owner re-author passes the prefix rule (an established slug is never
  force-renamed, R2.5);
- foreign-owner conflict → `SlugAuthorConflict` (no clobber, no write);
- a valid claim persists exactly ONE top-level `SET slug` Change-Op via `apply_ops`;
- an explicit `null` / blank CLEARS the slug with a scoped `REMOVE slug` (no claim).

The marker store is the REAL `S3SlugMarkerStore` over a conditional-honouring in-memory fake S3
client (the sibling `test_slug_lifecycle_preservation.py` pattern — real claim semantics, never a
trivially-succeeding mock). The write repository is an in-memory `RecordingFakeRepository`. No
boto3, no AWS (steering 35/39).

Validates (bugfix): Requirements 2.3, 2.4, 3.3, 3.4
"""

from __future__ import annotations

import io
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

from sam.members.domain.config_fields_crud_service import (
    SLUG_OWNER_KIND,
    SLUG_OWNER_PLANE,
    SLUG_RESOURCE_REF,
    ConfigFieldsCrudError,
    ConfigFieldsCrudService,
    SlugAuthorConflict,
    SlugAuthorRejected,
)
from sam.members.repository.projection_config_write_repository import REMOVE, SET
from sam.members.repository.slug_marker_store import S3SlugMarkerStore, SlugMarker

_TENANT = "h-dcn"
_PREFIX = "h-dcn"
_BUCKET = "myadmin-public-pages-test"


# ── In-memory seams (no boto3 / no AWS) — mirror the sibling test patterns ─────────────


class _FakeClientError(Exception):
    """botocore ClientError stand-in with the `.response` shape the store reads."""

    def __init__(self, code, status, message="boom"):
        self.response = {
            "Error": {"Code": code, "Message": message},
            "ResponseMetadata": {"HTTPStatusCode": status},
        }
        super().__init__(f"{code}: {message}")


class _ConditionalFakeS3:
    """In-memory S3 client HONOURING `If-None-Match: *` + get/delete so the REAL store's
    claim idempotency / clobber logic runs (NOT a mock)."""

    def __init__(self):
        self.objects: dict[tuple, dict] = {}

    def put_object(
        self, *, Bucket, Key, Body, ContentType=None, Metadata=None, IfNoneMatch=None
    ):
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


class RecordingFakeRepository:
    """Records every `apply_ops` call (mirrors the sibling CRUD test). No boto3."""

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


class FakePrefixReader:
    """In-memory `PublicPrefixReader` — returns a configured public prefix."""

    def __init__(self, prefix):
        self._prefix = prefix

    def get_public_prefix(self, tenant_id):
        return self._prefix


def _service(*, prefix=_PREFIX, store=None, repo=None):
    store = (
        store
        if store is not None
        else S3SlugMarkerStore(client=_ConditionalFakeS3(), bucket=_BUCKET)
    )
    repo = repo if repo is not None else RecordingFakeRepository()
    svc = ConfigFieldsCrudService(
        repo,
        slug_marker_store=store,
        prefix_reader=FakePrefixReader(prefix),
    )
    return svc, store, repo


# ── The op EXISTS and is a public method named with "slug" (the exploration test's hook) ──


def test_set_form_slug_is_a_public_method():
    assert hasattr(ConfigFieldsCrudService, "set_form_slug")


# ── Valid author: validate → claim → single identity Change-Op ─────────────────────────


def test_set_form_slug_valid_claims_marker_and_persists_single_identity_op():
    svc, store, repo = _service()

    result = svc.set_form_slug(_TENANT, "h-dcn-aanmelden")

    assert result == {"version": "v-next", "idempotent_replay": False}
    # The marker was claimed for the SAM form owner body (identical owner to the publish path).
    marker = store.resolve("h-dcn-aanmelden")
    assert marker is not None
    assert marker.owner_plane == SLUG_OWNER_PLANE == "sam"
    assert marker.kind == SLUG_OWNER_KIND == "application_form"
    assert marker.tenant_id == _TENANT
    assert marker.resource_ref == SLUG_RESOURCE_REF == "config#fields"
    # EXACTLY one op — a top-level `SET slug` identity Change-Op (never a whole-record replace).
    call = repo.last
    assert call["tenant_id"] == _TENANT
    assert call["config_id"] == "fields"
    assert call["ops"] == [
        {"action": SET, "path": ["slug"], "value": "h-dcn-aanmelden"}
    ]


def test_set_form_slug_op_names_only_slug_so_published_state_is_untouched():
    # The op must address ONLY the `slug` path — DynamoDB then leaves published_*/ every slice
    # physically untouched (R3.4 carry-through BY CONSTRUCTION). Assert no op names a published_*
    # / fields / overrides / functional_groups path.
    svc, _store, repo = _service()
    svc.set_form_slug(_TENANT, "h-dcn-x")
    for op in repo.last["ops"]:
        assert op["path"] == ["slug"]


def test_set_form_slug_trims_whitespace_before_claim_and_persist():
    svc, store, repo = _service()
    svc.set_form_slug(_TENANT, "  h-dcn-aanmelden  ")
    assert store.resolve("h-dcn-aanmelden") is not None
    assert repo.last["ops"][0]["value"] == "h-dcn-aanmelden"


def test_set_form_slug_forwards_client_op_id():
    svc, _store, repo = _service()
    svc.set_form_slug(_TENANT, "h-dcn-x", client_op_id="op-123")
    assert repo.last["client_op_id"] == "op-123"


# ── Format / reserved rejection (no claim, no write) ───────────────────────────────────


@pytest.mark.parametrize(
    "bad",
    ["H-DCN", "-bad", "bad-", "a", "has space", "admin"],
)
def test_set_form_slug_malformed_or_reserved_rejected_no_claim_no_write(bad):
    svc, store, repo = _service()
    with pytest.raises(SlugAuthorRejected):
        svc.set_form_slug(_TENANT, bad)
    assert repo.calls == []  # nothing persisted
    # no marker claimed
    assert all(not k.startswith("_slugs/") for (_b, k) in store._client.objects)


def test_set_form_slug_non_string_rejected():
    svc, _store, repo = _service()
    with pytest.raises(SlugAuthorRejected):
        svc.set_form_slug(_TENANT, 123)  # type: ignore[arg-type]
    assert repo.calls == []


# ── SEC-4 prefix-ownership rejection (no claim, no write) ──────────────────────────────


def test_set_form_slug_outside_tenant_prefix_rejected():
    svc, store, repo = _service(prefix="h-dcn")
    # Well-formed, but sits under ANOTHER tenant's prefix → SEC-4 reject.
    with pytest.raises(SlugAuthorRejected):
        svc.set_form_slug(_TENANT, "other-tenant-apply")
    assert repo.calls == []
    assert all(not k.startswith("_slugs/") for (_b, k) in store._client.objects)


def test_set_form_slug_prefixless_tenant_new_claim_rejected():
    svc, _store, repo = _service(prefix=None)
    with pytest.raises(SlugAuthorRejected):
        svc.set_form_slug(_TENANT, "h-dcn-aanmelden")
    assert repo.calls == []


def test_set_form_slug_exact_prefix_is_allowed():
    svc, store, repo = _service(prefix="h-dcn")
    svc.set_form_slug(_TENANT, "h-dcn")  # slug == prefix exactly
    assert store.resolve("h-dcn") is not None
    assert repo.last["ops"][0]["value"] == "h-dcn"


# ── Grandfathered same-owner re-author (established slug not force-renamed) ─────────────


def test_set_form_slug_grandfathered_same_owner_reauthor_is_idempotent():
    # Pre-seed the tenant's OWN marker for a slug that does NOT satisfy the current prefix rule
    # (legacy), then re-author it: the grandfather short-circuit lets it through the prefix check,
    # and the same-owner claim is idempotent (no conflict), with the slug persisted.
    store = S3SlugMarkerStore(client=_ConditionalFakeS3(), bucket=_BUCKET)
    own = SlugMarker(
        owner_plane=SLUG_OWNER_PLANE,
        kind=SLUG_OWNER_KIND,
        tenant_id=_TENANT,
        resource_ref=SLUG_RESOURCE_REF,
    )
    store.claim(
        "legacyslug", own
    )  # an already-live, non-prefixed slug owned by this tenant
    svc, store, repo = _service(prefix="h-dcn", store=store)

    svc.set_form_slug(_TENANT, "legacyslug")  # re-author the established slug

    assert repo.last["ops"] == [
        {"action": SET, "path": ["slug"], "value": "legacyslug"}
    ]
    # Still exactly one marker (idempotent re-claim, no duplicate/clobber).
    markers = [k for (_b, k) in store._client.objects if k.startswith("_slugs/")]
    assert markers == ["_slugs/legacyslug"]


# ── Foreign-owner conflict (clobber backstop — no write) ───────────────────────────────


def test_set_form_slug_foreign_owner_conflict_no_clobber_no_write():
    store = S3SlugMarkerStore(client=_ConditionalFakeS3(), bucket=_BUCKET)
    # A DIFFERENT tenant already owns `h-dcn-aanmelden` under the SAM form kind.
    foreign = SlugMarker(
        owner_plane="sam",
        kind="application_form",
        tenant_id="some-other-tenant",
        resource_ref="config#fields",
    )
    store.claim("h-dcn-aanmelden", foreign)
    svc, store, repo = _service(prefix="h-dcn", store=store)

    with pytest.raises(SlugAuthorConflict) as exc:
        svc.set_form_slug(_TENANT, "h-dcn-aanmelden")
    assert exc.value.slug == "h-dcn-aanmelden"
    assert repo.calls == []  # NOTHING persisted
    # The foreign marker is untouched (never clobbered).
    marker = store.resolve("h-dcn-aanmelden")
    assert marker is not None and marker.tenant_id == "some-other-tenant"


# ── Clear with null / blank (scoped REMOVE, no claim) ──────────────────────────────────


@pytest.mark.parametrize("cleared", [None, "", "   "])
def test_set_form_slug_clear_emits_scoped_remove_no_claim(cleared):
    svc, store, repo = _service()
    svc.set_form_slug(_TENANT, cleared)
    assert repo.last["ops"] == [{"action": REMOVE, "path": ["slug"]}]
    # Clearing claims no marker.
    assert all(not k.startswith("_slugs/") for (_b, k) in store._client.objects)


# ── Mis-wired service (no seams) fails loud, never silently persists ───────────────────


def test_set_form_slug_without_seams_fails_loud():
    svc = ConfigFieldsCrudService(RecordingFakeRepository())  # no store / prefix reader
    with pytest.raises(ConfigFieldsCrudError):
        svc.set_form_slug(_TENANT, "h-dcn-aanmelden")


# ══════════════════════════════════════════════════════════════════════════════════════
# bugfix-slug-lifecycle Task 3.2 — change/rename support via the marker-store `rename`.
#
# DECISION: `S3SlugMarkerStore.rename` EXISTS (claim-new-before-release-old, R4.6), so a slug
# CHANGE is LOW-COST and is wired into `set_form_slug`. When the tenant already owns a DIFFERENT
# stored `config#fields.slug`, the op routes the old→new transition through `rename` (claim new,
# persist new, release old) in that safe order, instead of a bare claim that would ORPHAN the old
# `_slugs/{old}` marker. A NEW / same-slug author keeps the task-3.1 bare-claim path.
#
# Change detection reads the tenant's current slug via a forward `get_form_slug(tenant_id)` reader.
# Production's `MembersProjectionReader` exposes BOTH `get_public_prefix` and `get_form_slug`, so it
# serves as both `prefix_reader` and `slug_reader`; these tests use a reader fake that does too.
#
# Validates (bugfix): Requirements 2.3, 2.4
# ══════════════════════════════════════════════════════════════════════════════════════


class FakePrefixAndSlugReader:
    """In-memory reader exposing BOTH `get_public_prefix` and the forward `get_form_slug`.

    Mirrors production's `MembersProjectionReader` (which exposes both): `get_public_prefix` drives
    the SEC-4 prefix check; `get_form_slug` lets `set_form_slug` detect a CHANGE (a different
    currently-stored slug) and route it through `S3SlugMarkerStore.rename`.
    """

    def __init__(self, prefix, current_slug=None):
        self._prefix = prefix
        self._current_slug = current_slug

    def get_public_prefix(self, tenant_id):
        return self._prefix

    def get_form_slug(self, tenant_id):
        return self._current_slug


def _service_with_slug_reader(
    *, prefix=_PREFIX, current_slug=None, store=None, repo=None
):
    """Build a service whose injected reader reports a CURRENT stored slug (change detection)."""
    store = (
        store
        if store is not None
        else S3SlugMarkerStore(client=_ConditionalFakeS3(), bucket=_BUCKET)
    )
    repo = repo if repo is not None else RecordingFakeRepository()
    reader = FakePrefixAndSlugReader(prefix, current_slug=current_slug)
    svc = ConfigFieldsCrudService(
        repo,
        slug_marker_store=store,
        prefix_reader=reader,
    )
    return svc, store, repo


def _own_marker(tenant_id=_TENANT):
    return SlugMarker(
        owner_plane=SLUG_OWNER_PLANE,
        kind=SLUG_OWNER_KIND,
        tenant_id=tenant_id,
        resource_ref=SLUG_RESOURCE_REF,
    )


def _slug_keys(store):
    return sorted(k for (_b, k) in store._client.objects if k.startswith("_slugs/"))


# ── The marker store DOES expose a `rename` (the low-cost precondition this task rests on) ──


def test_marker_store_rename_exists_so_change_is_low_cost():
    # Evidence for the task's "low-cost?" decision: `rename` is present, so a change is handled by
    # rename rather than deferred as a follow-up.
    assert hasattr(S3SlugMarkerStore, "rename")


# ── Change: author a DIFFERENT slug → rename (claim new, persist new, release old) ─────


def test_set_form_slug_change_renames_claims_new_releases_old_and_persists_new():
    store = S3SlugMarkerStore(client=_ConditionalFakeS3(), bucket=_BUCKET)
    # The tenant already owns `h-dcn-aanmelden` (marker present, stored on config#fields).
    store.claim("h-dcn-aanmelden", _own_marker())
    svc, store, repo = _service_with_slug_reader(
        prefix="h-dcn", current_slug="h-dcn-aanmelden", store=store
    )

    svc.set_form_slug(_TENANT, "h-dcn-inschrijven")  # CHANGE to a new slug

    # New marker claimed, OLD marker released — no orphan left behind.
    assert _slug_keys(store) == ["_slugs/h-dcn-inschrijven"]
    new_marker = store.resolve("h-dcn-inschrijven")
    assert new_marker is not None and new_marker.tenant_id == _TENANT
    assert store.resolve("h-dcn-aanmelden") is None
    # The NEW slug is persisted via a single identity Change-Op (never a whole-record replace).
    assert repo.last["ops"] == [
        {"action": SET, "path": ["slug"], "value": "h-dcn-inschrijven"}
    ]


def test_set_form_slug_change_persist_only_names_slug_path():
    store = S3SlugMarkerStore(client=_ConditionalFakeS3(), bucket=_BUCKET)
    store.claim("h-dcn-aanmelden", _own_marker())
    svc, _store, repo = _service_with_slug_reader(
        prefix="h-dcn", current_slug="h-dcn-aanmelden", store=store
    )
    svc.set_form_slug(_TENANT, "h-dcn-inschrijven")
    for op in repo.last["ops"]:
        assert op["path"] == [
            "slug"
        ]  # published_* / every slice untouched by construction


# ── Change SAFE order: a FOREIGN owner of the NEW slug → conflict, OLD intact, no write ─


def test_set_form_slug_change_foreign_new_owner_keeps_old_and_persists_nothing():
    store = S3SlugMarkerStore(client=_ConditionalFakeS3(), bucket=_BUCKET)
    # The tenant owns the OLD slug; a DIFFERENT tenant owns the target NEW slug.
    store.claim("h-dcn-aanmelden", _own_marker())
    store.claim("h-dcn-inschrijven", _own_marker(tenant_id="some-other-tenant"))
    svc, store, repo = _service_with_slug_reader(
        prefix="h-dcn", current_slug="h-dcn-aanmelden", store=store
    )

    with pytest.raises(SlugAuthorConflict) as exc:
        svc.set_form_slug(_TENANT, "h-dcn-inschrijven")
    assert exc.value.slug == "h-dcn-inschrijven"

    # claim-new-before-release-old: the new claim fails FIRST, so the OLD marker is never released
    # (the tenant never ends up with no slug) and the foreign marker is untouched.
    old = store.resolve("h-dcn-aanmelden")
    assert old is not None and old.tenant_id == _TENANT
    foreign = store.resolve("h-dcn-inschrijven")
    assert foreign is not None and foreign.tenant_id == "some-other-tenant"
    assert repo.calls == []  # NOTHING persisted


# ── Same-slug re-author is NOT a rename (its own marker is not released) ────────────────


def test_set_form_slug_same_slug_reauthor_is_not_a_rename():
    store = S3SlugMarkerStore(client=_ConditionalFakeS3(), bucket=_BUCKET)
    store.claim("h-dcn-aanmelden", _own_marker())
    svc, store, repo = _service_with_slug_reader(
        prefix="h-dcn", current_slug="h-dcn-aanmelden", store=store
    )

    svc.set_form_slug(
        _TENANT, "h-dcn-aanmelden"
    )  # re-author the SAME slug (idempotent claim)

    # The marker still exists (not released by a spurious rename) and the slug is persisted.
    assert _slug_keys(store) == ["_slugs/h-dcn-aanmelden"]
    assert store.resolve("h-dcn-aanmelden") is not None
    assert repo.last["ops"] == [
        {"action": SET, "path": ["slug"], "value": "h-dcn-aanmelden"}
    ]


# ── New author with NO prior slug keeps the task-3.1 bare-claim path (no release) ──────


def test_set_form_slug_new_author_no_prior_slug_uses_bare_claim():
    svc, store, repo = _service_with_slug_reader(prefix="h-dcn", current_slug=None)
    svc.set_form_slug(_TENANT, "h-dcn-aanmelden")
    assert _slug_keys(store) == ["_slugs/h-dcn-aanmelden"]
    assert repo.last["ops"] == [
        {"action": SET, "path": ["slug"], "value": "h-dcn-aanmelden"}
    ]


# ── Change detection degrades safely when the reader has no `get_form_slug` (3.1-era fake) ──


def test_set_form_slug_without_forward_reader_still_authors_via_bare_claim():
    # The task-3.1 `_service` helper injects a reader with ONLY `get_public_prefix` — no forward
    # `get_form_slug`. Change detection degrades to "no prior slug" and authoring still works
    # (rename support is strictly additive, never a regression to the 3.1 path).
    svc, store, repo = _service(prefix="h-dcn")
    svc.set_form_slug(_TENANT, "h-dcn-aanmelden")
    assert store.resolve("h-dcn-aanmelden") is not None
    assert repo.last["ops"] == [
        {"action": SET, "path": ["slug"], "value": "h-dcn-aanmelden"}
    ]


# ── Change away then clear is unaffected (clear is a scoped REMOVE, no marker op) ──────


def test_set_form_slug_clear_with_prior_slug_still_scoped_remove_no_rename():
    store = S3SlugMarkerStore(client=_ConditionalFakeS3(), bucket=_BUCKET)
    store.claim("h-dcn-aanmelden", _own_marker())
    svc, store, repo = _service_with_slug_reader(
        prefix="h-dcn", current_slug="h-dcn-aanmelden", store=store
    )

    svc.set_form_slug(_TENANT, None)  # CLEAR

    # Clear is a scoped REMOVE and deliberately does NOT release the marker (teardown/rename owns
    # marker lifecycle) — the marker is left in place, exactly as the task-3.1 clear contract.
    assert repo.last["ops"] == [{"action": REMOVE, "path": ["slug"]}]
    assert _slug_keys(store) == ["_slugs/h-dcn-aanmelden"]


# ══════════════════════════════════════════════════════════════════════════════════════
# set_public_prefix — the SAM-owned slug PREFIX author op (config#fields.public_prefix).
#
# The prefix is the tenant's own public stem under which every form slug must sit (SEC-4). It is
# authored as a SINGLE identity Change-Op on the top-level `public_prefix` path — slug-safe shape,
# no marker claim (a prefix is a namespace, not a globally-unique address). Explicit null/blank
# CLEARS it via a scoped REMOVE. Malformed/reserved → SlugAuthorRejected (same 422 path as slug).
# ══════════════════════════════════════════════════════════════════════════════════════


def test_set_public_prefix_is_a_public_method():
    assert hasattr(ConfigFieldsCrudService, "set_public_prefix")


def test_set_public_prefix_valid_persists_single_identity_op_no_marker_claim():
    svc, store, repo = _service()

    result = svc.set_public_prefix(_TENANT, "h-dcn")

    assert result == {"version": "v-next", "idempotent_replay": False}
    # EXACTLY one op — a top-level `SET public_prefix` identity Change-Op (no whole-record replace).
    call = repo.last
    assert call["tenant_id"] == _TENANT
    assert call["config_id"] == "fields"
    assert call["ops"] == [{"action": SET, "path": ["public_prefix"], "value": "h-dcn"}]
    # No marker is claimed for a prefix (it is not a public address).
    assert not any(k.startswith("_slugs/") for (_b, k) in store._client.objects)


def test_set_public_prefix_op_names_only_public_prefix():
    # Must address ONLY the `public_prefix` path, so slug / published_* / every slice stay
    # physically untouched (never a whole-record replace, steering 39).
    svc, _store, repo = _service()
    svc.set_public_prefix(_TENANT, "acme")
    for op in repo.last["ops"]:
        assert op["path"] == ["public_prefix"]


def test_set_public_prefix_trims_whitespace():
    svc, _store, repo = _service()
    svc.set_public_prefix(_TENANT, "  h-dcn  ")
    assert repo.last["ops"][0]["value"] == "h-dcn"


def test_set_public_prefix_forwards_client_op_id():
    svc, _store, repo = _service()
    svc.set_public_prefix(_TENANT, "h-dcn", client_op_id="op-xyz")
    assert repo.last["client_op_id"] == "op-xyz"


def test_set_public_prefix_none_clears_via_scoped_remove():
    svc, _store, repo = _service()
    svc.set_public_prefix(_TENANT, None)
    assert repo.last["ops"] == [{"action": REMOVE, "path": ["public_prefix"]}]


def test_set_public_prefix_blank_clears_via_scoped_remove():
    svc, _store, repo = _service()
    svc.set_public_prefix(_TENANT, "   ")
    assert repo.last["ops"] == [{"action": REMOVE, "path": ["public_prefix"]}]


def test_set_public_prefix_rejects_uppercase_malformed():
    svc, _store, repo = _service()
    with pytest.raises(SlugAuthorRejected):
        svc.set_public_prefix(_TENANT, "H-DCN")
    assert repo.calls == []  # nothing persisted on a rejection


def test_set_public_prefix_rejects_too_short():
    svc, _store, repo = _service()
    with pytest.raises(SlugAuthorRejected):
        svc.set_public_prefix(_TENANT, "ab")
    assert repo.calls == []


def test_set_public_prefix_rejects_reserved():
    svc, _store, repo = _service()
    with pytest.raises(SlugAuthorRejected):
        svc.set_public_prefix(_TENANT, "admin")
    assert repo.calls == []


def test_set_public_prefix_rejects_leading_hyphen():
    svc, _store, repo = _service()
    with pytest.raises(SlugAuthorRejected):
        svc.set_public_prefix(_TENANT, "-dcn")
    assert repo.calls == []
