"""Membership-service Lidmaatschap Beheer CATALOG surface (M1 split): catalog reads / writes and the serialization helpers. Mixed into ``MembershipService`` -- bodies verbatim."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from sam.members.domain.field_resolver import (
    ResolvedField,
)
from sam.members.domain.fixed_fields import (
    EnumOption,
    MemberNumberFormat,
)


class CatalogMixin:
    @staticmethod
    def _serialize_enum_option(opt: EnumOption) -> dict[str, Any]:
        """Project a rich :class:`EnumOption` to pure JSON — ``{value, label{nl,en}, allowed,
        order?, roles?}`` (03b unified enum model, Req 3.1).

        Surfaces the value-level ``roles`` gate (R4.12) so the frontend can filter a dropdown to
        the caller's permitted options as a CONVENIENCE — the domain remains the authoritative
        gate (:meth:`_reject_disallowed_enum_values`). ``roles`` is omitted when the option is
        open (no restriction) so the payload stays minimal.

        ``allowed`` (the retired/grandfather flag, Req 3.2) is ALWAYS carried — the frontend
        needs it to hide a retired option from the picker while still displaying an existing
        stored value — so it is NOT omitted even when ``True``. ``order`` (render / default rank)
        is carried only when the option is ranked (``None`` → omitted, payload stays minimal).
        """
        payload: dict[str, Any] = {
            "value": opt.value,
            "label": dict(opt.label),
            "allowed": bool(opt.allowed),
        }
        if opt.order is not None:
            payload["order"] = int(opt.order)
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
        field_options: Sequence[Mapping[str, Any]] | None,
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
        - ``scope`` (remediation R3.5) — ``{enabled, required_for}`` when the field is a scope
          axis, so the authoring UI can read the current scope state back; omitted otherwise. The
          scope VALUES are the field's enum values (single vocabulary, R3.2), so no ``values``
          sub-key is emitted; scope RESOLUTION (``allowed_scopes``) is unchanged (R3.8);
        - ``member_number_format`` (R4.8) — the tenant format pattern for the ``member_number``
          manual-entry string field (immediate frontend feedback; server authoritative);
        - ``options`` — the ONE canonical dropdown source the read-assembly seam (design C4 / F8,
          ``_membership_writes_fieldconfig._assemble_field_options``) populated for this field:
          the ACTIVE catalog for ``membership_type`` (reference), the scope dimension's values for
          a scope-backed field, or the field's rich ``{value, label, roles?}`` options for an
          inline enum — ``None`` for a non-selectable field. This serializer NO LONGER re-branches
          by field kind and NO LONGER falls back to ``field.choices`` (F9): it serializes exactly
          the ``field_options`` the seam computed, so the staff editor read and the public read
          see the SAME vocabulary from the SAME assembly point.

        ``field_options`` is the seam's pre-computed canonical option list (JSON-friendly dicts),
        or ``None`` for a field with no selectable source.
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
            # Single-list PROVENANCE badge (Phase 3 step 8, R1.2) — base / tenant_added /
            # base_overridden, derived at resolve time. Additive to the serialized shape; the
            # resolved field SET + `(group, order, key)` order are unchanged (Property 1, R1.6).
            "provenance": field.provenance.value,
            "functional_group": field.functional_group or field.group,
        }
        if field.show_when is not None:
            payload["show_when"] = dict(field.show_when)
        if field.scope is not None:
            # Remediation R3.5: surface the field's SCOPE attribute as ``{enabled, required_for}``
            # so the authoring UI can READ the current scope state back (it was previously DEAD on
            # read — never populated on ``ResolvedField``, never serialized). The ``values`` sub-key
            # is deliberately NOT emitted: scope values ARE the field's enum values (single
            # vocabulary, R3.2) — the Flask builder derives ``config#scope`` from the enum. Scope
            # RESOLUTION (``allowed_scopes``) is unaffected — it reads ``config#scope``, not this.
            payload["scope"] = {
                "enabled": bool(field.scope.enabled),
                "required_for": list(field.scope.required_for),
            }
        if (
            field.member_number_format is not None
            and not field.member_number_format.is_empty()
        ):
            payload["member_number_format"] = (
                CatalogMixin._serialize_member_number_format(field.member_number_format)
            )
        # The ONE canonical `options` the read-assembly seam (design C4 / F8) populated for this
        # field — reference (active catalog) / scope (dimension values) / inline enum, or `None`.
        # No per-kind branch and no `field.choices` fallback here (F9): this serializer consumes
        # the seam's single `options` so the staff and public reads agree by construction.
        payload["options"] = (
            [dict(o) for o in field_options] if field_options is not None else None
        )

        # Public member-application attributes (spec 11; D20 / R4.2 / R4a / R4b / R7.1). The
        # Application Form Builder AUTHORS these onto `config#fields` and reads them BACK through
        # this staff serializer to re-seed its on-the-form toggles + per-field controls after a
        # save. They were previously DEAD on this read (resolved onto `ResolvedField`, consumed by
        # the public read/create path, but never serialized here) — so the builder reseeded every
        # field OFF after a save even though the write persisted. Emit them verbatim, mirroring the
        # frontend `OverlayField` shape; the server stays the authoritative enforcer (R8).
        payload["application_visible"] = bool(field.application_visible)
        payload["application_required"] = bool(field.application_required)
        payload["application_choices"] = (
            list(field.application_choices)
            if field.application_choices is not None
            else None
        )
        payload["format"] = (
            {"checker": field.format.checker, "params": dict(field.format.params)}
            if field.format is not None
            else None
        )
        return payload
