"""Tenant-admin scan endpoints (dashboard, reconciliation scan, SSE status, approve-delete).

Endpoint handlers resolve the service factory through the
``routes.media_asset_routes`` package namespace at call time so that
``patch('routes.media_asset_routes._get_service')`` continues to intercept
every service instantiation.
"""

import json
import logging
import uuid

from flask import Response, jsonify, request
from flask.typing import ResponseReturnValue

from auth.cognito_utils import cognito_required
from auth.tenant_context import tenant_required
from routes import media_asset_routes as pkg

logger = logging.getLogger(__name__)

media_asset_bp = pkg.media_asset_bp

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
        service = pkg._get_service()
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
        service = pkg._get_service()
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

        service = pkg._get_service()
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
