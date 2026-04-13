-- Remove invalid parameters from Railway
DELETE FROM parameters
WHERE (
        namespace = 'general'
        AND `key` = 'default_administration'
    )
    OR (
        namespace = 'storage'
        AND `key` IN ('download_folder', 'vendor_folder_mappings')
    );