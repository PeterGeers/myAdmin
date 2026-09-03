"""
Media Asset Service

Exclusive gateway for all S3 write/delete operations on managed buckets.
Manages the asset lifecycle: upload → register → reference → orphan → delete.

Reference: .kiro/specs/Common/image-asset-management/requirements.md
"""

import logging
from typing import ClassVar

# boto3 is imported here so the concern mixins can reach it via
# ``services.media_asset_service.boto3`` (see services.media_asset.base._mas_boto3)
# and so the test suite's ``patch('services.media_asset_service.boto3.client', ...)``
# intercepts every S3 call made from any mixin.
import boto3  # noqa: F401  (re-exported for mixins/tests)

from database import DatabaseManager
from services.media_asset.base import ENTITY_TYPE_REGISTRY
from services.media_asset.helpers import HelpersMixin
from services.media_asset.import_ops import ImportMixin
from services.media_asset.lifecycle import LifecycleMixin
from services.media_asset.reconcile import ReconcileMixin
from services.media_asset.store_register import StoreRegisterMixin
from services.parameter_service import ParameterService

logger = logging.getLogger(__name__)

# Re-exported from services.media_asset.base for backward compatibility so that
# `from services.media_asset_service import ENTITY_TYPE_REGISTRY` keeps working.
__all__ = ["ENTITY_TYPE_REGISTRY", "MediaAssetService"]


class MediaAssetService(
    StoreRegisterMixin,
    LifecycleMixin,
    ReconcileMixin,
    ImportMixin,
    HelpersMixin,
):
    """Central service for media asset lifecycle management.

    The implementation is split across concern mixins under
    ``services.media_asset``:

    - :class:`~services.media_asset.store_register.StoreRegisterMixin`
    - :class:`~services.media_asset.lifecycle.LifecycleMixin`
    - :class:`~services.media_asset.reconcile.ReconcileMixin`
    - :class:`~services.media_asset.import_ops.ImportMixin`
    - :class:`~services.media_asset.helpers.HelpersMixin`
    """

    MEDIA_TYPES: ClassVar[dict[str, dict]] = {
        "image": {
            "extensions": {".jpg", ".jpeg", ".png", ".webp", ".gif", ".svg"},
            "mime_prefixes": ["image/"],
            "max_size": 10 * 1024 * 1024,  # 10 MB
        },
        "video": {
            "extensions": {".mp4", ".webm"},
            "mime_prefixes": ["video/"],
            "max_size": 100 * 1024 * 1024,  # 100 MB
        },
        "document": {
            "extensions": {".pdf"},
            "mime_prefixes": ["application/pdf"],
            "max_size": 25 * 1024 * 1024,  # 25 MB
        },
        "web_content": {
            "extensions": {".html", ".json"},
            "mime_prefixes": ["text/html", "application/json"],
            "max_size": 5 * 1024 * 1024,  # 5 MB
        },
    }

    CATEGORY_BUCKETS: ClassVar[dict[str, str]] = {
        "invoices": "S3_SHARED_BUCKET",
        "branding": "S3_SHARED_BUCKET",
        "templates": "S3_SHARED_BUCKET",
        "landing-pages": "LANDING_PAGES_BUCKET",
    }

    MAGIC_BYTES: ClassVar[dict[bytes, str]] = {
        b"\xff\xd8\xff": "image/jpeg",
        b"\x89PNG\r\n\x1a\n": "image/png",
        b"RIFF": "image/webp",  # check WEBP at offset 8
        b"GIF87a": "image/gif",
        b"GIF89a": "image/gif",
        b"%PDF": "application/pdf",
        b"\x00\x00\x00": "video/mp4",  # ftyp box (check offset 4)
        b"\x1aE\xdf\xa3": "video/webm",
    }

    RETENTION_KEYS = (
        "invoices_days",
        "branding_days",
        "templates_days",
        "landing_pages_days",
        "landing_pages_media_days",
    )

    def __init__(
        self,
        db_manager: DatabaseManager,
        parameter_service: ParameterService | None = None,
    ):
        self.db = db_manager
        self.ps = parameter_service or ParameterService(db_manager)
        self._presigned_cache = {}  # {asset_id: (url, expires_at)}
        self._last_reconciliation = {}  # {tenant: summary} — in-memory cache for UI retrieval
