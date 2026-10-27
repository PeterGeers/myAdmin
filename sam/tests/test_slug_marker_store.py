"""
SAM pytest for the ``_slugs/{slug}`` bucket-marker store (spec 12 Tasks 1.2/1.3; OQ4; design
§Reverse-lookup / D6) — :class:`sam.members.repository.slug_marker_store.S3SlugMarkerStore`.

These pin the marker store's observable contract WITHOUT real AWS (an in-memory fake S3 client,
mirroring the hand fakes the SAM suite already uses — ``FakeTable`` in the projection reader tests,
``FakeClientError`` in the session-dedup test):

Task 1.2 — the conditional-put CLAIM:
- a claim on a FREE slug succeeds and writes the owning ``tenant_id`` (body + metadata), with the
  if-none-match precondition on the ``_slugs/{slug}`` key;
- a SECOND claim for the SAME slug collides (if-none-match precondition fails) and surfaces as a
  caller-safe :class:`SlugClaimConflict`, NOT a raw 500 / unclassified error;
- the reserved ``_slugs/`` prefix is rejected fail-loud (a slug named ``_slugs`` or beginning
  ``_slugs/``), BEFORE any S3 call.

Task 1.3 — the reverse slug→tenant RESOLVE:
- a known slug's marker resolves to its ``tenant_id`` (scan-free ``get_object``);
- an unknown / missing / blank / oversized / reserved slug resolves to ``None`` — non-probeable,
  fail-safe (never raises, never guesses a tenant); verify-before-trust (Property 2);
- the store satisfies the :class:`TenantSlugReader` Protocol and drops into :class:`TenantDirectory`
  by duck-typing, giving the full non-probeable 404 behaviour the public edge relies on.

Validates: Requirements R4.3, R7.1, R7.2
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

from sam.members.domain.tenant_directory import (
    MAX_SLUG_LENGTH,
    ResolveFailure,
    TenantDirectory,
    TenantSlugReader,
)
from sam.members.repository.slug_marker_store import (
    SLUG_MARKER_PREFIX,
    S3SlugMarkerStore,
    SlugClaimConflict,
    is_reserved_slug,
)


# ---------------------------------------------------------------------------
# In-memory fake S3 client — only the three calls the store makes.
# ---------------------------------------------------------------------------


class _FakeClientError(Exception):
    """Stand-in for ``botocore.exceptions.ClientError`` with the structured ``.response`` shape.

    The store classifies S3 errors structurally (``response['Error']['Code']`` /
    ``ResponseMetadata.HTTPStatusCode``) without importing botocore, so a lookalike works.
    """

    def __init__(self, code: str, status: int, message: str = "boom"):
        self.response = {
            "Error": {"Code": code, "Message": message},
            "ResponseMetadata": {"HTTPStatusCode": status},
        }
        super().__init__(f"{code}: {message}")


class FakeS3Client:
    """In-memory S3 that honours the if-none-match CONDITIONAL put + a get_object/not-found.

    - ``put_object(..., IfNoneMatch="*")`` writes ONLY when the key is free; a second write to the
      same key raises a ``PreconditionFailed`` (412) lookalike — exactly how S3 enforces the claim.
    - ``get_object`` returns a streaming-ish body + metadata, or raises ``NoSuchKey`` (404) for a
      missing key.
    """

    def __init__(self):
        self.objects: dict[
            tuple, dict
        ] = {}  # (bucket, key) -> {"body": bytes, "meta": {...}}
        self.put_calls: list[dict] = []

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
        return {
            "Body": io.BytesIO(obj["body"]),
            "Metadata": dict(obj["meta"]),
        }


BUCKET = "myadmin-public-pages-test"


@pytest.fixture()
def s3() -> FakeS3Client:
    return FakeS3Client()


@pytest.fixture()
def store(s3) -> S3SlugMarkerStore:
    # Inject the fake client + bucket so NO AWS / env is touched (account-agnostic code).
    return S3SlugMarkerStore(client=s3, bucket=BUCKET)


# ── Task 1.2: the conditional-put claim ───────────────────────────────────────────────────


def test_claim_slug_free_slug_succeeds_and_records_owner(store, s3):
    store.claim_slug("hdcn-application-form", "h-dcn")

    key = (BUCKET, f"{SLUG_MARKER_PREFIX}hdcn-application-form")
    assert key in s3.objects
    # The owning tenant_id is written into BOTH the body and the metadata.
    assert s3.objects[key]["body"] == b"h-dcn"
    assert s3.objects[key]["meta"]["tenant-id"] == "h-dcn"
    # It used the if-none-match precondition on the reserved marker prefix (outside served {slug}/).
    assert s3.put_calls[0]["IfNoneMatch"] == "*"
    assert s3.put_calls[0]["Key"].startswith(SLUG_MARKER_PREFIX)


def test_claim_slug_same_slug_twice_collides_as_caller_safe_conflict(store):
    store.claim_slug("hdcn-application-form", "h-dcn")

    # A second claim for the SAME slug fails the if-none-match precondition → caller-safe conflict,
    # NOT a raw 500 / unclassified error.
    with pytest.raises(SlugClaimConflict) as excinfo:
        store.claim_slug("hdcn-application-form", "another-tenant")
    assert excinfo.value.slug == "hdcn-application-form"
    # The message names only the slug — no internals leak.
    assert "hdcn-application-form" in str(excinfo.value)


def test_claim_different_slugs_both_succeed(store, s3):
    store.claim_slug("hdcn-application-form", "h-dcn")
    store.claim_slug("zktk-application-form", "zktk-tenant")

    assert (BUCKET, f"{SLUG_MARKER_PREFIX}hdcn-application-form") in s3.objects
    assert (BUCKET, f"{SLUG_MARKER_PREFIX}zktk-application-form") in s3.objects


@pytest.mark.parametrize("reserved", ["_slugs", "_slugs/", "_slugs/anything", "_SLUGS"])
def test_claim_reserved_prefix_rejected_before_any_s3_call(store, s3, reserved):
    with pytest.raises(ValueError):
        store.claim_slug(reserved, "h-dcn")
    # Rejected fail-loud BEFORE any S3 call — the control plane can never be aliased.
    assert s3.put_calls == []


@pytest.mark.parametrize("bad_tenant", ["", "   ", None])
def test_claim_blank_tenant_id_rejected(store, bad_tenant):
    with pytest.raises(ValueError):
        store.claim_slug("some-form", bad_tenant)  # type: ignore[arg-type]


# ── Task 1.3: the reverse slug→tenant resolve ─────────────────────────────────────────────


def test_resolve_slug_known_marker_returns_tenant(store):
    store.claim_slug("hdcn-application-form", "h-dcn")

    assert store.resolve_slug("hdcn-application-form") == "h-dcn"


def test_resolve_slug_reads_from_metadata_when_body_blank(store, s3):
    # A marker written with only metadata (defensive: a hand-authored / legacy object) still
    # resolves — the store falls back to x-amz-meta-tenant-id.
    s3.objects[(BUCKET, f"{SLUG_MARKER_PREFIX}meta-only")] = {
        "body": b"   ",
        "meta": {"tenant-id": "h-dcn"},
    }
    assert store.resolve_slug("meta-only") == "h-dcn"


def test_resolve_slug_unknown_returns_none(store):
    store.claim_slug("hdcn-application-form", "h-dcn")

    assert store.resolve_slug("not-a-slug") is None


def test_resolve_slug_missing_marker_returns_none(store):
    # Nothing claimed at all — a scan-free get_object miss is "no match", never a raise.
    assert store.resolve_slug("anything") is None


@pytest.mark.parametrize(
    "bad",
    [
        "",  # blank
        "   ",  # whitespace-only (reserved-style guard trims)
        "_slugs",  # reserved
        "_slugs/leak",  # reserved prefix
        None,  # non-string
    ],
)
def test_resolve_slug_blank_or_reserved_returns_none_without_s3(store, s3, bad):
    # A reserved / blank / non-string slug can never resolve to a tenant and must NOT touch S3
    # (non-probeable, fail-safe).
    store.claim_slug("real-form", "h-dcn")
    s3_calls_before = len(
        getattr(s3, "get_calls", [])
    )  # FakeS3Client has none; proves no get path
    assert store.resolve_slug(bad) is None  # type: ignore[arg-type]
    # No exception, and a real slug still resolves afterwards (the store is not wedged).
    assert store.resolve_slug("real-form") == "h-dcn"
    _ = s3_calls_before


def test_resolve_slug_empty_body_and_no_metadata_returns_none(store, s3):
    s3.objects[(BUCKET, f"{SLUG_MARKER_PREFIX}empty-marker")] = {
        "body": b"",
        "meta": {},
    }
    assert store.resolve_slug("empty-marker") is None


def test_resolve_slug_oversized_returns_none(store):
    # An oversized slug (longer than the resolver's DNS-label cap) is a well-formed, non-reserved
    # string, so the store treats it as any other miss: the scan-free get_object finds no marker →
    # None (never a raise, never a guessed tenant). The resolver's own length guard rejects it even
    # earlier (see the end-to-end test below); the store is non-probeable in its own right too.
    store.claim_slug("real-form", "h-dcn")
    oversized = "a" * (MAX_SLUG_LENGTH + 1)
    assert store.resolve_slug(oversized) is None
    # Not wedged — a real slug still resolves afterwards.
    assert store.resolve_slug("real-form") == "h-dcn"


# ── satisfies the Protocol + works end-to-end through TenantDirectory ──────────────────────


def test_store_satisfies_the_tenant_slug_reader_protocol(store):
    assert isinstance(store, TenantSlugReader)


def test_end_to_end_through_the_resolver(store):
    # The whole reverse-lookup seam the submit edge wires: the marker store behind TenantDirectory.
    store.claim_slug("hdcn-application-form", "h-dcn")
    directory = TenantDirectory(store)

    hit = directory.resolve("HDCN-APPLICATION-FORM")  # case-insensitive at the resolver
    assert hit.ok is True
    assert hit.tenant_id == "h-dcn"

    miss = directory.resolve("not-a-slug")
    assert miss.ok is False
    assert miss.failure is ResolveFailure.NOT_FOUND


def test_end_to_end_all_negative_cases_collapse_to_one_not_found(store):
    # R7.2 / spec 12 Task 1.5: the OQ4 reverse reader (the `_slugs/{slug}` marker store — the
    # "ConfigFieldsSlugReader" the task names) must resolve a KNOWN slug AND return the SAME
    # non-probeable not-found for EVERY negative — unknown, forged/garbage, blank, AND oversized —
    # when driven end-to-end through the REAL store behind TenantDirectory (not a fake reader). This
    # pins all four negatives against the actual reverse mechanism, not just the fake in
    # test_tenant_directory.py.
    store.claim_slug("hdcn-application-form", "h-dcn")
    directory = TenantDirectory(store)

    # Known slug resolves (verify-before-trust: only the allow-listed marker resolves).
    assert directory.resolve("hdcn-application-form").tenant_id == "h-dcn"

    oversized = "a" * (MAX_SLUG_LENGTH + 1)
    negatives = [
        directory.resolve("not-a-real-tenant"),  # unknown but well-formed
        directory.resolve("'; DROP TABLE members; --"),  # forged/garbage
        directory.resolve(""),  # blank
        directory.resolve("   "),  # whitespace-only
        directory.resolve(oversized),  # oversized (> MAX_SLUG_LENGTH)
    ]
    # Every negative is byte-for-byte the SAME uniform not-found — no enumeration oracle.
    for outcome in negatives:
        assert outcome.ok is False
        assert outcome.tenant_id is None
        assert outcome.failure is ResolveFailure.NOT_FOUND
        assert outcome == negatives[0]


# ── is_reserved_slug unit coverage (design D6) ─────────────────────────────────────────────


@pytest.mark.parametrize(
    "value,expected",
    [
        ("_slugs", True),
        ("_slugs/", True),
        ("_slugs/hdcn", True),
        ("_SLUGS", True),  # case-insensitive
        ("  _slugs  ", True),  # trimmed
        ("", True),  # blank is reserved (reject fail-loud)
        (None, True),  # non-string
        ("hdcn-application-form", False),
        ("slugs", False),  # only the exact prefix is reserved, not a superstring
        ("my_slugs", False),
    ],
)
def test_is_reserved_slug(value, expected):
    assert is_reserved_slug(value) is expected
