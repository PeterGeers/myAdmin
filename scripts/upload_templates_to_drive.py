#!/usr/bin/env python3
"""
Upload Templates to Tenant Google Drives

This script uploads HTML, XLSX, and other templates to each tenant's Google Drive
Templates folder. It stores the template metadata in the tenant_template_config table.

Usage:
    python scripts/upload_templates_to_drive.py [--tenant TENANT_NAME] [--dry-run]
    
    If --tenant is not specified, it will process all tenants with credentials.
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
import json

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class TemplateUploader:
    """Uploads templates to tenant Google Drives"""
    
    # Templates to upload for each tenant
    # Format: (local_path, template_type, mime_type, description)
    TEMPLATES = [
        # HTML Templates
        ('backend/templates/html/aangifte_ib_template.html', 'aangifte_ib_html', 'text/html', 
         'Aangifte IB HTML Report Template'),
        ('backend/templates/html/btw_aangifte_template.html', 'btw_aangifte_html', 'text/html',
         'BTW Aangifte HTML Report Template'),
        ('backend/templates/html/toeristenbelasting_template.html', 'toeristenbelasting_html', 'text/html',
         'Toeristenbelasting HTML Report Template'),
        ('backend/templates/html/str_invoice_nl_template.html', 'str_invoice_nl', 'text/html',
         'STR Invoice Template (Dutch)'),
        ('backend/templates/html/str_invoice_en_template.html', 'str_invoice_en', 'text/html',
         'STR Invoice Template (English)'),
        
        # XLSX Templates
        ('backend/templates/xlsx/template.xlsx', 'financial_report_xlsx', 
         'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
         'Financial Report Excel Template'),
    ]
    
    def __init__(self, db: DatabaseManager):
        self.db = db
        self.base_path = Path(__file__).parent.parent
    
    def get_tenants_with_credentials(self):
        """Get list of tenants that have Google Drive credentials"""
        query = """
            SELECT DISTINCT administration 
            FROM tenant_credentials 
            WHERE credential_type = 'google_drive_oauth'
        """
        results = self.db.execute_query(query)
        return [r['administration'] for r in results]
    
    def get_templates_folder_id(self, administration: str) -> str:
        """Get the Templates folder ID for a tenant from tenant_config"""
        query = """
            SELECT config_value 
            FROM tenant_config 
            WHERE administration = %s AND config_key = 'google_drive_templates_folder_id'
        """
        results = self.db.execute_query(query, (administration,))
        
        if results and results[0]['config_value']:
            return results[0]['config_value']
        
        raise Exception(
            f"Templates folder ID not found for {administration}. "
            "Please run create_template_folders.py first."
        )
    
    def load_field_mappings(self, template_type: str) -> dict:
        """
        Load field mappings for a template type if they exist.
        
        Args:
            template_type: The template type (e.g., 'aangifte_ib_html')
            
        Returns:
            dict: Field mappings or empty dict if not found
        """
        # Map template types to their field mapping files
        mapping_files = {
            'aangifte_ib_html': 'backend/templates/html/aangifte_ib_field_mappings.json',
        }
        
        mapping_file = mapping_files.get(template_type)
        if not mapping_file:
            return {}
        
        mapping_path = self.base_path / mapping_file
        if not mapping_path.exists():
            logger.warning(f"Field mappings file not found: {mapping_path}")
            return {}
        
        try:
            with open(mapping_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Failed to load field mappings from {mapping_path}: {e}")
            return {}
    
    def upload_template(self, drive_service: GoogleDriveService, 
                       local_path: str, template_type: str, 
                       mime_type: str, folder_id: str, 
                       dry_run: bool = False) -> dict:
        """
        Upload a single template file to Google Drive.
        
        Args:
            drive_service: GoogleDriveService instance
            local_path: Path to local template file
            template_type: Template type identifier
            mime_type: MIME type of the file
            folder_id: Google Drive folder ID to upload to
            dry_run: If True, only check without uploading
            
        Returns:
            dict: Upload result with file_id and url
        """
        full_path = self.base_path / local_path
        
        if not full_path.exists():
            raise FileNotFoundError(f"Template file not found: {full_path}")
        
        filename = full_path.name
        
        # Check if file already exists
        check_result = drive_service.check_file_exists(filename, folder_id)
        
        if check_result['exists']:
            file_info = check_result['file']
            logger.info(f"   ✅ Template '{filename}' already exists")
            logger.info(f"      ID: {file_info['id']}")
            logger.info(f"      URL: {file_info['url']}")
            return file_info
        
        if dry_run:
            logger.info(f"   🔍 [DRY RUN] Would upload: {filename}")
            return {'id': 'DRY_RUN', 'name': filename, 'url': 'N/A'}
        
        # Upload the file
        logger.info(f"   📤 Uploading: {filename}")
        
        if mime_type == 'text/html':
            # For HTML files, read content and upload as text
            with open(full_path, 'r', encoding='utf-8') as f:
                content = f.read()
            file_info = drive_service.upload_text_file(content, filename, folder_id, mime_type)
        else:
            # For binary files (XLSX, etc.), upload as file
            file_info = drive_service.upload_file(str(full_path), filename, folder_id)
        
        logger.info(f"   ✅ Uploaded: {filename}")
        logger.info(f"      ID: {file_info['id']}")
        logger.info(f"      URL: {file_info['url']}")
        
        return file_info
    
    def store_template_metadata(self, administration: str, template_type: str,
                                file_id: str, description: str, field_mappings: dict = None):
        """Store template metadata in tenant_template_config table"""
        
        # Check if template config already exists
        check_query = """
            SELECT id FROM tenant_template_config 
            WHERE administration = %s AND template_type = %s
        """
        existing = self.db.execute_query(check_query, (administration, template_type))
        
        # Convert field_mappings to JSON string
        mappings_json = json.dumps(field_mappings) if field_mappings else None
        
        if existing:
            # Update existing
            update_query = """
                UPDATE tenant_template_config 
                SET template_file_id = %s,
                    field_mappings = %s,
                    is_active = TRUE,
                    updated_at = CURRENT_TIMESTAMP
                WHERE administration = %s AND template_type = %s
            """
            self.db.execute_query(
                update_query, 
                (file_id, mappings_json, administration, template_type),
                fetch=False, 
                commit=True
            )
            logger.info(f"      Updated metadata for: {template_type}")
        else:
            # Insert new
            insert_query = """
                INSERT INTO tenant_template_config 
                (administration, template_type, template_file_id, field_mappings, is_active)
                VALUES (%s, %s, %s, %s, TRUE)
            """
            self.db.execute_query(
                insert_query,
                (administration, template_type, file_id, mappings_json),
                fetch=False,
                commit=True
            )
            logger.info(f"      Stored metadata for: {template_type}")
    
    def upload_templates_for_tenant(self, administration: str, dry_run: bool = False):
        """
        Upload all templates for a tenant.
        
        Args:
            administration: Tenant name
            dry_run: If True, only check what would be uploaded without uploading
        """
        logger.info(f"\n{'='*60}")
        logger.info(f"Processing tenant: {administration}")
        logger.info(f"{'='*60}")
        
        try:
            # Initialize Google Drive service for this tenant
            drive_service = GoogleDriveService(administration)
            logger.info(f"✅ Successfully authenticated Google Drive for {administration}")
            
            # Get Templates folder ID
            templates_folder_id = self.get_templates_folder_id(administration)
            logger.info(f"📁 Templates folder ID: {templates_folder_id}")
            
            # Track uploaded templates
            upload_results = {}
            
            # Upload each template
            for local_path, template_type, mime_type, description in self.TEMPLATES:
                logger.info(f"\n--- Processing template: {template_type} ---")
                logger.info(f"   Description: {description}")
                
                try:
                    # Upload the template
                    file_info = self.upload_template(
                        drive_service,
                        local_path,
                        template_type,
                        mime_type,
                        templates_folder_id,
                        dry_run
                    )
                    
                    upload_results[template_type] = file_info
                    
                    # Store metadata in database (skip in dry run)
                    if not dry_run and file_info['id'] != 'DRY_RUN':
                        # Load field mappings if available
                        field_mappings = self.load_field_mappings(template_type)
                        
                        self.store_template_metadata(
                            administration,
                            template_type,
                            file_info['id'],
                            description,
                            field_mappings
                        )
                    
                except Exception as e:
                    logger.error(f"   ❌ Failed to upload {template_type}: {e}")
                    upload_results[template_type] = {'error': str(e)}
            
            # Summary
            logger.info(f"\n{'='*60}")
            logger.info(f"✅ Completed processing for {administration}")
            logger.info(f"{'='*60}")
            
            success_count = sum(1 for r in upload_results.values() if 'error' not in r)
            error_count = sum(1 for r in upload_results.values() if 'error' in r)
            
            logger.info(f"Templates processed: {len(upload_results)}")
            logger.info(f"  ✅ Successful: {success_count}")
            logger.info(f"  ❌ Failed: {error_count}")
            
            if error_count > 0:
                logger.info("\nFailed templates:")
                for template_type, result in upload_results.items():
                    if 'error' in result:
                        logger.info(f"  - {template_type}: {result['error']}")
            
            return upload_results
            
        except Exception as e:
            logger.error(f"❌ Error processing tenant {administration}: {e}")
            raise
    
    def process_all_tenants(self, dry_run: bool = False):
        """Process all tenants with Google Drive credentials"""
        tenants = self.get_tenants_with_credentials()
        
        if not tenants:
            logger.warning("⚠️  No tenants found with Google Drive credentials")
            return
        
        logger.info(f"Found {len(tenants)} tenant(s) with Google Drive credentials:")
        for tenant in tenants:
            logger.info(f"  - {tenant}")
        
        results = {}
        for tenant in tenants:
            try:
                results[tenant] = self.upload_templates_for_tenant(tenant, dry_run)
            except Exception as e:
                logger.error(f"Failed to process {tenant}: {e}")
                results[tenant] = {'error': str(e)}
        
        return results
    
    def process_single_tenant(self, administration: str, dry_run: bool = False):
        """Process a single tenant"""
        # Verify tenant has credentials
        tenants = self.get_tenants_with_credentials()
        
        if administration not in tenants:
            logger.error(f"❌ Tenant '{administration}' not found or has no Google Drive credentials")
            logger.info(f"Available tenants: {', '.join(tenants)}")
            return None
        
        return self.upload_templates_for_tenant(administration, dry_run)


def main():
    """Main entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Upload templates to tenant Google Drives'
    )
    parser.add_argument(
        '--tenant',
        type=str,
        help='Process only this tenant (default: process all tenants)'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Check what would be uploaded without actually uploading'
    )
    
    args = parser.parse_args()
    
    # Initialize database
    db = DatabaseManager()
    uploader = TemplateUploader(db)
    
    # Process tenant(s)
    if args.tenant:
        logger.info(f"Processing single tenant: {args.tenant}")
        uploader.process_single_tenant(args.tenant, dry_run=args.dry_run)
    else:
        logger.info("Processing all tenants with Google Drive credentials")
        uploader.process_all_tenants(dry_run=args.dry_run)


if __name__ == '__main__':
    main()
