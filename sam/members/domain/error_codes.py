"""Shared field-error vocabulary for the platform API response & error standard v1.0.

This module is the **single source of truth** for the machine-readable error *codes* the
Members domain layer emits, plus the :class:`FieldError` value that carries one RFC 9457
(``application/problem+json``) per-entry detail through the domain → handler → frontend chain.

Why a value object and not a bare string
-----------------------------------------
Before v1.0 the domain validators returned free English strings (``"is required"``,
``"must be one of: A, B"``). Those cannot be localized and forced the frontend to
string-sniff. The standard replaces each string with a :class:`FieldError` carrying:

- ``code``   — a **machine** identifier that is *also* an i18n key in the EXISTING
  ``errors``/``validation`` namespaces (see ``TRANSLATION_KEY_CONVENTIONS.md``). The frontend
  resolves it with ``t(code, params)``; no new namespace is invented.
- ``params`` — optional interpolation values for the i18n template (e.g. ``{"allowed": ...}``
  for ``validation.mustBeOneOf``). ``None`` when the message takes no parameters.
- ``detail`` — the **human English fallback** (the message the old code returned). It is kept
  so nothing is lost: when a client cannot resolve ``code`` it degrades to this text.

The handler later reshapes the domain's ``{field: FieldError}`` map into the RFC 9457 array
``errors: [{field, code, params?, detail}, …]`` (task 3.5); this module owns only the per-entry
*vocabulary*, not the transport shape.

Codes are keys in the EXISTING ``errors`` namespace — do NOT invent a namespace
-------------------------------------------------------------------------------
Every code below is a key in the frontend's ``errors`` namespace (``frontend/src/locales/{en,nl}/
errors.json``), resolved as ``t('errors:<path>', params)`` (the ``namespace:path`` form the i18n
tests already use, e.g. ``i18n.exists('errors:api.networkError')``). Field-level validation codes
live under that namespace's ``validation`` category (``errors.validation.*``) — the single home
that already hosts flat string leaves — rather than the standalone ``validation`` namespace file
(whose keys are grouped objects with no home for a flat leaf). New keys added by v1.0 are created
in ``errors.json`` by task 3.7; this module just names them (camelCase leaf, per the conventions).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

__all__ = [
    "FieldError",
    # field-level validation codes (validation.* namespace)
    "VALIDATION_REQUIRED",
    "VALIDATION_MUST_NOT_BE_BLANK",
    "VALIDATION_MUST_BE_A_STRING",
    "VALIDATION_MUST_BE_ONE_OF",
    "VALIDATION_INVALID_DATE",
    "VALIDATION_UNSUPPORTED_FIELD_TYPE",
    # field-level domain codes (errors.* namespace)
    "MEMBER_NUMBER_FORMAT",
    "ENUM_ROLE_RESTRICTED",
    "MEMBERSHIP_TYPE_TENANT",
    "MEMBERSHIP_TYPE_TYPE_CODE",
    "MEMBERSHIP_TYPE_LABEL",
    "MEMBERSHIP_TYPE_ORDER",
    "MEMBERSHIP_TYPE_UNKNOWN_REFERENCE",
    "MEMBERSHIP_TYPE_RETIRED",
    "ANALYTICS_SET_TENANT",
    "ANALYTICS_SET_ID",
    "ANALYTICS_SET_NAME",
    "ANALYTICS_SET_KIND",
    "ANALYTICS_SET_DEFINITION",
    "ANALYTICS_SET_ORIGIN",
    "ANALYTICS_SET_DELIVERY",
    "TEMPLATE_TENANT",
    "TEMPLATE_ID",
    "TEMPLATE_NAME",
    "TEMPLATE_LANGUAGES",
    "TEMPLATE_MERGE_FIELDS",
    "TEMPLATE_ORIGIN",
    "SCHEDULE_TENANT",
    "SCHEDULE_ID",
    "SCHEDULE_SET",
    "SCHEDULE_CRON",
    "SCHEDULE_ENABLED",
    "PREF_LIST_TENANT",
    "PREF_LIST_SUB",
    "PREF_LIST_REFS",
    "COLUMN_PREFS_TENANT",
    "COLUMN_PREFS_SUB",
    "COLUMN_PREFS_COLUMNS",
]


@dataclass(frozen=True)
class FieldError:
    """One RFC 9457 per-entry problem detail: a machine ``code`` + human ``detail``.

    Instances are frozen (immutable) so an error value can be shared/reused safely. ``params``
    is optional interpolation for the i18n template keyed by ``code``; keep it ``None`` when the
    message is parameter-free. ``detail`` is the English fallback (the pre-v1.0 message text) —
    it MUST always be a complete, human-readable sentence so a client that cannot resolve the
    code still shows something meaningful.

    This value is namespace-agnostic about transport: the domain puts it in a ``{field: FieldError}``
    map (keyed by dotted field key), and the handler flattens it to the ``{field, code, params?,
    detail}`` RFC 9457 array entry (task 3.5).
    """

    code: str
    detail: str
    params: Mapping[str, Any] | None = field(default=None)

    def as_entry(self, *, field_key: str | None = None) -> dict[str, Any]:
        """Render this error as an RFC 9457 per-entry dict.

        ``field_key`` (the dotted field path) is included as ``field`` when supplied — the
        handler passes it when flattening a ``{field: FieldError}`` map into the ``errors``
        array; a bare ``reasons`` entry omits it. ``params`` is included only when set, so a
        parameter-free entry stays ``{code, detail}`` (or ``{field, code, detail}``).
        """
        entry: dict[str, Any] = {"code": self.code, "detail": self.detail}
        if field_key is not None:
            entry = {"field": field_key, **entry}
        if self.params is not None:
            entry["params"] = dict(self.params)
        return entry


# ── Field-level validation codes — keys in the EXISTING ``errors`` namespace, ``validation``
#    category (``errors.validation.*``) ──────────────────────────────────────────────────
#
# These name a *single field's* rule failure. They live under the ``errors`` namespace's
# ``validation`` category (``errors.json`` → ``validation.*``), NOT the standalone ``validation``
# namespace file: that file groups keys under sub-objects (``required.field``, ``format.email``),
# where a flat leaf like ``mustNotBeBlank`` has no home and ``required`` is an OBJECT (unresolvable
# as a string). ``errors.validation`` already hosts flat string leaves (``required``,
# ``invalidFormat``, …) — the natural, single-namespace home (resolved ``t('errors:validation.x')``,
# mirroring ``errors.api.*``). ``VALIDATION_REQUIRED`` / ``VALIDATION_UNSUPPORTED_FIELD_TYPE`` reuse
# pre-existing ``errors.validation`` strings; the rest are added to the locale files by task 3.7.

#: A required field was absent/null. **Reused** existing ``errors.validation.required`` string.
#: NOTE: the coupled prune in ``membership_service._drop_hidden_required_errors`` compares against
#: THIS constant (task 3.3), replacing the old ``== "is required"`` string check — keep in sync.
VALIDATION_REQUIRED = "errors.validation.required"

#: A required string/reference field was present but blank/whitespace.
VALIDATION_MUST_NOT_BE_BLANK = "errors.validation.mustNotBeBlank"

#: A string/reference/open-enum field received a non-string (or blank open-enum) value.
VALIDATION_MUST_BE_A_STRING = "errors.validation.mustBeAString"

#: A closed-enum value was not in the allowed set. ``params`` carries ``{"allowed": [...]}``.
VALIDATION_MUST_BE_ONE_OF = "errors.validation.mustBeOneOf"

#: A date field was not a valid ISO-8601 (YYYY-MM-DD) calendar date. Both old date messages map
#: here (``detail`` keeps the specific English wording).
VALIDATION_INVALID_DATE = "errors.validation.invalidDate"

#: Defensive: an unknown field type in the registry (a programming error, not user input).
#: Surfaces under the existing generic ``errors.validation.invalidFormat`` key.
VALIDATION_UNSUPPORTED_FIELD_TYPE = "errors.validation.invalidFormat"


# ── Field-level domain codes — keys in the EXISTING ``errors.*`` i18n namespace ──────────
#
# These name Members-domain-specific field failures (member number, role-gated enum, catalog).
# Added to the locale files by task 3.7.

#: A present ``member_number`` was blank or violated the tenant format pattern. ``params`` may
#: carry ``{"example": ...}`` or ``{"pattern": ...}`` for the format hint.
MEMBER_NUMBER_FORMAT = "errors.member.numberFormat"

#: An overlay enum value is allowed only for roles the caller lacks. ``params`` carries
#: ``{"roles": [...]}`` (the roles that MAY set the value).
ENUM_ROLE_RESTRICTED = "errors.enum.roleRestricted"

#: A membership-type catalog entry has an invalid/blank ``tenant_id`` (tenant-isolation hazard).
MEMBERSHIP_TYPE_TENANT = "errors.membershiptype.tenant"

#: A membership-type catalog entry has an invalid/blank ``type_code``.
MEMBERSHIP_TYPE_TYPE_CODE = "errors.membershiptype.typeCode"

#: A membership-type catalog entry has an invalid/blank ``label``.
MEMBERSHIP_TYPE_LABEL = "errors.membershiptype.label"

#: A membership-type catalog entry has an invalid ``order`` (non-integer / negative).
MEMBERSHIP_TYPE_ORDER = "errors.membershiptype.order"

#: A member references a ``membership_type`` code that is not in the tenant catalog.
#: ``params`` carries ``{"type_code": ...}``.
MEMBERSHIP_TYPE_UNKNOWN_REFERENCE = "errors.membershiptype.unknownReference"

#: A member references a ``membership_type`` that exists but is retired (``active=false``).
#: ``params`` carries ``{"type_code": ...}``.
MEMBERSHIP_TYPE_RETIRED = "errors.membershiptype.retired"


# ── Analytics-set field-level domain codes — keys in the EXISTING ``errors.*`` namespace ──
#
# Analytics-set (member saved-set) validation codes. Mirror the membership-type catalog block:
# one code per validated field. A set's ``definition`` is a mapping (the frontend ``PivotConfig``
# in snake_case); group_columns and aggregate_measures may be EMPTY (a filtered-list set, F-011).

#: An analytics-set entry has an invalid/blank ``tenant_id`` (tenant-isolation hazard).
ANALYTICS_SET_TENANT = "errors.analyticsset.tenant"

#: An analytics-set entry has an invalid/blank ``set_id``.
ANALYTICS_SET_ID = "errors.analyticsset.id"

#: An analytics-set entry has an invalid/blank ``name``.
ANALYTICS_SET_NAME = "errors.analyticsset.name"

#: An analytics-set entry has an invalid ``kind`` (must be ``'count'`` or ``'list'``).
ANALYTICS_SET_KIND = "errors.analyticsset.kind"

#: An analytics-set entry has an invalid ``definition`` (must be a mapping).
ANALYTICS_SET_DEFINITION = "errors.analyticsset.definition"

#: An analytics-set entry has an invalid ``origin`` (must be ``'user'`` or ``'predefined'``).
ANALYTICS_SET_ORIGIN = "errors.analyticsset.origin"

#: An analytics-set entry has an invalid optional ``delivery`` block (R3): a bad ``mode``, a
#: ``to_fixed`` mode missing its ``recipients`` list, a ``per_recipient`` mode carrying stored
#: recipients, or a malformed shape. ``params`` may carry ``{"allowed": [...]}`` for a bad mode.
ANALYTICS_SET_DELIVERY = "errors.analyticsset.delivery"


# ── Template field-level domain codes (R2 — stored mail templates, on-plane) ──────────────
#
# Mail-template (R2) validation codes. Mirror the analytics-set block: one code per validated
# field. A template's metadata lives on-plane (``template#<id>``); its body HTML + logo binaries
# live in S3 (never inline — 400 KB + binary). The entity is written module-agnostic (no
# member-specific logic) so it can extract to ``sam/shared/templates/`` on a second consumer
# (steering 35 rule of three) — hence a neutral ``errors.template.*`` namespace, NOT
# ``errors.member*``.

#: A template entry has an invalid/blank ``tenant_id`` (tenant-isolation hazard).
TEMPLATE_TENANT = "errors.template.tenant"

#: A template entry has an invalid/blank ``template_id`` (also a sort-key id segment).
TEMPLATE_ID = "errors.template.id"

#: A template entry has an invalid/blank ``name``.
TEMPLATE_NAME = "errors.template.name"

#: A template entry has invalid ``languages`` (must be a mapping of lang → {subject, body key},
#: with at least one language present and each entry carrying a non-blank subject + body key).
TEMPLATE_LANGUAGES = "errors.template.languages"

#: A template entry has invalid ``merge_fields`` (must be a list of non-blank field-key strings).
TEMPLATE_MERGE_FIELDS = "errors.template.mergeFields"

#: A template entry has an invalid ``origin`` (must be ``'user'`` or ``'preset'``).
TEMPLATE_ORIGIN = "errors.template.origin"


# ── Schedule field-level domain codes (R5 — scheduled execution of a set + delivery) ──────
#
# Scheduled-run (R5) validation codes. Mirror the analytics-set / template blocks: one code
# per validated field. A schedule's metadata lives on-plane (``schedule#<id>``) and names the
# analytics-set to run on a cron/rate expression. The entity is STORAGE-ONLY — the "only
# schedulable if the set has a delivery block" rule is a SERVICE/route gate (task 5.2), not an
# entity concern — so a neutral ``errors.schedule.*`` namespace (no member-specific logic),
# mirroring the analyticsset/template namespaces.

#: A schedule entry has an invalid/blank ``tenant_id`` (tenant-isolation hazard). The tenant is
#: PINNED in the schedule (R5 — an unattended run has no interactive user).
SCHEDULE_TENANT = "errors.schedule.tenant"

#: A schedule entry has an invalid/blank ``schedule_id`` (also a sort-key id segment).
SCHEDULE_ID = "errors.schedule.id"

#: A schedule entry has an invalid/blank ``set_id`` (the analytics-set the schedule runs).
SCHEDULE_SET = "errors.schedule.set"

#: A schedule entry has an invalid/blank ``cron`` (the EventBridge Scheduler schedule
#: expression — a ``cron(...)`` / ``rate(...)`` / ``at(...)`` expression; validated as a
#: non-blank string here, the exact grammar is enforced by the scheduler at task 5.3).
SCHEDULE_CRON = "errors.schedule.cron"

#: A schedule entry has an invalid ``enabled`` (must be a bool).
SCHEDULE_ENABLED = "errors.schedule.enabled"


# ── Preferred-list field-level domain codes (R11.2 — per-user analytics-set preferred list) ──

#: A preferred-list entry has an invalid/blank ``tenant_id`` (tenant-isolation hazard).
PREF_LIST_TENANT = "errors.preflist.tenant"

#: A preferred-list entry has an invalid/blank ``sub`` (the owning user principal).
PREF_LIST_SUB = "errors.preflist.sub"

#: A preferred-list entry has invalid ``refs`` (must be a list of non-blank reference strings).
PREF_LIST_REFS = "errors.preflist.refs"


# ── Column-preferences field-level domain codes (session-columns R6 — per-user column set) ──
#
# Mirror the preferred-list block 1:1 (``columns`` ↔ ``refs``). A column-preferences record is a
# user's PRIVATE, per-user, tenant-scoped ordered list of field-config column keys.

#: A column-preferences entry has an invalid/blank ``tenant_id`` (tenant-isolation hazard).
COLUMN_PREFS_TENANT = "errors.colprefs.tenant"

#: A column-preferences entry has an invalid/blank ``sub`` (the owning user principal).
COLUMN_PREFS_SUB = "errors.colprefs.sub"

#: A column-preferences entry has invalid ``columns`` (must be a list of non-blank field keys).
COLUMN_PREFS_COLUMNS = "errors.colprefs.columns"
