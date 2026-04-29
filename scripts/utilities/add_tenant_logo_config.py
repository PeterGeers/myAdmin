#!/usr/bin/env python3
"""Add logo file ID to tenant configuration"""

import sys
from pathlib import Path

backend_src = Path(__file__).parent / 'backend' / 'src'
sys.path.insert(0, str(backend_src))

from database import DatabaseManager

def main():
    db = DatabaseManager(test_mode=False)
    
    # Add logo file ID for GoodwinSolutions
    logo_file_id = '1EJ1wo3qCWUzdUOoW5AYhZM1Fhz0vGJyW'
    
    # Check if config exists
    check_query = """
        SELECT id FROM tenant_config
        WHERE administration = 'GoodwinSolutions' 
        AND config_key = 'company_logo_file_id'
    """
    existing = db.execute_query(check_query)
    
    if existing:
        # Update
        update_query = """
            UPDATE tenant_config
            SET config_value = %s
            WHERE administration = 'GoodwinSolutions' 
            AND config_key = 'company_logo_file_id'
        """
        db.execute_query(update_query, (logo_file_id,), fetch=False, commit=True)
        print(f"✅ Updated logo file ID for GoodwinSolutions: {logo_file_id}")
    else:
        # Insert
        insert_query = """
            INSERT INTO tenant_config (administration, config_key, config_value)
            VALUES ('GoodwinSolutions', 'company_logo_file_id', %s)
        """
        db.execute_query(insert_query, (logo_file_id,), fetch=False, commit=True)
        print(f"✅ Added logo file ID for GoodwinSolutions: {logo_file_id}")
    
    print(f"\nLogo URL: https://lh3.googleusercontent.com/d/{logo_file_id}")
    print(f"Or: https://drive.google.com/uc?export=view&id={logo_file_id}")

if __name__ == '__main__':
    main()
