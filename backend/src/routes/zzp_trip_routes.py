"""
ZZP Trip Routes: Vehicle, trip, and route preset management endpoints.

Provides CRUD endpoints for vehicles, trips, and route presets in the
Rittenregistratie module. Import/export/billing endpoints are in
zzp_trip_import_export_routes.py.

Reference: .kiro/specs/ZZP/rittenregistratie/design.md §3.1, §3.2, §3.5
"""

import logging

from flask import Blueprint, jsonify, request
from flask.typing import ResponseReturnValue

from auth.cognito_utils import cognito_required
from auth.tenant_context import tenant_required
from database import DatabaseManager
from services.module_registry import module_required
from services.parameter_service import ParameterService
from services.zzp_route_preset_service import RoutePresetService
from services.zzp_trip_service import TripService
from services.zzp_vehicle_service import VehicleService

logger = logging.getLogger(__name__)

zzp_trip_bp = Blueprint("zzp_trip", __name__)

_test_mode = False


def set_test_mode(flag: bool) -> None:
    global _test_mode
    _test_mode = flag


def _get_vehicle_service() -> VehicleService:
    db = DatabaseManager(test_mode=_test_mode)
    param_svc = ParameterService(db)
    return VehicleService(db=db, parameter_service=param_svc)


def _get_trip_service() -> TripService:
    db = DatabaseManager(test_mode=_test_mode)
    param_svc = ParameterService(db)
    return TripService(db=db, parameter_service=param_svc)


def _get_route_preset_service() -> RoutePresetService:
    db = DatabaseManager(test_mode=_test_mode)
    param_svc = ParameterService(db)
    return RoutePresetService(db=db, parameter_service=param_svc)


# ── Vehicle Endpoints (Design §3.1) ────────────────────────


@zzp_trip_bp.route("/api/zzp/vehicles", methods=["GET"])
@cognito_required(required_permissions=["zzp_read"])
@tenant_required()
@module_required("ZZP")
def list_vehicles(user_email, user_roles, tenant, user_tenants) -> ResponseReturnValue:
    """List vehicles for the tenant, optionally filtered by is_active."""
    try:
        svc = _get_vehicle_service()
        is_active_param = request.args.get("is_active")
        if is_active_param is not None:
            active_only = is_active_param.lower() == "true"
        else:
            active_only = True
        vehicles = svc.list_vehicles(tenant, active_only=active_only)
        return jsonify({"success": True, "data": vehicles})
    except Exception as e:  # noqa: BLE001
        logger.error("list_vehicles error for %s: %s", tenant, e)
        return jsonify({"success": False, "error": "An internal error occurred"}), 500


@zzp_trip_bp.route("/api/zzp/vehicles", methods=["POST"])
@cognito_required(required_permissions=["zzp_crud"])
@tenant_required()
@module_required("ZZP")
def create_vehicle(user_email, user_roles, tenant, user_tenants) -> ResponseReturnValue:
    """Create a new vehicle."""
    try:
        svc = _get_vehicle_service()
        data = request.get_json()
        if not data:
            return jsonify({"success": False, "error": "Request body required"}), 400
        vehicle = svc.create_vehicle(tenant, data, created_by=user_email)
        return jsonify({"success": True, "data": vehicle}), 201
    except ValueError as ve:
        return jsonify({"success": False, "error": str(ve)}), 400
    except Exception as e:  # noqa: BLE001
        logger.error("create_vehicle error for %s: %s", tenant, e)
        return jsonify({"success": False, "error": "An internal error occurred"}), 500


@zzp_trip_bp.route("/api/zzp/vehicles/<int:vehicle_id>", methods=["PUT"])
@cognito_required(required_permissions=["zzp_crud"])
@tenant_required()
@module_required("ZZP")
def update_vehicle(
    user_email, user_roles, tenant, user_tenants, vehicle_id
) -> ResponseReturnValue:
    """Update an existing vehicle."""
    try:
        svc = _get_vehicle_service()
        data = request.get_json()
        if not data:
            return jsonify({"success": False, "error": "Request body required"}), 400
        vehicle = svc.update_vehicle(tenant, vehicle_id, data)
        return jsonify({"success": True, "data": vehicle})
    except ValueError as ve:
        return jsonify({"success": False, "error": str(ve)}), 400
    except Exception as e:  # noqa: BLE001
        logger.error("update_vehicle error for %s/%s: %s", tenant, vehicle_id, e)
        return jsonify({"success": False, "error": "An internal error occurred"}), 500


@zzp_trip_bp.route("/api/zzp/vehicles/<int:vehicle_id>", methods=["DELETE"])
@cognito_required(required_permissions=["zzp_crud"])
@tenant_required()
@module_required("ZZP")
def deactivate_vehicle(
    user_email, user_roles, tenant, user_tenants, vehicle_id
) -> ResponseReturnValue:
    """Soft-delete a vehicle (set is_active = false)."""
    try:
        svc = _get_vehicle_service()
        svc.deactivate_vehicle(tenant, vehicle_id)
        return jsonify(
            {"success": True, "data": {"id": vehicle_id, "is_active": False}}
        )
    except ValueError as ve:
        return jsonify({"success": False, "error": str(ve)}), 400
    except Exception as e:  # noqa: BLE001
        logger.error("deactivate_vehicle error for %s/%s: %s", tenant, vehicle_id, e)
        return jsonify({"success": False, "error": "An internal error occurred"}), 500


# ── Trip Endpoints (Design §3.2) ───────────────────────────


@zzp_trip_bp.route("/api/zzp/trips", methods=["GET"])
@cognito_required(required_permissions=["zzp_crud"])
@tenant_required()
@module_required("ZZP")
def list_trips(user_email, user_roles, tenant, user_tenants) -> ResponseReturnValue:
    """List trips with filtering and pagination.

    Query params: vehicle_id, date_from, date_to, trip_category,
                  contact_id, is_billed, is_gap_fill, limit, offset
    """
    try:
        svc = _get_trip_service()

        # Build filters dict from query params
        filters = {}
        if request.args.get("vehicle_id"):
            filters["vehicle_id"] = request.args.get("vehicle_id")
        if request.args.get("date_from"):
            filters["date_from"] = request.args.get("date_from")
        if request.args.get("date_to"):
            filters["date_to"] = request.args.get("date_to")
        if request.args.get("trip_category"):
            filters["trip_category"] = request.args.get("trip_category")
        if request.args.get("contact_id"):
            filters["contact_id"] = request.args.get("contact_id")
        if request.args.get("is_billed") is not None:
            filters["is_billed"] = request.args.get("is_billed", "").lower() == "true"
        if request.args.get("is_gap_fill") is not None:
            filters["is_gap_fill"] = (
                request.args.get("is_gap_fill", "").lower() == "true"
            )
        if request.args.get("limit"):
            filters["limit"] = request.args.get("limit")
        if request.args.get("offset"):
            filters["offset"] = request.args.get("offset")

        result = svc.list_trips(tenant, filters=filters)
        return jsonify(
            {"success": True, "data": result["data"], "total": result["total"]}
        )
    except ValueError as ve:
        return jsonify({"success": False, "error": str(ve)}), 400
    except Exception as e:  # noqa: BLE001
        logger.error("list_trips error for %s: %s", tenant, e)
        return jsonify({"success": False, "error": "An internal error occurred"}), 500


@zzp_trip_bp.route("/api/zzp/trips", methods=["POST"])
@cognito_required(required_permissions=["zzp_crud"])
@tenant_required()
@module_required("ZZP")
def create_trip(user_email, user_roles, tenant, user_tenants) -> ResponseReturnValue:
    """Create a new trip record. Includes gap warnings if odometer gap detected."""
    try:
        svc = _get_trip_service()
        data = request.get_json()
        if not data:
            return jsonify({"success": False, "error": "Request body required"}), 400
        result = svc.create_trip(tenant, data, created_by=user_email)

        # Build response — pass through warnings and gap_fill_offer if present
        response = {"success": True, "data": result["data"]}
        if "warnings" in result:
            response["warnings"] = result["warnings"]
        if "gap_fill_offer" in result:
            response["gap_fill_offer"] = result["gap_fill_offer"]

        return jsonify(response), 201
    except ValueError as ve:
        return jsonify({"success": False, "error": str(ve)}), 400
    except Exception as e:  # noqa: BLE001
        logger.error("create_trip error for %s: %s", tenant, e)
        return jsonify({"success": False, "error": "An internal error occurred"}), 500


@zzp_trip_bp.route("/api/zzp/trips/gap-fill", methods=["POST"])
@cognito_required(required_permissions=["zzp_crud"])
@tenant_required()
@module_required("ZZP")
def create_gap_fill(
    user_email, user_roles, tenant, user_tenants
) -> ResponseReturnValue:
    """Accept a gap-fill suggestion to fill an odometer gap between trips."""
    try:
        svc = _get_trip_service()
        data = request.get_json()
        if not data:
            return jsonify({"success": False, "error": "Request body required"}), 400

        # Validate required fields
        required_fields = [
            "vehicle_id",
            "trip_date",
            "start_odometer",
            "end_odometer",
            "start_address",
            "end_address",
            "trip_category",
            "trip_purpose",
        ]
        missing = [f for f in required_fields if f not in data or data[f] is None]
        if missing:
            return jsonify(
                {
                    "success": False,
                    "error": f"Missing required fields: {', '.join(missing)}",
                }
            ), 400

        result = svc.create_gap_fill(tenant, data, user_email)
        return jsonify({"success": True, "data": result}), 201
    except ValueError as ve:
        return jsonify({"success": False, "error": str(ve)}), 400
    except Exception as e:  # noqa: BLE001
        logger.error("create_gap_fill error for %s: %s", tenant, e)
        return jsonify({"success": False, "error": "An internal error occurred"}), 500


@zzp_trip_bp.route("/api/zzp/trips/gaps", methods=["GET"])
@cognito_required(required_permissions=["zzp_crud"])
@tenant_required()
@module_required("ZZP")
def list_gaps(user_email, user_roles, tenant, user_tenants) -> ResponseReturnValue:
    """List unresolved gap-fill entries (purpose = 'Niet geregistreerd').

    Optional query param: vehicle_id (int) — filter by vehicle.
    Reference: Design §3.4
    """
    try:
        svc = _get_trip_service()
        vehicle_id = request.args.get("vehicle_id")
        gaps = svc.get_unresolved_gaps(tenant, vehicle_id=vehicle_id)
        return jsonify({"success": True, "data": gaps})
    except ValueError as ve:
        return jsonify({"success": False, "error": str(ve)}), 400
    except Exception as e:  # noqa: BLE001
        logger.error("list_gaps error for %s: %s", tenant, e)
        return jsonify({"success": False, "error": "An internal error occurred"}), 500


@zzp_trip_bp.route("/api/zzp/trips/unbilled", methods=["GET"])
@cognito_required(required_permissions=["zzp_crud"])
@tenant_required()
@module_required("ZZP")
def get_unbilled_trips(
    user_email, user_roles, tenant, user_tenants
) -> ResponseReturnValue:
    """Get unbilled billable trips for a client.

    Required query param: contact_id (int).
    Reference: Design §3.3 GET /api/zzp/trips/unbilled
    """
    try:
        contact_id = request.args.get("contact_id")
        if not contact_id:
            return jsonify(
                {"success": False, "error": "contact_id query parameter is required"}
            ), 400

        svc = _get_trip_service()
        trips = svc.get_unbilled_trips(tenant, int(contact_id))
        return jsonify({"success": True, "data": trips})
    except ValueError as ve:
        return jsonify({"success": False, "error": str(ve)}), 400
    except Exception as e:  # noqa: BLE001
        logger.error("get_unbilled_trips error for %s: %s", tenant, e)
        return jsonify({"success": False, "error": "An internal error occurred"}), 500


@zzp_trip_bp.route("/api/zzp/trips/summary", methods=["GET"])
@cognito_required(required_permissions=["zzp_crud"])
@tenant_required()
@module_required("ZZP")
def get_trip_summary(
    user_email, user_roles, tenant, user_tenants
) -> ResponseReturnValue:
    """Get yearly trip summary with category totals and monthly breakdown.

    Required query params: vehicle_id (int), year (int).

    Reference: Design §3.4 GET /api/zzp/trips/summary
    """
    try:
        vehicle_id = request.args.get("vehicle_id")
        year = request.args.get("year")

        if not vehicle_id or not year:
            return jsonify(
                {
                    "success": False,
                    "error": "vehicle_id and year query parameters are required",
                }
            ), 400

        svc = _get_trip_service()
        summary = svc.get_summary(tenant, int(vehicle_id), int(year))
        return jsonify({"success": True, "data": summary})
    except ValueError as ve:
        return jsonify({"success": False, "error": str(ve)}), 400
    except Exception as e:  # noqa: BLE001
        logger.error("get_trip_summary error for %s: %s", tenant, e)
        return jsonify({"success": False, "error": "An internal error occurred"}), 500


@zzp_trip_bp.route("/api/zzp/trips/<int:trip_id>", methods=["GET"])
@cognito_required(required_permissions=["zzp_crud"])
@tenant_required()
@module_required("ZZP")
def get_trip(
    user_email, user_roles, tenant, user_tenants, trip_id
) -> ResponseReturnValue:
    """Get a single trip by ID."""
    try:
        svc = _get_trip_service()
        trip = svc.get_trip(tenant, trip_id)
        if trip is None:
            return jsonify({"success": False, "error": "Trip not found"}), 404
        return jsonify({"success": True, "data": trip})
    except ValueError as ve:
        return jsonify({"success": False, "error": str(ve)}), 400
    except Exception as e:  # noqa: BLE001
        logger.error("get_trip error for %s/%s: %s", tenant, trip_id, e)
        return jsonify({"success": False, "error": "An internal error occurred"}), 500


@zzp_trip_bp.route("/api/zzp/trips/<int:trip_id>", methods=["PUT"])
@cognito_required(required_permissions=["zzp_crud"])
@tenant_required()
@module_required("ZZP")
def update_trip(
    user_email, user_roles, tenant, user_tenants, trip_id
) -> ResponseReturnValue:
    """Update/correct a trip. Requires correction_reason. Increments version, writes audit log.

    Reference: Design §3.2 PUT /api/zzp/trips/{id}
    """
    try:
        svc = _get_trip_service()
        data = request.get_json()
        if not data:
            return jsonify({"success": False, "error": "Request body required"}), 400

        correction_reason = data.pop("correction_reason", None)
        if not correction_reason:
            return jsonify(
                {"success": False, "error": "correction_reason is required"}
            ), 400

        trip = svc.update_trip(
            tenant, trip_id, data, correction_reason, updated_by=user_email
        )
        return jsonify({"success": True, "data": trip})
    except ValueError as ve:
        return jsonify({"success": False, "error": str(ve)}), 400
    except Exception as e:  # noqa: BLE001
        logger.error("update_trip error for %s/%s: %s", tenant, trip_id, e)
        return jsonify({"success": False, "error": "An internal error occurred"}), 500


@zzp_trip_bp.route("/api/zzp/trips/<int:trip_id>", methods=["DELETE"])
@cognito_required(required_permissions=["zzp_crud"])
@tenant_required()
@module_required("ZZP")
def cancel_trip(
    user_email, user_roles, tenant, user_tenants, trip_id
) -> ResponseReturnValue:
    """Soft-cancel a trip (sets is_cancelled = true). Requires cancel_reason.

    Reference: Design §3.2 DELETE /api/zzp/trips/{id}
    """
    try:
        svc = _get_trip_service()
        data = request.get_json()
        if not data:
            return jsonify({"success": False, "error": "Request body required"}), 400

        cancel_reason = data.get("cancel_reason")
        if not cancel_reason:
            return jsonify(
                {"success": False, "error": "cancel_reason is required"}
            ), 400

        svc.cancel_trip(tenant, trip_id, cancel_reason, cancelled_by=user_email)
        return jsonify({"success": True, "data": {"id": trip_id, "is_cancelled": True}})
    except ValueError as ve:
        return jsonify({"success": False, "error": str(ve)}), 400
    except Exception as e:  # noqa: BLE001
        logger.error("cancel_trip error for %s/%s: %s", tenant, trip_id, e)
        return jsonify({"success": False, "error": "An internal error occurred"}), 500


@zzp_trip_bp.route("/api/zzp/trips/<int:trip_id>/history", methods=["GET"])
@cognito_required(required_permissions=["zzp_crud"])
@tenant_required()
@module_required("ZZP")
def get_trip_history(
    user_email, user_roles, tenant, user_tenants, trip_id
) -> ResponseReturnValue:
    """Get correction audit trail for a trip.

    Reference: Design §3.2 GET /api/zzp/trips/{id}/history
    """
    try:
        svc = _get_trip_service()
        history = svc.get_trip_history(tenant, trip_id)
        return jsonify({"success": True, "data": history})
    except ValueError as ve:
        return jsonify({"success": False, "error": str(ve)}), 400
    except Exception as e:  # noqa: BLE001
        logger.error("get_trip_history error for %s/%s: %s", tenant, trip_id, e)
        return jsonify({"success": False, "error": "An internal error occurred"}), 500


# ── Route Preset Endpoints (Design §3.5) ──────────────────


@zzp_trip_bp.route("/api/zzp/route-presets", methods=["GET"])
@cognito_required(required_permissions=["zzp_crud"])
@tenant_required()
@module_required("ZZP")
def list_route_presets(
    user_email, user_roles, tenant, user_tenants
) -> ResponseReturnValue:
    """List route presets (top X by usage in last 6 months + manual presets)."""
    try:
        svc = _get_route_preset_service()
        presets = svc.get_suggestions(tenant)
        return jsonify({"success": True, "data": presets})
    except Exception as e:  # noqa: BLE001
        logger.error("list_route_presets error for %s: %s", tenant, e)
        return jsonify({"success": False, "error": "An internal error occurred"}), 500


@zzp_trip_bp.route("/api/zzp/route-presets", methods=["POST"])
@cognito_required(required_permissions=["zzp_crud"])
@tenant_required()
@module_required("ZZP")
def create_route_preset(
    user_email, user_roles, tenant, user_tenants
) -> ResponseReturnValue:
    """Create a manual route preset."""
    try:
        svc = _get_route_preset_service()
        data = request.get_json()
        if not data:
            return jsonify({"success": False, "error": "Request body required"}), 400
        preset = svc.create_preset(tenant, data)
        return jsonify({"success": True, "data": preset}), 201
    except ValueError as ve:
        return jsonify({"success": False, "error": str(ve)}), 400
    except Exception as e:  # noqa: BLE001
        logger.error("create_route_preset error for %s: %s", tenant, e)
        return jsonify({"success": False, "error": "An internal error occurred"}), 500


@zzp_trip_bp.route("/api/zzp/route-presets/<int:preset_id>", methods=["PUT"])
@cognito_required(required_permissions=["zzp_crud"])
@tenant_required()
@module_required("ZZP")
def update_route_preset(
    user_email, user_roles, tenant, user_tenants, preset_id
) -> ResponseReturnValue:
    """Update a route preset's defaults."""
    try:
        svc = _get_route_preset_service()
        data = request.get_json()
        if not data:
            return jsonify({"success": False, "error": "Request body required"}), 400
        preset = svc.update_preset(tenant, preset_id, data)
        return jsonify({"success": True, "data": preset})
    except ValueError as ve:
        return jsonify({"success": False, "error": str(ve)}), 400
    except Exception as e:  # noqa: BLE001
        logger.error("update_route_preset error for %s/%s: %s", tenant, preset_id, e)
        return jsonify({"success": False, "error": "An internal error occurred"}), 500


@zzp_trip_bp.route("/api/zzp/route-presets/<int:preset_id>", methods=["DELETE"])
@cognito_required(required_permissions=["zzp_crud"])
@tenant_required()
@module_required("ZZP")
def delete_route_preset(
    user_email, user_roles, tenant, user_tenants, preset_id
) -> ResponseReturnValue:
    """Delete a route preset."""
    try:
        svc = _get_route_preset_service()
        svc.delete_preset(tenant, preset_id)
        return jsonify({"success": True, "data": {"id": preset_id, "deleted": True}})
    except ValueError as ve:
        return jsonify({"success": False, "error": str(ve)}), 400
    except Exception as e:  # noqa: BLE001
        logger.error("delete_route_preset error for %s/%s: %s", tenant, preset_id, e)
        return jsonify({"success": False, "error": "An internal error occurred"}), 500
