#!/usr/bin/env python3
"""
Carefully reorder tabs in myAdminReports.tsx
1. Update TabList order
2. Reorder TabPanels to match
"""

def reorder_tabs():
    file_path = 'frontend/src/components/myAdminReports.tsx'
    
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Step 1: Update TabList
    old_tablist = '''          <TabList>
            <Tab color="white">💰 Mutaties (P&L)</Tab>
            <Tab color="white">🏠 BNB Revenue</Tab>
            <Tab color="white">📊 Actuals</Tab>
            <Tab color="white">🏡 BNB Actuals</Tab>

            <Tab color="white">🧾 BTW aangifte</Tab>
            <Tab color="white">🏨 Toeristenbelasting</Tab>
            <Tab color="white">📈 View ReferenceNumber</Tab>
            <Tab color="white">🎻 BNB Violins</Tab>
            <Tab color="white">🔄 BNB Terugkerend</Tab>
            <Tab color="white">📈 BNB Future</Tab>
            <Tab color="white">📋 Aangifte IB</Tab>
          </TabList>'''
    
    new_tablist = '''          <TabList>
            {/* === BNB REPORTS === */}
            <Tab color="white">🏠 BNB Revenue</Tab>
            <Tab color="white">🏡 BNB Actuals</Tab>
            <Tab color="white">🎻 BNB Violins</Tab>
            <Tab color="white">🔄 BNB Terugkerend</Tab>
            <Tab color="white">📈 BNB Future</Tab>
            <Tab color="white">🏨 Toeristenbelasting</Tab>
            
            {/* === FINANCIAL REPORTS === */}
            <Tab color="white">💰 Mutaties (P&L)</Tab>
            <Tab color="white">📊 Actuals</Tab>
            <Tab color="white">🧾 BTW aangifte</Tab>
            <Tab color="white">📈 View ReferenceNumber</Tab>
            <Tab color="white">📋 Aangifte IB</Tab>
          </TabList>'''
    
    content = content.replace(old_tablist, new_tablist)
    
    # Step 2: Read file as lines for TabPanel reordering
    lines = content.split('\n')
    
    # Find TabPanels section
    tabpanels_start = None
    for i, line in enumerate(lines):
        if '<TabPanels>' in line and i > 1600:
            tabpanels_start = i
            break
    
    if not tabpanels_start:
        print("Error: Could not find TabPanels")
        return
    
    # Define sections by searching for their unique content markers
    # Format: (name, start_marker, approximate_line_offset)
    sections_info = [
        ('Mutaties', 'mutatiesFilters.dateFrom', 20),
        ('BNB Revenue', 'bnbFilters.dateFrom', 110),
        ('Actuals', 'actualsFilters', 300),
        ('BNB Actuals', 'bnbActualsFilters', 420),
        ('BTW', 'btwFilters.quarter', 140),
        ('Toeristenbelasting', 'toeristenbelastingData', 140),
        ('ReferenceNumber', 'refAnalysisFilters.referenceNumber', 220),
        ('BNB Violins', 'bnbViolinFilters.metric', 145),
        ('BNB Terugkerend', 'returningGuests', 120),
        ('BNB Future', 'bnbFutureData', 210),
        ('Aangifte IB', 'aangifteIbData', 370),
    ]
    
    # Extract each section
    sections = {}
    content_str = '\n'.join(lines)
    
    # Find each section by its marker
    import re
    
    # Find all TabPanel starts
    tabpanel_pattern = r'(\s*\{/\* .* Tab \*/\}\s*<TabPanel>.*?</TabPanel>)'
    matches = list(re.finditer(tabpanel_pattern, content_str, re.DOTALL))
    
    if len(matches) != 11:
        print(f"Warning: Found {len(matches)} TabPanels, expected 11")
    
    # Identify each section by its content
    for match in matches:
        section_content = match.group(1)
        for name, marker, _ in sections_info:
            if marker in section_content:
                sections[name] = section_content
                break
    
    if len(sections) != 11:
        print(f"Error: Could only identify {len(sections)} sections")
        print(f"Found: {list(sections.keys())}")
        return
    
    # New order
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
    
    # Find where TabPanels section starts and ends
    tabpanels_match = re.search(r'(<TabPanels>)(.*?)(</TabPanels>)', content_str, re.DOTALL)
    if not tabpanels_match:
        print("Error: Could not find TabPanels section")
        return
    
    before = content_str[:tabpanels_match.start(2)]
    after = content_str[tabpanels_match.end(2):]
    
    # Build new TabPanels content
    new_tabpanels_content = '\n'
    for name in new_order:
        if name in sections:
            new_tabpanels_content += sections[name] + '\n\n'
        else:
            print(f"Warning: Section '{name}' not found")
    
    # Reconstruct file
    new_content = before + new_tabpanels_content + after
    
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(new_content)
    
    print(f"✓ Reordered tabs in {file_path}")
    print(f"  TabList updated with grouped sections")
    print(f"  TabPanels reordered: {', '.join(new_order)}")

if __name__ == '__main__':
    reorder_tabs()
