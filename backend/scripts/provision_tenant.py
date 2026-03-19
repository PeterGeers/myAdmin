#!/usr/bin/env python3
"""
Provision Tenant Script

Manual provisioning script for verified trial signups.
Run after a user has verified their email (status='verified' in pending_signups).

Usage:
    python scripts/provision_tenant.py <email>
    python scripts/provision_tenant.py peter@jabaki.nl --dry-run
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
import mysql.connector
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

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)


# ============================================================================
# Database helpers
# ============================================================================

def get_promo_db_config():
    """Connection config for myadmin_promo database"""
    return {
        'host': os.getenv('DB_HOST', 'localhost'),
        'user': os.getenv('DB_USER', 'root'),
        'password': os.getenv('DB_PASSWORD', ''),
        'database': os.getenv('PROMO_DB_NAME', 'myadmin_promo'),
        'port': int(os.getenv('DB_PORT', '3306')),
    }


def get_finance_db_config(test_mode=False):
    """Connection config for finance database"""
    db_name = os.getenv('TEST_DB_NAME', 'testfinance') if test_mode else os.getenv('DB_NAME', 'finance')
    return {
        'host': os.getenv('DB_HOST', 'localhost'),
        'user': os.getenv('DB_USER', 'root'),
        'password': os.getenv('DB_PASSWORD', ''),
        'database': db_name,
        'port': int(os.getenv('DB_PORT', '3306')),
    }


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
    conn = mysql.connector.connect(**get_finance_db_config(test_mode))
    try:
        cursor = conn.cursor()
        candidate = base_name
        suffix = 1
        while True:
            cursor.execute(
                "SELECT COUNT(*) FROM tenants WHERE administration = %s",
                (candidate,)
            )
            count = cursor.fetchone()[0]
            if count == 0:
                break
            candidate = f"{base_name}{suffix}"
            suffix += 1
        cursor.close()
        return candidate
    finally:
        conn.close()


# ============================================================================
# Provisioning steps
# ============================================================================

def lookup_signup(email: str) -> dict:
    """Step 1: Look up pending_signups row"""
    conn = mysql.connector.connect(**get_promo_db_config())
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM pending_signups WHERE email = %s", (email,))
        row = cursor.fetchone()
        cursor.close()
        return row
    finally:
        conn.close()


def insert_tenant(admin_name: str, display_name: str, email: str, test_mode=False):
    """Step 2: Insert into tenants table"""
    conn = mysql.connector.connect(**get_finance_db_config(test_mode))
    try:
        cursor = conn.cursor()
        cursor.execute(
            """INSERT INTO tenants 
               (administration, display_name, status, contact_email, country, created_at, created_by)
               VALUES (%s, %s, 'active', %s, 'Netherlands', NOW(), 'provision_tenant.py')""",
            (admin_name, display_name, email)
        )
        conn.commit()
        cursor.close()
        logger.info(f"  ✅ Tenant '{admin_name}' inserted into tenants table")
    finally:
        conn.close()


def insert_modules(admin_name: str, test_mode=False):
    """Step 3: Insert tenant_modules — FIN, STR, TENADMIN for all trial signups"""
    modules = ['FIN', 'STR', 'TENADMIN']

    conn = mysql.connector.connect(**get_finance_db_config(test_mode))
    try:
        cursor = conn.cursor()
        for module in modules:
            cursor.execute(
                """INSERT INTO tenant_modules (administration, module_name, is_active, created_at)
                   VALUES (%s, %s, TRUE, NOW())""",
                (admin_name, module)
            )
        conn.commit()
        cursor.close()
        logger.info(f"  ✅ Modules inserted: {', '.join(modules)}")
    finally:
        conn.close()


def copy_default_chart_of_accounts(admin_name: str, test_mode=False):
    """Step 4: Copy rekeningschema from GoodwinSolutions as default template"""
    conn = mysql.connector.connect(**get_finance_db_config(test_mode))
    try:
        cursor = conn.cursor()
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
        cursor.close()
        logger.info(f"  ✅ Copied {count} chart of accounts entries from GoodwinSolutions")
    finally:
        conn.close()


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
    conn = mysql.connector.connect(**get_promo_db_config())
    try:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE pending_signups SET status = 'provisioned', provisioned_at = NOW() WHERE email = %s",
            (email,)
        )
        conn.commit()
        cursor.close()
        logger.info(f"  ✅ pending_signups status updated to 'provisioned'")
    finally:
        conn.close()


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

def provision(email: str, dry_run=False, test_mode=False):
    """Run the full provisioning flow"""
    db_label = 'testfinance' if test_mode else 'finance'
    logger.info(f"Provisioning tenant for: {email} (DB: {db_label})")

    # Step 1: Look up signup
    signup = lookup_signup(email)
    if not signup:
        logger.error(f"❌ No pending_signups record found for {email}")
        sys.exit(1)

    if signup['status'] == 'provisioned':
        logger.error(f"❌ {email} is already provisioned (provisioned_at: {signup.get('provisioned_at')})")
        sys.exit(1)

    if signup['status'] != 'verified':
        logger.error(f"❌ {email} status is '{signup['status']}' — must be 'verified' to provision")
        sys.exit(1)

    # Generate administration name
    admin_name = generate_administration_name(signup.get('company_name', ''), email, test_mode)
    display_name = signup.get('company_name') or f"{signup['first_name']} {signup['last_name']}"
    first_name = signup['first_name']

    logger.info(f"  Signup: {first_name} {signup['last_name']} ({email})")
    logger.info(f"  Administration: {admin_name}")
    logger.info(f"  Display name: {display_name}")
    logger.info(f"  Modules: FIN, STR, TENADMIN")

    if dry_run:
        logger.info("\n🔍 DRY RUN — no changes made")
        return

    # Step 2: Insert tenant
    insert_tenant(admin_name, display_name, email, test_mode)

    # Step 3: Insert modules
    insert_modules(admin_name, test_mode)

    # Step 4: Copy default chart of accounts
    copy_default_chart_of_accounts(admin_name, test_mode)

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
    parser.add_argument('--dry-run', action='store_true', help='Show what would happen without making changes')
    parser.add_argument('--test-mode', action='store_true', help='Use testfinance DB instead of finance')
    args = parser.parse_args()

    provision(args.email, dry_run=args.dry_run, test_mode=args.test_mode)
