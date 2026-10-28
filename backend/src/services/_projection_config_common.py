"""Governance projection — shared primitives for the tenant-level ``config#*`` row builders.

INTERNAL helper module of :mod:`services._projection_config_builders` — extracted from it
(code-quality file-length split, 2026-10-28) with **zero behaviour change**. Holds the pieces
the per-row builders (``config#scope`` / ``config#fields`` / ``config#mail``) all share:

- the ``members.*`` parameter namespace + the two param keys read by more than one builder
  (``field_overlay`` is the scope AND fields source; ``scope_dimensions`` is still imported by
  :mod:`services._projection_scopegrant`);
- :func:`_enum_values_from_field` — the single scope/enum vocabulary extractor used by both the
  scope builder and the fixed-override mapper;
- the row-version helpers (:func:`_scope_config_version` / :func:`_config_row_version`) every
  builder calls — including the version-bump-trap fix.

The facade :mod:`services._projection_config_builders` re-exports every public-and-private name
listed in its ``__all__``, so ``from services._projection_config_builders import
_MEMBERS_PARAM_NAMESPACE`` (and friends) keeps resolving unchanged after the split.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from services.projection_builder import _normalize_version

# --- Shared parameter identity -------------------------------------------------

#: Parameter namespace that carries the Members module's tenant-scope config
#: data (S5b design.md C2). Tenant Admin authors these via
#: ``ParameterService.set_param(scope="tenant", namespace="members", ...)``
#: (``/api/tenant-admin/parameters``); the ``members.*`` namespace is gated to
#: the active MEMBERS module (``parameter_schema.py``). The builder only READS
#: these — it never writes MySQL (Property 1, one-directional).
_MEMBERS_PARAM_NAMESPACE = "members"

#: The single tenant-scope parameter key that holds the scope-dimension
#: definitions as a JSON list, one entry per dimension. Authored by Tenant Admin
#: (region values Noord/Zuid/Oost/West etc.); read here and mapped 1:1 to the
#: ``config#scope`` row's ``dimensions`` shape that
#: ``sam/members/domain/scope_dimensions.py`` ``ScopeDimension`` consumes.
_SCOPE_DIMENSIONS_PARAM_KEY = "scope_dimensions"

#: The single tenant-scope parameter key that holds the Members field-config
#: overlay as a JSON object with two members-authored maps — ``fields`` (the
#: variable overlay: added "club detail" fields) and ``overrides`` (presentation
#: overrides of fixed fields). Authored by Tenant Admin (same
#: ``/api/tenant-admin/parameters`` surface as ``scope_dimensions``); read here
#: and mapped 1:1 to the ``config#fields`` row's ``fields``/``overrides`` shape
#: that ``sam/members/domain/field_resolver.py`` ``TenantOverlay`` consumes
#: (``TenantOverlay.fields`` = added ``OverlayField``s keyed by canonical key;
#: ``TenantOverlay.overrides`` = ``FixedFieldOverride``s keyed by canonical dotted
#: key ``group.field``). The ``members.*`` namespace declaration/gating to the
#: active MEMBERS module is a later ``[H]`` task (11.x, ``parameter_schema.py``);
#: this builder only READS whatever value exists (Property 1, one-directional).
_FIELD_OVERLAY_PARAM_KEY = "field_overlay"


def _enum_values_from_field(spec: Mapping[str, Any]) -> list[str] | None:
    """Extract a field's ENUM VALUES — the single scope vocabulary (R3.4).

    The single-vocabulary rule (R3.2/R3.4): a scope-axis field's dimension values ARE the
    field's own enum values. They are read from the field's enum vocabulary, in priority
    order:

    - rich ``options`` — a list of ``{value, label?, roles?}`` dicts (or bare strings): the
      per-option ``value`` (or the bare string) is the vocabulary;
    - a bare ``choices`` string list.

    Returns the ordered, de-duplicated list of non-blank string values, or ``None`` when the
    field declares no usable enum vocabulary (not an enum / value-less) — the caller treats
    ``None`` as "no enum vocabulary", which is a validation error at save for an ENABLED
    scope axis (R3.4).
    """

    def _collect_values(raw: Any) -> list[str] | None:
        if not isinstance(raw, (list, tuple)):
            return None
        values: list[str] = []
        seen: set[str] = set()
        for entry in raw:
            if isinstance(entry, Mapping):
                value = entry.get("value")
            else:
                value = entry
            if not isinstance(value, str) or not value.strip():
                continue
            if value in seen:
                continue
            seen.add(value)
            values.append(value)
        return values or None

    # Rich `options` first (the canonical enum vocabulary), then bare `choices`.
    return _collect_values(spec.get("options")) or _collect_values(spec.get("choices"))


# Version fields the builder reads off the tenant row for the config#scope item,
# in priority order — mirrors projection_builder._VERSION_FIELDS. A row with none
# gets a deterministic 0 so the item is well-formed and re-sync is idempotent.
_SCOPE_VERSION_FIELDS = ("version", "updated_at", "revision", "modified_at")


def _scope_config_version(tenant: Mapping[str, Any]) -> Any:
    """Return the first present, non-null version field on the tenant row, else 0.

    Deterministic (no clock read) so a re-sync on unchanged input reproduces the
    same version — preserving the sync's idempotent/versioned write (R5.6). The
    tenant row's revision is used because ``config#scope`` is tenant-level; a more
    precise per-parameter version can supersede it once the trigger (task 6.x)
    threads a param-change revision through.
    """
    for name in _SCOPE_VERSION_FIELDS:
        value = tenant.get(name)
        if value is not None:
            return _normalize_version(value)
    return 0


def _config_row_version(
    tenant: Mapping[str, Any],
    parameter_service: Any,
    tenant_id: str,
    param_keys: Sequence[str],
) -> Any:
    """Version a ``config#*`` row off its SOURCE param(s), not just the tenant row.

    THE VERSION-BUMP TRAP FIX (impact-analysis §0.3 / Phase 0 step 2). The
    ``config#*`` rows are written under the sync's VERSION-GUARDED conditional put
    (``_supersedes`` / the ``#v < :incoming`` condition), which writes only when the
    incoming ``version`` STRICTLY supersedes the stored one. Deriving that version
    from the TENANT row alone (:func:`_scope_config_version`) is the bug: editing a
    ``members.*`` param (e.g. ``field_overlay``) does NOT bump the tenant row, so the
    projected row keeps the same version, the conditional put SKIPS it, and the edit
    never reaches DynamoDB (``written=0 skipped=N`` — the #6/#7/#8 "config won't save"
    symptom). The historic workaround was to hand-bump ``tenants.updated_at``.

    FIX — version off the PARAM's own ``updated_at`` (``parameters`` table,
    ``ON UPDATE CURRENT_TIMESTAMP``) when it is present, exactly as
    :func:`services._projection_scopegrant._scopegrant_version` already does for
    per-user grants (same freshness mechanism, same monotonic ISO-8601 ordering via
    :func:`_normalize_version`):

    - (a) **advances on a param edit** — the edited param's ``updated_at`` moves
      forward, so the new version strictly supersedes the stored one and the put
      writes (the edit propagates — the trap is gone);
    - (b) **is stable on an unchanged re-sync** — an untouched param reproduces the
      SAME ``updated_at`` → same version → the conditional put is a no-op (idempotence
      preserved, no version churn, R5.6);
    - (c) **fits the existing plumbing** — ``_normalize_version`` renders the
      ``datetime`` to an ISO-8601 string that sorts lexicographically in chronological
      order, a valid monotonic version for BOTH the write conditional put and the
      read-side staleness check.

    When a row is driven by MORE THAN ONE param (``config#mail`` reads four keys), the
    MAX param revision wins so an edit to ANY of them bumps the row. Param revisions
    are compared only against each other (all ISO-8601 strings — safely ordered); the
    tenant-row version is used ONLY as the fallback when NO param in ``param_keys`` has
    a per-param revision (an un-authored row, or a source — e.g. a test fixture — that
    exposes no ``get_param_revision``). This mirrors ``_scopegrant_version``: never mix
    a param ISO timestamp and an int tenant ``version`` in one comparison.

    One-directional discipline (Property 1): only READS — ``get_param_revision`` issues
    a plain SELECT; this helper never writes MySQL.
    """
    revisions: list[Any] = []
    getter = getattr(parameter_service, "get_param_revision", None)
    if callable(getter):
        for key in param_keys:
            revision = getter(_MEMBERS_PARAM_NAMESPACE, key, tenant=tenant_id)
            if revision is not None:
                revisions.append(_normalize_version(revision))
    if revisions:
        return max(revisions)
    return _scope_config_version(tenant)
