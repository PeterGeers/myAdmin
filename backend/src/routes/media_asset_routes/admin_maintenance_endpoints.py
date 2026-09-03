"""Tenant-admin maintenance endpoints (unregistered objects, imports, duplicates, retention).

Endpoint handlers resolve the service factory through the
``routes.media_asset_routes`` package namespace at call time so that
``patch('routes.media_asset_routes._get_service')`` continues to intercept
every service instantiation.
"""

import logging

from flask import jsonify, request
from flask.typing import ResponseReturnValue

from auth.cognito_utils import cognito_required
from auth.tenant_context import tenant_required
from routes import media_asset_routes as pkg

logger = logging.getLogger(__name__)

media_asset_bp = pkg.media_asset_bp


@media_asset_bp.route("/unregistered", methods=["GET"])
@cognito_required(required_permissions=["storage_manage"])
@tenant_required()
def get_unregistered(
    user_email, user_roles, tenant, user_tenants
) -> ResponseReturnValue:
    """List unregistered S3 objects (in S3 but not in asset registry).

    Performs a lightweight S3 scan comparing bucket contents against the
    registry for this tenant. Returns objects with metadata (key, bucket,
    size, last_modified).

    Returns:
        200: {success: true, data: [{s3_key, bucket, size, last_modified}, ...]}
        500: {success: false, error: '<message>'}
    """
    try:
        service = pkg._get_service()
        result = service.get_unregistered_objects(tenant)
        return jsonify(result), 200

    except Exception as e:
        logger.error(f"Get unregistered objects error: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@media_asset_bp.route("/delete-unregistered", methods=["POST"])
@cognito_required(required_permissions=["storage_manage"])
@tenant_required()
def delete_unregistered(
    user_email, user_roles, tenant, user_tenants
) -> ResponseReturnValue:
    """Delete unregistered S3 objects permanently.

    Removes S3 objects that are not in the asset registry. This is a
    destructive operation — objects are permanently deleted from S3.

    Request JSON:
        s3_keys: List of S3 keys to delete (must be unregistered)

    Returns:
        200: {success: true, deleted: N, skipped: N}
        400: {success: false, error: '<message>'}
        500: {success: false, error: '<message>'}
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({"success": False, "error": "Request body is required"}), 400

        s3_keys = data.get("s3_keys")
        if not s3_keys or not isinstance(s3_keys, list):
            return jsonify(
                {"success": False, "error": "s3_keys array is required"}
            ), 400

        service = pkg._get_service()
        result = service.delete_unregistered_objects(
            tenant, s3_keys, operator=user_email
        )

        if result.get("success"):
            return jsonify(result), 200
        else:
            return jsonify(result), 400

    except Exception as e:
        logger.error(f"Delete unregistered objects error: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@media_asset_bp.route("/import", methods=["POST"])
@cognito_required(required_permissions=["storage_manage"])
@tenant_required()
def import_assets(user_email, user_roles, tenant, user_tenants) -> ResponseReturnValue:
    """Import unregistered S3 objects into the asset registry.

    Supports two modes:
    1. Category-based: {"category": "invoices"} — imports all unregistered objects in that category
    2. Key-based: {"s3_keys": ["key1", "key2"]} — imports specific S3 keys

    Request JSON:
        category: Category to import (invoices, branding, templates, landing-pages)
        OR
        s3_keys: List of specific S3 keys to import

    Returns:
        200: {success: true, imported: N, skipped: N}
        400: {success: false, error: '<message>'}
        501: {success: false, error: 'Not implemented'}
        500: {success: false, error: '<message>'}
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({"success": False, "error": "Request body is required"}), 400

        s3_keys = data.get("s3_keys")
        category = data.get("category", "")

        # Mode 1: Import specific S3 keys
        if s3_keys and isinstance(s3_keys, list):
            service = pkg._get_service()
            imported = 0
            skipped = 0

            for key in s3_keys:
                # Verify key belongs to this tenant
                if not key.startswith(f"{tenant}/"):
                    skipped += 1
                    continue

                # Derive category from key path (e.g., "TenantA/invoices/file.pdf" → "invoices")
                parts = key.split("/")
                key_category = parts[1] if len(parts) > 2 else ""

                try:
                    result = service.import_legacy_assets(
                        tenant=tenant, category=key_category
                    )
                    if result.get("success"):
                        imported += result.get("imported", 0)
                        skipped += result.get("skipped", 0)
                    else:
                        skipped += 1
                except (NotImplementedError, Exception):
                    skipped += 1

            return jsonify(
                {
                    "success": True,
                    "imported": imported,
                    "skipped": skipped,
                }
            ), 200

        # Mode 2: Category-based import (legacy)
        if not category:
            return jsonify(
                {"success": False, "error": "category or s3_keys is required"}
            ), 400

        service = pkg._get_service()
        result = service.import_legacy_assets(tenant=tenant, category=category)

        if result.get("success"):
            return jsonify(result), 200
        else:
            return jsonify(result), 400

    except NotImplementedError:
        return jsonify(
            {
                "success": False,
                "error": "Import functionality is not yet implemented",
            }
        ), 501
    except Exception as e:
        logger.error(f"Import assets error: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@media_asset_bp.route("/duplicates", methods=["GET"])
@cognito_required(required_permissions=["storage_manage"])
@tenant_required()
def list_duplicates(
    user_email, user_roles, tenant, user_tenants
) -> ResponseReturnValue:
    """List duplicate content_hash groups for this tenant.

    Returns assets grouped by content_hash where COUNT > 1.

    Returns:
        200: {success: true, data: [{content_hash, count, assets: [...]}, ...]}
        500: {success: false, error: '<message>'}
    """
    try:
        service = pkg._get_service()
        result = service.get_duplicate_groups(tenant)
        return jsonify(result), 200

    except Exception as e:
        logger.error(f"List duplicates error: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@media_asset_bp.route("/merge-duplicates", methods=["POST"])
@cognito_required(required_permissions=["storage_manage"])
@tenant_required()
def merge_duplicates(
    user_email, user_roles, tenant, user_tenants
) -> ResponseReturnValue:
    """Merge a group of duplicate assets (same content_hash).

    Keeps one asset (the oldest/primary), re-attaches all references from the
    others to the kept asset, and deletes the rest.

    Request JSON:
        keep_asset_id: The asset ID to keep
        duplicate_asset_ids: List of asset IDs to merge into the kept one

    Returns:
        200: {success: true, kept: '<id>', merged: N, deleted: N}
        400: {success: false, error: '<message>'}
        500: {success: false, error: '<message>'}
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({"success": False, "error": "Request body is required"}), 400

        keep_asset_id = data.get("keep_asset_id")
        duplicate_asset_ids = data.get("duplicate_asset_ids")

        if not keep_asset_id:
            return jsonify(
                {"success": False, "error": "keep_asset_id is required"}
            ), 400

        if not duplicate_asset_ids or not isinstance(duplicate_asset_ids, list):
            return jsonify(
                {"success": False, "error": "duplicate_asset_ids array is required"}
            ), 400

        service = pkg._get_service()
        result = service.merge_duplicates(
            tenant=tenant,
            keep_asset_id=keep_asset_id,
            duplicate_asset_ids=duplicate_asset_ids,
        )

        if result.get("success"):
            return jsonify(result), 200
        else:
            return jsonify(result), 400

    except Exception as e:
        logger.error(f"Merge duplicates error: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@media_asset_bp.route("/retention-settings", methods=["GET"])
@cognito_required(required_permissions=["storage_manage"])
@tenant_required()
def get_retention_settings(
    user_email, user_roles, tenant, user_tenants
) -> ResponseReturnValue:
    """Get current retention configuration with source indicators.

    Returns the resolved retention settings for each category. Each value
    includes a 'source' field indicating whether it comes from a tenant
    override or the system default.

    Returns:
        200: {success: true, data: {key: {value, source}, ...}}
        500: {success: false, error: '<message>'}
    """
    try:
        service = pkg._get_service()
        result = service.get_retention_settings(tenant)
        return jsonify(result), 200

    except Exception as e:
        logger.error(f"Get retention settings error: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@media_asset_bp.route("/retention-settings", methods=["PUT"])
@cognito_required(required_permissions=["storage_manage"])
@tenant_required()
def update_retention_settings(
    user_email, user_roles, tenant, user_tenants
) -> ResponseReturnValue:
    """Update tenant-level retention overrides.

    Request JSON:
        Key-value pairs where keys are retention parameter names and values
        are positive integers (days). Example: {"branding_days": 60}

    Returns:
        200: {success: true, updated: ['key1', 'key2']}
        400: {success: false, error: '<message>'}
        500: {success: false, error: '<message>'}
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({"success": False, "error": "Request body is required"}), 400

        if not isinstance(data, dict):
            return jsonify(
                {"success": False, "error": "Request body must be a JSON object"}
            ), 400

        service = pkg._get_service()
        result = service.update_retention_settings(tenant, data)
        return jsonify(result), 200

    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    except Exception as e:
        logger.error(f"Update retention settings error: {e}")
        return jsonify({"success": False, "error": str(e)}), 500
