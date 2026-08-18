"""
ZZP Trip Import/Export Routes: Import, export, and billing endpoints.

Extracted from zzp_trip_routes.py for file-size compliance (<500 lines).
Provides export (PDF/CSV/XLSX), CSV/Excel import with validation,
and invoice-from-trips billing endpoint.

Reference: .kiro/specs/ZZP/rittenregistratie/design.md §3.3, §3.4, §4.4
"""

import json
import logging

from flask import Blueprint, jsonify, make_response, request
from flask.typing import ResponseReturnValue

from auth.cognito_utils import cognito_required
from auth.tenant_context import tenant_required
from database import DatabaseManager
from services.module_registry import module_required
from services.parameter_service import ParameterService
from services.tax_rate_service import TaxRateService
from services.zzp_invoice_service import ZZPInvoiceService
from services.zzp_trip_export_service import TripExportService
from services.zzp_trip_import_service import TripImportService
from services.zzp_trip_service import TripService
from services.zzp_vehicle_service import VehicleService

logger = logging.getLogger(__name__)

zzp_trip_io_bp = Blueprint("zzp_trip_io", __name__)

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


def _get_invoice_service() -> ZZPInvoiceService:
    db = DatabaseManager(test_mode=_test_mode)
    tax_svc = TaxRateService(db)
    param_svc = ParameterService(db)
    return ZZPInvoiceService(
        db=db, tax_rate_service=tax_svc, parameter_service=param_svc
    )


def _get_export_service() -> TripExportService:
    db = DatabaseManager(test_mode=_test_mode)
    param_svc = ParameterService(db)
    return TripExportService(db=db, parameter_service=param_svc)


def _get_import_service() -> TripImportService:
    db = DatabaseManager(test_mode=_test_mode)
    param_svc = ParameterService(db)
    return TripImportService(db=db, parameter_service=param_svc)


# ── Export Endpoints (Design §3.4) ─────────────────────────


@zzp_trip_io_bp.route("/api/zzp/trips/export", methods=["GET"])
@cognito_required(required_permissions=["zzp_crud"])
@tenant_required()
@module_required("ZZP")
def export_trips(user_email, user_roles, tenant, user_tenants) -> ResponseReturnValue:
    """Export trips as PDF, CSV, or XLSX file download.

    Required query params: vehicle_id (int), year (int), format (pdf/csv/xlsx).
    Optional: trip_category (str), contact_id (int).

    Reference: Design §3.4 GET /api/zzp/trips/export
    """
    try:
        # Validate required params
        vehicle_id = request.args.get("vehicle_id")
        year = request.args.get("year")
        export_format = request.args.get("format")

        if not vehicle_id or not year or not export_format:
            return jsonify(
                {
                    "success": False,
                    "error": "vehicle_id, year, and format query parameters are required",
                }
            ), 400

        # Validate format
        export_format = export_format.lower()
        if export_format not in ("pdf", "csv", "xlsx"):
            return jsonify(
                {"success": False, "error": "format must be one of: pdf, csv, xlsx"}
            ), 400

        # Build optional filters
        filters = {}
        if request.args.get("trip_category"):
            filters["trip_category"] = request.args.get("trip_category")
        if request.args.get("contact_id"):
            filters["contact_id"] = request.args.get("contact_id")

        export_svc = _get_export_service()

        # Call appropriate export method
        if export_format == "pdf":
            file_bytes = export_svc.export_pdf(
                tenant, int(vehicle_id), int(year), filters
            )
            content_type = "application/pdf"
            ext = "pdf"
        elif export_format == "csv":
            file_bytes = export_svc.export_csv(
                tenant, int(vehicle_id), int(year), filters
            )
            content_type = "text/csv; charset=utf-8"
            ext = "csv"
        else:  # xlsx
            file_bytes = export_svc.export_xlsx(
                tenant, int(vehicle_id), int(year), filters
            )
            content_type = (
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
            ext = "xlsx"

        # Get vehicle license plate for filename
        vehicle_svc = _get_vehicle_service()
        vehicle = vehicle_svc.get_vehicle(tenant, int(vehicle_id))
        license_plate = (
            vehicle.get("license_plate", "onbekend") if vehicle else "onbekend"
        )
        # Sanitize license plate for filename (remove spaces/special chars)
        license_plate_safe = license_plate.replace(" ", "").replace("-", "")

        filename = f"rittenregistratie_{year}_{license_plate_safe}.{ext}"

        response = make_response(file_bytes)
        response.headers["Content-Type"] = content_type
        response.headers["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response
    except ValueError as ve:
        return jsonify({"success": False, "error": str(ve)}), 400
    except RuntimeError as re:
        logger.error("export_trips runtime error for %s: %s", tenant, re)
        return jsonify({"success": False, "error": str(re)}), 500
    except Exception as e:
        logger.error("export_trips error for %s: %s", tenant, e)
        return jsonify({"success": False, "error": "An internal error occurred"}), 500


# ── Import Endpoints (Design §4.4) ─────────────────────────


@zzp_trip_io_bp.route("/api/zzp/trips/import", methods=["POST"])
@cognito_required(required_permissions=["zzp_crud"])
@tenant_required()
@module_required("ZZP")
def import_trips(user_email, user_roles, tenant, user_tenants) -> ResponseReturnValue:
    """Upload and validate a CSV/Excel file for trip import."""
    try:
        svc = _get_import_service()

        file = request.files.get("file")
        if not file or not file.filename:
            return jsonify({"success": False, "error": "No file provided"}), 400

        vehicle_id = request.form.get("vehicle_id")
        if not vehicle_id:
            return jsonify({"success": False, "error": "vehicle_id is required"}), 400

        column_mapping_str = request.form.get("column_mapping")
        column_mapping = json.loads(column_mapping_str) if column_mapping_str else None

        # Parse the file
        parse_result = svc.parse_file(file.stream, file.filename, column_mapping)
        if not parse_result["success"]:
            return jsonify({"success": False, "error": parse_result["error"]}), 400

        # Validate
        validation_result = svc.validate_import(
            tenant, int(vehicle_id), parse_result["rows"]
        )
        return jsonify(validation_result)
    except json.JSONDecodeError:
        return jsonify({"success": False, "error": "Invalid column_mapping JSON"}), 400
    except Exception as e:
        logger.error("import_trips error for %s: %s", tenant, e)
        return jsonify({"success": False, "error": "An internal error occurred"}), 500


@zzp_trip_io_bp.route("/api/zzp/trips/import/commit", methods=["POST"])
@cognito_required(required_permissions=["zzp_crud"])
@tenant_required()
@module_required("ZZP")
def commit_import(user_email, user_roles, tenant, user_tenants) -> ResponseReturnValue:
    """Commit validated import rows as trip records."""
    try:
        svc = _get_import_service()
        data = request.get_json()
        if not data:
            return jsonify({"success": False, "error": "Request body required"}), 400

        vehicle_id = data.get("vehicle_id")
        if not vehicle_id:
            return jsonify({"success": False, "error": "vehicle_id is required"}), 400

        rows = data.get("rows")
        if not rows or not isinstance(rows, list):
            return jsonify(
                {"success": False, "error": "rows must be a non-empty list"}
            ), 400

        skip_error_rows = data.get("skip_error_rows", False)

        # If skip_error_rows is True, filter out error rows before commit
        if skip_error_rows:
            rows = [r for r in rows if r.get("_status") != "error"]

        result = svc.commit_import(tenant, int(vehicle_id), rows, created_by=user_email)
        return jsonify(result)
    except Exception as e:
        logger.error("commit_import error for %s: %s", tenant, e)
        return jsonify({"success": False, "error": "An internal error occurred"}), 500


@zzp_trip_io_bp.route("/api/zzp/trips/import/template", methods=["GET"])
@cognito_required(required_permissions=["zzp_read"])
@tenant_required()
@module_required("ZZP")
def get_import_template(
    user_email, user_roles, tenant, user_tenants
) -> ResponseReturnValue:
    """Download CSV template for trip import."""
    try:
        svc = _get_import_service()
        csv_bytes = svc.get_template_csv()
        response = make_response(csv_bytes)
        response.headers["Content-Type"] = "text/csv; charset=utf-8"
        response.headers["Content-Disposition"] = (
            "attachment; filename=ritten_template.csv"
        )
        return response
    except Exception as e:
        logger.error("get_import_template error for %s: %s", tenant, e)
        return jsonify({"success": False, "error": "An internal error occurred"}), 500


# ── Billing Endpoints (Design §3.3) ───────────────────────


@zzp_trip_io_bp.route("/api/zzp/invoices/from-trips", methods=["POST"])
@cognito_required(required_permissions=["zzp_crud"])
@tenant_required()
@module_required("ZZP")
def create_invoice_from_trips(
    user_email, user_roles, tenant, user_tenants
) -> ResponseReturnValue:
    """Create an invoice from selected trips.

    Request body: {contact_id, trip_ids, km_rate, invoice_date, payment_terms_days}
    Creates one invoice line per trip: description, quantity=distance_km, unit_price=km_rate.
    Marks trips as billed after invoice creation.

    Reference: Design §3.3 POST /api/zzp/invoices/from-trips
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({"success": False, "error": "Request body required"}), 400

        # Validate required fields
        required = ["contact_id", "trip_ids", "km_rate"]
        missing = [f for f in required if f not in data or data[f] is None]
        if missing:
            return jsonify(
                {
                    "success": False,
                    "error": f"Missing required fields: {', '.join(missing)}",
                }
            ), 400

        if not isinstance(data["trip_ids"], list) or len(data["trip_ids"]) == 0:
            return jsonify(
                {"success": False, "error": "trip_ids must be a non-empty list"}
            ), 400

        trip_service = _get_trip_service()
        invoice_service = _get_invoice_service()

        invoice = invoice_service.create_invoice_from_trips(
            tenant=tenant,
            contact_id=data["contact_id"],
            trip_ids=data["trip_ids"],
            km_rate=float(data["km_rate"]),
            data={
                "invoice_date": data.get("invoice_date"),
                "payment_terms_days": data.get("payment_terms_days"),
            },
            created_by=user_email,
            trip_service=trip_service,
        )
        return jsonify({"success": True, "data": invoice}), 201
    except ValueError as ve:
        return jsonify({"success": False, "error": str(ve)}), 400
    except RuntimeError as re:
        logger.error("create_invoice_from_trips runtime error for %s: %s", tenant, re)
        return jsonify({"success": False, "error": str(re)}), 500
    except Exception as e:
        logger.error("create_invoice_from_trips error for %s: %s", tenant, e)
        return jsonify({"success": False, "error": "An internal error occurred"}), 500
