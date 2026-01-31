#!/usr/bin/env python3
"""View sample field mappings from database"""

import sys
from pathlib import Path
import json

# Add backend/src to path
backend_src = Path(__file__).parent.parent / 'backend' / 'src'
sys.path.insert(0, str(backend_src))

from database import DatabaseManager

db = DatabaseManager()

# Get one sample from each template type
query = """
    SELECT administration, template_type, 
           JSON_EXTRACT(field_mappings, '$.version') as version,
           JSON_EXTRACT(field_mappings, '$.description') as description
    FROM tenant_template_config
    WHERE administration = 'GoodwinSolutions'
    ORDER BY template_type
"""

results = db.execute_query(query)

print("\nField Mappings Summary:")
print("="*80)
print(f"{'Template Type':<30} {'Version':<10} {'Description':<40}")
print("-"*80)

for row in results:
    template_type = row['template_type']
    version = str(row['version']).strip('"') if row['version'] else 'N/A'
    description = str(row['description']).strip('"') if row['description'] else 'N/A'
    print(f"{template_type:<30} {version:<10} {description[:38]:<40}")

print("="*80)

# Show detailed view of one template
print("\nDetailed view of btw_aangifte_html:")
print("="*80)

detail_query = """
    SELECT field_mappings
    FROM tenant_template_config
    WHERE administration = 'GoodwinSolutions' AND template_type = 'btw_aangifte_html'
"""

detail = db.execute_query(detail_query)
if detail and detail[0]['field_mappings']:
    mappings = json.loads(detail[0]['field_mappings'])
    print(json.dumps(mappings, indent=2))
else:
    print("No field mappings found")
