#!/usr/bin/env python3
"""Check tenant configuration for logo settings"""

import sys
from pathlib import Path

backend_src = Path(__file__).parent / 'backend' / 'src'
sys.path.insert(0, str(backend_src))

from database import DatabaseManager

def main():
    db = DatabaseManager(test_mode=False)
    
    query = """
        SELECT config_key, config_value
        FROM tenant_config
        WHERE administration = 'GoodwinSolutions'
        AND config_key LIKE '%logo%'
    """
    
    results = db.execute_query(query)
    
    print("\nLogo-related configuration for GoodwinSolutions:")
    print("=" * 80)
    
    if results:
        for row in results:
            print(f"{row['config_key']}: {row['config_value']}")
    else:
        print("No logo configuration found")
        print("\nAll config keys for GoodwinSolutions:")
        all_query = "SELECT config_key FROM tenant_config WHERE administration = 'GoodwinSolutions'"
        all_results = db.execute_query(all_query)
        for row in all_results:
            print(f"  - {row['config_key']}")

if __name__ == '__main__':
    main()
