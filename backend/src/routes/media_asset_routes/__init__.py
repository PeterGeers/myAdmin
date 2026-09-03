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

The endpoint handlers are split across cohesive submodules under
``routes.media_asset_routes``:

- :mod:`routes.media_asset_routes.user_endpoints`
- :mod:`routes.media_asset_routes.admin_endpoints`
- :mod:`routes.media_asset_routes.admin_maintenance_endpoints`
- :mod:`routes.media_asset_routes.sysadmin_endpoints`

Reference: .kiro/specs/Common/image-asset-management/design.md
"""

import logging

from flask import Blueprint

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


# Import endpoint submodules AFTER the blueprint and helpers are defined so that
# their route registrations attach to ``media_asset_bp`` and their handlers can
# resolve ``_get_service`` (and other helpers) via this package namespace at
# call time. This keeps ``patch('routes.media_asset_routes._get_service')``
# working exactly as before the split.
from routes.media_asset_routes import (
    admin_endpoints,  # noqa: F401
    admin_maintenance_endpoints,  # noqa: F401
    sysadmin_endpoints,  # noqa: F401
    user_endpoints,  # noqa: F401
)

__all__ = ["media_asset_bp", "set_test_mode"]
