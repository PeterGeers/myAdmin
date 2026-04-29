#!/usr/bin/env python3
"""
Add FIN module to PeterPrive and GoodwinSolutions tenants
"""
import os
import sys

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.database import DatabaseManager

def add_fin_module_to_tenant(tenant_name):
    """Add FIN module to a tenant"""
    db_manager = DatabaseManager()
    conn = None
    cursor = None
    
    try:
        conn = db_manager.get_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Check if FIN module already exists
        cursor.execute("""
            SELECT * FROM tenant_modules 
            WHERE administration = %s AND module_name = 'FIN'
        """, (tenant_name,))
        
        result = cursor.fetchone()
        
        if result:
            print(f"✅ {tenant_name} already has FIN module (Active: {result['is_active']})")
            return True
        
        # Insert FIN module
        print(f"Adding FIN module to {tenant_name}...")
        cursor.execute("""
            INSERT INTO tenant_modules (administration, module_name, is_active, created_at)
            VALUES (%s, 'FIN', TRUE, NOW())
        """, (tenant_name,))
        
        conn.commit()
        print(f"✅ Successfully added FIN module to {tenant_name}")
        return True
            
    except Exception as e:
        print(f"❌ Error adding FIN module to {tenant_name}: {e}")
        if conn:
            conn.rollback()
        return False
        
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

def list_tenant_modules(tenant_name):
    """List all modules for a tenant"""
    db_manager = DatabaseManager()
    conn = None
    cursor = None
    
    try:
        conn = db_manager.get_connection()
        cursor = conn.cursor(dictionary=True)
        
        cursor.execute("""
            SELECT module_name, is_active, created_at 
            FROM tenant_modules 
            WHERE administration = %s
            ORDER BY module_name
        """, (tenant_name,))
        
        results = cursor.fetchall()
        
        if not results:
            print(f"  No modules found for {tenant_name}")
            return
            
        for row in results:
            status = "✅" if row['is_active'] else "❌"
            print(f"  {status} {row['module_name']} (Created: {row['created_at']})")
            
    except Exception as e:
        print(f"❌ Error listing modules for {tenant_name}: {e}")
        
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

if __name__ == "__main__":
    print("="*60)
    print("ADD FIN MODULE TO TENANTS")
    print("="*60)
    print()
    
    tenants = ['PeterPrive', 'GoodwinSolutions']
    
    for tenant in tenants:
        print(f"\n{tenant}:")
        add_fin_module_to_tenant(tenant)
        list_tenant_modules(tenant)
    
    print("\n" + "="*60)
    print("✅ COMPLETE")
    print("="*60)
