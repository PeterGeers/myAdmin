"""
Member Application Form — the **role-recipients reader** (design seam (d), R8.2–R8.5).

A read-only, thin consumer of the shared governance projection that resolves WHO a new
application's staff notification goes to. It mirrors the projection-read discipline of
:class:`sam.members.repository.projection_config_reader.MembersProjectionReader` and
:class:`sam.pretokengen.projection_governance_reader.ProjectionGovernanceReader` exactly —
one DynamoDB ``Query`` per tenant partition, a per-invocation cache so a partition is read
at most once, fail-fast table resolution via :mod:`services.projection_schema`, and
*empty-is-valid* everywhere (a missing/empty partition is never an error) — but it answers
a different question: the **all-scope ``Members_CRUD`` recipient set** (plus an optional
scope-matched copy, plus a ``TenantAdmin`` fallback).

Why this exists (design seam (d) / D9 / D9a)
--------------------------------------------
A new applicant is a **tenant-wide event**, so the primary recipients are the tenant's
``Members_CRUD`` users who administer the WHOLE tenant — those holding the ``Members_CRUD``
role (``role#<email>#Members_CRUD``) AND an **all-scope grant** (``scopegrant#<email>#<dim>``
== ``["*"]``) on the tenant's governing scope dimension(s). A scope-LIMITED ``Members_CRUD``
user (who administers only their own scope value, e.g. one region) is NOT in this base set.

Three refinements layer on top, all **scope-generic** (no hardcoded ``region`` — the
governing dimension(s) come from the tenant's projected ``config#scope`` row, so this works
for ``region`` / ``chapter`` / ``department`` / … alike):

- **D9a — optional scope-matched copy.** WHEN the caller supplies the applicant's selected
  scope value (the worker reads it from the record, gated by the tenant's scope-copy toggle
  — task 8.2's ``application_scope_copy`` on ``config#mail``), this ALSO returns the
  ``Members_CRUD`` users whose grant for the governing dimension *covers that value* — the
  scope-local reviewer. This ADDS to the all-scope set, never replaces it (R8.3a).
- **No scope dimension configured (R8.3).** A tenant whose ``config#scope`` enables no
  dimension has all its ``Members_CRUD`` treated as all-scope — every ``Members_CRUD`` user
  is a recipient (there is no partition to be limited to).
- **``TenantAdmin`` fallback (R8.4).** WHEN the all-scope ``Members_CRUD`` set is EMPTY, fall
  back to the member module's tenant administrator — the ``TenantAdmin``-role holders
  (``role#<email>#TenantAdmin``) of the same partition. (OQ7 confirmed ``TenantAdmin`` as the
  projected segment; it is the ``members:admin`` capability holder, also an admin-role default
  in :data:`sam.members.domain.scope_access.ADMIN_ROLE_DEFAULTS`.)

Empty → ``NO_NOTIFY`` signal (R8.5)
-----------------------------------
WHEN neither any all-scope ``Members_CRUD`` NOR any ``TenantAdmin`` exists, this returns a
:class:`RecipientResolution` whose ``is_empty`` is ``True`` and whose ``fallback_used`` names
why. The caller (task 6.4) maps that to the stable ``NO_NOTIFY`` keyword note on
``overlay.additional_info`` + a platform-operator alert — the application record is still
created; the notification is simply undeliverable, surfaced on the inbox, never silently
dropped.

Layering
--------
SAM-plane **infrastructure adapter**: depends on ``boto3`` (lazily) + the projection schema +
the storage-agnostic scope model (:mod:`sam.members.domain.scope_dimensions`). The domain
never imports it (dependency inversion — the arrow points inward). It **reads only** — it
never writes MySQL or the projection.

Tenancy (R8.1 / Property 1, steering 35)
----------------------------------------
Recipients are resolved ENTIRELY within the SAM plane from the tenant's OWN partition
(``tenant_id`` is the partition key, so a Query cannot address another tenant). No Cognito
query, no Flask call, no client-supplied value ever contributes a recipient (R8.9).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from services import projection_schema as schema

from sam.members.domain.scope_dimensions import (
    WILDCARD,
    ScopeConfig,
    enabled_dimensions,
)

__all__ = [
    "RoleRecipientsReader",
    "RecipientResolution",
    "MEMBERS_CRUD_ROLE",
    "TENANT_ADMIN_ROLE",
]

#: The projected role segment whose per-tenant holders review applications (R8.2). Matched
#: against the ``role#<email>#<role>`` sort key's role id-part.
MEMBERS_CRUD_ROLE = "Members_CRUD"

#: The member module's tenant-administrator role segment — the R8.4 fallback recipient set
#: (OQ7 confirmed ``TenantAdmin``; it is the ``members:admin`` capability holder).
TENANT_ADMIN_ROLE = "TenantAdmin"


@dataclass(frozen=True)
class RecipientResolution:
    """The resolved staff-notification recipients for a new application (R8.2–R8.5).

    Carries the resolved address lists plus enough provenance for the caller (task 6.4) to
    act: the Reply-To (R9a) mirrors the SAME set, so the worker needs to know which set was
    used and whether the result is empty (→ ``NO_NOTIFY``).

    Attributes:
        all_scope: The de-duplicated, order-preserved all-scope ``Members_CRUD`` recipients
            (R8.3). This is the primary/base set — also the Reply-To set (R9a.2) — and is
            EMPTY when no all-scope ``Members_CRUD`` user exists.
        scope_matched: The optional D9a scope-matched copy (R8.3a) — ``Members_CRUD`` users
            whose grant covers the applicant's selected scope value. ADDS to ``all_scope``;
            empty when the caller passed no ``applicant_scope_value`` (toggle off / no value
            selected) or no scope-local reviewer matched. A recipient already in ``all_scope``
            is NOT duplicated here.
        tenant_admin: The ``TenantAdmin`` fallback recipients (R8.4), populated ONLY when the
            all-scope ``Members_CRUD`` set was empty; otherwise empty.
        fallback_used: ``True`` when ``tenant_admin`` is the operative recipient set (the
            all-scope base was empty but a ``TenantAdmin`` existed).

    Notes:
        ``recipients`` is the operative TO set the worker sends to; ``reply_to`` is the R9a
        Reply-To set (mirrors the recipients, never a client value); ``is_empty`` is the R8.5
        ``NO_NOTIFY`` signal.
    """

    all_scope: tuple[str, ...] = ()
    scope_matched: tuple[str, ...] = ()
    tenant_admin: tuple[str, ...] = ()
    fallback_used: bool = False

    @property
    def recipients(self) -> tuple[str, ...]:
        """The operative TO recipient set (R8.3/R8.3a/R8.4), de-duplicated, order-preserved.

        The all-scope base + the optional scope-matched copy (D9a); or, WHEN the all-scope
        base was empty, the ``TenantAdmin`` fallback. Empty only when the whole resolution is
        empty (→ ``NO_NOTIFY``, R8.5).
        """
        if self.all_scope:
            return _dedupe((*self.all_scope, *self.scope_matched))
        return self.tenant_admin

    @property
    def reply_to(self) -> tuple[str, ...]:
        """The Reply-To set (R9a) — the all-scope ``Members_CRUD`` set, else ``TenantAdmin``.

        Mirrors the authoritative recipient list (R9a.2/R9a.5): the all-scope base set, or the
        ``TenantAdmin`` fallback when the base was empty (R9a.3). The D9a scope-matched copy is
        deliberately NOT in the Reply-To — a reply should reach the tenant-wide admins, not a
        scope-local reviewer (R9a.2 names the all-scope set specifically). Empty → no Reply-To
        is set (R9a.4), the R8.5 handling applies.
        """
        if self.all_scope:
            return self.all_scope
        return self.tenant_admin

    @property
    def is_empty(self) -> bool:
        """``True`` when there are NO recipients at all — the R8.5 ``NO_NOTIFY`` signal."""
        return not self.recipients


def _dedupe(emails: Sequence[str]) -> tuple[str, ...]:
    """De-duplicate ``emails`` preserving first-seen order (stable recipient order)."""
    seen: set[str] = set()
    out: list[str] = []
    for e in emails:
        if e and e not in seen:
            seen.add(e)
            out.append(e)
    return tuple(out)


class RoleRecipientsReader:
    """Resolve a new application's staff recipients from the governance projection (seam (d)).

    One ``Query`` per tenant partition (cached per invocation), *empty-is-valid*, fail-fast
    table resolution — the same read discipline as the sibling projection readers. The scope
    config (which dimension(s) govern "all-scope") is read via an injected provider so the
    reader stays **scope-generic** and testable: in production the SAM edge passes a
    :class:`~sam.members.repository.projection_config_reader.MembersProjectionReader` (which
    satisfies ``get_scope_config``) reading the tenant's ``config#scope`` row; tests pass a
    ``StaticScopeConfigProvider``.

    Args:
        scope_config_provider: A ``ScopeConfigProvider`` (anything with
            ``get_scope_config(tenant_id) -> ScopeConfig``). Supplies the tenant's governing
            scope dimension(s) so "all-scope" is defined per the tenant's config, not a
            hardcoded ``region`` (D9 scope-generic). A tenant with no configured dimensions
            resolves to a tenant-wide config → all ``Members_CRUD`` are all-scope (R8.3).
        table: A boto3 DynamoDB Table (or a fake exposing ``query``). Defaults to the
            fail-fast-resolved projection table
            (:func:`services.projection_schema.get_projection_table_resource`). Injectable so
            tests use an in-memory fake / local dynamodb-local.
    """

    def __init__(self, scope_config_provider, table=None):
        self._scope_config_provider = scope_config_provider
        self._table = table
        # Per-invocation cache: tenant_id -> that partition's items, so the partition is
        # Queried at most once (shared across the role + grant scans below).
        self._partition_cache: dict[str, list[dict]] = {}

    @property
    def table(self):
        """The projection table, resolved lazily + fail-fast on first use (R4.1)."""
        if self._table is None:
            self._table = schema.get_projection_table_resource()
        return self._table

    # ── Public API ──────────────────────────────────────────────────────────────────

    def resolve_recipients(
        self,
        tenant_id: str,
        applicant_scope_value: str | None = None,
    ) -> RecipientResolution:
        """Resolve the staff recipients for a new application in ``tenant_id`` (R8.2–R8.5).

        Reads the tenant partition once and builds, scope-generically:

        1. the ``Members_CRUD`` emails (``role#<email>#Members_CRUD`` rows, R8.2);
        2. each such user's scope grants for the governing dimension(s) from their
           ``scopegrant#<email>#<dimension>`` rows;
        3. the **all-scope** subset (R8.3): users whose grant is ``["*"]`` for EVERY governing
           dimension. A tenant with no enabled dimension treats ALL ``Members_CRUD`` as
           all-scope (there is no dimension to be limited on);
        4. the optional **scope-matched copy** (R8.3a/D9a): WHEN ``applicant_scope_value`` is
           given, the ``Members_CRUD`` users whose grant for a governing dimension COVERS that
           value (an explicit value match, or an all-scope grant), minus those already in the
           all-scope set;
        5. the **``TenantAdmin`` fallback** (R8.4) — resolved ONLY when the all-scope base is
           empty — from the ``role#<email>#TenantAdmin`` rows of the same partition.

        An empty result (no all-scope ``Members_CRUD`` and no ``TenantAdmin``) is returned as
        an empty :class:`RecipientResolution` (``is_empty``) — the caller maps it to the R8.5
        ``NO_NOTIFY`` note + operator alert. Never raises on missing/empty data.

        Args:
            tenant_id: The tenant (partition key) whose recipients to resolve. The tenancy
                boundary — a Query cannot reach another tenant's partition (R8.1/Property 1).
            applicant_scope_value: The scope value the applicant selected (e.g. a region),
                for the D9a scope-matched copy. ``None`` / empty → no scope copy (the toggle is
                off or no value was selected — the worker decides whether to pass it).

        Returns:
            A :class:`RecipientResolution` with the all-scope set, the optional scope-matched
            copy, the ``TenantAdmin`` fallback (when used), and the ``NO_NOTIFY`` signal.
        """
        if not tenant_id:
            return RecipientResolution()

        members_crud = self._members_crud_emails(tenant_id)
        governing = self._governing_dimensions(tenant_id)

        all_scope = self._filter_all_scope(tenant_id, members_crud, governing)

        scope_matched: tuple[str, ...] = ()
        if applicant_scope_value:
            scope_matched = self._filter_scope_matched(
                tenant_id,
                members_crud,
                governing,
                applicant_scope_value,
                exclude=set(all_scope),
            )

        if all_scope:
            return RecipientResolution(
                all_scope=all_scope,
                scope_matched=scope_matched,
            )

        # No all-scope Members_CRUD → TenantAdmin fallback (R8.4). The D9a scope copy is a
        # refinement of the base set, so it does not apply when there IS no base set.
        tenant_admin = self._role_emails(tenant_id, TENANT_ADMIN_ROLE)
        return RecipientResolution(
            tenant_admin=tenant_admin,
            fallback_used=bool(tenant_admin),
        )

    # ── Row scans (mirror the projection readers' filter patterns) ────────────────────

    def _members_crud_emails(self, tenant_id: str) -> tuple[str, ...]:
        """The tenant's ``Members_CRUD`` emails from ``role#<email>#Members_CRUD`` rows (R8.2)."""
        return self._role_emails(tenant_id, MEMBERS_CRUD_ROLE)

    def _role_emails(self, tenant_id: str, role: str) -> tuple[str, ...]:
        """Collect the email id-segments of ``role#<email>#<role>`` rows for ``role``.

        Mirrors ``ProjectionGovernanceReader.get_user_roles_by_tenant``'s role filter — keep
        ``RECORD_TYPE_ROLE`` items whose role id-part (or explicit ``role`` attr) equals
        ``role`` — but collects the EMAIL segment instead of the role. De-duplicated,
        order-preserved. A missing/empty partition yields ``()`` (empty is valid).
        """
        emails: list[str] = []
        for item in self._query_partition(tenant_id):
            record_type, id_parts = self._classify(item)
            if record_type != schema.RECORD_TYPE_ROLE or len(id_parts) < 2:
                continue
            email, role_segment = id_parts[0], (item.get("role") or id_parts[1])
            if role_segment == role and email:
                emails.append(email)
        return _dedupe(emails)

    def _scope_grants_for(self, tenant_id: str, email: str) -> dict[str, list[str]]:
        """Return ``{dimension -> values}`` for ``email`` from its ``scopegrant#`` rows.

        Mirrors ``MembersProjectionReader.get_scope_grants``: keep
        ``scopegrant#<email>#<dimension>`` rows whose email segment equals ``email``; each
        contributes ``{dimension: values}`` where ``values`` is the granted subset or
        ``["*"]`` for all-access. A dimension with no grant for this user is simply ABSENT.
        """
        grants: dict[str, list[str]] = {}
        if not email:
            return grants
        for item in self._query_partition(tenant_id):
            record_type, id_parts = self._classify(item)
            if record_type != schema.RECORD_TYPE_SCOPEGRANT or len(id_parts) < 2:
                continue
            if id_parts[0] != email:
                continue
            dimension = item.get("dimension") or id_parts[1]
            grants[dimension] = list(item.get("values") or [])
        return grants

    # ── Scope filters (scope-generic — governing dimension(s) from config#scope) ──────

    def _governing_dimensions(self, tenant_id: str) -> tuple[str, ...]:
        """The keys of the tenant's ENABLED scope dimensions (scope-generic, D9/R8.3).

        Read from the injected ``ScopeConfigProvider`` (the tenant's ``config#scope`` row in
        production). A tenant with NO enabled dimension yields ``()`` — the "tenant-wide"
        collapse: every ``Members_CRUD`` is treated as all-scope (R8.3). Never a hardcoded
        ``region``. Degrades to ``()`` on any provider hiccup (empty-is-valid).
        """
        try:
            config = self._scope_config_provider.get_scope_config(tenant_id)
        except Exception:
            return ()
        if not isinstance(config, ScopeConfig):
            return ()
        return tuple(d.key for d in enabled_dimensions(config.dimensions))

    def _filter_all_scope(
        self,
        tenant_id: str,
        members_crud: Sequence[str],
        governing: Sequence[str],
    ) -> tuple[str, ...]:
        """Keep the ``Members_CRUD`` users who are all-scope on EVERY governing dimension (R8.3).

        A tenant with no governing dimension (``governing`` empty) treats ALL ``Members_CRUD``
        as all-scope — there is no dimension on which a grant could be limited (R8.3). With one
        or more governing dimensions, a user is all-scope iff, for each, their grant exists and
        equals ``["*"]`` (the :data:`~sam.members.domain.scope_dimensions.WILDCARD` sentinel).
        A scope-LIMITED user (a concrete value, or no grant on a governing dimension) is
        excluded from the base rule.
        """
        if not governing:
            return _dedupe(members_crud)
        kept: list[str] = []
        for email in members_crud:
            grants = self._scope_grants_for(tenant_id, email)
            if all(self._is_all_scope(grants.get(dim)) for dim in governing):
                kept.append(email)
        return _dedupe(kept)

    def _filter_scope_matched(
        self,
        tenant_id: str,
        members_crud: Sequence[str],
        governing: Sequence[str],
        applicant_scope_value: str,
        exclude: set[str],
    ) -> tuple[str, ...]:
        """Keep the ``Members_CRUD`` users whose grant COVERS ``applicant_scope_value`` (D9a/R8.3a).

        The optional scope-matched copy: on any governing dimension, a user whose grant either
        is all-scope (``["*"]``) or explicitly contains the applicant's selected value COVERS
        that value and gets a copy. Users already in the all-scope set (``exclude``) are NOT
        duplicated — the copy ADDS to, never replaces, the base (R8.3a). With no governing
        dimension there is no scope to match on → ``()`` (the base R8.3 "all are all-scope"
        already notified everyone).
        """
        if not governing:
            return ()
        kept: list[str] = []
        for email in members_crud:
            if email in exclude:
                continue
            grants = self._scope_grants_for(tenant_id, email)
            if any(
                self._covers_value(grants.get(dim), applicant_scope_value)
                for dim in governing
            ):
                kept.append(email)
        return _dedupe(kept)

    @staticmethod
    def _is_all_scope(values) -> bool:
        """``True`` iff ``values`` is the all-access grant ``["*"]`` (R8.3).

        A missing grant (``None`` — the user is not granted this dimension at all) is NOT
        all-scope; an explicit list of concrete values is NOT all-scope. Only the single
        :data:`~sam.members.domain.scope_dimensions.WILDCARD` sentinel counts.
        """
        return list(values or []) == [WILDCARD]

    @staticmethod
    def _covers_value(values, scope_value: str) -> bool:
        """``True`` iff the grant ``values`` covers ``scope_value`` (D9a/R8.3a).

        Covered when the grant is all-access (``["*"]``) or explicitly contains the value. A
        missing grant covers nothing.
        """
        vals = list(values or [])
        return vals == [WILDCARD] or scope_value in vals

    # ── Projection read primitives (mirror the sibling readers) ───────────────────────

    def _query_partition(self, tenant_id: str) -> list[dict]:
        """Return all projected items for ``tenant_id`` (cached, read-only).

        One DynamoDB ``Query`` on the partition key; a missing/empty partition returns ``[]``
        (empty is valid). boto3 is imported lazily so the module imports cleanly where boto3's
        condition types aren't needed (a fake table in tests pre-seeds the cache via ``query``).
        """
        if not tenant_id:
            return []
        if tenant_id in self._partition_cache:
            return self._partition_cache[tenant_id]

        from boto3.dynamodb.conditions import Key

        response = self.table.query(
            KeyConditionExpression=Key(schema.PARTITION_KEY_ATTR).eq(tenant_id)
        )
        items = list(response.get("Items", []) or [])
        self._partition_cache[tenant_id] = items
        return items

    @staticmethod
    def _classify(item: dict) -> tuple[str, tuple[str, ...]]:
        """Return ``(record_type, id_parts)`` for a projected item's sort key.

        A missing/blank sort key classifies as ``("", ())`` so it is simply skipped by the
        callers (never a raise) — empty is valid.
        """
        sk = item.get(schema.SORT_KEY_ATTR, "")
        return schema.split_sort_key(sk) if sk else ("", ())
