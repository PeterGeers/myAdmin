"""Aangifte IB (Income Tax declaration) reporting endpoints.

Extracted from reporting_routes.py for file size management.
All endpoints are prefixed with /api/reports via blueprint registration.
"""

from flask import Blueprint, request, jsonify
from flask.typing import ResponseReturnValue
from database import DatabaseManager
from mutaties_cache import get_cache
from datetime import datetime
from auth.cognito_utils import cognito_required
from auth.tenant_context import tenant_required

aangifte_ib_bp = Blueprint("aangifte_ib", __name__)

# Global variables set by app.py
flag = False
logger = None


def set_test_mode(test_mode) -> None:
    """Set test mode flag"""
    global flag
    flag = test_mode


def set_logger(log_instance) -> None:
    """Set logger instance"""
    global logger
    logger = log_instance


@aangifte_ib_bp.route("/aangifte-ib", methods=["GET"])
@cognito_required(required_permissions=["reports_read"])
@tenant_required()
def aangifte_ib(user_email, user_roles, tenant, user_tenants) -> ResponseReturnValue:
    """Get Aangifte IB data grouped by Parent and Aangifte (using in-memory cache)"""
    try:
        # Get parameters
        year = request.args.get("year")
        administration = request.args.get(
            "administration", tenant
        )  # Default to current tenant

        if not year:
            return jsonify({"success": False, "error": "Year is required"}), 400

        # Validate user has access to requested administration
        if administration not in user_tenants:
            return jsonify(
                {"success": False, "error": "Access denied to administration"}
            ), 403

        # Get cache instance
        cache = get_cache()
        db = DatabaseManager(test_mode=flag)

        # Ensure cache is loaded (will auto-refresh if needed)
        cache.get_data(db)

        # Query from cache (much faster than SQL)
        summary_data = cache.query_aangifte_ib(
            year, administration, user_tenants=user_tenants
        )
        # Get ALL available years from database (not just cached years)
        available_years = cache.get_available_years(db)
        # Only show administrations user has access to
        available_administrations = [
            admin
            for admin in cache.get_available_administrations(year)
            if admin in user_tenants
        ]

        return jsonify(
            {
                "success": True,
                "data": summary_data,
                "available_years": available_years,
                "available_administrations": available_administrations,
            }
        )

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@aangifte_ib_bp.route("/aangifte-ib-details", methods=["GET"])
@cognito_required(required_permissions=["reports_read"])
@tenant_required()
def aangifte_ib_details(
    user_email, user_roles, tenant, user_tenants
) -> ResponseReturnValue:
    """Get underlying accounts for a specific Parent and Aangifte (using in-memory cache)"""
    try:
        # Get parameters
        year = request.args.get("year")
        administration = request.args.get(
            "administration", tenant
        )  # Default to current tenant
        parent = request.args.get("parent")
        aangifte = request.args.get("aangifte")

        if not all([year, parent, aangifte]):
            return jsonify(
                {"success": False, "error": "Year, parent, and aangifte are required"}
            ), 400

        # Validate user has access to requested administration
        if administration not in user_tenants:
            return jsonify(
                {"success": False, "error": "Access denied to administration"}
            ), 403

        # Get cache instance
        cache = get_cache()
        db = DatabaseManager(test_mode=flag)

        # Ensure cache is loaded (will auto-refresh if needed)
        cache.get_data(db)

        # Query from cache (much faster than SQL) with tenant filtering
        details_data = cache.query_aangifte_ib_details(
            year, administration, parent, aangifte, user_tenants
        )

        return jsonify(
            {
                "success": True,
                "data": details_data,
                "parent": parent,
                "aangifte": aangifte,
            }
        )

    except Exception as e:
        import traceback

        error_details = traceback.format_exc()
        print(f"Error in aangifte_ib_details: {error_details}", flush=True)
        return jsonify(
            {
                "success": False,
                "error": str(e),
                "details": error_details if flag else None,
            }
        ), 500


@aangifte_ib_bp.route("/aangifte-ib-export", methods=["POST"])
@cognito_required(required_permissions=["reports_export"])
@tenant_required()
def aangifte_ib_export(
    user_email, user_roles, tenant, user_tenants
) -> ResponseReturnValue:
    """Generate HTML export for Aangifte IB report using TemplateService with field mappings

    Supports multiple output destinations:
    - download: Return content to frontend for download (default)
    - gdrive: Upload to tenant's Google Drive
    - s3: Upload to AWS S3 (future implementation)
    """
    try:
        data = request.get_json()
        year = data.get("year")
        administration = data.get("administration", tenant)  # Default to current tenant
        report_data = data.get("data", [])
        output_destination = data.get(
            "output_destination", "download"
        )  # Default to download
        folder_id = data.get("folder_id")  # Optional Google Drive folder ID

        if not year:
            return jsonify({"success": False, "error": "Year is required"}), 400

        # Validate user has access to requested administration
        if administration == "all":
            return jsonify(
                {
                    "success": False,
                    "error": "A specific administration is required for export",
                }
            ), 400

        if administration not in user_tenants:
            return jsonify(
                {"success": False, "error": "Access denied to administration"}
            ), 403

        # Get cache instance for account details
        cache = get_cache()
        db = DatabaseManager(test_mode=flag)

        # Get consistent snapshot for the entire export operation
        snapshot = cache.get_snapshot(db)

        # Use report_generators to generate table rows
        from report_generators import generate_table_rows

        table_rows_data = generate_table_rows(
            report_data=report_data,
            cache=cache,
            year=year,
            administration=administration,
            user_tenants=user_tenants,
        )

        # Convert row data to HTML
        table_rows_html = _render_table_rows(table_rows_data)

        # Initialize TemplateService
        from services.template_service import TemplateService

        template_service = TemplateService(db)

        # Prepare template data
        template_data = {
            "year": str(year),
            "administration": administration if administration != "all" else "All",
            "generated_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "table_rows": table_rows_html,
        }

        # Try to get template metadata from database
        template_type = "aangifte_ib_html"
        metadata = None

        try:
            metadata = template_service.get_template_metadata(
                administration, template_type
            )
        except Exception as e:
            if logger:
                logger.warning(f"Could not get template metadata from database: {e}")

        # Load template
        template_content = None
        if metadata and metadata.get("template_file_id"):
            # Load from Google Drive
            try:
                template_content = template_service.fetch_template_from_drive(
                    metadata["template_file_id"], administration
                )
                field_mappings = metadata.get("field_mappings", {})
            except Exception as e:
                if logger:
                    logger.error(f"Failed to fetch template from Google Drive: {e}")
                # Fallback to filesystem
                template_content = None

        if not template_content:
            # Fallback: Load from filesystem
            import os

            template_path = os.path.join(
                os.path.dirname(__file__),
                "..",
                "..",
                "templates",
                "html",
                "aangifte_ib_template.html",
            )

            if not os.path.exists(template_path):
                if logger:
                    logger.error(f"Template not found: {template_path}")
                return jsonify({"success": False, "error": "Template not found"}), 500

            with open(template_path, "r", encoding="utf-8") as f:
                template_content = f.read()

            # Use default field mappings (simple placeholder replacement)
            field_mappings = {
                "fields": {
                    key: {"path": key, "format": "text"} for key in template_data.keys()
                },
                "formatting": {
                    "locale": "nl_NL",
                    "date_format": "%Y-%m-%d %H:%M:%S",
                    "number_decimals": 2,
                },
            }

        # Apply field mappings using TemplateService
        html_content = template_service.apply_field_mappings(
            template_content, template_data, field_mappings
        )

        # Generate filename
        filename = f"Aangifte_IB_{administration}_{year}.html"

        # Handle output destination
        from services.output_service import OutputService

        output_service = OutputService(db)

        output_result = output_service.handle_output(
            content=html_content,
            filename=filename,
            destination=output_destination,
            administration=administration,
            content_type="text/html",
            folder_id=folder_id,
        )

        # Return result based on destination
        if output_destination == "download":
            return jsonify(
                {
                    "success": True,
                    "html": output_result["content"],
                    "filename": output_result["filename"],
                }
            )
        else:
            # For gdrive or s3, return URL and metadata
            return jsonify(
                {
                    "success": True,
                    "destination": output_result["destination"],
                    "url": output_result.get("url"),
                    "filename": output_result["filename"],
                    "message": output_result["message"],
                }
            )

    except Exception as e:
        print(f"Error in aangifte_ib_export: {e}", flush=True)
        import traceback

        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500


def _render_table_rows(rows_data) -> str:
    """
    Convert row data dictionaries to HTML table rows.

    Args:
        rows_data: List of row dictionaries from generate_table_rows()

    Returns:
        HTML string of table rows
    """
    html_rows = []

    for row in rows_data:
        _row_type = row.get("row_type", "")
        css_class = row.get("css_class", "")
        parent = row.get("parent", "")
        aangifte = row.get("aangifte", "")
        description = row.get("description", "")
        amount = row.get("amount", "")
        indent_level = row.get("indent_level", 0)

        # Apply indentation class
        parent_td_class = ""
        if indent_level == 1:
            parent_td_class = ' class="indent-1"'
        elif indent_level == 2:
            parent_td_class = ' class="indent-2"'

        # Build table row
        html_row = f'<tr class="{css_class}">'
        html_row += f"<td{parent_td_class}>{parent}</td>"
        html_row += f"<td>{aangifte}</td>"
        html_row += f"<td>{description}</td>"
        html_row += f'<td class="amount">{amount}</td>'
        html_row += "</tr>"

        html_rows.append(html_row)

    return "\n".join(html_rows)


@aangifte_ib_bp.route("/aangifte-ib-xlsx-export", methods=["POST"])
@cognito_required(required_permissions=["reports_export"])
@tenant_required()
def aangifte_ib_xlsx_export(
    user_email, user_roles, tenant, user_tenants
) -> ResponseReturnValue:
    """Generate XLSX export for Aangifte IB with tenant filtering"""
    try:
        data = request.get_json()
        administrations = data.get("administrations", [])
        years = data.get("years", [])

        if not administrations or not years:
            return jsonify(
                {"success": False, "error": "Administrations and years are required"}
            ), 400

        # Validate all requested administrations against user_tenants
        unauthorized_admins = [
            admin for admin in administrations if admin not in user_tenants
        ]
        if unauthorized_admins:
            return jsonify(
                {
                    "success": False,
                    "error": f"Access denied to administrations: {', '.join(unauthorized_admins)}",
                }
            ), 403

        # Debug: Check available administrations (filtered by user_tenants)
        db = DatabaseManager(test_mode=flag)
        conn = db.get_connection()
        cursor = conn.cursor(dictionary=True)

        # Build query with tenant filtering — query base mutaties table directly
        placeholders = ", ".join(["%s"] * len(user_tenants))
        query = f"SELECT DISTINCT administration FROM mutaties WHERE administration IN ({placeholders}) ORDER BY administration"
        cursor.execute(query, user_tenants)
        available_admins = [row["administration"] for row in cursor.fetchall()]
        cursor.close()
        conn.close()

        from xlsx_export import XLSXExportProcessor

        xlsx_processor = XLSXExportProcessor(test_mode=flag)
        results = xlsx_processor.generate_xlsx_export(administrations, years)

        successful_results = [r for r in results if r["success"]]

        return jsonify(
            {
                "success": True,
                "results": results,
                "available_administrations": available_admins,
                "message": f"Generated {len(successful_results)} XLSX files out of {len(results)} requested",
            }
        )

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@aangifte_ib_bp.route("/aangifte-ib-xlsx-export-stream", methods=["POST"])
@cognito_required(required_permissions=["reports_export"])
@tenant_required()
def aangifte_ib_xlsx_export_stream(
    user_email, user_roles, tenant, user_tenants
) -> ResponseReturnValue:
    """Generate XLSX export for Aangifte IB with streaming progress and tenant filtering"""
    from flask import Response
    import json

    print("STREAMING ENDPOINT CALLED!")

    try:
        data = request.get_json()
        if not data:
            return jsonify({"success": False, "error": "No JSON data provided"}), 400

        administrations = data.get("administrations", [])
        years = data.get("years", [])

        if not administrations or not years:
            return jsonify(
                {"success": False, "error": "Administrations and years are required"}
            ), 400

        # Validate all requested administrations against user_tenants
        unauthorized_admins = [
            admin for admin in administrations if admin not in user_tenants
        ]
        if unauthorized_admins:
            return jsonify(
                {
                    "success": False,
                    "error": f"Access denied to administrations: {', '.join(unauthorized_admins)}",
                }
            ), 403

        def generate_progress():
            try:
                from xlsx_export import XLSXExportProcessor

                xlsx_processor = XLSXExportProcessor(test_mode=flag)

                # Send initial progress
                yield f"data: {json.dumps({'type': 'start', 'administrations': administrations, 'years': years}, default=str)}\n\n"

                # Process with progress updates
                for progress_data in xlsx_processor.generate_xlsx_export_with_progress(
                    administrations, years
                ):
                    yield f"data: {json.dumps(progress_data, default=str)}\n\n"

            except Exception as e:
                import traceback

                traceback.print_exc()
                yield f"data: {json.dumps({'type': 'error', 'error': str(e)})}\n\n"

        return Response(
            generate_progress(),
            mimetype="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    except Exception as e:
        import traceback

        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500


@aangifte_ib_bp.route("/aangifte-ib-xlsx-download", methods=["POST"])
@cognito_required(required_permissions=["reports_export"])
@tenant_required()
def aangifte_ib_xlsx_download(
    user_email, user_roles, tenant, user_tenants
) -> ResponseReturnValue:
    """Generate XLSX workbook for Aangifte IB and return as downloadable file.

    This endpoint generates just the Excel workbook (no file downloads from
    Google Drive/S3) and returns it directly as a file download.
    """
    from flask import send_file
    import os

    try:
        data = request.get_json()
        if not data:
            return jsonify({"success": False, "error": "No JSON data provided"}), 400

        administration = data.get("administration", tenant)
        year = data.get("year")

        if not administration or not year:
            return jsonify(
                {"success": False, "error": "Administration and year are required"}
            ), 400

        # Validate access
        if administration not in user_tenants:
            return jsonify(
                {
                    "success": False,
                    "error": f"Access denied to administration: {administration}",
                }
            ), 403

        from xlsx_export import XLSXExportProcessor

        xlsx_processor = XLSXExportProcessor(test_mode=flag)

        # Get ledger data
        ledger_data = xlsx_processor.make_ledgers(year, administration)

        if not ledger_data:
            return jsonify(
                {
                    "success": False,
                    "error": f"No data found for {administration} {year}",
                }
            ), 404

        # Create temp file for the XLSX
        import tempfile

        with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
            tmp_path = tmp.name

        try:
            # Write workbook to temp file
            xlsx_processor.write_workbook(ledger_data, tmp_path, "data", administration)

            # Send file as download
            filename = f"{administration}{year}.xlsx"
            return send_file(
                tmp_path,
                mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                as_attachment=True,
                download_name=filename,
            )
        finally:
            # Clean up temp file after response is sent
            import atexit

            atexit.register(lambda: os.path.exists(tmp_path) and os.remove(tmp_path))

    except Exception as e:
        import traceback

        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500
