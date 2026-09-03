"""Legacy import and reference-discovery operations for MediaAssetService."""

import mimetypes
import os
from datetime import datetime, timezone

from botocore.exceptions import ClientError

from db_exceptions import IntegrityError
from services.media_asset.base import _mas_boto3, _maslog


class ImportMixin:
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
        existing_rows = self.db.execute_query(
            existing_query, (tenant, category), fetch=True
        )
        existing_keys = {row["s3_key"] for row in existing_rows}

        # Step 4: Process each unregistered object
        newly_registered = 0
        already_registered = 0
        unclassified = []
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

        for obj in s3_objects:
            s3_key = obj["key"]
            file_size = obj["size"]

            # AC 5: Skip objects already registered
            if s3_key in existing_keys:
                already_registered += 1
                continue

            # Extract original_filename from key (last segment after the last '/')
            original_filename = s3_key.rsplit("/", 1)[-1] if "/" in s3_key else s3_key

            # Detect media_type from extension
            ext = os.path.splitext(original_filename)[1].lower()
            detected_media_type = None
            for media_type, rules in self.MEDIA_TYPES.items():
                if ext in rules["extensions"]:
                    detected_media_type = media_type
                    break

            # AC 8: Unclassifiable objects (unknown extension) are skipped
            if detected_media_type is None:
                unclassified.append(
                    {
                        "s3_key": s3_key,
                        "filename": original_filename,
                        "reason": f"Unknown extension '{ext}'",
                    }
                )
                continue

            # Generate asset_id
            asset_id = self._generate_asset_id()

            # Detect mime_type from extension
            mime_type = (
                mimetypes.guess_type(original_filename)[0] or "application/octet-stream"
            )

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
                    asset_id,
                    tenant,
                    bucket,
                    s3_key,
                    mime_type,
                    file_size,
                    category,
                    detected_media_type,
                    original_filename,
                    "ACTIVE",
                    now,
                    now,
                ),
                fetch=False,
                commit=True,
            )
            newly_registered += 1

        # AC 6: Return summary report
        return {
            "success": True,
            "administration": tenant,
            "category": category,
            "total_scanned": total_scanned,
            "newly_registered": newly_registered,
            "already_registered": already_registered,
            "unclassified": unclassified,
        }

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
            return {"success": True, "references_created": 0, "already_linked": 0}

        # Step 2: Build a lookup: s3_key → asset_id
        key_to_asset = {row["s3_key"]: row["id"] for row in assets}

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
                mutatie_id = str(match["ID"])
                # INSERT reference (idempotent via unique constraint)
                try:
                    insert_query = """
                        INSERT INTO s3_asset_references
                        (administration, asset_id, entity_type, entity_id, created_at)
                        VALUES (%s, %s, %s, %s, NOW())
                    """
                    self.db.execute_query(
                        insert_query,
                        (tenant, asset_id, "invoice", mutatie_id),
                        fetch=False,
                        commit=True,
                    )
                    references_created += 1
                except IntegrityError:
                    # Already linked (unique constraint on asset_id, entity_type, entity_id)
                    already_linked += 1

        return {
            "success": True,
            "references_created": references_created,
            "already_linked": already_linked,
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
            return {"success": True, "references_created": 0, "already_linked": 0}

        # Step 2: Build a lookup: s3_key → asset_id
        key_to_asset = {row["s3_key"]: row["id"] for row in assets}

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
                param_key = match["key"]
                entity_id = f"{tenant}:{param_key}"
                try:
                    insert_query = """
                        INSERT INTO s3_asset_references
                        (administration, asset_id, entity_type, entity_id, created_at)
                        VALUES (%s, %s, %s, %s, NOW())
                    """
                    self.db.execute_query(
                        insert_query,
                        (tenant, asset_id, "branding", entity_id),
                        fetch=False,
                        commit=True,
                    )
                    references_created += 1
                except IntegrityError:
                    already_linked += 1

        return {
            "success": True,
            "references_created": references_created,
            "already_linked": already_linked,
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
            return {"success": True, "references_created": 0, "already_linked": 0}

        # Step 2: Get all landing pages for this tenant
        pages_query = """
            SELECT id, content FROM landing_pages
            WHERE administration = %s
        """
        pages = self.db.execute_query(pages_query, (tenant,), fetch=True)

        if not pages:
            return {"success": True, "references_created": 0, "already_linked": 0}

        # Step 3: For each page, check if content contains any registered s3_key
        references_created = 0
        already_linked = 0

        for page in pages:
            page_id = str(page["id"])
            content = page.get("content") or ""

            for asset in assets:
                s3_key = asset["s3_key"]
                asset_id = asset["id"]

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
                            (tenant, asset_id, "landing_page", page_id),
                            fetch=False,
                            commit=True,
                        )
                        references_created += 1
                    except IntegrityError:
                        already_linked += 1

        return {
            "success": True,
            "references_created": references_created,
            "already_linked": already_linked,
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
            return {"success": True, "references_created": 0, "already_linked": 0}

        # Step 2: Build a lookup: s3_key → asset_id
        key_to_asset = {row["s3_key"]: row["id"] for row in assets}

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
                template_key = match["key"]
                try:
                    insert_query = """
                        INSERT INTO s3_asset_references
                        (administration, asset_id, entity_type, entity_id, created_at)
                        VALUES (%s, %s, %s, %s, NOW())
                    """
                    self.db.execute_query(
                        insert_query,
                        (tenant, asset_id, "template", template_key),
                        fetch=False,
                        commit=True,
                    )
                    references_created += 1
                except IntegrityError:
                    already_linked += 1

        return {
            "success": True,
            "references_created": references_created,
            "already_linked": already_linked,
        }

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
        result = self.db.execute_query(
            query, (tenant, tenant), fetch=False, commit=True
        )
        return {"success": True, "orphaned": result}

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
            s3_client = _mas_boto3().client("s3")
            paginator = s3_client.get_paginator("list_objects_v2")
            page_iterator = paginator.paginate(Bucket=bucket, Prefix=prefix)

            for page in page_iterator:
                for obj in page.get("Contents", []):
                    key = obj["Key"]
                    size = obj.get("Size", 0)
                    # Filter out .folder markers (zero-byte directory placeholders)
                    if key.endswith(".folder") and size == 0:
                        continue
                    objects.append({"key": key, "size": size})
        except ClientError as e:
            _maslog().error(
                "S3 list failed: bucket=%s, prefix=%s, error=%s", bucket, prefix, str(e)
            )
        except Exception as e:
            _maslog().error(
                "Unexpected error listing S3 objects: bucket=%s, prefix=%s, error=%s",
                bucket,
                prefix,
                str(e),
            )

        return objects
