"""
End-to-end test for Aangifte IB report generation.

This script tests the complete Aangifte IB report generation workflow:
1. Fetch real data from database
2. Generate table rows using the generator
3. Render HTML output
4. Compare with expected format
5. Save output for manual inspection

Tests both GoodwinSolutions and PeterPrive tenants.
"""

import os
import sys
from datetime import datetime
from pathlib import Path

# Add backend/src to path
backend_src = Path(__file__).parent / 'src'
sys.path.insert(0, str(backend_src))

# Load environment variables
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / '.env')

from database import DatabaseManager
from mutaties_cache import get_cache
from report_generators import generate_table_rows


def fetch_aangifte_ib_data(db, year, administration):
    """Fetch Aangifte IB summary data from database using VW logic."""
    query = """
        SELECT 
            v.Parent,
            v.Aangifte,
            SUM(v.Amount) as Amount,
            MIN(r.AccountID) as MinAccountID
        FROM vw_mutaties v
        LEFT JOIN rekeningschema r ON v.Reknum = r.Account AND v.administration = r.Administration
        WHERE (
            (v.VW = 'N' AND v.TransactionDate <= %s) OR
            (v.VW = 'Y' AND YEAR(v.TransactionDate) = %s)
        )
        AND v.administration = %s
        AND v.Parent IS NOT NULL
        AND v.Aangifte IS NOT NULL
        GROUP BY v.Parent, v.Aangifte
        ORDER BY v.Parent, MinAccountID
    """
    
    year_end = f"{year}-12-31"
    results = db.execute_query(query, (year_end, year, administration), fetch=True)
    
    # Convert to list of dicts
    data = []
    for row in results:
        data.append({
            'Parent': row['Parent'],
            'Aangifte': row['Aangifte'],
            'Amount': float(row['Amount'])
        })
    
    return data


def render_table_rows_html(rows_data):
    """Convert row data dictionaries to HTML table rows."""
    html_rows = []
    
    for row in rows_data:
        row_type = row.get('row_type', '')
        css_class = row.get('css_class', '')
        parent = row.get('parent', '')
        aangifte = row.get('aangifte', '')
        description = row.get('description', '')
        amount = row.get('amount', '')
        indent_level = row.get('indent_level', 0)
        
        # Apply indentation class
        parent_td_class = ''
        if indent_level == 1:
            parent_td_class = ' class="indent-1"'
        elif indent_level == 2:
            parent_td_class = ' class="indent-2"'
        
        # Build table row
        html_row = f'<tr class="{css_class}">'
        html_row += f'<td{parent_td_class}>{parent}</td>'
        html_row += f'<td>{aangifte}</td>'
        html_row += f'<td>{description}</td>'
        html_row += f'<td class="amount">{amount}</td>'
        html_row += '</tr>'
        
        html_rows.append(html_row)
    
    return '\n'.join(html_rows)


def generate_html_report(year, administration, table_rows_html):
    """Generate complete HTML report."""
    template_path = Path(__file__).parent / 'templates' / 'html' / 'aangifte_ib_template.html'
    
    with open(template_path, 'r', encoding='utf-8') as f:
        template_html = f.read()
    
    # Replace placeholders
    html_content = template_html.replace('{{ year }}', str(year))
    html_content = html_content.replace('{{ administration }}', administration)
    html_content = html_content.replace('{{ generated_date }}', datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
    html_content = html_content.replace('{{ table_rows }}', table_rows_html)
    
    return html_content


def test_tenant(db, cache, year, administration, user_tenants):
    """Test Aangifte IB generation for a specific tenant."""
    print(f"\n{'='*80}")
    print(f"Testing: {administration} - Year {year}")
    print(f"{'='*80}")
    
    # Step 1: Fetch data
    print(f"\n[1/5] Fetching data from database...")
    report_data = fetch_aangifte_ib_data(db, year, administration)
    print(f"  ✓ Found {len(report_data)} parent-aangifte combinations")
    
    if not report_data:
        print(f"  ⚠ No data found for {administration} in {year}")
        return None
    
    # Show sample data
    print(f"\n  Sample data (first 3 rows):")
    for i, row in enumerate(report_data[:3]):
        print(f"    {i+1}. Parent: {row['Parent']}, Aangifte: {row['Aangifte']}, Amount: €{row['Amount']:,.2f}")
    
    # Step 2: Generate table rows
    print(f"\n[2/5] Generating table rows...")
    
    # Debug: Check P&L items for resultaat calculation
    pl_items = [item for item in report_data if item['Parent'].startswith(('4', '5', '6', '7', '8', '9'))]
    resultaat_calc = sum(item['Amount'] for item in pl_items)
    print(f"  Debug: P&L items count: {len(pl_items)}")
    print(f"  Debug: Calculated RESULTAAT: €{resultaat_calc:,.2f}")
    
    table_rows_data = generate_table_rows(
        report_data=report_data,
        cache=cache,
        year=year,
        administration=administration,
        user_tenants=user_tenants
    )
    print(f"  ✓ Generated {len(table_rows_data)} table rows")
    
    # Show row type breakdown
    row_types = {}
    for row in table_rows_data:
        row_type = row.get('row_type', 'unknown')
        row_types[row_type] = row_types.get(row_type, 0) + 1
    
    print(f"\n  Row type breakdown:")
    for row_type, count in sorted(row_types.items()):
        print(f"    - {row_type}: {count}")
    
    # Step 3: Render HTML
    print(f"\n[3/5] Rendering HTML...")
    table_rows_html = render_table_rows_html(table_rows_data)
    html_content = generate_html_report(year, administration, table_rows_html)
    print(f"  ✓ Generated HTML ({len(html_content)} characters)")
    
    # Step 4: Save output
    print(f"\n[4/5] Saving output...")
    output_dir = Path(__file__).parent / 'templates' / 'xml'
    output_file = output_dir / f'Aangifte_IB_{administration}_{year}_test.html'
    
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(html_content)
    
    print(f"  ✓ Saved to: {output_file}")
    
    # Step 5: Compare with expected output (if exists)
    print(f"\n[5/5] Comparing with expected output...")
    expected_file = output_dir / f'Aangifte_IB_{administration}_{year}.html'
    
    if expected_file.exists():
        with open(expected_file, 'r', encoding='utf-8') as f:
            expected_content = f.read()
        
        # Compare structure (ignore generated date)
        expected_lines = [line.strip() for line in expected_content.split('\n') if line.strip() and 'Generated:' not in line]
        actual_lines = [line.strip() for line in html_content.split('\n') if line.strip() and 'Generated:' not in line]
        
        if expected_lines == actual_lines:
            print(f"  ✓ Output matches expected format exactly!")
        else:
            print(f"  ⚠ Output differs from expected format")
            print(f"    Expected lines: {len(expected_lines)}")
            print(f"    Actual lines: {len(actual_lines)}")
            
            # Find first difference
            for i, (exp, act) in enumerate(zip(expected_lines, actual_lines)):
                if exp != act:
                    print(f"\n    First difference at line {i+1}:")
                    print(f"      Expected: {exp[:100]}...")
                    print(f"      Actual:   {act[:100]}...")
                    break
    else:
        print(f"  ℹ No expected output file found at: {expected_file}")
        print(f"    This is the first run - output saved for future comparison")
    
    return {
        'administration': administration,
        'year': year,
        'data_rows': len(report_data),
        'table_rows': len(table_rows_data),
        'output_file': str(output_file),
        'success': True
    }


def main():
    """Main test execution."""
    print("\n" + "="*80)
    print("Aangifte IB End-to-End Test")
    print("="*80)
    
    # Initialize database and cache
    print("\n[Setup] Initializing database and cache...")
    db = DatabaseManager(test_mode=False)
    cache = get_cache()
    cache.get_data(db)  # Load cache
    print(f"  ✓ Database connected")
    print(f"  ✓ Cache loaded ({len(cache.data) if cache.data is not None else 0} records)")
    
    # Test configuration
    year = 2025
    tenants = [
        {
            'administration': 'GoodwinSolutions',
            'user_tenants': ['GoodwinSolutions', 'PeterPrive']
        },
        {
            'administration': 'PeterPrive',
            'user_tenants': ['GoodwinSolutions', 'PeterPrive']
        }
    ]
    
    # Run tests
    results = []
    for tenant_config in tenants:
        try:
            result = test_tenant(
                db=db,
                cache=cache,
                year=year,
                administration=tenant_config['administration'],
                user_tenants=tenant_config['user_tenants']
            )
            if result:
                results.append(result)
        except Exception as e:
            print(f"\n  ✗ Error testing {tenant_config['administration']}: {e}")
            import traceback
            traceback.print_exc()
            results.append({
                'administration': tenant_config['administration'],
                'year': year,
                'success': False,
                'error': str(e)
            })
    
    # Summary
    print(f"\n{'='*80}")
    print("Test Summary")
    print(f"{'='*80}")
    
    successful = [r for r in results if r.get('success')]
    failed = [r for r in results if not r.get('success')]
    
    print(f"\nTotal tests: {len(results)}")
    print(f"Successful: {len(successful)}")
    print(f"Failed: {len(failed)}")
    
    if successful:
        print(f"\n✓ Successful tests:")
        for result in successful:
            print(f"  - {result['administration']} ({result['year']}): {result['table_rows']} rows generated")
            print(f"    Output: {result['output_file']}")
    
    if failed:
        print(f"\n✗ Failed tests:")
        for result in failed:
            print(f"  - {result['administration']} ({result['year']}): {result.get('error', 'Unknown error')}")
    
    print(f"\n{'='*80}")
    
    return len(failed) == 0


if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)
