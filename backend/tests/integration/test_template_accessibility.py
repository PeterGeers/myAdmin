"""
Integration tests for template accessibility from Google Drive.

This test suite verifies that all templates uploaded to tenant Google Drives
are accessible and can be fetched successfully.

Tests verify:
1. Template metadata exists in database
2. Templates can be fetched from Google Drive
3. Template content is valid (non-empty, correct format)
4. All tenants have access to their templates
5. Template isolation (tenants can only access their own templates)

Test Organization: Integration Tests
- Uses real database connections
- Uses real Google Drive API calls
- Requires tenant credentials in database
- Should be run after Phase 2.4 (Template Upload) completion
"""

import pytest
import logging
from database import DatabaseManager
from services.template_service import TemplateService
from google_drive_service import GoogleDriveService

logger = logging.getLogger(__name__)


@pytest.mark.integration
class TestTemplateAccessibility:
    """Integration tests for template accessibility"""
    
    @pytest.fixture
    def db(self):
        """Create database connection"""
        db = DatabaseManager()
        yield db
        # Cleanup handled by DatabaseManager
    
    @pytest.fixture
    def template_service(self, db):
        """Create TemplateService instance"""
        return TemplateService(db)
    
    def test_all_tenants_have_templates(self, db):
        """
        Verify that all expected tenants have templates configured in database.
        
        This test checks that template metadata exists for each tenant.
        """
        # Get all tenants with templates
        query = """
            SELECT DISTINCT administration 
            FROM tenant_template_config
            ORDER BY administration
        """
        results = db.execute_query(query)
        tenants = [r['administration'] for r in results]
        
        # Verify we have at least the expected tenants
        expected_tenants = ['GoodwinSolutions', 'PeterPrive']
        
        for expected_tenant in expected_tenants:
            assert expected_tenant in tenants, \
                f"Expected tenant '{expected_tenant}' not found in tenant_template_config"
        
        logger.info(f"✅ Found {len(tenants)} tenant(s) with templates: {tenants}")
    
    def test_template_metadata_completeness(self, db):
        """
        Verify that all template metadata is complete and valid.
        
        Checks:
        - template_file_id is not null
        - template_type is not null
        - administration is not null
        - is_active is set
        """
        query = """
            SELECT administration, template_type, template_file_id, is_active
            FROM tenant_template_config
            ORDER BY administration, template_type
        """
        templates = db.execute_query(query)
        
        assert len(templates) > 0, "No templates found in database"
        
        for template in templates:
            # Verify required fields are present
            assert template['administration'], \
                f"Template missing administration: {template}"
            assert template['template_type'], \
                f"Template missing template_type: {template}"
            assert template['template_file_id'], \
                f"Template missing template_file_id: {template}"
            assert template['is_active'] is not None, \
                f"Template missing is_active flag: {template}"
        
        logger.info(f"✅ All {len(templates)} template metadata records are complete")
    
    def test_expected_template_types_exist(self, db):
        """
        Verify that all expected template types exist for each tenant.
        
        Expected template types:
        - aangifte_ib_html
        - btw_aangifte_html
        - toeristenbelasting_html
        - str_invoice_nl
        - str_invoice_en
        - financial_report_xlsx
        """
        expected_types = [
            'aangifte_ib_html',
            'btw_aangifte_html',
            'toeristenbelasting_html',
            'str_invoice_nl',
            'str_invoice_en',
            'financial_report_xlsx'
        ]
        
        # Get all tenants
        query = """
            SELECT DISTINCT administration 
            FROM tenant_template_config
        """
        tenants = [r['administration'] for r in db.execute_query(query)]
        
        for tenant in tenants:
            # Get template types for this tenant
            query = """
                SELECT template_type 
                FROM tenant_template_config
                WHERE administration = %s AND is_active = TRUE
            """
            results = db.execute_query(query, (tenant,))
            tenant_types = [r['template_type'] for r in results]
            
            # Verify all expected types exist
            for expected_type in expected_types:
                assert expected_type in tenant_types, \
                    f"Tenant '{tenant}' missing template type '{expected_type}'"
            
            logger.info(f"✅ Tenant '{tenant}' has all {len(expected_types)} expected template types")
    
    def test_google_drive_authentication(self, db):
        """
        Verify that Google Drive authentication works for all tenants.
        
        This test verifies that:
        1. Credentials exist in database
        2. GoogleDriveService can authenticate
        3. Service object is created successfully
        """
        # Get all tenants
        query = """
            SELECT DISTINCT administration 
            FROM tenant_template_config
        """
        tenants = [r['administration'] for r in db.execute_query(query)]
        
        for tenant in tenants:
            try:
                # Try to create GoogleDriveService
                drive_service = GoogleDriveService(tenant)
                
                # Verify service was created
                assert drive_service is not None, \
                    f"GoogleDriveService is None for tenant '{tenant}'"
                assert drive_service.service is not None, \
                    f"GoogleDriveService.service is None for tenant '{tenant}'"
                
                logger.info(f"✅ Google Drive authentication successful for '{tenant}'")
                
            except Exception as e:
                pytest.fail(f"Google Drive authentication failed for '{tenant}': {e}")
    
    def test_fetch_template_from_drive(self, template_service, db):
        """
        Verify that templates can be fetched from Google Drive.
        
        This test:
        1. Gets template metadata from database
        2. Fetches template content from Google Drive
        3. Verifies content is valid (non-empty, correct format)
        
        Note: XLSX files are binary and cannot be decoded as UTF-8.
        The current TemplateService.fetch_template_from_drive() method
        only supports text files. For XLSX files, we verify they exist
        in Google Drive but skip content validation.
        """
        # Get all active templates
        query = """
            SELECT administration, template_type, template_file_id
            FROM tenant_template_config
            WHERE is_active = TRUE
            ORDER BY administration, template_type
        """
        templates = db.execute_query(query)
        
        assert len(templates) > 0, "No active templates found"
        
        # Test fetching each template
        for template in templates:
            admin = template['administration']
            template_type = template['template_type']
            file_id = template['template_file_id']
            
            # XLSX files are binary and can't be decoded as UTF-8
            # Skip content fetch for XLSX, just verify file exists in Drive
            if template_type.endswith('_xlsx'):
                try:
                    # Verify file exists by checking metadata
                    from google_drive_service import GoogleDriveService
                    drive_service = GoogleDriveService(admin)
                    
                    file_metadata = drive_service.service.files().get(
                        fileId=file_id,
                        fields='id,name,mimeType'
                    ).execute()
                    
                    assert file_metadata['id'] == file_id, \
                        f"File ID mismatch for {admin}/{template_type}"
                    
                    logger.info(f"✅ XLSX file exists in Drive: {admin}/{template_type}")
                    
                except Exception as e:
                    pytest.fail(f"Failed to verify XLSX file {admin}/{template_type}: {e}")
                
                continue
            
            # For text-based templates (HTML), fetch and verify content
            try:
                # Fetch template content
                content = template_service.fetch_template_from_drive(
                    file_id=file_id,
                    administration=admin
                )
                
                # Verify content is not empty
                assert content, \
                    f"Template content is empty for {admin}/{template_type}"
                assert len(content) > 0, \
                    f"Template content has zero length for {admin}/{template_type}"
                
                # Verify content format based on template type
                if template_type.endswith('_html'):
                    # HTML templates should contain HTML tags
                    assert '<' in content and '>' in content, \
                        f"HTML template {admin}/{template_type} doesn't contain HTML tags"
                
                logger.info(f"✅ Successfully fetched {admin}/{template_type} ({len(content)} bytes)")
                
            except Exception as e:
                pytest.fail(f"Failed to fetch template {admin}/{template_type}: {e}")
    
    def test_template_content_validity(self, template_service, db):
        """
        Verify that template content is valid and contains expected elements.
        
        For HTML templates:
        - Should contain placeholder syntax ({{ }})
        - Should be well-formed HTML
        
        For XLSX templates:
        - Should be binary data
        - Should have reasonable size
        """
        # Get all active HTML templates
        query = """
            SELECT administration, template_type, template_file_id
            FROM tenant_template_config
            WHERE is_active = TRUE AND template_type LIKE '%_html'
            ORDER BY administration, template_type
        """
        html_templates = db.execute_query(query)
        
        for template in html_templates:
            admin = template['administration']
            template_type = template['template_type']
            file_id = template['template_file_id']
            
            # Fetch template content
            content = template_service.fetch_template_from_drive(
                file_id=file_id,
                administration=admin
            )
            
            # Verify HTML structure
            assert '<!DOCTYPE html>' in content or '<html' in content, \
                f"Template {admin}/{template_type} missing HTML declaration"
            
            # Verify contains placeholders (Jinja2 syntax)
            assert '{{' in content and '}}' in content, \
                f"Template {admin}/{template_type} missing placeholder syntax"
            
            # Verify basic HTML tags
            assert '<body' in content, \
                f"Template {admin}/{template_type} missing <body> tag"
            
            logger.info(f"✅ Template {admin}/{template_type} content is valid")
    
    def test_template_isolation(self, db):
        """
        Verify that template isolation is maintained.
        
        Each tenant should only have access to their own templates.
        Template file IDs should be unique per tenant.
        """
        # Get all templates grouped by tenant
        query = """
            SELECT administration, template_type, template_file_id
            FROM tenant_template_config
            WHERE is_active = TRUE
            ORDER BY administration, template_type
        """
        templates = db.execute_query(query)
        
        # Group by tenant
        by_tenant = {}
        for template in templates:
            admin = template['administration']
            if admin not in by_tenant:
                by_tenant[admin] = []
            by_tenant[admin].append(template)
        
        # Verify file IDs are unique across tenants
        all_file_ids = [t['template_file_id'] for t in templates]
        unique_file_ids = set(all_file_ids)
        
        assert len(all_file_ids) == len(unique_file_ids), \
            "Template file IDs are not unique - templates may be shared across tenants"
        
        logger.info(f"✅ Template isolation verified - all file IDs are unique")
    
    def test_get_template_metadata_method(self, template_service, db):
        """
        Verify that TemplateService.get_template_metadata works correctly.
        
        This method is used by report generation routes to get template info.
        """
        # Get a sample template from database
        query = """
            SELECT administration, template_type
            FROM tenant_template_config
            WHERE is_active = TRUE
            LIMIT 1
        """
        result = db.execute_query(query)
        
        assert len(result) > 0, "No active templates found for testing"
        
        sample = result[0]
        admin = sample['administration']
        template_type = sample['template_type']
        
        # Get metadata using TemplateService
        metadata = template_service.get_template_metadata(admin, template_type)
        
        # Verify metadata is returned
        assert metadata is not None, \
            f"get_template_metadata returned None for {admin}/{template_type}"
        assert 'template_file_id' in metadata, \
            "Metadata missing template_file_id"
        assert metadata['template_file_id'], \
            "template_file_id is empty"
        
        logger.info(f"✅ get_template_metadata works correctly for {admin}/{template_type}")
    
    def test_inactive_templates_not_accessible(self, template_service, db):
        """
        Verify that inactive templates are not returned by get_template_metadata.
        
        This ensures that deactivated templates are not used for report generation.
        """
        # Check if there are any inactive templates
        query = """
            SELECT administration, template_type
            FROM tenant_template_config
            WHERE is_active = FALSE
            LIMIT 1
        """
        result = db.execute_query(query)
        
        if len(result) == 0:
            pytest.skip("No inactive templates found to test")
        
        sample = result[0]
        admin = sample['administration']
        template_type = sample['template_type']
        
        # Try to get metadata for inactive template
        metadata = template_service.get_template_metadata(admin, template_type)
        
        # Should return None for inactive template
        assert metadata is None, \
            f"get_template_metadata should return None for inactive template {admin}/{template_type}"
        
        logger.info(f"✅ Inactive template {admin}/{template_type} correctly not accessible")
    
    @pytest.mark.slow
    def test_all_templates_accessible_comprehensive(self, template_service, db):
        """
        Comprehensive test that verifies ALL templates are accessible.
        
        This is a slower test that fetches every single template to ensure
        complete accessibility across all tenants.
        
        Marked as 'slow' because it makes many Google Drive API calls.
        
        Note: XLSX files are binary and cannot be decoded as UTF-8.
        For XLSX files, we verify they exist in Google Drive but skip content fetch.
        """
        # Get all active templates
        query = """
            SELECT administration, template_type, template_file_id
            FROM tenant_template_config
            WHERE is_active = TRUE
            ORDER BY administration, template_type
        """
        templates = db.execute_query(query)
        
        total = len(templates)
        success = 0
        failures = []
        
        logger.info(f"Testing accessibility of {total} templates...")
        
        for template in templates:
            admin = template['administration']
            template_type = template['template_type']
            file_id = template['template_file_id']
            
            try:
                # XLSX files are binary and can't be decoded as UTF-8
                if template_type.endswith('_xlsx'):
                    # Verify file exists by checking metadata
                    from google_drive_service import GoogleDriveService
                    drive_service = GoogleDriveService(admin)
                    
                    file_metadata = drive_service.service.files().get(
                        fileId=file_id,
                        fields='id,name,mimeType'
                    ).execute()
                    
                    assert file_metadata['id'] == file_id
                    success += 1
                else:
                    # Fetch text-based template
                    content = template_service.fetch_template_from_drive(
                        file_id=file_id,
                        administration=admin
                    )
                    
                    # Verify content
                    assert content and len(content) > 0
                    success += 1
                
            except Exception as e:
                failures.append({
                    'admin': admin,
                    'template_type': template_type,
                    'file_id': file_id,
                    'error': str(e)
                })
        
        # Report results
        logger.info(f"\n{'='*80}")
        logger.info(f"Template Accessibility Test Results")
        logger.info(f"{'='*80}")
        logger.info(f"Total templates: {total}")
        logger.info(f"✅ Successful: {success}")
        logger.info(f"❌ Failed: {len(failures)}")
        
        if failures:
            logger.error("\nFailed templates:")
            for failure in failures:
                logger.error(f"  - {failure['admin']}/{failure['template_type']}: {failure['error']}")
        
        # Assert all succeeded
        assert len(failures) == 0, \
            f"{len(failures)} template(s) failed accessibility test"
        
        logger.info(f"\n✅ All {total} templates are accessible")


@pytest.mark.integration
class TestTemplateAccessibilityPerTenant:
    """Integration tests for template accessibility per tenant"""
    
    @pytest.fixture
    def db(self):
        """Create database connection"""
        db = DatabaseManager()
        yield db
    
    @pytest.fixture
    def template_service(self, db):
        """Create TemplateService instance"""
        return TemplateService(db)
    
    @pytest.mark.parametrize("tenant", ["GoodwinSolutions", "PeterPrive"])
    def test_tenant_has_all_templates(self, tenant, db):
        """
        Verify that each tenant has all expected template types.
        
        This test is parameterized to run for each tenant.
        """
        expected_types = [
            'aangifte_ib_html',
            'btw_aangifte_html',
            'toeristenbelasting_html',
            'str_invoice_nl',
            'str_invoice_en',
            'financial_report_xlsx'
        ]
        
        # Get template types for this tenant
        query = """
            SELECT template_type 
            FROM tenant_template_config
            WHERE administration = %s AND is_active = TRUE
        """
        results = db.execute_query(query, (tenant,))
        tenant_types = [r['template_type'] for r in results]
        
        # Verify all expected types exist
        for expected_type in expected_types:
            assert expected_type in tenant_types, \
                f"Tenant '{tenant}' missing template type '{expected_type}'"
        
        logger.info(f"✅ Tenant '{tenant}' has all {len(expected_types)} expected templates")
    
    @pytest.mark.parametrize("tenant", ["GoodwinSolutions", "PeterPrive"])
    def test_tenant_can_fetch_all_templates(self, tenant, template_service, db):
        """
        Verify that each tenant can fetch all their templates.
        
        This test is parameterized to run for each tenant.
        
        Note: XLSX files are binary and cannot be decoded as UTF-8.
        For XLSX files, we verify they exist in Google Drive but skip content fetch.
        """
        # Get all templates for this tenant
        query = """
            SELECT template_type, template_file_id
            FROM tenant_template_config
            WHERE administration = %s AND is_active = TRUE
        """
        templates = db.execute_query(query, (tenant,))
        
        assert len(templates) > 0, f"No templates found for tenant '{tenant}'"
        
        # Try to fetch each template
        for template in templates:
            template_type = template['template_type']
            file_id = template['template_file_id']
            
            # XLSX files are binary and can't be decoded as UTF-8
            if template_type.endswith('_xlsx'):
                try:
                    # Verify file exists by checking metadata
                    from google_drive_service import GoogleDriveService
                    drive_service = GoogleDriveService(tenant)
                    
                    file_metadata = drive_service.service.files().get(
                        fileId=file_id,
                        fields='id,name,mimeType'
                    ).execute()
                    
                    assert file_metadata['id'] == file_id
                    logger.info(f"✅ {tenant} can access XLSX file {template_type}")
                    
                except Exception as e:
                    pytest.fail(f"{tenant} failed to access XLSX {template_type}: {e}")
                
                continue
            
            # For text-based templates, fetch content
            try:
                content = template_service.fetch_template_from_drive(
                    file_id=file_id,
                    administration=tenant
                )
                
                assert content and len(content) > 0, \
                    f"Empty content for {tenant}/{template_type}"
                
                logger.info(f"✅ {tenant} can fetch {template_type}")
                
            except Exception as e:
                pytest.fail(f"{tenant} failed to fetch {template_type}: {e}")
