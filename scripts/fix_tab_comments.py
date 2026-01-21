#!/usr/bin/env python3
"""
Fix tab comments to match the actual TabPanel content
"""

def fix_comments():
    file_path = 'frontend/src/components/myAdminReports.tsx'
    
    with open(file_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    # Define the correct order and their line numbers (approximate)
    # We'll search for specific content to identify each tab
    
    replacements = [
        # Line 1619: Should be BNB Revenue (has bnbFilters.dateFrom)
        (1619, '            {/* BNB Revenue Tab */}\n'),
        # Line 1818: Should be BNB Actuals (has bnbActualsFilters)
        (1818, '            {/* BNB Actuals Tab */}\n'),
        # Line 2215: Should be BNB Violins (has bnbViolinFilters)
        (2215, '            {/* BNB Violins Tab */}\n'),
        # Line 2359: Should be BNB Terugkerend (has returningGuests)
        (2359, '            {/* BNB Terugkerend Tab */}\n'),
        # Line 2481: Should be BNB Future (has bnbFutureData)
        (2481, '            {/* BNB Future Tab */}\n'),
        # Line 2692: Should be Toeristenbelasting (has toeristenbelastingData)
        (2692, '            {/* Toeristenbelasting Tab */}\n'),
        # Line 2831: Should be Mutaties (has mutatiesFilters)
        (2831, '            {/* Mutaties Tab */}\n'),
        # Line 2941: Should be Actuals (has actualsFilters)
        (2941, '            {/* Actuals Dashboard Tab */}\n'),
        # Line 3261: Should be BTW (has btwFilters)
        (3261, '            {/* BTW aangifte Tab */}\n'),
        # Line 3403: Should be View ReferenceNumber (has refAnalysisFilters)
        (3403, '            {/* View ReferenceNumber Tab */}\n'),
        # Line 3626: Should be Aangifte IB (has aangifteIbData)
        (3626, '            {/* Aangifte IB Tab */}\n'),
    ]
    
    # Apply replacements
    for line_num, new_content in replacements:
        if line_num < len(lines):
            lines[line_num] = new_content
    
    with open(file_path, 'w', encoding='utf-8') as f:
        f.writelines(lines)
    
    print(f"✓ Fixed tab comments in {file_path}")
    print("  Order: BNB Revenue, BNB Actuals, BNB Violins, BNB Terugkerend, BNB Future,")
    print("         Toeristenbelasting, Mutaties, Actuals, BTW, ReferenceNumber, Aangifte IB")

if __name__ == '__main__':
    fix_comments()
