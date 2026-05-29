"""
One-time seed: Insert verified records for all SES verified emails × all tenants.
"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from datetime import datetime
from database import DatabaseManager

# The 4 verified emails from SES
VERIFIED_EMAILS = [
    'pjageers@gmail.com',
    'peter@pgeers.nl',
    'webhulpje@h-dcn.nl',
    'webmaster@h-dcn.nl',
]

def get_all_tenants(db):
    """Get all distinct administration values from parameters."""
    rows = db.execute_query(
        """SELECT DISTINCT scope_id AS administration
           FROM parameters
           WHERE scope = 'tenant' AND scope_id IS NOT NULL AND scope_id != ''"""
    )
    return [r['administration'] for r in rows]

def main():
    db = DatabaseManager(test_mode=False)
    tenants = get_all_tenants(db)
    print(f"Found {len(tenants)} tenants: {tenants}")
    
    now = datetime.utcnow()
    inserted = 0
    
    for tenant in tenants:
        for email in VERIFIED_EMAILS:
            # Check if already exists
            existing = db.execute_query(
                """SELECT id FROM email_verifications
                   WHERE administration = %s AND email = %s""",
                (tenant, email)
            )
            if existing:
                print(f"  SKIP: {tenant} / {email} — already exists")
                continue
            
            db.execute_query(
                """INSERT INTO email_verifications
                   (administration, email, status, initiated_at, verified_at)
                   VALUES (%s, %s, 'verified', %s, %s)""",
                (tenant, email, now, now),
                fetch=False, commit=True
            )
            print(f"  INSERTED: {tenant} / {email} (verified)")
            inserted += 1
    
    print(f"\nDone. Inserted {inserted} records.")

if __name__ == '__main__':
    main()
