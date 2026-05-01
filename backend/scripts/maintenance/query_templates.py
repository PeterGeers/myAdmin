import sys
import os
import json
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / 'src'))

from database import DatabaseManager

db = DatabaseManager()
rows = db.execute_query('''
    SELECT id, administration, template_type, is_active, version, approved_at, approved_by
    FROM tenant_template_config 
    ORDER BY administration, template_type
''')

print("\n=== TENANT TEMPLATE CONFIG RECORDS ===\n")
print(f"{'ID':<5} {'Administration':<20} {'Template Type':<25} {'Active':<8} {'Version':<8} {'Approved At':<20} {'Approved By':<30}")
print("-" * 140)

for r in rows:
    print(f"{r['id']:<5} {r['administration']:<20} {r['template_type']:<25} {str(r['is_active']):<8} {r['version']:<8} {str(r['approved_at']):<20} {str(r['approved_by']):<30}")
