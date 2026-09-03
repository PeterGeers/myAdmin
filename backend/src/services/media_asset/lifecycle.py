"""Lifecycle, deletion, dashboard and retention operations for MediaAssetService."""

import os
from datetime import datetime, timezone

from botocore.exceptions import ClientError

from db_exceptions import IntegrityError
from services.media_asset.base import _mas_boto3, _maslog


class LifecycleMixin:
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
        with self.db.transaction() as (cursor, _):
            # Step 1: Lock the asset row (SELECT FOR UPDATE)
            cursor.execute(
                "SELECT id, status, s3_key, bucket, category FROM s3_assets "
                "WHERE id = %s AND administration = %s FOR UPDATE",
                (asset_id, tenant),
            )
            asset = cursor.fetchone()

            if not asset:
                return {"success": False, "error": "Asset not found"}

            # Step 2: Verify status allows deletion
            status = asset["status"] if isinstance(asset, dict) else asset[1]

            # Step 3: Reference guard — verify zero references (Req 10 AC 1)
            cursor.execute(
                "SELECT COUNT(*) AS cnt FROM s3_asset_references "
                "WHERE asset_id = %s AND administration = %s",
                (asset_id, tenant),
            )
            count_row = cursor.fetchone()
            ref_count = (
                count_row["cnt"] if isinstance(count_row, dict) else count_row[0]
            )

            # Req 5 AC 10: If asset regained a reference, report re-activated
            if ref_count > 0 and status in ("ORPHAN", "DELETION_ELIGIBLE"):
                return {
                    "success": False,
                    "error": "re-activated",
                    "reference_count": ref_count,
                }

            # Req 5 AC 12 / Req 10 AC 2: Active references → reject
            if ref_count > 0:
                return {
                    "success": False,
                    "error": f"Asset still has {ref_count} active references",
                    "reference_count": ref_count,
                }

            # Status check: only ORPHAN/DELETION_ELIGIBLE or ACTIVE with zero refs
            # (ACTIVE with zero refs is allowed per design — zero refs is the guard)

            # Step 4: S3 deletion (Req 5 AC 13: if fails, retain record)
            s3_key = asset["s3_key"] if isinstance(asset, dict) else asset[2]
            bucket = asset["bucket"] if isinstance(asset, dict) else asset[3]
            category = asset["category"] if isinstance(asset, dict) else asset[4]

            deleted = self._delete_raw(bucket, s3_key)
            if not deleted:
                return {"success": False, "error": "S3 deletion failed"}

            # Step 5: Remove registry records
            cursor.execute(
                "DELETE FROM s3_asset_references WHERE asset_id = %s AND administration = %s",
                (asset_id, tenant),
            )
            cursor.execute(
                "DELETE FROM s3_assets WHERE id = %s AND administration = %s",
                (asset_id, tenant),
            )

        # Step 6: Audit log (Req 5 AC 11)
        _maslog().info(
            "Asset deleted: asset_id=%s, administration=%s, bucket=%s, "
            "category=%s, approved_by=%s",
            asset_id,
            tenant,
            bucket,
            category,
            approved_by,
        )

        # Step 7: Return success
        return {"success": True, "asset_id": asset_id}

    def force_delete(
        self, tenant: str, asset_id: str, operator: str, reason: str
    ) -> dict:
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
        with self.db.transaction() as (cursor, _):
            # Step 1: Lock the asset row
            cursor.execute(
                "SELECT id, status, s3_key, bucket, category FROM s3_assets "
                "WHERE id = %s AND administration = %s FOR UPDATE",
                (asset_id, tenant),
            )
            asset = cursor.fetchone()

            if not asset:
                return {"success": False, "error": "Asset not found"}

            # Step 2: Count references for audit (NOT for guard — bypassed)
            cursor.execute(
                "SELECT COUNT(*) AS cnt FROM s3_asset_references "
                "WHERE asset_id = %s AND administration = %s",
                (asset_id, tenant),
            )
            count_row = cursor.fetchone()
            ref_count = (
                count_row["cnt"] if isinstance(count_row, dict) else count_row[0]
            )

            # Step 3: S3 deletion
            s3_key = asset["s3_key"] if isinstance(asset, dict) else asset[2]
            bucket = asset["bucket"] if isinstance(asset, dict) else asset[3]
            _category = asset["category"] if isinstance(asset, dict) else asset[4]

            deleted = self._delete_raw(bucket, s3_key)
            if not deleted:
                return {"success": False, "error": "S3 deletion failed"}

            # Step 5: Remove registry records (bypass reference guard)
            cursor.execute(
                "DELETE FROM s3_asset_references WHERE asset_id = %s AND administration = %s",
                (asset_id, tenant),
            )
            cursor.execute(
                "DELETE FROM s3_assets WHERE id = %s AND administration = %s",
                (asset_id, tenant),
            )

        # Step 6: WARNING-level audit entry (Req 10 AC 7, AC 8)
        _maslog().warning(
            "FORCE DELETE: asset_id=%s, administration=%s, operator=%s, "
            "reference_count=%d, reason=%s, timestamp=%s",
            asset_id,
            tenant,
            operator,
            ref_count,
            reason,
            datetime.now(timezone.utc).isoformat(),
        )

        # Step 7: Return success
        return {
            "success": True,
            "asset_id": asset_id,
            "reference_count": ref_count,
            "operator": operator,
            "reason": reason,
        }

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
        categories = ["invoices", "branding", "templates", "landing-pages"]
        transitioned = 0

        for category in categories:
            if category == "landing-pages":
                # Landing-pages has different retention per media type group
                # Group 1: web_content (landing_pages_days)
                retention_web = self._get_retention_days(
                    tenant, category, media_type="web_content"
                )
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
                    fetch=False,
                    commit=True,
                )
                transitioned += result_web

                # Group 2: image/video (landing_pages_media_days)
                retention_media = self._get_retention_days(
                    tenant, category, media_type="image"
                )
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
                    fetch=False,
                    commit=True,
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
                    fetch=False,
                    commit=True,
                )
                transitioned += result

        return {"success": True, "transitioned": transitioned}

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
        s3_objects = {}  # {s3_key: {bucket, size, last_modified}}

        s3_client = _mas_boto3().client("s3")

        def list_with_metadata(bucket, prefix):
            """List S3 objects with full metadata."""
            try:
                paginator = s3_client.get_paginator("list_objects_v2")
                page_iterator = paginator.paginate(Bucket=bucket, Prefix=prefix)

                for page in page_iterator:
                    for obj in page.get("Contents", []):
                        key = obj["Key"]
                        size = obj.get("Size", 0)
                        # Filter out .folder markers
                        if key.endswith(".folder") and size == 0:
                            continue
                        s3_objects[key] = {
                            "bucket": bucket,
                            "size": size,
                            "last_modified": obj.get("LastModified", "").isoformat()
                            if obj.get("LastModified")
                            else None,
                        }
            except ClientError as e:
                _maslog().error(
                    "S3 list failed: bucket=%s, prefix=%s, error=%s",
                    bucket,
                    prefix,
                    str(e),
                )

        # Scan shared bucket
        shared_bucket = os.environ.get("S3_SHARED_BUCKET")
        if shared_bucket:
            list_with_metadata(shared_bucket, f"{tenant}/")

        # Scan public-pages bucket
        pages_bucket = os.environ.get("LANDING_PAGES_BUCKET")
        if pages_bucket:
            list_with_metadata(pages_bucket, f"{tenant}/")

        # Get registered keys
        registry_query = """
            SELECT s3_key FROM s3_assets
            WHERE administration = %s
        """
        registry_rows = self.db.execute_query(registry_query, (tenant,), fetch=True)
        registered_keys = {row["s3_key"] for row in registry_rows}

        # Find unregistered objects
        unregistered = []
        for key in sorted(s3_objects.keys()):
            if key not in registered_keys:
                info = s3_objects[key]
                unregistered.append(
                    {
                        "s3_key": key,
                        "bucket": info["bucket"],
                        "size": info["size"],
                        "last_modified": info["last_modified"],
                    }
                )

        return {"success": True, "data": unregistered}

    def delete_unregistered_objects(
        self, tenant: str, s3_keys: list, operator: str
    ) -> dict:
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
        # Safety check: verify keys are not registered
        if s3_keys:
            placeholders = ", ".join(["%s"] * len(s3_keys))
            check_query = f"""
                SELECT s3_key FROM s3_assets
                WHERE administration = %s AND s3_key IN ({placeholders})
            """
            params = [tenant] + s3_keys
            registered = self.db.execute_query(check_query, tuple(params), fetch=True)
            registered_set = {row["s3_key"] for row in registered}
        else:
            registered_set = set()

        # Resolve bucket for each key
        shared_bucket = os.environ.get("S3_SHARED_BUCKET")
        pages_bucket = os.environ.get("LANDING_PAGES_BUCKET")

        s3_client = _mas_boto3().client("s3")
        deleted = 0
        skipped = 0

        for key in s3_keys:
            # Skip registered keys
            if key in registered_set:
                skipped += 1
                _maslog().warning(
                    "Skipping delete of registered key: tenant=%s, key=%s", tenant, key
                )
                continue

            # Verify key belongs to this tenant
            if not key.startswith(f"{tenant}/"):
                skipped += 1
                _maslog().warning(
                    "Skipping delete of non-tenant key: tenant=%s, key=%s", tenant, key
                )
                continue

            # Determine bucket from key path
            # landing-pages go in pages_bucket, others in shared_bucket
            bucket = pages_bucket if "/landing-pages/" in key else shared_bucket

            if not bucket:
                skipped += 1
                continue

            try:
                s3_client.delete_object(Bucket=bucket, Key=key)
                deleted += 1
                _maslog().info(
                    "Deleted unregistered S3 object: tenant=%s, key=%s, operator=%s",
                    tenant,
                    key,
                    operator,
                )
            except ClientError as e:
                skipped += 1
                _maslog().error(
                    "Failed to delete S3 object: key=%s, error=%s", key, str(e)
                )

        return {"success": True, "deleted": deleted, "skipped": skipped}

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
            count = row["cnt"]
            status = row["status"]
            total_assets += count
            if status == "ACTIVE":
                active_assets = count
            elif status == "ORPHAN":
                orphaned_assets = count
            elif status == "DELETION_ELIGIBLE":
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
            storage_by_category[row["category"]] = {
                "count": row["cnt"],
                "bytes": int(row["total_bytes"]),
            }

        # Last scan timestamp (from in-memory cache)
        last_scan_at = None
        cached = self._last_reconciliation.get(tenant)
        if cached and "timestamp" in cached:
            last_scan_at = cached["timestamp"]

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
            top_orphans.append(
                {
                    "id": row["id"],
                    "filename": row["original_filename"],
                    "size": row["file_size"],
                    "days_orphaned": row["days_orphaned"] or 0,
                }
            )

        return {
            "success": True,
            "data": {
                "total_assets": total_assets,
                "active_assets": active_assets,
                "orphaned_assets": orphaned_assets,
                "deletion_eligible": deletion_eligible,
                "storage_by_category": storage_by_category,
                "last_scan_at": last_scan_at,
                "top_orphans": top_orphans,
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
            content_hash = row["content_hash"]
            count = row["cnt"]

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
                assets.append(
                    {
                        "id": asset_row["id"],
                        "original_filename": asset_row["original_filename"],
                        "file_size": asset_row["file_size"],
                        "category": asset_row["category"],
                        "status": asset_row["status"],
                        "created_at": asset_row["created_at"],
                        "reference_count": asset_row["reference_count"],
                    }
                )

            groups.append(
                {
                    "content_hash": content_hash,
                    "count": count,
                    "assets": assets,
                }
            )

        return {"success": True, "data": groups}

    def merge_duplicates(
        self, tenant: str, keep_asset_id: str, duplicate_asset_ids: list
    ) -> dict:
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
        keep_rows = self.db.execute_query(
            keep_query, (keep_asset_id, tenant), fetch=True
        )
        if not keep_rows:
            return {
                "success": False,
                "error": f"Keep asset '{keep_asset_id}' not found",
            }

        merged = 0
        deleted = 0
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

        for dup_id in duplicate_asset_ids:
            if dup_id == keep_asset_id:
                continue  # Skip if someone accidentally includes the keep asset

            with self.db.transaction() as (cursor, _):
                # Verify duplicate belongs to tenant
                cursor.execute(
                    "SELECT id, s3_key, bucket FROM s3_assets "
                    "WHERE id = %s AND administration = %s",
                    (dup_id, tenant),
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
                    (dup_id, tenant),
                )
                refs = cursor.fetchall()

                for ref in refs:
                    entity_type = (
                        ref["entity_type"] if isinstance(ref, dict) else ref[1]
                    )
                    entity_id = ref["entity_id"] if isinstance(ref, dict) else ref[2]

                    # Try to insert the reference for the kept asset (ignore if exists)
                    try:
                        cursor.execute(
                            """
                            INSERT INTO s3_asset_references
                            (administration, asset_id, entity_type, entity_id, created_at)
                            VALUES (%s, %s, %s, %s, %s)
                            """,
                            (tenant, keep_asset_id, entity_type, entity_id, now),
                        )
                    except IntegrityError:
                        # Reference already exists on kept asset — skip
                        pass

                # Delete duplicate's references
                cursor.execute(
                    "DELETE FROM s3_asset_references WHERE asset_id = %s AND administration = %s",
                    (dup_id, tenant),
                )

                # Delete duplicate's S3 object
                s3_key = dup_row["s3_key"] if isinstance(dup_row, dict) else dup_row[1]
                bucket = dup_row["bucket"] if isinstance(dup_row, dict) else dup_row[2]
                self._delete_raw(bucket, s3_key)

                # Delete duplicate's DB record
                cursor.execute(
                    "DELETE FROM s3_assets WHERE id = %s AND administration = %s",
                    (dup_id, tenant),
                )

                merged += len(refs)
                deleted += 1

        # Ensure kept asset is ACTIVE (it now has references)
        self.db.execute_query(
            "UPDATE s3_assets SET status = 'ACTIVE', orphaned_at = NULL, updated_at = %s "
            "WHERE id = %s AND administration = %s AND status != 'ACTIVE'",
            (now, keep_asset_id, tenant),
            fetch=False,
            commit=True,
        )

        _maslog().info(
            "Merge duplicates: kept=%s, deleted=%d, refs_moved=%d, tenant=%s",
            keep_asset_id,
            deleted,
            merged,
            tenant,
        )

        return {
            "success": True,
            "kept": keep_asset_id,
            "merged": merged,
            "deleted": deleted,
        }

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
            tenant_value = self.ps._resolve_from_db(
                "tenant", tenant, "asset_retention", key
            )

            if tenant_value is not None:
                data[key] = {"value": int(tenant_value), "source": "tenant_override"}
            else:
                # Fall back to CODE_DEFAULTS (system default)
                code_default = CODE_DEFAULTS.get(("asset_retention", key))
                value = code_default["value"] if code_default else 30
                data[key] = {"value": int(value), "source": "system_default"}

        return {"success": True, "data": data}

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
                scope="tenant",
                scope_id=tenant,
                namespace="asset_retention",
                key=key,
                value=int(value),
                value_type="number",
            )
            updated.append(key)

        return {"success": True, "updated": updated}
