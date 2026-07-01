"""
SysAdmin Invoice Processing Test Tool Endpoints

API endpoints for testing the invoice processing pipeline in dry-run mode.
Provides file upload processing, custom prompt re-runs, and vendor history lookup.

All endpoints require the SysAdmin role. No tenant isolation needed — the test tool
is tenant-agnostic (SysAdmin operates across tenants).
"""

import re
import os
import tempfile
from flask import Blueprint, request, jsonify
from flask.typing import ResponseReturnValue
from auth.cognito_utils import cognito_required
from services.invoice_test_service import InvoiceTestService
import logging

# Initialize logger
logger = logging.getLogger(__name__)

# Create blueprint
sysadmin_test_tool_bp = Blueprint("sysadmin_test_tool", __name__)

# Constants
ALLOWED_EXTENSIONS = {"pdf", "jpg", "jpeg", "png", "csv", "eml", "mhtml"}
MAX_FILE_SIZE_BYTES = 20 * 1024 * 1024  # 20 MB
VENDOR_NAME_PATTERN = re.compile(r"^[a-zA-Z0-9_ -]{1,100}$")
MAX_PROMPT_LENGTH = 10_000
MIN_PROMPT_LENGTH = 1


def _validate_file_extension(filename: str) -> bool:
    """Check if file has an allowed extension (case-insensitive).

    Args:
        filename: The uploaded filename to validate.

    Returns:
        True if extension is allowed, False otherwise.
    """
    if not filename or "." not in filename:
        return False
    extension = filename.rsplit(".", 1)[1].lower()
    return extension in ALLOWED_EXTENSIONS


def _validate_file_size(file) -> bool:
    """Check if file size is within the 20 MB limit.

    Seeks to end to determine size, then resets position.

    Args:
        file: The uploaded file object.

    Returns:
        True if file is within size limit, False otherwise.
    """
    file.seek(0, os.SEEK_END)
    size = file.tell()
    file.seek(0)
    return size <= MAX_FILE_SIZE_BYTES


def _validate_vendor_name(vendor_name: str) -> bool:
    """Validate vendor name matches allowed pattern.

    Pattern: alphanumeric, hyphens, underscores, 1-100 characters.

    Args:
        vendor_name: The vendor/folder name to validate.

    Returns:
        True if vendor name is valid, False otherwise.
    """
    return bool(VENDOR_NAME_PATTERN.match(vendor_name))


def _validate_prompt_length(prompt: str) -> bool:
    """Validate prompt is between 1 and 10,000 characters.

    Args:
        prompt: The custom prompt text to validate.

    Returns:
        True if prompt length is valid, False otherwise.
    """
    return MIN_PROMPT_LENGTH <= len(prompt) <= MAX_PROMPT_LENGTH


@sysadmin_test_tool_bp.route("/process", methods=["POST"])
@cognito_required(required_roles=["SysAdmin"])
def process_file(user_email, user_roles) -> ResponseReturnValue:
    """
    Upload and process a file through the invoice pipeline in dry-run mode.

    Authorization: SysAdmin role required

    Request: multipart/form-data
        - file: Invoice file (PDF/JPG/JPEG/PNG/CSV/EML/MHTML, max 20 MB)
        - folderName: Optional vendor/folder name (default: "TestVendor")
        - administration: Optional tenant identifier for vendor history lookup
    """
    try:
        # Validate file presence
        if "file" not in request.files:
            return jsonify({"success": False, "error": "No file provided"}), 400

        file = request.files["file"]

        if not file.filename:
            return jsonify({"success": False, "error": "No file selected"}), 400

        # Validate file extension
        if not _validate_file_extension(file.filename):
            allowed = ", ".join(sorted(ext.upper() for ext in ALLOWED_EXTENSIONS))
            return jsonify(
                {
                    "success": False,
                    "error": f"Unsupported file type. Allowed types: {allowed}",
                }
            ), 400

        # Validate file size
        if not _validate_file_size(file):
            return jsonify(
                {"success": False, "error": "File exceeds maximum size of 20 MB"}
            ), 400

        # Validate file is not empty (0 bytes)
        file.seek(0, os.SEEK_END)
        file_size = file.tell()
        file.seek(0)
        if file_size == 0:
            return jsonify({"success": False, "error": "File is empty (0 bytes)"}), 400

        # Validate vendor/folder name if provided
        folder_name = request.form.get("folderName", "TestVendor")
        if folder_name and not _validate_vendor_name(folder_name):
            return jsonify(
                {
                    "success": False,
                    "error": "Invalid vendor name. Must be 1-100 characters: alphanumeric, hyphens, underscores only",
                }
            ), 400

        administration = request.form.get("administration")

        # Save uploaded file to temp location
        extension = file.filename.rsplit(".", 1)[1].lower()
        fd, temp_file_path = tempfile.mkstemp(suffix=f".{extension}")
        try:
            os.close(fd)
            file.save(temp_file_path)
        except Exception:
            # Cleanup on save failure
            if os.path.exists(temp_file_path):
                os.remove(temp_file_path)
            raise

        # Process file through the pipeline (service handles temp file cleanup)
        service = InvoiceTestService()
        result = service.process_file_dry_run(
            temp_file_path, folder_name, administration
        )

        return jsonify(
            {
                "success": True,
                "pipeline_result": result.get("pipeline_result"),
                "performance": result.get("performance"),
                "ai_usage_preview": result.get("ai_usage_preview"),
                "execution_log": result.get("execution_log", ""),
                "errors": result.get("errors", []),
                "prompt_used": result.get("prompt_used", ""),
            }
        ), 200

    except Exception as e:
        logger.error(f"Process file error: {e}", exc_info=True)
        print(f"Process file error: {e}", flush=True)
        return jsonify({"success": False, "error": str(e)}), 500


@sysadmin_test_tool_bp.route("/rerun-prompt", methods=["POST"])
@cognito_required(required_roles=["SysAdmin"])
def rerun_prompt(user_email, user_roles) -> ResponseReturnValue:
    """
    Re-run AI extraction with a custom prompt against previously extracted text.

    Authorization: SysAdmin role required

    Request: application/json
        - text_content: The raw extracted text to run AI against
        - custom_prompt: Modified extraction prompt (1-10,000 characters)
        - vendor_hint: Optional vendor name for context
    """
    try:
        data = request.get_json(silent=True)

        if not data:
            return jsonify({"success": False, "error": "Request body is required"}), 400

        # Validate text_content
        text_content = data.get("text_content")
        if not text_content:
            return jsonify({"success": False, "error": "text_content is required"}), 400

        # Validate custom_prompt
        custom_prompt = data.get("custom_prompt")
        if custom_prompt is None:
            return jsonify(
                {"success": False, "error": "custom_prompt is required"}
            ), 400

        if not _validate_prompt_length(custom_prompt):
            return jsonify(
                {
                    "success": False,
                    "error": f"Prompt must be between {MIN_PROMPT_LENGTH} and {MAX_PROMPT_LENGTH} characters",
                }
            ), 400

        vendor_hint = data.get("vendor_hint")

        # Call InvoiceTestService to re-run AI extraction with custom prompt
        service = InvoiceTestService()
        result = service.rerun_with_custom_prompt(
            text_content, custom_prompt, vendor_hint
        )

        # Return HTTP 422 for sanitization rejection or validation failures
        if "error" in result and not result.get("success", True):
            return jsonify(result), 422

        return jsonify(result), 200

    except Exception as e:
        logger.error(f"Rerun prompt error: {e}", exc_info=True)
        print(f"Rerun prompt error: {e}", flush=True)
        return jsonify({"success": False, "error": str(e)}), 500


@sysadmin_test_tool_bp.route("/vendor-history", methods=["GET"])
@cognito_required(required_roles=["SysAdmin"])
def vendor_history(user_email, user_roles) -> ResponseReturnValue:
    """
    Get previous transactions for a vendor.

    Authorization: SysAdmin role required

    Query Parameters:
        - folderName: Required. Vendor/folder name to look up.
        - administration: Optional. Tenant identifier to scope the lookup.
    """
    try:
        # Validate folderName
        folder_name = request.args.get("folderName")
        if not folder_name:
            return jsonify({"success": False, "error": "folderName is required"}), 400

        if not _validate_vendor_name(folder_name):
            return jsonify(
                {
                    "success": False,
                    "error": "Invalid vendor name. Must be 1-100 characters: alphanumeric, hyphens, underscores only",
                }
            ), 400

        administration = request.args.get("administration")

        # Call service to get vendor history
        service = InvoiceTestService()
        transactions = service.get_vendor_history(folder_name, administration)

        return jsonify(
            {
                "success": True,
                "vendor_name": folder_name,
                "transactions": transactions,
                "count": len(transactions),
            }
        ), 200

    except Exception as e:
        logger.error(f"Vendor history error: {e}", exc_info=True)
        print(f"Vendor history error: {e}", flush=True)
        return jsonify({"success": False, "error": str(e)}), 500
