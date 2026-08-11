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
from datetime import datetime, timedelta, timezone
from typing import Optional

import boto3
from botocore.exceptions import ClientError
from ulid import ULID

from database import DatabaseManager
from db_exceptions import IntegrityError
from services.parameter_service import ParameterService

logger = logging.getLogger(__name__)

# entity_type → (table, id_column, existence_query) or None for ephemeral types
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


class MediaAssetService:
    """Central service for media asset lifecycle management."""

    # Allowed media types with validation rules
    MEDIA_TYPES = {
        'image': {
            'extensions': {'.jpg', '.jpeg', '.png', '.webp', '.gif', '.svg'},
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

    # Category → environment variable name for bucket resolution
    CATEGORY_BUCKETS = {
        'invoices': 'S3_SHARED_BUCKET',
        'branding': 'S3_SHARED_BUCKET',
        'templates': 'S3_SHARED_BUCKET',
        'landing-pages': 'LANDING_PAGES_BUCKET',
    }

    # Magic bytes for binary file type detection
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

    def __init__(self, db_manager: DatabaseManager, parameter_service: Optional[ParameterService] = None):
        self.db = db_manager
        self.ps = parameter_service or ParameterService(db_manager)
        self._presigned_cache = {}  # {asset_id: (url, expires_at)}
        self._last_reconciliation = {}  # {tenant: summary} — in-memory cache for UI retrieval

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
        """Upload to S3 + register in s3_assets + optionally attach reference.

        Flow:
        1. Validate file (type, magic bytes, size)
        2. Compute SHA-256 content_hash
        3. Generate asset_id
        4. Build S3 key
        5. Upload to S3
        6. Insert s3_assets row (+ optionally s3_asset_references)
        7. Check for duplicates (non-blocking)
        8. Return result

        If S3 write fails, no DB records are created.
        If DB commit fails after S3 write, log orphaned key for reconciliation.

        Args:
            tenant: Tenant identifier (administration).
            file_data: Raw file bytes.
            filename: Original filename with extension.
            category: Asset category (invoices, branding, templates, landing-pages).
            entity_type: Optional entity type for reference attachment.
            entity_id: Optional entity id for reference attachment.
            metadata: Optional additional metadata dict.

        Returns:
            Dict with 'success', 'asset', and 'duplicate_of' keys.

        Raises:
            ValueError: If file validation fails or category is invalid.
        """
        # Step 1: Validate file (AC 3-7 from Req 1)
        validation = self._validate_file(file_data, filename)
        media_type = validation['media_type']
        mime_type = validation['mime_type']

        # Step 2: Compute SHA-256 content_hash
        content_hash = hashlib.sha256(file_data).hexdigest()

        # Step 3: Generate asset_id
        asset_id = self._generate_asset_id()

        # Step 4: Resolve bucket and build S3 key
        bucket = self._resolve_bucket(category)
        s3_key = self._build_s3_key(tenant, category, asset_id, filename)

        # Step 5: Upload to S3 — if this fails, no DB records are created (Req 9 AC 9)
        upload_success = self._upload_raw(bucket, s3_key, file_data, mime_type)
        if not upload_success:
            return {'success': False, 'error': 'S3 upload failed'}

        # Step 6: Insert DB records — commit only after S3 write succeeds (Req 9 AC 8)
        now = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
        file_size = len(file_data)

        try:
            with self.db.transaction() as (cursor, conn):
                # INSERT s3_assets
                insert_asset_query = """
                    INSERT INTO s3_assets
                    (id, administration, bucket, s3_key, mime_type, file_size,
                     category, media_type, original_filename, content_hash,
                     status, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """
                cursor.execute(insert_asset_query, (
                    asset_id, tenant, bucket, s3_key, mime_type, file_size,
                    category, media_type, filename, content_hash,
                    'ACTIVE', now,
                ))

                # Optionally INSERT s3_asset_references (Req 1 AC 8)
                reference_count = 0
                if entity_type and entity_id:
                    insert_ref_query = """
                        INSERT INTO s3_asset_references
                        (administration, asset_id, entity_type, entity_id, created_at)
                        VALUES (%s, %s, %s, %s, %s)
                    """
                    cursor.execute(insert_ref_query, (
                        tenant, asset_id, entity_type, entity_id, now,
                    ))
                    reference_count = 1

        except Exception as e:
            # DB commit failed after S3 write — log orphaned key (Req 9 AC 10)
            logger.error(
                "DB commit failed after S3 write — orphaned S3 key: "
                "bucket=%s, key=%s, timestamp=%s, error=%s",
                bucket, s3_key, now, str(e)
            )
            return {
                'success': False,
                'error': 'Database registration failed after S3 upload',
                'orphaned_key': {'bucket': bucket, 'key': s3_key},
            }

        # Step 7: Check for duplicate content_hash (non-blocking)
        duplicate_of = self._check_duplicate(tenant, asset_id, content_hash)

        # Step 8: Return result
        asset_record = {
            'id': asset_id,
            's3_key': s3_key,
            'bucket': bucket,
            'mime_type': mime_type,
            'file_size': file_size,
            'category': category,
            'media_type': media_type,
            'original_filename': filename,
            'content_hash': content_hash,
            'status': 'ACTIVE',
            'created_at': now,
            'reference_count': reference_count,
        }

        return {
            'success': True,
            'asset': asset_record,
            'duplicate_of': duplicate_of,
        }

    def attach(self, tenant: str, asset_id: str, entity_type: str, entity_id: str) -> dict:
        """Create a reference from entity to asset.

        Inserts a row into s3_asset_references linking the asset to the given
        entity. If the asset was ORPHAN or DELETION_ELIGIBLE, reverts status
        to ACTIVE and clears orphaned_at.

        The operation is idempotent: if (asset_id, entity_type, entity_id)
        already exists, returns success without creating a duplicate.

        Args:
            tenant: Tenant identifier (administration).
            asset_id: The asset to attach to.
            entity_type: Type of referencing entity (e.g., 'invoice').
            entity_id: ID of the referencing entity.

        Returns:
            Dict with 'success' and either 'asset' info or 'error' message.
        """
        now = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')

        with self.db.transaction() as (cursor, conn):
            # Step 1: Verify asset exists and belongs to tenant
            cursor.execute(
                "SELECT id, status FROM s3_assets WHERE id = %s AND administration = %s",
                (asset_id, tenant)
            )
            asset_row = cursor.fetchone()

            if not asset_row:
                return {'success': False, 'error': 'Asset not found'}

            # Step 2: INSERT reference (idempotent via unique constraint)
            try:
                cursor.execute(
                    """
                    INSERT INTO s3_asset_references
                    (administration, asset_id, entity_type, entity_id, created_at)
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (tenant, asset_id, entity_type, entity_id, now)
                )
            except IntegrityError:
                # Unique constraint violation — already exists, treat as success
                pass

            # Step 3: If asset was ORPHAN or DELETION_ELIGIBLE, revert to ACTIVE
            current_status = asset_row['status'] if isinstance(asset_row, dict) else asset_row[1]
            if current_status in ('ORPHAN', 'DELETION_ELIGIBLE'):
                cursor.execute(
                    """
                    UPDATE s3_assets
                    SET status = 'ACTIVE', orphaned_at = NULL, updated_at = %s
                    WHERE id = %s AND administration = %s
                    """,
                    (now, asset_id, tenant)
                )
            else:
                # Step 4: Update updated_at timestamp
                cursor.execute(
                    "UPDATE s3_assets SET updated_at = %s WHERE id = %s AND administration = %s",
                    (now, asset_id, tenant)
                )

        return {
            'success': True,
            'asset_id': asset_id,
            'entity_type': entity_type,
            'entity_id': entity_id,
            'status': 'ACTIVE' if current_status in ('ORPHAN', 'DELETION_ELIGIBLE') else current_status,
            'updated_at': now,
        }

    def detach(self, tenant: str, asset_id: str, entity_type: str, entity_id: str) -> dict:
        """Remove a reference. If zero refs remain, mark ORPHAN.

        Deletes the matching row from s3_asset_references and updates the
        asset status accordingly:
        - If remaining references > 0: keep status as-is, update updated_at
        - If remaining references == 0: set status=ORPHAN, record orphaned_at

        Args:
            tenant: Tenant identifier (administration).
            asset_id: The asset to detach from.
            entity_type: Type of referencing entity (e.g., 'invoice').
            entity_id: ID of the referencing entity.

        Returns:
            Dict with 'success' and either 'asset' info or 'error' message.
        """
        now = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')

        with self.db.transaction() as (cursor, conn):
            # Step 1: Verify asset exists and belongs to tenant
            cursor.execute(
                "SELECT id, status FROM s3_assets WHERE id = %s AND administration = %s",
                (asset_id, tenant)
            )
            asset_row = cursor.fetchone()

            if not asset_row:
                return {'success': False, 'error': 'Asset not found'}

            # Step 2: DELETE the reference row
            cursor.execute(
                """
                DELETE FROM s3_asset_references
                WHERE asset_id = %s AND entity_type = %s AND entity_id = %s AND administration = %s
                """,
                (asset_id, entity_type, entity_id, tenant)
            )

            if cursor.rowcount == 0:
                return {'success': False, 'error': 'Reference not found'}

            # Step 3: Count remaining references for this asset
            cursor.execute(
                "SELECT COUNT(*) AS cnt FROM s3_asset_references WHERE asset_id = %s AND administration = %s",
                (asset_id, tenant)
            )
            count_row = cursor.fetchone()
            reference_count = count_row['cnt'] if isinstance(count_row, dict) else count_row[0]

            # Step 4: Update asset status based on remaining references
            if reference_count == 0:
                cursor.execute(
                    """
                    UPDATE s3_assets
                    SET status = 'ORPHAN', orphaned_at = %s, updated_at = %s
                    WHERE id = %s AND administration = %s
                    """,
                    (now, now, asset_id, tenant)
                )
                new_status = 'ORPHAN'
            else:
                cursor.execute(
                    "UPDATE s3_assets SET updated_at = %s WHERE id = %s AND administration = %s",
                    (now, asset_id, tenant)
                )
                current_status = asset_row['status'] if isinstance(asset_row, dict) else asset_row[1]
                new_status = current_status

        return {
            'success': True,
            'asset': {
                'id': asset_id,
                'status': new_status,
                'reference_count': reference_count,
                'updated_at': now,
            },
        }

    def replace(self, tenant: str, entity_type: str, entity_id: str,
                old_asset_id: str, new_asset_id: str) -> dict:
        """Atomically detach old + attach new within one transaction.

        Replaces an entity's asset reference in a single DB transaction.
        If old_asset_id is None or empty, delegates to a simple attach.

        AC 7: Atomically detach old_asset_id and attach new_asset_id.
        AC 8: If attach fails, roll back so old reference remains intact.
        AC 9: When old_asset_id is null/empty, treat as simple attach.
        AC 10: If old_asset_id has no matching reference, return error — do NOT attach new.

        Args:
            tenant: Tenant identifier (administration).
            entity_type: Type of referencing entity (e.g., 'invoice').
            entity_id: ID of the referencing entity.
            old_asset_id: Asset to detach (None/empty → simple attach).
            new_asset_id: Asset to attach.

        Returns:
            Dict with 'success' and asset info or 'error' message.
        """
        now = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')

        # AC 9: When old_asset_id is null or empty, treat as simple attach
        if not old_asset_id:
            return self.attach(tenant, new_asset_id, entity_type, entity_id)

        # AC 7: Atomically detach old + attach new within one transaction
        with self.db.transaction() as (cursor, conn):
            # Step 1: Verify old reference exists (AC 10)
            cursor.execute(
                """
                SELECT id FROM s3_asset_references
                WHERE asset_id = %s AND entity_type = %s AND entity_id = %s AND administration = %s
                """,
                (old_asset_id, entity_type, entity_id, tenant)
            )
            old_ref = cursor.fetchone()

            if not old_ref:
                return {
                    'success': False,
                    'error': (
                        f"No reference found for old_asset_id '{old_asset_id}' "
                        f"with entity_type '{entity_type}' and entity_id '{entity_id}'"
                    ),
                }

            # Step 2: Verify new asset exists and belongs to tenant
            cursor.execute(
                "SELECT id, status FROM s3_assets WHERE id = %s AND administration = %s",
                (new_asset_id, tenant)
            )
            new_asset_row = cursor.fetchone()

            if not new_asset_row:
                return {
                    'success': False,
                    'error': f"New asset '{new_asset_id}' not found",
                }

            # Step 3: DELETE old reference
            cursor.execute(
                """
                DELETE FROM s3_asset_references
                WHERE asset_id = %s AND entity_type = %s AND entity_id = %s AND administration = %s
                """,
                (old_asset_id, entity_type, entity_id, tenant)
            )

            # Step 4: INSERT new reference
            try:
                cursor.execute(
                    """
                    INSERT INTO s3_asset_references
                    (administration, asset_id, entity_type, entity_id, created_at)
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (tenant, new_asset_id, entity_type, entity_id, now)
                )
            except IntegrityError:
                # Reference already exists (idempotent) — not an error
                pass

            # Step 5: Check if old asset has zero remaining refs → mark ORPHAN
            cursor.execute(
                "SELECT COUNT(*) AS cnt FROM s3_asset_references WHERE asset_id = %s AND administration = %s",
                (old_asset_id, tenant)
            )
            old_ref_count_row = cursor.fetchone()
            old_ref_count = old_ref_count_row['cnt'] if isinstance(old_ref_count_row, dict) else old_ref_count_row[0]

            old_new_status = 'ACTIVE'
            if old_ref_count == 0:
                cursor.execute(
                    """
                    UPDATE s3_assets
                    SET status = 'ORPHAN', orphaned_at = %s, updated_at = %s
                    WHERE id = %s AND administration = %s
                    """,
                    (now, now, old_asset_id, tenant)
                )
                old_new_status = 'ORPHAN'

            # Step 6: If new asset was ORPHAN or DELETION_ELIGIBLE → revert to ACTIVE
            new_status = new_asset_row['status'] if isinstance(new_asset_row, dict) else new_asset_row[1]
            if new_status in ('ORPHAN', 'DELETION_ELIGIBLE'):
                cursor.execute(
                    """
                    UPDATE s3_assets
                    SET status = 'ACTIVE', orphaned_at = NULL, updated_at = %s
                    WHERE id = %s AND administration = %s
                    """,
                    (now, new_asset_id, tenant)
                )
                new_status = 'ACTIVE'
            else:
                cursor.execute(
                    "UPDATE s3_assets SET updated_at = %s WHERE id = %s AND administration = %s",
                    (now, new_asset_id, tenant)
                )

        return {
            'success': True,
            'old_asset': {
                'id': old_asset_id,
                'status': old_new_status,
                'reference_count': old_ref_count,
            },
            'new_asset': {
                'id': new_asset_id,
                'status': new_status,
                'entity_type': entity_type,
                'entity_id': entity_id,
            },
            'updated_at': now,
        }

    def get_asset(self, tenant: str, asset_id: str) -> dict:
        """Retrieve asset metadata + presigned URL + references.

        Queries s3_assets and s3_asset_references for the given asset,
        generates a presigned URL (with caching), and returns the combined
        result.

        AC 1: Return asset metadata fields.
        AC 2: Include presigned S3 URL valid for 60 minutes.
        AC 3: Asset retrieval scoped to authenticated tenant.
        AC 4: If asset belongs to different tenant, return not-found.
        AC 5: If asset_id doesn't exist, return not-found.
        AC 6: ORPHAN assets still permit retrieval until permanently deleted.

        Args:
            tenant: Tenant identifier (administration).
            asset_id: The asset ID to retrieve.

        Returns:
            Dict with 'success' and either 'asset' data or 'error' message.
        """
        # Step 1: Query s3_assets with tenant isolation (AC 3, 4, 5)
        asset_query = """
            SELECT id, bucket, s3_key, mime_type, file_size, category,
                   media_type, original_filename, status, created_at
            FROM s3_assets
            WHERE id = %s AND administration = %s
        """
        results = self.db.execute_query(asset_query, (asset_id, tenant), fetch=True)

        if not results:
            return {'success': False, 'error': 'Asset not found'}

        asset = results[0]

        # Step 2: Query s3_asset_references (AC 1)
        refs_query = """
            SELECT entity_type, entity_id, created_at
            FROM s3_asset_references
            WHERE asset_id = %s AND administration = %s
        """
        references = self.db.execute_query(refs_query, (asset_id, tenant), fetch=True)

        # Step 3: Generate presigned URL (AC 2, AC 7 via _get_presigned_url caching)
        presigned_url = self._get_presigned_url(asset)

        # Step 4: Return combined result
        return {
            'success': True,
            'asset': {
                'id': asset['id'],
                's3_key': asset['s3_key'],
                'mime_type': asset['mime_type'],
                'file_size': asset['file_size'],
                'category': asset['category'],
                'media_type': asset['media_type'],
                'original_filename': asset['original_filename'],
                'status': asset['status'],
                'created_at': asset['created_at'],
                'presigned_url': presigned_url,
                'references': references,
            },
        }

    def search_assets(self, tenant: str, filters: dict) -> dict:
        """Paginated search for Asset Picker.

        Builds a dynamic query with optional WHERE clauses based on filters.
        Results include reference_count via subquery and presigned URLs for
        image assets.

        Supported filters:
            q: LIKE match on original_filename (partial, case-insensitive)
            category: Exact match on category column
            media_type: Exact match on media_type column
            status: Exact match on status column (default: ACTIVE)
            sort: Column to sort by (default: created_at)
            order: ASC or DESC (default: desc)
            page: Page number, 1-based (default: 1)
            page_size: Results per page (default: 20, max: 100)

        Args:
            tenant: Tenant identifier (administration).
            filters: Dict of query parameters from the request.

        Returns:
            Dict with 'success', 'data' (list of asset dicts), and
            'pagination' (page, page_size, total, total_pages).
        """
        import math

        # Parse pagination params
        page = max(1, int(filters.get('page', 1)))
        page_size = min(100, max(1, int(filters.get('page_size', 20))))

        # Parse sort params (whitelist allowed columns)
        allowed_sort_columns = {'created_at', 'original_filename', 'file_size', 'mime_type', 'category'}
        sort = filters.get('sort', 'created_at')
        if sort not in allowed_sort_columns:
            sort = 'created_at'

        order = filters.get('order', 'desc').upper()
        if order not in ('ASC', 'DESC'):
            order = 'DESC'

        # Build WHERE clauses
        where_clauses = ['a.administration = %s']
        params = [tenant]

        if filters.get('q'):
            where_clauses.append('a.original_filename LIKE %s')
            params.append(f"%{filters['q']}%")

        if filters.get('category'):
            where_clauses.append('a.category = %s')
            params.append(filters['category'])

        if filters.get('media_type'):
            where_clauses.append('a.media_type = %s')
            params.append(filters['media_type'])

        if filters.get('status'):
            where_clauses.append('a.status = %s')
            params.append(filters['status'])

        where_sql = ' AND '.join(where_clauses)

        # Count total results
        count_query = f"SELECT COUNT(*) AS total FROM s3_assets a WHERE {where_sql}"
        count_result = self.db.execute_query(count_query, tuple(params), fetch=True)
        total = count_result[0]['total'] if count_result else 0
        total_pages = math.ceil(total / page_size) if total > 0 else 0

        # Fetch paginated results with reference_count subquery
        offset = (page - 1) * page_size
        data_query = f"""
            SELECT a.id, a.original_filename, a.mime_type, a.file_size,
                   a.category, a.media_type, a.status, a.created_at,
                   a.bucket, a.s3_key,
                   (SELECT COUNT(*) FROM s3_asset_references r
                    WHERE r.asset_id = a.id) AS reference_count
            FROM s3_assets a
            WHERE {where_sql}
            ORDER BY a.{sort} {order}
            LIMIT %s OFFSET %s
        """
        data_params = tuple(params) + (page_size, offset)
        rows = self.db.execute_query(data_query, data_params, fetch=True)

        # Build response data with presigned URLs for images
        data = []
        for row in rows:
            media_type = row['media_type']
            presigned_url = None
            if media_type == 'image':
                presigned_url = self._get_presigned_url(row)

            data.append({
                'id': row['id'],
                'original_filename': row['original_filename'],
                'mime_type': row['mime_type'],
                'file_size': row['file_size'],
                'category': row['category'],
                'media_type': media_type,
                'status': row['status'],
                'created_at': row['created_at'],
                'reference_count': row['reference_count'],
                'presigned_url': presigned_url,
            })

        return {
            'success': True,
            'data': data,
            'pagination': {
                'page': page,
                'page_size': page_size,
                'total': total,
                'total_pages': total_pages,
            },
        }

    def delete_asset(self, tenant: str, asset_id: str, approved_by: str) -> dict:
        """Delete asset after reference guard check. Tenant admin only.

        Performs an atomic check-then-delete with SELECT FOR UPDATE to prevent
        race conditions. Only assets with status ORPHAN or DELETION_ELIGIBLE
        can be deleted (or ACTIVE with zero references).

        Flow:
        1. Lock the asset row (SELECT FOR UPDATE)
        2. Verify status is ORPHAN or DELETION_ELIGIBLE (or zero refs)
        3. Verify zero references within same transaction (reference guard)
        4. Call _delete_raw to remove S3 object
        5. DELETE from s3_asset_references + s3_assets
        6. Audit log
        7. Return success/failure

        Req 5 AC 4: Only when tenant admin explicitly approves.
        Req 5 AC 9: Verify zero references within same transaction.
        Req 5 AC 10: If asset regained reference, skip and report re-activated.
        Req 5 AC 11: Log deletion details.
        Req 5 AC 12: If active references, reject with error.
        Req 5 AC 13: If S3 deletion fails, retain record and report failure.
        Req 10 AC 1: Query s3_asset_references and verify zero rows in same transaction.
        Req 10 AC 2: If reference count > 0, abort with error and reference count.

        Args:
            tenant: Tenant identifier (administration).
            asset_id: The asset ID to delete.
            approved_by: Email of the approving tenant admin.

        Returns:
            Dict with 'success' and either deletion confirmation or 'error' message.
        """
        with self.db.transaction() as (cursor, conn):
            # Step 1: Lock the asset row (SELECT FOR UPDATE)
            cursor.execute(
                "SELECT id, status, s3_key, bucket, category FROM s3_assets "
                "WHERE id = %s AND administration = %s FOR UPDATE",
                (asset_id, tenant)
            )
            asset = cursor.fetchone()

            if not asset:
                return {'success': False, 'error': 'Asset not found'}

            # Step 2: Verify status allows deletion
            status = asset['status'] if isinstance(asset, dict) else asset[1]

            # Step 3: Reference guard — verify zero references (Req 10 AC 1)
            cursor.execute(
                "SELECT COUNT(*) AS cnt FROM s3_asset_references "
                "WHERE asset_id = %s AND administration = %s",
                (asset_id, tenant)
            )
            count_row = cursor.fetchone()
            ref_count = count_row['cnt'] if isinstance(count_row, dict) else count_row[0]

            # Req 5 AC 10: If asset regained a reference, report re-activated
            if ref_count > 0 and status in ('ORPHAN', 'DELETION_ELIGIBLE'):
                return {
                    'success': False,
                    'error': 're-activated',
                    'reference_count': ref_count,
                }

            # Req 5 AC 12 / Req 10 AC 2: Active references → reject
            if ref_count > 0:
                return {
                    'success': False,
                    'error': f'Asset still has {ref_count} active references',
                    'reference_count': ref_count,
                }

            # Status check: only ORPHAN/DELETION_ELIGIBLE or ACTIVE with zero refs
            # (ACTIVE with zero refs is allowed per design — zero refs is the guard)

            # Step 4: S3 deletion (Req 5 AC 13: if fails, retain record)
            s3_key = asset['s3_key'] if isinstance(asset, dict) else asset[2]
            bucket = asset['bucket'] if isinstance(asset, dict) else asset[3]
            category = asset['category'] if isinstance(asset, dict) else asset[4]

            deleted = self._delete_raw(bucket, s3_key)
            if not deleted:
                return {'success': False, 'error': 'S3 deletion failed'}

            # Step 5: Remove registry records
            cursor.execute(
                "DELETE FROM s3_asset_references WHERE asset_id = %s AND administration = %s",
                (asset_id, tenant)
            )
            cursor.execute(
                "DELETE FROM s3_assets WHERE id = %s AND administration = %s",
                (asset_id, tenant)
            )

        # Step 6: Audit log (Req 5 AC 11)
        logger.info(
            "Asset deleted: asset_id=%s, administration=%s, bucket=%s, "
            "category=%s, approved_by=%s",
            asset_id, tenant, bucket, category, approved_by
        )

        # Step 7: Return success
        return {'success': True, 'asset_id': asset_id}

    def force_delete(self, tenant: str, asset_id: str, operator: str, reason: str) -> dict:
        """Emergency delete bypassing reference guard. admin_manage only.

        Intended solely for emergency recovery. Bypasses the reference guard
        entirely — deletes the asset even if active references exist.

        Permission enforcement (admin_manage) is at the route level, not here.

        Flow:
        1. Lock the asset row (SELECT FOR UPDATE)
        2. Count references (for audit, not for guard)
        3. Call _delete_raw to remove S3 object
        4. If S3 fails, return error
        5. DELETE from s3_asset_references + s3_assets
        6. Log WARNING-level audit entry
        7. Return success

        Req 10 AC 7: force_delete bypasses reference guard, logs warning with
        asset_id, reference count, operator identity.
        Req 10 AC 8: Audit entry includes asset_id, administration, operator
        email, reference count at time of deletion, reason, timestamp.

        Args:
            tenant: Tenant identifier (administration).
            asset_id: The asset ID to force-delete.
            operator: Email of the system admin performing the operation.
            reason: Reason for the emergency deletion.

        Returns:
            Dict with 'success' and either deletion confirmation or 'error' message.
        """
        with self.db.transaction() as (cursor, conn):
            # Step 1: Lock the asset row
            cursor.execute(
                "SELECT id, status, s3_key, bucket, category FROM s3_assets "
                "WHERE id = %s AND administration = %s FOR UPDATE",
                (asset_id, tenant)
            )
            asset = cursor.fetchone()

            if not asset:
                return {'success': False, 'error': 'Asset not found'}

            # Step 2: Count references for audit (NOT for guard — bypassed)
            cursor.execute(
                "SELECT COUNT(*) AS cnt FROM s3_asset_references "
                "WHERE asset_id = %s AND administration = %s",
                (asset_id, tenant)
            )
            count_row = cursor.fetchone()
            ref_count = count_row['cnt'] if isinstance(count_row, dict) else count_row[0]

            # Step 3: S3 deletion
            s3_key = asset['s3_key'] if isinstance(asset, dict) else asset[2]
            bucket = asset['bucket'] if isinstance(asset, dict) else asset[3]
            category = asset['category'] if isinstance(asset, dict) else asset[4]

            deleted = self._delete_raw(bucket, s3_key)
            if not deleted:
                return {'success': False, 'error': 'S3 deletion failed'}

            # Step 5: Remove registry records (bypass reference guard)
            cursor.execute(
                "DELETE FROM s3_asset_references WHERE asset_id = %s AND administration = %s",
                (asset_id, tenant)
            )
            cursor.execute(
                "DELETE FROM s3_assets WHERE id = %s AND administration = %s",
                (asset_id, tenant)
            )

        # Step 6: WARNING-level audit entry (Req 10 AC 7, AC 8)
        logger.warning(
            "FORCE DELETE: asset_id=%s, administration=%s, operator=%s, "
            "reference_count=%d, reason=%s, timestamp=%s",
            asset_id, tenant, operator, ref_count, reason,
            datetime.now(timezone.utc).isoformat()
        )

        # Step 7: Return success
        return {
            'success': True,
            'asset_id': asset_id,
            'reference_count': ref_count,
            'operator': operator,
            'reason': reason,
        }

    # === Reconciliation ===

    def run_reconciliation(self, tenant: str) -> dict:
        """Full reconciliation scan. Implements phases incrementally.

        Phase 1 (S3 scan): Compare S3 objects against the s3_assets registry.
        Phase 2 (Reference verification): Verify entity existence, remove stale refs.
        Phase 3 (Transition eligible): Move orphans past retention to DELETION_ELIGIBLE.

        Args:
            tenant: Tenant identifier (administration).

        Returns:
            Dict with 'success', 'tenant', phase results, and 'summary' report.
        """
        result = {
            'success': True,
            'tenant': tenant,
            'phase1': self._reconcile_s3_scan(tenant),
            'phase2': self._reconcile_references(tenant),
            'phase3': self.transition_eligible(tenant),
        }

        # Build reconciliation report (Req 6 AC 4)
        result['summary'] = self._build_reconciliation_report(
            tenant, result['phase1'], result['phase2'], result['phase3']
        )

        # Store in memory cache for UI retrieval
        self._last_reconciliation[tenant] = result['summary']

        return result

    def run_reconciliation_with_progress(self, tenant: str):
        """Run reconciliation as a generator, yielding SSE progress events.

        Designed to be consumed by a Flask route that wraps the output in a
        Response with mimetype='text/event-stream'. Each yield is a dict that
        the route handler serializes as an SSE `data:` frame.

        Phases:
            scanning_s3 — Listing S3 objects and comparing against registry
            checking_registry — Comparing S3 objects vs registered assets
            verifying_references — Checking entity existence, removing stale refs
            transitioning — Moving eligible orphans to DELETION_ELIGIBLE
            complete — Final summary report

        Args:
            tenant: Tenant identifier (administration).

        Yields:
            Dicts with 'type' ('progress' or 'complete') and phase-specific data.
        """
        # Phase 1: scanning_s3
        yield {
            'type': 'progress',
            'phase': 'scanning_s3',
            'message': 'Scanning S3 buckets...',
        }

        phase1 = self._reconcile_s3_scan(tenant)

        # Phase 2: checking_registry
        yield {
            'type': 'progress',
            'phase': 'checking_registry',
            'message': 'Comparing with registry...',
            'total_s3': phase1.get('total_s3', 0),
            'total_registry': phase1.get('total_registry', 0),
            'unregistered': len(phase1.get('unregistered', [])),
            'missing': len(phase1.get('missing', [])),
        }

        phase2 = self._reconcile_references(tenant)

        # Phase 3: verifying_references
        yield {
            'type': 'progress',
            'phase': 'verifying_references',
            'message': 'Verifying entity references...',
            'stale_found': phase2.get('stale_removed', 0),
            'newly_orphaned': phase2.get('newly_orphaned', 0),
        }

        phase3 = self.transition_eligible(tenant)

        # Phase 4: transitioning
        yield {
            'type': 'progress',
            'phase': 'transitioning',
            'message': 'Transitioning eligible assets...',
            'transitioned': phase3.get('transitioned', 0),
        }

        # Build final report and cache it
        summary = self._build_reconciliation_report(tenant, phase1, phase2, phase3)
        self._last_reconciliation[tenant] = summary

        # Phase 5: complete
        yield {
            'type': 'complete',
            'phase': 'complete',
            'summary': summary,
        }

    def _build_reconciliation_report(self, tenant: str, phase1: dict, phase2: dict, phase3: dict) -> dict:
        """Build reconciliation summary report from phase results.

        Produces the report format specified by Req 6 AC 4:
        - administration: tenant name
        - timestamp: execution timestamp (ISO 8601)
        - total_assets: total registry count from phase1
        - consistent: total_assets minus missing count
        - unregistered: count of S3 objects not in registry
        - missing: count of registry records with no S3 object
        - stale_references: count of stale refs removed in phase2
        - newly_eligible: count of assets transitioned in phase3

        Args:
            tenant: Tenant identifier (administration).
            phase1: Result dict from _reconcile_s3_scan.
            phase2: Result dict from _reconcile_references.
            phase3: Result dict from transition_eligible.

        Returns:
            Summary report dict.
        """
        total_assets = phase1.get('total_registry', 0)
        missing_count = len(phase1.get('missing', []))
        unregistered_count = len(phase1.get('unregistered', []))
        stale_count = phase2.get('stale_removed', 0)
        newly_eligible_count = phase3.get('transitioned', 0)
        consistent = total_assets - missing_count

        return {
            'administration': tenant,
            'timestamp': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
            'total_assets': total_assets,
            'consistent': consistent,
            'unregistered': unregistered_count,
            'missing': missing_count,
            'stale_references': stale_count,
            'newly_eligible': newly_eligible_count,
        }

    def _reconcile_s3_scan(self, tenant: str) -> dict:
        """Phase 1: Compare S3 objects vs registry.

        Lists all objects under {tenant}/ across both buckets (shared and
        public-pages), compares against s3_assets WHERE administration = tenant,
        and identifies:
        - unregistered: S3 objects with no corresponding registry row
        - missing: registry records whose S3 object does not exist in the bucket

        Filters out .folder marker objects (zero-byte directory placeholders).

        Req 6 AC 1: Identify S3 objects with no corresponding row in s3_assets.
        Req 6 AC 2: Identify s3_assets records where S3 object does not exist.
        Req 6 AC 6: Process assets scoped per tenant (administration).

        Args:
            tenant: Tenant identifier (administration).

        Returns:
            Dict with unregistered[], missing[], total_s3, total_registry.
        """
        # Step 1: List all S3 objects across both buckets for this tenant
        s3_objects = {}  # {s3_key: bucket}

        # Shared bucket: categories invoices, branding, templates
        shared_bucket = os.environ.get('S3_SHARED_BUCKET')
        if shared_bucket:
            shared_keys = self._list_s3_objects(shared_bucket, f"{tenant}/")
            for key in shared_keys:
                s3_objects[key] = shared_bucket

        # Public-pages bucket: category landing-pages
        pages_bucket = os.environ.get('LANDING_PAGES_BUCKET')
        if pages_bucket:
            pages_keys = self._list_s3_objects(pages_bucket, f"{tenant}/")
            for key in pages_keys:
                s3_objects[key] = pages_bucket

        # Step 2: Get all registered s3_keys from the registry for this tenant
        registry_query = """
            SELECT s3_key, bucket FROM s3_assets
            WHERE administration = %s
        """
        registry_rows = self.db.execute_query(registry_query, (tenant,), fetch=True)
        registered_keys = {row['s3_key'] for row in registry_rows}

        # Step 3: Compare
        s3_key_set = set(s3_objects.keys())

        # Unregistered: in S3 but NOT in registry
        unregistered = [
            {'s3_key': key, 'bucket': s3_objects[key]}
            for key in sorted(s3_key_set - registered_keys)
        ]

        # Missing: in registry but NOT in S3
        missing = [
            {'s3_key': row['s3_key'], 'bucket': row['bucket']}
            for row in registry_rows
            if row['s3_key'] not in s3_key_set
        ]

        return {
            'unregistered': unregistered,
            'missing': missing,
            'total_s3': len(s3_key_set),
            'total_registry': len(registered_keys),
        }

    def _reconcile_references(self, tenant: str) -> dict:
        """Phase 2: Verify references — check entity existence, remove stale refs.

        For each row in s3_asset_references for this tenant:
        1. Look up entity_type in ENTITY_TYPE_REGISTRY
        2. If entity_type is None (ephemeral) or unknown, skip it
        3. If entity_type has a verification query, check entity existence
        4. If entity doesn't exist → mark reference as stale
        5. DELETE all stale references
        6. For assets whose reference count drops to zero → UPDATE status='ORPHAN'

        Req 6 AC 3: Identify stale references pointing to non-existent entities.
        Req 6 AC 7: Remove stale refs and update asset status to ORPHAN.

        Args:
            tenant: Tenant identifier (administration).

        Returns:
            Dict with stale_removed, newly_orphaned, skipped_types counts.
        """
        # Step 1: Query all references for this tenant
        refs_query = """
            SELECT id, asset_id, entity_type, entity_id
            FROM s3_asset_references
            WHERE administration = %s
        """
        references = self.db.execute_query(refs_query, (tenant,), fetch=True)

        stale_ref_ids = []
        stale_asset_ids = set()
        skipped_types = set()

        # Step 2: For each reference, check entity existence
        for ref in references:
            entity_type = ref['entity_type']
            entity_id = ref['entity_id']

            registry_entry = ENTITY_TYPE_REGISTRY.get(entity_type)

            # Unknown entity_type — skip with warning
            if entity_type not in ENTITY_TYPE_REGISTRY:
                skipped_types.add(entity_type)
                logger.warning(
                    "Unknown entity_type '%s' in s3_asset_references (ref id=%s), skipping",
                    entity_type, ref['id']
                )
                continue

            # Ephemeral type (None) — skip, no existence check
            if registry_entry is None:
                skipped_types.add(entity_type)
                continue

            # Run the existence check query
            _table, _id_col, existence_query = registry_entry
            result = self.db.execute_query(
                existence_query, (entity_id, tenant), fetch=True
            )

            if not result:
                # Entity doesn't exist → stale reference
                stale_ref_ids.append(ref['id'])
                stale_asset_ids.add(ref['asset_id'])

        # Step 3: DELETE stale references
        stale_removed = 0
        if stale_ref_ids:
            with self.db.transaction() as (cursor, conn):
                # Delete stale refs in batches
                placeholders = ', '.join(['%s'] * len(stale_ref_ids))
                cursor.execute(
                    f"DELETE FROM s3_asset_references WHERE id IN ({placeholders})",
                    tuple(stale_ref_ids)
                )
                stale_removed = cursor.rowcount

        # Step 4: For affected assets, check if refs dropped to zero → mark ORPHAN
        newly_orphaned = 0
        now = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')

        if stale_asset_ids:
            with self.db.transaction() as (cursor, conn):
                for asset_id in stale_asset_ids:
                    cursor.execute(
                        "SELECT COUNT(*) AS cnt FROM s3_asset_references "
                        "WHERE asset_id = %s AND administration = %s",
                        (asset_id, tenant)
                    )
                    count_row = cursor.fetchone()
                    ref_count = count_row['cnt'] if isinstance(count_row, dict) else count_row[0]

                    if ref_count == 0:
                        cursor.execute(
                            """
                            UPDATE s3_assets
                            SET status = 'ORPHAN', orphaned_at = %s, updated_at = %s
                            WHERE id = %s AND administration = %s
                              AND status = 'ACTIVE'
                            """,
                            (now, now, asset_id, tenant)
                        )
                        if cursor.rowcount > 0:
                            newly_orphaned += 1

        return {
            'stale_removed': stale_removed,
            'newly_orphaned': newly_orphaned,
            'skipped_types': sorted(skipped_types),
        }

    def _list_s3_objects(self, bucket: str, prefix: str) -> list:
        """List all S3 object keys under a prefix, filtering out .folder markers.

        Uses paginated list_objects_v2 to handle buckets with many objects.
        Excludes zero-byte objects ending in '.folder' (directory placeholders).

        Args:
            bucket: S3 bucket name.
            prefix: Key prefix to list under (e.g., 'TenantA/').

        Returns:
            List of S3 key strings.
        """
        keys = []
        try:
            s3_client = boto3.client('s3')
            paginator = s3_client.get_paginator('list_objects_v2')
            page_iterator = paginator.paginate(Bucket=bucket, Prefix=prefix)

            for page in page_iterator:
                for obj in page.get('Contents', []):
                    key = obj['Key']
                    size = obj.get('Size', 0)
                    # Filter out .folder markers (zero-byte directory placeholders)
                    if key.endswith('.folder') and size == 0:
                        continue
                    keys.append(key)
        except ClientError as e:
            logger.error(
                "S3 list failed: bucket=%s, prefix=%s, error=%s",
                bucket, prefix, str(e)
            )
        except Exception as e:
            logger.error(
                "Unexpected error listing S3 objects: bucket=%s, prefix=%s, error=%s",
                bucket, prefix, str(e)
            )

        return keys

    def transition_eligible(self, tenant: str) -> dict:
        """Move orphans past retention period to DELETION_ELIGIBLE status.

        Evaluates all ORPHAN assets and transitions those whose orphaned_at
        plus their applicable retention period has elapsed. Assets with a
        per-asset retention_days override use that value instead of the
        tenant/system default.

        For landing-pages category, retention differs by media_type:
        - web_content/document → landing_pages_days (default 7)
        - image/video → landing_pages_media_days (default 30)

        AC 2 (Req 5): Change status to DELETION_ELIGIBLE when retention
        exceeded. No S3 object is deleted at this point.
        AC 8 (Req 5): Resolution order: asset-level retention_days →
        tenant-level parameter → system default.

        Args:
            tenant: Tenant identifier (administration).

        Returns:
            Dict with 'success' and 'transitioned' count.
        """
        categories = ['invoices', 'branding', 'templates', 'landing-pages']
        transitioned = 0

        for category in categories:
            if category == 'landing-pages':
                # Landing-pages has different retention per media type group
                # Group 1: web_content (landing_pages_days)
                retention_web = self._get_retention_days(tenant, category, media_type='web_content')
                result_web = self.db.execute_query(
                    """
                    UPDATE s3_assets
                    SET status = 'DELETION_ELIGIBLE'
                    WHERE administration = %s
                      AND category = %s
                      AND status = 'ORPHAN'
                      AND media_type IN ('web_content', 'document')
                      AND (
                          (retention_days IS NOT NULL AND orphaned_at <= DATE_SUB(NOW(), INTERVAL retention_days DAY))
                          OR
                          (retention_days IS NULL AND orphaned_at <= DATE_SUB(NOW(), INTERVAL %s DAY))
                      )
                    """,
                    (tenant, category, retention_web),
                    fetch=False, commit=True
                )
                transitioned += result_web

                # Group 2: image/video (landing_pages_media_days)
                retention_media = self._get_retention_days(tenant, category, media_type='image')
                result_media = self.db.execute_query(
                    """
                    UPDATE s3_assets
                    SET status = 'DELETION_ELIGIBLE'
                    WHERE administration = %s
                      AND category = %s
                      AND status = 'ORPHAN'
                      AND media_type IN ('image', 'video')
                      AND (
                          (retention_days IS NOT NULL AND orphaned_at <= DATE_SUB(NOW(), INTERVAL retention_days DAY))
                          OR
                          (retention_days IS NULL AND orphaned_at <= DATE_SUB(NOW(), INTERVAL %s DAY))
                      )
                    """,
                    (tenant, category, retention_media),
                    fetch=False, commit=True
                )
                transitioned += result_media
            else:
                # Non-landing-pages: single retention value for the category
                retention = self._get_retention_days(tenant, category, media_type=None)
                result = self.db.execute_query(
                    """
                    UPDATE s3_assets
                    SET status = 'DELETION_ELIGIBLE'
                    WHERE administration = %s
                      AND category = %s
                      AND status = 'ORPHAN'
                      AND (
                          (retention_days IS NOT NULL AND orphaned_at <= DATE_SUB(NOW(), INTERVAL retention_days DAY))
                          OR
                          (retention_days IS NULL AND orphaned_at <= DATE_SUB(NOW(), INTERVAL %s DAY))
                      )
                    """,
                    (tenant, category, retention),
                    fetch=False, commit=True
                )
                transitioned += result

        return {'success': True, 'transitioned': transitioned}

    # === Tenant Admin: Unregistered Objects ===

    def get_unregistered_objects(self, tenant: str) -> dict:
        """List S3 objects that are not registered in the asset registry.

        Performs a scan of S3 buckets for this tenant and compares against
        the registry. Returns detailed metadata for unregistered objects
        including size and last_modified.

        Args:
            tenant: Tenant identifier (administration).

        Returns:
            Dict with 'success' and 'data' containing list of unregistered objects.
        """
        import os
        import boto3
        from botocore.exceptions import ClientError

        s3_objects = {}  # {s3_key: {bucket, size, last_modified}}

        s3_client = boto3.client('s3')

        def list_with_metadata(bucket, prefix):
            """List S3 objects with full metadata."""
            try:
                paginator = s3_client.get_paginator('list_objects_v2')
                page_iterator = paginator.paginate(Bucket=bucket, Prefix=prefix)

                for page in page_iterator:
                    for obj in page.get('Contents', []):
                        key = obj['Key']
                        size = obj.get('Size', 0)
                        # Filter out .folder markers
                        if key.endswith('.folder') and size == 0:
                            continue
                        s3_objects[key] = {
                            'bucket': bucket,
                            'size': size,
                            'last_modified': obj.get('LastModified', '').isoformat()
                            if obj.get('LastModified') else None,
                        }
            except ClientError as e:
                logger.error(
                    "S3 list failed: bucket=%s, prefix=%s, error=%s",
                    bucket, prefix, str(e)
                )

        # Scan shared bucket
        shared_bucket = os.environ.get('S3_SHARED_BUCKET')
        if shared_bucket:
            list_with_metadata(shared_bucket, f"{tenant}/")

        # Scan public-pages bucket
        pages_bucket = os.environ.get('LANDING_PAGES_BUCKET')
        if pages_bucket:
            list_with_metadata(pages_bucket, f"{tenant}/")

        # Get registered keys
        registry_query = """
            SELECT s3_key FROM s3_assets
            WHERE administration = %s
        """
        registry_rows = self.db.execute_query(registry_query, (tenant,), fetch=True)
        registered_keys = {row['s3_key'] for row in registry_rows}

        # Find unregistered objects
        unregistered = []
        for key in sorted(s3_objects.keys()):
            if key not in registered_keys:
                info = s3_objects[key]
                unregistered.append({
                    's3_key': key,
                    'bucket': info['bucket'],
                    'size': info['size'],
                    'last_modified': info['last_modified'],
                })

        return {'success': True, 'data': unregistered}

    def delete_unregistered_objects(self, tenant: str, s3_keys: list, operator: str) -> dict:
        """Delete unregistered S3 objects permanently.

        Verifies each key is truly unregistered before deletion. Skips any
        key that exists in the registry (safety guard).

        Args:
            tenant: Tenant identifier (administration).
            s3_keys: List of S3 keys to delete.
            operator: Email of the user performing the deletion.

        Returns:
            Dict with 'success', 'deleted', and 'skipped' counts.
        """
        import os
        import boto3
        from botocore.exceptions import ClientError

        # Safety check: verify keys are not registered
        if s3_keys:
            placeholders = ', '.join(['%s'] * len(s3_keys))
            check_query = f"""
                SELECT s3_key FROM s3_assets
                WHERE administration = %s AND s3_key IN ({placeholders})
            """
            params = [tenant] + s3_keys
            registered = self.db.execute_query(check_query, tuple(params), fetch=True)
            registered_set = {row['s3_key'] for row in registered}
        else:
            registered_set = set()

        # Resolve bucket for each key
        shared_bucket = os.environ.get('S3_SHARED_BUCKET')
        pages_bucket = os.environ.get('LANDING_PAGES_BUCKET')

        s3_client = boto3.client('s3')
        deleted = 0
        skipped = 0

        for key in s3_keys:
            # Skip registered keys
            if key in registered_set:
                skipped += 1
                logger.warning(
                    "Skipping delete of registered key: tenant=%s, key=%s",
                    tenant, key
                )
                continue

            # Verify key belongs to this tenant
            if not key.startswith(f"{tenant}/"):
                skipped += 1
                logger.warning(
                    "Skipping delete of non-tenant key: tenant=%s, key=%s",
                    tenant, key
                )
                continue

            # Determine bucket from key path
            # landing-pages go in pages_bucket, others in shared_bucket
            bucket = pages_bucket if '/landing-pages/' in key else shared_bucket

            if not bucket:
                skipped += 1
                continue

            try:
                s3_client.delete_object(Bucket=bucket, Key=key)
                deleted += 1
                logger.info(
                    "Deleted unregistered S3 object: tenant=%s, key=%s, operator=%s",
                    tenant, key, operator
                )
            except ClientError as e:
                skipped += 1
                logger.error(
                    "Failed to delete S3 object: key=%s, error=%s",
                    key, str(e)
                )

        return {'success': True, 'deleted': deleted, 'skipped': skipped}

    # === Tenant Admin: Dashboard & Duplicates ===

    def get_dashboard_stats(self, tenant: str) -> dict:
        """Get summary statistics for the tenant admin dashboard.

        Queries aggregate counts by status, storage by category, the last
        reconciliation timestamp, and the top orphaned assets.

        Args:
            tenant: Tenant identifier (administration).

        Returns:
            Dict with 'success' and 'data' containing summary stats.
        """
        # Total counts by status
        status_query = """
            SELECT status, COUNT(*) AS cnt
            FROM s3_assets
            WHERE administration = %s
            GROUP BY status
        """
        status_rows = self.db.execute_query(status_query, (tenant,), fetch=True)

        total_assets = 0
        active_assets = 0
        orphaned_assets = 0
        deletion_eligible = 0

        for row in status_rows:
            count = row['cnt']
            status = row['status']
            total_assets += count
            if status == 'ACTIVE':
                active_assets = count
            elif status == 'ORPHAN':
                orphaned_assets = count
            elif status == 'DELETION_ELIGIBLE':
                deletion_eligible = count

        # Storage by category
        category_query = """
            SELECT category, COUNT(*) AS cnt, COALESCE(SUM(file_size), 0) AS total_bytes
            FROM s3_assets
            WHERE administration = %s
            GROUP BY category
        """
        category_rows = self.db.execute_query(category_query, (tenant,), fetch=True)

        storage_by_category = {}
        for row in category_rows:
            storage_by_category[row['category']] = {
                'count': row['cnt'],
                'bytes': int(row['total_bytes']),
            }

        # Last scan timestamp (from in-memory cache)
        last_scan_at = None
        cached = self._last_reconciliation.get(tenant)
        if cached and 'timestamp' in cached:
            last_scan_at = cached['timestamp']

        # Top orphans (oldest orphaned assets, limit 10)
        orphans_query = """
            SELECT id, original_filename, file_size, orphaned_at,
                   DATEDIFF(NOW(), orphaned_at) AS days_orphaned
            FROM s3_assets
            WHERE administration = %s AND status IN ('ORPHAN', 'DELETION_ELIGIBLE')
              AND orphaned_at IS NOT NULL
            ORDER BY orphaned_at ASC
            LIMIT 10
        """
        orphan_rows = self.db.execute_query(orphans_query, (tenant,), fetch=True)

        top_orphans = []
        for row in orphan_rows:
            top_orphans.append({
                'id': row['id'],
                'filename': row['original_filename'],
                'size': row['file_size'],
                'days_orphaned': row['days_orphaned'] or 0,
            })

        return {
            'success': True,
            'data': {
                'total_assets': total_assets,
                'active_assets': active_assets,
                'orphaned_assets': orphaned_assets,
                'deletion_eligible': deletion_eligible,
                'storage_by_category': storage_by_category,
                'last_scan_at': last_scan_at,
                'top_orphans': top_orphans,
            },
        }

    def get_duplicate_groups(self, tenant: str) -> dict:
        """List duplicate content_hash groups for this tenant.

        Finds all content_hash values that have more than one asset row,
        then returns the grouped assets for each hash.

        Args:
            tenant: Tenant identifier (administration).

        Returns:
            Dict with 'success' and 'data' containing list of duplicate groups.
        """
        # Find hashes with duplicates
        hash_query = """
            SELECT content_hash, COUNT(*) AS cnt
            FROM s3_assets
            WHERE administration = %s
              AND content_hash IS NOT NULL
              AND content_hash != ''
            GROUP BY content_hash
            HAVING COUNT(*) > 1
            ORDER BY cnt DESC
        """
        hash_rows = self.db.execute_query(hash_query, (tenant,), fetch=True)

        groups = []
        for row in hash_rows:
            content_hash = row['content_hash']
            count = row['cnt']

            # Get the assets for this hash
            assets_query = """
                SELECT id, original_filename, file_size, category, status, created_at,
                       (SELECT COUNT(*) FROM s3_asset_references r
                        WHERE r.asset_id = a.id AND r.administration = %s) AS reference_count
                FROM s3_assets a
                WHERE a.administration = %s AND a.content_hash = %s
                ORDER BY a.created_at ASC
            """
            asset_rows = self.db.execute_query(
                assets_query, (tenant, tenant, content_hash), fetch=True
            )

            assets = []
            for asset_row in asset_rows:
                assets.append({
                    'id': asset_row['id'],
                    'original_filename': asset_row['original_filename'],
                    'file_size': asset_row['file_size'],
                    'category': asset_row['category'],
                    'status': asset_row['status'],
                    'created_at': asset_row['created_at'],
                    'reference_count': asset_row['reference_count'],
                })

            groups.append({
                'content_hash': content_hash,
                'count': count,
                'assets': assets,
            })

        return {'success': True, 'data': groups}

    def merge_duplicates(self, tenant: str, keep_asset_id: str, duplicate_asset_ids: list) -> dict:
        """Merge duplicate assets: keep one, re-attach refs, delete the rest.

        For each duplicate asset:
        1. Re-attach all references from the duplicate to the kept asset
        2. Delete the duplicate's S3 object
        3. Remove the duplicate's DB records

        Args:
            tenant: Tenant identifier (administration).
            keep_asset_id: The asset ID to keep (primary).
            duplicate_asset_ids: List of asset IDs to merge into the kept one.

        Returns:
            Dict with 'success', 'kept', 'merged', and 'deleted' counts.
        """
        # Verify the keep asset exists and belongs to tenant
        keep_query = """
            SELECT id, content_hash FROM s3_assets
            WHERE id = %s AND administration = %s
        """
        keep_rows = self.db.execute_query(keep_query, (keep_asset_id, tenant), fetch=True)
        if not keep_rows:
            return {'success': False, 'error': f"Keep asset '{keep_asset_id}' not found"}

        merged = 0
        deleted = 0
        now = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')

        for dup_id in duplicate_asset_ids:
            if dup_id == keep_asset_id:
                continue  # Skip if someone accidentally includes the keep asset

            with self.db.transaction() as (cursor, conn):
                # Verify duplicate belongs to tenant
                cursor.execute(
                    "SELECT id, s3_key, bucket FROM s3_assets "
                    "WHERE id = %s AND administration = %s",
                    (dup_id, tenant)
                )
                dup_row = cursor.fetchone()
                if not dup_row:
                    continue  # Skip non-existent or wrong-tenant assets

                # Re-attach all references from duplicate to the kept asset
                cursor.execute(
                    """
                    SELECT id, entity_type, entity_id
                    FROM s3_asset_references
                    WHERE asset_id = %s AND administration = %s
                    """,
                    (dup_id, tenant)
                )
                refs = cursor.fetchall()

                for ref in refs:
                    entity_type = ref['entity_type'] if isinstance(ref, dict) else ref[1]
                    entity_id = ref['entity_id'] if isinstance(ref, dict) else ref[2]

                    # Try to insert the reference for the kept asset (ignore if exists)
                    try:
                        cursor.execute(
                            """
                            INSERT INTO s3_asset_references
                            (administration, asset_id, entity_type, entity_id, created_at)
                            VALUES (%s, %s, %s, %s, %s)
                            """,
                            (tenant, keep_asset_id, entity_type, entity_id, now)
                        )
                    except IntegrityError:
                        # Reference already exists on kept asset — skip
                        pass

                # Delete duplicate's references
                cursor.execute(
                    "DELETE FROM s3_asset_references WHERE asset_id = %s AND administration = %s",
                    (dup_id, tenant)
                )

                # Delete duplicate's S3 object
                s3_key = dup_row['s3_key'] if isinstance(dup_row, dict) else dup_row[1]
                bucket = dup_row['bucket'] if isinstance(dup_row, dict) else dup_row[2]
                self._delete_raw(bucket, s3_key)

                # Delete duplicate's DB record
                cursor.execute(
                    "DELETE FROM s3_assets WHERE id = %s AND administration = %s",
                    (dup_id, tenant)
                )

                merged += len(refs)
                deleted += 1

        # Ensure kept asset is ACTIVE (it now has references)
        self.db.execute_query(
            "UPDATE s3_assets SET status = 'ACTIVE', orphaned_at = NULL, updated_at = %s "
            "WHERE id = %s AND administration = %s AND status != 'ACTIVE'",
            (now, keep_asset_id, tenant),
            fetch=False, commit=True
        )

        logger.info(
            "Merge duplicates: kept=%s, deleted=%d, refs_moved=%d, tenant=%s",
            keep_asset_id, deleted, merged, tenant
        )

        return {
            'success': True,
            'kept': keep_asset_id,
            'merged': merged,
            'deleted': deleted,
        }

    # === Retention Settings ===

    # The full set of allowed retention parameter keys
    RETENTION_KEYS = (
        'invoices_days',
        'branding_days',
        'templates_days',
        'landing_pages_days',
        'landing_pages_media_days',
    )

    def get_retention_settings(self, tenant: str) -> dict:
        """Get resolved retention settings with source indicator per key.

        For each known retention key, resolves the effective value and
        determines whether it comes from a tenant override or the system
        default (CODE_DEFAULTS).

        Args:
            tenant: Tenant identifier (administration).

        Returns:
            Dict with 'success' and 'data' mapping each key to
            {value, source} where source is 'tenant_override' or 'system_default'.
        """
        from services.parameter_service import CODE_DEFAULTS

        data = {}
        for key in self.RETENTION_KEYS:
            # Check if tenant has an override in the DB
            tenant_value = self.ps._resolve_from_db('tenant', tenant, 'asset_retention', key)

            if tenant_value is not None:
                data[key] = {'value': int(tenant_value), 'source': 'tenant_override'}
            else:
                # Fall back to CODE_DEFAULTS (system default)
                code_default = CODE_DEFAULTS.get(('asset_retention', key))
                value = code_default['value'] if code_default else 30
                data[key] = {'value': int(value), 'source': 'system_default'}

        return {'success': True, 'data': data}

    def update_retention_settings(self, tenant: str, updates: dict) -> dict:
        """Validate and save tenant-level retention overrides.

        Accepts a dict of key-value pairs where keys must be in RETENTION_KEYS
        and values must be positive integers. Each valid pair is saved as a
        tenant-scope parameter via ParameterService.

        Args:
            tenant: Tenant identifier (administration).
            updates: Dict mapping retention keys to integer day values.

        Returns:
            Dict with 'success' and 'updated' list of keys that were saved.

        Raises:
            ValueError: If any key is not in the allowed set or value is invalid.
        """
        invalid_keys = [k for k in updates if k not in self.RETENTION_KEYS]
        if invalid_keys:
            raise ValueError(
                f"Invalid retention keys: {', '.join(invalid_keys)}. "
                f"Allowed: {', '.join(self.RETENTION_KEYS)}"
            )

        updated = []
        for key, value in updates.items():
            if not isinstance(value, (int, float)) or value <= 0:
                raise ValueError(
                    f"Invalid value for '{key}': must be a positive integer"
                )

            self.ps.set_param(
                scope='tenant',
                scope_id=tenant,
                namespace='asset_retention',
                key=key,
                value=int(value),
                value_type='number',
            )
            updated.append(key)

        return {'success': True, 'updated': updated}

    # === Import ===

    def import_legacy_assets(self, tenant: str, category: str) -> dict:
        """Scan S3 prefix and register untracked objects in the registry.

        Scans the S3 bucket/prefix for the given tenant and category,
        identifies objects not yet registered in s3_assets, and INSERTs
        new rows with status=ACTIVE and migrated_at=NOW().

        Does NOT re-upload, move, copy, or modify any existing S3 objects.

        AC 1: Scan S3 bucket and prefix, identify unregistered objects.
        AC 2: INSERT with status=ACTIVE, detected mime_type, file_size, etc.
        AC 3: SHALL NOT re-upload, move, copy, or modify S3 objects.
        AC 4: Generate ast_<ULID> id for each imported asset.
        AC 5: Skip objects whose s3_key already matches — safe for repeat runs.
        AC 6: Return summary report.
        AC 7: Import scoped to authenticated tenant.
        AC 8: Unclassifiable objects skipped and included in report.

        Args:
            tenant: Tenant identifier (administration).
            category: Asset category (invoices, branding, templates, landing-pages).

        Returns:
            Dict with success, administration, category, total_scanned,
            newly_registered, already_registered, unclassified.
        """
        # Step 1: Resolve bucket from category
        bucket = self._resolve_bucket(category)

        # Step 2: List S3 objects with metadata under {tenant}/{category}/
        prefix = f"{tenant}/{category}/"
        s3_objects = self._list_s3_objects_detailed(bucket, prefix)
        total_scanned = len(s3_objects)

        # Step 3: Get existing s3_keys from registry for this tenant+category
        existing_query = """
            SELECT s3_key FROM s3_assets
            WHERE administration = %s AND category = %s
        """
        existing_rows = self.db.execute_query(existing_query, (tenant, category), fetch=True)
        existing_keys = {row['s3_key'] for row in existing_rows}

        # Step 4: Process each unregistered object
        newly_registered = 0
        already_registered = 0
        unclassified = []
        now = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')

        for obj in s3_objects:
            s3_key = obj['key']
            file_size = obj['size']

            # AC 5: Skip objects already registered
            if s3_key in existing_keys:
                already_registered += 1
                continue

            # Extract original_filename from key (last segment after the last '/')
            original_filename = s3_key.rsplit('/', 1)[-1] if '/' in s3_key else s3_key

            # Detect media_type from extension
            ext = os.path.splitext(original_filename)[1].lower()
            detected_media_type = None
            for media_type, rules in self.MEDIA_TYPES.items():
                if ext in rules['extensions']:
                    detected_media_type = media_type
                    break

            # AC 8: Unclassifiable objects (unknown extension) are skipped
            if detected_media_type is None:
                unclassified.append({
                    's3_key': s3_key,
                    'filename': original_filename,
                    'reason': f"Unknown extension '{ext}'",
                })
                continue

            # Generate asset_id
            asset_id = self._generate_asset_id()

            # Detect mime_type from extension
            mime_type = mimetypes.guess_type(original_filename)[0] or 'application/octet-stream'

            # INSERT into s3_assets with status=ACTIVE, migrated_at=NOW()
            insert_query = """
                INSERT INTO s3_assets
                (id, administration, bucket, s3_key, mime_type, file_size,
                 category, media_type, original_filename, status, migrated_at, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
            self.db.execute_query(
                insert_query,
                (
                    asset_id, tenant, bucket, s3_key, mime_type, file_size,
                    category, detected_media_type, original_filename,
                    'ACTIVE', now, now,
                ),
                fetch=False,
                commit=True,
            )
            newly_registered += 1

        # AC 6: Return summary report
        return {
            'success': True,
            'administration': tenant,
            'category': category,
            'total_scanned': total_scanned,
            'newly_registered': newly_registered,
            'already_registered': already_registered,
            'unclassified': unclassified,
        }

    # === Reference Discovery ===

    def discover_invoice_references(self, tenant: str) -> dict:
        """Discover references from mutaties.Ref3 matching registered s3_keys.

        Scans the mutaties table for Ref3 values that match s3_keys in the
        asset registry, and creates s3_asset_references entries for each match.

        Req 11 Phase 1, AC 2: For each registered legacy asset, scan mutaties
        for Ref3 column matching the asset's s3_key → entity_type='invoice',
        entity_id=mutaties.ID.

        Args:
            tenant: Tenant identifier (administration).

        Returns:
            Dict with success, references_created count, already_linked count.
        """
        # Step 1: Get all registered invoice s3_keys for this tenant
        assets_query = """
            SELECT id, s3_key FROM s3_assets
            WHERE administration = %s AND category = 'invoices'
        """
        assets = self.db.execute_query(assets_query, (tenant,), fetch=True)

        if not assets:
            return {'success': True, 'references_created': 0, 'already_linked': 0}

        # Step 2: Build a lookup: s3_key → asset_id
        key_to_asset = {row['s3_key']: row['id'] for row in assets}

        # Step 3: Scan mutaties for Ref3 values that match any registered s3_key
        references_created = 0
        already_linked = 0

        for s3_key, asset_id in key_to_asset.items():
            # Find mutaties rows where Ref3 exactly matches this s3_key
            match_query = """
                SELECT ID FROM mutaties
                WHERE administration = %s AND Ref3 = %s
            """
            matches = self.db.execute_query(match_query, (tenant, s3_key), fetch=True)

            for match in matches:
                mutatie_id = str(match['ID'])
                # INSERT reference (idempotent via unique constraint)
                try:
                    insert_query = """
                        INSERT INTO s3_asset_references
                        (administration, asset_id, entity_type, entity_id, created_at)
                        VALUES (%s, %s, %s, %s, NOW())
                    """
                    self.db.execute_query(
                        insert_query,
                        (tenant, asset_id, 'invoice', mutatie_id),
                        fetch=False, commit=True
                    )
                    references_created += 1
                except IntegrityError:
                    # Already linked (unique constraint on asset_id, entity_type, entity_id)
                    already_linked += 1

        return {
            'success': True,
            'references_created': references_created,
            'already_linked': already_linked,
        }

    def discover_branding_references(self, tenant: str) -> dict:
        """Discover references from parameter_values (branding) matching s3_keys.

        Scans parameter_values where namespace='branding' for values that match
        registered s3_keys in the asset registry, and creates s3_asset_references
        entries for each match.

        Req 11 Phase 1, AC 2: Branding assets — scan parameter_values where
        namespace='branding' for S3 key values → entity_type='branding',
        entity_id='{tenant}:{key}'.

        Args:
            tenant: Tenant identifier (administration).

        Returns:
            Dict with success, references_created count, already_linked count.
        """
        # Step 1: Get all registered branding s3_keys for this tenant
        assets_query = """
            SELECT id, s3_key FROM s3_assets
            WHERE administration = %s AND category = 'branding'
        """
        assets = self.db.execute_query(assets_query, (tenant,), fetch=True)

        if not assets:
            return {'success': True, 'references_created': 0, 'already_linked': 0}

        # Step 2: Build a lookup: s3_key → asset_id
        key_to_asset = {row['s3_key']: row['id'] for row in assets}

        # Step 3: Scan parameter_values for branding entries matching registered s3_keys
        references_created = 0
        already_linked = 0

        for s3_key, asset_id in key_to_asset.items():
            match_query = """
                SELECT `key` FROM parameter_values
                WHERE namespace = 'branding' AND scope_type = 'tenant'
                  AND scope_value = %s AND value = %s
            """
            matches = self.db.execute_query(match_query, (tenant, s3_key), fetch=True)

            for match in matches:
                param_key = match['key']
                entity_id = f"{tenant}:{param_key}"
                try:
                    insert_query = """
                        INSERT INTO s3_asset_references
                        (administration, asset_id, entity_type, entity_id, created_at)
                        VALUES (%s, %s, %s, %s, NOW())
                    """
                    self.db.execute_query(
                        insert_query,
                        (tenant, asset_id, 'branding', entity_id),
                        fetch=False, commit=True
                    )
                    references_created += 1
                except IntegrityError:
                    already_linked += 1

        return {
            'success': True,
            'references_created': references_created,
            'already_linked': already_linked,
        }

    def discover_landing_page_references(self, tenant: str) -> dict:
        """Discover references from landing_pages content matching s3_keys.

        Scans the landing_pages table for JSON content that contains registered
        s3_keys (simple string search), and creates s3_asset_references entries.

        Req 11 Phase 1, AC 2: Landing page assets — scan landing_pages table
        for JSON content containing S3 keys → entity_type='landing_page',
        entity_id=landing_pages.id.

        Args:
            tenant: Tenant identifier (administration).

        Returns:
            Dict with success, references_created count, already_linked count.
        """
        # Step 1: Get all registered landing-pages s3_keys for this tenant
        assets_query = """
            SELECT id, s3_key FROM s3_assets
            WHERE administration = %s AND category = 'landing-pages'
        """
        assets = self.db.execute_query(assets_query, (tenant,), fetch=True)

        if not assets:
            return {'success': True, 'references_created': 0, 'already_linked': 0}

        # Step 2: Get all landing pages for this tenant
        pages_query = """
            SELECT id, content FROM landing_pages
            WHERE administration = %s
        """
        pages = self.db.execute_query(pages_query, (tenant,), fetch=True)

        if not pages:
            return {'success': True, 'references_created': 0, 'already_linked': 0}

        # Step 3: For each page, check if content contains any registered s3_key
        references_created = 0
        already_linked = 0

        for page in pages:
            page_id = str(page['id'])
            content = page.get('content') or ''

            for asset in assets:
                s3_key = asset['s3_key']
                asset_id = asset['id']

                # Simple string search: does the content contain this s3_key?
                if s3_key in content:
                    try:
                        insert_query = """
                            INSERT INTO s3_asset_references
                            (administration, asset_id, entity_type, entity_id, created_at)
                            VALUES (%s, %s, %s, %s, NOW())
                        """
                        self.db.execute_query(
                            insert_query,
                            (tenant, asset_id, 'landing_page', page_id),
                            fetch=False, commit=True
                        )
                        references_created += 1
                    except IntegrityError:
                        already_linked += 1

        return {
            'success': True,
            'references_created': references_created,
            'already_linked': already_linked,
        }

    def discover_template_references(self, tenant: str) -> dict:
        """Discover references from parameter_values (templates) matching s3_keys.

        Scans parameter_values where namespace='templates' for values that match
        registered s3_keys in the asset registry, and creates s3_asset_references
        entries for each match.

        Req 11 Phase 1, AC 2: Templates — scan parameter_values where
        namespace='templates' for S3 key values → entity_type='template',
        entity_id='{key}' (the template parameter key).

        Args:
            tenant: Tenant identifier (administration).

        Returns:
            Dict with success, references_created count, already_linked count.
        """
        # Step 1: Get all registered template s3_keys for this tenant
        assets_query = """
            SELECT id, s3_key FROM s3_assets
            WHERE administration = %s AND category = 'templates'
        """
        assets = self.db.execute_query(assets_query, (tenant,), fetch=True)

        if not assets:
            return {'success': True, 'references_created': 0, 'already_linked': 0}

        # Step 2: Build a lookup: s3_key → asset_id
        key_to_asset = {row['s3_key']: row['id'] for row in assets}

        # Step 3: Scan parameter_values for template entries matching registered s3_keys
        references_created = 0
        already_linked = 0

        for s3_key, asset_id in key_to_asset.items():
            match_query = """
                SELECT `key` FROM parameter_values
                WHERE namespace = 'templates' AND scope_type = 'tenant'
                  AND scope_value = %s AND value = %s
            """
            matches = self.db.execute_query(match_query, (tenant, s3_key), fetch=True)

            for match in matches:
                template_key = match['key']
                try:
                    insert_query = """
                        INSERT INTO s3_asset_references
                        (administration, asset_id, entity_type, entity_id, created_at)
                        VALUES (%s, %s, %s, %s, NOW())
                    """
                    self.db.execute_query(
                        insert_query,
                        (tenant, asset_id, 'template', template_key),
                        fetch=False, commit=True
                    )
                    references_created += 1
                except IntegrityError:
                    already_linked += 1

        return {
            'success': True,
            'references_created': references_created,
            'already_linked': already_linked,
        }

    # === Orphan Marking (Post-Import) ===

    def mark_unreferenced_as_orphans(self, tenant: str) -> dict:
        """Mark imported assets with zero references as ORPHAN.

        Uses migrated_at as the orphaned_at timestamp (Req 11 AC 3).
        Only targets assets that were imported (migrated_at IS NOT NULL)
        and currently have status=ACTIVE with no references.

        Called after import + reference discovery completes for a tenant.

        Args:
            tenant: Tenant identifier (administration).

        Returns:
            Dict with 'success' and 'orphaned' count of newly orphaned assets.
        """
        query = """
            UPDATE s3_assets a
            SET a.status = 'ORPHAN', a.orphaned_at = a.migrated_at
            WHERE a.administration = %s
              AND a.migrated_at IS NOT NULL
              AND a.status = 'ACTIVE'
              AND NOT EXISTS (
                  SELECT 1 FROM s3_asset_references r
                  WHERE r.asset_id = a.id AND r.administration = %s
              )
        """
        result = self.db.execute_query(query, (tenant, tenant), fetch=False, commit=True)
        return {'success': True, 'orphaned': result}

    def _list_s3_objects_detailed(self, bucket: str, prefix: str) -> list:
        """List S3 objects with metadata under a prefix.

        Similar to _list_s3_objects but returns dicts with key and size
        for use by import_legacy_assets.

        Args:
            bucket: S3 bucket name.
            prefix: Key prefix to list under (e.g., 'TenantA/invoices/').

        Returns:
            List of dicts with 'key' (str) and 'size' (int).
        """
        objects = []
        try:
            s3_client = boto3.client('s3')
            paginator = s3_client.get_paginator('list_objects_v2')
            page_iterator = paginator.paginate(Bucket=bucket, Prefix=prefix)

            for page in page_iterator:
                for obj in page.get('Contents', []):
                    key = obj['Key']
                    size = obj.get('Size', 0)
                    # Filter out .folder markers (zero-byte directory placeholders)
                    if key.endswith('.folder') and size == 0:
                        continue
                    objects.append({'key': key, 'size': size})
        except ClientError as e:
            logger.error(
                "S3 list failed: bucket=%s, prefix=%s, error=%s",
                bucket, prefix, str(e)
            )
        except Exception as e:
            logger.error(
                "Unexpected error listing S3 objects: bucket=%s, prefix=%s, error=%s",
                bucket, prefix, str(e)
            )

        return objects

    # === Internal helpers (fully implemented) ===

    def _generate_asset_id(self) -> str:
        """Generate ast_<ULID> identifier.

        Returns:
            String in format 'ast_' followed by a ULID.
        """
        return f"ast_{ULID()}"

    def _resolve_bucket(self, category: str) -> str:
        """Resolve bucket name from env var based on category.

        Args:
            category: One of the keys in CATEGORY_BUCKETS.

        Returns:
            The bucket name from the corresponding environment variable.

        Raises:
            ValueError: If category is not recognized or env var is not set.
        """
        env_var = self.CATEGORY_BUCKETS.get(category)
        if env_var is None:
            valid_categories = ', '.join(sorted(self.CATEGORY_BUCKETS.keys()))
            raise ValueError(
                f"Unknown category '{category}'. "
                f"Valid categories: {valid_categories}"
            )

        bucket = os.environ.get(env_var)
        if not bucket:
            raise ValueError(
                f"Environment variable '{env_var}' is not set "
                f"(required for category '{category}')"
            )

        return bucket

    def _build_s3_key(self, tenant: str, category: str, asset_id: str, filename: str) -> str:
        """Build S3 key path: {tenant}/{category}/{asset_id}_{filename}.

        Args:
            tenant: Tenant identifier (administration).
            category: Asset category (e.g., 'invoices', 'branding').
            asset_id: Generated asset ID (ast_<ULID>).
            filename: Original filename.

        Returns:
            The full S3 key string.
        """
        return f"{tenant}/{category}/{asset_id}_{filename}"

    def _validate_file(self, file_data: bytes, filename: str) -> dict:
        """Validate file type (extension + magic bytes) and size.

        Checks:
        1. File is not empty
        2. Extension matches a known media type
        3. Content headers (magic bytes) match the expected type
           (skipped for web content: .html, .json)
        4. File size is within limits for the detected media type

        Args:
            file_data: Raw file bytes.
            filename: Original filename with extension.

        Returns:
            Dict with 'media_type' and 'mime_type' on success.

        Raises:
            ValueError: If validation fails (empty file, bad type, oversized).
        """
        # AC 7: Check empty file
        if not file_data:
            raise ValueError("A file is required. The upload contained no file or an empty file body.")

        ext = os.path.splitext(filename)[1].lower()

        # Find which media_type this extension belongs to
        detected_media_type = None
        for media_type, rules in self.MEDIA_TYPES.items():
            if ext in rules['extensions']:
                detected_media_type = media_type
                break

        # AC 5: Unsupported extension
        if detected_media_type is None:
            allowed_summary = "; ".join(
                f"{mt}: {', '.join(sorted(rules['extensions']))}"
                for mt, rules in self.MEDIA_TYPES.items()
            )
            raise ValueError(
                f"Unsupported file type '{ext}'. "
                f"Allowed types — {allowed_summary}"
            )

        # AC 3: Validate magic bytes (skip for web content)
        if detected_media_type == 'web_content':
            mime_type = self._sniff_web_content(file_data, ext)
        elif ext == '.svg':
            # SVG is text-based XML — validate by content sniffing, not magic bytes
            mime_type = self._validate_svg_content(file_data)
        else:
            mime_type = self._validate_magic_bytes(file_data, ext, detected_media_type)

        # AC 4 & 6: Validate file size
        max_size = self.MEDIA_TYPES[detected_media_type]['max_size']
        if len(file_data) > max_size:
            max_mb = max_size / (1024 * 1024)
            file_mb = len(file_data) / (1024 * 1024)
            raise ValueError(
                f"File size ({file_mb:.1f} MB) exceeds the {max_mb:.0f} MB "
                f"limit for media type '{detected_media_type}'."
            )

        return {
            'media_type': detected_media_type,
            'mime_type': mime_type,
        }

    def _validate_magic_bytes(self, file_data: bytes, ext: str, media_type: str) -> str:
        """Validate binary file content against known magic byte signatures.

        Args:
            file_data: Raw file bytes.
            ext: File extension (lowercase, with dot).
            media_type: Expected media type category.

        Returns:
            Detected MIME type string.

        Raises:
            ValueError: If magic bytes don't match any known signature for the type.
        """
        detected_mime = self._detect_mime_from_bytes(file_data)

        if detected_mime is None:
            raise ValueError(
                f"File content does not match any known format for "
                f"media type '{media_type}'. The file may be corrupted or "
                f"the extension '{ext}' does not match the actual content."
            )

        # Cross-check: detected MIME should match the media type's expected prefixes
        expected_prefixes = self.MEDIA_TYPES[media_type]['mime_prefixes']
        if not any(detected_mime.startswith(prefix) for prefix in expected_prefixes):
            raise ValueError(
                f"File content detected as '{detected_mime}' does not match "
                f"the expected type for extension '{ext}' "
                f"(expected: {', '.join(expected_prefixes)}). "
                f"The file extension may not match its actual content."
            )

        return detected_mime

    def _detect_mime_from_bytes(self, file_data: bytes) -> Optional[str]:
        """Detect MIME type from file content using magic bytes.

        Args:
            file_data: Raw file bytes (at least first 12 bytes needed).

        Returns:
            Detected MIME type string, or None if no match found.
        """
        if len(file_data) < 4:
            return None

        # Check each signature against the file header
        for signature, mime_type in self.MAGIC_BYTES.items():
            if mime_type == 'image/webp':
                # WEBP: starts with RIFF, then has WEBP at offset 8
                if (file_data[:4] == b'RIFF' and
                        len(file_data) >= 12 and
                        file_data[8:12] == b'WEBP'):
                    return 'image/webp'
            elif mime_type == 'video/mp4':
                # MP4: has 'ftyp' at offset 4
                if (len(file_data) >= 8 and
                        file_data[4:8] == b'ftyp'):
                    return 'video/mp4'
            else:
                if file_data[:len(signature)] == signature:
                    return mime_type

        return None

    def _sniff_web_content(self, file_data: bytes, ext: str) -> str:
        """Validate web content files by extension + basic content check.

        Web content (.html, .json) has no reliable magic bytes.
        Validation is by extension match and basic content sniffing.

        Args:
            file_data: Raw file bytes.
            ext: File extension (lowercase, with dot).

        Returns:
            MIME type for the web content.

        Raises:
            ValueError: If content doesn't appear to be valid for the extension.
        """
        if ext == '.html':
            # Basic check: should contain HTML-like content
            try:
                text = file_data[:1024].decode('utf-8', errors='ignore').lower()
            except Exception:
                text = ''
            if not any(marker in text for marker in ['<html', '<!doctype', '<head', '<body', '<div']):
                raise ValueError(
                    "File with .html extension does not appear to contain valid HTML content."
                )
            return 'text/html'
        elif ext == '.json':
            # Basic check: should start with { or [ after whitespace
            try:
                text = file_data[:256].decode('utf-8', errors='ignore').strip()
            except Exception:
                text = ''
            if not text or text[0] not in ('{', '['):
                raise ValueError(
                    "File with .json extension does not appear to contain valid JSON content."
                )
            return 'application/json'

        # Should not reach here since we only call for web_content extensions
        return mimetypes.guess_type(f"file{ext}")[0] or 'application/octet-stream'

    def _validate_svg_content(self, file_data: bytes) -> str:
        """Validate SVG file content by checking for XML/SVG markers.

        SVG files are text-based XML and don't have binary magic bytes.
        Validates by checking the content starts with expected SVG/XML markers.

        Args:
            file_data: Raw file bytes.

        Returns:
            'image/svg+xml' on success.

        Raises:
            ValueError: If content doesn't appear to be valid SVG.
        """
        try:
            text = file_data[:1024].decode('utf-8', errors='ignore').strip().lower()
        except Exception:
            text = ''

        if not any(marker in text for marker in ['<svg', '<?xml']):
            raise ValueError(
                "File with .svg extension does not appear to contain valid SVG content."
            )
        return 'image/svg+xml'

    # === Raw S3 operations (stubs) ===

    def _upload_raw(self, bucket: str, key: str, file_data: bytes, content_type: str) -> bool:
        """Raw S3 put_object. Only called from store_and_register.

        Args:
            bucket: S3 bucket name.
            key: Full S3 key path.
            file_data: Raw file bytes to upload.
            content_type: MIME type for the object.

        Returns:
            True if upload succeeded, False otherwise.
        """
        try:
            s3_client = boto3.client('s3')
            s3_client.put_object(
                Bucket=bucket,
                Key=key,
                Body=file_data,
                ContentType=content_type,
            )
            return True
        except ClientError as e:
            logger.error(
                "S3 upload failed: bucket=%s, key=%s, error=%s",
                bucket, key, str(e)
            )
            return False
        except Exception as e:
            logger.error(
                "Unexpected error during S3 upload: bucket=%s, key=%s, error=%s",
                bucket, key, str(e)
            )
            return False

    def _delete_raw(self, bucket: str, key: str) -> bool:
        """Raw S3 delete_object. Only called from delete_asset/force_delete.

        Args:
            bucket: S3 bucket name.
            key: Full S3 key path of the object to delete.

        Returns:
            True if deletion succeeded, False otherwise.
        """
        try:
            s3_client = boto3.client('s3')
            s3_client.delete_object(Bucket=bucket, Key=key)
            return True
        except ClientError as e:
            logger.error(
                "S3 delete failed: bucket=%s, key=%s, error=%s",
                bucket, key, str(e)
            )
            return False
        except Exception as e:
            logger.error(
                "Unexpected error during S3 delete: bucket=%s, key=%s, error=%s",
                bucket, key, str(e)
            )
            return False

    def _get_retention_days(self, tenant: str, category: str, media_type: str) -> int:
        """Resolve retention days for a given category and media type.

        Resolution order (Req 5, AC 8):
        1. Asset-level retention_days override (handled at caller level)
        2. Tenant-level parameter (via ParameterService scope chain)
        3. System default (via CODE_DEFAULTS)

        For landing-pages category, the key depends on media_type:
        - image/video → 'landing_pages_media_days'
        - other (web_content, document) → 'landing_pages_days'

        Args:
            tenant: Tenant identifier (administration).
            category: Asset category (invoices, branding, templates, landing-pages).
            media_type: Asset media type (image, video, document, web_content).

        Returns:
            Integer number of retention days.
        """
        key = self._retention_param_key(category, media_type)
        value = self.ps.get_param('asset_retention', key, tenant=tenant)
        if value is not None:
            return int(value)
        # Shouldn't happen if CODE_DEFAULTS is populated, but defensive fallback
        return 30

    @staticmethod
    def _retention_param_key(category: str, media_type: str) -> str:
        """Map category + media_type to the asset_retention parameter key.

        Args:
            category: Asset category.
            media_type: Asset media type.

        Returns:
            The parameter key string for use with namespace 'asset_retention'.
        """
        if category == 'landing-pages':
            if media_type in ('image', 'video'):
                return 'landing_pages_media_days'
            return 'landing_pages_days'

        # Normalize category for param key lookup (e.g., 'landing-pages' → 'landing_pages')
        key_prefix = category.replace('-', '_')
        return f"{key_prefix}_days"

    def _get_presigned_url(self, asset: dict, ttl: int = 3600) -> str:
        """Return cached presigned URL or generate new one.

        Caches presigned URLs in memory with a safety margin of 10 minutes
        before expiry. For 60-minute URLs (ttl=3600), this means the cache
        effectively has a ~50-minute TTL.

        AC 7: Cache presigned URLs in memory with TTL of 50 minutes.

        Args:
            asset: Dict with 'id', 'bucket', and 's3_key' keys.
            ttl: URL validity in seconds (default 3600 = 60 minutes).

        Returns:
            Presigned URL string for the S3 object.
        """
        asset_id = asset['id']
        now = datetime.now(timezone.utc)

        # Check cache (50-min effective TTL for 60-min URLs)
        if asset_id in self._presigned_cache:
            url, expires_at = self._presigned_cache[asset_id]
            if now < expires_at - timedelta(minutes=10):
                return url

        # Generate new presigned URL
        s3_client = boto3.client('s3')
        url = s3_client.generate_presigned_url(
            'get_object',
            Params={'Bucket': asset['bucket'], 'Key': asset['s3_key']},
            ExpiresIn=ttl
        )

        self._presigned_cache[asset_id] = (url, now + timedelta(seconds=ttl))
        return url

    def _check_duplicate(self, tenant: str, current_asset_id: str, content_hash: str) -> Optional[dict]:
        """Check if another asset in the same tenant has the same content_hash.

        This is a non-blocking check — duplicates are reported but do not
        prevent the upload.

        Args:
            tenant: Tenant identifier (administration).
            current_asset_id: The just-created asset's ID (to exclude from search).
            content_hash: SHA-256 hex digest to search for.

        Returns:
            Dict with 'asset_id' and 'original_filename' of the duplicate,
            or None if no duplicate found.
        """
        try:
            query = """
                SELECT id, original_filename
                FROM s3_assets
                WHERE administration = %s
                  AND content_hash = %s
                  AND id != %s
                ORDER BY created_at ASC
                LIMIT 1
            """
            results = self.db.execute_query(query, (tenant, content_hash, current_asset_id))
            if results:
                return {
                    'asset_id': results[0]['id'],
                    'original_filename': results[0]['original_filename'],
                }
        except Exception as e:
            # Duplicate detection is non-blocking — log and continue
            logger.warning(
                "Duplicate check failed for asset %s: %s",
                current_asset_id, str(e)
            )
        return None
