"""Shared constants and indirection helpers for the MediaAssetService concern mixins.

Kept in a dependency-free module so the concern mixins and the main
``services.media_asset_service`` module can both import it without a cycle.

The ``_mas_boto3`` / ``_maslog`` accessors deliberately resolve ``boto3`` and the
logger through the ``services.media_asset_service`` module namespace at call
time. This keeps the existing test suite working unchanged: tests patch
``services.media_asset_service.boto3.client`` and ``services.media_asset_service.logger``,
and because the mixins reach those symbols via the main module rather than their
own module globals, the patches are observed everywhere.
"""


def _mas_boto3():
    """Return ``boto3`` as seen through the main media_asset_service module.

    Resolving it lazily (rather than importing ``boto3`` into each mixin module)
    means ``patch('services.media_asset_service.boto3.client', ...)`` intercepts
    every S3 call made from any mixin.
    """
    from services import media_asset_service as _mas

    return _mas.boto3


def _maslog():
    """Return the main module logger so test patches on
    ``services.media_asset_service.logger`` are observed from the mixins.
    """
    from services import media_asset_service as _mas

    return _mas.logger


# entity_type → (table, id_column, existence_query) or None for ephemeral types
# Special: 'dynamodb' as table name indicates DynamoDB-backed entity (no MySQL query)
ENTITY_TYPE_REGISTRY = {
    "invoice": (
        "mutaties",
        "ID",
        "SELECT 1 FROM mutaties WHERE ID = %s AND administration = %s LIMIT 1",
    ),
    "branding": (
        "parameter_values",
        None,
        (
            "SELECT 1 FROM parameter_values WHERE namespace = 'branding' "
            "AND `key` = %s AND scope_type = 'tenant' AND scope_value = %s LIMIT 1"
        ),
    ),
    "landing_page": (
        "dynamodb",
        "slug",
        None,
    ),  # DynamoDB — verified via LandingPageService
    "template": (
        "parameter_values",
        None,
        (
            "SELECT 1 FROM parameter_values WHERE namespace = 'templates' "
            "AND `key` = %s AND scope_type = 'tenant' AND scope_value = %s LIMIT 1"
        ),
    ),
    "report": None,  # Ephemeral — auto-expire after 90 days, no existence check
    "zzp_invoice": (
        "zzp_invoices",
        "id",
        "SELECT 1 FROM zzp_invoices WHERE id = %s AND administration = %s LIMIT 1",
    ),
}
