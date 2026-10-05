"""Membership-service Lidmaatschap Beheer CATALOG surface (M1 split): catalog reads / writes and the serialization helpers. Mixed into ``MembershipService`` -- bodies verbatim."""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from sam.members.domain._membership_errors import (
    MEMBERSHIP_TYPE_FIELD_KEY,
    MembershipTypeConflict,
    MembershipTypeNotFound,
)
from sam.members.domain.field_resolver import (
    ResolvedField,
)
from sam.members.domain.fixed_fields import (
    EnumOption,
    MemberNumberFormat,
)
from sam.members.domain.membership_type_catalog import (
    MembershipTypeEntry,
    MembershipTypeValidationError,
)


class CatalogMixin:
    # ── Lidmaatschap Beheer catalog reads (design C8, R2.4 — task 3.4) ────────────────

    def list_membership_types(
        self, tenant_id: str, *, active_only: bool = False
    ) -> list[dict[str, Any]]:
        """List the tenant's Lidmaatschap Beheer catalog entries (design C8, R2.4).

        The MANAGEMENT read behind ``GET /membership-types``. Asks the repository for the
        tenant's catalog (keyed by ``tenant_id`` — Property 1), already ordered by
        ``(order, type_code)``, and projects each entry to the JSON-friendly management shape
        (:meth:`_serialize_catalog_entry` — carries ``active`` so an admin can see which types
        are retired). The frontend renders it and enforces nothing (authority stays here).

        Args:
            active_only: ``False`` (default) returns ALL entries incl. soft-deleted
                (``active=false``) so the management view shows retired types (design C8
                soft-delete semantics); ``True`` returns only the assignable ones — the same
                active-only view the dropdown feed uses. The active/all choice is explicit and
                lives on the domain read, not hidden in the handler.
        """
        entries = self._repo.list_membership_types(tenant_id, active_only=active_only)
        return [self._serialize_catalog_entry(entry) for entry in entries]

    def get_membership_type(self, tenant_id: str, type_code: str) -> dict[str, Any]:
        """Fetch one Lidmaatschap Beheer catalog entry by its ``type_code`` (design C8, R2.4).

        The read behind ``GET /membership-types/{type_code}``. Fetches within the tenant
        (Property 1) and returns the entry in the JSON-friendly management shape. An absent
        code (or one that exists only for another tenant) raises :class:`MembershipTypeNotFound`
        — the edge maps that to a ``404`` (consistent with :class:`MemberNotFound`). A
        soft-deleted (``active=false``) entry is still returned (management shows retired
        types), never a 404.
        """
        entry = self._repo.get_membership_type(tenant_id, type_code)
        if entry is None:
            raise MembershipTypeNotFound(tenant_id, type_code)
        return self._serialize_catalog_entry(entry)

    # ── Lidmaatschap Beheer catalog writes (design C8, R2.4/R1.4 — task 5.3) ──────────
    #
    # CRUD for catalog entries: create + update persist a validated entry; delete is a
    # SOFT-delete (active=false), never a hard delete — existing members keep their reference
    # while the type leaves the dropdown (C8 referential integrity). All tenant-scoped
    # (Property 1) and tenant-agnostic (no ``if tenant``): the catalog is the tenant's own
    # managed data. The repository is the sole DynamoDB touch-point + validates on persist.

    def create_membership_type(
        self, tenant_id: str, body: Mapping[str, Any]
    ) -> dict[str, Any]:
        """Create a Lidmaatschap Beheer catalog entry for the tenant (design C8, R2.4).

        Builds a :class:`MembershipTypeEntry` from the client body, stamping the authoritative
        ``tenant_id`` (never trusting a body ``tenant_id`` — verify-before-trust, Property 2),
        validates it (:meth:`MembershipTypeEntry.validate` — non-blank code with no key
        separator, a non-blank ``nl`` label, an integer ``order``), and persists it. Create is
        NOT an upsert: a ``type_code`` that already exists for the tenant raises
        :class:`MembershipTypeConflict` (→ 409) so a create can never silently mutate a live
        type (an intentional change goes through :meth:`update_membership_type`). A malformed
        body raises :class:`MembershipTypeValidationError` (→ 422). Returns the persisted entry
        in the management shape.
        """
        entry = self._entry_from_body(tenant_id, body)
        entry.validate()
        if self._repo.get_membership_type(tenant_id, entry.type_code) is not None:
            raise MembershipTypeConflict(tenant_id, entry.type_code)
        saved = self._repo.save_membership_type(tenant_id, entry)
        return self._serialize_catalog_entry(saved)

    def update_membership_type(
        self, tenant_id: str, type_code: str, body: Mapping[str, Any]
    ) -> dict[str, Any]:
        """Update an existing catalog entry (design C8, R2.4).

        Loads the entry within the tenant (Property 1); an absent code raises
        :class:`MembershipTypeNotFound` (→ 404). Merges the client body over the existing
        entry — the path's ``type_code`` is authoritative for identity (a body ``type_code`` /
        ``tenant_id`` can never move the entry), the ``label`` is replaced when supplied, and
        ``active`` / ``order`` are overridden when present — then validates and persists.
        Returns the updated entry in the management shape.
        """
        existing = self._repo.get_membership_type(tenant_id, type_code)
        if existing is None:
            raise MembershipTypeNotFound(tenant_id, type_code)

        payload = dict(body) if isinstance(body, Mapping) else {}
        label = existing.label
        if "label" in payload and isinstance(payload.get("label"), Mapping):
            label = dict(payload["label"])
        active = bool(payload["active"]) if "active" in payload else existing.active
        order = existing.order
        if "order" in payload:
            try:
                order = int(payload["order"])
            except (TypeError, ValueError):
                raise MembershipTypeValidationError({"order": "must be an integer"})

        updated = MembershipTypeEntry(
            tenant_id=tenant_id,          # authoritative — never the body
            type_code=type_code,          # the path is authoritative for identity
            label=label,
            active=active,
            order=order,
        )
        updated.validate()
        saved = self._repo.save_membership_type(tenant_id, updated)
        return self._serialize_catalog_entry(saved)

    def deactivate_membership_type(
        self, tenant_id: str, type_code: str
    ) -> dict[str, Any]:
        """Soft-delete (retire) a catalog entry: ``active=false`` — NEVER a hard delete (C8).

        The retired type keeps existing members' references valid (design C8 referential
        integrity) while leaving the dropdown for new/edited members (the active-only feed +
        the reference check both exclude it). Tenant-scoped (Property 1); an absent code raises
        :class:`MembershipTypeNotFound` (→ 404). Idempotent — retiring an already-retired type
        returns it unchanged. Returns the retired entry in the management shape (``active`` will
        be ``False``); the entry is still gettable in the management view (it is not removed).
        """
        retired = self._repo.deactivate_membership_type(tenant_id, type_code)
        if retired is None:
            raise MembershipTypeNotFound(tenant_id, type_code)
        return self._serialize_catalog_entry(retired)

    @staticmethod
    def _entry_from_body(tenant_id: str, body: Mapping[str, Any]) -> MembershipTypeEntry:
        """Build a :class:`MembershipTypeEntry` from a client create body (unvalidated).

        Stamps the authoritative ``tenant_id`` (never a body value — Property 2) and reads the
        entry's ``type_code`` / ``label`` / ``active`` / ``order`` from the body with the
        entity's defaults (``active=True``, ``order=0``). The caller validates the result. A
        non-integer ``order`` is left as-is so :meth:`MembershipTypeEntry.validate` surfaces it
        as a field error (a 422) rather than the handler guessing.
        """
        payload = dict(body) if isinstance(body, Mapping) else {}
        label = payload.get("label")
        return MembershipTypeEntry(
            tenant_id=tenant_id,
            type_code=str(payload.get("type_code", "")),
            label=dict(label) if isinstance(label, Mapping) else {},
            active=bool(payload.get("active", True)),
            order=payload.get("order", 0),
        )

    @staticmethod
    def _serialize_catalog_option(entry: MembershipTypeEntry) -> dict[str, Any]:
        """Project a catalog entry to the DROPDOWN-OPTION shape (the active-only feed, C8).

        The presentation shape the ``membership_type`` field's ``options`` carry: the
        reference ``value`` (``type_code``) the member record stores, its i18n ``label``, and
        the ``order`` for rendering. It deliberately omits ``active`` — the dropdown only ever
        lists active entries, so the flag would be noise.
        """
        return {
            "value": entry.type_code,
            "label": dict(entry.label),
            "order": int(entry.order),
        }

    @staticmethod
    def _serialize_catalog_entry(entry: MembershipTypeEntry) -> dict[str, Any]:
        """Project a catalog entry to the MANAGEMENT shape (the catalog read routes, C8).

        Carries the full management view — ``type_code`` (the reference key), i18n ``label``,
        ``active`` (so an admin sees which types are retired), and ``order`` — as pure JSON.
        Distinct from :meth:`_serialize_catalog_option` (the dropdown feed) which drops
        ``active`` because that feed is active-only.
        """
        return {
            "type_code": entry.type_code,
            "label": dict(entry.label),
            "active": bool(entry.active),
            "order": int(entry.order),
        }

    @staticmethod
    def _serialize_enum_option(opt: EnumOption) -> dict[str, Any]:
        """Project a rich :class:`EnumOption` (``{value, label{nl,en}, roles?}``) to pure JSON.

        Surfaces the value-level ``roles`` gate (R4.12) so the frontend can filter a dropdown to
        the caller's permitted options as a CONVENIENCE — the domain remains the authoritative
        gate (:meth:`_reject_disallowed_enum_values`). ``roles`` is omitted when the option is
        open (no restriction) so the payload stays minimal.
        """
        payload: dict[str, Any] = {"value": opt.value, "label": dict(opt.label)}
        if opt.roles:
            payload["roles"] = list(opt.roles)
        return payload

    @staticmethod
    def _serialize_member_number_format(fmt: MemberNumberFormat) -> dict[str, Any]:
        """Project a :class:`MemberNumberFormat` to pure JSON for the frontend's format feedback.

        Carries the tenant's ``member_number`` format so the Add/Edit modal can give IMMEDIATE
        format feedback (R4.8): the effective ``regex`` (the compiled prefix+width or the raw
        regex), the ``prefix`` / ``width`` primitives, and a human-readable ``example``. The
        server stays authoritative — this is convenience feedback, not the enforced rule.
        """
        return {
            "prefix": fmt.prefix,
            "width": int(fmt.width),
            "regex": fmt.as_regex(),
            "example": fmt.example(),
        }

    @staticmethod
    def _serialize_field(
        field: ResolvedField,
        *,
        options: Sequence[Mapping[str, Any]],
    ) -> dict[str, Any]:
        """Project a :class:`ResolvedField` into the JSON-friendly shape the frontend renders.

        Carries what the frontend needs to render the resolved field set in the sectioned
        view/edit/add/delete modals (task 4.4, design C-SURFACE) and nothing it needs to
        *enforce* (authority stays server-side, R2.3):

        - ``key`` / ``group`` (storage bucket) / ``type`` / ``required`` / ``label`` /
          ``visible`` / ``order`` / ``origin`` (as before);
        - ``functional_group`` (R4.9) — the PARAMETER-DRIVEN display group the modals SECTION by;
        - ``read_only`` — ``True`` for calculated (derived) fields, which are never editable (R4.4);
        - ``show_when`` (R4.12) — the per-field conditional-visibility condition (a hidden field
          is not required, mirrored authoritatively server-side);
        - ``member_number_format`` (R4.8) — the tenant format pattern for the ``member_number``
          manual-entry string field (immediate frontend feedback; server authoritative);
        - ``options`` — the dropdown source per R4.11: for ``membership_type`` the ACTIVE catalog
          entries; for any other field with rich :class:`EnumOption`s (e.g. ``status``, an overlay
          enum) the ``{value, label, roles?}`` options carrying the value-level role gate (R4.12);
          else the bare ``choices`` list; else ``None``.
        """
        payload: dict[str, Any] = {
            "key": field.key,
            "group": field.group,
            "type": field.type.value,
            "required": bool(field.required),
            "label": dict(field.label),
            "visible": bool(field.visible),
            "read_only": bool(field.read_only),
            "order": int(field.order),
            "origin": field.origin.value,
            "functional_group": field.functional_group or field.group,
        }
        if field.show_when is not None:
            payload["show_when"] = dict(field.show_when)
        if field.member_number_format is not None and not field.member_number_format.is_empty():
            payload["member_number_format"] = (
                CatalogMixin._serialize_member_number_format(field.member_number_format)
            )
        if field.dotted_key() == MEMBERSHIP_TYPE_FIELD_KEY:
            payload["options"] = [dict(o) for o in options]
        elif field.options is not None:
            # Rich enum options ({value,label,roles?}) — carry the value-level role gate (R4.12)
            # so the frontend can filter the dropdown to the caller's permitted values.
            payload["options"] = [
                CatalogMixin._serialize_enum_option(o) for o in field.options
            ]
        elif field.choices is not None:
            payload["options"] = list(field.choices)
        else:
            payload["options"] = None
        return payload
