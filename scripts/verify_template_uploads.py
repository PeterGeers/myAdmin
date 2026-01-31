#!/usr/bin/env python3
"""
Verify Template Uploads

This script verifies that templates were successfully uploaded to tenant Google Drives
and that metadata is correctly stored in the database.

Usage:
    python scripts/verify_template_uploads.py [--tenant TENANT_NAME]
"""

import sys
import os
from pathlib import Path

# Add backend/src to path
backend_src = Path(__file__).parent.parent / 'backend' / 'src'
sys.path.insert(0, str(backend_src))

from database import DatabaseManager
from google_drive_service import GoogleDriveService
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class TemplateVerifier:
    """Verifies template uploads"""
    
    def __init__(self, db: DatabaseManager):
        self.db = db
    
    def get_tenants_with_templates(self):
        """Get list of tenants that have templates configured"""
        query = """
            SELECT DISTINCT administration 
            FROM tenant_template_config
            ORDER BY administration
        """
        results = self.db.execute_query(query)
        return [r['administration'] for r in results]
    
    def get_template_metadata(self, administration: str = None):
        """Get template metadata from database"""
        if administration:
            query = """
                SELECT administration, template_type, template_file_id, is_active, 
                       created_at, updated_at
                FROM tenant_template_config
                WHERE administration = %s
                ORDER BY template_type
            """
            return self.db.execute_query(query, (administration,))
        else:
            query = """
                SELECT administration, template_type, template_file_id, is_active,
                       created_at, updated_at
                FROM tenant_template_config
                ORDER BY administration, template_type
            """
            return self.db.execute_query(query)
    
    def verify_file_exists(self, drive_service: GoogleDriveService, file_id: str):
        """Verify that a file exists in Google Drive"""
        try:
            file = drive_service.service.files().get(
                fileId=file_id,
                fields='id,name,webViewLink,mimeType'
            ).execute()
            
            return {
                'exists': True,
                'name': file.get('name'),
                'url': file.get('webViewLink'),
                'mime_type': file.get('mimeType')
            }
        except Exception as e:
            return {
                'exists': False,
                'error': str(e)
            }
    
    def verify_tenant_templates(self, administration: str):
        """Verify all templates for a tenant"""
        logger.info(f"\n{'='*80}")
        logger.info(f"Verifying templates for: {administration}")
        logger.info(f"{'='*80}")
        
        try:
            # Get template metadata from database
            templates = self.get_template_metadata(administration)
            
            if not templates:
                logger.warning(f"⚠️  No templates found for {administration}")
                return
            
            logger.info(f"Found {len(templates)} template(s) in database")
            
            # Initialize Google Drive service
            drive_service = GoogleDriveService(administration)
            logger.info(f"✅ Successfully authenticated Google Drive")
            
            # Verify each template
            all_verified = True
            
            for template in templates:
                template_type = template['template_type']
                file_id = template['template_file_id']
                is_active = template['is_active']
                
                logger.info(f"\n--- {template_type} ---")
                logger.info(f"   File ID: {file_id}")
                logger.info(f"   Active: {is_active}")
                logger.info(f"   Created: {template['created_at']}")
                logger.info(f"   Updated: {template['updated_at']}")
                
                # Verify file exists in Google Drive
                result = self.verify_file_exists(drive_service, file_id)
                
                if result['exists']:
                    logger.info(f"   ✅ File exists in Google Drive")
                    logger.info(f"      Name: {result['name']}")
                    logger.info(f"      Type: {result['mime_type']}")
                    logger.info(f"      URL: {result['url']}")
                else:
                    logger.error(f"   ❌ File NOT found in Google Drive")
                    logger.error(f"      Error: {result.get('error', 'Unknown error')}")
                    all_verified = False
            
            # Summary
            logger.info(f"\n{'='*80}")
            if all_verified:
                logger.info(f"✅ All templates verified successfully for {administration}")
            else:
                logger.error(f"❌ Some templates failed verification for {administration}")
            logger.info(f"{'='*80}")
            
            return all_verified
            
        except Exception as e:
            logger.error(f"❌ Error verifying templates for {administration}: {e}")
            return False
    
    def verify_all_tenants(self):
        """Verify templates for all tenants"""
        tenants = self.get_tenants_with_templates()
        
        if not tenants:
            logger.warning("⚠️  No tenants found with templates")
            return
        
        logger.info(f"Found {len(tenants)} tenant(s) with templates:")
        for tenant in tenants:
            logger.info(f"  - {tenant}")
        
        results = {}
        for tenant in tenants:
            results[tenant] = self.verify_tenant_templates(tenant)
        
        # Overall summary
        logger.info(f"\n{'='*80}")
        logger.info("OVERALL SUMMARY")
        logger.info(f"{'='*80}")
        
        success_count = sum(1 for v in results.values() if v)
        total_count = len(results)
        
        logger.info(f"Tenants verified: {total_count}")
        logger.info(f"  ✅ Successful: {success_count}")
        logger.info(f"  ❌ Failed: {total_count - success_count}")
        
        return results
    
    def print_database_summary(self):
        """Print a summary of all templates in the database"""
        logger.info(f"\n{'='*80}")
        logger.info("DATABASE SUMMARY")
        logger.info(f"{'='*80}")
        
        templates = self.get_template_metadata()
        
        if not templates:
            logger.warning("⚠️  No templates found in database")
            return
        
        logger.info(f"\nTotal templates: {len(templates)}\n")
        
        # Group by tenant
        by_tenant = {}
        for template in templates:
            admin = template['administration']
            if admin not in by_tenant:
                by_tenant[admin] = []
            by_tenant[admin].append(template)
        
        for admin, tenant_templates in by_tenant.items():
            logger.info(f"\n{admin} ({len(tenant_templates)} templates):")
            for template in tenant_templates:
                status = "✅ Active" if template['is_active'] else "⏸️  Inactive"
                logger.info(f"  {status} {template['template_type']}")
                logger.info(f"     File ID: {template['template_file_id']}")


def main():
    """Main entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Verify template uploads to tenant Google Drives'
    )
    parser.add_argument(
        '--tenant',
        type=str,
        help='Verify only this tenant (default: verify all tenants)'
    )
    parser.add_argument(
        '--summary-only',
        action='store_true',
        help='Only show database summary without verifying Google Drive'
    )
    
    args = parser.parse_args()
    
    # Initialize database
    db = DatabaseManager()
    verifier = TemplateVerifier(db)
    
    if args.summary_only:
        verifier.print_database_summary()
    elif args.tenant:
        logger.info(f"Verifying single tenant: {args.tenant}")
        verifier.verify_tenant_templates(args.tenant)
    else:
        logger.info("Verifying all tenants")
        verifier.verify_all_tenants()


if __name__ == '__main__':
    main()
