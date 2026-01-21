#!/usr/bin/env python3
"""
Reorder TabPanels in myAdminReports.tsx to match the new tab order
"""

def reorder_tabpanels():
    file_path = 'frontend/src/components/myAdminReports.tsx'
    
    with open(file_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    # Tab sections with line numbers (0-indexed)
    sections = {
        'Mutaties': (1618, 1728),
        'BNB Revenue': (1728, 1927),
        'Actuals': (1927, 2247),
        'BNB Actuals': (2247, 2644),
        'BTW': (2644, 2786),
        'Toeristenbelasting': (2786, 2925),
        'ReferenceNumber': (2925, 3148),
        'BNB Violins': (3148, 3292),
        'BNB Terugkerend': (3292, 3414),
        'BNB Future': (3414, 3625),
        'Aangifte IB': (3625, 3995),
    }
    
    # New order matching the TabList
    new_order = [
        'BNB Revenue',
        'BNB Actuals',
        'BNB Violins',
        'BNB Terugkerend',
        'BNB Future',
        'Toeristenbelasting',
        'Mutaties',
        'Actuals',
        'BTW',
        'ReferenceNumber',
        'Aangifte IB',
    ]
    
    # Extract sections
    extracted = {}
    for name, (start, end) in sections.items():
        extracted[name] = lines[start:end+1]
    
    # Build new file
    new_lines = lines[:1618]  # Everything before TabPanels
    
    # Add sections in new order
    for name in new_order:
        new_lines.extend(extracted[name])
    
    # Add everything after TabPanels
    new_lines.extend(lines[3996:])
    
    # Write back
    with open(file_path, 'w', encoding='utf-8') as f:
        f.writelines(new_lines)
    
    print(f"✓ Reordered TabPanels in {file_path}")
    print(f"  New order: {', '.join(new_order)}")

if __name__ == '__main__':
    reorder_tabpanels()
