"""System-admin media asset endpoints (force-delete, migrate, cross-tenant stats).

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

        service = pkg._get_service()
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
        service = pkg._get_service()
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
