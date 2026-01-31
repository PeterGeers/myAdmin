#!/usr/bin/env python3
"""Check field_mappings in tenant_template_config table"""

import sys
from pathlib import Path

# Add backend/src to path
backend_src = Path(__file__).parent.parent / 'backend' / 'src'
sys.path.insert(0, str(backend_src))

from database import DatabaseManager

db = DatabaseManager()
result = db.execute_query(
    'SELECT administration, template_type, field_mappings FROM tenant_template_config ORDER BY administration, template_type'
)

print("\nField Mappings Status:")
print("="*80)

for row in result:
    admin = row['administration']
    template_type = row['template_type']
    field_mappings = row['field_mappings']
    
    status = "✅ HAS MAPPINGS" if field_mappings else "❌ EMPTY"
    print(f"{admin:20} {template_type:30} {status}")

print("="*80)
