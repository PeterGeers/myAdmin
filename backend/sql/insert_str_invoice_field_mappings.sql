-- =====================================================
-- STR Invoice Field Mappings Migration
-- =====================================================
-- Purpose: Insert field mappings for STR invoice templates
-- Date: January 2026
-- Related: Railway Migration Phase 2.5
-- =====================================================

-- Note: Replace '<google_drive_file_id_nl>' and '<google_drive_file_id_en>' 
-- with actual Google Drive file IDs after uploading templates

-- =====================================================
-- GoodwinSolutions - Dutch STR Invoice Template
-- =====================================================
INSERT INTO tenant_template_config (
    administration,
    template_type,
 