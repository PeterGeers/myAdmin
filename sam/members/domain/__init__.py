"""
Members domain layer — the generic membership engine.

Storage-agnostic and tenant-agnostic: it calls the repository through an interface,
builds no HTTP responses, writes no DynamoDB queries. This is where the reused h-dcn
business logic (fixed/variable fields, membership workflow, scope access) lands.
"""

from .field_resolver import (
    OVERLAY_GROUP,
    FieldConfig,
    FieldOrigin,
    FieldResolver,
    FixedFieldOverride,
    OverlayError,
    OverlayField,
    ResolvedField,
    StaticOverlayProvider,
    TenantOverlay,
    TenantOverlayProvider,
)
from .membership_type_catalog import (
    CATALOG_LOCALES,
    MembershipTypeEntry,
    MembershipTypeValidationError,
)

__all__ = [
    "OVERLAY_GROUP",
    "FieldConfig",
    "FieldOrigin",
    "FieldResolver",
    "FixedFieldOverride",
    "OverlayError",
    "OverlayField",
    "ResolvedField",
    "StaticOverlayProvider",
    "TenantOverlay",
    "TenantOverlayProvider",
    "CATALOG_LOCALES",
    "MembershipTypeEntry",
    "MembershipTypeValidationError",
]
