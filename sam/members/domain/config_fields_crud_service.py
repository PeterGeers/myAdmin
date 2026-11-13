"""
Spec 03 Task 2.2 — ``ConfigFieldsCrudService``: the DISJOINT, identity-keyed Change-Op surface
for ``config#fields`` mutations (design C1; design-review Must-fix #3).

This is the single domain authority for ``config#fields`` CRUD. It accepts a mutation BY DOMAIN
IDENTITY (a field/group key + the attribute change), decides storage placement server-side, and
emits a Change-Op set that it hands to the repository's
:meth:`~sam.members.repository.projection_config_write_repository.MembersConfigWriteRepository.apply_ops`
(the task-2.4 contract). It NEVER lets a caller supply a storage path, a whole overlay, or a whole
``functional_groups`` object — each op addresses ONE path, so a partial payload is structurally
unable to truncate the catalog or any slice (steering 39; R1/R4).

Why DISJOINT ops (design-review Must-fix #3)
--------------------------------------------
Field DEFINITION and application-form configuration are two NON-OVERLAPPING surfaces:

- :meth:`set_field` owns field DEFINITION attributes ONLY
  (``{type,label,order,required,visible,choices,options,scope,functional_group}``). It is
  STRUCTURALLY INCAPABLE of writing an ``application_*`` attribute — passing one is rejected.
- :meth:`set_field_application` owns the FOUR application attributes ONLY
  (``{application_visible, application_required, application_choices, format}``). It is
  STRUCTURALLY INCAPABLE of writing a definition attribute (R7.2 under R7=A, design D3(A)).

Because the two op surfaces do not overlap in name, the application-form builder's single op
(``set_field_application``) can never reach a field/group definition — that disjointness IS the
"narrow surface" stability guarantee D3(A) rests on (it is not enforced by a separate table).

Layering (steering 35/39 — dependency inversion)
-------------------------------------------------
This is a **domain** service: NO ``boto3``, NO DynamoDB / table resolution. It depends only on
the pure fixed-field registry (for placement) and on a repository exposing ``apply_ops`` (in
production the concrete
:class:`~sam.members.repository.projection_config_write_repository.MembersConfigWriteRepository`,
in tests an in-memory fake). The repository owns the ``update_item`` mechanics and the version
conditional; this service owns INTENT → OPS translation and must not duplicate repository logic.

The ops contract this service produces (task 2.4)
-------------------------------------------------
Each op is ``{"action": SET|REMOVE, "path": [segment, ...], "value": <any for SET>}`` where
``path`` is a list of RAW key segments outer→inner (the repository binds every segment through
``ExpressionAttributeNames``, so a dotted ``"<group>.<key>"`` override key is a LITERAL segment,
never a nested path). ``SET``/``REMOVE``/``LEGACY_NO_VERSION`` are imported from the repository
module so the two planes cannot drift on the verb tokens. ``base_version`` sentinels:
``None`` (no row yet) / :data:`LEGACY_NO_VERSION` (existing legacy row) / an explicit version
string (optimistic lock). ``apply_ops`` raises :class:`ChangeOpError` / :class:`StaleVersionError`.

Placement / verb mechanics (TASK 2.3 — design-review Q2/Q8 + Must-fix #1)
------------------------------------------------------------------------
Each public op reads the resolved ``config#fields`` record ONCE, STRONGLY-CONSISTENT, ONLY to
validate + decide placement/version — NOT a read-merge-write. The read flag flows all the way to
the repository ``Query`` (``get_raw_fields_overlay(..., consistent_read=True)``) so a stale
eventually-consistent read can never produce a spurious 409 (Should-fix). The mechanics:

- :meth:`_read_snapshot` — the single strongly-consistent validate-and-place read per op.
- :meth:`_resolve_placement` / :meth:`_group_placement` — map a domain identity to its storage
  path segments (``fields.<key>`` variable / ``overrides.<dotted>`` base-calc /
  ``functional_groups.<gkey>`` group) AND choose the CREATE-vs-UPDATE verb by ENTRY EXISTENCE in
  the snapshot (``create`` flag).
- :meth:`_attr_ops` — emits the chosen verb: a CREATE seeds the WHOLE entry with one
  ``SET #o.#k = :whole`` (never ``if_not_exists`` parent-seed + child-set in one expression —
  DynamoDB rejects it, Must-fix #1; the parent MAP exists by the C6 row skeleton); an UPDATE
  emits per-aspect ``SET #o.#k.#attr = :v`` / ``REMOVE`` ops.
- :meth:`_base_version_from_snapshot` — resolves the conditional-write base version from the SAME
  snapshot: a version present → optimistic lock; a legacy versionless row → ``LEGACY_NO_VERSION``;
  the empty/never-authored shape → ``None`` (first write onto the skeleton).

The dotted override key is handed to the repository as a LITERAL segment; the repository binds
every segment through ``ExpressionAttributeNames`` (so a ``.`` is a key name, never a nested path,
design-review Q2) — this service only guarantees the segments are correct.

Delete-safety guards (TASK 2.6 — design C1; R4.3; design-review Should-fix)
--------------------------------------------------------------------------
A delete is ALWAYS an explicit op (never inferred from omission, R2.5) AND must never leave the
record — or member data — inconsistent. Two guards fire BEFORE the ``REMOVE`` op is emitted:

- :meth:`_guard_delete_group` (R4.3) — refuse deleting a functional group that STILL HOLDS
  fields. "Holds a field" is read from the SAME consistent snapshot: any variable field
  (``fields.<key>``) or authored override (``overrides.<dotted>``) whose resolved
  ``functional_group`` is this group. Deleting a non-empty group would orphan those fields into
  a group that no longer exists, so it is refused with a caller-safe reason — the admin must
  first move or delete the fields.
- :meth:`_guard_delete_field` (design C1; review Should-fix) — refuse deleting a VARIABLE field
  that is IN USE: either member records store a value under the key, OR a group/application
  reference points at it. "In use" is reported by an optional, injected ``usage_probe``
  (:class:`FieldUsageProbe`-shaped) — the domain stays storage-agnostic (steering 35/39); the
  probe owns the member-data / reference lookup. When a field is in use the delete is refused
  with a caller-safe reason that offers ``visible=false`` (hide) as the safe alternative, so a
  delete can never orphan member data. A base field "delete" is :meth:`reset_field` (revert),
  never removing a base definition (Q9) — :meth:`delete_field` already refuses a base field.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from sam.members.repository.projection_config_write_repository import (
    StaleVersionError,
)

from ._config_fields_delete_guards import ConfigFieldsDeleteGuardsMixin
from ._config_fields_field_ops import ConfigFieldsFieldOpsMixin
from ._config_fields_integrity import ConfigFieldsIntegrityMixin
from ._config_fields_read import ConfigFieldsReadMixin
from ._config_fields_shared import (
    _CONFIG_ID_FIELDS,
    FIELD_APPLICATION_ATTRS,
    FIELD_DEFINITION_ATTRS,
    GROUP_ATTRS,
    SLUG_OWNER_KIND,
    SLUG_OWNER_PLANE,
    SLUG_RESOURCE_REF,
    ConfigFieldsCrudError,
    SlugAuthorConflict,
    SlugAuthorRejected,
)
from ._config_fields_slug_ops import ConfigFieldsSlugOpsMixin
from ._config_fields_wire import ConfigFieldsWireOpsMixin

__all__ = [
    "FIELD_APPLICATION_ATTRS",
    "FIELD_DEFINITION_ATTRS",
    "GROUP_ATTRS",
    "SLUG_OWNER_KIND",
    "SLUG_OWNER_PLANE",
    "SLUG_RESOURCE_REF",
    "ConfigFieldsCrudError",
    "ConfigFieldsCrudService",
    "SlugAuthorConflict",
    "SlugAuthorRejected",
]


class ConfigFieldsCrudService(
    ConfigFieldsFieldOpsMixin,
    ConfigFieldsSlugOpsMixin,
    ConfigFieldsIntegrityMixin,
    ConfigFieldsWireOpsMixin,
    ConfigFieldsReadMixin,
    ConfigFieldsDeleteGuardsMixin,
):
    """Identity-keyed Change-Op authority for ``config#fields`` (design C1).

    Each public method accepts a DOMAIN IDENTITY (a field/group key) plus the change, never a
    storage path or a whole object. It normalises the change into a set of SET/REMOVE path ops and
    delegates the atomic, version-conditional write to the repository's ``apply_ops`` (task 2.4).

    Args:
        repository: An object exposing
            ``apply_ops(tenant_id, config_id, ops, base_version, client_op_id=None)`` — in
            production the concrete
            :class:`~sam.members.repository.projection_config_write_repository.MembersConfigWriteRepository`,
            in tests an in-memory fake. Injectable so the domain stays storage-agnostic (no boto3).
        reader: Optional resolved-view reader used by task 2.3's placement/version mechanics
            (``ConsistentRead`` validate-and-place read). Left injectable now; the 2.2 surface does
            not require it (the stubs degrade to first-write placement), so unit tests can omit it.
        usage_probe: Optional member-data / reference usage probe used by the task-2.6
            :meth:`delete_field` safety guard. Any object exposing
            ``field_in_use(tenant_id, field_key) -> bool`` (or the richer
            ``field_usage(tenant_id, field_key) -> Mapping`` described on :meth:`_field_usage`).
            The domain stays storage-agnostic (steering 35/39) — the probe owns the member-data /
            reference lookup. When no probe is wired the field-usage guard cannot observe member
            data and does not block on it (the snapshot-level reference check still runs); a probe
            is injected in production so a real delete can never orphan member data.
    """

    def __init__(
        self,
        repository,
        reader=None,
        usage_probe=None,
        *,
        slug_marker_store=None,
        prefix_reader=None,
        slug_reader=None,
    ):
        self._repository = repository
        self._reader = reader
        self._usage_probe = usage_probe
        # Slug-author seams (bugfix-slug-lifecycle task 3.1) — the shared `_slugs/{slug}` claim
        # store + the tenant's own public-prefix reader, both constructor-injected so the domain
        # stays boto3-free (steering 35/39). Tests inject in-memory fakes; production wires the
        # real S3SlugMarkerStore + MembersProjectionReader. Absent → `set_form_slug` cannot claim
        # and refuses fail-loud (it is never called on a service built without them).
        self._slug_marker_store = slug_marker_store
        self._prefix_reader = prefix_reader
        # Change/rename seam (bugfix-slug-lifecycle task 3.2) — the FORWARD slug reader
        # (`get_form_slug(tenant_id) -> str | None`) used ONLY to detect a slug CHANGE (the tenant
        # already owns a DIFFERENT stored slug) so the op can hand the old→new transition to
        # `S3SlugMarkerStore.rename` (claim-new-before-release-old, R4.6) instead of a bare claim
        # that would ORPHAN the old `_slugs/{old}` marker. Injected separately but DEFAULTS to the
        # `prefix_reader` when that object also exposes `get_form_slug` (production's
        # `MembersProjectionReader` exposes both), so production needs no extra wiring. When no
        # forward reader is available (a 3.1-era fake with only `get_public_prefix`), change
        # detection degrades to "no prior slug" and the op keeps the task-3.1 bare-claim behavior —
        # the rename path is strictly additive.
        self._slug_reader = slug_reader
        if (
            self._slug_reader is None
            and prefix_reader is not None
            and hasattr(prefix_reader, "get_form_slug")
        ):
            self._slug_reader = prefix_reader

    def _apply(
        self,
        tenant_id: str,
        ops: list[dict],
        *,
        snapshot: Mapping[str, Any] | None,
        client_op_id: str | None,
    ) -> dict:
        """The single choke point: resolve the base version + delegate to ``apply_ops`` (task 2.4).

        Takes the SAME consistent snapshot the placement read produced so the base-version
        decision and the placement decision see one coherent view of the row (one strongly-
        consistent read per public op, not two). The op-emission shape handed to the repository is
        stable. Returns the repository result verbatim (``{"version": ..., "idempotent_replay":
        ...}``).
        """
        base_version = self._base_version_from_snapshot(snapshot)
        return self._repository.apply_ops(
            tenant_id=tenant_id,
            config_id=_CONFIG_ID_FIELDS,
            ops=ops,
            base_version=base_version,
            client_op_id=client_op_id,
        )

    def _run(
        self,
        tenant_id: str,
        derive,
        *,
        client_op_id: str | None,
    ) -> dict:
        """Read the consistent snapshot, derive the ops from it, and apply — with a GUARDED
        ONE-SHOT auto-retry on a version conflict (task 4.1; design C2/D5, review Should-fix).

        ``derive`` is a callable ``(snapshot) -> ops`` that RE-RUNS the op derivation (placement +
        verb choice + any safety guard) against WHATEVER snapshot it is handed. This is what makes
        the retry correct rather than a blind replay: under D3(A) the configurator and the
        form-builder share one ``config#fields`` row, so a row-level ``version`` conflict can be
        raised by an UNRELATED concurrent edit (e.g. another admin set a different field). On a
        :class:`StaleVersionError` we re-read the row STRONGLY-CONSISTENT, re-derive the ops against
        that fresh view (so a CREATE that the concurrent writer turned into an UPDATE — or a guard
        whose basis changed — is re-evaluated, never a stale replay), and retry the write ONCE.

        The guardrail (why retrying here is safe): every op this service emits is keyed by a single
        DOMAIN IDENTITY (one ``fields.<key>`` / ``overrides.<dotted>`` / ``functional_groups.<gkey>``
        path) and is IDEMPOTENT by that identity (SET the same attrs / REMOVE the same entry) — and
        :meth:`~...apply_ops` rejects overlapping paths up front — so re-applying the SAME intent
        onto a newer base is well-defined. We retry EXACTLY ONCE: if the second attempt also
        conflicts, we surface the :class:`StaleVersionError` (the edge maps it to a caller-safe 409
        "reload and retry"). We never loop, and we never paper over a genuine concurrent edit to the
        SAME identity — the re-derive + single-shot bound is the guard the review asked for. A
        malformed/out-of-surface request raises :class:`ConfigFieldsCrudError` from ``derive`` on
        the first pass and is never retried.
        """
        snapshot = self._read_snapshot(tenant_id)
        ops = derive(snapshot)
        try:
            return self._apply(
                tenant_id, ops, snapshot=snapshot, client_op_id=client_op_id
            )
        except StaleVersionError:
            # ONE guarded retry: re-read, re-derive against the fresh view, re-apply. A second
            # conflict is a genuine concurrent edit → surface the 409 (never loop).
            fresh_snapshot = self._read_snapshot(tenant_id)
            fresh_ops = derive(fresh_snapshot)
            return self._apply(
                tenant_id,
                fresh_ops,
                snapshot=fresh_snapshot,
                client_op_id=client_op_id,
            )
