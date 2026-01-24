#!/usr/bin/env python3
"""
Verify all views use lowercase 'administration' column
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.database import DatabaseManager

db = DatabaseManager()

print("=" * 60)
print("Verifying All Views Use Lowercase Administration")
print("=" * 60)

# Get all views
result = db.execute_query("""
    SELECT TABLE_NAME
    FROM INFORMATION_SCHEMA.VIEWS
    WHERE TABLE_SCHEMA = DATABASE()
    ORDER BY TABLE_NAME
""")

views = [r['TABLE_NAME'] for r in result]
print(f"\nFound {len(views)} views to check\n")

issues_found = []

for view_name in views:
    print(f"Checking {view_name}...")
    
    # Get view definition
    try:
        result = db.execute_query(f"SHOW CREATE VIEW {view_name}")
        if result:
            create_view = result[0]['Create View']
            
            # Count occurrences
            lowercase_count = create_view.count('`administration`')
            uppercase_count = create_view.count('`Administration`')
            
            # Also check without backticks
            lowercase_count += create_view.count('.administration')
            uppercase_count += create_view.count('.Administration')
            
            if uppercase_count > 0:
                print(f"   ⚠️  ISSUE: Uses uppercase 'Administration' ({uppercase_count} times)")
                issues_found.append({
                    'view': view_name,
                    'uppercase': uppercase_count,
                    'lowercase': lowercase_count
                })
            else:
                print(f"   ✅ OK: Uses lowercase 'administration' ({lowercase_count} times)")
        
        # Test the view works
        test_result = db.execute_query(f"SELECT * FROM {view_name} LIMIT 1")
        
        # Check if result has administration column
        if test_result and len(test_result) > 0:
            cols = list(test_result[0].keys())
            if 'Administration' in cols:
                print(f"   ⚠️  ISSUE: Returns uppercase 'Administration' column")
                if view_name not in [i['view'] for i in issues_found]:
                    issues_found.append({
                        'view': view_name,
                        'uppercase': 1,
                        'lowercase': 0,
                        'in_result': True
                    })
            elif 'administration' in cols:
                print(f"   ✅ OK: Returns lowercase 'administration' column")
                
    except Exception as e:
        print(f"   ❌ ERROR: {str(e)[:100]}")
        issues_found.append({
            'view': view_name,
            'error': str(e)
        })

# Summary
print("\n" + "=" * 60)
print("Summary")
print("=" * 60)

if issues_found:
    print(f"\n⚠️  Found {len(issues_found)} views with issues:\n")
    for issue in issues_found:
        print(f"   - {issue['view']}")
        if 'error' in issue:
            print(f"     Error: {issue['error'][:80]}")
        else:
            if issue.get('uppercase', 0) > 0:
                print(f"     Uses uppercase 'Administration' {issue['uppercase']} times")
            if issue.get('in_result'):
                print(f"     Returns uppercase column in results")
    
    print("\n" + "=" * 60)
    print("Action Required")
    print("=" * 60)
    print("\nRun these scripts to fix the issues:")
    for issue in issues_found:
        if 'error' not in issue:
            print(f"   - Fix {issue['view']}: Recreate view with lowercase 'administration'")
else:
    print("\n✅ All views are using lowercase 'administration' correctly!")
    print("\nMySQL Workbench should work without issues.")
    print("If you still see errors, try:")
    print("   1. Right-click schema → Refresh All")
    print("   2. Close and reopen MySQL Workbench")
