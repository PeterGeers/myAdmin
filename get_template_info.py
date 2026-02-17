#!/usr/bin/env python3
"""Get template file IDs from database"""

import sys
from pathlib import Path

# Add backend/src to path
backend_src = Path(__file__).parent / 'backend' / 'src'
sys.path.insert(0, str(backend_src))

from database import DatabaseManager

def main():
    db = DatabaseManager(test_mode=False)
    
    query = """
        SELECT 
            administration,
            template_type,
            template_file_id,
            is_active,
            created_at,
            updated_at
        FROM tenant_template_config
        WHERE administration = 'GoodwinSolutions'
        ORDER BY template_type
    """
    
    results = db.execute_query(query)
    
    print("\nTemplate Configuration for GoodwinSolutions:")
    print("=" * 80)
    
    for row in results:
        print(f"\nTemplate Type: {row['template_type']}")
        print(f"  File ID: {row['template_file_id']}")
        print(f"  Active: {row['is_active']}")
        print(f"  Created: {row['created_at']}")
        print(f"  Updated: {row['updated_at']}")
        print(f"  URL: https://drive.google.com/file/d/{row['template_file_id']}/view")

if __name__ == '__main__':
    main()
