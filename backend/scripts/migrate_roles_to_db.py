"""
Migrate Cognito group-based roles to per-tenant DB roles.

For each Cognito user, reads their groups and tenants, then inserts
per-tenant role rows into user_tenant_roles. Skips global roles
(SysAdmin, Administrators, System_CRUD) since those stay in JWT.

Usage:
    python scripts/migrate_roles_to_db.py --dry-run     # Preview only
    python scripts/migrate_roles_to_db.py               # Execute migration
    python scripts/migrate_roles_to_db.py --db-host=xxx --db-password=xxx  # Custom DB
"""

import argparse
import json
import os
import sys
import boto3
import mysql.connector

GLOBAL_ROLES = {'SysAdmin', 'Administrators', 'System_CRUD'}


def get_args():
    parser = argparse.ArgumentParser(description='Migrate Cognito roles to user_tenant_roles table')
    parser.add_argument('--dry-run', action='store_true', help='Preview without writing to DB')
    parser.add_argument('--db-host', default=os.getenv('DB_HOST', 'localhost'))
    parser.add_argument('--db-port', type=int, default=int(os.getenv('DB_PORT', '3306')))
    parser.add_argument('--db-user', default=os.getenv('DB_USER', 'peter'))
    parser.add_argument('--db-password', default=os.getenv('DB_PASSWORD', ''))
    parser.add_argument('--db-name', default=os.getenv('DB_NAME', 'finance'))
    parser.add_argument('--region', default=os.getenv('AWS_REGION', 'eu-west-1'))
    parser.add_argument('--user-pool-id', default=os.getenv('COGNITO_USER_POOL_ID', ''))
    return parser.parse_args()


def main():
    args = get_args()
    mode = 'DRY RUN' if args.dry_run else 'LIVE'
    print(f'=== Migration: Cognito roles → user_tenant_roles ({mode}) ===')
    print(f'DB: {args.db_host}:{args.db_port}/{args.db_name}')

    # Connect to DB
    conn = mysql.connector.connect(
        host=args.db_host, port=args.db_port,
        user=args.db_user, password=args.db_password,
        database=args.db_name
    )
    cursor = conn.cursor(dictionary=True)

    # Get valid tenants
    cursor.execute('SELECT administration FROM tenants')
    valid_tenants = {r['administration'] for r in cursor.fetchall()}
    print(f'Valid tenants: {sorted(valid_tenants)}')

    # Get Cognito users
    cognito = boto3.client('cognito-idp', region_name=args.region)
    users = cognito.list_users(UserPoolId=args.user_pool_id, Limit=60)

    inserted = 0
    skipped = 0

    for u in users['Users']:
        username = u['Username']
        email = next((a['Value'] for a in u['Attributes'] if a['Name'] == 'email'), username)
        tenants_raw = next((a['Value'] for a in u['Attributes'] if a['Name'] == 'custom:tenants'), '[]')
        try:
            tenants = json.loads(tenants_raw)
        except (json.JSONDecodeError, TypeError):
            tenants = [tenants_raw] if tenants_raw else []

        groups_resp = cognito.admin_list_groups_for_user(Username=username, UserPoolId=args.user_pool_id)
        per_tenant_roles = [g['GroupName'] for g in groups_resp['Groups'] if g['GroupName'] not in GLOBAL_ROLES]

        if not tenants or not per_tenant_roles:
            continue

        for tenant in tenants:
            if tenant not in valid_tenants:
                print(f'  SKIP {email} x {tenant} (not in tenants table)')
                skipped += 1
                continue
            for role in per_tenant_roles:
                if args.dry_run:
                    print(f'  [DRY] {email} | {tenant} | {role}')
                    inserted += 1
                else:
                    try:
                        cursor.execute(
                            'INSERT IGNORE INTO user_tenant_roles (email, administration, role, created_by) VALUES (%s, %s, %s, %s)',
                            (email, tenant, role, 'migration')
                        )
                        conn.commit()
                        inserted += 1
                        print(f'  OK {email} | {tenant} | {role}')
                    except Exception as e:
                        print(f'  ERR {email} | {tenant} | {role}: {e}')

    cursor.close()
    conn.close()
    print(f'\nDone: {inserted} {"would be inserted" if args.dry_run else "inserted"}, {skipped} skipped')


if __name__ == '__main__':
    main()
