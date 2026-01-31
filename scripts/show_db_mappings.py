#!/usr/bin/env python3
import sys
from pathlib import Path

backend_src = Path(__file__).parent.parent / 'backend' / 'src'
sys.path.insert(0, str(backend_src))

from database import DatabaseManager

db = DatabaseManager()
r = db.execute_query('SELECT field_mappings FROM tenant_template_config WHERE template_type = "financial_report_xlsx" LIMIT 1')
print(r[0]['field_mappings'] if r else 'None')
