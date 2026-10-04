"""Membership-service READ surface (M1 split): scope filtering, self-service ownership, calculated-field enrichment, and the member / membership / payment reads. Mixed into ``MembershipService`` -- bodies are verbatim."""
from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from sam.members.domain.calculated_fields import CALCULATED_FIELDS
from sam.members.domain.error_codes import (
    ENUM_ROLE_RESTRICTED,
    MEMBERSHIP_TYPE_RETIRED,
    MEMBERSHIP_TYPE_UNKNOWN_REFERENCE,
    VALIDATION_MUST_BE_ONE_OF,
    VALIDATION_REQUIRED,
    VALIDATION_UNSUPPORTED_FIELD_TYPE,
    FieldError,
)
from sam.members.domain.field_resolver import (
    OVERLAY_GROUP,
    FieldOrigin,
    FieldResolver,
    FunctionalGroup,
    ResolvedField,
    StaticOverlayProvider,
    TenantOverlayProvider,
    _member_value,
    evaluate_show_when,
)
from sam.members.domain.field_resolver import (
    FieldConfig as ResolvedFieldConfig,
)
from sam.members.domain.fixed_fields import (
    MEMBER_NUMBER_FIELD_KEY,
    EnumOption,
    FieldGroup,
    FieldType,
    FieldValidationError,
    MemberNumberFormat,
    MembershipStatus,
    roles_for_option,
    validate_fixed_fields,
    validate_member_number_format,
)
from sam.members.domain.lifecycle_config import (
    GuardEvaluation,
    LifecycleConfig,
    LifecycleConfigProvider,
    StaticLifecycleConfigProvider,
    evaluate_guards,
    evaluate_required_fields,
)
from sam.members.domain.membership_type_catalog import (
    MembershipTypeEntry,
    MembershipTypeValidationError,
)
from sam.members.domain.scope_canon import scope_canon
from sam.members.domain.scope_dimensions import (
    WILDCARD,
    ScopeConfigProvider,
)
from sam.members.domain.tenant_hooks import HookName, TenantHookRegistry
from sam.members.domain.transition_hooks import TransitionHookRegistry
from sam.members.domain.view_contexts import (
    StaticViewContextsProvider,
    ViewContext,
    ViewContextsProvider,
)
from sam.members.repository.members_repository import (
    Member,
    Membership,
    MembersRepository,
    Payment,
)

from sam.members.domain._membership_errors import (
    DEFAULT_SCOPE_DIMENSION_KEY,
    MEMBERSHIP_STATUS_FIELD_KEY,
    MEMBERSHIP_TYPE_FIELD_KEY,
    MemberNotFound,
    MemberValidationError,
    MembershipTypeConflict,
    MembershipTypeNotFound,
    ScopeDenied,
    TransitionDenied,
    TransitionResult,
    _as_field_error,
)


class ReadsMixin:
    # ── Scope helpers (domain-layer scope filtering — design C4, Property 4/6) ────────
    #
    # s5d task 4.1/4.2 (R3.3/R6.2, ODx2 Option A): ``allowed_scopes`` is a PER-DIMENSION
    # map ``{dimension_key: [values]}`` resolved at the edge — one entry per enabled
    # dimension (``["*"]`` = all for that dimension, a subset = scoped, ``[]`` = deny). Task
    # 4.2 formalizes multi-dimension enforcement: :meth:`_in_scope` ITERATES the whole map
    # and a member is visible only if it passes EVERY dimension (AND — Property 6). Each
    # dimension is evaluated against the member's own field (``_record_scope_values(member,
    # dimension_key)`` reads that dimension's field), so a two-dimension tenant reads two
    # different fields. Single-dimension tenants (h-dcn ``region``) are the N=1 case — one
    # map entry — so behaviour is unchanged; there is NO special-casing of one vs many.
    # The gating-``dimension_key`` param is gone from ``_in_scope`` and the public read/write
    # methods: the map itself carries every dimension the check needs.

    @staticmethod
    def _is_wildcard(values: Sequence[str]) -> bool:
        """True when the caller may see every record for a dimension (``["*"]``)."""
        return list(values) == [WILDCARD]

    @staticmethod
    def _is_deny(values: Sequence[str]) -> bool:
        """True when the caller has no grant for a dimension (empty) → see nothing (Property 4)."""
        return len(list(values)) == 0

    @staticmethod
    def _record_scope_values(
        member: Member, dimension_key: str
    ) -> list[str]:
        """The member's canonical value for the gating dimension, as a 0-or-1-element list.

        Scope is a **plain member field** now — the ``scope_values`` bucket is retired (S5d
        D1, R3.4). A dimension binds to a normal member field (``members.scope_dimensions[
        dim].field``, defaulting to the dimension ``key`` — h-dcn's ``region`` dimension binds
        to the tenant-added ``region`` overlay field). We read the member's SCALAR value for
        that field via the shared field→bucket accessor (:func:`~sam.members.domain.
        field_resolver._member_value`): a dotted field key resolves to its explicit bucket,
        while a bare key resolves nested-bucket-first (``personal`` / ``membership`` /
        ``overlay``) with a flat top-level fallback — the bucket is NEVER hardcoded.

        The read value is passed through the shared :func:`~sam.members.domain.scope_canon.
        scope_canon` so a member's stored value and a granted value share one canonical
        vocabulary (Property 4). A member is single-valued per scope field (R3.2), so this
        returns ``[scope_canon(value)]`` for a present value, or ``[]`` when the field is
        absent / blank (which a scoped caller never intersects → not visible; a wildcard
        caller sees the record anyway because wildcard short-circuits before this is
        consulted).
        """
        if not isinstance(member, Mapping):
            return []
        # The field the dimension binds to defaults to the dimension key (h-dcn: "region").
        raw = _member_value(member, dimension_key)
        if raw is None:
            return []
        canonical = scope_canon(raw if isinstance(raw, str) else str(raw))
        if not canonical:
            return []
        return [canonical]

    def _passes_dimension(
        self, member: Member, dimension_key: str, values: Sequence[str]
    ) -> bool:
        """Whether ``member`` passes ONE scope dimension's grant (design C4, Property 4).

        The per-dimension rule, evaluated against the member's OWN field for that dimension:

        - ``["*"]`` → passes (tenant-wide for that dimension);
        - ``[]`` → fails (no grant for that dimension → deny — Property 4);
        - a subset → passes only when the member's canonical value for that dimension's field
          intersects the granted subset.

        Enforcement is exact-equality on the CANONICAL form: both the member's stored value
        (already canonicalised by :meth:`_record_scope_values`, which reads that dimension's
        field via ``members.scope_dimensions[dim].field``, default = the dimension key) and
        each granted value are reduced by :func:`scope_canon`, so case / diacritic / separator
        variants match while partials never do. The wildcard sentinel is preserved verbatim.
        """
        if self._is_wildcard(values):
            return True
        if self._is_deny(values):
            return False
        granted = {scope_canon(s) if s != WILDCARD else s for s in values}
        record_values = set(self._record_scope_values(member, dimension_key))
        return bool(granted & record_values)

    def _in_scope(
        self,
        member: Member,
        allowed_scopes: Mapping[str, Sequence[str]],
    ) -> bool:
        """Whether ``member`` is visible to a caller holding ``allowed_scopes`` (Property 6).

        s5d task 4.2 (R3.3, ODx2 Option A): ``allowed_scopes`` is the PER-DIMENSION map
        ``{dimension_key: [values]}`` the edge resolves over EVERY enabled dimension. This
        ITERATES the map and applies the per-dimension rule (:meth:`_passes_dimension`) to
        each entry, reading each dimension's own field. A member is visible ONLY IF it passes
        EVERY dimension (AND-across-dimensions): pass one dimension but fail another → NOT
        visible; ``["*"]`` passes a dimension, ``[]`` fails it.

        An EMPTY map (``{}``) — no dimension grant at all — is deny-by-default: ``all(...)``
        over no entries would be vacuously true, so we treat the empty map as "see nothing".
        A tenant-wide caller is ``{"<dim>": ["*"]}`` (the edge's collapse), never ``{}``.
        Single-dimension tenants (h-dcn ``region``) are the N=1 case — one entry — so this
        reduces to the original single-dimension behaviour with no special-casing.
        """
        if not allowed_scopes:
            return False
        return all(
            self._passes_dimension(member, dimension_key, values)
            for dimension_key, values in allowed_scopes.items()
        )

    # ── Self-service ownership (design C1 self_service routes) ────────────────────────

    @staticmethod
    def _owns_record(member: Member, requester_sub: str | None) -> bool:
        """Whether ``requester_sub`` identifies the owner of ``member`` (self-service).

        A member may read their OWN record even without a broad scope grant. Ownership is
        matched on the record's identity, in priority order, tolerant of what the record
        carries (the fixed registry has no cognito field yet, so we accept whichever
        identity is present):

        1. a cognito subject stored on the record (``sub`` / ``cognito_sub``);
        2. the ``member_id`` (a token whose subject *is* the member id);
        3. the personal email (``personal.email``).

        A missing ``requester_sub`` never matches (no ambient ownership). This never widens
        access to *other* members — it is a per-record identity check.
        """
        if not requester_sub:
            return False
        candidates: set[str] = set()
        for key in ("sub", "cognito_sub"):
            value = member.get(key)
            if value:
                candidates.add(str(value))
        member_id = member.get("member_id")
        if member_id:
            candidates.add(str(member_id))
        personal = member.get("personal") or {}
        if isinstance(personal, Mapping):
            email = personal.get("email")
            if email:
                candidates.add(str(email))
        return str(requester_sub) in candidates

    def _visible_member_or_raise(
        self,
        tenant_id: str,
        member_id: str,
        allowed_scopes: Mapping[str, Sequence[str]],
        *,
        requester_sub: str | None,
        self_service: bool,
    ) -> Member:
        """Fetch a member and enforce scope + self-service, or raise :class:`MemberNotFound`.

        The shared gate behind every single-member read (``get_member`` and the child reads
        that hang off a member). It fetches within the tenant (Property 1), then allows the
        read when EITHER the member is in the caller's scope OR the caller owns the record
        via self-service. Anything else is an indistinguishable not-found (no existence
        leak).
        """
        member = self._repo.get_member(tenant_id, member_id)
        if member is None:
            raise MemberNotFound(tenant_id, member_id)

        if self._in_scope(member, allowed_scopes):
            return self._enrich_calculated(member)
        if self_service and self._owns_record(member, requester_sub):
            return self._enrich_calculated(member)
        raise MemberNotFound(tenant_id, member_id)

    # ── Calculated-field enrichment (R4.4) ─────────────────────────────────────────────
    @staticmethod
    def _enrich_calculated(record: Member) -> Member:
        """Return a copy of ``record`` with calculated (derived) fields merged in (R4.4).

        Calculated fields are NEVER stored; they are computed on read from the record's fixed
        fields (``compute_calculated_fields``) and merged into the record under their STORAGE
        bucket (``personal`` / ``membership``) beside the fixed fields, so the presentation
        accessor (``valueFor(record, group, key)``) resolves them exactly like a stored field.
        A derivation whose inputs are absent yields ``None`` and is simply omitted (never a
        raise). Non-mapping records pass through untouched (defensive).
        """
        if not isinstance(record, Mapping):
            return record
        enriched: dict[str, Any] = {k: v for k, v in record.items()}
        for calc in CALCULATED_FIELDS:
            value = calc.evaluate(enriched)
            if value is None:
                continue
            bucket_key = calc.group.value  # storage bucket: "personal" / "membership"
            bucket = enriched.get(bucket_key)
            bucket = dict(bucket) if isinstance(bucket, Mapping) else {}
            bucket[calc.key] = value
            enriched[bucket_key] = bucket
        return enriched

    # ── Member reads ──────────────────────────────────────────────────────────────────

    def list_members(
        self,
        tenant_id: str,
        allowed_scopes: Mapping[str, Sequence[str]],
        *,
        filters: Mapping[str, Any] | None = None,
    ) -> list[Member]:
        """List the tenant's members, narrowed to the caller's scope (design C4, Property 4/6).

        Asks the repository for the tenant's members (keyed by ``tenant_id`` — Property 1),
        optionally passing ``filters`` through, then narrows by ``allowed_scopes`` (the s5d
        per-dimension map ``{dimension_key: [values]}``): a member is returned only when it
        passes EVERY dimension (:meth:`_in_scope` — AND-across-dimensions, Property 6). An
        empty map, or a dimension whose grant is ``[]``, yields nothing (deny-by-default); a
        dimension whose grant is ``["*"]`` passes that axis. Ordering is the repository's.

        A guaranteed-deny map short-circuits before scanning: an EMPTY map, or ANY dimension
        whose grant is ``[]`` (which no member can pass on that axis), means the AND can never
        hold — so we return ``[]`` without asking the repository at all (deny-by-default).
        """
        if not allowed_scopes or any(
            self._is_deny(values) for values in allowed_scopes.values()
        ):
            # Deny-by-default: no scope grant (empty map or a denied dimension) → see nothing,
            # without even scanning results.
            return []
        members = self._repo.list_members(tenant_id, filters=filters)
        return [
            self._enrich_calculated(m)
            for m in members
            if self._in_scope(m, allowed_scopes)
        ]

    def export_members(
        self,
        tenant_id: str,
        allowed_scopes: Mapping[str, Sequence[str]],
        *,
        filters: Mapping[str, Any] | None = None,
    ) -> list[Member]:
        """Export the tenant's members (scope-narrowed) — the export projection.

        Same scope semantics as :meth:`list_members` (a scoped exporter exports only their
        scope; an empty scope exports nothing). Kept a distinct method so the export
        projection can diverge from the list projection later without touching the scope
        rule; today it returns the same scope-filtered records.
        """
        return self.list_members(tenant_id, allowed_scopes, filters=filters)

    def get_member(
        self,
        tenant_id: str,
        member_id: str,
        allowed_scopes: Mapping[str, Sequence[str]],
        *,
        requester_sub: str | None = None,
        self_service: bool = False,
    ) -> Member:
        """Fetch one member by id, enforcing scope + self-service (design C1/C4).

        Fetches within the tenant (Property 1) and returns the member when it is in the
        caller's scope, OR — when ``self_service`` — when the caller owns the record
        (matched on ``requester_sub``). Otherwise raises :class:`MemberNotFound` (the edge
        maps that to a 404 without leaking whether the member exists out of scope).
        """
        return self._visible_member_or_raise(
            tenant_id,
            member_id,
            allowed_scopes,
            requester_sub=requester_sub,
            self_service=self_service,
        )

    def get_self(
        self,
        tenant_id: str,
        requester_sub: str | None,
    ) -> Member:
        """Return the calling member's OWN record (the ``GET /members/me`` self-service read).

        Pure self-service: there is no broad scope grant on this route (its capability is
        ``None``); the caller is only ever entitled to their own record. We resolve the
        record by scanning the tenant's members for the one the ``requester_sub`` owns
        (tenant-scoped — Property 1), and raise :class:`MemberNotFound` if none matches.
        Because ownership is a per-record identity match, this can never return another
        member.
        """
        if not requester_sub:
            raise MemberNotFound(tenant_id, "<self>")
        for member in self._repo.list_members(tenant_id):
            if self._owns_record(member, requester_sub):
                return self._enrich_calculated(member)
        raise MemberNotFound(tenant_id, "<self>")

    # ── Membership reads (scope-checked via the parent member) ────────────────────────

    def list_memberships(
        self,
        tenant_id: str,
        member_id: str,
        allowed_scopes: Mapping[str, Sequence[str]],
        *,
        requester_sub: str | None = None,
        self_service: bool = False,
    ) -> list[Membership]:
        """List a member's memberships, gated by the parent member's visibility.

        The membership read is only permitted once the parent member passes the scope /
        self-service gate (:meth:`_visible_member_or_raise`), so a scoped caller cannot read
        the memberships of an out-of-scope member. Then the repository is asked for that
        member's memberships (tenant-scoped — Property 1).
        """
        self._visible_member_or_raise(
            tenant_id,
            member_id,
            allowed_scopes,
            requester_sub=requester_sub,
            self_service=self_service,
        )
        return list(self._repo.list_memberships(tenant_id, member_id))

    def get_membership(
        self,
        tenant_id: str,
        member_id: str,
        membership_id: str,
        allowed_scopes: Mapping[str, Sequence[str]],
        *,
        requester_sub: str | None = None,
        self_service: bool = False,
    ) -> Membership:
        """Fetch one membership of a member, gated by the parent member's visibility.

        Enforces the parent member's scope / self-service gate first, then fetches the
        membership within the tenant. A missing membership (under a visible member) raises
        :class:`MemberNotFound` — the edge maps it to a 404.
        """
        self._visible_member_or_raise(
            tenant_id,
            member_id,
            allowed_scopes,
            requester_sub=requester_sub,
            self_service=self_service,
        )
        membership = self._repo.get_membership(tenant_id, member_id, membership_id)
        if membership is None:
            raise MemberNotFound(tenant_id, member_id)
        return membership

    # ── Member-scoped payments (scope-checked via the parent member) ──────────────────

    def get_member_payments(
        self,
        tenant_id: str,
        member_id: str,
        allowed_scopes: Mapping[str, Sequence[str]],
        *,
        requester_sub: str | None = None,
        self_service: bool = False,
    ) -> list[Payment]:
        """List a member's payments, gated by the parent member's visibility.

        Same gate as the membership reads: the parent member must be visible (scope or
        self-service) before its payments are returned, so payments never leak across scope.
        The repository read is tenant-scoped (Property 1).
        """
        self._visible_member_or_raise(
            tenant_id,
            member_id,
            allowed_scopes,
            requester_sub=requester_sub,
            self_service=self_service,
        )
        return list(self._repo.list_member_payments(tenant_id, member_id))

