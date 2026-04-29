#!/usr/bin/env python3
"""
Add TENADMIN module to all tenants
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.database import DatabaseManager

def add_tenadmin_to_all_tenants():
    """Add TENADMIN module to all tenants that don't have it"""
    db_manager = DatabaseManager()
    conn = None
    cursor = None
    
    try:
        conn = db_manager.get_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Get all tenants
        cursor.execute("SELECT DISTINCT administration FROM tenants")
        tenants = cursor.fetchall()
        
        print(f"Found {len(tenants)} tenants")
        print()
        
        for tenant in tenants:
            admin = tenant['administration']
            
            # Check if TENADMIN already exists
            cursor.execute("""
                SELECT * FROM tenant_modules 
                WHERE administration = %s AND module_name = 'TENADMIN'
            """, (admin,))
            
            if cursor.fetchone():
                print(f"✅ {admin}: TENADMIN already exists")
            else:
                # Insert TENADMIN
                cursor.execute("""
                    INSERT INTO tenant_modules (administration, module_name, is_active, created_at)
                    VALUES (%s, 'TENADMIN', TRUE, NOW())
                """, (admin,))
                conn.commit()
                print(f"✅ {admin}: TENADMIN added")
        
        print()
        print("="*60)
        print("ALL TENANT MODULES (after update)")
        print("="*60)
        
        cursor.execute("""
            SELECT * FROM tenant_modules 
            ORDER BY administration, module_name
        """)
        
        for row in cursor.fetchall():
            print(f"{row['administration']:20} | {row['module_name']:10} | Active: {row['is_active']}")
        
        return True
        
    except Exception as e:
        print(f"❌ Error: {e}")
        if conn:
            conn.rollback()
        return False
        
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

if __name__ == "__main__":
    print("="*60)
    print("ADD TENADMIN MODULE TO ALL TENANTS")
    print("="*60)
    print()
    
    success = add_tenadmin_to_all_tenants()
    
    print()
    print("="*60)
    if success:
        print("✅ COMPLETE")
    else:
        print("❌ FAILED")
    print("="*60)
