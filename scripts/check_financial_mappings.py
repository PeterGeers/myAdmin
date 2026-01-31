#!/usr/bin/env python3
import sys
from pathlib import Path
import json

backend_src = Path(__file__).parent.parent / 'backend' / 'src'
sys.path.insert(0, str(backend_src))

from database import DatabaseManager

db = DatabaseManager()

query = """
    SELECT administration, field_mappings
    FROM tenant_template_config
    WHERE template_type = 'financial_report_xlsx'
"""

results = db.execute_query(query)

for row in results:
    print(f"\n{row['administration']}:")
    print("="*80)
    if row['field_mappings']:
        mappings = json.loads(row['field_mappings'])
        print(json.dumps(mappings, indent=2))
    else:
        print("No mappings")
