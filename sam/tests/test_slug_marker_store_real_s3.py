"""
HC6 REAL-S3 battery for the spec-14 / D-SLUG slug-marker store — task 1.4 **T2 + T3**.

:class:`sam.members.repository.slug_marker_store.S3SlugMarkerStore` claim/resolve/release over
the ``_slugs/{slug}`` conditional-PUT (``If-None-Match: *``) mechanism. The cross-plane uniqueness
GUARANTEE *is* that real S3 behaviour, so the two tests that assert it — the cross-plane/kind
duplicate (T2) and the concurrency race (T3) — MUST exercise REAL S3, never an in-memory mock that
simply returns success (HC6; task 1.1 decision record, verified on the real bucket/region). A mock
proves nothing here: it would pass even if the store forgot the condition entirely.

The rest of the T1–T8 battery (T1 same-plane dup, T4 idempotent re-publish, T5 resolve-by-body,
T6 safe rename, T7 format/reserved, T8 clobber backstop) is covered against a conditional-honouring
FAKE in the two sibling files and is intentionally NOT duplicated here — see the mapping in the
module docstring of ``test_slug_marker_store_structured.py`` and the T1–T8 table below:

    T1 same-plane dup → SlugTaken ............... test_slug_marker_store_structured.py
                                                  ::test_claim_same_slug_different_plane_collides_as_slug_taken
                                                  + REAL-S3 variant here (T2 covers cross-plane; same-plane
                                                    is the same gate — see test_t1_same_plane_dup_* below)
    T2 cross-plane/kind dup → SlugTaken ......... THIS FILE (REAL S3, HC6)
    T3 concurrency race → exactly one winner .... THIS FILE (REAL S3, HC6)
    T4 idempotent same-owner re-publish ......... test_slug_marker_store_structured.py
                                                  ::test_claim_same_owner_republish_is_idempotent
    T5 resolve-by-body-not-name (Property 2) .... test_slug_marker_store_structured.py
                                                  ::test_resolve_reads_ownership_from_body
    T6 safe rename (claim-new-before-release) ... test_slug_marker_store_structured.py
                                                  ::test_rename_claims_new_before_releasing_old
                                                  + ::test_rename_failed_new_claim_leaves_old_slug_intact
    T7 format/reserved rejected ................. test_slug_marker_store_structured.py
                                                  ::test_fast_fail_rejects_reserved_prefix_and_reserved_word
                                                  + test_slug_marker_store.py::test_is_reserved_slug
    T8 clobber backstop (foreign never clobbered) test_slug_marker_store_structured.py
                                                  ::test_claim_mismatched_owner_republish_is_rejected_clobber_backstop

HC6 — WHY REAL S3 (not moto): moto is NOT installed in this env, and more importantly the task
says the guarantee must be proven against the ACTUAL conditional-PUT S3 honours. These tests hit
the verified bucket ``myadmin-public-pages-nonprofit-506221081911`` (eu-west-1, account
506221081911, profile ``nonprofit-deploy``) and are OPT-IN: skipped unless ``RUN_REAL_S3=1`` and
the bucket is reachable, so the default ``sam/tests`` unit run needs NO AWS creds. Every marker
object is written under a DISPOSABLE unique key and DELETED in teardown even on failure (no litter).

Run them explicitly (from the repo root, nonprofit account):

    env -u AWS_ACCESS_KEY_ID -u AWS_SECRET_ACCESS_KEY -u AWS_SESSION_TOKEN \
        -u AWS_ENDPOINT_URL_DYNAMODB AWS_PROFILE=nonprofit-deploy RUN_REAL_S3=1 \
        python -m pytest sam/tests/test_slug_marker_store_real_s3.py -q -c sam/pytest.ini

Validates: Requirements R4.1 (atomic cross-plane uniqueness), R4.6, R3.4, R3.5 (open kind set)
"""

from __future__ import annotations

import os
import sys
import time
import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest

_REPO_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from sam.members.repository.slug_marker_store import (
    S3SlugMarkerStore,
    SlugMarker,
    SlugTaken,
)

# The verified target bucket/region (task 1.1 decision record). Overridable via env for a
# different verified bucket, but defaults to the one HC6 was proven against.
REAL_BUCKET = os.environ.get(
    "REAL_S3_PUBLIC_PAGES_BUCKET", "myadmin-public-pages-nonprofit-506221081911"
)
REAL_REGION = os.environ.get("AWS_REGION", "eu-west-1")

#: All disposable keys this run creates get a stable prefix so a stray object (e.g. if the
#: process is killed mid-test) is trivially identifiable and sweepable. It still lives UNDER the
#: reserved ``_slugs/`` marker prefix because the store writes there — but with a ``_test-...``
#: segment that no real page slug could ever be (a real slug may not begin ``_``).
_TEST_SLUG_PREFIX = "_test-1-4"


pytestmark = pytest.mark.real_s3


def _real_s3_enabled() -> bool:
    return os.environ.get("RUN_REAL_S3") == "1"


def _s3_client_or_skip():
    """Return a real boto3 S3 client, or skip the test if S3 / the bucket is unreachable.

    Opt-in: without ``RUN_REAL_S3=1`` we skip unconditionally so the default unit run needs no
    AWS. When opted in, a reachability ``head_bucket`` turns an env/cred problem into a clean
    SKIP (not a hard error) so the suite degrades gracefully where AWS is absent — HC6 is about
    proving the guarantee WHEN we can reach S3, not about failing CI boxes that cannot.
    """
    if not _real_s3_enabled():
        pytest.skip(
            "RUN_REAL_S3 != 1 — real-S3 HC6 tests are opt-in (see module docstring)"
        )
    try:
        import boto3
        from botocore.exceptions import BotoCoreError, ClientError
    except ImportError as exc:  # pragma: no cover - boto3 is a hard dep in this env
        pytest.skip(f"boto3 unavailable: {exc}")
    try:
        client = boto3.client("s3", region_name=REAL_REGION)
        client.head_bucket(Bucket=REAL_BUCKET)
    except (
        ClientError,
        BotoCoreError,
    ) as exc:  # unreachable / no creds / wrong account
        pytest.skip(f"real S3 bucket {REAL_BUCKET} unreachable: {exc}")
    return client


def _unique_slug(tag: str) -> str:
    """A disposable, collision-proof slug for one test (timestamp + random suffix)."""
    return f"{_TEST_SLUG_PREFIX}-{tag}-{int(time.time())}-{uuid.uuid4().hex[:10]}"


@pytest.fixture()
def real_store():
    """A store bound to the REAL bucket, with teardown that deletes every slug it claimed.

    Tests append each slug they claim to ``created`` so teardown can release them ALL — even if
    the test body raises — leaving no litter in the shared bucket (HC6 cleanup requirement).
    """
    client = _s3_client_or_skip()
    store = S3SlugMarkerStore(client=client, bucket=REAL_BUCKET)
    created: list[str] = []
    try:
        yield store, created
    finally:
        for slug in created:
            try:
                store.release(slug)
            except Exception:  # noqa: BLE001, S110 - best-effort teardown; never mask the test result
                pass


def _owner(
    plane="sam", kind="application_form", tenant_id="h-dcn", ref="config#fields"
) -> SlugMarker:
    return SlugMarker(
        owner_plane=plane, kind=kind, tenant_id=tenant_id, resource_ref=ref
    )


# ═══════════════════════════════════════════════════════════════════════════════════════════
# T1 (real variant) — same-plane duplicate → SlugTaken, proven on real S3.
# The same-plane dup and the cross-plane dup (T2) are the SAME atomic gate; T1 is covered against
# the fake in the sibling file, and pinned here on REAL S3 too for completeness.
# ═══════════════════════════════════════════════════════════════════════════════════════════


def test_t1_same_plane_dup_second_claim_raises_slug_taken_real_s3(real_store):
    store, created = real_store
    slug = _unique_slug("t1-same-plane")
    created.append(slug)

    store.claim(slug, _owner(tenant_id="h-dcn"))
    # A SECOND claim from the SAME plane/kind but a DIFFERENT tenant is a foreign claim → SlugTaken.
    with pytest.raises(SlugTaken) as excinfo:
        store.claim(slug, _owner(tenant_id="other-tenant"))
    assert excinfo.value.slug == slug
    # The original owner is intact — never clobbered.
    assert store.resolve(slug).tenant_id == "h-dcn"


# ═══════════════════════════════════════════════════════════════════════════════════════════
# T2 — cross-plane / cross-kind duplicate → SlugTaken, proven on REAL S3 (HC6).
# ═══════════════════════════════════════════════════════════════════════════════════════════


def test_t2_cross_plane_kind_dup_second_claim_raises_slug_taken_real_s3(real_store):
    store, created = real_store
    slug = _unique_slug("t2-cross-plane")
    created.append(slug)

    # First claim: the SAM application_form producer.
    store.claim(slug, _owner(plane="sam", kind="application_form", tenant_id="h-dcn"))

    # A racing claimer from a DIFFERENT plane AND a DIFFERENT (open-set) kind — a webshop on the
    # flask plane — hits the real If-None-Match precondition and collides → SlugTaken. The gate is
    # tenant/plane/kind-agnostic: uniqueness is global per slug key (Property 1). This is the exact
    # behaviour a mock could not prove.
    foreign = _owner(
        plane="flask", kind="webshop", tenant_id="other-tenant", ref="shop#42"
    )
    with pytest.raises(SlugTaken) as excinfo:
        store.claim(slug, foreign)
    assert excinfo.value.slug == slug

    # The ORIGINAL owner survives — the foreign cross-plane claim never overwrote it (clobber
    # backstop, decided from the BODY not the slug string — Property 2).
    marker = store.resolve(slug)
    assert (marker.owner_plane, marker.kind, marker.tenant_id) == (
        "sam",
        "application_form",
        "h-dcn",
    )


def test_t2_cross_kind_same_plane_dup_raises_slug_taken_real_s3(real_store):
    store, created = real_store
    slug = _unique_slug("t2-cross-kind")
    created.append(slug)

    store.claim(slug, _owner(plane="sam", kind="application_form", tenant_id="h-dcn"))
    # Same plane, DIFFERENT kind (an event_calendar) — still a foreign owner → SlugTaken.
    with pytest.raises(SlugTaken):
        store.claim(slug, _owner(plane="sam", kind="event_calendar", tenant_id="h-dcn"))
    assert store.resolve(slug).kind == "application_form"


# ═══════════════════════════════════════════════════════════════════════════════════════════
# T3 — concurrency race: N concurrent claimers → EXACTLY ONE winner, N−1 SlugTaken (REAL S3, HC6).
# ═══════════════════════════════════════════════════════════════════════════════════════════


@pytest.mark.slow
@pytest.mark.parametrize("n_claimers", [8])
def test_t3_concurrent_claimers_exactly_one_winner_real_s3(real_store, n_claimers):
    store, created = real_store
    slug = _unique_slug("t3-race")
    # Register for cleanup up-front: whoever wins, the one marker that lands must be released.
    created.append(slug)

    # N distinct claimers, each from a DIFFERENT plane/kind/tenant, all racing for the SAME slug.
    owners = [
        _owner(
            plane=("sam" if i % 2 == 0 else "flask"),
            kind=("application_form" if i % 3 == 0 else f"future_kind_{i}"),
            tenant_id=f"tenant-{i}",
            ref=f"ref#{i}",
        )
        for i in range(n_claimers)
    ]

    results: list[object] = [None] * n_claimers

    def _attempt(idx: int):
        try:
            store.claim(slug, owners[idx])
            return ("won", idx)
        except SlugTaken:
            return ("taken", idx)

    # Fire them as concurrently as the GIL + network let us — the ATOMICITY is enforced by S3's
    # conditional PUT, not by the client, so this is a genuine race against real S3.
    with ThreadPoolExecutor(max_workers=n_claimers) as pool:
        futures = [pool.submit(_attempt, i) for i in range(n_claimers)]
        for fut in futures:
            outcome, idx = fut.result()
            results[idx] = outcome

    winners = [i for i, r in enumerate(results) if r == "won"]
    taken = [i for i, r in enumerate(results) if r == "taken"]

    # Property 1: EXACTLY ONE winner, the other N−1 all raised SlugTaken.
    assert len(winners) == 1, (
        f"expected exactly one winner, got {winners} (results={results})"
    )
    assert len(taken) == n_claimers - 1, (
        f"expected {n_claimers - 1} SlugTaken, got {taken}"
    )

    # The resolved marker is the winner's body — ownership read from the BODY (Property 2), and it
    # is one of the racers, never a merge/garbage.
    marker = store.resolve(slug)
    assert marker is not None
    winner_owner = owners[winners[0]]
    assert (marker.owner_plane, marker.kind, marker.tenant_id) == (
        winner_owner.owner_plane,
        winner_owner.kind,
        winner_owner.tenant_id,
    )
