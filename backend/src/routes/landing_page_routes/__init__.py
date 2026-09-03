"""
Landing Page Routes

This module provides API endpoints for managing tenant landing page slugs,
draft editing, publishing/unpublishing landing pages, version history,
rollback, image uploads, resolving slugs for public delivery, and domain
configuration.

Endpoints:
- GET  /api/landing/slug              - Get current tenant's slug
- PUT  /api/landing/slug              - Set/update tenant's slug
- POST /api/landing/slug/validate     - Validate slug format + availability
- GET  /api/landing/domains           - Get Jabaki + custom domain status
- POST /api/landing/domains/jabaki/enable  - Enable Jabaki subdomain
- POST /api/landing/domains/jabaki/disable - Disable Jabaki subdomain
- POST /api/landing/domains/custom         - Register custom domain
- POST /api/landing/domains/custom/verify  - Verify custom domain cert status
- DELETE /api/landing/domains/custom        - Remove custom domain
- GET  /api/landing/draft             - Load current draft from DynamoDB
- PUT  /api/landing/draft             - Save draft to DynamoDB (auto-save)
- POST /api/landing/publish           - Publish current draft to S3
- POST /api/landing/unpublish         - Take landing page offline
- GET  /api/landing/versions          - List published version history
- POST /api/landing/rollback          - Rollback to a previous version
- POST /api/landing/images/upload     - Upload image to public S3 bucket
- GET  /api/public/landing/resolve/<slug> - Public: resolve slug -> administration
- POST /api/public/landing/<slug>/contact - Public: submit contact form inquiry

The endpoint handlers are split across cohesive submodules under
``routes.landing_page_routes``:

- :mod:`routes.landing_page_routes.slug_endpoints`
- :mod:`routes.landing_page_routes.domain_endpoints`
- :mod:`routes.landing_page_routes.draft_endpoints`
- :mod:`routes.landing_page_routes.version_endpoints`
- :mod:`routes.landing_page_routes.image_endpoints`
- :mod:`routes.landing_page_routes.branding_endpoints`
- :mod:`routes.landing_page_routes.public_endpoints`
- :mod:`routes.landing_page_routes.sysadmin_endpoints`

Note: Register this blueprint in app.py:
    from routes.landing_page_routes import landing_page_bp
    app.register_blueprint(landing_page_bp)
"""

import logging
import os

from flask import Blueprint

from database import DatabaseManager
from services.domain_service import DomainService
from services.media_asset_service import MediaAssetService
from services.parameter_service import ParameterService
from services.tenant_slug_service import TenantSlugService

logger = logging.getLogger(__name__)

landing_page_bp = Blueprint("landing_page", __name__)


def _get_slug_service() -> TenantSlugService:
    """Create a TenantSlugService instance with current DB config."""
    test_mode = os.getenv("TEST_MODE", "false").lower() == "true"
    db = DatabaseManager(test_mode=test_mode)
    return TenantSlugService(db)


def _get_domain_service() -> DomainService:
    """Create a DomainService instance with current DB config."""
    test_mode = os.getenv("TEST_MODE", "false").lower() == "true"
    db = DatabaseManager(test_mode=test_mode)
    return DomainService(db)


def _get_landing_page_service():
    """Create a LandingPageService instance."""
    from services.landing_page_service import LandingPageService

    return LandingPageService()


def _get_publish_service():
    """Create a LandingPagePublishService instance with dependencies."""
    from services.landing_page_publish_service import LandingPagePublishService
    from services.landing_page_service import LandingPageService

    test_mode = os.getenv("TEST_MODE", "false").lower() == "true"
    db = DatabaseManager(test_mode=test_mode)

    landing_page_svc = LandingPageService()
    param_svc = ParameterService(db)
    slug_svc = TenantSlugService(db)

    return LandingPagePublishService(
        landing_page_service=landing_page_svc,
        parameter_service=param_svc,
        slug_service=slug_svc,
        db_manager=db,
    )


def _get_parameter_service():
    """Create a ParameterService instance."""
    test_mode = os.getenv("TEST_MODE", "false").lower() == "true"
    db = DatabaseManager(test_mode=test_mode)
    return ParameterService(db)


def _record_audit_event(
    tenant: str,
    action: str,
    version: int | None,
    performed_by: str,
    details: str | None = None,
) -> None:
    """
    Record a landing page audit event in MySQL.

    Inserts into the landing_page_audit table. Failures are logged but
    never raised — audit must not break the main workflow.

    Args:
        tenant: Administration identifier
        action: Action type (publish, unpublish, rollback)
        version: Version number involved (nullable for unpublish)
        performed_by: Email of the user who performed the action
        details: Optional additional detail text
    """
    try:
        test_mode = os.getenv("TEST_MODE", "false").lower() == "true"
        db = DatabaseManager(test_mode=test_mode)
        query = """
            INSERT INTO landing_page_audit
                (administration, action, version, performed_by, details)
            VALUES (%s, %s, %s, %s, %s)
        """
        db.execute_query(
            query,
            (tenant, action, version, performed_by, details),
            fetch=False,
            commit=True,
        )
    except Exception as e:
        logger.error(f"Failed to record audit event for tenant {tenant}: {e}")


def _send_contact_notification(
    administration: str, visitor_name: str, visitor_email: str, message: str
) -> None:
    """
    Send an email notification to the tenant about a new contact form submission.

    Uses ParameterService to look up the tenant's contact email from the
    landing_page namespace ('email' key). Falls back silently if no email is
    configured or if SES fails.
    """
    try:
        from datetime import datetime, timezone

        from services.parameter_service import ParameterService
        from services.ses_email_service import SESEmailService

        test_mode = os.getenv("TEST_MODE", "false").lower() == "true"
        db = DatabaseManager(test_mode=test_mode)
        param_svc = ParameterService(db)

        # Get tenant contact email from landing_page namespace
        tenant_email = param_svc.get_param(
            "landing_page", "email", tenant=administration
        )

        if not tenant_email:
            logger.info(
                f"No contact email configured for tenant '{administration}', "
                f"skipping notification."
            )
            return

        # Build notification email (HTML-escape values to prevent email XSS)
        import html as html_module

        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        subject = f"Nieuw contactformulier bericht van {visitor_name}"

        text_body = (
            f"Nieuw bericht via contactformulier\n"
            f"{'=' * 40}\n\n"
            f"Naam:    {visitor_name}\n"
            f"Email:   {visitor_email}\n"
            f"Datum:   {timestamp}\n\n"
            f"Bericht:\n{message}\n"
        )

        safe_name = html_module.escape(visitor_name)
        safe_email = html_module.escape(visitor_email)
        safe_message = html_module.escape(message)

        html_body = (
            f"<h2>Nieuw bericht via contactformulier</h2>"
            f"<table style='border-collapse:collapse;'>"
            f"<tr><td style='padding:4px 12px 4px 0;font-weight:bold;'>Naam:</td>"
            f"<td>{safe_name}</td></tr>"
            f"<tr><td style='padding:4px 12px 4px 0;font-weight:bold;'>Email:</td>"
            f"<td><a href='mailto:{safe_email}'>{safe_email}</a></td></tr>"
            f"<tr><td style='padding:4px 12px 4px 0;font-weight:bold;'>Datum:</td>"
            f"<td>{timestamp}</td></tr>"
            f"</table>"
            f"<h3>Bericht:</h3>"
            f"<p style='white-space:pre-wrap;'>{safe_message}</p>"
        )

        ses = SESEmailService()
        result = ses.send_email(
            to_email=tenant_email,
            subject=subject,
            html_body=html_body,
            text_body=text_body,
            email_type="contact_form",
            administration=administration,
        )

        if result["success"]:
            logger.info(
                f"Contact notification sent to {tenant_email} for tenant '{administration}'"
            )
        else:
            logger.warning(
                f"Failed to send contact notification to {tenant_email}: "
                f"{result.get('error')}"
            )

    except Exception as e:
        # Never fail the submission because of notification errors
        logger.error(
            f"Error sending contact notification for tenant '{administration}': {e}"
        )


# Import endpoint submodules AFTER the blueprint and shared helpers are defined
# so that their route registrations attach to ``landing_page_bp`` and their
# handlers can resolve the shared helpers/imports (``_get_slug_service``,
# ``DatabaseManager``, ``MediaAssetService``, ``ParameterService``, ``os``,
# ``_send_contact_notification`` etc.) via this package namespace at call time.
# This keeps existing ``patch('routes.landing_page_routes.<name>')`` calls in
# the test suite working exactly as before the split.
from routes.landing_page_routes import (  # noqa: F401
    branding_endpoints,
    domain_endpoints,
    draft_endpoints,
    image_endpoints,
    public_endpoints,
    slug_endpoints,
    sysadmin_endpoints,
    version_endpoints,
)

# ``MediaAssetService`` is re-exported here (rather than imported only where it
# is used) because the test suite patches it as
# ``routes.landing_page_routes.MediaAssetService`` and the image-upload handler
# resolves it through this package namespace at call time.
__all__ = ["MediaAssetService", "landing_page_bp"]
