"""Debug which row is different."""

from pathlib import Path
import re

def extract_rows_detailed(html_content):
    """Extract detailed row information."""
    rows = re.findall(r'<tr class="([^"]+)">(.*?)</tr>', html_content, re.DOTALL)
    
    data = []
    for css_class, row_content in rows:
        cells = re.findall(r'<td[^>]*>(.*?)</td>', row_content)
        # Clean up cells
        cells = [c.strip() for c in cells]
        data.append({
            'class': css_class,
            'parent': cells[0] if len(cells) > 0 else '',
            'aangifte': cells[1] if len(cells) > 1 else '',
            'description': cells[2] if len(cells) > 2 else '',
            'amount': cells[3] if len(cells) > 3 else ''
        })
    
    return data

output_dir = Path(__file__).parent / 'templates' / 'xml'
expected = output_dir / 'Aangifte_IB_GoodwinSolutions_2025.html'
actual = output_dir / 'Aangifte_IB_GoodwinSolutions_2025_test.html'

with open(expected, 'r', encoding='utf-8') as f:
    expected_content = f.read()

with open(actual, 'r', encoding='utf-8') as f:
    actual_content = f.read()

expected_rows = extract_rows_detailed(expected_content)
actual_rows = extract_rows_detailed(actual_content)

print(f"Expected: {len(expected_rows)} rows")
print(f"Actual: {len(actual_rows)} rows")
print()

# Find differences
print("Expected rows:")
for i, row in enumerate(expected_rows):
    print(f"{i+1:2d}. [{row['class']:20s}] {row['parent']:10s} | {row['aangifte']:30s} | {row['amount']:15s}")

print("\n" + "="*100 + "\n")

print("Actual rows:")
for i, row in enumerate(actual_rows):
    print(f"{i+1:2d}. [{row['class']:20s}] {row['parent']:10s} | {row['aangifte']:30s} | {row['amount']:15s}")
