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

from services import projection_schema as schema

from sam.members.domain.execute_and_deliver import AdHocMailBody
from sam.members.handler._http import ParsedRequest
from sam.members.handler.routes import CAP_MEMBERS_ADMIN
from sam.shared.auth_utils import has_capability

if (
    TYPE_CHECKING
):  # pragma: no cover - typing only, avoids an app<->_dispatch import cycle
    from sam.members.domain.config_fields_crud_service import ConfigFieldsCrudError
    from sam.members.domain.template_service import TemplateService
    from sam.members.handler.app import RequestContext


#: Sentinel a per-resource group dispatcher returns when the route ``name`` is NOT one of
#: its routes, so :func:`sam.members.handler._dispatch.dispatch_route` moves on to the next
#: group IN DECLARATION ORDER — preserving the exact fall-through of the original single
#: ``if name == ...`` chain (literal-route-before-``{param}`` ordering is decided by the
#: router, not here, so group order only needs to be stable, which it is). A group that
#: returns anything else (including ``None``) HANDLED the route.
UNHANDLED: Any = object()


# ── Template service seam (R2 — pivot-output-actions task 2.3) ─────────────────────────
#
# The template CRUD routes are backed by the standalone
# :class:`~sam.members.domain.template_service.TemplateService` (not the MembershipService).
# It is resolved lazily once (warm-reuse) over the production repository (which structurally
# satisfies the service's metadata-store port) + the S3-backed body store, mirroring
# :func:`sam.members.handler.app._get_membership_service`. A test replaces :data:`_TEMPLATE_SERVICE`
# (or patches :func:`get_template_service`) with a service over in-memory fakes, so no AWS is
# touched. Kept HERE (not on the ``app`` facade) because the template dispatch lives here; the
# accessor is module-global so warm invocations reuse one service.

#: The module-global template service, built once at cold start (``None`` until first use).
_TEMPLATE_SERVICE: "TemplateService | None" = None


def get_template_service() -> "TemplateService":
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


# ── Execute-and-deliver service seam (R4 — pivot-output-actions task 4.2) ──────────────
#
# The `deliver` route (`POST /members/analytics-sets/{set_id}/deliver`) is backed by the
# standalone :class:`~sam.members.domain.execute_and_deliver.ExecuteAndDeliverService` (task
# 4.1 — NOT the MembershipService). It is resolved lazily once (warm-reuse), mirroring
# :func:`get_template_service` / :func:`app._get_membership_service`. A test replaces
# :data:`_EXECUTE_AND_DELIVER_SERVICE` (or patches :func:`get_execute_and_deliver_service`) with
# a service over an in-memory fake repo + a FAKE queue, so no AWS/SQS is touched. Kept HERE (not
# on the ``app`` facade) because the deliver dispatch lives here; the accessor is module-global
# so warm invocations reuse one service.
#
# The task-4.1 service takes THREE injected ports — ``(repo, pivot_runner, queue)`` — and the
# ``MailQueue`` port it enqueues through is ``enqueue(MailJob) -> None``. Two thin production
# shims bridge that service to this stack's existing adapters:
#   * ``_PassThroughPivotRunner`` — the pivot/list engine is not built on the SAM plane yet
#     (design §4.2: today the pivot runs frontend/Flask-side), so the production runner passes
#     the re-fetched member rows through as the result rows. It satisfies the service's
#     ``PivotRunner`` Protocol; when the real engine lands it drops in unchanged.
#   * ``_SqsMailQueueAdapter`` — the production ``SqsMailSendQueue`` enqueues a plain JSON
#     mapping (``enqueue(Mapping) -> str``); the service hands it a frozen ``MailJob`` and
#     expects ``enqueue(MailJob) -> None``. This adapter converts the job to the JSON send-job
#     envelope the worker (task 4.3) consumes and forwards it, satisfying the ``MailQueue`` port.

#: The module-global execute-and-deliver service, built once at cold start (``None`` until first use).
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

    def __init__(self, sqs_queue: Any):
        self._queue = sqs_queue

    def enqueue(self, job: Any) -> None:
        self._queue.enqueue(_mail_job_to_envelope(job))


def _mail_job_to_envelope(job: Any) -> dict[str, Any]:
    """Flatten a frozen ``MailJob`` into the JSON send-job envelope the worker consumes (task 4.3)."""
    return {
        "job_id": job.job_id,
        "tenant_id": job.tenant_id,
        "set_id": job.set_id,
        "run_id": job.run_id,
        "mode": job.mode,
        "recipients": list(job.recipients),
        # The resolved tenant From + the user's Reply-To, stamped at enqueue (mail-spec task 1.3)
        # — the worker FORWARDS them to SES without re-resolving (Property 2).
        "from_address": job.from_address,
        "reply_to": job.reply_to,
        "template_id": job.template_id,
        "merge_values": dict(job.merge_values),
        "attachment": dict(job.attachment) if job.attachment is not None else None,
        "rows": [dict(r) for r in job.rows],
        # The DISPLAY names ride the envelope so the worker (task 6.2) can NAME the export
        # (`{Tenant_Name}-{Pivot_Name}.csv`) + PREFIX the subject without a second lookup
        # (members-overview-tweaks R5.2/R5.3/R5.5). `tenant_id` / `set_id` above are opaque
        # keys; these were stamped onto the MailJob at enqueue from the AUTHORITATIVE verified
        # tenant context + the stored set — never a request-body value. Defaulted to "" on a
        # job that predates the fields (additive, backward-compatible); the worker falls back
        # to a safe generic name when either is blank.
        "tenant_name": job.tenant_name,
        "pivot_name": job.pivot_name,
    }


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


# ── Send-run status read service seam (R9 — mail-spec task 3.2) ───────────────────────
#
# The two mail-run READ routes (`GET /members/mail-runs[/{run_id}]`) are backed by the
# standalone :class:`~sam.members.domain.mail_run_status.MailRunStatusService` (NOT the
# MembershipService) over the tenant-pinned repository's task-3.1 read methods
# (`list_mail_runs` / `get_mail_run` / `list_mail_run_failures`). It is resolved lazily once
# (warm-reuse), mirroring :func:`get_template_service` / :func:`get_execute_and_deliver_service`.
# A test replaces :data:`_MAIL_RUN_STATUS_SERVICE` (or patches :func:`get_mail_run_status_service`)
# with a service over an in-memory fake repo, so no AWS is touched. The user-vs-admin SCOPING
# (R9.3) is resolved HERE in the dispatch (from the verified sub + the members:admin entitlement)
# and handed to the service as a plain boolean — the service holds the scope rule, the edge holds
# the auth fact (verify-before-trust).

#: The module-global mail-run status service, built once at cold start (``None`` until first use).
_MAIL_RUN_STATUS_SERVICE: Any = None


class MailRunNotFound(Exception):
    """Raised when a requested send-run is not visible to the caller (→ 404).

    Either the run does not exist in the tenant, OR it exists but was triggered by ANOTHER
    user and the caller is not a Tenant_Admin (R9.3). The two cases are deliberately
    INDISTINGUISHABLE — a non-admin cannot tell "no such run" apart from "someone else's run",
    so a scoped caller cannot probe for another user's runs (mirrors the member-read 404
    not-found policy). The edge maps this to a 404.
    """

    def __init__(self, run_id: str):
        self.run_id = run_id
        super().__init__(f"mail run '{run_id}' not found or not visible")


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


# ── Config-write service seam (spec 02, Task 1.6 — design C1/C2) ──────────────────────
#
# The `write_config` route (`PUT /members/config/{configId}`) is backed by the standalone
# :class:`~sam.members.domain.config_write_service.ConfigWriteService` (Component 2 — NOT the
# MembershipService). It validates the per-`configId` body shape, stamps the row-level version,
# and delegates the versioned put to the
# :class:`~sam.members.repository.projection_config_write_repository.MembersConfigWriteRepository`
# (Component 3). It is resolved lazily once (warm-reuse), mirroring
# :func:`get_template_service` / :func:`get_execute_and_deliver_service`. A test replaces
# :data:`_CONFIG_WRITE_SERVICE` (or patches :func:`get_config_write_service`) with a service over
# an in-memory fake repo, so no AWS is touched. Kept HERE (not on the ``app`` facade) because the
# config-write dispatch lives here; the accessor is module-global so warm invocations reuse one
# service.

#: The CLOSED set of writable config ids the GENERIC ``write_config`` route (``PUT
#: /members/config/{configId}`` → whole-object ``put_config``) accepts (R2.2/R2.5). The repository
#: re-checks the writable surface (defense in depth), but the edge rejects an id outside the set
#: FIRST, before any write — so `views`/unknown is a 400 and the write path is never entered
#: (Config_Views_Residue never authored). The tokens come from the shared projection schema so
#: route, repo, and reader agree.
#:
#: ``config#fields`` is DELIBERATELY EXCLUDED here (spec 03 Task 7.1 — R1.5 / R11.1): the generic
#: whole-object door SHALL NOT dispatch ``fields`` to the whole-row ``put_config`` at all. The
#: ONLY client-reachable write for ``config#fields`` is the Change-Op route (``PUT
#: /members/config/fields`` → ``write_config_fields`` → ``apply_ops``). Removing ``fields`` from
#: this set makes the dangerous whole-object replace STRUCTURALLY unreachable from a request — not
#: merely shadowed by route declaration order (the literal ``/members/config/fields`` route winning
#: over ``{configId}``). Even a direct ``PUT /members/config/fields`` that somehow reached this
#: generic branch is now rejected here with a caller-safe 400 before any ``put_config``, so the
#: whole-row replace cannot be misused to truncate the catalog (the root-cause defect). The
#: whole-row ``put_config`` survives ONLY as an internal primitive — the C6 ``ensure_skeleton``
#: create + the LIST→MAP migration — never on a client path. ``scope`` / ``mail`` keep their
#: existing whole-object write contract (Task 7.1 is scoped to ``fields`` per R1.5).
_WRITABLE_CONFIG_IDS = frozenset({schema.CONFIG_ID_SCOPE, schema.CONFIG_ID_MAIL})

#: The module-global config-write service, built once at cold start (``None`` until first use).
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


# ── config#fields Change-Op service seam (spec 03 Task 2.7 — design C1/C2) ────────────
#
# The `write_config_fields` route (`PUT /members/config/fields`, design-review Q7a) is backed by
# the standalone :class:`~sam.members.domain.config_fields_crud_service.ConfigFieldsCrudService`
# (NOT the ConfigWriteService whole-overlay path). It accepts a Change-Op list (identity-keyed
# ops), decides storage placement server-side, and delegates each op to a single version-
# conditional `update_item` path write via the SAME
# :class:`~sam.members.repository.projection_config_write_repository.MembersConfigWriteRepository`
# `apply_ops` contract — so a partial payload can never truncate the catalog (spec 03 root cause).
# Resolved lazily once (warm-reuse), mirroring :func:`get_config_write_service`. A test replaces
# :data:`_CONFIG_FIELDS_CRUD_SERVICE` (or patches :func:`get_config_fields_crud_service`) with a
# service over an in-memory fake repo (+ optional fake reader), so no AWS is touched.
#
# The reader is wired as a FRESH per-request projection reader via a thin factory indirection
# (same staleness argument as :func:`get_config_write_service`): the service reads the resolved
# `config#fields` row STRONGLY-CONSISTENT only to validate + decide placement/version, so each op
# must see current partition state, never a warm-container cache. Building the reader touches no
# AWS (its table resolves lazily + fail-fast on the first Query).

#: The module-global config#fields Change-Op service, built once at cold start (``None`` until first use).
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

    def get_raw_fields_overlay(self, tenant_id, consistent_read: bool = False):
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

    def get_config_fields_version(self, tenant_id, consistent_read: bool = False):
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
        from sam.members.repository.projection_config_write_repository import (
            MembersConfigWriteRepository,
        )

        _CONFIG_FIELDS_CRUD_SERVICE = ConfigFieldsCrudService(
            MembersConfigWriteRepository(),
            reader=_FreshReaderIndirection(),
        )
    return _CONFIG_FIELDS_CRUD_SERVICE


# ── Application-form publish service seam (spec 12 Task 2.1 — design §C4 / R5) ─────────
#
# The `publish_application_form` route (`POST /members/application-form/publish`) is backed by the
# standalone :class:`~sam.members.domain.application_publish.ApplicationPublishService` (NOT the
# MembershipService). It owns the readiness gate (slug + certified sender + ≥1 on-form field,
# R5.4) — REAL and tested here — and the publish seam, whose live S3 render/write + CloudFront
# invalidation is task 2.2 and stays DORMANT (the seam raises PublishPipelineNotWired). It is
# resolved lazily once (warm-reuse), mirroring :func:`get_config_write_service`. A test replaces
# :data:`_APPLICATION_PUBLISH_SERVICE` (or patches :func:`get_application_publish_service`) with a
# service over in-memory fakes, so no AWS is touched. The service's three seams are satisfied by
# ONE DynamoDB-backed projection reader (``get_form_slug`` / ``is_mail_certified`` /
# ``get_mail_domain``) plus the public field-config read (the single filter authority, reused via
# the MembershipService's ``get_public_field_config``) — no readiness logic is duplicated.

#: The module-global publish service, built once at cold start (``None`` until first use).
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

        reader = MembersProjectionReader()
        _APPLICATION_PUBLISH_SERVICE = ApplicationPublishService(
            slug_reader=reader,
            readiness_provider=reader,
            field_config_reader=_get_membership_service(),
        )
    return _APPLICATION_PUBLISH_SERVICE


# ── Application-form live preview is IN-BROWSER (spec 12, redesign C / R3) ─────────────
#
# The former `preview_application` seam (`POST /members/application-preview`, spec 11 R7.2) — a
# one-shot membership service built over the request-body overlay to run `get_public_field_config`
# — has been RETIRED. Preview is now entirely in-browser (the builder reproduces the applicant-
# facing selection with a pure client filter and the shared renderer, spec 12 §C2 / D4, task 5.2),
# so the body-overlay provider + the one-shot preview-service builder are gone. The PUBLIC
# `get_public_field_config` read + the publish path remain the authoritative server filter.


# ── Shared dispatch helpers ────────────────────────────────────────────────────────────


def _caller_is_tenant_admin(ctx: "RequestContext") -> bool:
    """True when the verified caller holds ``members:admin`` for the active tenant (R9.3).

    The R9.3 scope decision — a plain user sees only their OWN sends, a Tenant_Admin sees ALL
    the tenant's — is an AUTHORIZATION fact, so it derives from the VERIFIED entitlement, never
    a header/body (verify-before-trust, Property 3). Uses the three-state
    :func:`~sam.shared.auth_utils.has_capability`: only an authoritative ``True`` grant counts
    as admin; a ``False`` (token-backed denial) or ``None`` (the token does not answer) both
    resolve to NOT-admin, so the caller is scoped to their own sends — fail-closed to the
    narrower view, never a silent widening to the whole tenant.
    """
    return has_capability(ctx.claims, ctx.tenant_id, CAP_MEMBERS_ADMIN) is True


def _mail_run_to_dict(run: Mapping[str, Any]) -> dict[str, Any]:
    """Shape a stored ``mailrun#`` tally into the JSON the status screen renders.

    Drops the DynamoDB plumbing keys (the partition/sort key + the ``ttl`` epoch) that are
    storage detail, not status the SPA needs, and passes the status fields through. The edge's
    JSON encoder already turns DynamoDB ``Decimal`` counts into ints, so the tally's numeric
    ``recipient_count`` / ``sent`` / ``failed`` serialize cleanly.
    """
    drop = {"tenant_id", "sk", "ttl"}
    return {k: v for k, v in run.items() if k not in drop}


def _mail_failure_to_dict(failure: Mapping[str, Any]) -> dict[str, Any]:
    """Shape a stored ``mailrecipient#`` FAILURE sub-record into the drill-down JSON.

    Drops the DynamoDB plumbing keys (partition/sort key + ``ttl``), surfacing the per-failure
    fields the screen shows — ``address`` / ``status`` / ``reason`` / ``message_id`` — as
    metadata only (never member PII beyond the mailed address).
    """
    drop = {"tenant_id", "sk", "ttl"}
    return {k: v for k, v in failure.items() if k not in drop}


def _new_run_id(tenant_id: str, set_id: str, requested_by: str | None) -> str:
    """Mint a ``run_id`` for one interactive deliver run (audit attribution + idempotency, R4).

    The service folds ``run_id`` into every job's stable idempotency id (design §4.2), so one
    logical run gets one id across the whole fan-out while two distinct runs never collide. For
    the interactive route each click is a fresh run, so the id combines the set, the verified
    caller (``requested_by`` — attribution, never a gate), and a UTC timestamp. The scheduler
    (R5, task 5.3) supplies its own run id the same way.
    """
    from datetime import datetime, timezone

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    who = requested_by or "anon"
    return f"deliver:{set_id}:{who}:{stamp}"


def _verified_email(ctx: "RequestContext") -> str | None:
    """The triggering user's VERIFIED email (the mail Reply-To, R4.3) — from the JWT claims only.

    The Reply-To is the logged-in user's address so replies reach the real sender (R4.3). It is
    read from the VERIFIED token claims (``email``) the edge already decoded — never a header or
    body value (verify-before-trust, Property 3). Returns ``None`` when the token carries no email
    claim; the send still proceeds (the From carries the tenant identity) with no Reply-To, rather
    than guessing one.
    """
    email = ctx.claims.get("email") if isinstance(ctx.claims, Mapping) else None
    if isinstance(email, str) and email.strip():
        return email.strip()
    return None


def _delivery_outcome_to_dict(outcome: Any) -> dict[str, Any]:
    """Shape the service's frozen ``DeliveryOutcome`` into the JSON receipt the 202 echoes.

    The edge's JSON encoder (``_http._json_default``) only knows how to serialize Decimals, so
    the dataclass is flattened here into a plain mapping — the enqueued-send receipt (how many
    jobs went on the queue, how many rows were skipped for want of an address, the stable job
    ids) the SPA can surface after a deliver.
    """
    return {
        "run_id": outcome.run_id,
        "mode": outcome.mode,
        "enqueued": outcome.enqueued,
        "skipped_no_address": outcome.skipped_no_address,
        "job_ids": list(outcome.job_ids),
    }


def _str_tuple(value: Any) -> tuple[str, ...]:
    """Coerce a JSON array value into a tuple of strings (empty when absent/not a list).

    The ad-hoc body's ``recipients`` is a JSON array of addresses. API Gateway hands the body
    through as parsed JSON, so a well-formed array is already a ``list``; a missing / non-list
    value normalises to an empty tuple so the SERVICE'S shape validation surfaces the "to_fixed
    requires recipients" 422 (:class:`AdHocMailInvalid`) rather than the edge guessing. Non-str
    entries are dropped (the service's ``to_fixed`` guard already treats blank/absent as "no
    recipient").
    """
    if not isinstance(value, (list, tuple)):
        return ()
    return tuple(v for v in value if isinstance(v, str))


def _row_tuple(value: Any) -> tuple[Mapping[str, Any], ...]:
    """Coerce the body's ``result_rows`` JSON array into a tuple of row mappings.

    The compose ships its CURRENT result rows (already computed client/pivot-side) on the body;
    each row is a JSON object. A missing / non-list value normalises to an empty tuple so the
    service's ``per_recipient`` guard surfaces the "no result rows to mail" 422; non-object
    entries are dropped (a row that is not a mapping carries no resolvable address or merge
    values anyway).
    """
    if not isinstance(value, (list, tuple)):
        return ()
    return tuple(r for r in value if isinstance(r, Mapping))


def _parse_ad_hoc_body(request: ParsedRequest) -> AdHocMailBody:
    """Parse the ad-hoc send request body into an :class:`AdHocMailBody` (SHAPE only, R2).

    The thin edge's whole job here is to lift the JSON compose body into the frozen
    :class:`~sam.members.domain.execute_and_deliver.AdHocMailBody` the service consumes — it
    does NOT validate it. The AUTHORITATIVE shape validation (unknown ``mode``, a ``to_fixed``
    with no recipients, a ``per_recipient`` with no rows) lives in
    :meth:`ExecuteAndDeliverService.send_ad_hoc` (raising :class:`AdHocMailInvalid` → 422 at the
    edge), so a malformed body is surfaced by the service, never guessed here (verify-before-
    trust: the handler never enriches the body; ``tenant_id`` + Reply-To are stamped by the
    dispatch from the VERIFIED context, never read off the body).

    A missing / non-object body normalises to an empty mapping, so an absent ``mode`` flows
    through as ``None`` and the service rejects it with the "unknown delivery mode" 422 — the
    honest "the body is malformed" answer rather than a silent no-op. ``set_id`` is a free-form
    audit LABEL (default ``"adhoc"``), NOT a saved-set key.
    """
    body = request.body if isinstance(request.body, Mapping) else {}

    attachment = body.get("attachment")
    label_options = body.get("label_options")
    recipient_field = body.get("recipient_field")
    template_id = body.get("template_id")
    set_id = body.get("set_id")

    return AdHocMailBody(
        mode=body.get("mode"),
        result_rows=_row_tuple(body.get("result_rows")),
        recipients=_str_tuple(body.get("recipients")),
        template_id=template_id
        if isinstance(template_id, str) and template_id
        else None,
        attachment=attachment if isinstance(attachment, str) and attachment else None,
        label_options=label_options if isinstance(label_options, Mapping) else None,
        recipient_field=(
            recipient_field
            if isinstance(recipient_field, str) and recipient_field
            else None
        ),
        set_id=set_id if isinstance(set_id, str) and set_id else "adhoc",
    )


class RouteNotImplemented(NotImplementedError):
    """Raised by the (stubbed) domain dispatch for a route whose behaviour is pending.

    The route exists in the map and resolved correctly; its domain implementation is a
    later Step-1/Step-3/Step-5 task. The edge maps this to ``501 Not Implemented`` so a
    caller can tell "route not built yet" apart from "no such route" (404).
    """

    def __init__(self, route_name: str):
        self.route_name = route_name
        super().__init__(f"route '{route_name}' is not implemented yet")


class StaleClientBundleError(RuntimeError):
    """A ``config#fields`` write arrived in the RETIRED whole-overlay shape (spec 03 Task 5.3a).

    During the deprecation window (design "Migration/rollout — Slice 3") the server still gets
    the occasional write from a CACHED OLD SPA bundle that has not reloaded since the frontend
    switched to the Change-Op contract. That bundle sends a WHOLE RECORD — ``fields`` /
    ``overrides`` / ``fixed_overrides`` / ``functional_groups`` / ``field_overlay`` as a whole
    object — instead of an ``ops`` Change-Op list. Without this guard such a body falls into the
    GENERIC empty-ops :class:`ConfigFieldsCrudError` (a 400 "must carry a non-empty 'ops' list"),
    which the user on a stale tab cannot act on.

    This exception marks that specific shape so the edge can map it to an INTELLIGIBLE,
    caller-safe "reload the app" response (a distinct machine code + a 409), DISTINCT from the
    ops-validation 400 — so the SPA can render a dedicated "a newer version is available, please
    reload" prompt rather than an obscure validation failure. It carries NO raw internals
    (steering 39): the message names only the stale-client condition and the remedy.

    A :class:`RuntimeError` (not a :class:`ConfigFieldsCrudError`/``ValueError``) so the handler
    catches it on its OWN branch and never collapses it into the generic validation 400.
    """


def _require_path_param(ctx: "RequestContext", name: str) -> str:
    """Return a required path parameter, or raise :class:`RouteNotImplemented`-free 400-ish.

    The router only matches a route when its ``{param}`` segments are present, so a resolved
    READ route always carries its ids; this guard is defensive (a mis-wired route would
    surface loudly rather than silently reading the wrong member).
    """
    value = ctx.path_params.get(name)
    if not value:
        raise KeyError(name)
    return value


def _query_flag(query: Mapping[str, Any], name: str) -> bool:
    """Read a boolean query-string flag, tolerant of the usual truthy spellings.

    API Gateway hands query params as strings (or ``None`` when absent). ``true`` / ``1`` /
    ``yes`` / ``on`` (any case) read as ``True``; anything else (incl. a missing param) reads
    as ``False`` — so the flag defaults off, which for the catalog list means "management
    view: return ALL entries" unless the caller explicitly asks ``?active_only=true``.
    """
    raw = query.get(name) if isinstance(query, Mapping) else None
    if raw is None:
        return False
    return str(raw).strip().lower() in {"true", "1", "yes", "on"}


# ── Rows-per-page selector + cursor paging (Req 25, Task 1.17) ─────────────────────────
#
# The Members table READ path accepts a per-user runtime page-size selector (NOT tenant config
# — `default_page_size` is retired, R25.9) and DynamoDB-native cursor paging. The FIXED options
# apply the value as the DynamoDB Query `Limit`; the `Max` option OMITS the `Limit` so DynamoDB
# returns one page up to its natural ~1 MB boundary (`Max` = one Query page, NOT all rows,
# R25.3). Prev/next walk the `LastEvaluatedKey` cursor the read path returns for EVERY option
# incl. `Max` (R25.4); there is no SQL-style offset / jump-to-page.

#: The fixed Rows_Per_Page_Selector options (R25.1) — each applied as the DynamoDB Query
#: `Limit`. `Max` (the fifth option) is expressed as the sentinel string and carries NO limit.
_FIXED_PAGE_SIZES = frozenset({50, 100, 250, 500})

#: The wire token for the `Max` option (one Query page up to ~1 MB, no `Limit`).
_PAGE_SIZE_MAX = "max"


def _parse_page_size(query: Mapping[str, Any]) -> tuple[bool, int | None]:
    """Parse the `?page_size=` Rows_Per_Page selector param (Req 25).

    Returns ``(paging_requested, limit)``:

    - no `page_size` param → ``(False, None)``: the LEGACY list path (the full scope-narrowed
      list, backward-compatible with callers that do not opt into cursor paging).
    - `page_size=max` (any case) → ``(True, None)``: the `Max` option — one DynamoDB Query page
      with NO `Limit`, bounded by the natural ~1 MB response boundary (R25.3).
    - `page_size=50|100|250|500` → ``(True, <int>)``: a fixed option applied as the Query
      `Limit` (R25.2).

    An unrecognised value (not `max` and not one of the fixed options) falls back to the
    platform-default fixed option (50) rather than erroring — a stray/garbled selector value
    must never 500 a plain list read; the frontend only ever sends the known tokens (R25.10).
    """
    raw = query.get("page_size") if isinstance(query, Mapping) else None
    if raw is None:
        return False, None
    token = str(raw).strip().lower()
    if token == _PAGE_SIZE_MAX:
        return True, None
    try:
        value = int(token)
    except (TypeError, ValueError):
        return True, 50
    if value in _FIXED_PAGE_SIZES:
        return True, value
    # Unknown numeric selector → platform fallback fixed option (never all-rows, never a raise).
    return True, 50


def _write_body(request: ParsedRequest) -> Mapping[str, Any]:
    """The parsed request body for a WRITE route, as a mapping (empty when absent/non-JSON).

    Write routes carry a JSON object body; a missing or non-object body is normalised to an
    empty mapping so the domain layer's authoritative validation surfaces the "required
    field" errors (a 422), rather than the handler guessing. The handler never enriches the
    body — the domain stamps the verified ``tenant_id`` itself (verify-before-trust).
    """
    body = request.body
    return body if isinstance(body, Mapping) else {}


# ── config#fields Change-Op body → service dispatch (spec 03 Task 2.7 — Q7a) ──────────
#
# The `PUT /members/config/fields` body is a Change-Op LIST, not a whole overlay. Each op is an
# identity-keyed intent the edge dispatches to the matching ConfigFieldsCrudService method — the
# service owns storage placement + the version-conditional write. The edge is THIN: it only lifts
# the JSON into method calls and never validates the op semantics (the service raises
# ConfigFieldsCrudError → 400 / StaleVersionError → 409, mapped at the handler). `tenant_id` is
# the VERIFIED tenant from the context — NEVER read off the body (steering 39).

#: The accepted op `op` tokens → the ConfigFieldsCrudService method name they dispatch to. The
#: ATTR ops (set_*) carry an `attrs` object; the WHOLE-entry ops (reset/delete) do not. Keeping
#: the map here (not in the service) is the edge's only knowledge of the op vocabulary; the
#: service enforces the disjoint attribute surfaces.
_FIELDS_OP_METHODS = frozenset(
    {
        "set_field",
        "set_field_application",
        "reset_field",
        "delete_field",
        "set_group",
        "delete_group",
    }
)

#: The ops whose identity is a FIELD key (vs a GROUP key) and whether they carry an attrs payload.
_FIELD_IDENTITY_OPS = frozenset(
    {"set_field", "set_field_application", "reset_field", "delete_field"}
)
_ATTR_OPS = frozenset({"set_field", "set_field_application", "set_group"})

#: The top-level keys that ONLY ever appear in the RETIRED whole-overlay / ``field_overlay``
#: body shape a cached OLD SPA bundle sends (spec 03 Task 5.3a). A write body that carries any of
#: these as a whole record — and no ``ops`` Change-Op list — is a stale-client write, mapped to
#: the intelligible "reload the app" rejection rather than the generic empty-ops 400. These are
#: the raw-shape keys steering 39 keeps OUT of the API surface, so their PRESENCE on a write body
#: is itself the stale-bundle signal (a current bundle never sends them).
_WHOLE_OVERLAY_BODY_KEYS = frozenset(
    {"fields", "overrides", "fixed_overrides", "functional_groups", "field_overlay"}
)


def _dispatch_config_fields_ops(
    service: Any, tenant_id: str, request: ParsedRequest
) -> dict:
    """Apply a Change-Op list body to config#fields, op-by-op, via the injected service (2.7).

    The body MUST be ``{"ops": [ {op, key|group, attrs?, client_op_id?}, ... ]}`` (a bare list is
    also accepted for tolerance). The edge validates ONLY the envelope shape — an empty/absent ops
    list, an op that is not an object, or an unknown ``op`` token is a deliberate caller-safe
    :class:`ConfigFieldsCrudError` (→ 400). It does NOT validate op semantics (attribute surfaces,
    placement, version): each op is handed to the matching service method, which owns that and
    raises ``ConfigFieldsCrudError`` (→ 400) / ``StaleVersionError`` (→ 409). ``tenant_id`` is the
    VERIFIED tenant — the body never carries a tenant (steering 39).

    Returns an envelope ``{"success": True, "results": [<per-op service result>, ...]}`` so the
    caller sees each op's authoritative new version (the service result verbatim).

    Stale-SPA-bundle guard (TASK 5.3a — design "Migration/rollout Slice 3"): a body that carries
    a RETIRED whole-overlay shape (``fields`` / ``overrides`` / ``fixed_overrides`` /
    ``functional_groups`` / ``field_overlay`` as a whole record, no ``ops`` list) is a cached OLD
    SPA bundle that has not reloaded since the Change-Op switch. It is rejected with a distinct
    :class:`StaleClientBundleError` (→ an intelligible 409 "reload the app" the SPA can prompt on),
    NOT the generic empty-ops 400 — so a user on a stale tab gets an actionable message.
    """
    body = request.body
    # Accept either {"ops": [...]} (the canonical shape) or a bare list (tolerance).
    if isinstance(body, Mapping):
        raw_ops = body.get("ops")
    elif isinstance(body, (list, tuple)):
        raw_ops = body
    else:
        raw_ops = None

    if not isinstance(raw_ops, (list, tuple)) or not raw_ops:
        # BEFORE the generic empty-ops rejection: a whole-overlay body (the retired shape a cached
        # old SPA bundle sends — a whole record keyed by `fields`/`overrides`/`fixed_overrides`/
        # `functional_groups`/`field_overlay`, never an `ops` list) is a STALE CLIENT, not a
        # malformed Change-Op envelope. Surface the intelligible "reload the app" rejection so the
        # SPA prompts a reload instead of showing an obscure validation 400 (Task 5.3a).
        if isinstance(body, Mapping) and _WHOLE_OVERLAY_BODY_KEYS.intersection(body):
            raise StaleClientBundleError(
                "This change was sent in a retired format by an out-of-date app version. "
                "Please reload the page to get the latest version, then try again."
            )
        from sam.members.domain.config_fields_crud_service import ConfigFieldsCrudError

        raise ConfigFieldsCrudError(
            "config#fields write body must carry a non-empty 'ops' Change-Op list "
            "(the whole-overlay body is no longer accepted on this route)"
        )

    results: list[Any] = []
    for index, op in enumerate(raw_ops):
        results.append(_apply_one_config_fields_op(service, tenant_id, op, index))
    return {"success": True, "results": results}


def _apply_one_config_fields_op(
    service: Any, tenant_id: str, op: Any, index: int
) -> Any:
    """Dispatch ONE Change-Op mapping to its ConfigFieldsCrudService method (2.7).

    Validates only the op ENVELOPE (a mapping, a known ``op`` token, a non-empty identity); the
    service owns the attribute-surface / placement / version semantics. The dotted or bare field
    key is passed through verbatim (the service resolves placement). ``client_op_id`` is forwarded
    when present (lost-response idempotency). A malformed envelope raises
    :class:`ConfigFieldsCrudError` (→ caller-safe 400), naming the op INDEX, never echoing internals.
    """
    from sam.members.domain.config_fields_crud_service import ConfigFieldsCrudError

    if not isinstance(op, Mapping):
        raise ConfigFieldsCrudError(f"op[{index}] must be an object")
    op_kind = op.get("op")
    if op_kind not in _FIELDS_OP_METHODS:
        raise ConfigFieldsCrudError(
            f"op[{index}] has unknown op {op_kind!r}; must be one of "
            f"{sorted(_FIELDS_OP_METHODS)}"
        )

    client_op_id = op.get("client_op_id")
    client_op_id = (
        client_op_id if isinstance(client_op_id, str) and client_op_id else None
    )

    # Identity: a FIELD op keys on `key` (accept `field_key` too); a GROUP op keys on `group`
    # (accept `group_key` too). The service re-validates a blank identity, but surface a clear
    # envelope error here so the caller sees WHICH op is malformed.
    if op_kind in _FIELD_IDENTITY_OPS:
        identity = op.get("key") or op.get("field_key")
        identity_label = "key"
    else:
        identity = op.get("group") or op.get("group_key")
        identity_label = "group"
    if not isinstance(identity, str) or not identity:
        raise ConfigFieldsCrudError(
            f"op[{index}] ({op_kind}) requires a non-empty {identity_label!r} identity"
        )

    method = getattr(service, op_kind)
    if op_kind in _ATTR_OPS:
        attrs = op.get("attrs")
        if not isinstance(attrs, Mapping):
            raise ConfigFieldsCrudError(
                f"op[{index}] ({op_kind}) requires an 'attrs' object of attribute changes"
            )
        return method(tenant_id, identity, attrs, client_op_id=client_op_id)
    # reset_field / delete_field / delete_group — identity only, no attrs payload.
    return method(tenant_id, identity, client_op_id=client_op_id)
