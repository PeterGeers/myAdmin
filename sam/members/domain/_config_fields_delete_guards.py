"""Delete-safety guards (group/field in use).

Part of ConfigFieldsCrudService (code-quality-fixes-2026-11-12 task 4).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ._config_fields_shared import ConfigFieldsCrudError


class ConfigFieldsDeleteGuardsMixin:
    """Delete-safety guards (group/field in use)."""

    # ── Delete-safety guards (task 2.6 — design C1; R4.3; review Should-fix) ────────────

    def _guard_delete_field(
        self,
        tenant_id: str,
        field_key: str,
        placement: Mapping[str, Any],
        *,
        snapshot: Mapping[str, Any] | None = None,
    ) -> None:
        """Refuse deleting a VARIABLE field that is IN USE (design C1; review Should-fix).

        A delete must never orphan data. Two kinds of "in use" block the delete:

        - **Member data:** some member record stores a value under this field's key. Observed via
          the optional injected ``usage_probe`` (storage-agnostic — the domain never queries the
          members table itself, steering 35/39). When no probe is wired this leg cannot be checked
          and does not block (production always wires one).
        - **A dangling reference:** a group/application reference points at the field (e.g. an
          ``application_choices`` subset or a ``show_when`` condition naming it). The probe may also
          report this; the snapshot carries the field's own authored shape for a lightweight check.

        When the field is in use the delete is REFUSED with a caller-safe
        :class:`ConfigFieldsCrudError` that names the safe alternative — hide the field
        (``visible=false``) instead of deleting it, which preserves the stored member values while
        removing it from forms. The error carries NO raw internals (steering 39).
        """
        usage = self._field_usage(tenant_id, field_key)
        if usage is None:
            return
        reasons: list[str] = []
        if usage.get("member_data"):
            reasons.append("member records still store a value under it")
        if usage.get("references"):
            refs = usage["references"]
            if isinstance(refs, (list, tuple, set)):
                reasons.append(
                    "it is still referenced by "
                    + ", ".join(sorted(str(r) for r in refs))
                )
            else:
                reasons.append("it is still referenced elsewhere")
        if not reasons:
            return
        raise ConfigFieldsCrudError(
            f"cannot delete field {field_key!r}: " + "; ".join(reasons) + ". "
            "Hide it instead (set visible=false) to keep existing data while removing it from "
            "forms."
        )

    def _field_usage(self, tenant_id: str, field_key: str) -> dict | None:
        """Ask the injected ``usage_probe`` whether ``field_key`` is in use, normalised to a dict.

        Returns ``{"member_data": bool, "references": <iterable|falsey>}`` or ``None`` when no
        probe is wired (usage unobservable → the member-data leg does not block). Accepts either
        probe shape:

        - a rich ``field_usage(tenant_id, field_key)`` returning a mapping with ``member_data`` /
          ``references`` keys (passed through), or
        - a boolean ``field_in_use(tenant_id, field_key)`` (normalised to
          ``{"member_data": <bool>}``).
        """
        probe = self._usage_probe
        if probe is None:
            return None
        if hasattr(probe, "field_usage"):
            usage = probe.field_usage(tenant_id, field_key)
            return dict(usage) if isinstance(usage, Mapping) else {}
        if hasattr(probe, "field_in_use"):
            return {"member_data": bool(probe.field_in_use(tenant_id, field_key))}
        return None

    def _guard_delete_group(
        self,
        tenant_id: str,
        group_key: str,
        placement: Mapping[str, Any],
        *,
        snapshot: Mapping[str, Any] | None = None,
    ) -> None:
        """Refuse deleting a functional group that STILL HOLDS fields (R4.3).

        Reads the SAME consistent snapshot used for placement: a group is non-empty when any
        AUTHORED field in the overlay — a variable field (``fields.<key>``) or a base-field
        override (``fixed_overrides.<dotted>``) — resolves into this group via its
        ``functional_group`` aspect. Deleting a non-empty group would orphan those fields into a
        group that no longer exists, so it is REFUSED with a caller-safe
        :class:`ConfigFieldsCrudError`; the admin must first move or delete the member fields.

        Note: this inspects the AUTHORED overlay (the snapshot), which is what the write addresses.
        A group holding only base fields whose membership is code-defined is a separate concern
        handled by the resolver; the authored-overlay check is the one that keeps a delete op from
        orphaning a tenant-authored field.
        """
        if not isinstance(snapshot, Mapping):
            return
        held = self._fields_in_group(snapshot, group_key)
        if held:
            raise ConfigFieldsCrudError(
                f"cannot delete group {group_key!r}: it still holds "
                + ", ".join(repr(k) for k in held)
                + ". Move or delete those fields first."
            )

    @staticmethod
    def _fields_in_group(snapshot: Mapping[str, Any], group_key: str) -> list[str]:
        """Authored field keys (variable + override) whose ``functional_group`` is ``group_key``.

        Scans the snapshot's ``fields`` and ``fixed_overrides`` wire containers; a spec assigns the
        group via its ``functional_group`` aspect. Returns the keys in a stable (sorted) order so
        the refusal message is deterministic.
        """
        held: list[str] = []
        for wire_key in ("fields", "fixed_overrides"):
            container = snapshot.get(wire_key)
            if not isinstance(container, Mapping):
                continue
            for key, spec in container.items():
                if (
                    isinstance(spec, Mapping)
                    and spec.get("functional_group") == group_key
                ):
                    held.append(key)
        return sorted(held)
