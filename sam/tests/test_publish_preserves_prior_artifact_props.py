"""
SAM property test — spec 15 (sam-page-look-and-feel) Property 10 / Req 5.5.

Property 10 — Publish failure preserves the previously published artifact:
    *For any* publish in which Layer 2 fails to produce styling, the Publish_Step SHALL NOT
    replace the previously published Application_Form and SHALL return a failure indication.
    (Validates: Requirements 5.5.)

Req 5.5 (exact): IF the Look_And_Feel_Capability fails to produce styling during the
Publish_Step, THEN THE Publish_Step SHALL NOT replace the previously published
Application_Form and SHALL return a failure indication to the caller.

Why this holds (grounded in the task-7.2 wiring, `application_publish.publish`): the publish
step resolves the tenant's look-and-feel VALUES through the injected
``LookAndFeelSettingsReader`` and runs them through Layer 2 (``render_page_styles``) INSIDE
``render_application_form_page`` — and that render call happens BEFORE the slug claim and
BEFORE the live ``put_object`` artifact write. So a Layer-2 failure (a values mapping carrying
an unsupported attribute → ``UnsupportedAttributeError``) raises out of the render step, before
any write, and the previously published artifact is never touched. The "failure indication to
the caller" is the propagated raise (publish returns NO success dict).

Modelled with in-memory fakes only (no AWS, no DynamoDB):
  * a ``FakeLookAndFeelReader`` returning a values mapping that carries ≥1 unsupported key, so
    Layer 2 rejects it during the render step;
  * a REAL ``S3PublicPageArtifactStore`` over an in-memory fake S3 PRE-SEEDED with a prior
    published ``{slug}/index.html`` + ``{slug}/form.json`` (the "previously published
    Application_Form"); and
  * a REAL ``S3SlugMarkerStore`` over a conditional in-memory fake (claim never reached).

The property asserts, across ≥100 Hypothesis iterations over the space of
supported-subset-plus-unsupported values mappings:
  1. publish RAISES (a failure indication — never a success dict); and
  2. every pre-seeded served artifact is BYTE-IDENTICAL to its prior content, with NO new /
     partial served key written — the previous artifact is preserved intact.

Test-only; no product code is changed. Runs via
``python -m pytest sam/tests/test_publish_preserves_prior_artifact_props.py -c sam/pytest.ini``.

Validates: Requirements 5.5
"""

from __future__ import annotations

import os
import sys

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)
_BACKEND_SRC = os.path.join(_REPO_ROOT, "backend", "src")
if _BACKEND_SRC not in sys.path:
    sys.path.insert(0, _BACKEND_SRC)

from sam.members.domain.application_publish import (
    ApplicationPublishService,
    PublishPipelineNotWired,
)
from sam.members.domain.application_readiness import StaticMailReadinessProvider
from sam.members.repository.public_page_artifact_store import (
    FORM_JSON_ARTIFACT_NAME,
    INDEX_ARTIFACT_NAME,
    S3PublicPageArtifactStore,
)
from sam.members.repository.slug_marker_store import S3SlugMarkerStore
from sam.shared.page_styles import SUPPORTED_ATTRIBUTES

# ── Constants describing the fully-ready tenant + its slug (mirrors the dispatch tests) ──
_TENANT = "h-dcn"
_SLUG = "h-dcn-aanmelden"  # well-formed AND under the default `h-dcn` prefix
_PREFIX = "h-dcn"
_CLAIM_BUCKET = "myadmin-public-pages-test"
_ARTIFACT_BUCKET = "myadmin-public-pages-nonprofit-506221081911"
_DIST_ID = "E1PUBLICPAGES"
_PUBLIC_API_BASE = "https://api.jabaki.nl"

# The exact prior-published bytes we pre-seed and then assert survive byte-for-byte. Distinct,
# recognizable content so a partial/overwritten publish would be obvious.
_PRIOR_INDEX_HTML = b"<!DOCTYPE html><html><head></head><body>PRIOR PUBLISHED FORM v7</body></html>"
_PRIOR_FORM_JSON = b'{"tenant_id":"h-dcn","fields":[{"key":"prior_field"}],"published_version":7}'


@pytest.fixture(autouse=True)
def _set_public_api_base_env(monkeypatch):
    """The publish render step resolves `PUBLIC_API_BASE_URL` fail-fast (no silent default).

    A ready-tenant publish must have it set so the render path reaches the Layer-2 call (where the
    failure we model fires). Note the Layer-2 failure is raised *before* the base is even used to
    write anything — but the resolve runs first, so we supply a representative value.
    """
    monkeypatch.setenv("PUBLIC_API_BASE_URL", _PUBLIC_API_BASE)


# ── In-memory seams (no boto3, no AWS) ────────────────────────────────────────────────


class FakeSlugReader:
    """In-memory ``FormSlugReader`` — returns the configured slug."""

    def __init__(self, slug):
        self._slug = slug

    def get_form_slug(self, tenant_id):
        return self._slug


class FakeFieldConfigReader:
    """In-memory ``PublicFieldConfigReader`` — a schema with ``n`` on-form fields (ready gate)."""

    def __init__(self, on_form_field_count):
        self._n = on_form_field_count

    def get_public_field_config(self, tenant_id):
        return {
            "tenant_id": tenant_id,
            "fields": [{"key": f"f{i}"} for i in range(self._n)],
            "locales": ["nl", "en"],
            "notice": {"version": None},
        }


class FakePrefixReader:
    """In-memory ``PublicPrefixReader`` — returns the configured public prefix."""

    def __init__(self, prefix):
        self._prefix = prefix

    def get_public_prefix(self, tenant_id):
        return self._prefix


class FakeLookAndFeelReader:
    """In-memory ``LookAndFeelSettingsReader`` returning values that trigger a Layer-2 failure.

    Records every call so the test can assert the resolve really ran (and thus Layer 2 was
    reached) on the failing publish path.
    """

    def __init__(self, values):
        self._values = dict(values)
        self.calls = []

    def get_look_and_feel(self, tenant_id):
        self.calls.append(tenant_id)
        return self._values


class _FakeClientError(Exception):
    """Stand-in for botocore ClientError with the structured ``.response`` the stores read."""

    def __init__(self, code, status, message="boom"):
        self.response = {
            "Error": {"Code": code, "Message": message},
            "ResponseMetadata": {"HTTPStatusCode": status},
        }
        super().__init__(f"{code}: {message}")


class _ConditionalFakeS3:
    """In-memory S3 honouring ``If-None-Match: *`` + get/delete (the marker-store fake pattern)."""

    def __init__(self):
        self.objects = {}

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
        import io

        key = (Bucket, Key)
        if key not in self.objects:
            raise _FakeClientError("NoSuchKey", 404, "missing")
        obj = self.objects[key]
        return {"Body": io.BytesIO(obj["body"]), "Metadata": dict(obj["meta"])}

    def delete_object(self, *, Bucket, Key):
        self.objects.pop((Bucket, Key), None)
        return {}


class _ArtifactFakeS3:
    """In-memory S3 for the SERVED ``{slug}/`` artifacts; pre-seedable with a prior publish."""

    def __init__(self):
        self.objects = {}

    def seed(self, key, body):
        """Pre-seed a prior-published served object (the 'previously published form')."""
        self.objects[(_ARTIFACT_BUCKET, key)] = {"body": body, "content_type": None}

    def put_object(self, *, Bucket, Key, Body, ContentType=None, CacheControl=None):
        self.objects[(Bucket, Key)] = {
            "body": Body
            if isinstance(Body, (bytes, bytearray))
            else str(Body).encode("utf-8"),
            "content_type": ContentType,
        }
        return {}


class _FakeCloudFront:
    """In-memory CloudFront — never reached on the failing-render path, present for the writer."""

    def __init__(self):
        self.calls = []

    def create_invalidation(self, *, DistributionId, InvalidationBatch):
        self.calls.append({"dist": DistributionId, "batch": InvalidationBatch})
        return {"Invalidation": {"Id": "I123"}}


def _seeded_artifact_store():
    """A REAL ``S3PublicPageArtifactStore`` over a fake S3 pre-seeded with the prior publish."""
    s3 = _ArtifactFakeS3()
    s3.seed(f"{_SLUG}/{INDEX_ARTIFACT_NAME}", _PRIOR_INDEX_HTML)
    s3.seed(f"{_SLUG}/{FORM_JSON_ARTIFACT_NAME}", _PRIOR_FORM_JSON)
    writer = S3PublicPageArtifactStore(
        s3_client=s3,
        cloudfront_client=_FakeCloudFront(),
        bucket=_ARTIFACT_BUCKET,
        distribution_id=_DIST_ID,
    )
    return writer, s3


def _service(look_and_feel_values, *, marker_store=None, artifact_writer=None):
    """A fully-READY publish service wired with a look-and-feel reader that fails Layer 2."""
    readiness = StaticMailReadinessProvider({_TENANT: (True, "h-dcn.nl")})
    return ApplicationPublishService(
        slug_reader=FakeSlugReader(_SLUG),
        readiness_provider=readiness,
        field_config_reader=FakeFieldConfigReader(1),
        slug_marker_store=marker_store,
        prefix_reader=FakePrefixReader(_PREFIX),
        artifact_writer=artifact_writer,
        look_and_feel_reader=FakeLookAndFeelReader(look_and_feel_values),
    )


# ── Smart generator: supported-subset values PLUS ≥1 unsupported key ──────────────────
# The input space for a Layer-2 FAILURE is "any values mapping carrying a key outside the seven
# supported attributes" (Req 3.4 / `render_page_styles` rejection). We constrain the generator
# to exactly that space: an arbitrary (possibly empty) valid subset of the seven supported
# attributes, merged with 1-4 guaranteed-unsupported keys (text filtered to exclude the
# supported set). Disjoint by construction, so every generated mapping triggers the Layer-2
# failure the property is about — no wasted examples.

_unsupported_key = st.text(min_size=1, max_size=30).filter(
    lambda k: k not in SUPPORTED_ATTRIBUTES
)

_supported_subset = st.dictionaries(
    keys=st.sampled_from(sorted(SUPPORTED_ATTRIBUTES)),
    values=st.text(min_size=1, max_size=20),
    max_size=len(SUPPORTED_ATTRIBUTES),
)

_failing_values = st.builds(
    lambda supported, unsupported: {**supported, **unsupported},
    supported=_supported_subset,
    unsupported=st.dictionaries(
        keys=_unsupported_key,
        values=st.one_of(st.text(max_size=20), st.integers(), st.booleans(), st.none()),
        min_size=1,
        max_size=4,
    ),
)


@settings(max_examples=150)
@given(values=_failing_values)
def test_property_10_publish_failure_preserves_the_previously_published_artifact(values):
    """Feature: sam-page-look-and-feel, Property 10: For any publish in which Layer 2 fails to produce styling, the Publish_Step SHALL NOT replace the previously published Application_Form and SHALL return a failure indication.

    Validates: Requirements 5.5

    A fully-ready tenant publishes, but the resolved look-and-feel VALUES carry an unsupported
    attribute, so Layer 2 (`render_page_styles`, inside `render_application_form_page`) rejects
    the render — which runs BEFORE the slug claim and the live artifact write. The property:
      1. publish RAISES (a failure indication — never a success dict); and
      2. the previously published served artifacts are BYTE-IDENTICAL to their prior content,
         with NO new / partial served key written.
    """
    marker_store = S3SlugMarkerStore(
        client=_ConditionalFakeS3(), bucket=_CLAIM_BUCKET
    )
    writer, served_s3 = _seeded_artifact_store()

    # Snapshot the prior-published served objects BEFORE the failed publish (deep copy of bytes).
    before = {
        key: bytes(obj["body"]) for key, obj in served_s3.objects.items()
    }

    svc = _service(values, marker_store=marker_store, artifact_writer=writer)

    # 1. Failure indication: publish must RAISE (never return a success dict). Layer 2's
    #    UnsupportedAttributeError is a ValueError subclass; the publish surfaces no {'success': ...}.
    result = None
    with pytest.raises(Exception) as excinfo:  # noqa: PT011 - broad: any raise is a failure indication
        result = svc.publish(_TENANT)
    assert result is None  # nothing returned — no success dict escaped
    # The failure is the Layer-2 rejection, NOT the dormant-seam marker (writer IS injected, so a
    # successful render would have reached the live write, not PublishPipelineNotWired).
    assert not isinstance(excinfo.value, PublishPipelineNotWired)

    # 2. The previously published artifact is preserved — byte-identical, no new/partial key.
    after = {key: bytes(obj["body"]) for key, obj in served_s3.objects.items()}
    assert after.keys() == before.keys()  # no new served key written, none removed
    for key in before:
        assert after[key] == before[key]  # byte-for-byte unchanged
    # Concretely: the seeded prior bytes are exactly what remains under the served prefix.
    assert (
        served_s3.objects[(_ARTIFACT_BUCKET, f"{_SLUG}/{INDEX_ARTIFACT_NAME}")]["body"]
        == _PRIOR_INDEX_HTML
    )
    assert (
        served_s3.objects[(_ARTIFACT_BUCKET, f"{_SLUG}/{FORM_JSON_ARTIFACT_NAME}")]["body"]
        == _PRIOR_FORM_JSON
    )
