"""
s5c Task 2.4 — authoritative save-time validation for the ``members.*`` parameters
(Flask/MySQL plane; design C-SCHEMA / C-VIEW, Property 7 fail-fast).

This is the Flask-plane guard that runs on a PUT of a ``members.*`` parameter *before*
the value is stored, so a bad config never corrupts the projected tenant config:

- **``members.field_overlay``** — reuses the SAM-domain ``FieldResolver._reject_invalid_overlay``
  semantics (fail-fast): reject an override of an unknown field key, a variable field colliding
  with a fixed/calculated key, an enum variable field with no choices, and — the s5c addition
  (R4.9) — any ``functional_group`` (on a fixed override or a variable field) that is not present
  in the tenant's ``functional_groups`` catalog. It also rejects loosening a platform-required
  fixed field (optional-only tightening).

Cross-plane reuse decision (task 2.4 guidance)
----------------------------------------------
The task asks us to *prefer reuse* of the SAM-domain resolver, and to reimplement the minimal
equivalent (referencing the same contract) only if a cross-plane import is not clean. **We
reimplement here**, because:

- The two planes are independently deployed and packaged: the Flask/MySQL app (``backend/src``,
  Railway) and the SAM module (``sam/members``, Lambda) have **separate** Python paths, pytest
  configs, and dependency trees. ``backend/src`` does not (and must not) place ``sam`` on its
  import path — importing ``sam.members.domain.field_resolver`` into the Flask runtime would
  couple the Railway service to the Lambda package and drag SAM's dependencies into Flask.
- The projection layer already re-expresses these same overlay/scope shapes on the Flask plane
  (``projection_sync.py`` reads ``members.*`` and builds ``config#fields`` / ``config#scope``);
  a small, self-contained validator here is consistent with that boundary.

To keep the two implementations honest, the platform base field-key set below is a **direct
transcription** of the canonical keys in ``sam/members/domain/fixed_fields.py`` +
``calculated_fields.py`` (the single source of truth for field names). The rejection is
fail-fast with a descriptive :class:`MembersConfigError` (mirroring ``OverlayError`` /
``FieldValidationError``) and never mutates or stores the config.

Module layout (code-quality 2026-10-28 task 10 — pure structural split)
-----------------------------------------------------------------------
This module is the stable PUBLIC FACADE. The implementation is split across three cohesive
sub-modules, all re-exported here so the import surface
(``from services.members_config_validation import …``) is unchanged:

- ``_members_config_fields`` — :class:`MembersConfigError`, the platform base field-key /
  format-token sets, and :func:`validate_field_overlay` (+ its scope / application-attr
  helpers).
- ``_members_config_scalars`` — the scalar-param validators (mail config, application
  params, ``default_page_size``).
- ``_members_config_labels`` — :func:`fold_field_overlay_labels` (the per-locale label fold).

The two dispatch entry points (:func:`validate_members_param`, :func:`fold_members_param`)
that the parameter save path calls live here, keyed by ``members.<key>``.
"""

from __future__ import annotations

from typing import Any

from services._members_config_fields import (
    CALCULATED_FIELD_KEYS,
    FIXED_FIELD_KEYS,
    OVERLAY_GROUP,
    PLATFORM_FORMAT_TOKENS,
    MembersConfigError,
    validate_field_overlay,
)
from services._members_config_labels import fold_field_overlay_labels
from services._members_config_scalars import (
    validate_application_consent_notice,
    validate_application_scope_copy,
    validate_default_page_size,
    validate_mail_certified,
    validate_mail_domain,
    validate_mail_local_part,
)

__all__ = [
    "CALCULATED_FIELD_KEYS",
    "FIXED_FIELD_KEYS",
    "OVERLAY_GROUP",
    "PLATFORM_FORMAT_TOKENS",
    "MembersConfigError",
    "fold_field_overlay_labels",
    "fold_members_param",
    "validate_application_consent_notice",
    "validate_application_scope_copy",
    "validate_default_page_size",
    "validate_field_overlay",
    "validate_mail_certified",
    "validate_mail_domain",
    "validate_mail_local_part",
    "validate_members_param",
]


# ── save-path label fold dispatch ──────────────────────────────────────────────────────


def fold_members_param(key: str, value: Any) -> Any:
    """Fold per-locale label inputs for one ``members.<key>`` value on save (R3.2).

    The save-path pre-store transform companion to :func:`validate_members_param`: for the
    keys whose authored shape carries tenant labels (currently ``field_overlay``), assemble
    the editor's per-locale ``label_<locale>`` inputs into the stored inline ``{nl,en,…}``
    dict. For every other key the value is returned unchanged. Never mutates the input;
    returns the value to store.
    """
    if key == "field_overlay":
        return fold_field_overlay_labels(value)
    return value


# ── dispatch entry point used by the parameter save path ───────────────────────────────


def validate_members_param(
    key: str,
    value: Any,
) -> None:
    """Validate one ``members.<key>`` value on save; no-op for keys with no save-time rule.

    Dispatches to the per-key validator:
    - ``field_overlay``    → :func:`validate_field_overlay`
    - ``mail_domain``       → :func:`validate_mail_domain`
    - ``mail_local_part``   → :func:`validate_mail_local_part`
    - ``mail_certified``    → :func:`validate_mail_certified`
    - ``application_scope_copy``     → :func:`validate_application_scope_copy`
    - ``application_consent_notice`` → :func:`validate_application_consent_notice`
    - ``default_page_size`` → :func:`validate_default_page_size`

    ``scope_dimensions`` has no cross-reference rule of its own here (its internal shape is
    validated by the SAM ``ScopeConfig`` on read); a PUT of it is accepted as-is. Raises
    :class:`MembersConfigError` on any violation; returns None otherwise.
    """
    if key == "field_overlay":
        validate_field_overlay(value)
    elif key == "mail_domain":
        validate_mail_domain(value)
    elif key == "mail_local_part":
        validate_mail_local_part(value)
    elif key == "mail_certified":
        validate_mail_certified(value)
    elif key == "application_scope_copy":
        validate_application_scope_copy(value)
    elif key == "application_consent_notice":
        validate_application_consent_notice(value)
    elif key == "default_page_size":
        validate_default_page_size(value)
