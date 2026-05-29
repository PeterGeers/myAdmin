"""
One-time seed script: Populate email_verifications table from SES verified identities.

Queries AWS SES for all verified email identities, matches them to tenants
via the zzp_branding.contact_email parameter, and inserts 'verified' records
into the email_verifications table.

Usage:
    python backend/scripts/seed_email_verifications.py [--dry-run] [--env production|local]

Options:
    --dry-run       Show what would be inserted without actually writing to DB
    --env           Target environment: 'production' (Railway) or 'local' (Docker)
                    Default: local
"""

import os
import sys
import argparse
from datetime import datetime

# Add backend/src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import boto3


def get_ses_verified_emails(region: str = 'eu-west-1') -> list:
    """Query SES for all verified email identities."""
    ses = boto3.client('ses', region_name=region)

    # Get all email identities
    response = ses.list_identities(IdentityType='EmailAddress', MaxItems=1000)
    all_emails = response.get('Identities', [])

    if not all_emails:
        print("No email identities found in SES.")
        return []

    # Check verification status for all
    attrs_response = ses.get_identity_verification_attributes(Identities=all_emails)
    attributes = attrs_response.get('VerificationAttributes', {})

    verified = []
    for email, info in attributes.items():
        if info.get('VerificationStatus') == 'Success':
            verified.append(email)

    return verified


def get_tenant_email_mapping(db) -> dict:
    """Get mapping of contact_email → administration from parameters table.

    Returns: {email_address: administration_id}
    """
    rows = db.execute_query(
        """SELECT scope_id AS administration, value AS email
           FROM parameters
           WHERE namespace = 'zzp_branding'
           AND `key` = 'contact_email'
           AND scope = 'tenant'
           AND value IS NOT NULL
           AND value != ''"""
    )

    mapping = {}
    for row in rows:
        email = row['email']
        admin = row['administration']
        # Value might be JSON-quoted
        if isinstance(email, str):
            email = email.strip().strip('"')
        if email:
            mapping[email.lower()] = admin

    return mapping


def get_existing_verifications(db) -> set:
    """Get set of (administration, email) pairs already in email_verifications."""
    rows = db.execute_query(
        """SELECT administration, email FROM email_verifications
           WHERE status IN ('verified', 'pending')"""
    )
    return {(r['administration'], r['email']) for r in rows}


def seed_verifications(db, verified_emails: list, tenant_mapping: dict,
                       existing: set, dry_run: bool = False) -> int:
    """Insert verified records for matching tenant emails.

    Returns: number of records inserted
    """
    now = datetime.utcnow()
    inserted = 0

    for email in verified_emails:
        email_lower = email.lower()
        if email_lower not in tenant_mapping:
            print(f"  SKIP: {email} — no matching tenant")
            continue

        administration = tenant_mapping[email_lower]

        if (administration, email) in existing:
            print(f"  SKIP: {email} ({administration}) — already has record")
            continue

        if dry_run:
            print(f"  WOULD INSERT: {email} → {administration} (verified)")
        else:
            db.execute_query(
                """INSERT INTO email_verifications
                   (administration, email, status, initiated_at, verified_at)
                   VALUES (%s, %s, 'verified', %s, %s)""",
                (administration, email, now, now),
                fetch=False, commit=True
            )
            print(f"  INSERTED: {email} → {administration} (verified)")

        inserted += 1

    return inserted


def main():
    parser = argparse.ArgumentParser(description='Seed email_verifications from SES')
    parser.add_argument('--dry-run', action='store_true',
                        help='Show what would be inserted without writing')
    parser.add_argument('--env', choices=['local', 'production'], default='local',
                        help='Target environment (default: local)')
    args = parser.parse_args()

    # Set test_mode based on environment
    if args.env == 'local':
        os.environ.setdefault('DB_HOST', 'localhost')
        test_mode = False
    else:
        # Production uses Railway env vars (DB_HOST, DB_PORT, etc.)
        test_mode = False

    region = os.environ.get('AWS_REGION', 'eu-west-1')

    print(f"=== Seed email_verifications from SES ({args.env}) ===")
    print(f"  Region: {region}")
    print(f"  Dry run: {args.dry_run}")
    print()

    # Step 1: Get verified emails from SES
    print("1. Querying SES for verified email identities...")
    verified_emails = get_ses_verified_emails(region)
    print(f"   Found {len(verified_emails)} verified emails in SES")
    print()

    # Step 2: Connect to database
    print("2. Connecting to database...")
    from database import DatabaseManager
    db = DatabaseManager(test_mode=test_mode)
    print("   Connected.")
    print()

    # Step 3: Get tenant → email mapping
    print("3. Loading tenant contact email mapping...")
    tenant_mapping = get_tenant_email_mapping(db)
    print(f"   Found {len(tenant_mapping)} tenants with contact_email configured")
    print()

    # Step 4: Get existing records
    print("4. Checking existing verification records...")
    existing = get_existing_verifications(db)
    print(f"   Found {len(existing)} existing records")
    print()

    # Step 5: Seed
    print("5. Seeding verification records...")
    inserted = seed_verifications(db, verified_emails, tenant_mapping, existing,
                                  dry_run=args.dry_run)
    print()

    action = "Would insert" if args.dry_run else "Inserted"
    print(f"=== Done. {action} {inserted} records. ===")


if __name__ == '__main__':
    main()
