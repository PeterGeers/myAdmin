#!/usr/bin/env python3
"""
Check and insert myAdmin ADMIN module into tenant_modules table
"""
import os
import sys
from datetime import datetime

# Add parent directory to path to import database module
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.database import DatabaseManager

def check_and_insert_myadmin_module():
    """Check if myAdmin ADMIN module exists, insert if not"""
    db_manager = DatabaseManager()
    conn = None
    cursor = None
    
    try:
        # Get database connection
        conn = db_manager.get_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Check if myAdmin ADMIN module exists
        print("Checking for myAdmin ADMIN module...")
        cursor.execute("""
            SELECT * FROM tenant_modules 
            WHERE administration = 'myAdmin' AND module_name = 'ADMIN'
        """)
        
        result = cursor.fetchone()
        
        if result:
            print("✅ myAdmin ADMIN module already exists:")
            print(f"   ID: {result['id']}")
            print(f"   Administration: {result['administration']}")
            print(f"   Module: {result['module_name']}")
            print(f"   Active: {result['is_active']}")
            print(f"   Created: {result['created_at']}")
            return True
        
        # Insert myAdmin ADMIN module
        print("❌ myAdmin ADMIN module not found. Inserting...")
        cursor.execute("""
            INSERT INTO tenant_modules (administration, module_name, is_active, created_at)
            VALUES ('myAdmin', 'ADMIN', TRUE, NOW())
        """)
        
        conn.commit()
        
        # Verify insertion
        cursor.execute("""
            SELECT * FROM tenant_modules 
            WHERE administration = 'myAdmin' AND module_name = 'ADMIN'
        """)
        
        result = cursor.fetchone()
        
        if result:
            print("✅ Successfully inserted myAdmin ADMIN module:")
            print(f"   ID: {result['id']}")
            print(f"   Administration: {result['administration']}")
            print(f"   Module: {result['module_name']}")
            print(f"   Active: {result['is_active']}")
            print(f"   Created: {result['created_at']}")
            return True
        else:
            print("❌ Failed to verify insertion")
            return False
            
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

def check_tenant_modules_schema():
    """Display tenant_modules table schema"""
    db_manager = DatabaseManager()
    conn = None
    cursor = None
    
    try:
        conn = db_manager.get_connection()
        cursor = conn.cursor(dictionary=True)
        
        print("\n" + "="*60)
        print("TENANT_MODULES TABLE SCHEMA")
        print("="*60)
        
        cursor.execute("DESCRIBE tenant_modules")
        
        for row in cursor.fetchall():
            print(f"Field: {row['Field']}")
            print(f"  Type: {row['Type']}")
            print(f"  Null: {row['Null']}")
            print(f"  Key: {row['Key']}")
            print(f"  Default: {row['Default']}")
            print(f"  Extra: {row['Extra']}")
            print()
            
    except Exception as e:
        print(f"❌ Error getting schema: {e}")
        
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

def list_all_tenant_modules():
    """List all tenant modules"""
    db_manager = DatabaseManager()
    conn = None
    cursor = None
    
    try:
        conn = db_manager.get_connection()
        cursor = conn.cursor(dictionary=True)
        
        print("\n" + "="*60)
        print("ALL TENANT MODULES")
        print("="*60)
        
        cursor.execute("""
            SELECT * FROM tenant_modules 
            ORDER BY administration, module_name
        """)
        
        results = cursor.fetchall()
        
        if not results:
            print("No tenant modules found")
            return
            
        for row in results:
            print(f"ID: {row['id']} | {row['administration']} | {row['module_name']} | Active: {row['is_active']} | Created: {row['created_at']}")
            
    except Exception as e:
        print(f"❌ Error listing modules: {e}")
        
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

if __name__ == "__main__":
    print("="*60)
    print("MYADMIN MODULE CHECK AND INSERT")
    print("="*60)
    print()
    
    # Check and insert myAdmin ADMIN module
    success = check_and_insert_myadmin_module()
    
    # Display schema
    check_tenant_modules_schema()
    
    # List all modules
    list_all_tenant_modules()
    
    print("\n" + "="*60)
    if success:
        print("✅ TASK COMPLETE")
    else:
        print("❌ TASK FAILED")
    print("="*60)
