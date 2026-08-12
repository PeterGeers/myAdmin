"""
Media Asset Routes

API endpoints for the Media Asset Management service.
Handles upload, metadata retrieval, search, attachment/detachment,
tenant admin dashboard, reconciliation, and system admin operations.

Blueprint: media_asset_bp (url_prefix='/api/media-assets')

Endpoints:
- POST /api/media-assets/upload              - Upload + register + optional attach
- GET  /api/media-assets/<asset_id>          - Get metadata + presigned URL
- GET  /api/media-assets/search              - Paginated search for Asset Picker
- POST /api/media-assets/<asset_id>/attach   - Attach reference
- POST /api/media-assets/<asset_id>/detach   - Detach reference
- POST /api/media-assets/replace             - Atomic replace
- GET  /api/media-assets/dashboard           - Summary stats (tenant admin)
- POST /api/media-assets/scan                - Trigger reconciliation (tenant admin)
- GET  /api/media-assets/scan/<scan_id>/status - SSE progress for scan (tenant admin)
- POST /api/media-assets/approve-delete      - Approve deletion (tenant admin)
- GET  /api/media-assets/unregistered        - List unregistered S3 objects (tenant admin)
- POST /api/media-assets/delete-unregistered - Delete unregistered S3 objects (tenant admin)
- POST /api/media-assets/import              - Import unregistered S3 objects (tenant admin)
- GET  /api/media-assets/duplicates          - List duplicate content_hash groups (tenant admin)
- POST /api/media-assets/merge-duplicates    - Merge duplicate assets (tenant admin)
- GET  /api/media-assets/retention-settings  - Get retention config (tenant admin)
- PUT  /api/media-assets/retention-settings  - Update retention config (tenant admin)
- POST /api/media-assets/force-delete        - Emergency bypass delete (sysadmin)
- POST /api/media-assets/migrate             - Full migration trigger (sysadmin)
- GET  /api/media-assets/admin/tenants       - Cross-tenant stats (sysadmin)

Reference: .kiro/specs/Common/image-asset-management/design.md
"""

import json
import logging
import uuid

from flask import Blueprint, Response, jsonify, request
from flask.typing import ResponseReturnValue

from auth.cognito_utils import cognito_required
from auth.tenant_context import tenant_required
from database import DatabaseManager
from services.media_asset_service import MediaAssetService
from services.parameter_service import ParameterService

logger = logging.getLogger(__name__)

# Create blueprint
media_asset_bp = Blueprint("media_assets", __name__, url_prefix="/api/media-assets")

# Global variables set by app.py
flag = False  # Test mode flag


def set_test_mode(test_mode) -> None:
    """Set test mode flag"""
    global flag
    flag = test_mode


def _get_service() -> MediaAssetService:
    """Create a MediaAssetService instance with current test mode setting."""
    db = DatabaseManager(test_mode=flag)
    ps = ParameterService(db)
    return MediaAssetService(db, ps)


@media_asset_bp.route("/health", methods=["GET"])
def health() -> ResponseReturnValue:
    """Health check endpoint for the media assets service."""
    return jsonify({"success": True, "service": "media_assets"})


# === Regular User Endpoints ===


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
        service = _get_service()
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

        service = _get_service()
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
        service = _get_service()
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

        service = _get_service()
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

        service = _get_service()
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

        service = _get_service()
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


# === Tenant Admin Endpoints (storage_manage) ===

# In-memory store for active scan generators keyed by scan_id
_active_scans: dict = {}


@media_asset_bp.route("/dashboard", methods=["GET"])
@cognito_required(required_permissions=["storage_manage"])
@tenant_required()
def get_dashboard(user_email, user_roles, tenant, user_tenants) -> ResponseReturnValue:
    """Summary stats for the tenant admin asset dashboard.

    Returns:
        200: {success: true, data: {total_assets, active_assets, ...}}
        500: {success: false, error: '<message>'}
    """
    try:
        service = _get_service()
        result = service.get_dashboard_stats(tenant)
        return jsonify(result), 200

    except Exception as e:
        logger.error(f"Dashboard stats error: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@media_asset_bp.route("/scan", methods=["POST"])
@cognito_required(required_permissions=["storage_manage"])
@tenant_required()
def trigger_scan(user_email, user_roles, tenant, user_tenants) -> ResponseReturnValue:
    """Trigger a reconciliation scan (async). Returns scan_id for SSE streaming.

    Returns:
        202: {success: true, scan_id: '<uuid>'}
        500: {success: false, error: '<message>'}
    """
    try:
        scan_id = str(uuid.uuid4())

        # Store the generator for later SSE consumption
        service = _get_service()
        _active_scans[scan_id] = {
            "tenant": tenant,
            "generator": service.run_reconciliation_with_progress(tenant),
        }

        return jsonify({"success": True, "scan_id": scan_id}), 202

    except Exception as e:
        logger.error(f"Trigger scan error: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@media_asset_bp.route("/scan/<scan_id>/status", methods=["GET"])
def scan_status_stream(scan_id) -> ResponseReturnValue:
    """SSE stream for reconciliation scan progress.

    Uses query parameter authentication since EventSource cannot send custom headers.

    Query Parameters:
        token: JWT token for authentication
        administration: Tenant identifier

    Path Parameters:
        scan_id: The scan ID returned by POST /api/media-assets/scan

    Returns:
        200: SSE stream with progress events
        401: {success: false, error: 'Authentication required'}
        404: {success: false, error: 'Scan not found'}
    """
    # SSE endpoints use query-param auth since EventSource can't send headers
    token = request.args.get("token")
    tenant = request.args.get("administration")

    if not token:
        return jsonify({"success": False, "error": "Authentication required"}), 401

    # Manually validate the token
    from auth.cognito_utils import (
        _extract_with_base64,
        _extract_with_verifier,
        _get_jwt_verifier,
    )

    verifier = _get_jwt_verifier()
    if verifier is not None:
        _, user_roles, auth_error = _extract_with_verifier(verifier, token)
    else:
        _, user_roles, auth_error = _extract_with_base64(token)

    if auth_error:
        return jsonify({"success": False, "error": "Authentication failed"}), 401

    # Check permissions
    from auth.cognito_utils import validate_permissions

    is_authorized, _ = validate_permissions(user_roles or [], ["storage_manage"])
    if not is_authorized:
        return jsonify({"success": False, "error": "Insufficient permissions"}), 403

    if not tenant:
        return jsonify({"success": False, "error": "Tenant is required"}), 400

    scan_entry = _active_scans.get(scan_id)

    if not scan_entry:
        return jsonify({"success": False, "error": "Scan not found"}), 404

    # Verify tenant ownership
    if scan_entry["tenant"] != tenant:
        return jsonify({"success": False, "error": "Scan not found"}), 404

    def generate_progress():
        try:
            generator = scan_entry["generator"]
            for progress_data in generator:
                yield f"data: {json.dumps(progress_data, default=str)}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'error': str(e)})}\n\n"
        finally:
            # Clean up after stream completes
            _active_scans.pop(scan_id, None)

    return Response(
        generate_progress(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@media_asset_bp.route("/approve-delete", methods=["POST"])
@cognito_required(required_permissions=["storage_manage"])
@tenant_required()
def approve_delete(user_email, user_roles, tenant, user_tenants) -> ResponseReturnValue:
    """Bulk approve deletion of eligible assets.

    Request JSON:
        asset_ids: List of asset IDs to delete

    Returns:
        200: {success: true, deleted: N, skipped: N, details: [...]}
        400: {success: false, error: '<message>'}
        500: {success: false, error: '<message>'}
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({"success": False, "error": "Request body is required"}), 400

        asset_ids = data.get("asset_ids")
        if not asset_ids or not isinstance(asset_ids, list):
            return jsonify(
                {"success": False, "error": "asset_ids array is required"}
            ), 400

        service = _get_service()
        deleted = 0
        skipped = 0
        details = []

        for asset_id in asset_ids:
            result = service.delete_asset(
                tenant=tenant,
                asset_id=asset_id,
                approved_by=user_email,
            )
            if result.get("success"):
                deleted += 1
                details.append({"asset_id": asset_id, "status": "deleted"})
            else:
                skipped += 1
                details.append(
                    {
                        "asset_id": asset_id,
                        "status": "skipped",
                        "reason": result.get("error", "unknown"),
                    }
                )

        return jsonify(
            {
                "success": True,
                "deleted": deleted,
                "skipped": skipped,
                "details": details,
            }
        ), 200

    except Exception as e:
        logger.error(f"Approve delete error: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


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
        service = _get_service()
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

        service = _get_service()
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
            service = _get_service()
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

        service = _get_service()
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
        service = _get_service()
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

        service = _get_service()
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
        service = _get_service()
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

        service = _get_service()
        result = service.update_retention_settings(tenant, data)
        return jsonify(result), 200

    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    except Exception as e:
        logger.error(f"Update retention settings error: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


# === System Admin Endpoints (admin_manage) ===


@media_asset_bp.route("/force-delete", methods=["POST"])
@cognito_required(required_permissions=["admin_manage"])
@tenant_required(allow_sysadmin=True)
def force_delete_asset(
    user_email, user_roles, tenant, user_tenants
) -> ResponseReturnValue:
    """Emergency bypass delete. System admin only.

    Bypasses the reference guard entirely — deletes the asset even if active
    references exist. Requires admin_manage permission and logs a WARNING-level
    audit entry.

    Request JSON:
        asset_id: The asset ID to force-delete
        tenant: Optional tenant override (sysadmin can target any tenant)
        reason: Reason for the emergency deletion

    Returns:
        200: {success: true, asset_id, reference_count, operator, reason}
        400: {success: false, error: '<message>'}
        500: {success: false, error: '<message>'}
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({"success": False, "error": "Request body is required"}), 400

        asset_id = data.get("asset_id")
        if not asset_id:
            return jsonify({"success": False, "error": "asset_id is required"}), 400

        reason = data.get("reason")
        if not reason:
            return jsonify({"success": False, "error": "reason is required"}), 400

        # Use specified tenant or fall back to authenticated tenant
        target_tenant = data.get("tenant") or tenant

        service = _get_service()
        result = service.force_delete(
            tenant=target_tenant,
            asset_id=asset_id,
            operator=user_email,
            reason=reason,
        )

        if result.get("success"):
            return jsonify(result), 200
        else:
            return jsonify(result), 400

    except Exception as e:
        logger.error(f"Force delete error: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@media_asset_bp.route("/migrate", methods=["POST"])
@cognito_required(required_permissions=["admin_manage"])
@tenant_required(allow_sysadmin=True)
def migrate_assets(user_email, user_roles, tenant, user_tenants) -> ResponseReturnValue:
    """Full migration trigger for all tenants. System admin only.

    Calls import_legacy_assets for each specified tenant/category combination.
    Currently returns 501 (not implemented) since the underlying import
    functionality is still a stub.

    Request JSON:
        tenants: List of tenant IDs to migrate, or "all" for all tenants

    Returns:
        501: {success: false, error: 'Migration not yet implemented'}
        400: {success: false, error: '<message>'}
        500: {success: false, error: '<message>'}
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({"success": False, "error": "Request body is required"}), 400

        tenants_param = data.get("tenants")
        if not tenants_param:
            return jsonify({"success": False, "error": "tenants is required"}), 400

        if tenants_param != "all" and not isinstance(tenants_param, list):
            return jsonify(
                {
                    "success": False,
                    "error": "tenants must be a list of tenant IDs or 'all'",
                }
            ), 400

        # import_legacy_assets is not yet implemented — return 501
        return jsonify(
            {
                "success": False,
                "error": "Migration not yet implemented",
            }
        ), 501

    except Exception as e:
        logger.error(f"Migrate assets error: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@media_asset_bp.route("/admin/tenants", methods=["GET"])
@cognito_required(required_permissions=["admin_manage"])
@tenant_required(allow_sysadmin=True)
def admin_tenant_stats(
    user_email, user_roles, tenant, user_tenants
) -> ResponseReturnValue:
    """Cross-tenant asset statistics. System admin only.

    Queries aggregate stats across all tenants — total assets and storage
    per tenant. Does NOT filter by a single administration; this is a
    sysadmin cross-tenant view.

    Returns:
        200: {success: true, data: [{tenant, total_assets, total_bytes}, ...]}
        500: {success: false, error: '<message>'}
    """
    try:
        service = _get_service()
        db = service.db

        # Cross-tenant aggregate query — GROUP BY administration without tenant filter
        stats_query = """
            SELECT
                administration AS tenant,
                COUNT(*) AS total_assets,
                COALESCE(SUM(file_size), 0) AS total_bytes
            FROM s3_assets
            GROUP BY administration
            ORDER BY total_bytes DESC
        """
        rows = db.execute_query(stats_query, fetch=True)

        data = []
        for row in rows:
            data.append(
                {
                    "tenant": row["tenant"],
                    "total_assets": row["total_assets"],
                    "total_bytes": row["total_bytes"],
                }
            )

        return jsonify({"success": True, "data": data}), 200

    except Exception as e:
        logger.error(f"Admin tenant stats error: {e}")
        return jsonify({"success": False, "error": str(e)}), 500
