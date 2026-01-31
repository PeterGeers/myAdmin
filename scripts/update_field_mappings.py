#!/usr/bin/env python3
"""
Update Field Mappings in Database

This script reads field mapping JSON files and updates the tenant_template_config
table with the field mappings for each template type.

Usage:
    python scripts/update_field_mappings.py [--tenant TENANT_NAME] [--dry-run]
"""

import sys
import os
from pathlib import Path
import json

# Add backend/src to path
backend_src = Path(__file__).parent.parent / 'backend' / 'src'
sys.path.insert(0, str(backend_src))

from database import DatabaseManager
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class FieldMappingsUpdater:
    """Updates field mappings in tenant_template_config table"""
    
    # Mapping of template types to their field mapping files
    FIELD_MAPPING_FILES = {
        'aangifte_ib_html': 'backend/templates/html/aangifte_ib_field_mappings.json',
        'btw_aangifte_html': 'backend/templates/html/btw_aangifte_field_mappings.json',
        'str_invoice_nl': 'backend/templates/html/str_invoice_field_mappings.json',
        'str_invoice_en': 'backend/templates/html/str_invoice_field_mappings.json',
        'toeristenbelasting_html': 'backend/templates/html/toeristenbelasting_field_mappings.json',
        'financial_report_xlsx': 'backend/templates/xlsx/financial_report_field_mappings.json',
    }
    
    def __init__(self, db: DatabaseManager):
        self.db = db
        self.base_path = Path(__file__).parent.parent
    
    def get_tenants_with_templates(self):
        """Get list of tenants that have templates configured"""
        query = """
            SELECT DISTINCT administration 
            FROM tenant_template_config
            ORDER BY administration
        """
        results = self.db.execute_query(query)
        return [r['administration'] for r in results]
    
    def load_field_mappings(self, template_type: str) -> dict:
        """
        Load field mappings for a template type.
        
        Args:
            template_type: The template type (e.g., 'aangifte_ib_html')
            
        Returns:
            dict: Field mappings or None if not found
        """
        mapping_file = self.FIELD_MAPPING_FILES.get(template_type)
        if not mapping_file:
            logger.warning(f"No field mapping file defined for template type: {template_type}")
            return None
        
        mapping_path = self.base_path / mapping_file
        if not mapping_path.exists():
            logger.warning(f"Field mappings file not found: {mapping_path}")
            return None
        
        try:
            with open(mapping_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load field mappings from {mapping_path}: {e}")
            return None
    
    def update_field_mappings(self, administration: str, template_type: str, 
                             field_mappings: dict, dry_run: bool = False):
        """
        Update field mappings for a specific template.
        
        Args:
            administration: Tenant name
            template_type: Template type identifier
            field_mappings: Field mappings dictionary
            dry_run: If True, only show what would be updated
        """
        if dry_run:
            logger.info(f"   🔍 [DRY RUN] Would update field mappings for {template_type}")
            return
        
        # Convert field_mappings to JSON string
        mappings_json = json.dumps(field_mappings)
        
        # Update the database
        update_query = """
            UPDATE tenant_template_config 
            SET field_mappings = %s,
                updated_at = CURRENT_TIMESTAMP
            WHERE administration = %s AND template_type = %s
        """
        
        self.db.execute_query(
            update_query,
            (mappings_json, administration, template_type),
            fetch=False,
            commit=True
        )
        
        logger.info(f"   ✅ Updated field mappings for {template_type}")
    
    def process_tenant(self, administration: str, dry_run: bool = False):
        """
        Update field mappings for all templates of a tenant.
        
        Args:
            administration: Tenant name
            dry_run: If True, only show what would be updated
        """
        logger.info(f"\n{'='*80}")
        logger.info(f"Processing tenant: {administration}")
        logger.info(f"{'='*80}")
        
        # Get all templates for this tenant
        query = """
            SELECT template_type, field_mappings
            FROM tenant_template_config
            WHERE administration = %s
            ORDER BY template_type
        """
        templates = self.db.execute_query(query, (administration,))
        
        if not templates:
            logger.warning(f"No templates found for {administration}")
            return
        
        logger.info(f"Found {len(templates)} template(s)")
        
        updated_count = 0
        skipped_count = 0
        error_count = 0
        
        for template in templates:
            template_type = template['template_type']
            current_mappings = template['field_mappings']
            
            logger.info(f"\n--- Processing: {template_type} ---")
            
            # Check if mappings already exist
            if current_mappings:
                logger.info(f"   ℹ️  Field mappings already exist (will be overwritten)")
            else:
                logger.info(f"   ℹ️  No field mappings currently set")
            
            # Load field mappings from file
            field_mappings = self.load_field_mappings(template_type)
            
            if not field_mappings:
                logger.warning(f"   ⚠️  No field mappings file found, skipping")
                skipped_count += 1
                continue
            
            try:
                # Update the database
                self.update_field_mappings(
                    administration,
                    template_type,
                    field_mappings,
                    dry_run
                )
                updated_count += 1
            except Exception as e:
                logger.error(f"   ❌ Failed to update: {e}")
                error_count += 1
        
        # Summary
        logger.info(f"\n{'='*80}")
        logger.info(f"Summary for {administration}")
        logger.info(f"{'='*80}")
        logger.info(f"Templates processed: {len(templates)}")
        logger.info(f"  ✅ Updated: {updated_count}")
        logger.info(f"  ⚠️  Skipped: {skipped_count}")
        logger.info(f"  ❌ Errors: {error_count}")
    
    def process_all_tenants(self, dry_run: bool = False):
        """Process all tenants with templates"""
        tenants = self.get_tenants_with_templates()
        
        if not tenants:
            logger.warning("⚠️  No tenants found with templates")
            return
        
        logger.info(f"Found {len(tenants)} tenant(s) with templates:")
        for tenant in tenants:
            logger.info(f"  - {tenant}")
        
        for tenant in tenants:
            try:
                self.process_tenant(tenant, dry_run)
            except Exception as e:
                logger.error(f"Failed to process {tenant}: {e}")
        
        logger.info(f"\n{'='*80}")
        logger.info("✅ All tenants processed")
        logger.info(f"{'='*80}")


def main():
    """Main entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Update field mappings in tenant_template_config table'
    )
    parser.add_argument(
        '--tenant',
        type=str,
        help='Process only this tenant (default: process all tenants)'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would be updated without actually updating'
    )
    
    args = parser.parse_args()
    
    # Initialize database
    db = DatabaseManager()
    updater = FieldMappingsUpdater(db)
    
    # Process tenant(s)
    if args.tenant:
        logger.info(f"Processing single tenant: {args.tenant}")
        updater.process_tenant(args.tenant, dry_run=args.dry_run)
    else:
        logger.info("Processing all tenants with templates")
        updater.process_all_tenants(dry_run=args.dry_run)


if __name__ == '__main__':
    main()
