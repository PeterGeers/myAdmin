"""Regular-user media asset endpoints (upload, get, search, attach/detach, replace).

Endpoint handlers resolve the service factory and blueprint through the
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


@media_asset_bp.route("/health", methods=["GET"])
def health() -> ResponseReturnValue:
    """Health check endpoint for the media assets service."""
    return jsonify({"success": True, "service": "media_assets"})


@media_asset_bp.route("/upload", methods=["POST"])
@cognito_required(required_permissions=["storage_write"])
@tenant_required()
def upload_asset(user_email, user_roles, tenant, user_tenants) -> ResponseReturnValue:
    """Upload a file, register it in the asset registry, and optionally attach.

    Request (multipart/form-data):
        file: Binary file data
        category: Asset category (invoices, branding, templates, landing-pages)
        entity_type: Optional entity type for reference attachment
        entity_id: Optional entity ID for reference attachment

    Returns:
        201: {success: true, asset: {...}, duplicate_of: ...}
        400: {success: false, error: '<message>'} on validation error
        500: {success: false, error: '<message>'} on unexpected error
    """
    try:
        # Validate file is present
        if "file" not in request.files:
            return jsonify({"success": False, "error": "No file provided"}), 400

        file = request.files["file"]
        if not file.filename:
            return jsonify({"success": False, "error": "No file selected"}), 400

        # Read form fields
        category = request.form.get("category", "")
        if not category:
            return jsonify({"success": False, "error": "Category is required"}), 400

        entity_type = request.form.get("entity_type") or None
        entity_id = request.form.get("entity_id") or None

        # Read file data
        file_data = file.read()

        # Call service
        service = pkg._get_service()
        result = service.store_and_register(
            tenant=tenant,
            file_data=file_data,
            filename=file.filename,
            category=category,
            entity_type=entity_type,
            entity_id=entity_id,
        )

        if result["success"]:
            return jsonify(result), 201
        else:
            return jsonify(result), 400

    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    except Exception as e:
        logger.error(f"Asset upload error: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@media_asset_bp.route("/search", methods=["GET"])
@cognito_required(required_permissions=["storage_read"])
@tenant_required()
def search_assets(user_email, user_roles, tenant, user_tenants) -> ResponseReturnValue:
    """Paginated asset search for the Asset Picker.

    Query Parameters:
        q: Search term (LIKE match on original_filename)
        category: Filter by category (exact match)
        media_type: Filter by media_type (exact match)
        status: Filter by status (exact match)
        sort: Sort column (default: created_at)
        order: Sort order - asc or desc (default: desc)
        page: Page number, 1-based (default: 1)
        page_size: Results per page (default: 20, max: 100)

    Returns:
        200: {success: true, data: [...], pagination: {...}}
        500: {success: false, error: '<message>'}
    """
    try:
        filters = {
            "q": request.args.get("q", ""),
            "category": request.args.get("category", ""),
            "media_type": request.args.get("media_type", ""),
            "status": request.args.get("status", ""),
            "sort": request.args.get("sort", "created_at"),
            "order": request.args.get("order", "desc"),
            "page": request.args.get("page", "1"),
            "page_size": request.args.get("page_size", "20"),
        }

        service = pkg._get_service()
        result = service.search_assets(tenant=tenant, filters=filters)

        return jsonify(result), 200

    except Exception as e:
        logger.error(f"Search assets error: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@media_asset_bp.route("/<asset_id>", methods=["GET"])
@cognito_required(required_permissions=["storage_read"])
@tenant_required()
def get_asset(
    user_email, user_roles, tenant, user_tenants, asset_id
) -> ResponseReturnValue:
    """Get asset metadata and presigned URL.

    Path Parameters:
        asset_id: The asset ID to retrieve

    Returns:
        200: {success: true, asset: {...}}
        404: {success: false, error: 'Asset not found'}
        500: {success: false, error: '<message>'}
    """
    try:
        service = pkg._get_service()
        result = service.get_asset(tenant=tenant, asset_id=asset_id)

        if result["success"]:
            return jsonify(result), 200
        else:
            return jsonify(result), 404

    except Exception as e:
        logger.error(f"Get asset error: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@media_asset_bp.route("/<asset_id>/attach", methods=["POST"])
@cognito_required(required_permissions=["storage_write"])
@tenant_required()
def attach_asset(
    user_email, user_roles, tenant, user_tenants, asset_id
) -> ResponseReturnValue:
    """Attach an entity reference to an asset.

    Path Parameters:
        asset_id: The asset ID to attach to

    Request JSON:
        entity_type: Type of referencing entity (e.g., 'invoice')
        entity_id: ID of the referencing entity

    Returns:
        200: {success: true, ...}
        400: {success: false, error: '<message>'}
        500: {success: false, error: '<message>'}
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({"success": False, "error": "Request body is required"}), 400

        entity_type = data.get("entity_type")
        entity_id = data.get("entity_id")

        if not entity_type or not entity_id:
            return jsonify(
                {"success": False, "error": "entity_type and entity_id are required"}
            ), 400

        service = pkg._get_service()
        result = service.attach(
            tenant=tenant,
            asset_id=asset_id,
            entity_type=entity_type,
            entity_id=str(entity_id),
        )

        if result["success"]:
            return jsonify(result), 200
        else:
            return jsonify(result), 400

    except Exception as e:
        logger.error(f"Attach asset error: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@media_asset_bp.route("/<asset_id>/detach", methods=["POST"])
@cognito_required(required_permissions=["storage_write"])
@tenant_required()
def detach_asset(
    user_email, user_roles, tenant, user_tenants, asset_id
) -> ResponseReturnValue:
    """Detach an entity reference from an asset.

    Path Parameters:
        asset_id: The asset ID to detach from

    Request JSON:
        entity_type: Type of referencing entity (e.g., 'invoice')
        entity_id: ID of the referencing entity

    Returns:
        200: {success: true, asset: {...}}
        400: {success: false, error: '<message>'}
        500: {success: false, error: '<message>'}
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({"success": False, "error": "Request body is required"}), 400

        entity_type = data.get("entity_type")
        entity_id = data.get("entity_id")

        if not entity_type or not entity_id:
            return jsonify(
                {"success": False, "error": "entity_type and entity_id are required"}
            ), 400

        service = pkg._get_service()
        result = service.detach(
            tenant=tenant,
            asset_id=asset_id,
            entity_type=entity_type,
            entity_id=str(entity_id),
        )

        if result["success"]:
            return jsonify(result), 200
        else:
            return jsonify(result), 400

    except Exception as e:
        logger.error(f"Detach asset error: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@media_asset_bp.route("/replace", methods=["POST"])
@cognito_required(required_permissions=["storage_write"])
@tenant_required()
def replace_asset(user_email, user_roles, tenant, user_tenants) -> ResponseReturnValue:
    """Atomically replace an entity's asset reference.

    Request JSON:
        entity_type: Type of referencing entity
        entity_id: ID of the referencing entity
        old_asset_id: Asset to detach (null/empty → simple attach)
        new_asset_id: Asset to attach

    Returns:
        200: {success: true, ...}
        400: {success: false, error: '<message>'}
        500: {success: false, error: '<message>'}
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({"success": False, "error": "Request body is required"}), 400

        entity_type = data.get("entity_type")
        entity_id = data.get("entity_id")
        old_asset_id = data.get("old_asset_id") or None
        new_asset_id = data.get("new_asset_id")

        if not entity_type or not entity_id:
            return jsonify(
                {"success": False, "error": "entity_type and entity_id are required"}
            ), 400

        if not new_asset_id:
            return jsonify({"success": False, "error": "new_asset_id is required"}), 400

        service = pkg._get_service()
        result = service.replace(
            tenant=tenant,
            entity_type=entity_type,
            entity_id=str(entity_id),
            old_asset_id=old_asset_id,
            new_asset_id=new_asset_id,
        )

        if result["success"]:
            return jsonify(result), 200
        else:
            return jsonify(result), 400

    except Exception as e:
        logger.error(f"Replace asset error: {e}")
        return jsonify({"success": False, "error": str(e)}), 500
