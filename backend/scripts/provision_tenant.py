#!/usr/bin/env python3
"""
Provision Tenant Script

Manual provisioning script for verified trial signups.
Run after a user has verified their email (status='verified' in pending_signups).

Usage:
    python scripts/provision_tenant.py <email>
    python scripts/provision_tenant.py peter@jabaki.nl --dry-run
    python scripts/provision_tenant.py peter@jabaki.nl --name "MyCompany" --modules "FIN,STR,TENADMIN"
    python scripts/provision_tenant.py peter@jabaki.nl --test-mode

Steps:
    1. Look up pending_signups row (myadmin_promo DB)
    2. Generate administration name from company/email
    3. Insert tenants row (finance DB)
    4. Insert tenant_modules rows — FIN + TENADMIN, optionally STR (finance DB)
    5. Copy default rekeningschema (chart of accounts) from GoodwinSolutions template
    6. Update Cognito user: add custom:tenants attribute
    7. Update pending_signups.status = 'provisioned' (myadmin_promo DB)
    8. Send admin notification via SNS
"""

import os
import sys
import json
import re
import argparse
import logging
import boto3
from datetime import datetime
from pathlib import Path

# Add src to path
backend_dir = Path(__file__).parent.parent
src_dir = backend_dir / 'src'
sys.path.insert(0, str(src_dir))
sys.path.insert(0, str(backend_dir))

# Load .env
from dotenv import load_dotenv
load_dotenv(backend_dir / '.env')

from database import DatabaseManager

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)


# ============================================================================
# Database helpers
# ============================================================================

def get_promo_db():
    """Get DatabaseManager for myadmin_promo database"""
    db = DatabaseManager()
    db.config['database'] = os.getenv('PROMO_DB_NAME', 'myadmin_promo')
    return db


def get_finance_db(test_mode=False):
    """Get DatabaseManager for finance database"""
    return DatabaseManager(test_mode=test_mode)


def generate_administration_name(company_name: str, email: str, test_mode=False) -> str:
    """
    Generate a unique administration name from company name or email.
    Rules: PascalCase, alphanumeric only, max 50 chars, must be unique in tenants table.
    Appends numeric suffix if name already exists.
    """
    source = company_name.strip() if company_name else email.split('@')[0]
    # Remove non-alphanumeric, split into words, PascalCase
    words = re.sub(r'[^a-zA-Z0-9\s]', '', source).split()
    base_name = ''.join(w.capitalize() for w in words if w)
    if not base_name:
        base_name = 'NewTenant'
    base_name = base_name[:45]  # Leave room for suffix

    # Check uniqueness against finance DB
    db = get_finance_db(test_mode)
    candidate = base_name
    suffix = 1
    while True:
        result = db.execute_query(
            "SELECT COUNT(*) as cnt FROM tenants WHERE administration = %s",
            (candidate,)
        )
        count = result[0]['cnt'] if result else 0
        if count == 0:
            break
        candidate = f"{base_name}{suffix}"
        suffix += 1
    return candidate


# ============================================================================
# Provisioning steps
# ============================================================================

def lookup_signup(email: str) -> dict:
    """Step 1: Look up pending_signups row"""
    db = get_promo_db()
    result = db.execute_query(
        "SELECT * FROM pending_signups WHERE email = %s",
        (email,)
    )
    return result[0] if result else None


def insert_tenant(admin_name: str, display_name: str, email: str, test_mode=False):
    """Step 2: Insert into tenants table"""
    db = get_finance_db(test_mode)
    db.execute_query(
        """INSERT INTO tenants 
           (administration, display_name, status, contact_email, country, created_at, created_by)
           VALUES (%s, %s, 'active', %s, 'Netherlands', NOW(), 'provision_tenant.py')""",
        (admin_name, display_name, email),
        fetch=False, commit=True
    )
    logger.info(f"  ✅ Tenant '{admin_name}' inserted into tenants table")


def insert_modules_list(admin_name: str, modules: list, test_mode=False):
    """Step 3: Insert tenant_modules from provided list"""
    db = get_finance_db(test_mode)
    with db.get_cursor() as (cursor, conn):
        for module in modules:
            cursor.execute(
                """INSERT INTO tenant_modules (administration, module_name, is_active, created_at)
                   VALUES (%s, %s, TRUE, NOW())""",
                (admin_name, module)
            )
        conn.commit()
    logger.info(f"  ✅ Modules inserted: {', '.join(modules)}")


def copy_default_chart_of_accounts(admin_name: str, test_mode=False):
    """Step 4: Copy rekeningschema from GoodwinSolutions as default template"""
    db = get_finance_db(test_mode)
    with db.get_cursor() as (cursor, conn):
        cursor.execute(
            """INSERT INTO rekeningschema 
               (Account, AccountLookup, AccountName, SubParent, Parent, VW, Belastingaangifte, administration, Pattern)
               SELECT Account, AccountLookup, AccountName, SubParent, Parent, VW, Belastingaangifte, %s, Pattern
               FROM rekeningschema 
               WHERE administration = 'GoodwinSolutions'""",
            (admin_name,)
        )
        count = cursor.rowcount
        conn.commit()
    logger.info(f"  ✅ Copied {count} chart of accounts entries from GoodwinSolutions")


def update_cognito_user(email: str, admin_name: str):
    """Step 5: Add administration to Cognito user's custom:tenants attribute"""
    region = os.getenv('AWS_REGION', 'eu-west-1')
    pool_id = os.getenv('SIGNUP_COGNITO_USER_POOL_ID', os.getenv('COGNITO_USER_POOL_ID'))

    client = boto3.client('cognito-idp', region_name=region)

    # Get current user attributes
    try:
        user = client.admin_get_user(UserPoolId=pool_id, Username=email)
    except client.exceptions.UserNotFoundException:
        logger.error(f"  ❌ Cognito user {email} not found")
        raise

    # Parse existing tenants
    current_tenants = []
    for attr in user.get('UserAttributes', []):
        if attr['Name'] == 'custom:tenants':
            try:
                current_tenants = json.loads(attr['Value'])
            except (json.JSONDecodeError, TypeError):
                current_tenants = []

    if admin_name not in current_tenants:
        current_tenants.append(admin_name)

    client.admin_update_user_attributes(
        UserPoolId=pool_id,
        Username=email,
        UserAttributes=[{
            'Name': 'custom:tenants',
            'Value': json.dumps(current_tenants)
        }]
    )
    logger.info(f"  ✅ Cognito user updated: custom:tenants = {json.dumps(current_tenants)}")


def mark_provisioned(email: str):
    """Step 6: Update pending_signups status to 'provisioned'"""
    db = get_promo_db()
    db.execute_query(
        "UPDATE pending_signups SET status = 'provisioned', provisioned_at = NOW() WHERE email = %s",
        (email,),
        fetch=False, commit=True
    )
    logger.info(f"  ✅ pending_signups status updated to 'provisioned'")


def send_notification(email: str, admin_name: str, first_name: str):
    """Step 7: Send admin notification via SNS"""
    try:
        from aws_notifications import get_notification_service
        service = get_notification_service()
        if service and service.is_enabled():
            service.send_business_notification(
                'Tenant Provisioned',
                f"Tenant '{admin_name}' provisioned for {email}",
                {'email': email, 'administration': admin_name, 'name': first_name}
            )
            logger.info(f"  ✅ Admin notification sent")
        else:
            logger.info(f"  ⚠️  SNS not configured — skipping notification")
    except Exception as e:
        logger.warning(f"  ⚠️  Notification failed (non-critical): {e}")


# ============================================================================
# Main
# ============================================================================

def provision(email: str, dry_run=False, test_mode=False, admin_name_override=None, modules_override=None, force=False):
    """Run the full provisioning flow"""
    db_label = 'testfinance' if test_mode else 'finance'
    logger.info(f"Provisioning tenant for: {email} (DB: {db_label})")

    # Step 1: Look up signup
    signup = lookup_signup(email)
    if not signup:
        logger.error(f"❌ No pending_signups record found for {email}")
        sys.exit(1)

    if signup['status'] == 'provisioned' and not force:
        logger.error(f"❌ {email} is already provisioned (provisioned_at: {signup.get('provisioned_at')})")
        logger.info("  Use --force to rerun provisioning for partial failures")
        sys.exit(1)

    if signup['status'] not in ('verified', 'provisioned'):
        logger.error(f"❌ {email} status is '{signup['status']}' — must be 'verified' to provision")
        sys.exit(1)

    # Administration name: use override from frontend, fallback to auto-generated
    if admin_name_override:
        admin_name = admin_name_override
        logger.info(f"  Using provided administration name: {admin_name}")
        # Still check uniqueness
        db = get_finance_db(test_mode)
        result = db.execute_query(
            "SELECT COUNT(*) as cnt FROM tenants WHERE administration = %s",
            (admin_name,)
        )
        if result and result[0]['cnt'] > 0:
            logger.error(f"❌ Administration '{admin_name}' already exists in tenants table")
            sys.exit(1)
    else:
        admin_name = generate_administration_name(signup.get('company_name', ''), email, test_mode)

    # Modules: use override from frontend, fallback to default
    if modules_override:
        modules = [m.strip().upper() for m in modules_override.split(',')]
        # Always ensure TENADMIN is included
        if 'TENADMIN' not in modules:
            modules.append('TENADMIN')
        logger.info(f"  Using provided modules: {', '.join(modules)}")
    else:
        modules = ['FIN', 'STR', 'TENADMIN']

    display_name = signup.get('company_name') or f"{signup['first_name']} {signup['last_name']}"
    first_name = signup['first_name']

    logger.info(f"  Signup: {first_name} {signup['last_name']} ({email})")
    logger.info(f"  Administration: {admin_name}")
    logger.info(f"  Display name: {display_name}")
    logger.info(f"  Modules: {', '.join(modules)}")

    if dry_run:
        logger.info("\n🔍 DRY RUN — no changes made")
        return

    # Step 2: Insert tenant + modules + chart via shared service
    from database import DatabaseManager
    from services.tenant_provisioning_service import TenantProvisioningService

    db = DatabaseManager(test_mode=test_mode)
    service = TenantProvisioningService(db)

    locale = signup.get('locale', 'nl')
    results = service.create_and_provision_tenant(
        administration=admin_name,
        display_name=display_name,
        contact_email=email,
        modules=modules,
        created_by='provision_tenant.py',
        locale=locale,
        initial_admin_email=email,
    )

    logger.info(f"  Provisioning results: tenant={results['tenant']}, "
                f"chart={results['chart']} ({results['chart_rows']} rows)")
    for mod in results['modules']:
        logger.info(f"    Module {mod['name']}: {mod['status']}")
    if 'initial_admin' in results:
        logger.info(f"  Initial admin: {results['initial_admin']['status']}")
    for warning in results.get('warnings', []):
        logger.warning(f"  ⚠️  {warning}")

    # Step 5: Update Cognito user
    update_cognito_user(email, admin_name)

    # Step 6: Mark provisioned
    mark_provisioned(email)

    # Step 7: Notify admin
    send_notification(email, admin_name, first_name)

    logger.info(f"\n✅ Tenant '{admin_name}' provisioned successfully for {email}")
    logger.info(f"   User can now log in and will see administration '{admin_name}'")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Provision a new tenant from a verified signup')
    parser.add_argument('email', help='Email of the verified signup to provision')
    parser.add_argument('--name', dest='admin_name', help='Administration name (overrides auto-generated)')
    parser.add_argument('--modules', help='Comma-separated module list, e.g. "FIN,STR,TENADMIN" (default: FIN,STR,TENADMIN)')
    parser.add_argument('--dry-run', action='store_true', help='Show what would happen without making changes')
    parser.add_argument('--force', action='store_true', help='Rerun provisioning even if already provisioned (for partial failures)')
    parser.add_argument('--test-mode', action='store_true', help='Use testfinance DB instead of finance')
    args = parser.parse_args()

    provision(args.email, dry_run=args.dry_run, test_mode=args.test_mode,
              admin_name_override=args.admin_name, modules_override=args.modules,
              force=args.force)
