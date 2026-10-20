"""
Folder Management Routes Blueprint

Handles folder listing and creation endpoints for Google Drive integration.
Extracted from app.py during refactoring (Phase 1.4)
"""

import os

from flask import Blueprint, jsonify, request
from flask.typing import ResponseReturnValue

from auth.cognito_utils import cognito_required
from auth.tenant_context import tenant_required
from google_drive_service import GoogleDriveService
from routes.error_responses import error_response
from services.storage_resolver import (
    create_s3_folder,
    list_s3_folders,
    resolve_storage_provider,
)

folder_bp = Blueprint("folders", __name__)

# Access to config from app.py
# This will be set by app.py after blueprint registration
config = None


def set_config(app_config) -> None:
    """Set the config from app.py"""
    global config
    config = app_config


@folder_bp.route("/api/folders", methods=["GET"])
@cognito_required(required_permissions=["invoices_read"])
def get_folders(user_email, user_roles) -> ResponseReturnValue:
    """Return available vendor folders with an optional case-insensitive
    substring filter (the ``regex`` query param is matched literally, not as a
    regular expression — see the ReDoS mitigation note below)."""
    try:
        # Get tenant from request header
        from auth.tenant_context import get_current_tenant

        tenant = get_current_tenant(request)

        if not tenant:
            return jsonify(
                {"error": "No tenant specified. Please select a tenant."}
            ), 400

        filter_pattern = request.args.get("regex")
        print(
            f"get_folders called for tenant={tenant}, filter={filter_pattern}",
            flush=True,
        )

        # Deliberate validation guard: cap the filter length before any matching.
        # A user-supplied value is attacker-controllable, so bound its size to keep
        # the (now substring-only) match cheap and avoid pathological inputs.
        if filter_pattern is not None and len(filter_pattern) > 128:
            return jsonify({"error": "Invalid regex pattern: too long"}), 400

        # Production mode - resolve storage provider
        try:
            provider = resolve_storage_provider(tenant)
            print(
                f"Production mode: provider={provider} for tenant={tenant}",
                flush=True,
            )

            if provider == "s3_shared":
                # S3 tenant: list folders from S3 prefixes
                folders = list_s3_folders(tenant)
                print(
                    f"S3: found {len(folders)} folders for tenant={tenant}",
                    flush=True,
                )
            else:
                # Google Drive tenant: use existing Drive service
                print(
                    f"Production mode: fetching Google Drive folders for tenant={tenant}",
                    flush=True,
                )
                drive_service = GoogleDriveService(administration=tenant)
                drive_folders = drive_service.list_subfolders()
                print(
                    f"Raw drive_folders result: {type(drive_folders)}, length: {len(drive_folders) if drive_folders else 0}",
                    flush=True,
                )

                # Extract folder names and deduplicate (Google Drive allows duplicate folder names)
                folder_names = [folder["name"] for folder in drive_folders]
                # Use dict.fromkeys() to preserve order while removing duplicates
                folders = list(dict.fromkeys(folder_names))

                if len(folder_names) != len(folders):
                    print(
                        f"Warning: Deduplicated {len(folder_names)} folders to {len(folders)} unique names",
                        flush=True,
                    )
                    # Log which folders were duplicated
                    from collections import Counter

                    duplicates = [
                        name
                        for name, count in Counter(folder_names).items()
                        if count > 1
                    ]
                    print(f"Duplicate folder names found: {duplicates}", flush=True)

                print(
                    f"Google Drive: found {len(folders)} unique folders for tenant={tenant}",
                    flush=True,
                )
        except Exception as e:
            print(
                f"Storage error for tenant={tenant}: {type(e).__name__}: {e}",
                flush=True,
            )
            import traceback

            traceback.print_exc()
            # Fallback to local folders if storage backend fails
            folders = list(config.vendor_folders.values())
            print(f"Fallback: returning {len(folders)} local folders", flush=True)

        # Apply a case-insensitive substring filter if provided.
        # No real caller passes a regex (the frontend fetches the full list and
        # filters client-side), so a user-supplied `re.compile` is pure ReDoS /
        # regex-injection surface (CodeQL py/regex-injection). A plain substring
        # match covers the only legitimate need and runs in linear time.
        if filter_pattern:
            needle = filter_pattern.lower()
            filtered_folders = [
                folder for folder in folders if needle in folder.lower()
            ]
            print(
                f"Filter '{filter_pattern}' narrowed {len(folders)} folders to {len(filtered_folders)}",
                flush=True,
            )
            folders = filtered_folders

        return jsonify(folders)
    except Exception as e:
        print(f"Error in get_folders: {e}", flush=True)
        return error_response(
            e, "Folder request failed", status=500, include_success=False
        )


@folder_bp.route("/api/create-folder", methods=["POST"])
@cognito_required(required_permissions=["invoices_create"])
@tenant_required()
def create_folder(user_email, user_roles, tenant, user_tenants) -> ResponseReturnValue:
    """Create a new folder in Google Drive"""
    try:
        data = request.get_json()
        folder_name = data.get("folderName")
        if folder_name:
            # Create local folder (always happens regardless of provider)
            folder_path = config.get_storage_folder(folder_name)
            config.ensure_folder_exists(folder_path)

            # Resolve storage provider for this tenant
            provider = resolve_storage_provider(tenant)
            print(f"create_folder: provider={provider} for tenant={tenant}", flush=True)

            if provider == "s3_shared":
                # S3 tenant: create folder marker in S3
                try:
                    s3_result = create_s3_folder(tenant, folder_name)
                    print(
                        f"Created S3 folder marker for: {folder_name}, tenant={tenant}",
                        flush=True,
                    )
                    return jsonify(
                        {
                            "success": True,
                            "path": folder_path,
                            "drive_folder": s3_result,
                        }
                    )
                except Exception as s3_error:
                    print(
                        f"S3 folder creation failed for tenant {tenant}: {s3_error}",
                        flush=True,
                    )
                    return jsonify({"success": True, "path": folder_path})
            else:
                # Google Drive tenant: create folder in correct parent
                try:
                    print(
                        f"Creating Google Drive folder for tenant: {tenant}", flush=True
                    )
                    drive_service = GoogleDriveService(administration=tenant)
                    use_test = os.getenv("TEST_MODE", "false").lower() == "true"
                    parent_folder_id = (
                        os.getenv("TEST_FACTUREN_FOLDER_ID")
                        if use_test
                        else os.getenv("FACTUREN_FOLDER_ID")
                    )

                    if parent_folder_id:
                        drive_result = drive_service.create_folder(
                            folder_name, parent_folder_id
                        )
                        print(
                            f"Created Google Drive folder: {folder_name} in {'test' if use_test else 'production'} parent for tenant {tenant}",
                            flush=True,
                        )
                        return jsonify(
                            {
                                "success": True,
                                "path": folder_path,
                                "drive_folder": drive_result,
                            }
                        )
                except Exception as drive_error:
                    print(
                        f"Google Drive folder creation failed for tenant {tenant}: {drive_error}",
                        flush=True,
                    )

            return jsonify({"success": True, "path": folder_path})
        return jsonify({"success": False, "error": "No folder name provided"}), 400
    except Exception as e:
        return error_response(e, "Folder request failed", status=500)
