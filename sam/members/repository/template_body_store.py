"""
S3-backed **template body store** (R2, task 2.3 wiring) — the production
:class:`~sam.members.domain.template_service.TemplateBodyStore`.

The template SERVICE (``sam/members/domain/template_service.py``) depends only on the
``TemplateBodyStore`` Protocol (``put_body`` / ``get_body`` / ``delete_body`` keyed by an
S3 object key) so it carries NO boto3 dependency and stays extractable to
``sam/shared/templates/`` on a second consumer (steering 35, rule of three). THIS module is
the production implementation of that port — the S3 counterpart to how
:class:`~sam.members.repository.members_repository.DynamoDbMembersRepository` is the sole
DynamoDB touch-point. It lives in the repository layer because it is a storage adapter
(design C6 layering): the domain service never imports it; the handler edge injects it.

Why the body lives in S3 (not inline on the DynamoDB item)
----------------------------------------------------------
A template body is HTML that may be large and sits next to logo binaries; a DynamoDB item
caps at 400 KB and must not carry binaries. So the on-plane ``template#<id>`` item carries
only the per-language ``s3_body_key`` ref (see
:func:`~sam.members.repository.table_design.template_body_s3_key`) and the body text lives
in the shared bucket ``myadmin-shared`` under the tenant-prefixed layout the table-design
module owns (``<tenant>/templates/<template_id>/<lang>.html``, steering 23). This store only
reads/writes the OBJECT at a key it is handed — it never assembles the key (the service does,
via the injected key builder from task 2.1), so a tenant-prefix mistake cannot originate here.

Config + fail-fast (mirrors ``table_design.resolve_members_table_name``)
------------------------------------------------------------------------
The bucket NAME is resolved from ``S3_SHARED_BUCKET`` (``myadmin-shared-<env>`` per env) with
NO default — a missing/blank var raises :class:`~services.dynamodb_client.DynamoDBConfigError`
(reusing the one fail-fast ``require_env`` so the no-dangerous-fallback discipline lives in a
single place, steering 23). The boto3 S3 client + the bucket name resolve LAZILY on first use,
so importing this module (and the handler, and the test suite) touches NO AWS. The client is
injectable so a test can supply a fake / a local MinIO without an AWS round-trip.
"""

from __future__ import annotations

from typing import Any

from services.dynamodb_client import REGION_ENV_VAR, require_env

__all__ = [
    "SHARED_BUCKET_ENV_VAR",
    "S3TemplateBodyStore",
    "resolve_shared_bucket_name",
]

#: The env var carrying the shared bucket name (``myadmin-shared-<env>``), env as a suffix per
#: steering 23/43. No default is ever synthesized — a missing/blank var fails fast (mirrors
#: ``MEMBERS_TABLE`` / ``GOVERNANCE_PROJECTION_TABLE``).
SHARED_BUCKET_ENV_VAR = "S3_SHARED_BUCKET"


def resolve_shared_bucket_name() -> str:
    """Return the shared bucket name from ``S3_SHARED_BUCKET``, or fail fast.

    Reuses the T0 fail-fast client (:func:`services.dynamodb_client.require_env`) so the
    no-dangerous-fallback discipline lives in one place.

    Raises:
        services.dynamodb_client.DynamoDBConfigError: ``S3_SHARED_BUCKET`` is missing/blank.
    """
    return require_env(SHARED_BUCKET_ENV_VAR)


class S3TemplateBodyStore:
    """The S3-backed template body store — the production ``TemplateBodyStore`` (R2).

    Structurally satisfies the service's ``TemplateBodyStore`` Protocol (``put_body`` /
    ``get_body`` / ``delete_body``) so the domain service depends on the shape, not this class.
    Every method addresses the object by the S3 key it is handed (the service composes the
    tenant-prefixed key from the task-2.1 layout) within the one shared bucket; this store
    never derives a key itself, so it carries no tenancy logic of its own.

    The S3 client + bucket name are resolved LAZILY + fail-fast on first use so import touches
    no AWS. The client is injectable (dependency inversion) for tests.

    Args:
        client: An optional boto3 S3 client (or a compatible fake). If omitted, resolved lazily
            on first use against the resolved region.
        bucket: An optional bucket name override. If omitted, resolved lazily + fail-fast from
            ``S3_SHARED_BUCKET`` on first use.
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
        """The shared bucket name, resolved lazily + fail-fast from the env on first use."""
        if self._bucket is None:
            self._bucket = resolve_shared_bucket_name()
        return self._bucket

    # ── the TemplateBodyStore port ─────────────────────────────────────────────────────

    def put_body(self, key: str, body_html: str) -> None:
        """Store (or replace) the body HTML text at ``key`` (``text/html; charset=utf-8``)."""
        if not key:
            raise ValueError("body-store key must be non-empty")
        self.client.put_object(
            Bucket=self.bucket,
            Key=key,
            Body=(body_html if isinstance(body_html, str) else str(body_html)).encode(
                "utf-8"
            ),
            ContentType="text/html; charset=utf-8",
        )

    def get_body(self, key: str) -> str | None:
        """Return the body HTML text at ``key``, or ``None`` if the object is absent.

        A missing object (``NoSuchKey`` / ``404``) is a normal "no body yet" answer, not an
        error — it maps to ``None`` so the service can surface the data/ops fault clearly
        rather than crashing. Any other S3 error propagates (fail loud).
        """
        if not key:
            return None
        try:
            response = self.client.get_object(Bucket=self.bucket, Key=key)
        except Exception as exc:  # noqa: BLE001 - narrow to not-found below, re-raise the rest
            if _is_not_found(exc):
                return None
            raise
        body = response.get("Body")
        raw = body.read() if body is not None else b""
        return raw.decode("utf-8") if isinstance(raw, (bytes, bytearray)) else str(raw)

    def delete_body(self, key: str) -> None:
        """Delete the body object at ``key`` (idempotent — an absent key is a no-op)."""
        if not key:
            return
        self.client.delete_object(Bucket=self.bucket, Key=key)


def _is_not_found(exc: Exception) -> bool:
    """True when an S3 exception means "the object does not exist" (vs a real failure).

    boto3 raises ``botocore.exceptions.ClientError`` with an ``Error.Code`` of ``NoSuchKey``
    (or an HTTP ``404``) for a missing object. We read the structured response without importing
    botocore at module import (it is already a transitive dep, but the check stays duck-typed so
    a fake client's exception shapes work too).
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
