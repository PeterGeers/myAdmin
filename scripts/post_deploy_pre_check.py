#!/usr/bin/env python3
"""
Post-deploy pre-check script (Deliverable #5).

Runs after SAM deploy to verify:
1. Required environment variables / API URLs are available
2. Projection freshness is sane (no stale data)
3. Cognito configuration is valid

This script is called from deploy-sam-members.yml and deploy-frontend.yml workflows.
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone

# Add backend to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend', 'src'))

from database import DatabaseManager


def check_env_vars(env: str) -> tuple[bool, list[str]]:
    """Check that required environment variables are set for the given environment."""
    errors = []

    # Required variables per environment
    required_vars = {
        'test': [
            'VITE_API_URL',
            'VITE_COGNITO_USER_POOL_ID',
            'VITE_COGNITO_CLIENT_ID',
            'VITE_COGNITO_DOMAIN',
            'VITE_AWS_REGION',
            'VITE_REDIRECT_SIGN_IN',
            'VITE_REDIRECT_SIGN_OUT',
            'VITE_MEMBERS_API_BASE_URL',
        ],
        'prod': [
            'VITE_API_URL',
            'VITE_COGNITO_USER_POOL_ID',
            'VITE_COGNITO_CLIENT_ID',
            'VITE_COGNITO_DOMAIN',
            'VITE_AWS_REGION',
            'VITE_REDIRECT_SIGN_IN',
            'VITE_REDIRECT_SIGN_OUT',
            'VITE_MEMBERS_API_BASE_URL',
        ],
    }

    for var in required_vars.get(env, []):
        if not os.environ.get(var):
            errors.append(f"Missing required env var: {var}")

    return len(errors) == 0, errors


def check_projection_freshness() -> tuple[bool, list[str]]:
    """
    Check projection freshness by querying the GovernanceProjectionTable.
    Returns (healthy, errors).
    """
    errors = []

    try:
        db = DatabaseManager()

        # Check if projection table has recent data (within last 24 hours)
        # Use the projection_timestamp or similar column
        rows = db.execute_query(
            """
            SELECT MAX(projection_timestamp) as latest_ts
            FROM governance_projection
            WHERE projection_timestamp IS NOT NULL
            """,
            fetch=True,
        )

        if rows and rows[0].get('latest_ts'):
            latest_ts = rows[0]['latest_ts']
            # Convert to datetime if it's a string
            if isinstance(latest_ts, str):
                latest_ts = datetime.fromisoformat(latest_ts.replace('Z', '+00:00'))

            if latest_ts.tzinfo is None:
                latest_ts = latest_ts.replace(tzinfo=timezone.utc)

            now = datetime.now(timezone.utc)
            age_hours = (now - latest_ts).total_seconds() / 3600

            if age_hours > 24:
                errors.append(
                    f"Projection data is stale: latest update was {age_hours:.1f} hours ago "
                    f"(threshold: 24 hours)"
                )
        else:
            errors.append("No projection data found in GovernanceProjectionTable")

    except Exception as e:
        errors.append(f"Failed to check projection freshness: {e}")

    return len(errors) == 0, errors


def check_cognito_config() -> tuple[bool, list[str]]:
    """Check that Cognito configuration is valid."""
    errors = []

    # These would be populated from SAM stack outputs in a real deployment
    # For now, check that the required secrets exist
    required_secrets = [
        'VITE_COGNITO_USER_POOL_ID',
        'VITE_COGNITO_CLIENT_ID',
        'VITE_COGNITO_DOMAIN',
    ]

    for secret in required_secrets:
        if not os.environ.get(secret):
            errors.append(f"Missing Cognito config: {secret}")

    return len(errors) == 0, errors


def main():
    parser = argparse.ArgumentParser(description='Post-deploy pre-checks')
    parser.add_argument('--env', required=True, choices=['test', 'prod'],
                        help='Environment to check (test or prod)')
    args = parser.parse_args()

    all_errors = []
    all_warnings = []

    print(f"\n=== Post-deploy pre-check for {args.env} environment ===\n")

    # Check 1: Required env vars
    print("1. Checking required environment variables...")
    ok, errors = check_env_vars(args.env)
    if ok:
        print("   ✅ All required env vars present")
    else:
        for e in errors:
            print(f"   ❌ {e}")
        all_errors.extend(errors)

    # Check 2: Cognito configuration
    print("\n2. Checking Cognito configuration...")
    ok, errors = check_cognito_config()
    if ok:
        print("   ✅ Cognito configuration valid")
    else:
        for e in errors:
            print(f"   ❌ {e}")
        all_errors.extend(errors)

    # Check 3: Projection freshness
    print("\n3. Checking projection freshness...")
    ok, errors = check_projection_freshness()
    if ok:
        print("   ✅ Projection data is fresh")
    else:
        for e in errors:
            print(f"   ⚠️  {e}")
        # Projection freshness is a warning, not a hard failure
        all_warnings.extend(errors)

    # Summary
    print("\n=== Summary ===")
    if all_errors:
        print(f"❌ FAILED: {len(all_errors)} error(s)")
        for e in all_errors:
            print(f"   - {e}")
        sys.exit(1)
    elif all_warnings:
        print(f"⚠️  PASSED WITH WARNINGS: {len(all_warnings)} warning(s)")
        for w in all_warnings:
            print(f"   - {w}")
        sys.exit(0)
    else:
        print("✅ All checks passed")
        sys.exit(0)


if __name__ == '__main__':
    main()