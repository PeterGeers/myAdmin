"""
S3-backed **slug-marker store** — the ``_slugs/{slug}`` claim + reverse-lookup adapter.

This is the one shared surface that lets ANY producer — the application form now, a
webshop / event calendar / migrated landing page later — atomically claim and resolve a
slug across planes WITHOUT a shared database. It carries two layered contracts:

- **spec 14 / D-SLUG — the cross-plane platform contract.** ``claim(slug, owner)`` /
  ``resolve(slug)`` / ``release(slug)`` over a structured JSON marker BODY
  ``{owner_plane, kind, tenant_id, resource_ref}``. Ownership, kind, and tenant are decided
  by READING THE BODY — never by parsing the slug string (Property 2). The uniqueness gate is
  an ATOMIC conditional ``put_object`` with ``If-None-Match: *`` (task 1.1 decision record:
  verified on the real bucket/region — a collision surfaces as ``412 PreconditionFailed`` →
  :class:`SlugTaken`), so N concurrent claimers from ANY plane/kind yield exactly one winner
  (Property 1). This is the API new producers wire to. On top of the raw claim it layers the
  task-1.3 publish semantics: an ADVISORY per-producer fast-fail pre-check
  (:func:`validate_slug_fast_fail`, UX only — NOT the uniqueness gate); an IDEMPOTENT same-owner
  re-publish (``claim`` succeeds silently when the existing marker body matches ``owner_plane`` +
  ``kind`` + ``tenant_id``); a CLOBBER backstop (a mismatching/foreign owner is rejected, never
  overwritten); and a SAFE ``rename`` that claims the new slug BEFORE releasing the old (R4.5) so a
  failed/ crashed rename never leaves the producer with no slug.
- **spec 12 — the legacy single-string reverse-lookup.** ``claim_slug(slug, tenant_id)`` /
  ``resolve_slug(slug)`` → ``tenant_id`` (satisfying
  :class:`~sam.members.domain.tenant_directory.TenantSlugReader` for the public edge). Kept
  intact so existing callers + tests continue to work; ``resolve_slug`` transparently reads
  BOTH the new JSON body and the legacy plain-``tenant_id`` body.

Both contracts write to the SAME ``_slugs/{slug}`` key with the same if-none-match gate; the
new structured path is the forward-looking one.

The ``kind`` field is an OPEN set (see :data:`KNOWN_KINDS`): ``application_form`` is live;
``webshop`` / ``event_calendar`` / ``landing`` are named EXPECTED future kinds — **including
but not limited to these**. Adding a kind is a new ``kind`` value in the body + a new
producer; this store, the resolver, the CloudFront function and the rendering library do NOT
change. ``kind`` is therefore deliberately NOT validated against a closed enum.

OQ4 (spec 12) resolved the slug→``tenant_id`` reverse lookup to a control-plane MARKER OBJECT
in the shared public-pages bucket, rather than a slug-keyed row on the ``tenant_id``-PK
governance-projection table (which would break that table's structural-isolation invariant —
``template.yaml``). This module is the sole S3 touch-point for that marker:

- **Claim (Task 1.2):** a CONDITIONAL ``put_object`` on ``_slugs/{slug}`` using an *if-none-match*
  precondition that writes the owning ``tenant_id`` into the object body + metadata. The condition
  gives TENANT-scoped slug uniqueness (within-tenant only — there is NO global registry, OQ2) AND
  the slug→tenant mapping in ONE atomic step. A collision (the marker already exists) surfaces as a
  caller-safe :class:`SlugClaimConflict`, never a raw 500.
- **Resolve (Task 1.3):** a ``get_object`` on ``_slugs/{slug}`` → ``tenant_id``, scan-free. A miss
  (absent object, or an unreachable-as-empty read) returns ``None`` — never raises, never guesses a
  tenant (fail-safe, empty-is-valid; verify-before-trust, Property 2). The consuming
  :class:`~sam.members.domain.tenant_directory.TenantDirectory` maps that ``None`` to the uniform,
  non-probeable 404.

Reserved prefix (design D6)
---------------------------
``_slugs/`` is RESERVED: a real page slug may never be ``_slugs`` or begin ``_slugs/``, and the
marker objects deliberately live OUTSIDE any served ``{slug}/`` prefix — they are control plane,
never CloudFront-served. :func:`is_reserved_slug` is the single home of that rule; the write path
rejects a reserved slug fail-loud BEFORE any S3 call so a reserved name can never be claimed.

Account-agnostic CODE (design D2, migration-first)
--------------------------------------------------
The live-write path is dormant until the owner-run hosting migration (task 0.1) moves the
public-pages bucket to nonprofit. This module is account-agnostic: the bucket resolves lazily +
fail-fast from ``LANDING_PAGES_BUCKET`` (mirroring the landing publish path) and the boto3 S3 client
is injectable, so it is built + unit-tested now with a faked S3 client — no real AWS.

Layering (steering 35)
----------------------
SAM-plane **repository adapter**: it depends on boto3 + the fail-fast env helper and produces the
plain ``tenant_id`` string / raises a domain-shaped conflict. The domain never imports it; the
publish/edge wiring injects it. The format-validation authority stays
:mod:`sam.members.domain.form_slug` (reused, not duplicated) — this module adds only the
reserved-prefix rule and the S3 claim/resolve mechanism.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from services.dynamodb_client import REGION_ENV_VAR, require_env

from sam.members.domain.form_slug import validate_slug_format

__all__ = [
    "LANDING_PAGES_BUCKET_ENV_VAR",
    "SLUG_MARKER_PREFIX",
    "KNOWN_KINDS",
    "SlugClaimConflict",
    "SlugTaken",
    "SlugMarker",
    "S3SlugMarkerStore",
    "is_reserved_slug",
    "resolve_public_pages_bucket_name",
    "validate_slug_fast_fail",
]

#: The env var carrying the shared public-pages bucket name (``myadmin-public-pages-<env>``),
#: mirroring the landing publish path (design C4 / §Data Models). No default is synthesized — a
#: missing/blank var fails fast via the one ``require_env`` helper (steering 23, no dangerous
#: fallback).
LANDING_PAGES_BUCKET_ENV_VAR = "LANDING_PAGES_BUCKET"

#: The RESERVED marker prefix (design D6). Marker objects are written at ``_slugs/{slug}`` —
#: OUTSIDE any served ``{slug}/`` prefix, so they are control plane and never CloudFront-served.
SLUG_MARKER_PREFIX = "_slugs/"

#: The KNOWN producer ``kind`` values — a DOCUMENTATION aid, **NOT a closed allow-list**.
#:
#: ``kind`` is an OPEN, extensible set (spec 14 / D-SLUG). ``application_form`` is the live
#: producer; ``webshop`` / ``event_calendar`` / ``landing`` are named here as EXPECTED future
#: kinds — **including but not limited to these**. A new producer simply writes a new ``kind``
#: string in its marker body; this store does NOT reject an unlisted kind and callers MUST NOT
#: treat this tuple as exhaustive. It exists only so a reader can recognise the kinds in play
#: today — never to gate claims to a fixed enum (doing so would defeat the open-set design).
KNOWN_KINDS: tuple[str, ...] = (
    "application_form",  # live — the SAM application-form producer (spec 14 C2)
    "webshop",  # expected future kind
    "event_calendar",  # expected future kind
    "landing",  # expected future kind (a migrated landing page)
    # ... INCLUDING BUT NOT LIMITED TO the above — add a producer, not an enum entry.
)


@dataclass(frozen=True)
class SlugMarker:
    """The structured marker BODY — the extensible cross-plane producer contract (D-SLUG).

    Serialized as the JSON body of ``_slugs/{slug}``. Ownership / routing decisions are made by
    reading THESE fields, NEVER by parsing the slug string (Property 2) — so a slug owned by a
    different plane/kind, resolved at the SAM edge, yields a clean, non-probeable mismatch.

    Attributes:
        owner_plane: Which plane owns the slug (e.g. ``sam``; a future migrated landing page
            flips its ``owner_plane`` to ``sam``). How a cross-plane slug is told apart from an
            own-plane one at resolve time.
        kind: The producer kind — an OPEN set (:data:`KNOWN_KINDS`), ``application_form`` live;
            NOT a closed enum.
        tenant_id: The owning tenant in the owner plane's own tenancy vocabulary (the module
            plane's tenant key is ``tenant_id``, steering 35/39).
        resource_ref: A back-pointer to the producer's own record for this page (for the form,
            its ``config#fields`` row), so the owner can find its own data without anyone else
            knowing the shape.
    """

    owner_plane: str
    kind: str
    tenant_id: str
    resource_ref: str = ""

    def to_json_bytes(self) -> bytes:
        """Serialize to the compact, deterministic JSON body stored at ``_slugs/{slug}``."""
        return json.dumps(
            {
                "owner_plane": self.owner_plane,
                "kind": self.kind,
                "tenant_id": self.tenant_id,
                "resource_ref": self.resource_ref,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")

    @classmethod
    def from_mapping(cls, data: Any) -> "SlugMarker | None":
        """Build a marker from a parsed JSON body, or ``None`` if it is not a structured marker.

        Fail-safe: a body that is not a mapping, or that lacks a non-blank ``tenant_id``, returns
        ``None`` (the legacy plain-string path handles those). ``owner_plane`` / ``kind`` /
        ``resource_ref`` default to empty strings when absent so a partial future marker still
        resolves its tenant.
        """
        if not isinstance(data, dict):
            return None
        tenant_id = data.get("tenant_id")
        if not isinstance(tenant_id, str) or not tenant_id.strip():
            return None
        return cls(
            owner_plane=str(data.get("owner_plane", "")).strip(),
            kind=str(data.get("kind", "")).strip(),
            tenant_id=tenant_id.strip(),
            resource_ref=str(data.get("resource_ref", "")).strip(),
        )


class SlugTaken(Exception):
    """The slug is already claimed by ANOTHER owner (cross-plane / cross-kind) — spec 14 / D-SLUG.

    Raised by :meth:`S3SlugMarkerStore.claim` when the atomic conditional ``put_object``'s
    ``If-None-Match: *`` precondition fails (S3 ``412 PreconditionFailed``): a racing claimer from
    ANY plane or kind already owns ``_slugs/{slug}``. The publish/write edge maps this to a
    caller-safe conflict envelope (never a raw 500 / stack trace, steering 30 error contract). The
    message names only the slug — no internals leak.
    """

    def __init__(self, slug: str):
        self.slug = slug
        super().__init__(f"slug '{slug}' is already claimed")


class SlugClaimConflict(Exception):
    """A caller-safe conflict: the slug is already claimed (the marker exists).

    Raised by :meth:`S3SlugMarkerStore.claim_slug` when the conditional ``put_object``'s
    *if-none-match* precondition fails — i.e. another claim already owns ``_slugs/{slug}``. The
    publish/write edge maps this to the standard caller-safe conflict envelope (never a raw 500 /
    stack trace). The message names only the slug, no internals.
    """

    def __init__(self, slug: str):
        self.slug = slug
        super().__init__(f"slug '{slug}' is already claimed")


def is_reserved_slug(slug: object) -> bool:
    """Return ``True`` when ``slug`` collides with the reserved ``_slugs/`` control-plane prefix.

    A real page slug may never be exactly ``_slugs`` nor begin with ``_slugs/`` (design D6) — those
    names would alias the marker control plane. Non-string / blank input is treated as reserved
    (``True``) so it is rejected fail-loud rather than silently claimed; genuine format validation
    (length, charset) stays with :func:`sam.members.domain.form_slug.validate_slug_format`.
    """
    if not isinstance(slug, str) or not slug:
        return True
    # Compare case-insensitively: the marker prefix is a fixed control-plane token, and slugs are
    # case-folded at the resolver, so ``_SLUGS`` must not sneak past as a distinct name.
    normalized = slug.strip().lower()
    marker = SLUG_MARKER_PREFIX.rstrip("/")  # "_slugs"
    return normalized == marker or normalized.startswith(SLUG_MARKER_PREFIX)


def validate_slug_fast_fail(slug: object) -> str | None:
    """ADVISORY per-producer fast-fail pre-check for a slug — UX ONLY, NOT the uniqueness gate.

    This is the SAM config-row slug check the publish edge runs FIRST, before the atomic
    :meth:`S3SlugMarkerStore.claim`, so a malformed or reserved slug surfaces a friendly 400 early
    (good UX) instead of only failing deep in the claim path. It layers two cheap, local checks:

    - the shared **format** contract (:func:`sam.members.domain.form_slug.validate_slug_format` —
      the single SAM-plane home of the ``SLUG_PATTERN`` / length / reserved-word rules, R4.2); and
    - the **reserved control-plane prefix** rule (:func:`is_reserved_slug`, design D6).

    It is DELIBERATELY advisory (design D-SLUG "Layering"; R4.3): it is a fast-fail UX convenience,
    and it is explicitly NOT the uniqueness guarantee. It cannot see other planes/kinds and runs
    BEFORE the write, so relying on it for uniqueness would reintroduce a check-then-write race.
    The authoritative, atomic cross-plane uniqueness gate stays the ``If-None-Match: *`` conditional
    put inside :meth:`S3SlugMarkerStore.claim` (Property 1). A clean fast-fail (``None``) therefore
    does NOT promise the claim will succeed — a concurrent claimer can still win the atomic race.

    Returns a caller-safe error string (no internals) when the slug is malformed/reserved, or
    ``None`` when the slug is well-formed enough to ATTEMPT the atomic claim.
    """
    # Reserved control-plane prefix first (design D6) — a `_slugs/...` name can never be a page slug
    # and is caught here as early UX, though the claim path rejects it fail-loud regardless.
    if is_reserved_slug(slug):
        return (
            f"'{slug}' is reserved (the '{SLUG_MARKER_PREFIX}' prefix is control-plane only) "
            "and cannot be used as a page slug"
        )
    # Shared format contract (R4.2): lowercase/charset/length/reserved-word — reuse the one
    # authority, never re-implement.
    return validate_slug_format(slug)


def resolve_public_pages_bucket_name() -> str:
    """Return the public-pages bucket name from ``LANDING_PAGES_BUCKET``, or fail fast.

    Reuses the T0 fail-fast client (:func:`services.dynamodb_client.require_env`) so the
    no-dangerous-fallback discipline lives in one place (steering 23).

    Raises:
        services.dynamodb_client.DynamoDBConfigError: ``LANDING_PAGES_BUCKET`` is missing/blank.
    """
    return require_env(LANDING_PAGES_BUCKET_ENV_VAR)


def _marker_key(slug: str) -> str:
    """Return the control-plane marker key ``_slugs/{slug}`` for a (reserved-checked) slug."""
    return f"{SLUG_MARKER_PREFIX}{slug}"


class S3SlugMarkerStore:
    """The S3-backed ``_slugs/{slug}`` claim + reverse-lookup store (OQ4 / design §Reverse-lookup).

    The S3 client + bucket name resolve LAZILY + fail-fast on first use so import touches no AWS;
    the client is injectable (dependency inversion) for tests. All I/O is confined to the reserved
    ``_slugs/`` prefix in the one public-pages bucket.

    Args:
        client: An optional boto3 S3 client (or a compatible fake). If omitted, resolved lazily on
            first use against the resolved region.
        bucket: An optional bucket name override. If omitted, resolved lazily + fail-fast from
            ``LANDING_PAGES_BUCKET`` on first use.
    """

    def __init__(self, *, client: Any = None, bucket: str | None = None):
        self._client = client
        self._bucket = bucket

    # ── lazy, fail-fast resource resolution ───────────────────────────────────────────

    @property
    def client(self):
        """The boto3 S3 client, resolved lazily + fail-fast on first use."""
        if self._client is None:
            import boto3

            self._client = boto3.client("s3", region_name=require_env(REGION_ENV_VAR))
        return self._client

    @property
    def bucket(self) -> str:
        """The public-pages bucket name, resolved lazily + fail-fast from the env on first use."""
        if self._bucket is None:
            self._bucket = resolve_public_pages_bucket_name()
        return self._bucket

    # ── claim (Task 1.2) ───────────────────────────────────────────────────────────────

    def claim_slug(self, slug: str, tenant_id: str) -> None:
        """Claim ``_slugs/{slug}`` for ``tenant_id`` with a conditional (if-none-match) put.

        Writes the owning ``tenant_id`` into both the object body and ``x-amz-meta-tenant-id`` so
        the mapping survives whichever read path a later resolve takes, and uses the S3
        *if-none-match* precondition (``IfNoneMatch="*"``) so the write SUCCEEDS only when no marker
        exists yet — giving within-tenant uniqueness AND the mapping atomically (OQ4).

        Reserved-prefix guard (design D6): a slug that is ``_slugs`` or begins ``_slugs/`` (or a
        blank/non-string value) is rejected fail-loud with :class:`ValueError` BEFORE any S3 call,
        so a reserved name can never alias the marker control plane. ``tenant_id`` must be a
        non-blank string (the owner recorded in the marker).

        Raises:
            ValueError: the slug is reserved/blank, or ``tenant_id`` is blank.
            SlugClaimConflict: the marker already exists (if-none-match precondition failed) — a
                caller-safe conflict, NOT a 500.
        """
        if is_reserved_slug(slug):
            raise ValueError(
                f"'{slug}' is reserved (the '{SLUG_MARKER_PREFIX}' prefix is control-plane only) "
                "and cannot be claimed as a form slug"
            )
        if not isinstance(tenant_id, str) or not tenant_id.strip():
            raise ValueError("tenant_id must be a non-blank string to claim a slug")

        owner = tenant_id.strip()
        try:
            self.client.put_object(
                Bucket=self.bucket,
                Key=_marker_key(slug),
                Body=owner.encode("utf-8"),
                ContentType="text/plain; charset=utf-8",
                Metadata={"tenant-id": owner},
                # Conditional write: succeed ONLY when the marker does not already exist. S3
                # returns a 412 PreconditionFailed (ClientError) when something is already there.
                IfNoneMatch="*",
            )
        except Exception as exc:  # noqa: BLE001 - narrow to precondition-failed below, re-raise rest
            if _is_precondition_failed(exc):
                raise SlugClaimConflict(slug) from exc
            raise

    # ── spec 14 / D-SLUG: structured cross-plane claim / resolve / release ──────────────

    def claim(self, slug: str, owner: SlugMarker) -> None:
        """Atomically claim ``_slugs/{slug}`` for ``owner`` (the structured D-SLUG contract).

        Writes the structured marker body ``{owner_plane, kind, tenant_id, resource_ref}`` using
        the ``If-None-Match: *`` precondition so the write SUCCEEDS only when no marker exists yet.
        The S3 condition IS the check — there is no check-then-write race, so N concurrent claimers
        from ANY plane/kind yield exactly one winner and N−1 :class:`SlugTaken` (Property 1; task
        1.1 decision record, verified on the real bucket/region).

        ``owner.tenant_id`` is ALSO mirrored into ``x-amz-meta-tenant-id`` so the legacy
        :meth:`resolve_slug` reverse-lookup keeps working regardless of body shape.

        The reserved-prefix guard (design D6) rejects a slug that is ``_slugs`` / begins
        ``_slugs/`` (or a blank/non-string value) fail-loud BEFORE any S3 call, so a reserved name
        can never alias the marker control plane. ``kind`` is NOT validated against a closed enum
        (:data:`KNOWN_KINDS` is an open set).

        **Idempotent same-owner re-publish + clobber backstop (Property 6, R4.4):** when the marker
        already exists (the if-none-match precondition fails), the existing marker body is read and
        compared to ``owner`` on ``owner_plane`` + ``kind`` + ``tenant_id`` (decided from the BODY,
        never from the slug string — Property 2):

        - a MATCH on all three means this is the SAME owner re-publishing the SAME page → the claim
          SUCCEEDS idempotently (no :class:`SlugTaken`), leaving the existing marker in place;
        - any MISMATCH (a different plane, kind, or tenant) is a FOREIGN claim → :class:`SlugTaken`
          is raised and the foreign marker is never silently overwritten (the clobber backstop).

        Raises:
            ValueError: the slug is reserved/blank, or ``owner`` is missing a non-blank
                ``owner_plane`` / ``kind`` / ``tenant_id``.
            SlugTaken: the marker already exists AND is owned by a DIFFERENT owner (foreign claim) —
                a caller-safe conflict, NOT a 500.
        """
        if is_reserved_slug(slug):
            raise ValueError(
                f"'{slug}' is reserved (the '{SLUG_MARKER_PREFIX}' prefix is control-plane only) "
                "and cannot be claimed as a page slug"
            )
        if not isinstance(owner, SlugMarker):
            raise ValueError("owner must be a SlugMarker to claim a slug")
        for name in ("owner_plane", "kind", "tenant_id"):
            value = getattr(owner, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(
                    f"owner.{name} must be a non-blank string to claim a slug"
                )

        try:
            self.client.put_object(
                Bucket=self.bucket,
                Key=_marker_key(slug),
                Body=owner.to_json_bytes(),
                ContentType="application/json",
                # tenant-id mirrored into metadata so the legacy resolve_slug path still works.
                Metadata={"tenant-id": owner.tenant_id},
                # Conditional write: succeed ONLY when the marker does not already exist. S3
                # returns a 412 PreconditionFailed (ClientError) when something is already there.
                IfNoneMatch="*",
            )
        except Exception as exc:  # noqa: BLE001 - narrow to precondition-failed below, re-raise rest
            if _is_precondition_failed(exc):
                # The slug is already claimed. Decide idempotent re-publish vs foreign conflict from
                # the EXISTING marker BODY (Property 2) — never by parsing the slug string.
                if self._is_same_owner(slug, owner):
                    return  # idempotent same-owner re-publish (R4.4) — no clobber, no SlugTaken
                raise SlugTaken(slug) from exc  # foreign owner → clobber backstop
            raise

    def _is_same_owner(self, slug: str, owner: SlugMarker) -> bool:
        """True when the EXISTING ``_slugs/{slug}`` marker is owned by ``owner`` (Property 6 / R4.4).

        Ownership is compared on ``owner_plane`` + ``kind`` + ``tenant_id`` read from the marker
        BODY (never the slug string — Property 2). ``resource_ref`` is intentionally NOT part of the
        identity: the SAME page may re-publish with an updated back-pointer and still be the same
        owner. A missing/legacy/unreadable marker is treated as NOT the same owner (fail-safe → the
        caller sees a conflict rather than a silent clobber).
        """
        existing = self.resolve(slug)
        if existing is None:
            return False
        return (
            existing.owner_plane == owner.owner_plane
            and existing.kind == owner.kind
            and existing.tenant_id == owner.tenant_id
        )

    def rename(self, old_slug: str, new_slug: str, owner: SlugMarker) -> None:
        """Rename a page's slug SAFELY: claim ``new_slug`` BEFORE releasing ``old_slug`` (R4.5).

        Ordering is the whole point (Property 6 / design D-SLUG "rename claims-new-before-releasing-
        old"): the NEW slug is claimed first with the atomic conditional put, and ONLY once that
        succeeds is the OLD marker released. So a crash — or a failed new-claim — mid-rename never
        leaves the producer with NO slug: either the rename fully happened (new present, old gone)
        or it did not (old still owned, new not taken). A slug is never double-owned or orphaned.

        If ``new_slug`` is already taken by a FOREIGN owner, :meth:`claim` raises
        :class:`SlugTaken` and this method propagates it WITHOUT touching the old marker — the
        producer keeps ``old_slug`` intact (no release happens). A no-op rename where
        ``new_slug == old_slug`` is rejected fail-loud so a caller cannot accidentally release the
        slug it just (idempotently) re-claimed.

        Raises:
            ValueError: either slug is reserved/blank, ``owner`` is invalid, or the two slugs are
                equal (a rename to the same slug is a no-op the caller should not request).
            SlugTaken: ``new_slug`` is already owned by a DIFFERENT owner — ``old_slug`` is left
                untouched (the producer never ends up with no slug).
        """
        if (
            isinstance(old_slug, str)
            and isinstance(new_slug, str)
            and old_slug == new_slug
        ):
            raise ValueError(
                "rename requires a different new_slug (old and new are identical)"
            )
        # Claim the NEW slug first (atomic conditional put; idempotent for same-owner). Any
        # ValueError / foreign SlugTaken propagates BEFORE the old marker is touched.
        self.claim(new_slug, owner)
        # New slug is now owned by us — only now is it safe to release the old marker.
        self.release(old_slug)

    def resolve(self, slug: str) -> SlugMarker | None:
        """Return the structured :class:`SlugMarker` for ``_slugs/{slug}``, or ``None`` (fail-safe).

        A scan-free ``get_object`` on the marker key; ownership / kind / tenant are read from the
        BODY (Property 2 — never by parsing the slug string). Empty-is-valid / fail-safe:

        - a reserved/blank/non-string slug → ``None`` WITHOUT touching S3;
        - a MISSING marker (``NoSuchKey`` / ``404``) → ``None``;
        - a legacy plain-``tenant_id`` body (spec 12, no JSON) → a marker synthesized with an
          empty ``owner_plane``/``kind`` so a pre-structured claim still resolves its tenant;
        - a present-but-empty / unparseable body with no usable tenant → ``None``.

        Any OTHER S3 error (a genuine fault, not a miss) propagates. The caller decides routing
        from ``owner_plane``/``kind`` — a cross-plane/cross-kind slug is a clean, non-probeable
        mismatch at the SAM edge, never a leak.
        """
        if not isinstance(slug, str) or not slug or is_reserved_slug(slug):
            return None
        try:
            response = self.client.get_object(Bucket=self.bucket, Key=_marker_key(slug))
        except Exception as exc:  # noqa: BLE001 - a missing marker is "no match", not an error
            if _is_not_found(exc):
                return None
            raise

        raw = _read_raw_body(response)
        marker = _parse_marker_body(raw)
        if marker is not None:
            return marker

        # Legacy spec-12 marker: a plain tenant_id string in the body or metadata. Synthesize a
        # structured marker so a pre-structured claim still resolves (owner_plane/kind unknown).
        tenant_id = (raw or "").strip() or _read_metadata_tenant(response)
        if tenant_id:
            return SlugMarker(owner_plane="", kind="", tenant_id=tenant_id)
        return None

    def release(self, slug: str) -> None:
        """Release (delete) the ``_slugs/{slug}`` marker so the slug can be re-claimed.

        Used by the rename path (claim-new-before-release-old, Property 6) and teardown. A
        reserved/blank/non-string slug is rejected fail-loud BEFORE any S3 call. Deleting a marker
        that does not exist is a no-op on S3 (``delete_object`` is idempotent) — not an error.

        Raises:
            ValueError: the slug is reserved/blank.
        """
        if is_reserved_slug(slug):
            raise ValueError(
                f"'{slug}' is reserved (the '{SLUG_MARKER_PREFIX}' prefix is control-plane only)"
            )
        self.client.delete_object(Bucket=self.bucket, Key=_marker_key(slug))

    # ── resolve (Task 1.3) ─────────────────────────────────────────────────────────────

    def resolve_slug(self, slug: str) -> str | None:
        """Return the owning ``tenant_id`` for ``_slugs/{slug}``, or ``None`` (fail-safe).

        Satisfies the :class:`sam.members.domain.tenant_directory.TenantSlugReader` Protocol by
        duck-typing so it drops straight into :class:`TenantDirectory`. A scan-free ``get_object``
        on the marker key; the ``tenant_id`` is read from the object body (falling back to the
        ``x-amz-meta-tenant-id`` metadata). Empty-is-valid / fail-safe throughout (design
        §Reverse-lookup, Property 2):

        - a reserved/blank/non-string slug → ``None`` WITHOUT touching S3 (a reserved name can
          never resolve to a tenant);
        - a MISSING marker (``NoSuchKey`` / ``404``) → ``None``;
        - a present-but-empty / whitespace body with no usable metadata → ``None``;

        so the resolver maps every miss to the ONE non-probeable 404 and never guesses a tenant. Any
        OTHER S3 error (a genuine fault, not a miss) propagates — the resolver's own seam contract
        treats that as no-match, keeping the public surface non-probeable even when the store is
        unreachable-as-empty.
        """
        if not isinstance(slug, str) or not slug or is_reserved_slug(slug):
            return None
        try:
            response = self.client.get_object(Bucket=self.bucket, Key=_marker_key(slug))
        except Exception as exc:  # noqa: BLE001 - a missing marker is "no match", not an error
            if _is_not_found(exc):
                return None
            raise

        # Parse the structured JSON body first (spec 14), then fall back to the legacy
        # plain-tenant_id body (spec 12), then the x-amz-meta-tenant-id metadata.
        raw = _read_raw_body(response)
        marker = _parse_marker_body(raw)
        if marker is not None:
            return marker.tenant_id
        tenant_id = (raw or "").strip() or _read_metadata_tenant(response)
        return tenant_id or None


# ── structural S3-error classifiers (duck-typed; no botocore import at module scope) ──────


def _is_precondition_failed(exc: Exception) -> bool:
    """True when an S3 exception means the if-none-match precondition failed (slug already claimed).

    boto3 raises ``botocore.exceptions.ClientError`` carrying an ``Error.Code`` of
    ``PreconditionFailed`` (HTTP ``412``) when an ``IfNoneMatch="*"`` put hits an existing object.
    Read structurally (no botocore import at module scope) so a fake client in tests can raise a
    lookalike and this stays import-light — mirroring ``template_body_store._is_not_found``.
    """
    response = getattr(exc, "response", None)
    if not isinstance(response, dict):
        return False
    error = response.get("Error", {}) if isinstance(response.get("Error"), dict) else {}
    if str(error.get("Code")) in {
        "PreconditionFailed",
        "412",
        "ConditionalRequestConflict",
    }:
        return True
    status = (
        response.get("ResponseMetadata", {}).get("HTTPStatusCode")
        if isinstance(response.get("ResponseMetadata"), dict)
        else None
    )
    return status == 412


def _is_not_found(exc: Exception) -> bool:
    """True when an S3 exception means "the marker does not exist" (vs a real failure).

    Mirrors :func:`sam.members.repository.template_body_store._is_not_found`: ``NoSuchKey`` /
    ``NotFound`` / HTTP ``404``, read structurally so a fake client's exception shapes work too.
    """
    response = getattr(exc, "response", None)
    if not isinstance(response, dict):
        return False
    error = response.get("Error", {}) if isinstance(response.get("Error"), dict) else {}
    if str(error.get("Code")) in {"NoSuchKey", "404", "NotFound"}:
        return True
    status = (
        response.get("ResponseMetadata", {}).get("HTTPStatusCode")
        if isinstance(response.get("ResponseMetadata"), dict)
        else None
    )
    return status == 404


def _read_raw_body(response: Any) -> str | None:
    """Read the raw ``get_object`` body as text, or ``None`` (empty-is-valid).

    Decodes bytes as UTF-8; returns the (unstripped) text so callers can both JSON-parse it and
    fall back to treating it as a plain tenant_id string.
    """
    if not isinstance(response, dict):
        return None
    body = response.get("Body")
    if body is None:
        return None
    raw = body.read() if hasattr(body, "read") else body
    text = raw.decode("utf-8") if isinstance(raw, (bytes, bytearray)) else str(raw)
    return text


def _parse_marker_body(raw: str | None) -> SlugMarker | None:
    """Parse a raw body into a structured :class:`SlugMarker`, or ``None`` if it is not one.

    Fail-safe: a blank body, a non-JSON body (the legacy plain-``tenant_id`` string), or JSON that
    is not a mapping / lacks a non-blank ``tenant_id`` all return ``None`` so the caller can fall
    back to the legacy plain-string path. Never raises.
    """
    if not raw or not raw.strip():
        return None
    try:
        parsed = json.loads(raw)
    except (ValueError, TypeError):
        return None
    return SlugMarker.from_mapping(parsed)


def _read_metadata_tenant(response: Any) -> str | None:
    """Read the ``tenant_id`` from the ``x-amz-meta-tenant-id`` metadata, or ``None``."""
    if not isinstance(response, dict):
        return None
    metadata = response.get("Metadata")
    if not isinstance(metadata, dict):
        return None
    value = metadata.get("tenant-id") or metadata.get("tenant_id")
    value = value.strip() if isinstance(value, str) else None
    return value or None
