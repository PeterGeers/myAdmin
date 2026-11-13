"""
Members edge — route-dispatch SHARED seams, helpers, and exceptions (split from ``_dispatch``).

This module is the cohesion seam shared by the per-resource dispatch groups
(:mod:`sam.members.handler._dispatch_members`,
:mod:`sam.members.handler._dispatch_analytics`,
:mod:`sam.members.handler._dispatch_config`). It owns, with ZERO behaviour change:

- the lazily-built, warm-reused **standalone service accessors** (template,
  execute-and-deliver, mail-run status, config-write, config#fields Change-Op, and
  application-form publish) plus their production shim classes — each resolves its
  AWS resource lazily + fail-fast, so importing the module (and the auth-only tests)
  touches no AWS, and tests patch the accessor / module-global to inject fakes;
- the dispatch-layer **exceptions** (:class:`RouteNotImplemented`,
  :class:`MailRunNotFound`, :class:`StaleClientBundleError`) the handler maps to
  501 / 404 / 409;
- the small **request/body helpers** and the config#fields Change-Op body parsing the
  resource groups share;
- the :data:`UNHANDLED` sentinel the per-resource group dispatchers return when a route
  ``name`` is not theirs, so :func:`sam.members.handler._dispatch.dispatch_route` can try
  each group in the SAME declaration order the original single ``if name == ...`` chain had.

Re-exported from :mod:`sam.members.handler.app` (via ``_dispatch``); the module's public
import surface is unchanged. Pure structural split (code-quality task 4) — no behaviour change.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

if (
    TYPE_CHECKING
):  # pragma: no cover - typing only, avoids an app<->_dispatch import cycle
    from sam.members.domain.template_service import TemplateService

from ._dispatch_services_helpers import (  # noqa: F401 (surface compat)
    MailRunNotFound,
    RouteNotImplemented,
    StaleClientBundleError,
    _apply_one_config_fields_op,
    _caller_is_tenant_admin,
    _delivery_outcome_to_dict,
    _dispatch_config_fields_ops,
    _mail_failure_to_dict,
    _mail_job_to_envelope,
    _mail_run_to_dict,
    _new_run_id,
    _parse_ad_hoc_body,
    _parse_page_size,
    _query_flag,
    _require_path_param,
    _row_tuple,
    _str_tuple,
    _verified_email,
    _write_body,
)
from ._dispatch_services_shared import (  # noqa: F401 (surface compat)
    _ATTR_OPS,
    _FIELD_IDENTITY_OPS,
    _FIELDS_OP_METHODS,
    _FIXED_PAGE_SIZES,
    _PAGE_SIZE_MAX,
    _WHOLE_OVERLAY_BODY_KEYS,
    _WRITABLE_CONFIG_IDS,
    UNHANDLED,
)

_TEMPLATE_SERVICE: TemplateService | None = None


def get_template_service() -> TemplateService:
    """Return the module-global :class:`TemplateService`, building it once at cold start.

    Wires the template service (R2) over the tenant-scoped
    :class:`~sam.members.repository.members_repository.DynamoDbMembersRepository` (its four
    ``*_template`` methods structurally satisfy the service's ``TemplateMetadataStore`` port)
    and the S3-backed
    :class:`~sam.members.repository.template_body_store.S3TemplateBodyStore`. Both the table and
    the bucket resolve lazily + fail-fast on first use, so importing the module (and the
    auth-only tests) never touches AWS. Tests patch this accessor (or set ``_TEMPLATE_SERVICE``)
    to inject a service over in-memory fakes.
    """
    global _TEMPLATE_SERVICE
    if _TEMPLATE_SERVICE is None:
        from sam.members.domain.template_service import TemplateService
        from sam.members.repository.members_repository import DynamoDbMembersRepository
        from sam.members.repository.template_body_store import S3TemplateBodyStore

        _TEMPLATE_SERVICE = TemplateService(
            DynamoDbMembersRepository(), S3TemplateBodyStore()
        )
    return _TEMPLATE_SERVICE


_EXECUTE_AND_DELIVER_SERVICE: Any = None


class _PassThroughPivotRunner:
    """Production ``PivotRunner`` shim — returns the re-fetched member rows as the result rows.

    The pivot/list computation is not yet built on the SAM plane (design §4.2 — it runs
    frontend/Flask-side today), but the ``deliver`` route must still resolve the set, re-fetch
    the tenant's rows, and fan them out into send jobs. For both delivery modes the result rows
    ARE the member rows (``per_recipient`` mails each; ``to_fixed`` attaches the set), so a
    faithful pass-through is the honest interim runner. It satisfies the service's ``PivotRunner``
    Protocol, so when the real pivot engine lands it replaces this shim with no service change.
    """

    def run(
        self, tenant_id: str, definition: Mapping[str, Any], rows: Any
    ) -> list[Any]:
        return list(rows)


class _SqsMailQueueAdapter:
    """Bridge the task-4.1 ``MailQueue`` port (``enqueue(MailJob)``) onto ``SqsMailSendQueue``.

    The service builds frozen :class:`~sam.members.domain.execute_and_deliver.MailJob` records
    and enqueues them through the ``MailQueue`` Protocol (``enqueue(job) -> None``). The
    production :class:`~sam.members.repository.mail_send_queue.SqsMailSendQueue` instead takes a
    plain JSON-serializable mapping (``enqueue(Mapping) -> str``) — the send-job envelope the
    worker (task 4.3) consumes. This adapter flattens a ``MailJob`` into that envelope and
    forwards it, so the domain service stays storage-agnostic and the SQS adapter stays
    shape-agnostic (neither learns about the other).
    """

    def __init__(self, sqs_queue: Any) -> None:
        self._queue = sqs_queue

    def enqueue(self, job: Any) -> None:
        self._queue.enqueue(_mail_job_to_envelope(job))


def get_execute_and_deliver_service() -> Any:
    """Return the module-global execute-and-deliver service, building it once at cold start (R4).

    Wires the task-4.1 service over its THREE ports:
      * the tenant-scoped :class:`~sam.members.repository.members_repository.DynamoDbMembersRepository`
        (its ``get_analytics_set`` + ``list_members`` pin ``tenant_id`` — Property 1);
      * :class:`_PassThroughPivotRunner` (the interim production pivot runner — design §4.2);
      * :class:`_SqsMailQueueAdapter` over the SQS-backed
        :class:`~sam.members.repository.mail_send_queue.SqsMailSendQueue`.

    The table and the queue resolve lazily + fail-fast on first use, so importing the module
    (and the auth-only tests) never touches AWS. Tests patch this accessor (or set
    ``_EXECUTE_AND_DELIVER_SERVICE``) to inject a service over an in-memory fake repo + a fake
    queue.
    """
    global _EXECUTE_AND_DELIVER_SERVICE
    if _EXECUTE_AND_DELIVER_SERVICE is None:
        from sam.members.domain.execute_and_deliver import ExecuteAndDeliverService
        from sam.members.domain.mail_sender_resolver import MailSenderResolver
        from sam.members.repository.mail_send_queue import SqsMailSendQueue
        from sam.members.repository.members_repository import DynamoDbMembersRepository
        from sam.members.repository.projection_config_reader import (
            MembersProjectionReader,
        )

        # The pre-send certification resolver reads the PROJECTED config#mail flags (Option B —
        # no live SES call on the send path); MembersProjectionReader satisfies its
        # MailConfigReader seam by duck-typing. The table resolves lazily + fail-fast on first use.
        _EXECUTE_AND_DELIVER_SERVICE = ExecuteAndDeliverService(
            DynamoDbMembersRepository(),
            _PassThroughPivotRunner(),
            _SqsMailQueueAdapter(SqsMailSendQueue()),
            MailSenderResolver(MembersProjectionReader()),
        )
    return _EXECUTE_AND_DELIVER_SERVICE


_MAIL_RUN_STATUS_SERVICE: Any = None


def get_mail_run_status_service() -> Any:
    """Return the module-global mail-run status service, building it once at cold start (R9).

    Wires the task-3.2 :class:`~sam.members.domain.mail_run_status.MailRunStatusService` over
    the tenant-scoped
    :class:`~sam.members.repository.members_repository.DynamoDbMembersRepository` (its
    ``list_mail_runs`` / ``get_mail_run`` / ``list_mail_run_failures`` pin ``tenant_id`` —
    Property 3). The table resolves lazily + fail-fast on first use, so importing the module
    (and the auth-only tests) never touches AWS. Tests patch this accessor (or set
    ``_MAIL_RUN_STATUS_SERVICE``) to inject a service over an in-memory fake repo.
    """
    global _MAIL_RUN_STATUS_SERVICE
    if _MAIL_RUN_STATUS_SERVICE is None:
        from sam.members.domain.mail_run_status import MailRunStatusService
        from sam.members.repository.members_repository import DynamoDbMembersRepository

        _MAIL_RUN_STATUS_SERVICE = MailRunStatusService(DynamoDbMembersRepository())
    return _MAIL_RUN_STATUS_SERVICE


_CONFIG_WRITE_SERVICE: Any = None


def get_config_write_service() -> Any:
    """Return the module-global config-write service, building it once at cold start (Task 1.6).

    Wires the :class:`~sam.members.domain.config_write_service.ConfigWriteService` (Component 2)
    over the net-new :class:`~sam.members.repository.projection_config_write_repository.MembersConfigWriteRepository`
    (Component 3). The write repository resolves its table lazily + fail-fast on first real
    ``put_item`` (``GOVERNANCE_PROJECTION_TABLE``, no default), so importing the module (and the
    auth-only tests) never touches AWS. Tests patch this accessor (or set ``_CONFIG_WRITE_SERVICE``)
    to inject a service over an in-memory fake repo.
    """
    global _CONFIG_WRITE_SERVICE
    if _CONFIG_WRITE_SERVICE is None:
        from sam.members.domain.config_write_service import ConfigWriteService
        from sam.members.repository.projection_config_reader import (
            MembersProjectionReader,
        )
        from sam.members.repository.projection_config_write_repository import (
            MembersConfigWriteRepository,
        )

        # MERGE-ON-WRITE for config#fields (bugfix): the write reads the CURRENT stored overlay
        # and merges the incoming slices onto it, so a partial PUT (e.g. the Application Form
        # Builder sending only application-attribute toggles) can no longer wipe the tenant's other
        # slices. Pass the reader as a FACTORY (the class itself — a zero-arg callable) so each
        # write's merge builds a FRESH reader and reads uncached current state; a module-global
        # shared reader would serve STALE partition data to a later write on a warm Lambda. The
        # reader resolves its table lazily + fail-fast, same as the write repo, so cold import
        # still touches no AWS.
        _CONFIG_WRITE_SERVICE = ConfigWriteService(
            MembersConfigWriteRepository(),
            overlay_reader_factory=MembersProjectionReader,
        )
    return _CONFIG_WRITE_SERVICE


_CONFIG_FIELDS_CRUD_SERVICE: Any = None


class _FreshReaderIndirection:
    """A stable reader indirection that reads a FRESH projection per call.

    The :class:`ConfigFieldsCrudService` holds one reader reference for its lifetime; to avoid a
    stale warm-container partition cache (the validate-and-place read must reflect current state,
    design-review Should-fix), every read delegates to a NEWLY built
    :class:`~sam.members.repository.projection_config_reader.MembersProjectionReader`. Forwards the
    ``consistent_read`` kwarg the service passes (so the strongly-consistent validate-and-place
    read reaches the underlying Query). Building the reader touches no AWS (lazy fail-fast table).

    It exposes BOTH reads the Change-Op service needs: ``get_raw_fields_overlay`` (the authoring
    WIRE shape for placement) and ``get_config_fields_version`` (the SEPARATE control-plane read
    for the optimistic-lock ``version`` — never mixed into the wire shape, which feeds
    ``field_overlay`` API responses and must not carry ``version``).
    """

    def get_raw_fields_overlay(
        self, tenant_id: str, consistent_read: bool = False
    ) -> dict:
        from sam.members.repository.projection_config_reader import (
            MembersProjectionReader,
        )

        reader = MembersProjectionReader()
        try:
            return reader.get_raw_fields_overlay(
                tenant_id, consistent_read=consistent_read
            )
        except TypeError:
            # A reader whose signature predates the consistent_read kwarg — fall back to the
            # default read (the flag is a strengthening, not a placement precondition).
            return reader.get_raw_fields_overlay(tenant_id)

    def get_config_fields_version(
        self, tenant_id: str, consistent_read: bool = False
    ) -> str | None:
        from sam.members.repository.projection_config_reader import (
            MembersProjectionReader,
        )

        reader = MembersProjectionReader()
        try:
            return reader.get_config_fields_version(
                tenant_id, consistent_read=consistent_read
            )
        except TypeError:
            return reader.get_config_fields_version(tenant_id)


def get_config_fields_crud_service() -> Any:
    """Return the module-global config#fields Change-Op service, built once at cold start (2.7).

    Wires the :class:`~sam.members.domain.config_fields_crud_service.ConfigFieldsCrudService`
    (design C1) over the net-new
    :class:`~sam.members.repository.projection_config_write_repository.MembersConfigWriteRepository`
    `apply_ops` path writer (design C2) + a fresh-per-call projection reader (the validate-and-
    place read, :class:`_FreshReaderIndirection`). Both resolve their table lazily + fail-fast on
    first use, so importing the module (and the auth-only tests) never touches AWS. Tests patch
    this accessor (or set ``_CONFIG_FIELDS_CRUD_SERVICE``) to inject a service over in-memory fakes.
    """
    global _CONFIG_FIELDS_CRUD_SERVICE
    if _CONFIG_FIELDS_CRUD_SERVICE is None:
        from sam.members.domain.config_fields_crud_service import (
            ConfigFieldsCrudService,
        )
        from sam.members.repository.projection_config_reader import (
            MembersProjectionReader,
        )
        from sam.members.repository.projection_config_write_repository import (
            MembersConfigWriteRepository,
        )
        from sam.members.repository.slug_marker_store import S3SlugMarkerStore

        # bugfix-slug-lifecycle task 3.1: the slug-author op (`set_form_slug`) needs the shared
        # `_slugs/{slug}` marker store (the SAME store the publish path claims through) + the
        # tenant's own public-prefix reader (its projected `tenant` row) for the SEC-4 ownership
        # check. Both resolve their AWS resource lazily + fail-fast on first use, so cold import
        # still touches no AWS; the marker store's S3 client is injectable. A FRESH prefix reader
        # per build is fine — the prefix read is a plain forward read, not the version-sensitive
        # placement read the Change-Op write uses (that stays the `_FreshReaderIndirection`).
        # bugfix-slug-lifecycle task 3.2: a slug CHANGE (the tenant already owns a different stored
        # slug) is handled by `S3SlugMarkerStore.rename` (claim-new-before-release-old, R4.6) so the
        # old `_slugs/{old}` marker is not orphaned. The op detects a change via the forward
        # `get_form_slug` read — the SAME `MembersProjectionReader` already wired as `prefix_reader`
        # exposes it, so it also serves as the `slug_reader` (a plain forward read, not the
        # version-sensitive placement read the Change-Op write uses).
        _slug_projection_reader = MembersProjectionReader()
        _CONFIG_FIELDS_CRUD_SERVICE = ConfigFieldsCrudService(
            MembersConfigWriteRepository(),
            reader=_FreshReaderIndirection(),
            slug_marker_store=S3SlugMarkerStore(),
            prefix_reader=_slug_projection_reader,
            slug_reader=_slug_projection_reader,
        )
    return _CONFIG_FIELDS_CRUD_SERVICE


_APPLICATION_PUBLISH_SERVICE: Any = None


def get_application_publish_service() -> Any:
    """Return the module-global application-form publish service, built once at cold start (2.1).

    Wires the :class:`~sam.members.domain.application_publish.ApplicationPublishService` over its
    three read-only seams, all satisfied without duplicating any readiness logic:

      * the forward slug reader + the certified-sender provider are BOTH the DynamoDB-backed
        :class:`~sam.members.repository.projection_config_reader.MembersProjectionReader`
        (its ``get_form_slug`` satisfies ``FormSlugReader``; its ``is_mail_certified`` /
        ``get_mail_domain`` satisfy the shared ``MailReadinessProvider`` the submit gate uses);
      * the on-form-field count reads the public field-config through the SINGLE filter authority
        (the production :class:`~sam.members.domain.membership_service.MembershipService`'s
        ``get_public_field_config``) — reused via :func:`sam.members.handler.app._get_membership_service`
        so publish and submit never drift on "which fields are on the form".

    The table resolves lazily + fail-fast on first use, so importing the module (and the auth-only
    tests) never touches AWS. Tests patch this accessor (or set ``_APPLICATION_PUBLISH_SERVICE``)
    to inject a service over in-memory fakes.
    """
    global _APPLICATION_PUBLISH_SERVICE
    if _APPLICATION_PUBLISH_SERVICE is None:
        from sam.members.domain.application_publish import ApplicationPublishService
        from sam.members.handler.app import _get_membership_service
        from sam.members.repository.projection_config_reader import (
            MembersProjectionReader,
        )
        from sam.members.repository.public_page_artifact_store import (
            S3PublicPageArtifactStore,
        )
        from sam.members.repository.slug_marker_store import S3SlugMarkerStore

        reader = MembersProjectionReader()
        _APPLICATION_PUBLISH_SERVICE = ApplicationPublishService(
            slug_reader=reader,
            readiness_provider=reader,
            field_config_reader=_get_membership_service(),
            # spec 14 Task 8.1: the publish flow CLAIMS its slug via the shared `_slugs/{slug}`
            # marker store (Task 1) and resolves the tenant's own public prefix off its projected
            # `tenant` row (Task 6.3) for the SEC-4 ownership check. The store's S3 client is lazy +
            # injectable.
            slug_marker_store=S3SlugMarkerStore(),
            prefix_reader=reader,
            # spec 14 Task 9.1 (GATED live wiring): the LIVE write of the SERVED `{slug}/index.html`
            # + `{slug}/form.json` artifacts + the best-effort CloudFront invalidation. The store
            # resolves the SAME nonprofit bucket/distribution the landing publish uses
            # (`LANDING_PAGES_BUCKET` + `CLOUDFRONT_PUBLIC_PAGES_DISTRIBUTION_ID`, D7 — never a new
            # resource); its S3/CloudFront clients are lazy + injectable. A denied invalidation is
            # non-fatal (known-deferred to Task 9.2 SEC-8 IAM) — the put is authoritative.
            artifact_writer=S3PublicPageArtifactStore(),
            # Round 3 Defect 4: persist `published_version` / `published_at` on `config#fields`
            # after the artifact write, via the CRUD service's version-conditional Change-Op.
            publish_state_writer=_CrudPublishStateWriter(),
            # spec 15 Task 9 (C6 — Layer-3 wiring): inject the REAL look-and-feel reader so the
            # publish path resolves the tenant's stored presentation VALUES (the `look_and_feel`
            # slice on `config#fields`) and feeds them through Layer 2 (`render_page_styles`) into
            # the renderer's `branding=` — closing the Req 5 defect. The SAME DynamoDB-backed
            # `MembersProjectionReader` already wired as `slug_reader` / `readiness_provider` /
            # `prefix_reader` satisfies the `LookAndFeelSettingsReader` Protocol via its
            # `get_look_and_feel(tenant_id)` method; reusing the one reader keeps publish on a
            # single resolved-view read and touches no new AWS. When a test injects a service
            # WITHOUT this reader the renderer falls back to its defaults (backward compatible).
            look_and_feel_reader=reader,
        )
    return _APPLICATION_PUBLISH_SERVICE


class _CrudPublishStateWriter:
    """``PublishStateWriter`` backed by ``ConfigFieldsCrudService.set_publish_state`` (lazy)."""

    def record_publish(
        self, tenant_id: str, *, published_version: int, published_at: str
    ) -> None:
        get_config_fields_crud_service().set_publish_state(
            tenant_id,
            published_version=published_version,
            published_at=published_at,
        )


_LOOK_AND_FEEL_SETTINGS_SERVICE: Any = None


def get_look_and_feel_settings_service() -> Any:
    """Return the module-global look-and-feel settings service, built once at cold start (spec 15 Task 9).

    Wires the :class:`~sam.members.domain.look_and_feel_settings_service.LookAndFeelSettingsService`
    (design C3 / C6) over its two real seams, both reused from elsewhere in this composition root:

      * the resolved-view READER — the DynamoDB-backed
        :class:`~sam.members.repository.projection_config_reader.MembersProjectionReader` (its
        ``get_look_and_feel`` satisfies the service's ``LookAndFeelSettingsReader``);
      * the Change-Op WRITER — the shared config#fields Change-Op service from
        :func:`get_config_fields_crud_service` (its ``set_look_and_feel`` /
        ``remove_look_and_feel`` / ``copy_look_and_feel`` adapters satisfy
        ``LookAndFeelSettingsWriter``), so the authoring write rides the same version-conditional,
        path-scoped `apply_ops` contract as every other config#fields write.

    Both resolve their table lazily + fail-fast on first use, so importing the module (and the
    auth-only tests) never touches AWS. Tests patch this accessor (or set
    ``_LOOK_AND_FEEL_SETTINGS_SERVICE``) to inject a service over in-memory fakes.
    """
    global _LOOK_AND_FEEL_SETTINGS_SERVICE
    if _LOOK_AND_FEEL_SETTINGS_SERVICE is None:
        from sam.members.domain.look_and_feel_settings_service import (
            LookAndFeelSettingsService,
        )
        from sam.members.repository.projection_config_reader import (
            MembersProjectionReader,
        )

        _LOOK_AND_FEEL_SETTINGS_SERVICE = LookAndFeelSettingsService(
            reader=MembersProjectionReader(),
            writer=get_config_fields_crud_service(),
        )
    return _LOOK_AND_FEEL_SETTINGS_SERVICE
