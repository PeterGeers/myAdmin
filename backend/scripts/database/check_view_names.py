#!/usr/bin/env python3
"""
Check database view naming conventions
"""
import sys
sys.path.append('src')
from database import DatabaseManager

def check_view_naming():
    db = DatabaseManager()
    
    print("Checking database view naming conventions...")
    print("=" * 50)
    
    # Get all views
    views = db.execute_query('SHOW FULL TABLES WHERE Table_type = "VIEW"')
    
    print(f"Found {len(views)} views:")
    
    naming_issues = []
    
    for view in views:
        view_name = view['Tables_in_finance']
        print(f"  - {view_name}")
        
        # Check naming convention issues
        if view_name != view_name.lower():
            naming_issues.append(f"View '{view_name}' contains uppercase letters")
        
        if '_' not in view_name and view_name.startswith('vw'):
            naming_issues.append(f"View '{view_name}' may need underscore separator")
    
    print("\n" + "=" * 50)
    
    if naming_issues:
        print("❌ Naming convention issues found:")
        for issue in naming_issues:
            print(f"  - {issue}")
    else:
        print("✅ All views follow consistent naming conventions")
    
    print("\n" + "=" * 50)
    print("Analysis complete")

if __name__ == "__main__":
    check_view_naming()