"""Store / register / reference operations for MediaAssetService."""

import hashlib
from datetime import datetime, timezone

from db_exceptions import IntegrityError
from services.media_asset.base import _maslog


class StoreRegisterMixin:
    def store_and_register(
        self,
        tenant: str,
        file_data: bytes,
        filename: str,
        category: str,
        entity_type: str | None = None,
        entity_id: str | None = None,
        metadata: dict | None = None,
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
        media_type = validation["media_type"]
        mime_type = validation["mime_type"]

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
            return {"success": False, "error": "S3 upload failed"}

        # Step 6: Insert DB records — commit only after S3 write succeeds (Req 9 AC 8)
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        file_size = len(file_data)

        try:
            with self.db.transaction() as (cursor, _):
                # INSERT s3_assets
                insert_asset_query = """
                    INSERT INTO s3_assets
                    (id, administration, bucket, s3_key, mime_type, file_size,
                     category, media_type, original_filename, content_hash,
                     status, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """
                cursor.execute(
                    insert_asset_query,
                    (
                        asset_id,
                        tenant,
                        bucket,
                        s3_key,
                        mime_type,
                        file_size,
                        category,
                        media_type,
                        filename,
                        content_hash,
                        "ACTIVE",
                        now,
                    ),
                )

                # Optionally INSERT s3_asset_references (Req 1 AC 8)
                reference_count = 0
                if entity_type and entity_id:
                    insert_ref_query = """
                        INSERT INTO s3_asset_references
                        (administration, asset_id, entity_type, entity_id, created_at)
                        VALUES (%s, %s, %s, %s, %s)
                    """
                    cursor.execute(
                        insert_ref_query,
                        (
                            tenant,
                            asset_id,
                            entity_type,
                            entity_id,
                            now,
                        ),
                    )
                    reference_count = 1

        except Exception as e:
            # DB commit failed after S3 write — log orphaned key (Req 9 AC 10)
            _maslog().error(
                "DB commit failed after S3 write — orphaned S3 key: "
                "bucket=%s, key=%s, timestamp=%s, error=%s",
                bucket,
                s3_key,
                now,
                str(e),
            )
            return {
                "success": False,
                "error": "Database registration failed after S3 upload",
                "orphaned_key": {"bucket": bucket, "key": s3_key},
            }

        # Step 7: Check for duplicate content_hash (non-blocking)
        duplicate_of = self._check_duplicate(tenant, asset_id, content_hash)

        # Step 8: Return result
        asset_record = {
            "id": asset_id,
            "s3_key": s3_key,
            "bucket": bucket,
            "mime_type": mime_type,
            "file_size": file_size,
            "category": category,
            "media_type": media_type,
            "original_filename": filename,
            "content_hash": content_hash,
            "status": "ACTIVE",
            "created_at": now,
            "reference_count": reference_count,
        }

        return {
            "success": True,
            "asset": asset_record,
            "duplicate_of": duplicate_of,
        }

    def attach(
        self, tenant: str, asset_id: str, entity_type: str, entity_id: str
    ) -> dict:
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
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

        with self.db.transaction() as (cursor, _):
            # Step 1: Verify asset exists and belongs to tenant
            cursor.execute(
                "SELECT id, status FROM s3_assets WHERE id = %s AND administration = %s",
                (asset_id, tenant),
            )
            asset_row = cursor.fetchone()

            if not asset_row:
                return {"success": False, "error": "Asset not found"}

            # Step 2: INSERT reference (idempotent via unique constraint)
            try:
                cursor.execute(
                    """
                    INSERT INTO s3_asset_references
                    (administration, asset_id, entity_type, entity_id, created_at)
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (tenant, asset_id, entity_type, entity_id, now),
                )
            except IntegrityError:
                # Unique constraint violation — already exists, treat as success
                pass

            # Step 3: If asset was ORPHAN or DELETION_ELIGIBLE, revert to ACTIVE
            current_status = (
                asset_row["status"] if isinstance(asset_row, dict) else asset_row[1]
            )
            if current_status in ("ORPHAN", "DELETION_ELIGIBLE"):
                cursor.execute(
                    """
                    UPDATE s3_assets
                    SET status = 'ACTIVE', orphaned_at = NULL, updated_at = %s
                    WHERE id = %s AND administration = %s
                    """,
                    (now, asset_id, tenant),
                )
            else:
                # Step 4: Update updated_at timestamp
                cursor.execute(
                    "UPDATE s3_assets SET updated_at = %s WHERE id = %s AND administration = %s",
                    (now, asset_id, tenant),
                )

        return {
            "success": True,
            "asset_id": asset_id,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "status": "ACTIVE"
            if current_status in ("ORPHAN", "DELETION_ELIGIBLE")
            else current_status,
            "updated_at": now,
        }

    def detach(
        self, tenant: str, asset_id: str, entity_type: str, entity_id: str
    ) -> dict:
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
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

        with self.db.transaction() as (cursor, _):
            # Step 1: Verify asset exists and belongs to tenant
            cursor.execute(
                "SELECT id, status FROM s3_assets WHERE id = %s AND administration = %s",
                (asset_id, tenant),
            )
            asset_row = cursor.fetchone()

            if not asset_row:
                return {"success": False, "error": "Asset not found"}

            # Step 2: DELETE the reference row
            cursor.execute(
                """
                DELETE FROM s3_asset_references
                WHERE asset_id = %s AND entity_type = %s AND entity_id = %s AND administration = %s
                """,
                (asset_id, entity_type, entity_id, tenant),
            )

            if cursor.rowcount == 0:
                return {"success": False, "error": "Reference not found"}

            # Step 3: Count remaining references for this asset
            cursor.execute(
                "SELECT COUNT(*) AS cnt FROM s3_asset_references WHERE asset_id = %s AND administration = %s",
                (asset_id, tenant),
            )
            count_row = cursor.fetchone()
            reference_count = (
                count_row["cnt"] if isinstance(count_row, dict) else count_row[0]
            )

            # Step 4: Update asset status based on remaining references
            if reference_count == 0:
                cursor.execute(
                    """
                    UPDATE s3_assets
                    SET status = 'ORPHAN', orphaned_at = %s, updated_at = %s
                    WHERE id = %s AND administration = %s
                    """,
                    (now, now, asset_id, tenant),
                )
                new_status = "ORPHAN"
            else:
                cursor.execute(
                    "UPDATE s3_assets SET updated_at = %s WHERE id = %s AND administration = %s",
                    (now, asset_id, tenant),
                )
                current_status = (
                    asset_row["status"] if isinstance(asset_row, dict) else asset_row[1]
                )
                new_status = current_status

        return {
            "success": True,
            "asset": {
                "id": asset_id,
                "status": new_status,
                "reference_count": reference_count,
                "updated_at": now,
            },
        }

    def replace(
        self,
        tenant: str,
        entity_type: str,
        entity_id: str,
        old_asset_id: str,
        new_asset_id: str,
    ) -> dict:
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
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

        # AC 9: When old_asset_id is null or empty, treat as simple attach
        if not old_asset_id:
            return self.attach(tenant, new_asset_id, entity_type, entity_id)

        # AC 7: Atomically detach old + attach new within one transaction
        with self.db.transaction() as (cursor, _):
            # Step 1: Verify old reference exists (AC 10)
            cursor.execute(
                """
                SELECT id FROM s3_asset_references
                WHERE asset_id = %s AND entity_type = %s AND entity_id = %s AND administration = %s
                """,
                (old_asset_id, entity_type, entity_id, tenant),
            )
            old_ref = cursor.fetchone()

            if not old_ref:
                return {
                    "success": False,
                    "error": (
                        f"No reference found for old_asset_id '{old_asset_id}' "
                        f"with entity_type '{entity_type}' and entity_id '{entity_id}'"
                    ),
                }

            # Step 2: Verify new asset exists and belongs to tenant
            cursor.execute(
                "SELECT id, status FROM s3_assets WHERE id = %s AND administration = %s",
                (new_asset_id, tenant),
            )
            new_asset_row = cursor.fetchone()

            if not new_asset_row:
                return {
                    "success": False,
                    "error": f"New asset '{new_asset_id}' not found",
                }

            # Step 3: DELETE old reference
            cursor.execute(
                """
                DELETE FROM s3_asset_references
                WHERE asset_id = %s AND entity_type = %s AND entity_id = %s AND administration = %s
                """,
                (old_asset_id, entity_type, entity_id, tenant),
            )

            # Step 4: INSERT new reference
            try:
                cursor.execute(
                    """
                    INSERT INTO s3_asset_references
                    (administration, asset_id, entity_type, entity_id, created_at)
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (tenant, new_asset_id, entity_type, entity_id, now),
                )
            except IntegrityError:
                # Reference already exists (idempotent) — not an error
                pass

            # Step 5: Check if old asset has zero remaining refs → mark ORPHAN
            cursor.execute(
                "SELECT COUNT(*) AS cnt FROM s3_asset_references WHERE asset_id = %s AND administration = %s",
                (old_asset_id, tenant),
            )
            old_ref_count_row = cursor.fetchone()
            old_ref_count = (
                old_ref_count_row["cnt"]
                if isinstance(old_ref_count_row, dict)
                else old_ref_count_row[0]
            )

            old_new_status = "ACTIVE"
            if old_ref_count == 0:
                cursor.execute(
                    """
                    UPDATE s3_assets
                    SET status = 'ORPHAN', orphaned_at = %s, updated_at = %s
                    WHERE id = %s AND administration = %s
                    """,
                    (now, now, old_asset_id, tenant),
                )
                old_new_status = "ORPHAN"

            # Step 6: If new asset was ORPHAN or DELETION_ELIGIBLE → revert to ACTIVE
            new_status = (
                new_asset_row["status"]
                if isinstance(new_asset_row, dict)
                else new_asset_row[1]
            )
            if new_status in ("ORPHAN", "DELETION_ELIGIBLE"):
                cursor.execute(
                    """
                    UPDATE s3_assets
                    SET status = 'ACTIVE', orphaned_at = NULL, updated_at = %s
                    WHERE id = %s AND administration = %s
                    """,
                    (now, new_asset_id, tenant),
                )
                new_status = "ACTIVE"
            else:
                cursor.execute(
                    "UPDATE s3_assets SET updated_at = %s WHERE id = %s AND administration = %s",
                    (now, new_asset_id, tenant),
                )

        return {
            "success": True,
            "old_asset": {
                "id": old_asset_id,
                "status": old_new_status,
                "reference_count": old_ref_count,
            },
            "new_asset": {
                "id": new_asset_id,
                "status": new_status,
                "entity_type": entity_type,
                "entity_id": entity_id,
            },
            "updated_at": now,
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
            return {"success": False, "error": "Asset not found"}

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
            "success": True,
            "asset": {
                "id": asset["id"],
                "s3_key": asset["s3_key"],
                "mime_type": asset["mime_type"],
                "file_size": asset["file_size"],
                "category": asset["category"],
                "media_type": asset["media_type"],
                "original_filename": asset["original_filename"],
                "status": asset["status"],
                "created_at": asset["created_at"],
                "presigned_url": presigned_url,
                "references": references,
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
        page = max(1, int(filters.get("page", 1)))
        page_size = min(100, max(1, int(filters.get("page_size", 20))))

        # Parse sort params (whitelist allowed columns)
        allowed_sort_columns = {
            "created_at",
            "original_filename",
            "file_size",
            "mime_type",
            "category",
        }
        sort = filters.get("sort", "created_at")
        if sort not in allowed_sort_columns:
            sort = "created_at"

        order = filters.get("order", "desc").upper()
        if order not in ("ASC", "DESC"):
            order = "DESC"

        # Build WHERE clauses
        where_clauses = ["a.administration = %s"]
        params = [tenant]

        if filters.get("q"):
            where_clauses.append("a.original_filename LIKE %s")
            params.append(f"%{filters['q']}%")

        if filters.get("category"):
            where_clauses.append("a.category = %s")
            params.append(filters["category"])

        if filters.get("media_type"):
            where_clauses.append("a.media_type = %s")
            params.append(filters["media_type"])

        if filters.get("status"):
            where_clauses.append("a.status = %s")
            params.append(filters["status"])

        where_sql = " AND ".join(where_clauses)

        # Count total results
        count_query = f"SELECT COUNT(*) AS total FROM s3_assets a WHERE {where_sql}"
        count_result = self.db.execute_query(count_query, tuple(params), fetch=True)
        total = count_result[0]["total"] if count_result else 0
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
            media_type = row["media_type"]
            presigned_url = None
            if media_type == "image":
                presigned_url = self._get_presigned_url(row)

            data.append(
                {
                    "id": row["id"],
                    "original_filename": row["original_filename"],
                    "mime_type": row["mime_type"],
                    "file_size": row["file_size"],
                    "category": row["category"],
                    "media_type": media_type,
                    "status": row["status"],
                    "created_at": row["created_at"],
                    "reference_count": row["reference_count"],
                    "presigned_url": presigned_url,
                }
            )

        return {
            "success": True,
            "data": data,
            "pagination": {
                "page": page,
                "page_size": page_size,
                "total": total,
                "total_pages": total_pages,
            },
        }
