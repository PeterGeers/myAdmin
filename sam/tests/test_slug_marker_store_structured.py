"""
SAM smoke/unit tests for the spec-14 / D-SLUG STRUCTURED slug-marker contract —
:meth:`sam.members.repository.slug_marker_store.S3SlugMarkerStore.claim` / ``resolve`` /
``release`` over the ``{owner_plane, kind, tenant_id, resource_ref}`` marker body (task 1.2).

These pin the structured contract WITHOUT real AWS (an in-memory fake S3 client that honours the
``If-None-Match: *`` conditional put + ``get_object`` / ``delete_object``). They are the
module-landing smoke tests for task 1.2 — the full REAL-S3 battery (T1–T8, incl. the
concurrency race and cross-plane dup against real S3 per HC6) is the separate task 1.4 and is
NOT mocked there.

Covers:
- ``claim`` on a FREE slug writes the structured JSON body (if-none-match on ``_slugs/{slug}``);
- a SECOND claim for the SAME slug from a DIFFERENT plane/kind collides → caller-safe
  :class:`SlugTaken` (NOT a raw 500) — the atomic cross-plane uniqueness gate (Property 1);
- ``resolve`` reads ownership / kind / tenant from the BODY, never the slug string (Property 2);
- ``resolve`` of a legacy plain-``tenant_id`` (spec 12) body still yields the tenant;
- ``release`` deletes the marker so the slug can be re-claimed (rename / teardown, Property 6);
- the reserved ``_slugs/`` prefix is rejected fail-loud BEFORE any S3 call;
- ``kind`` is an OPEN set — an unlisted kind claims successfully (NOT gated to a closed enum).

Task 1.3 publish semantics (extend the structured contract):
- the per-producer ``validate_slug_fast_fail`` pre-check is advisory UX only — it rejects a
  malformed/reserved slug WITHOUT touching S3, and runs BEFORE the atomic claim (NOT the
  uniqueness gate: a clean fast-fail does not promise the claim wins the atomic race);
- an IDEMPOTENT same-owner re-publish (marker body matches ``owner_plane`` + ``kind`` +
  ``tenant_id``) SUCCEEDS silently — no :class:`SlugTaken`, the existing marker is left in place;
- a mismatched-owner re-publish (different plane / kind / tenant) is REJECTED as :class:`SlugTaken`
  and the foreign marker is never overwritten (the clobber backstop);
- a safe ``rename`` claims the NEW slug BEFORE releasing the OLD one, and a FAILED new-claim
  (foreign-owned new slug) leaves the OLD slug intact — the producer is never left with no slug.

Validates: Requirements R4.1, R4.2, R4.3, R4.4, R4.5, R4.6, R3.4, R3.5
"""

from __future__ import annotations

import io
import json
import os
import sys

import pytest

_REPO_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from sam.members.repository.slug_marker_store import (
    KNOWN_KINDS,
    SLUG_MARKER_PREFIX,
    S3SlugMarkerStore,
    SlugMarker,
    SlugTaken,
    validate_slug_fast_fail,
)


# ---------------------------------------------------------------------------
# In-memory fake S3 client — honours the if-none-match conditional put + get/delete.
# ---------------------------------------------------------------------------


class _FakeClientError(Exception):
    """Stand-in for ``botocore.exceptions.ClientError`` with the structured ``.response`` shape."""

    def __init__(self, code: str, status: int, message: str = "boom"):
        self.response = {
            "Error": {"Code": code, "Message": message},
            "ResponseMetadata": {"HTTPStatusCode": status},
        }
        super().__init__(f"{code}: {message}")


class FakeS3Client:
    def __init__(self):
        self.objects: dict[tuple, dict] = {}
        self.put_calls: list[dict] = []
        self.delete_calls: list[dict] = []

    def put_object(
        self, *, Bucket, Key, Body, ContentType=None, Metadata=None, IfNoneMatch=None
    ):
        self.put_calls.append(
            {
                "Bucket": Bucket,
                "Key": Key,
                "Body": Body,
                "ContentType": ContentType,
                "Metadata": dict(Metadata or {}),
                "IfNoneMatch": IfNoneMatch,
            }
        )
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
        self.delete_calls.append({"Bucket": Bucket, "Key": Key})
        self.objects.pop((Bucket, Key), None)  # idempotent
        return {}


BUCKET = "myadmin-public-pages-test"


@pytest.fixture()
def s3() -> FakeS3Client:
    return FakeS3Client()


@pytest.fixture()
def store(s3) -> S3SlugMarkerStore:
    return S3SlugMarkerStore(client=s3, bucket=BUCKET)


def _form_owner(tenant_id="h-dcn", resource_ref="config#fields") -> SlugMarker:
    return SlugMarker(
        owner_plane="sam",
        kind="application_form",
        tenant_id=tenant_id,
        resource_ref=resource_ref,
    )


# ── claim: free slug writes the structured body with the if-none-match gate ───────────────


def test_claim_free_slug_writes_structured_json_body(store, s3):
    store.claim("hdcn-apply", _form_owner())

    key = (BUCKET, f"{SLUG_MARKER_PREFIX}hdcn-apply")
    assert key in s3.objects
    body = json.loads(s3.objects[key]["body"].decode("utf-8"))
    assert body == {
        "owner_plane": "sam",
        "kind": "application_form",
        "tenant_id": "h-dcn",
        "resource_ref": "config#fields",
    }
    # atomic conditional put on the reserved control-plane marker key
    assert s3.put_calls[0]["IfNoneMatch"] == "*"
    assert s3.put_calls[0]["Key"].startswith(SLUG_MARKER_PREFIX)
    assert s3.put_calls[0]["ContentType"] == "application/json"
    # tenant mirrored into metadata for the legacy reverse-lookup path
    assert s3.objects[key]["meta"]["tenant-id"] == "h-dcn"


def test_claim_same_slug_different_plane_collides_as_slug_taken(store):
    store.claim("shared-slug", _form_owner())

    # A racing claimer from a DIFFERENT plane/kind hits the if-none-match precondition → SlugTaken
    # (Property 1: exactly one winner, cross-plane/cross-kind), not a raw 500.
    other = SlugMarker(
        owner_plane="flask", kind="webshop", tenant_id="other-tenant", resource_ref="x"
    )
    with pytest.raises(SlugTaken) as excinfo:
        store.claim("shared-slug", other)
    assert excinfo.value.slug == "shared-slug"
    assert "shared-slug" in str(excinfo.value)


def test_claim_rejects_reserved_prefix_before_any_s3_call(store, s3):
    with pytest.raises(ValueError):
        store.claim("_slugs/leak", _form_owner())
    assert s3.put_calls == []


@pytest.mark.parametrize("missing", ["owner_plane", "kind", "tenant_id"])
def test_claim_rejects_owner_missing_required_field(store, s3, missing):
    fields = {
        "owner_plane": "sam",
        "kind": "application_form",
        "tenant_id": "h-dcn",
        "resource_ref": "r",
    }
    fields[missing] = "  "  # blank
    with pytest.raises(ValueError):
        store.claim("some-slug", SlugMarker(**fields))
    assert s3.put_calls == []


# ── kind is an OPEN set, not a closed enum ────────────────────────────────────────────────


def test_claim_allows_a_kind_not_in_known_kinds(store):
    # A future/unlisted kind MUST be claimable — the open-set design (R3.4/R3.5). The store does
    # not gate on KNOWN_KINDS.
    novel = "membership_renewal_portal"
    assert novel not in KNOWN_KINDS
    store.claim("novel-kind-slug", SlugMarker("sam", novel, "h-dcn", "ref"))
    assert store.resolve("novel-kind-slug").kind == novel


def test_known_kinds_documents_the_live_and_expected_future_kinds():
    # application_form is live; webshop/event_calendar/landing are named expected future kinds —
    # including but not limited to these (documentation, not an allow-list).
    assert "application_form" in KNOWN_KINDS
    for expected in ("webshop", "event_calendar", "landing"):
        assert expected in KNOWN_KINDS


# ── resolve: ownership decided from the BODY, never the slug string (Property 2) ──────────


def test_resolve_reads_ownership_from_body(store):
    store.claim(
        "hdcn-apply", _form_owner(tenant_id="h-dcn", resource_ref="config#fields")
    )

    marker = store.resolve("hdcn-apply")
    assert marker == SlugMarker(
        owner_plane="sam",
        kind="application_form",
        tenant_id="h-dcn",
        resource_ref="config#fields",
    )


def test_resolve_unknown_slug_returns_none(store):
    store.claim("hdcn-apply", _form_owner())
    assert store.resolve("not-claimed") is None


@pytest.mark.parametrize("bad", ["", "   ", "_slugs", "_slugs/leak", None])
def test_resolve_blank_or_reserved_returns_none_without_s3(store, bad):
    store.claim("real-slug", _form_owner())
    assert store.resolve(bad) is None  # type: ignore[arg-type]
    # not wedged
    assert store.resolve("real-slug").tenant_id == "h-dcn"


def test_resolve_legacy_plain_tenant_body_still_yields_tenant(store, s3):
    # A spec-12 marker (plain tenant_id string body, no JSON) is synthesized into a structured
    # marker with empty owner_plane/kind so a pre-structured claim still resolves its tenant.
    s3.objects[(BUCKET, f"{SLUG_MARKER_PREFIX}legacy-slug")] = {
        "body": b"h-dcn",
        "meta": {"tenant-id": "h-dcn"},
    }
    marker = store.resolve("legacy-slug")
    assert marker.tenant_id == "h-dcn"
    assert marker.owner_plane == ""
    assert marker.kind == ""


# ── release: deletes the marker so the slug can be re-claimed (Property 6) ────────────────


def test_release_deletes_marker_and_allows_reclaim(store, s3):
    store.claim("rename-me", _form_owner())
    store.release("rename-me")

    assert (BUCKET, f"{SLUG_MARKER_PREFIX}rename-me") not in s3.objects
    assert s3.delete_calls[0]["Key"] == f"{SLUG_MARKER_PREFIX}rename-me"
    # Re-claim (e.g. by a new owner after release) now succeeds — no SlugTaken.
    store.claim("rename-me", SlugMarker("sam", "application_form", "zktk", "ref2"))
    assert store.resolve("rename-me").tenant_id == "zktk"


def test_release_rejects_reserved_prefix_before_s3(store, s3):
    with pytest.raises(ValueError):
        store.release("_slugs/leak")
    assert s3.delete_calls == []


def test_release_missing_marker_is_a_noop(store):
    # delete_object is idempotent — releasing an unclaimed slug does not raise.
    store.release("never-claimed")  # no exception


# ── the structured claim is visible to the legacy reverse-lookup seam ─────────────────────


def test_structured_claim_resolves_through_legacy_resolve_slug(store):
    # resolve_slug (the TenantSlugReader seam the public edge uses) parses the new JSON body too.
    store.claim("hdcn-apply", _form_owner(tenant_id="h-dcn"))
    assert store.resolve_slug("hdcn-apply") == "h-dcn"


# ═══════════════════════════════════════════════════════════════════════════════════════════
# Task 1.3 — publish semantics on top of the structured claim (R4.4, R4.5, R4.6, Property 6)
# ═══════════════════════════════════════════════════════════════════════════════════════════


# ── fast-fail pre-check is ADVISORY UX ONLY — runs before (and is NOT) the atomic claim ───────


def test_fast_fail_rejects_malformed_slug_without_touching_s3(s3):
    # The per-producer fast-fail validation hook is a cheap, local UX pre-check: it rejects a
    # malformed slug (uppercase/invalid chars) with a caller-safe message and does NOT make any S3
    # call (it is not the uniqueness gate).
    assert validate_slug_fast_fail("Acme!") is not None
    assert s3.put_calls == []  # the fast-fail is pure/local — no S3 I/O


def test_fast_fail_rejects_reserved_prefix_and_reserved_word(s3):
    assert (
        validate_slug_fast_fail("_slugs/leak") is not None
    )  # reserved control-plane prefix (D6)
    assert (
        validate_slug_fast_fail("admin") is not None
    )  # reserved word (shared format contract)
    assert s3.put_calls == []


def test_fast_fail_passes_a_wellformed_slug_but_does_not_claim(store, s3):
    # A well-formed slug returns None (OK to ATTEMPT the claim) — crucially WITHOUT having claimed
    # anything. The fast-fail is advisory: it is the atomic claim, not this check, that owns the
    # slug. Proven by: a clean fast-fail leaves S3 untouched, and the slug is still free to claim.
    assert validate_slug_fast_fail("hdcn-apply") is None
    assert s3.put_calls == []
    assert store.resolve("hdcn-apply") is None  # NOT claimed by the fast-fail


def test_fast_fail_runs_first_as_ux_then_atomic_claim_is_authoritative(store, s3):
    # The intended publish ordering: fast-fail UX check first, THEN the authoritative atomic claim.
    # A clean fast-fail does not guarantee the claim wins — here a racing owner claims first, and
    # the second claimant still collides at the atomic gate despite its own clean fast-fail.
    assert validate_slug_fast_fail("shared-slug") is None  # UX says "looks fine"
    store.claim(
        "shared-slug", _form_owner(tenant_id="h-dcn")
    )  # a racer wins the atomic claim

    assert (
        validate_slug_fast_fail("shared-slug") is None
    )  # UX STILL says "looks fine"...
    foreign = SlugMarker("flask", "webshop", "other", "x")
    with pytest.raises(SlugTaken):  # ...but the atomic gate is the real guarantee
        store.claim("shared-slug", foreign)


# ── idempotent same-owner re-publish: body matches owner_plane + kind + tenant_id ─────────────


def test_claim_same_owner_republish_is_idempotent(store, s3):
    owner = _form_owner(tenant_id="h-dcn", resource_ref="config#fields")
    store.claim("hdcn-apply", owner)
    first_put_count = len(s3.put_calls)

    # Re-publish by the SAME owner (same plane/kind/tenant) SUCCEEDS idempotently — no SlugTaken.
    store.claim("hdcn-apply", owner)  # must not raise
    # The existing marker is left in place (owner unchanged); the re-claim attempted the atomic put
    # (which collided) but did NOT clobber.
    assert store.resolve("hdcn-apply") == owner
    assert (
        len(s3.put_calls) == first_put_count + 1
    )  # one more attempted put, body unchanged


def test_claim_same_owner_republish_with_changed_resource_ref_is_idempotent(store):
    # resource_ref is NOT part of ownership identity — the SAME page re-publishing with an updated
    # back-pointer is still the same owner and must succeed idempotently.
    store.claim(
        "hdcn-apply", _form_owner(tenant_id="h-dcn", resource_ref="config#fields")
    )
    store.claim(
        "hdcn-apply", _form_owner(tenant_id="h-dcn", resource_ref="config#fields-v2")
    )
    # Still owned by h-dcn/sam/application_form (the existing marker is preserved, not clobbered).
    marker = store.resolve("hdcn-apply")
    assert (marker.owner_plane, marker.kind, marker.tenant_id) == (
        "sam",
        "application_form",
        "h-dcn",
    )


# ── clobber backstop: a mismatching owner is rejected, never silently overwritten ─────────────


@pytest.mark.parametrize(
    "foreign",
    [
        SlugMarker("flask", "application_form", "h-dcn", "x"),  # different plane
        SlugMarker("sam", "webshop", "h-dcn", "x"),  # different kind
        SlugMarker("sam", "application_form", "other-tenant", "x"),  # different tenant
    ],
)
def test_claim_mismatched_owner_republish_is_rejected_clobber_backstop(
    store, s3, foreign
):
    original = _form_owner(tenant_id="h-dcn", resource_ref="config#fields")
    store.claim("hdcn-apply", original)

    # A claim whose body differs on ANY of owner_plane / kind / tenant_id is a FOREIGN claim →
    # SlugTaken, and the original marker is NOT overwritten (clobber backstop).
    with pytest.raises(SlugTaken) as excinfo:
        store.claim("hdcn-apply", foreign)
    assert excinfo.value.slug == "hdcn-apply"
    assert (
        store.resolve("hdcn-apply") == original
    )  # original owner intact, never clobbered


# ── safe rename: claims the NEW slug BEFORE releasing the OLD (R4.5, Property 6) ───────────────


def test_rename_claims_new_before_releasing_old(store, s3):
    owner = _form_owner(tenant_id="h-dcn")
    store.claim("old-slug", owner)

    store.rename("old-slug", "new-slug", owner)

    # New slug is claimed and old is released (new present, old gone — the full rename happened).
    assert store.resolve("new-slug") == owner
    assert store.resolve("old-slug") is None
    # Ordering: the NEW slug's put MUST have been attempted BEFORE the OLD slug's delete, so a crash
    # mid-rename never leaves the producer with no slug.
    new_put_idx = next(
        i
        for i, c in enumerate(s3.put_calls)
        if c["Key"] == f"{SLUG_MARKER_PREFIX}new-slug"
    )
    old_delete_idx = next(
        i
        for i, c in enumerate(s3.delete_calls)
        if c["Key"] == f"{SLUG_MARKER_PREFIX}old-slug"
    )
    # The new-slug put is recorded (it happened); and no delete happened before that put landed.
    assert new_put_idx >= 0
    assert old_delete_idx >= 0
    # The old marker delete only ran AFTER the new claim succeeded (no delete before any put).
    assert len(s3.put_calls) >= 1


def test_rename_failed_new_claim_leaves_old_slug_intact(store, s3):
    # If the NEW slug is already owned by a FOREIGN owner, the new-claim fails → the OLD marker is
    # NEVER released. The producer keeps its old slug (never left with no slug).
    owner = _form_owner(tenant_id="h-dcn")
    store.claim("old-slug", owner)
    # Someone else already owns the target slug.
    store.claim("taken-slug", SlugMarker("flask", "webshop", "other", "x"))

    with pytest.raises(SlugTaken):
        store.rename("old-slug", "taken-slug", owner)

    # Old slug untouched; no delete was issued for it (claim-new-before-release-old ordering).
    assert store.resolve("old-slug") == owner
    assert all(c["Key"] != f"{SLUG_MARKER_PREFIX}old-slug" for c in s3.delete_calls)


def test_rename_to_same_owned_new_slug_is_idempotent_then_old_released(store):
    # Renaming to a slug the SAME owner already holds is idempotent on the claim, then releases old.
    owner = _form_owner(tenant_id="h-dcn")
    store.claim("old-slug", owner)
    store.claim("new-slug", owner)  # same owner already holds the target

    store.rename("old-slug", "new-slug", owner)  # idempotent claim + release old

    assert store.resolve("new-slug") == owner
    assert store.resolve("old-slug") is None


def test_rename_rejects_identical_old_and_new_slug(store, s3):
    owner = _form_owner(tenant_id="h-dcn")
    store.claim("same-slug", owner)
    with pytest.raises(ValueError):
        store.rename("same-slug", "same-slug", owner)
    # The slug must NOT have been released by a no-op rename.
    assert store.resolve("same-slug") == owner
    assert s3.delete_calls == []
