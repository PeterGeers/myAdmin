#!/usr/bin/env python3
"""Update Administrators role to SysAdmin in route files"""

import os
import re

files_to_update = [
    'src/scalability_routes.py',
    'src/duplicate_performance_routes.py',
    'src/app.py',
    'src/audit_routes.py'
]

for filepath in files_to_update:
    full_path = os.path.join('backend', filepath)
    if not os.path.exists(full_path):
        print(f"Skipping {full_path} - file not found")
        continue
    
    with open(full_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Replace Administrators with SysAdmin
    updated_content = content.replace("required_roles=['Administrators']", "required_roles=['SysAdmin']")
    
    if content != updated_content:
        with open(full_path, 'w', encoding='utf-8') as f:
            f.write(updated_content)
        print(f"✅ Updated {filepath}")
    else:
        print(f"⏭️  No changes needed in {filepath}")

print("\n✅ All files updated!")
