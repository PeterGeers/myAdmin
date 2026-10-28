"""
S5b Task 8.1 — the Members module **projection config reader** (design C4).

A read-only, ``boto3``-backed consumer of the S3/S5b governance projection that feeds the
S5 Members domain seams with **real projected data**. It mirrors
:mod:`sam.pretokengen.projection_governance_reader` exactly — one DynamoDB ``Query`` per
tenant partition, a per-invocation cache so a partition is read at most once, fail-fast
table resolution via :mod:`services.projection_schema`, and *empty-is-valid* everywhere —
but reconstructs the **S5b** projected rows (``config#scope`` / ``config#fields`` /
``scopegrant#<email>#<dimension>``) into the storage-agnostic domain shapes the UNCHANGED
domain consumes.

Why this exists (design C4)
---------------------------
The S5 domain (``scope_dimensions`` / ``field_resolver`` / ``scope_access``) is deliberately
storage-agnostic: it depends on two ``Protocol`` seams —
:class:`sam.members.domain.scope_dimensions.ScopeConfigProvider` and
:class:`sam.members.domain.field_resolver.TenantOverlayProvider` — never on where the config
lives. S5 shipped in-memory ``Static*`` providers as the reference. This reader is the
SAM-plane concrete provider that replaces them (task 8.2 wires it into cold start): it reads
the projection the S5b builders (tasks 5.1/5.2/5.3) populate and returns exactly the domain
dataclasses those seams expect, so it can be handed straight to ``FieldResolver`` /
``resolve_scope_access`` (duck-typed to the Protocols). It **reads only** — it never writes
MySQL or the projection.

Layering
--------
SAM-plane **infrastructure adapter**: it depends on ``boto3`` + the projection schema and
produces the domain shapes. The domain never imports it (dependency inversion — the arrow
points inward, exactly like ``FieldConfigMixin`` → ``parameter_service`` in the Flask plane).

Projected row shapes consumed (built by tasks 5.1/5.2/5.3)
----------------------------------------------------------
- ``config#scope``: ``dimensions`` = list of dicts (``key``/``field``/``label``/``enabled``/
  ``values``/``required_for``) → mapped 1:1 onto
  :class:`ScopeDimension`; the whole row → :class:`ScopeConfig`. A **missing row** →
  ``ScopeConfig(tenant_id, dimensions=())`` (tenant-wide), never an error (R1.6).
- ``config#fields``: ``fields`` = ``{name: {key,type,required,label,choices,visible,order}}``
  and ``overrides`` = ``{dotted: {label?,visible?,required?,order?}}`` →
  :class:`TenantOverlay`. The projected ``type`` is a *string*; it is converted to
  :class:`FieldType` (unknown/missing → :data:`FieldType.STRING`). A ``FixedFieldOverride``
  only carries the aspects actually present (a missing aspect stays ``None`` → "leave the
  base as-is"). A **missing row** → ``TenantOverlay()`` (fixed base only), never an error
  (R1.7).
- ``scopegrant#<email>#<dimension>``: ``dimension`` (str), ``values`` (list[str], or
  ``["*"]`` for all-access). :meth:`get_scope_grants` returns ``{dimension: values}`` for the
  **caller's** rows only — filtered by the email segment of the SK, mirroring how
  ``ProjectionGovernanceReader.get_user_roles_by_tenant`` filters ``role#<email>#<role>`` rows
  by ``id_parts[0] == email``. A missing grant is simply **absent** from the map (the edge
  then applies deny-by-default via ``required_for`` — R2.6).

Config + fail-fast (R4.1)
-------------------------
The table name is resolved from ``GOVERNANCE_PROJECTION_TABLE`` via the S3 fail-fast client
(:func:`services.projection_schema.get_projection_table_resource`) — missing/blank throws,
no dangerous default, resolved lazily on first real Query. In production the Lambda's IAM
role grants read on the projection table; ``AWS_ENDPOINT_URL_DYNAMODB`` is left UNSET (real
AWS) and only set for local testing against the T0 ``dynamodb-local`` container.

Module layout (code-quality file-length split, 2026-10-28)
----------------------------------------------------------
This file crossed 1000 lines, so the one reader class was split into cohesive mixins with
**zero behaviour change** — the public import surface is UNCHANGED
(``from sam.members.repository.projection_config_reader import MembersProjectionReader``),
and every method (including the field-build static methods such as
``MembersProjectionReader._build_override`` that tests / the Change-Op CRUD service call)
stays reachable as an attribute of the composed class:

- :mod:`sam.members.repository._config_reader_base` — shared read infrastructure
  (:class:`_ConfigReaderBase`): table resolution, the per-invocation partition cache,
  sort-key classification, the ``config#<id>`` row lookup, and the projection-staleness
  (``version``) surface; plus :func:`_normalize_functional_groups` and the ``config#<id>``
  token constants.
- :mod:`sam.members.repository._scope_reader` — the ``ScopeConfigProvider`` + scope-grant
  reads (:class:`_ScopeReadMixin`).
- :mod:`sam.members.repository._fields_overlay_reader` — the ``TenantOverlayProvider`` +
  authoring-wire + page-size/slug/version reads and the field-build helpers
  (:class:`_FieldOverlayReadMixin`).
- :mod:`sam.members.repository._mail_config_reader` — the ``config#mail`` gate / sender /
  consent-notice reads (:class:`_MailConfigReadMixin`).
"""

from __future__ import annotations

# ``_normalize_functional_groups`` and the ``_CONFIG_ID_*`` tokens historically lived in this
# module; they are re-exported here so any ``projection_config_reader._normalize_functional_groups``
# / ``._CONFIG_ID_FIELDS`` reference (tests, siblings) keeps resolving after the split.
from sam.members.repository._config_reader_base import (  # noqa: F401
    _CONFIG_ID_FIELDS,
    _CONFIG_ID_MAIL,
    _CONFIG_ID_SCOPE,
    _ConfigReaderBase,
    _normalize_functional_groups,
)
from sam.members.repository._fields_overlay_reader import _FieldOverlayReadMixin
from sam.members.repository._mail_config_reader import _MailConfigReadMixin
from sam.members.repository._scope_reader import _ScopeReadMixin

__all__ = ["MembersProjectionReader"]


class MembersProjectionReader(
    _FieldOverlayReadMixin,
    _ScopeReadMixin,
    _MailConfigReadMixin,
    _ConfigReaderBase,
):
    """Read-only Members config/grant reader backed by the governance projection (C4).

    Implements the S5 domain seams by duck-typing:

    - :meth:`get_scope_config` → :class:`ScopeConfigProvider`
      (``sam.members.domain.scope_dimensions``);
    - :meth:`get_overlay` → :class:`TenantOverlayProvider`
      (``sam.members.domain.field_resolver``);
    - :meth:`is_mail_enabled` → the tenant's mail-enabled gate flag from the ``config#mail``
      row (pivot-output-actions R0, design §6.3 — the Members edge reads it at request time,
      NO live MySQL);
    - :meth:`get_scope_grants` → the caller's projected scope grants (consumed by the edge's
      ``resolve_scope_access`` wiring, task 8.3).

    Mirrors :class:`sam.pretokengen.projection_governance_reader.ProjectionGovernanceReader`:
    one ``Query`` per tenant partition, a per-invocation ``_partition_cache`` so a partition
    is read at most once, and *empty-is-valid* (a missing/empty partition or row is never an
    error — only a missing table env fails fast, at the first real Query).

    The implementation is composed from four cohesive mixins (see the module docstring); this
    class adds no behaviour of its own — it only fixes the method-resolution order so every
    read surface resolves on one object. ``__init__`` (the injectable ``table`` arg) comes
    from :class:`_ConfigReaderBase`.

    Args:
        table: A boto3 DynamoDB Table (or a fake exposing ``query``). Defaults to the
            fail-fast-resolved projection table
            (:func:`services.projection_schema.get_projection_table_resource`). Injectable so
            tests use an in-memory fake / local dynamodb-local.
    """
