#!/usr/bin/env python3
"""
Post-Migration Reconciliation Script

Verifies data consistency between S3, the Asset Registry, and application data
after the media asset migration. Runs reconciliation per tenant and produces
a discrepancy report if any issues are found.

Usage:
    python backend/scripts/post_migration_reconciliation.py [--tenant TENANT] [--verbose]

Options:
    --tenant TENANT   Run reconciliation for a specific tenant only
    --verbose         Show detailed output for each tenant

Exit codes:
    0   All tenants pass — zero discrepancies
    1   Discrepancies found — see report output
"""

import sys
import os
import argparse
import json
from datetime import datetime, timezone

# Add parent directory to path to import src modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.database import DatabaseManager
from src.services.media_asset_service import MediaAssetService
from src.services.parameter_service import ParameterService


class PostMigrationReconciliation:
    """Run reconciliation checks per tenant and produce discrepancy reports."""

    def __init__(self, tenant_filter: str = None, verbose: bool = False):
        self.tenant_filter = tenant_filter
        self.verbose = verbose
        self.db = DatabaseManager()
        self.ps = ParameterService(self.db)
        self.asset_svc = MediaAssetService(self.db, self.ps)
        self.results = []

    def get_tenants(self) -> list:
        """Get list of tenants to reconcile.

        If --tenant was specified, returns just that tenant.
        Otherwise queries distinct administrations from s3_assets.

        Returns:
            List of tenant identifiers.
        """
        if self.tenant_filter:
            return [self.tenant_filter]

        rows = self.db.execute_query(
            "SELECT DISTINCT administration FROM s3_assets "
            "WHERE administration IS NOT NULL ORDER BY administration",
            fetch=True,
        )
        return [row['administration'] for row in rows] if rows else []

    def run_tenant_reconciliation(self, tenant: str) -> dict:
        """Run reconciliation for a single tenant.

        Calls MediaAssetService.run_reconciliation(tenant) and evaluates
        the result against the expected zero-discrepancy baseline.

        Args:
            tenant: Tenant identifier (administration).

        Returns:
            Dict with tenant, passed (bool), and details of any discrepancies.
        """
        if self.verbose:
            print(f"  Scanning tenant: {tenant}...")

        try:
            result = self.asset_svc.run_reconciliation(tenant)
        except Exception as e:
            return {
                'tenant': tenant,
                'passed': False,
                'error': str(e),
                'discrepancies': [],
            }

        summary = result.get('summary', {})
        phase1 = result.get('phase1', {})
        phase2 = result.get('phase2', {})

        unregistered_count = summary.get('unregistered', 0)
        missing_count = summary.get('missing', 0)
        stale_count = summary.get('stale_references', 0)

        discrepancies = []

        if unregistered_count > 0:
            examples = phase1.get('unregistered', [])[:10]
            discrepancies.append({
                'category': 'unregistered',
                'description': 'S3 objects not in registry',
                'count': unregistered_count,
                'examples': [item.get('s3_key', str(item)) for item in examples],
            })

        if missing_count > 0:
            examples = phase1.get('missing', [])[:10]
            discrepancies.append({
                'category': 'missing',
                'description': 'Registry records with no S3 object',
                'count': missing_count,
                'examples': [item.get('s3_key', str(item)) for item in examples],
            })

        if stale_count > 0:
            discrepancies.append({
                'category': 'stale',
                'description': 'Stale references to non-existent entities',
                'count': stale_count,
                'examples': [],  # Stale refs are already cleaned by reconciliation
            })

        passed = len(discrepancies) == 0

        return {
            'tenant': tenant,
            'passed': passed,
            'summary': summary,
            'discrepancies': discrepancies,
        }

    def run(self) -> bool:
        """Run reconciliation for all tenants.

        Returns:
            True if all tenants pass, False if any discrepancies found.
        """
        print("=" * 60)
        print("Post-Migration Reconciliation")
        print("=" * 60)
        print()

        tenants = self.get_tenants()

        if not tenants:
            print("No tenants found in s3_assets. Nothing to reconcile.")
            return True

        print(f"Reconciling {len(tenants)} tenant(s)...")
        print()

        all_passed = True

        for tenant in tenants:
            result = self.run_tenant_reconciliation(tenant)
            self.results.append(result)

            if result['passed']:
                print(f"  ✅ {tenant}: OK")
            else:
                all_passed = False
                if 'error' in result:
                    print(f"  ❌ {tenant}: ERROR — {result['error']}")
                else:
                    issues = ', '.join(
                        f"{d['category']}={d['count']}"
                        for d in result['discrepancies']
                    )
                    print(f"  ❌ {tenant}: DISCREPANCIES — {issues}")

        print()

        if all_passed:
            print("=" * 60)
            print("✅ All tenants passed reconciliation. Zero discrepancies.")
            print("=" * 60)
        else:
            self._print_discrepancy_report()

        return all_passed

    def _print_discrepancy_report(self):
        """Print detailed discrepancy report for failed tenants."""
        print("=" * 60)
        print("❌ DISCREPANCY REPORT")
        print("=" * 60)
        print()
        print(f"Timestamp: {datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}")
        print()

        failed_results = [r for r in self.results if not r['passed']]

        for result in failed_results:
            tenant = result['tenant']
            print(f"--- Tenant: {tenant} ---")

            if 'error' in result:
                print(f"  Error: {result['error']}")
                print()
                continue

            for disc in result['discrepancies']:
                print(f"  Category: {disc['category']}")
                print(f"  Description: {disc['description']}")
                print(f"  Count: {disc['count']}")
                if disc['examples']:
                    print(f"  Examples (first {len(disc['examples'])}):")
                    for example in disc['examples']:
                        print(f"    - {example}")
                print()

        print("=" * 60)
        print(f"Total failed tenants: {len(failed_results)}/{len(self.results)}")
        print("=" * 60)

    def get_report_data(self) -> dict:
        """Return structured report data for programmatic consumption.

        Returns:
            Dict with timestamp, all_passed, tenant_count, and per-tenant results.
        """
        return {
            'timestamp': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
            'all_passed': all(r['passed'] for r in self.results),
            'tenant_count': len(self.results),
            'passed_count': sum(1 for r in self.results if r['passed']),
            'failed_count': sum(1 for r in self.results if not r['passed']),
            'tenants': self.results,
        }


def main():
    parser = argparse.ArgumentParser(
        description='Run post-migration reconciliation per tenant'
    )
    parser.add_argument(
        '--tenant',
        type=str,
        default=None,
        help='Run reconciliation for a specific tenant only',
    )
    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Show detailed output for each tenant',
    )
    parser.add_argument(
        '--json',
        action='store_true',
        dest='output_json',
        help='Output results as JSON',
    )

    args = parser.parse_args()

    reconciliation = PostMigrationReconciliation(
        tenant_filter=args.tenant,
        verbose=args.verbose,
    )

    all_passed = reconciliation.run()

    if args.output_json:
        print()
        print(json.dumps(reconciliation.get_report_data(), indent=2))

    sys.exit(0 if all_passed else 1)


if __name__ == '__main__':
    main()
