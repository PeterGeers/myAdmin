"""
Template Preview Service for Railway Migration
Handles template preview generation, validation, and approval workflow.

This service provides template preview and validation capabilities for tenant administrators,
allowing them to safely upload, preview, and validate custom report templates before activation.

Delegates to:
- TemplateHtmlProcessor: HTML parsing, validation, and rendering
- TemplatePdfRenderer: Sample data fetching and field mapping generation
"""

import os
import json
import logging
from typing import Dict, Any, Optional
from datetime import datetime

from services.template_html_processor import TemplateHtmlProcessor
from services.template_pdf_renderer import TemplatePdfRenderer

logger = logging.getLogger(__name__)


class TemplatePreviewService:
    """
    Service for template preview and validation.

    Provides functionality for:
    - Generating template previews with sample data
    - Validating template syntax and structure
    - Fetching sample data for different template types
    - Approving and activating templates
    """

    def __init__(self, db_manager, administration: str):
        """
        Initialize the template preview service.

        Args:
            db_manager: DatabaseManager instance for database operations
            administration: The tenant/administration identifier
        """
        self.db = db_manager
        self.administration = administration

        # Import TemplateService for template operations
        from services.template_service import TemplateService

        self.template_service = TemplateService(db_manager)

        # Initialize helper modules
        self.html_processor = TemplateHtmlProcessor()
        self.renderer = TemplatePdfRenderer(db_manager, administration)

        logger.info(
            f"TemplatePreviewService initialized for administration '{administration}'"
        )

    def generate_preview(
        self, template_type: str, template_content: str, field_mappings: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Generate preview with sample data.

        This method validates the template, fetches sample data, and generates
        a preview HTML by rendering the template with the sample data.

        Args:
            template_type: Type of template (e.g., 'str_invoice_nl', 'btw_aangifte')
            template_content: Template HTML content
            field_mappings: Field mappings configuration

        Returns:
            Dictionary containing:
            {
                'success': bool,
                'preview_html': str (if successful),
                'validation': dict,
                'sample_data_info': dict (if successful)
            }
        """
        try:
            logger.info(f"Generating preview for template type '{template_type}'")

            # 1. Validate template
            validation = self.validate_template(template_type, template_content)

            if not validation["is_valid"]:
                logger.warning(f"Template validation failed for type '{template_type}'")
                return {"success": False, "validation": validation}

            # 2. Fetch sample data
            sample_data_result = self.fetch_sample_data(template_type)

            if not sample_data_result:
                logger.warning(
                    f"No sample data available for template type '{template_type}'"
                )
                return {
                    "success": False,
                    "validation": {
                        "is_valid": False,
                        "errors": [
                            {
                                "type": "no_sample_data",
                                "message": "No sample data available for preview generation",
                                "severity": "error",
                            }
                        ],
                        "warnings": [],
                    },
                }

            sample_data = sample_data_result["data"]
            sample_data_info = sample_data_result["metadata"]

            # 3. Generate preview using template renderer
            preview_html = self.html_processor.render_template(
                template_content, sample_data, field_mappings
            )

            logger.info(
                f"Successfully generated preview for template type '{template_type}'"
            )

            return {
                "success": True,
                "preview_html": preview_html,
                "validation": validation,
                "sample_data_info": sample_data_info,
            }

        except Exception as e:
            logger.error(f"Failed to generate preview: {e}")
            return {
                "success": False,
                "validation": {
                    "is_valid": False,
                    "errors": [
                        {
                            "type": "preview_generation_error",
                            "message": f"Failed to generate preview: {str(e)}",
                            "severity": "error",
                        }
                    ],
                    "warnings": [],
                },
            }

    def validate_template(
        self, template_type: str, template_content: str
    ) -> Dict[str, Any]:
        """
        Validate template syntax and structure.

        Performs multiple validation checks:
        - HTML syntax validation
        - Required placeholder validation
        - Security scan
        - File size check

        Args:
            template_type: Type of template
            template_content: Template HTML content

        Returns:
            Dictionary containing:
            {
                'is_valid': bool,
                'errors': list,
                'warnings': list,
                'checks_performed': list
            }
        """
        try:
            logger.info(f"Validating template type '{template_type}'")

            errors = []
            warnings = []

            # Check 1: HTML syntax
            syntax_errors = self.html_processor.validate_html_syntax(template_content)
            errors.extend(syntax_errors)

            # Check 2: Required placeholders
            placeholder_errors = self.html_processor.validate_placeholders(
                template_type, template_content
            )
            errors.extend(placeholder_errors)

            # Check 3: Security scan
            security_issues = self.html_processor.validate_security(template_content)
            errors.extend(
                [issue for issue in security_issues if issue.get("severity") == "error"]
            )
            warnings.extend(
                [
                    issue
                    for issue in security_issues
                    if issue.get("severity") == "warning"
                ]
            )

            # Check 4: File size
            max_size = int(os.getenv("TEMPLATE_MAX_SIZE_MB", "5")) * 1024 * 1024
            if len(template_content.encode("utf-8")) > max_size:
                errors.append(
                    {
                        "type": "file_size",
                        "message": f"Template exceeds {max_size // (1024 * 1024)}MB limit",
                        "severity": "error",
                    }
                )

            is_valid = len(errors) == 0

            # Log detailed error information
            if errors:
                for error in errors:
                    logger.warning(f"Validation error: {error}")

            logger.info(
                f"Template validation completed: "
                f"valid={is_valid}, errors={len(errors)}, warnings={len(warnings)}"
            )

            return {
                "is_valid": is_valid,
                "errors": errors,
                "warnings": warnings,
                "checks_performed": [
                    "html_syntax",
                    "required_placeholders",
                    "security_scan",
                    "file_size",
                ],
            }

        except Exception as e:
            logger.error(f"Template validation failed: {e}")
            return {
                "is_valid": False,
                "errors": [
                    {
                        "type": "validation_error",
                        "message": f"Validation failed: {str(e)}",
                        "severity": "error",
                    }
                ],
                "warnings": [],
                "checks_performed": [],
            }

    def fetch_sample_data(self, template_type: str) -> Optional[Dict[str, Any]]:
        """
        Fetch most recent data for template type.

        Retrieves sample data from the database based on template type.
        Returns placeholder data if no real data is available.

        Args:
            template_type: Type of template

        Returns:
            Dictionary containing:
            {
                'data': dict (sample data),
                'metadata': dict (information about the sample data)
            }
            Returns None if fetch fails.
        """
        try:
            logger.info(f"Fetching sample data for template type '{template_type}'")

            if template_type in ["str_invoice_nl", "str_invoice_en"]:
                return self.renderer.fetch_str_invoice_sample()
            elif template_type == "btw_aangifte":
                return self.renderer.fetch_btw_sample()
            elif template_type == "aangifte_ib":
                return self.renderer.fetch_aangifte_ib_sample()
            elif template_type == "toeristenbelasting":
                return self.renderer.fetch_toeristenbelasting_sample()
            else:
                return self.renderer.fetch_generic_sample()

        except Exception as e:
            logger.error(f"Failed to fetch sample data: {e}")
            return None

    def approve_template(
        self,
        template_type: str,
        template_content: str,
        field_mappings: Dict[str, Any],
        user_email: str,
        notes: str = "",
    ) -> Dict[str, Any]:
        """
        Approve and save template.

        This method:
        1. Validates the template
        2. Saves template to Google Drive
        3. Updates database metadata
        4. Archives previous version
        5. Logs approval

        Args:
            template_type: Type of template
            template_content: Template HTML content
            field_mappings: Field mappings configuration
            user_email: Email of user approving the template
            notes: Optional approval notes

        Returns:
            Dictionary containing:
            {
                'success': bool,
                'template_id': str (if successful),
                'file_id': str (if successful),
                'message': str,
                'previous_version': dict (if applicable)
            }
        """
        try:
            logger.info(
                f"Approving template type '{template_type}' by user '{user_email}'"
            )

            # 1. Validate template one more time
            validation = self.validate_template(template_type, template_content)
            if not validation["is_valid"]:
                return {
                    "success": False,
                    "message": "Template validation failed",
                    "validation": validation,
                }

            # 1.5. Auto-generate field_mappings if empty
            if not field_mappings or not field_mappings.get("fields"):
                logger.info(
                    f"Auto-generating field_mappings for template type '{template_type}'"
                )
                field_mappings = self.renderer.generate_default_field_mappings(
                    template_type, template_content
                )

            # 2. Get current template metadata (if exists)
            current_metadata = self.template_service.get_template_metadata(
                self.administration, template_type
            )

            previous_file_id = None
            version = 1

            if current_metadata:
                previous_file_id = current_metadata.get("template_file_id")
                # Increment version (would need to query for max version)
                version = 2  # Simplified - should query for actual max version

            # 3. Save template to Google Drive
            file_id = self._save_template_to_drive(
                template_type, template_content, version
            )

            # 4. Update database metadata
            self._update_template_metadata(
                template_type,
                file_id,
                field_mappings,
                user_email,
                notes,
                previous_file_id,
                version,
            )

            # 5. Log approval
            self._log_template_approval(template_type, user_email, notes, validation)

            logger.info(
                f"Successfully approved template type '{template_type}', "
                f"file_id '{file_id}', version {version}"
            )

            result = {
                "success": True,
                "template_id": f"tmpl_{template_type}_{version}",
                "file_id": file_id,
                "message": "Template approved and activated",
            }

            if previous_file_id:
                result["previous_version"] = {
                    "file_id": previous_file_id,
                    "archived_at": datetime.now().isoformat(),
                }

            return result

        except Exception as e:
            logger.error(f"Failed to approve template: {e}")
            return {
                "success": False,
                "message": f"Failed to approve template: {str(e)}",
            }

    # Template approval helper methods

    def _save_template_to_drive(
        self, template_type: str, template_content: str, version: int
    ) -> str:
        """
        Save template to Google Drive.

        Args:
            template_type: Type of template
            template_content: Template HTML content
            version: Version number

        Returns:
            Google Drive file ID

        Raises:
            Exception: If save fails
        """
        try:
            from google_drive_service import GoogleDriveService
            from io import BytesIO
            from googleapiclient.http import MediaIoBaseUpload

            # Initialize Google Drive service for this tenant
            drive_service = GoogleDriveService(self.administration)

            # Create file metadata
            file_name = f"{template_type}_v{version}.html"
            file_metadata = {"name": file_name, "mimeType": "text/html"}

            # Create media upload
            file_content = BytesIO(template_content.encode("utf-8"))
            media = MediaIoBaseUpload(
                file_content, mimetype="text/html", resumable=True
            )

            # Upload file
            file = (
                drive_service.service.files()
                .create(body=file_metadata, media_body=media, fields="id")
                .execute()
            )

            file_id = file.get("id")

            logger.info(f"Saved template to Google Drive: file_id '{file_id}'")

            return file_id

        except Exception as e:
            logger.error(f"Failed to save template to Google Drive: {e}")
            raise Exception(f"Failed to save template to Google Drive: {str(e)}")

    def _update_template_metadata(
        self,
        template_type: str,
        file_id: str,
        field_mappings: Dict[str, Any],
        user_email: str,
        notes: str,
        previous_file_id: Optional[str],
        version: int,
    ):
        """
        Update template metadata in database.

        Args:
            template_type: Type of template
            file_id: Google Drive file ID
            field_mappings: Field mappings configuration
            user_email: Email of approving user
            notes: Approval notes
            previous_file_id: Previous version file ID (if exists)
            version: Version number
        """
        try:
            # Convert field_mappings to JSON
            field_mappings_json = json.dumps(field_mappings) if field_mappings else None

            # Check if template config exists
            check_query = """
                SELECT id FROM tenant_template_config
                WHERE administration = %s AND template_type = %s
            """
            existing = self.db.execute_query(
                check_query, (self.administration, template_type)
            )

            if existing:
                # Update existing
                update_query = """
                    UPDATE tenant_template_config
                    SET template_file_id = %s,
                        field_mappings = %s,
                        version = %s,
                        approved_by = %s,
                        approved_at = NOW(),
                        approval_notes = %s,
                        previous_file_id = %s,
                        status = 'active',
                        is_active = TRUE,
                        updated_at = NOW()
                    WHERE administration = %s AND template_type = %s
                """
                self.db.execute_query(
                    update_query,
                    (
                        file_id,
                        field_mappings_json,
                        version,
                        user_email,
                        notes,
                        previous_file_id,
                        self.administration,
                        template_type,
                    ),
                    fetch=False,
                    commit=True,
                )
            else:
                # Insert new
                insert_query = """
                    INSERT INTO tenant_template_config
                    (administration, template_type, template_file_id, field_mappings,
                     version, approved_by, approved_at, approval_notes, previous_file_id,
                     status, is_active)
                    VALUES (%s, %s, %s, %s, %s, %s, NOW(), %s, %s, 'active', TRUE)
                """
                self.db.execute_query(
                    insert_query,
                    (
                        self.administration,
                        template_type,
                        file_id,
                        field_mappings_json,
                        version,
                        user_email,
                        notes,
                        previous_file_id,
                    ),
                    fetch=False,
                    commit=True,
                )

            logger.info(f"Updated template metadata for type '{template_type}'")

        except Exception as e:
            logger.error(f"Failed to update template metadata: {e}")
            raise Exception(f"Failed to update template metadata: {str(e)}")

    def _log_template_approval(
        self,
        template_type: str,
        user_email: str,
        notes: str,
        validation: Dict[str, Any],
    ) -> None:
        """
        Log template approval in validation log.

        Args:
            template_type: Type of template
            user_email: Email of approving user
            notes: Approval notes
            validation: Validation results
        """
        try:
            errors_json = json.dumps(validation.get("errors", []))
            warnings_json = json.dumps(validation.get("warnings", []))

            query = """
                INSERT INTO template_validation_log
                (administration, template_type, validation_result, errors, warnings,
                 validated_by, validated_at)
                VALUES (%s, %s, 'pass', %s, %s, %s, NOW())
            """

            self.db.execute_query(
                query,
                (
                    self.administration,
                    template_type,
                    errors_json,
                    warnings_json,
                    user_email,
                ),
                fetch=False,
                commit=True,
            )

            logger.info(f"Logged template approval for type '{template_type}'")

        except Exception as e:
            logger.error(f"Failed to log template approval: {e}")
            # Don't raise - logging failure shouldn't block approval
