"""
Verify that the generated Aangifte IB output matches the expected format structure.

This script checks:
1. HTML structure is valid
2. All required CSS classes are present
3. Table hierarchy is correct (parent → aangifte → account)
4. Amounts are properly formatted
5. All required sections are present
"""

import re
from pathlib import Path
from html.parser import HTMLParser


class AangifteIBValidator(HTMLParser):
    """HTML parser to validate Aangifte IB report structure."""
    
    def __init__(self):
        super().__init__()
        self.errors = []
        self.warnings = []
        self.in_tbody = False
        self.row_count = 0
        self.row_types = {
            'parent-row': 0,
            'aangifte-row': 0,
            'account-row': 0,
            'resultaat-positive': 0,
            'resultaat-negative': 0,
            'grand-total': 0
        }
        self.current_row_class = None
        self.current_td_count = 0
        self.has_title = False
        self.has_table = False
        
    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        
        if tag == 'title':
            self.has_title = True
        
        if tag == 'table':
            self.has_table = True
        
        if tag == 'tbody':
            self.in_tbody = True
        
        if tag == 'tr' and self.in_tbody:
            self.row_count += 1
            self.current_td_count = 0
            
            # Check for class attribute
            if 'class' in attrs_dict:
                row_class = attrs_dict['class']
                self.current_row_class = row_class
                
                if row_class in self.row_types:
                    self.row_types[row_class] += 1
                else:
                    self.warnings.append(f"Unknown row class: {row_class}")
            else:
                self.errors.append(f"Row {self.row_count} missing class attribute")
        
        if tag == 'td' and self.in_tbody:
            self.current_td_count += 1
    
    def handle_endtag(self, tag):
        if tag == 'tbody':
            self.in_tbody = False
        
        if tag == 'tr' and self.current_row_class:
            # Verify each row has 4 columns
            if self.current_td_count != 4:
                self.errors.append(
                    f"Row with class '{self.current_row_class}' has {self.current_td_count} columns, expected 4"
                )
            self.current_row_class = None
    
    def validate(self):
        """Run validation checks and return results."""
        results = {
            'valid': len(self.errors) == 0,
            'errors': self.errors,
            'warnings': self.warnings,
            'stats': {
                'total_rows': self.row_count,
                'row_types': self.row_types,
                'has_title': self.has_title,
                'has_table': self.has_table
            }
        }
        
        # Check required elements
        if not self.has_title:
            results['errors'].append("Missing <title> tag")
        
        if not self.has_table:
            results['errors'].append("Missing <table> tag")
        
        # Check row type requirements
        if self.row_types['parent-row'] == 0:
            results['errors'].append("No parent rows found")
        
        if self.row_types['aangifte-row'] == 0:
            results['errors'].append("No aangifte rows found")
        
        if self.row_types['grand-total'] == 0:
            results['warnings'].append("No grand total row found")
        
        # Update valid status
        results['valid'] = len(results['errors']) == 0
        
        return results


def validate_html_file(file_path):
    """Validate an Aangifte IB HTML file."""
    print(f"\nValidating: {file_path.name}")
    print("=" * 80)
    
    # Read file
    with open(file_path, 'r', encoding='utf-8') as f:
        html_content = f.read()
    
    # Parse and validate
    validator = AangifteIBValidator()
    validator.feed(html_content)
    results = validator.validate()
    
    # Print results
    print(f"\n✓ Total rows: {results['stats']['total_rows']}")
    print(f"\nRow type breakdown:")
    for row_type, count in sorted(results['stats']['row_types'].items()):
        if count > 0:
            print(f"  - {row_type}: {count}")
    
    if results['errors']:
        print(f"\n✗ Errors ({len(results['errors'])}):")
        for error in results['errors']:
            print(f"  - {error}")
    else:
        print(f"\n✓ No errors found")
    
    if results['warnings']:
        print(f"\n⚠ Warnings ({len(results['warnings'])}):")
        for warning in results['warnings']:
            print(f"  - {warning}")
    
    # Check amount formatting
    print(f"\n[Amount Formatting Check]")
    amount_pattern = r'<td class="amount">([^<]+)</td>'
    amounts = re.findall(amount_pattern, html_content)
    
    invalid_amounts = []
    for amount in amounts:
        # Check if amount matches expected format: -?[\d,]+\.\d{2}
        if not re.match(r'^-?[\d,]+\.\d{2}$', amount):
            invalid_amounts.append(amount)
    
    if invalid_amounts:
        print(f"  ⚠ Found {len(invalid_amounts)} amounts with unexpected format:")
        for amt in invalid_amounts[:5]:  # Show first 5
            print(f"    - {amt}")
    else:
        print(f"  ✓ All {len(amounts)} amounts properly formatted")
    
    # Check CSS classes
    print(f"\n[CSS Classes Check]")
    required_classes = [
        'parent-row', 'aangifte-row', 'account-row',
        'amount', 'indent-1', 'indent-2'
    ]
    
    missing_classes = []
    for css_class in required_classes:
        if css_class not in html_content:
            missing_classes.append(css_class)
    
    if missing_classes:
        print(f"  ⚠ Missing CSS classes: {', '.join(missing_classes)}")
    else:
        print(f"  ✓ All required CSS classes present")
    
    # Overall result
    print(f"\n{'='*80}")
    if results['valid'] and not invalid_amounts and not missing_classes:
        print("✓ VALIDATION PASSED")
        return True
    else:
        print("✗ VALIDATION FAILED")
        return False


def main():
    """Main validation execution."""
    print("\n" + "="*80)
    print("Aangifte IB Format Validation")
    print("="*80)
    
    # Find test output files
    output_dir = Path(__file__).parent / 'templates' / 'xml'
    test_files = list(output_dir.glob('Aangifte_IB_*_test.html'))
    
    if not test_files:
        print("\n✗ No test output files found")
        print(f"  Expected files matching: {output_dir}/Aangifte_IB_*_test.html")
        return False
    
    print(f"\nFound {len(test_files)} test output files")
    
    # Validate each file
    results = []
    for test_file in sorted(test_files):
        result = validate_html_file(test_file)
        results.append({
            'file': test_file.name,
            'valid': result
        })
    
    # Summary
    print(f"\n{'='*80}")
    print("Validation Summary")
    print(f"{'='*80}")
    
    passed = [r for r in results if r['valid']]
    failed = [r for r in results if not r['valid']]
    
    print(f"\nTotal files: {len(results)}")
    print(f"Passed: {len(passed)}")
    print(f"Failed: {len(failed)}")
    
    if passed:
        print(f"\n✓ Passed:")
        for result in passed:
            print(f"  - {result['file']}")
    
    if failed:
        print(f"\n✗ Failed:")
        for result in failed:
            print(f"  - {result['file']}")
    
    return len(failed) == 0


if __name__ == '__main__':
    import sys
    success = main()
    sys.exit(0 if success else 1)
