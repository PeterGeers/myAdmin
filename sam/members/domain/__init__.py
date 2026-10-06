"""
Members domain layer — the generic membership engine.

Storage-agnostic and tenant-agnostic: it calls the repository through an interface,
builds no HTTP responses, writes no DynamoDB queries. This is where the reused h-dcn
business logic (fixed/variable fields, membership workflow, scope access) lands.
"""

from .field_resolver import (
    OVERLAY_GROUP,
    AddressMapping,
    AnalyticsConfig,
    AnalyticsRole,
    FieldConfig,
    FieldOrigin,
    FieldResolver,
    FixedFieldOverride,
    JubileeRule,
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
    "CATALOG_LOCALES",
    "OVERLAY_GROUP",
    "AddressMapping",
    "AnalyticsConfig",
    "AnalyticsRole",
    "FieldConfig",
    "FieldOrigin",
    "FieldResolver",
    "FixedFieldOverride",
    "JubileeRule",
    "MembershipTypeEntry",
    "MembershipTypeValidationError",
    "OverlayError",
    "OverlayField",
    "ResolvedField",
    "StaticOverlayProvider",
    "TenantOverlay",
    "TenantOverlayProvider",
]
