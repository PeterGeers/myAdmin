#!/usr/bin/env python3
"""
Create Template Folders in Tenant Google Drives

This script creates the required folder structure in each tenant's Google Drive:
- Templates/
- Invoices/
- Reports/

It stores the folder IDs in the tenant_config table for future reference.

Usage:
    python scripts/create_template_folders.py [--tenant TENANT_NAME]
    
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

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class TemplateFolderCreator:
    """Creates template folder structure in tenant Google Drives"""
    
    # Folder structure to create
    FOLDER_STRUCTURE = [
        'Templates',
        'Invoices',
        'Reports'
    ]
    
    def __init__(self, db: DatabaseManager):
        self.db = db
    
    def get_tenants_with_credentials(self):
        """Get list of tenants that have Google Drive credentials"""
        query = """
            SELECT DISTINCT administration 
            FROM tenant_credentials 
            WHERE credential_type = 'google_drive_oauth'
        """
        results = self.db.execute_query(query)
        return [r['administration'] for r in results]
    
    def get_root_folder_id(self, administration: str) -> str:
        """
        Get the root folder ID for a tenant from tenant_config.
        If not set, returns None (will use Drive root).
        """
        query = """
            SELECT config_value 
            FROM tenant_config 
            WHERE administration = %s AND config_key = 'google_drive_root_folder_id'
        """
        results = self.db.execute_query(query, (administration,))
        
        if results and results[0]['config_value']:
            return results[0]['config_value']
        
        # Check environment variable as fallback (for existing tenants)
        if administration == 'GoodwinSolutions' or administration == 'PeterPrive':
            folder_id = os.getenv('FACTUREN_FOLDER_ID')
            if folder_id:
                logger.info(f"Using FACTUREN_FOLDER_ID from environment for {administration}: {folder_id}")
                return folder_id
        
        return None
    
    def check_folder_exists(self, drive_service: GoogleDriveService, folder_name: str, parent_id: str = None) -> dict:
        """
        Check if a folder already exists in the parent folder.
        
        Returns:
            dict with 'exists' (bool) and 'folder' (dict with id, name, url) if exists
        """
        try:
            query = f"name='{folder_name}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
            
            if parent_id:
                query += f" and '{parent_id}' in parents"
            
            results = drive_service.service.files().list(
                q=query,
                fields="files(id, name, webViewLink)",
                pageSize=10
            ).execute()
            
            files = results.get('files', [])
            
            if files:
                return {
                    'exists': True,
                    'folder': {
                        'id': files[0]['id'],
                        'name': files[0]['name'],
                        'url': files[0].get('webViewLink', '')
                    }
                }
            
            return {'exists': False}
            
        except Exception as e:
            logger.error(f"Error checking folder existence: {e}")
            return {'exists': False}
    
    def create_folder_structure(self, administration: str, dry_run: bool = False):
        """
        Create folder structure for a tenant.
        
        Args:
            administration: Tenant name
            dry_run: If True, only check what would be created without creating
        """
        logger.info(f"\n{'='*60}")
        logger.info(f"Processing tenant: {administration}")
        logger.info(f"{'='*60}")
        
        try:
            # Initialize Google Drive service for this tenant
            drive_service = GoogleDriveService(administration)
            logger.info(f"✅ Successfully authenticated Google Drive for {administration}")
            
            # Get root folder ID
            root_folder_id = self.get_root_folder_id(administration)
            
            if root_folder_id:
                logger.info(f"📁 Using root folder ID: {root_folder_id}")
            else:
                logger.info(f"📁 Using Google Drive root (no specific folder configured)")
            
            # Track created/existing folders
            folder_results = {}
            
            # Create each folder
            for folder_name in self.FOLDER_STRUCTURE:
                logger.info(f"\n--- Processing folder: {folder_name} ---")
                
                # Check if folder already exists
                check_result = self.check_folder_exists(drive_service, folder_name, root_folder_id)
                
                if check_result['exists']:
                    folder_info = check_result['folder']
                    logger.info(f"✅ Folder '{folder_name}' already exists")
                    logger.info(f"   ID: {folder_info['id']}")
                    logger.info(f"   URL: {folder_info['url']}")
                    folder_results[folder_name] = folder_info
                else:
                    if dry_run:
                        logger.info(f"🔍 [DRY RUN] Would create folder: {folder_name}")
                        folder_results[folder_name] = {'id': 'DRY_RUN', 'name': folder_name, 'url': 'N/A'}
                    else:
                        # Create the folder
                        logger.info(f"📁 Creating folder: {folder_name}")
                        folder_info = drive_service.create_folder(folder_name, root_folder_id)
                        logger.info(f"✅ Created folder '{folder_name}'")
                        logger.info(f"   ID: {folder_info['id']}")
                        logger.info(f"   URL: {folder_info['url']}")
                        folder_results[folder_name] = folder_info
            
            # Store folder IDs in tenant_config
            if not dry_run:
                logger.info(f"\n--- Storing folder IDs in database ---")
                self.store_folder_ids(administration, folder_results)
            
            # Summary
            logger.info(f"\n{'='*60}")
            logger.info(f"✅ Completed processing for {administration}")
            logger.info(f"{'='*60}")
            logger.info(f"Folders processed: {len(folder_results)}")
            for folder_name, folder_info in folder_results.items():
                logger.info(f"  - {folder_name}: {folder_info['id']}")
            
            return folder_results
            
        except Exception as e:
            logger.error(f"❌ Error processing tenant {administration}: {e}")
            raise
    
    def store_folder_ids(self, administration: str, folder_results: dict):
        """Store folder IDs in tenant_config table"""
        for folder_name, folder_info in folder_results.items():
            config_key = f"google_drive_{folder_name.lower()}_folder_id"
            
            # Check if config already exists
            check_query = """
                SELECT id FROM tenant_config 
                WHERE administration = %s AND config_key = %s
            """
            existing = self.db.execute_query(check_query, (administration, config_key))
            
            if existing:
                # Update existing
                update_query = """
                    UPDATE tenant_config 
                    SET config_value = %s, updated_at = CURRENT_TIMESTAMP
                    WHERE administration = %s AND config_key = %s
                """
                self.db.execute_query(update_query, (folder_info['id'], administration, config_key), fetch=False, commit=True)
                logger.info(f"   Updated config: {config_key} = {folder_info['id']}")
            else:
                # Insert new
                insert_query = """
                    INSERT INTO tenant_config (administration, config_key, config_value, is_secret)
                    VALUES (%s, %s, %s, 0)
                """
                self.db.execute_query(insert_query, (administration, config_key, folder_info['id']), fetch=False, commit=True)
                logger.info(f"   Stored config: {config_key} = {folder_info['id']}")
    
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
                results[tenant] = self.create_folder_structure(tenant, dry_run)
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
        
        return self.create_folder_structure(administration, dry_run)


def main():
    """Main entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Create template folders in tenant Google Drives'
    )
    parser.add_argument(
        '--tenant',
        type=str,
        help='Process only this tenant (default: process all tenants)'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Check what would be created without actually creating folders'
    )
    
    args = parser.parse_args()
    
    # Initialize database
    db = DatabaseManager()
    creator = TemplateFolderCreator(db)
    
    # Process tenant(s)
    if args.tenant:
        logger.info(f"Processing single tenant: {args.tenant}")
        creator.process_single_tenant(args.tenant, dry_run=args.dry_run)
    else:
        logger.info("Processing all tenants with Google Drive credentials")
        creator.process_all_tenants(dry_run=args.dry_run)


if __name__ == '__main__':
    main()
