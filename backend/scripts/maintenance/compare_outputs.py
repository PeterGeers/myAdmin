"""Compare generated output with expected output."""

from pathlib import Path
import re

def extract_table_data(html_content):
    """Extract table row data from HTML, ignoring formatting."""
    # Find all table rows
    rows = re.findall(r'<tr class="([^"]+)">(.*?)</tr>', html_content, re.DOTALL)
    
    data = []
    for css_class, row_content in rows:
        # Extract cell contents
        cells = re.findall(r'<td[^>]*>(.*?)</td>', row_content)
        data.append({
            'class': css_class,
            'cells': cells
        })
    
    return data

def compare_files(expected_file, actual_file):
    """Compare two HTML files, ignoring formatting differences."""
    print(f"\nComparing:")
    print(f"  Expected: {expected_file.name}")
    print(f"  Actual:   {actual_file.name}")
    print("-" * 80)
    
    with open(expected_file, 'r', encoding='utf-8') as f:
        expected_content = f.read()
    
    with open(actual_file, 'r', encoding='utf-8') as f:
        actual_content = f.read()
    
    # Extract table data
    expected_data = extract_table_data(expected_content)
    actual_data = extract_table_data(actual_content)
    
    print(f"\nRow counts:")
    print(f"  Expected: {len(expected_data)} rows")
    print(f"  Actual:   {len(actual_data)} rows")
    
    if len(expected_data) != len(actual_data):
        print(f"\n⚠ Row count mismatch!")
        return False
    
    # Compare each row
    mismatches = []
    for i, (exp, act) in enumerate(zip(expected_data, actual_data)):
        if exp['class'] != act['class']:
            mismatches.append(f"Row {i+1}: Class mismatch - expected '{exp['class']}', got '{act['class']}'")
        
        if exp['cells'] != act['cells']:
            mismatches.append(f"Row {i+1}: Cell content mismatch")
            mismatches.append(f"  Expected: {exp['cells']}")
            mismatches.append(f"  Actual:   {act['cells']}")
    
    if mismatches:
        print(f"\n✗ Found {len(mismatches)} mismatches:")
        for mismatch in mismatches[:10]:  # Show first 10
            print(f"  {mismatch}")
        if len(mismatches) > 10:
            print(f"  ... and {len(mismatches) - 10} more")
        return False
    else:
        print(f"\n✓ All {len(expected_data)} rows match perfectly!")
        print(f"  - Row classes match")
        print(f"  - Cell contents match")
        print(f"  - Amounts match")
        return True

def main():
    """Main comparison."""
    output_dir = Path(__file__).parent / 'templates' / 'xml'
    
    # Compare GoodwinSolutions
    expected = output_dir / 'Aangifte_IB_GoodwinSolutions_2025.html'
    actual = output_dir / 'Aangifte_IB_GoodwinSolutions_2025_test.html'
    
    if expected.exists() and actual.exists():
        result = compare_files(expected, actual)
        if result:
            print("\n" + "="*80)
            print("✓ SUCCESS: Generated output matches expected output exactly!")
            print("="*80)
            return True
        else:
            print("\n" + "="*80)
            print("✗ FAILURE: Generated output differs from expected output")
            print("="*80)
            return False
    else:
        print(f"\n✗ Files not found:")
        print(f"  Expected exists: {expected.exists()}")
        print(f"  Actual exists: {actual.exists()}")
        return False

if __name__ == '__main__':
    import sys
    success = main()
    sys.exit(0 if success else 1)
