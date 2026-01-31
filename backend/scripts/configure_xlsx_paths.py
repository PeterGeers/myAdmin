"""
Configure XLSX Template and Output Paths

This script configures the template and output paths for financial report XLSX generation
in the tenant_template_config table.

Usage:
    python scripts/configure_xlsx_paths.py --administration GoodwinSolutions \
        --template-path "C:\\path\\to\\template.xlsx" \
        --output-path "C:\\path\\to\\output"
"""

import sys
import os
import json
import argparse

# Add parent directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from database import DatabaseManager


def configure_xlsx_paths(administration, template_path, output_path, test_mode=False):
    """
    Configure XLSX template and output paths for an administration.
    
    Args:
        administration: Administration/tenant name
        template_path: Full path to XLSX template file
        output_path: Full path to output base directory
        test_mode: Whether to use test database
    """
    db = DatabaseManager(test_mode=test_mode)
    
    # Validate paths
    if not os.path.exists(template_path):
        print(f"Warning: Template path does not exist: {template_path}")
        response = input("Continue anyway? (y/n): ")
        if response.lower() != 'y':
            print("Aborted.")
            return False
    
    if not os.path.exists(output_path):
        print(f"Output path does not exist: {output_path}")
        response = input("Create it? (y/n): ")
        if response.lower() == 'y':
            os.makedirs(output_path, exist_ok=True)
            print(f"Created: {output_path}")
        else:
            print("Aborted.")
            return False
    
    # Prepare field mappings JSON
    field_mappings = {
        "template_path": template_path,
        "output_base_path": output_path,
        "configured_date": str(os.popen('date /t').read().strip() if os.name == 'nt' else os.popen('date').read().strip())
    }
    
    field_mappings_json = json.dumps(field_mappings)
    
    # Check if configuration already exists
    query_check = """
        SELECT id FROM tenant_template_config
        WHERE administration = %s AND template_type = 'financial_report_xlsx'
    """
    existing = db.execute_query(query_check, (administration,))
    
    if existing:
        # Update existing configuration
        query_update = """
            UPDATE tenant_template_config
            SET field_mappings = %s,
                is_active = TRUE,
                updated_at = NOW()
            WHERE administration = %s AND template_type = 'financial_report_xlsx'
        """
        db.execute_update(query_update, (field_mappings_json, administration))
        print(f"✓ Updated configuration for {administration}")
    else:
        # Insert new configuration
        query_insert = """
            INSERT INTO tenant_template_config (
                administration,
                template_type,
                template_file_id,
                field_mappings,
                is_active
            ) VALUES (%s, %s, %s, %s, %s)
        """
        db.execute_update(
            query_insert,
            (administration, 'financial_report_xlsx', 'local_file', field_mappings_json, True)
        )
        print(f"✓ Created configuration for {administration}")
    
    # Display configuration
    print("\nConfiguration:")
    print(f"  Administration: {administration}")
    print(f"  Template Path:  {template_path}")
    print(f"  Output Path:    {output_path}")
    
    return True


def main():
    parser = argparse.ArgumentParser(description='Configure XLSX template and output paths')
    parser.add_argument('--administration', required=True, help='Administration/tenant name')
    parser.add_argument('--template-path', required=True, help='Full path to XLSX template file')
    parser.add_argument('--output-path', required=True, help='Full path to output base directory')
    parser.add_argument('--test-mode', action='store_true', help='Use test database')
    
    args = parser.parse_args()
    
    print("Configuring XLSX Paths")
    print("=" * 50)
    
    success = configure_xlsx_paths(
        administration=args.administration,
        template_path=args.template_path,
        output_path=args.output_path,
        test_mode=args.test_mode
    )
    
    if success:
        print("\n✓ Configuration complete!")
        print("\nThe XLSXExportProcessor will now use these paths for this administration.")
    else:
        print("\n✗ Configuration failed.")
        sys.exit(1)


if __name__ == '__main__':
    main()
