"""Governance projection — tenant-level ``config#*`` row builders (extracted from
``projection_sync`` for cohesion).

The pure, read-only builders that shape a tenant's authored ``members.*`` tenant-scope
parameters into the ``config#scope`` / ``config#fields`` / ``config#mail`` projection
rows the SAM/Lambda module plane reads (S5b design.md C2). They are
re-exported from :mod:`services.projection_sync`; its public import surface is unchanged.

One-directional discipline (Property 1): every builder here issues **zero** MySQL writes
and does **not** write the projection itself — it only READS via ``ParameterService``
(read-only ``get_param``) and RETURNS the item for the sole writer
(:class:`services.projection_sync.ProjectionSync`). This is a pure structural split
(code-quality M2) with zero behaviour change.

Module layout (code-quality file-length split, 2026-10-28)
----------------------------------------------------------
This module crossed 1000 lines, so the three row builders were split into cohesive
per-row sub-modules with **zero behaviour change**. This file is now the **stable facade**:
its full import surface (every name in ``__all__`` below — the three public ``build_*``
functions AND the private helpers/constants that siblings such as
:mod:`services._projection_scopegrant` and the one-off migration scripts import) is
preserved and re-exported here, so ``from services._projection_config_builders import …``
keeps resolving exactly as before.

- :mod:`services._projection_config_common` — shared primitives: the ``members.*`` namespace,
  the ``field_overlay`` / ``scope_dimensions`` param keys, :func:`_enum_values_from_field`,
  and the row-version helpers (:func:`_scope_config_version` / :func:`_config_row_version`).
- :mod:`services._projection_scope_builder` — the ``config#scope`` builder + its dimension
  mapping and scope-as-field-attribute derivation.
- :mod:`services._projection_fields_builder` — the ``config#fields`` builder + its overlay /
  fixed-override / functional-group mappers and the default-page-size resolver.
- :mod:`services._projection_mail_builder` — the ``config#mail`` builder + the mail param
  keys and the consent-notice shaper.
"""

from __future__ import annotations

from services._projection_config_common import (
    _FIELD_OVERLAY_PARAM_KEY,
    _MEMBERS_PARAM_NAMESPACE,
    _SCOPE_DIMENSIONS_PARAM_KEY,
    _SCOPE_VERSION_FIELDS,
    _config_row_version,
    _enum_values_from_field,
    _scope_config_version,
)
from services._projection_fields_builder import (
    _DEFAULT_PAGE_SIZE_PARAM_KEY,
    _FIXED_OVERRIDE_FIELDS,
    _FUNCTIONAL_GROUP_FIELDS,
    _OVERLAY_FIELD_DEFAULTS,
    _map_fixed_override,
    _map_functional_group,
    _map_overlay_field,
    _resolve_default_page_size,
    build_config_fields_row,
)
from services._projection_mail_builder import (
    _APPLICATION_CONSENT_NOTICE_PARAM_KEY,
    _APPLICATION_SCOPE_COPY_PARAM_KEY,
    _MAIL_CERTIFIED_PARAM_KEY,
    _MAIL_DOMAIN_PARAM_KEY,
    _MAIL_ENABLED_PARAM_KEY,
    _MAIL_LOCAL_PART_DEFAULT,
    _MAIL_LOCAL_PART_PARAM_KEY,
    _MAIL_REPLY_TO_DEFAULT_PARAM_KEY,
    _resolve_application_consent_notice,
    build_config_mail_row,
)
from services._projection_scope_builder import (
    _DIMENSION_DEFAULTS,
    _FIELD_SCOPE_ATTR,
    _map_scope_dimension,
    _scope_dimension_from_field,
    _scope_dimensions_from_overlay,
    build_config_scope_row,
)

__all__ = [
    "_APPLICATION_CONSENT_NOTICE_PARAM_KEY",
    "_APPLICATION_SCOPE_COPY_PARAM_KEY",
    "_DEFAULT_PAGE_SIZE_PARAM_KEY",
    "_DIMENSION_DEFAULTS",
    "_FIELD_OVERLAY_PARAM_KEY",
    "_FIELD_SCOPE_ATTR",
    "_FIXED_OVERRIDE_FIELDS",
    "_FUNCTIONAL_GROUP_FIELDS",
    "_MAIL_CERTIFIED_PARAM_KEY",
    "_MAIL_DOMAIN_PARAM_KEY",
    "_MAIL_ENABLED_PARAM_KEY",
    "_MAIL_LOCAL_PART_DEFAULT",
    "_MAIL_LOCAL_PART_PARAM_KEY",
    "_MAIL_REPLY_TO_DEFAULT_PARAM_KEY",
    "_MEMBERS_PARAM_NAMESPACE",
    "_OVERLAY_FIELD_DEFAULTS",
    "_SCOPE_DIMENSIONS_PARAM_KEY",
    "_SCOPE_VERSION_FIELDS",
    "_config_row_version",
    "_enum_values_from_field",
    "_map_fixed_override",
    "_map_functional_group",
    "_map_overlay_field",
    "_map_scope_dimension",
    "_resolve_application_consent_notice",
    "_resolve_default_page_size",
    "_scope_config_version",
    "_scope_dimension_from_field",
    "_scope_dimensions_from_overlay",
    "build_config_fields_row",
    "build_config_mail_row",
    "build_config_scope_row",
]
