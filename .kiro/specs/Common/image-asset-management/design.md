# Design Document: Media Asset Management Service

## Architecture Overview

The Asset_Service is a new service module (`backend/src/services/media_asset_service.py`) that acts as the exclusive gateway for all S3 operations on managed buckets. It sits between the existing route/service layer and the S3 storage providers, intercepting all writes and deletes to ensure registry tracking.

```
┌─────────────────────────────────────────────────────────────┐
│  Routes / Existing Services                                  │
│  (invoice_routes, storage, landing_page_publish, zzp, etc.) │
└──────────────────────────┬──────────────────────────────────┘
                           │ store_and_register()
                           │ delete_asset()
                           │ attach() / detach()
                           ▼
┌─────────────────────────────────────────────────────────────┐
│  MediaAssetService                                           │
│  - Validation (type, size, magic bytes)                      │
│  - Registry (s3_assets, s3_asset_references)                 │
│  - Reference guard (delete protection)                       │
│  - Lifecycle (ACTIVE → ORPHAN → DELETION_ELIGIBLE)           │
│  - Presigned URL generation + caching                        │
└──────────────────────────┬──────────────────────────────────┘
                           │ _upload_raw() / _delete_raw()
                           ▼
┌─────────────────────────────────────────────────────────────┐
│  S3SharedStorage / S3TenantStorage (read-only public API)    │
│  - download(), list_files(), get_presigned_url()             │
│  - _upload_raw(), _delete_raw() (internal, Asset_Service only│
└─────────────────────────────────────────────────────────────┘
```

## Module Structure

```
backend/src/
├── services/
│   └── media_asset_service.py      # Core service (Req 1-6, 8-10)
├── routes/
│   └── media_asset_routes.py       # API endpoints (Req 12, 13)
├── storage/
│   ├── storage_provider.py         # ABC (refactored: write/delete → internal)
│   ├── s3_shared_storage.py        # Refactored: public = read-only
│   └── s3_tenant_storage.py        # Refactored: public = read-only
└── migrations/
    └── 20260811_create_s3_assets.sql  # DDL for Req 7
```

## Database Schema (Req 7)

### Table: `s3_assets`

```sql
CREATE TABLE s3_assets (
    id                VARCHAR(30) NOT NULL PRIMARY KEY,  -- ast_<ULID>
    administration    VARCHAR(50) NOT NULL,
    bucket            VARCHAR(100) NOT NULL,
    s3_key            VARCHAR(512) NOT NULL,
    mime_type         VARCHAR(100) NOT NULL,
    file_size         BIGINT NOT NULL,
    category          ENUM('invoices','branding','templates','landing-pages') NOT NULL,
    media_type        ENUM('image','video','document','web_content') NOT NULL,
    original_filename VARCHAR(255) NOT NULL,
    content_hash      VARCHAR(64) DEFAULT NULL,          -- SHA-256 hex
    status            ENUM('ACTIVE','ORPHAN','DELETION_ELIGIBLE') NOT NULL DEFAULT 'ACTIVE',
    retention_days    INT DEFAULT NULL,                   -- per-asset override
    created_at        DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at        DATETIME DEFAULT NULL ON UPDATE CURRENT_TIMESTAMP,
    orphaned_at       DATETIME DEFAULT NULL,
    migrated_at       DATETIME DEFAULT NULL,

    INDEX idx_admin_status (administration, status),
    INDEX idx_admin_category (administration, category),
    INDEX idx_status_orphaned (status, orphaned_at),
    INDEX idx_admin_hash (administration, content_hash),
    UNIQUE INDEX idx_admin_s3key (administration, s3_key)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

### Table: `s3_asset_references`

```sql
CREATE TABLE s3_asset_references (
    id              BIGINT AUTO_INCREMENT PRIMARY KEY,
    administration  VARCHAR(50) NOT NULL,
    asset_id        VARCHAR(30) NOT NULL,
    entity_type     VARCHAR(50) NOT NULL,
    entity_id       VARCHAR(100) NOT NULL,
    created_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    INDEX idx_administration (administration),
    CONSTRAINT fk_asset_ref_asset FOREIGN KEY (asset_id)
        REFERENCES s3_assets(id) ON DELETE CASCADE,
    UNIQUE INDEX idx_asset_entity (asset_id, entity_type, entity_id),
    INDEX idx_entity_lookup (entity_type, entity_id),
    INDEX idx_admin_asset (administration, asset_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

## Retention Configuration (Parameter-Driven)

Uses the existing `parameter_values` table via `ParameterService`. Tenant administrators can update these values via the Asset Administration UI or the existing Parameter Management page.

| Namespace         | Key                        | Scope  | Default | Description                     |
| ----------------- | -------------------------- | ------ | ------- | ------------------------------- |
| `asset_retention` | `invoices_days`            | tenant | 2555    | Invoice PDF retention (7 years) |
| `asset_retention` | `branding_days`            | tenant | 30      | Logo/letterhead retention       |
| `asset_retention` | `templates_days`           | tenant | 90      | Template file retention         |
| `asset_retention` | `landing_pages_days`       | tenant | 7       | Landing page web content        |
| `asset_retention` | `landing_pages_media_days` | tenant | 30      | Landing page images/videos      |

Seeded via `ParameterService.CODE_DEFAULTS` (system-scope defaults defined in code). These values are automatically discoverable in the Parameter Management UI without requiring SQL seed scripts. When a tenant admin sets an override, it creates a `parameter_values` row with `scope_type='tenant'` that takes precedence.

### Tenant Admin Access

- Tenant administrators (`storage_manage` permission) can read and update retention parameters for their own tenant via:
  - **Asset Administration UI** — a "Retention Settings" section within the dashboard (Req 12) showing current values per category with inline edit
  - **Parameter Management page** — the existing generic parameter editor already supports tenant-scoped parameters; these appear under namespace `asset_retention`
- Changes take effect immediately for new orphan evaluations. Assets already in DELETION_ELIGIBLE status are not reverted (tenant admin can manually extend retention via the "Extend retention" action in Req 12 AC 7).
- The UI SHALL display the system default alongside the tenant override so the administrator understands what applies when no override is set.

### Retention Settings API

| Method | Path                             | Permission       | Description                                                               |
| ------ | -------------------------------- | ---------------- | ------------------------------------------------------------------------- |
| GET    | `/api/assets/retention-settings` | `storage_manage` | Get current retention config (resolved: tenant override + system default) |
| PUT    | `/api/assets/retention-settings` | `storage_manage` | Update tenant-level retention overrides                                   |

```json
// GET Response
{
  "success": true,
  "data": {
    "invoices_days": {"value": 2555, "source": "system_default"},
    "branding_days": {"value": 60, "source": "tenant_override"},
    "templates_days": {"value": 90, "source": "system_default"},
    "landing_pages_days": {"value": 7, "source": "system_default"},
    "landing_pages_media_days": {"value": 30, "source": "system_default"}
  }
}

// PUT Request
{
  "branding_days": 60,
  "templates_days": 120
}

// PUT Response
{
  "success": true,
  "updated": ["branding_days", "templates_days"]
}
```

## Service Class: MediaAssetService

```python
"""
Media Asset Service

Exclusive gateway for all S3 write/delete operations on managed buckets.
Manages the asset lifecycle: upload → register → reference → orphan → delete.

Reference: .kiro/specs/Common/image-asset-management/requirements.md
"""

import hashlib
import logging
import mimetypes
import os
import uuid
from datetime import datetime, timezone

from database import DatabaseManager
from services.parameter_service import ParameterService

logger = logging.getLogger(__name__)


class MediaAssetService:
    """Central service for media asset lifecycle management."""

    # Allowed media types with validation rules
    MEDIA_TYPES = {
        'image': {
            'extensions': {'.jpg', '.jpeg', '.png', '.webp', '.gif'},
            'mime_prefixes': ['image/'],
            'max_size': 10 * 1024 * 1024,  # 10 MB
        },
        'video': {
            'extensions': {'.mp4', '.webm'},
            'mime_prefixes': ['video/'],
            'max_size': 100 * 1024 * 1024,  # 100 MB
        },
        'document': {
            'extensions': {'.pdf'},
            'mime_prefixes': ['application/pdf'],
            'max_size': 25 * 1024 * 1024,  # 25 MB
        },
        'web_content': {
            'extensions': {'.html', '.json'},
            'mime_prefixes': ['text/html', 'application/json'],
            'max_size': 5 * 1024 * 1024,  # 5 MB
        },
    }

    # Category → bucket resolution
    CATEGORY_BUCKETS = {
        'invoices': 'S3_SHARED_BUCKET',
        'branding': 'S3_SHARED_BUCKET',
        'templates': 'S3_SHARED_BUCKET',
        'landing-pages': 'LANDING_PAGES_BUCKET',
    }

    def __init__(self, db_manager: DatabaseManager, parameter_service: ParameterService = None):
        self.db = db_manager
        self.ps = parameter_service or ParameterService(db_manager)
        self._presigned_cache = {}  # {asset_id: (url, expires_at)}

    # === Primary API ===

    def store_and_register(
        self,
        tenant: str,
        file_data: bytes,
        filename: str,
        category: str,
        entity_type: str = None,
        entity_id: str = None,
        metadata: dict = None,
    ) -> dict:
        """Upload to S3 + register in s3_assets + optionally attach reference."""
        ...

    def attach(self, tenant: str, asset_id: str, entity_type: str, entity_id: str) -> dict:
        """Create a reference from entity to asset."""
        ...

    def detach(self, tenant: str, asset_id: str, entity_type: str, entity_id: str) -> dict:
        """Remove a reference. If zero refs remain, mark ORPHAN."""
        ...

    def replace(self, tenant: str, entity_type: str, entity_id: str,
                old_asset_id: str, new_asset_id: str) -> dict:
        """Atomically detach old + attach new within one transaction."""
        ...

    def get_asset(self, tenant: str, asset_id: str) -> dict:
        """Retrieve asset metadata + presigned URL + references."""
        ...

    def search_assets(self, tenant: str, filters: dict) -> dict:
        """Paginated search for Asset Picker (Req 13)."""
        ...

    def delete_asset(self, tenant: str, asset_id: str, approved_by: str) -> dict:
        """Delete after reference guard check. Tenant admin only."""
        ...

    def force_delete(self, tenant: str, asset_id: str, operator: str, reason: str) -> dict:
        """Emergency delete bypassing reference guard. admin_manage only."""
        ...

    # === Reconciliation (Req 6) ===

    def run_reconciliation(self, tenant: str) -> dict:
        """Full scan: S3 vs registry vs app references."""
        ...

    def transition_eligible(self, tenant: str) -> dict:
        """Move orphans past retention to DELETION_ELIGIBLE status."""
        ...

    # === Import (Req 8) ===

    def import_legacy_assets(self, tenant: str, category: str) -> dict:
        """Scan S3 prefix, register untracked objects."""
        ...

    # === Internal (not callable from outside) ===

    def _upload_raw(self, bucket: str, key: str, file_data: bytes, content_type: str) -> bool:
        """Raw S3 put_object. Only called from store_and_register."""
        ...

    def _delete_raw(self, bucket: str, key: str) -> bool:
        """Raw S3 delete_object. Only called from delete_asset/force_delete."""
        ...

    def _generate_asset_id(self) -> str:
        """Generate ast_<ULID> identifier."""
        ...

    def _validate_file(self, file_data: bytes, filename: str) -> dict:
        """Validate type + size. Returns {media_type, mime_type} or raises."""
        ...

    def _resolve_bucket(self, category: str) -> str:
        """Resolve bucket name from env var based on category."""
        ...

    def _build_s3_key(self, tenant: str, category: str, asset_id: str, filename: str) -> str:
        """Build path: {tenant}/{category}/{asset_id}_{filename}."""
        ...

    def _get_retention_days(self, tenant: str, category: str, media_type: str) -> int:
        """Resolve retention: asset override → tenant param → system default."""
        ...

    def _get_presigned_url(self, asset: dict, ttl: int = 3600) -> str:
        """Generate or return cached presigned URL."""
        ...
```

## API Endpoints (Req 12, 13)

Blueprint: `media_asset_bp = Blueprint('media_assets', __name__, url_prefix='/api/assets')`

### Regular User Endpoints (module-level permissions)

| Method | Path                            | Permission        | Description                         |
| ------ | ------------------------------- | ----------------- | ----------------------------------- |
| POST   | `/api/assets/upload`            | (module-specific) | Upload + register + optional attach |
| GET    | `/api/assets/{asset_id}`        | (authenticated)   | Get metadata + presigned URL        |
| GET    | `/api/assets/search`            | (authenticated)   | Paginated search for Asset Picker   |
| POST   | `/api/assets/{asset_id}/attach` | (module-specific) | Attach reference                    |
| POST   | `/api/assets/{asset_id}/detach` | (module-specific) | Detach reference                    |
| POST   | `/api/assets/replace`           | (module-specific) | Atomic replace                      |

### Tenant Admin Endpoints (`storage_manage`)

| Method | Path                                | Permission       | Description                         |
| ------ | ----------------------------------- | ---------------- | ----------------------------------- |
| GET    | `/api/assets/dashboard`             | `storage_manage` | Summary stats                       |
| POST   | `/api/assets/scan`                  | `storage_manage` | Trigger reconciliation              |
| GET    | `/api/assets/scan/{scan_id}/status` | `storage_manage` | SSE progress                        |
| POST   | `/api/assets/approve-delete`        | `storage_manage` | Approve deletion of eligible assets |
| POST   | `/api/assets/import`                | `storage_manage` | Import unregistered S3 objects      |
| GET    | `/api/assets/duplicates`            | `storage_manage` | List duplicate content_hash groups  |
| POST   | `/api/assets/merge-duplicates`      | `storage_manage` | Merge duplicate assets              |

### System Admin Endpoints (`admin_manage`)

| Method | Path                        | Permission     | Description                  |
| ------ | --------------------------- | -------------- | ---------------------------- |
| POST   | `/api/assets/force-delete`  | `admin_manage` | Emergency bypass delete      |
| POST   | `/api/assets/migrate`       | `admin_manage` | Full migration (all tenants) |
| GET    | `/api/assets/admin/tenants` | `admin_manage` | Cross-tenant stats           |

### Request/Response Contracts

#### POST `/api/assets/upload`

```json
// Request (multipart/form-data)
{
  "file": "<binary>",
  "category": "invoices|branding|templates|landing-pages",
  "entity_type": "invoice",        // optional
  "entity_id": "12345",            // optional
  "reference_number": "SUP-001"    // optional, for path building
}

// Response 201
{
  "success": true,
  "asset": {
    "id": "ast_01H5K3ABCDEFGHJKMNPQRSTVWX",
    "s3_key": "TenantA/invoices/ast_01H5.../invoice.pdf",
    "mime_type": "application/pdf",
    "file_size": 245000,
    "category": "invoices",
    "media_type": "document",
    "status": "ACTIVE",
    "presigned_url": "https://...",
    "reference_count": 1
  },
  "duplicate_of": null  // or {asset_id, original_filename} if hash match
}
```

#### GET `/api/assets/search`

```json
// Query params: ?q=invoice&category=invoices&media_type=document&sort=created_at&order=desc&page=1&page_size=20

// Response 200
{
  "success": true,
  "data": [
    {
      "id": "ast_...",
      "original_filename": "invoice_2024.pdf",
      "mime_type": "application/pdf",
      "file_size": 245000,
      "category": "invoices",
      "media_type": "document",
      "created_at": "2025-03-15T10:30:00Z",
      "reference_count": 2,
      "presigned_url": "https://..." // for images, null for docs
    }
  ],
  "pagination": {
    "page": 1,
    "page_size": 20,
    "total": 87,
    "total_pages": 5
  }
}
```

#### POST `/api/assets/approve-delete`

```json
// Request
{
  "asset_ids": ["ast_...", "ast_..."]
}

// Response 200
{
  "success": true,
  "deleted": 3,
  "skipped": 1,
  "details": [
    {"asset_id": "ast_...", "status": "deleted"},
    {"asset_id": "ast_...", "status": "skipped", "reason": "re-activated"}
  ]
}
```

#### GET `/api/assets/dashboard`

```json
// Response 200
{
  "success": true,
  "data": {
    "total_assets": 245,
    "active_assets": 210,
    "orphaned_assets": 30,
    "deletion_eligible": 5,
    "storage_by_category": {
      "invoices": { "count": 180, "bytes": 450000000 },
      "branding": { "count": 12, "bytes": 5000000 },
      "templates": { "count": 8, "bytes": 2000000 },
      "landing-pages": { "count": 45, "bytes": 120000000 }
    },
    "last_scan_at": "2026-08-10T02:00:00Z",
    "top_orphans": [
      {
        "id": "ast_...",
        "filename": "old_logo.png",
        "size": 2500000,
        "days_orphaned": 45
      }
    ]
  }
}
```

## Key Implementation Details

### Asset ID Generation

Uses ULID (Universally Unique Lexicographically Sortable Identifier) with `ast_` prefix:

```python
import ulid

def _generate_asset_id(self) -> str:
    return f"ast_{ulid.new().str}"
```

Dependency: `python-ulid` package (add to `requirements.txt`).

### S3 Key Structure

```
{tenant}/{category}/{asset_id}_{original_filename}

Examples:
  GoodwinSolutions/invoices/ast_01H5K3ABCDEF_Q1_report.pdf
  GoodwinSolutions/branding/ast_01H5K3ABCDEF_company_logo.png
  tenant-slug/landing-pages/ast_01H5K3ABCDEF_hero_image.webp (public-pages bucket)
```

For landing-pages category, the key uses the tenant's slug (from `TenantSlugService`) instead of the administration name, since these are served publicly via CloudFront.

### File Validation (Magic Bytes)

```python
MAGIC_BYTES = {
    b'\xff\xd8\xff': 'image/jpeg',
    b'\x89PNG\r\n\x1a\n': 'image/png',
    b'RIFF': 'image/webp',       # check WEBP at offset 8
    b'GIF87a': 'image/gif',
    b'GIF89a': 'image/gif',
    b'%PDF': 'application/pdf',
    b'\x00\x00\x00': 'video/mp4',  # ftyp box (check offset 4)
    b'\x1aE\xdf\xa3': 'video/webm',
}

def _validate_file(self, file_data: bytes, filename: str) -> dict:
    """Validate media type by extension + magic bytes."""
    ext = os.path.splitext(filename)[1].lower()

    # HTML/JSON: no magic bytes, validate by extension + content sniff
    if ext in ('.html', '.json'):
        return self._validate_web_content(file_data, ext)

    # Binary files: check magic bytes
    detected_mime = self._detect_mime_from_bytes(file_data)
    expected_mime = mimetypes.guess_type(filename)[0]

    # Cross-check extension vs content
    ...
```

### Reference Guard (Req 10)

```python
def delete_asset(self, tenant: str, asset_id: str, approved_by: str) -> dict:
    """Delete with reference guard. Transaction ensures atomicity."""
    with self.db.transaction() as (cursor, conn):
        # Lock the asset row
        cursor.execute(
            "SELECT id, status, s3_key, bucket FROM s3_assets "
            "WHERE id = %s AND administration = %s FOR UPDATE",
            (asset_id, tenant)
        )
        asset = cursor.fetchone()
        if not asset:
            return {'success': False, 'error': 'Asset not found'}

        # Check references
        cursor.execute(
            "SELECT COUNT(*) as cnt FROM s3_asset_references WHERE asset_id = %s",
            (asset_id,)
        )
        ref_count = cursor.fetchone()['cnt']
        if ref_count > 0:
            return {
                'success': False,
                'error': f'Asset still has {ref_count} active references',
                'reference_count': ref_count
            }

        # S3 deletion (outside transaction — can't rollback S3)
        deleted = self._delete_raw(asset['bucket'], asset['s3_key'])
        if not deleted:
            return {'success': False, 'error': 'S3 deletion failed'}

        # Remove registry records
        cursor.execute("DELETE FROM s3_asset_references WHERE asset_id = %s", (asset_id,))
        cursor.execute("DELETE FROM s3_assets WHERE id = %s", (asset_id,))

    # Audit log
    logger.info(
        "Asset deleted: %s by %s (tenant=%s, category=%s)",
        asset_id, approved_by, tenant, asset.get('category')
    )
    return {'success': True, 'asset_id': asset_id}
```

### Lifecycle Transition (Scheduled)

The `transition_eligible` method runs as part of the scheduled reconciliation or on-demand scan:

```python
def transition_eligible(self, tenant: str) -> dict:
    """Move orphans past retention period to DELETION_ELIGIBLE."""
    # Get tenant retention settings
    categories = ['invoices', 'branding', 'templates', 'landing-pages']
    transitioned = 0

    for category in categories:
        retention = self._get_retention_days(tenant, category, media_type=None)
        result = self.db.execute_query(
            """
            UPDATE s3_assets
            SET status = 'DELETION_ELIGIBLE'
            WHERE administration = %s
              AND category = %s
              AND status = 'ORPHAN'
              AND orphaned_at <= DATE_SUB(NOW(), INTERVAL %s DAY)
            """,
            (tenant, category, retention),
            fetch=False, commit=True
        )
        transitioned += result  # rowcount

    return {'success': True, 'transitioned': transitioned}
```

### Presigned URL Caching

```python
from datetime import datetime, timedelta

def _get_presigned_url(self, asset: dict, ttl: int = 3600) -> str:
    """Return cached presigned URL or generate new one."""
    asset_id = asset['id']
    now = datetime.now(timezone.utc)

    # Check cache (50-min TTL for 60-min URLs)
    if asset_id in self._presigned_cache:
        url, expires_at = self._presigned_cache[asset_id]
        if now < expires_at - timedelta(minutes=10):
            return url

    # Generate new
    s3_client = boto3.client('s3')
    url = s3_client.generate_presigned_url(
        'get_object',
        Params={'Bucket': asset['bucket'], 'Key': asset['s3_key']},
        ExpiresIn=ttl
    )

    self._presigned_cache[asset_id] = (url, now + timedelta(seconds=ttl))
    return url
```

## Entity Type Registry (Implementation Detail)

The reconciliation job needs to verify whether referenced entities still exist. This mapping is maintained as a module-level dict in the service:

```python
# entity_type → (table, id_column, existence_query)
ENTITY_TYPE_REGISTRY = {
    'invoice': ('mutaties', 'ID',
                "SELECT 1 FROM mutaties WHERE ID = %s AND administration = %s LIMIT 1"),
    'branding': ('parameter_values', None,
                 "SELECT 1 FROM parameter_values WHERE namespace = 'branding' "
                 "AND `key` = %s AND scope_type = 'tenant' AND scope_value = %s LIMIT 1"),
    'landing_page': ('landing_pages', 'id',
                     "SELECT 1 FROM landing_pages WHERE id = %s AND administration = %s LIMIT 1"),
    'template': ('parameter_values', None,
                 "SELECT 1 FROM parameter_values WHERE namespace = 'templates' "
                 "AND `key` = %s AND scope_type = 'tenant' AND scope_value = %s LIMIT 1"),
    'report': None,  # Ephemeral — auto-expire after 90 days, no existence check
    'zzp_invoice': ('zzp_invoices', 'id',
                    "SELECT 1 FROM zzp_invoices WHERE id = %s AND administration = %s LIMIT 1"),
}
```

When a new module adds an entity_type, it registers here. Unknown entity_types are skipped during stale-reference detection with a logged warning.

## StorageProvider Refactoring

The existing `StorageProvider` ABC is modified to make write/delete internal:

```python
class StorageProvider(ABC):
    """Abstract base class for file storage backends."""

    # Public API (unchanged)
    @abstractmethod
    def download(self, reference: str) -> bytes: ...

    @abstractmethod
    def list_files(self, path: str) -> list[dict]: ...

    # Internal — only callable by MediaAssetService
    @abstractmethod
    def _upload_raw(self, file_data: bytes, key: str, content_type: str) -> bool: ...

    @abstractmethod
    def _delete_raw(self, key: str) -> bool: ...

    # Removed from public interface:
    # def upload(...)  → callers must use MediaAssetService.store_and_register
    # def delete(...)  → callers must use MediaAssetService.delete_asset
```

**Migration path**: Keep the old `upload()` and `delete()` methods temporarily with a deprecation warning that logs the caller. Remove after all code paths are migrated (Req 11 Phase 2). The architectural test (Req 11 Phase 3) catches any remaining direct calls.

## Integration with Existing Code Paths

### Invoice Upload (invoice_service.py)

Before:

```python
storage = get_s3_storage(tenant)
s3_key = storage.upload(file_data, filename, metadata={"reference_number": folder_name})
```

After:

```python
from services.media_asset_service import MediaAssetService

asset_svc = MediaAssetService(self.db)
result = asset_svc.store_and_register(
    tenant=tenant,
    file_data=file_data,
    filename=filename,
    category='invoices',
    entity_type='invoice',
    entity_id=str(mutatie_id),
    metadata={'reference_number': folder_name}
)
s3_key = result['asset']['s3_key']
```

### Logo Upload (routes/storage.py)

Before:

```python
s3_client = boto3.client("s3")
s3_client.put_object(Bucket=bucket, Key=s3_key, Body=file_data, ContentType=content_type)
```

After:

```python
asset_svc = MediaAssetService(db, ps)
result = asset_svc.store_and_register(
    tenant=tenant,
    file_data=file_data,
    filename=f"company_logo.{ext}",
    category='branding',
    entity_type='branding',
    entity_id=f"{tenant}:company_logo"
)
```

### Landing Page Publish (landing_page_publish_service.py)

Before:

```python
self._s3.put_object(Bucket=self.bucket_name, Key=f"{slug}/landing.json", Body=json_body, ...)
self._s3.put_object(Bucket=self.bucket_name, Key=f"{slug}/index.html", Body=html_body, ...)
```

After:

```python
# In __init__, inject MediaAssetService
self.asset_svc = MediaAssetService(db_manager, parameter_service)

# Publish
result_json = self.asset_svc.store_and_register(
    tenant=tenant, file_data=json_body.encode(),
    filename='landing.json', category='landing-pages',
    entity_type='landing_page', entity_id=str(page_id)
)
result_html = self.asset_svc.store_and_register(
    tenant=tenant, file_data=html_body.encode(),
    filename='index.html', category='landing-pages',
    entity_type='landing_page', entity_id=str(page_id)
)
```

### Unpublish

Before:

```python
self._s3.delete_object(Bucket=self.bucket_name, Key=f"{slug}/landing.json")
```

After:

```python
# Detach references, then delete orphaned assets
self.asset_svc.detach(tenant, json_asset_id, 'landing_page', str(page_id))
self.asset_svc.delete_asset(tenant, json_asset_id, approved_by=published_by)
```

### Folder Marker Creation (storage_resolver.py)

Folder markers are out of scope for registry tracking (see requirements Out of Scope). They continue to use raw S3 via the internal method:

```python
# storage_resolver.py — no registry entry for .folder markers
storage = get_s3_storage(tenant)
storage._upload_raw(
    file_data=b"",
    key=f"{tenant}/invoices/{folder_name}/.folder",
    content_type="application/x-directory"
)
```

The architectural test excludes `storage_resolver.py`'s `.folder` writes specifically.

## Reconciliation Flow (Req 6)

```
┌─────────────────────────────────────────────────────────────┐
│ Tenant Admin clicks "Start Scan"                             │
│ POST /api/assets/scan                                        │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────────┐
│ Phase 1: Scan S3 buckets for tenant prefix                   │
│  → List all objects under {tenant}/ in shared bucket         │
│  → List all objects under {slug}/ in public-pages bucket     │
│  → Compare against s3_assets WHERE administration = tenant   │
│  Result: unregistered_objects[], missing_objects[]            │
├──────────────────────────────────────────────────────────────┤
│ Phase 2: Verify references                                   │
│  → For each s3_asset_references row, check entity existence  │
│    using ENTITY_TYPE_REGISTRY queries                         │
│  → Remove stale references, update status to ORPHAN if 0 refs│
│  Result: stale_references_cleaned                            │
├──────────────────────────────────────────────────────────────┤
│ Phase 3: Transition eligible                                 │
│  → For each ORPHAN where orphaned_at + retention < NOW()     │
│  → Update status to DELETION_ELIGIBLE                        │
│  Result: newly_eligible_count                                │
├──────────────────────────────────────────────────────────────┤
│ Phase 4: Produce report                                      │
│  → Store scan results for UI display                         │
│  → Return summary via SSE                                    │
└──────────────────────────────────────────────────────────────┘
```

SSE progress events follow the existing pattern in the codebase:

```python
def generate_scan_events(tenant, scan_id):
    yield f"data: {json.dumps({'phase': 'scanning_s3', 'progress': 0})}\n\n"
    # ... scan logic with periodic yields ...
    yield f"data: {json.dumps({'phase': 'complete', 'summary': {...}})}\n\n"
```

## Architectural Test (Req 9 AC 6, Req 11 Phase 3)

```python
# tests/architecture/test_no_direct_s3_writes.py
"""
Architectural test: ensures no code outside MediaAssetService directly
calls put_object or delete_object on managed S3 buckets.
"""
import ast
import os
import pytest

ALLOWED_FILES = {
    'services/media_asset_service.py',
    'storage/s3_shared_storage.py',
    'storage/s3_tenant_storage.py',
    'services/storage_resolver.py',  # .folder markers only
}

FORBIDDEN_CALLS = {'put_object', 'delete_object', 'copy_object'}


def test_no_direct_s3_writes():
    """Scan all .py files for direct S3 write/delete calls."""
    violations = []
    src_dir = os.path.join(os.path.dirname(__file__), '..', '..', 'src')

    for root, dirs, files in os.walk(src_dir):
        for fname in files:
            if not fname.endswith('.py'):
                continue
            rel = os.path.relpath(os.path.join(root, fname), src_dir)
            if rel in ALLOWED_FILES:
                continue
            # Simple string scan (AST parse for accuracy in Phase 3)
            with open(os.path.join(root, fname)) as f:
                content = f.read()
            for call in FORBIDDEN_CALLS:
                if call in content:
                    violations.append(f"{rel}: contains '{call}'")

    assert violations == [], f"Direct S3 calls found:\n" + "\n".join(violations)
```

## Security Considerations

1. **Tenant prefix enforcement**: Every S3 key is validated against `{tenant}/` prefix before read/write. Cross-tenant access returns 403.
2. **Presigned URLs**: 60-min TTL, scoped to the specific object key. Not shareable across tenants.
3. **Reference guard**: Prevents accidental data loss. Only bypassable via `force_delete` with `admin_manage` permission + audit log.
4. **Content validation**: Magic byte checking prevents content-type spoofing (e.g., uploading an executable as `.pdf`).
5. **Size limits**: Enforced server-side before S3 write to prevent storage abuse.

## Performance Considerations

1. **Presigned URL cache**: In-memory cache with 50-min TTL avoids re-signing on every request.
2. **Batch thumbnail generation**: Asset Picker generates URLs in batch (single DB query + batch sign).
3. **Paginated search**: Uses `LIMIT/OFFSET` on indexed columns. For large registries (>10K assets), consider cursor-based pagination.
4. **Reconciliation**: Runs per-tenant, not globally. Uses `list_objects_v2` pagination. Expected runtime: <30s for typical tenant (<1000 objects).

## Dependencies

New packages to add to `requirements.txt`:

```
python-ulid==2.7.0       # ULID generation for asset IDs
```

No other new dependencies — boto3, hashlib, mimetypes are already available.

## Migration Strategy (Req 11)

Migration is a one-time operation executed by the system administrator:

1. **Create tables**: Run DDL migration script
2. **Register parameters**: Add retention defaults to `CODE_DEFAULTS`
3. **Import existing**: Run `import_legacy_assets` for each tenant × category
4. **Discover references**: Scan application tables for existing S3 key references
5. **Refactor code paths**: One module at a time, deploy incrementally
6. **Enable architectural test**: Only after all paths are migrated
7. **Post-migration reconciliation**: Verify zero discrepancies

Each step is independently deployable. The service works in "dual mode" during migration — old paths still function but log deprecation warnings.
