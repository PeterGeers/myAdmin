"""Reconciliation operations for MediaAssetService."""

import os
from datetime import datetime, timezone

from botocore.exceptions import ClientError

from db_exceptions import DatabaseError
from services.media_asset.base import ENTITY_TYPE_REGISTRY, _mas_boto3, _maslog


class ReconcileMixin:
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
            "success": True,
            "tenant": tenant,
            "phase1": self._reconcile_s3_scan(tenant),
            "phase2": self._reconcile_references(tenant),
            "phase3": self.transition_eligible(tenant),
        }

        # Build reconciliation report (Req 6 AC 4)
        result["summary"] = self._build_reconciliation_report(
            tenant, result["phase1"], result["phase2"], result["phase3"]
        )

        # Store in memory cache for UI retrieval
        self._last_reconciliation[tenant] = result["summary"]

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
            "type": "progress",
            "phase": "scanning_s3",
            "message": "Scanning S3 buckets...",
        }

        phase1 = self._reconcile_s3_scan(tenant)

        # Phase 2: checking_registry
        yield {
            "type": "progress",
            "phase": "checking_registry",
            "message": "Comparing with registry...",
            "total_s3": phase1.get("total_s3", 0),
            "total_registry": phase1.get("total_registry", 0),
            "unregistered": len(phase1.get("unregistered", [])),
            "missing": len(phase1.get("missing", [])),
        }

        phase2 = self._reconcile_references(tenant)

        # Phase 3: verifying_references
        yield {
            "type": "progress",
            "phase": "verifying_references",
            "message": "Verifying entity references...",
            "stale_found": phase2.get("stale_removed", 0),
            "newly_orphaned": phase2.get("newly_orphaned", 0),
        }

        phase3 = self.transition_eligible(tenant)

        # Phase 4: transitioning
        yield {
            "type": "progress",
            "phase": "transitioning",
            "message": "Transitioning eligible assets...",
            "transitioned": phase3.get("transitioned", 0),
        }

        # Build final report and cache it
        summary = self._build_reconciliation_report(tenant, phase1, phase2, phase3)
        self._last_reconciliation[tenant] = summary

        # Phase 5: complete
        yield {
            "type": "complete",
            "phase": "complete",
            "summary": summary,
        }

    def _build_reconciliation_report(
        self, tenant: str, phase1: dict, phase2: dict, phase3: dict
    ) -> dict:
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
        total_assets = phase1.get("total_registry", 0)
        missing_count = len(phase1.get("missing", []))
        unregistered_count = len(phase1.get("unregistered", []))
        stale_count = phase2.get("stale_removed", 0)
        newly_eligible_count = phase3.get("transitioned", 0)
        consistent = total_assets - missing_count

        return {
            "administration": tenant,
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "total_assets": total_assets,
            "consistent": consistent,
            "unregistered": unregistered_count,
            "missing": missing_count,
            "stale_references": stale_count,
            "newly_eligible": newly_eligible_count,
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
        shared_bucket = os.environ.get("S3_SHARED_BUCKET")
        if shared_bucket:
            shared_keys = self._list_s3_objects(shared_bucket, f"{tenant}/")
            for key in shared_keys:
                s3_objects[key] = shared_bucket

        # Public-pages bucket: category landing-pages
        pages_bucket = os.environ.get("LANDING_PAGES_BUCKET")
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
        registered_keys = {row["s3_key"] for row in registry_rows}

        # Step 3: Compare
        s3_key_set = set(s3_objects.keys())

        # Unregistered: in S3 but NOT in registry
        unregistered = [
            {"s3_key": key, "bucket": s3_objects[key]}
            for key in sorted(s3_key_set - registered_keys)
        ]

        # Missing: in registry but NOT in S3
        missing = [
            {"s3_key": row["s3_key"], "bucket": row["bucket"]}
            for row in registry_rows
            if row["s3_key"] not in s3_key_set
        ]

        return {
            "unregistered": unregistered,
            "missing": missing,
            "total_s3": len(s3_key_set),
            "total_registry": len(registered_keys),
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
        # Track tables that don't exist so we skip them after first failure
        missing_tables = set()

        for ref in references:
            entity_type = ref["entity_type"]
            entity_id = ref["entity_id"]

            registry_entry = ENTITY_TYPE_REGISTRY.get(entity_type)

            # Unknown entity_type — skip with warning
            if entity_type not in ENTITY_TYPE_REGISTRY:
                skipped_types.add(entity_type)
                _maslog().warning(
                    "Unknown entity_type '%s' in s3_asset_references (ref id=%s), skipping",
                    entity_type,
                    ref["id"],
                )
                continue

            # Ephemeral type (None) — skip, no existence check
            if registry_entry is None:
                skipped_types.add(entity_type)
                continue

            # Run the existence check query
            _table, _id_col, existence_query = registry_entry

            # DynamoDB-backed entity — use dedicated service
            if _table == "dynamodb":
                if entity_type == "landing_page":
                    if not hasattr(self, "_landing_page_service"):
                        from services.landing_page_service import LandingPageService

                        try:
                            self._landing_page_service = LandingPageService()
                        except Exception as e:
                            _maslog().warning(
                                "Cannot initialize LandingPageService: %s, skipping landing_page checks",
                                e,
                            )
                            skipped_types.add(entity_type)
                            continue
                    # entity_id is the slug for landing pages
                    draft = self._landing_page_service.get_draft(entity_id)
                    if not draft:
                        stale_ref_ids.append(ref["id"])
                        stale_asset_ids.add(ref["asset_id"])
                else:
                    skipped_types.add(entity_type)
                continue

            # Skip if table was already found to be missing
            if _table in missing_tables:
                skipped_types.add(entity_type)
                continue

            try:
                result = self.db.execute_query(
                    existence_query, (entity_id, tenant), fetch=True
                )
            except DatabaseError as e:
                # Table doesn't exist (error 1146) — skip this entity_type entirely
                if "1146" in str(e) or "doesn't exist" in str(e):
                    _maslog().warning(
                        "Table '%s' does not exist, skipping entity_type '%s'",
                        _table,
                        entity_type,
                    )
                    missing_tables.add(_table)
                    skipped_types.add(entity_type)
                    continue
                raise

            if not result:
                # Entity doesn't exist → stale reference
                stale_ref_ids.append(ref["id"])
                stale_asset_ids.add(ref["asset_id"])

        # Step 3: DELETE stale references
        stale_removed = 0
        if stale_ref_ids:
            with self.db.transaction() as (cursor, _):
                # Delete stale refs in batches
                placeholders = ", ".join(["%s"] * len(stale_ref_ids))
                cursor.execute(
                    f"DELETE FROM s3_asset_references WHERE id IN ({placeholders})",
                    tuple(stale_ref_ids),
                )
                stale_removed = cursor.rowcount

        # Step 4: For affected assets, check if refs dropped to zero → mark ORPHAN
        newly_orphaned = 0
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

        if stale_asset_ids:
            with self.db.transaction() as (cursor, _):
                for asset_id in stale_asset_ids:
                    cursor.execute(
                        "SELECT COUNT(*) AS cnt FROM s3_asset_references "
                        "WHERE asset_id = %s AND administration = %s",
                        (asset_id, tenant),
                    )
                    count_row = cursor.fetchone()
                    ref_count = (
                        count_row["cnt"]
                        if isinstance(count_row, dict)
                        else count_row[0]
                    )

                    if ref_count == 0:
                        cursor.execute(
                            """
                            UPDATE s3_assets
                            SET status = 'ORPHAN', orphaned_at = %s, updated_at = %s
                            WHERE id = %s AND administration = %s
                              AND status = 'ACTIVE'
                            """,
                            (now, now, asset_id, tenant),
                        )
                        if cursor.rowcount > 0:
                            newly_orphaned += 1

        return {
            "stale_removed": stale_removed,
            "newly_orphaned": newly_orphaned,
            "skipped_types": sorted(skipped_types),
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
                    keys.append(key)
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

        return keys
