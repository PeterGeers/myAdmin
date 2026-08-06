-- Create landing_page_submissions table for Landing Page contact form
-- Stores visitor inquiries submitted via public landing page contact forms
-- No tenant FK — administration is denormalized for performance (public endpoint, no auth)
-- ============================================================================
CREATE TABLE IF NOT EXISTS landing_page_submissions (
    id INT AUTO_INCREMENT PRIMARY KEY,
    administration VARCHAR(50) NOT NULL,
    visitor_name VARCHAR(200) NOT NULL,
    visitor_email VARCHAR(200) NOT NULL,
    message TEXT NOT NULL,
    ip_address VARCHAR(45),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_read BOOLEAN DEFAULT FALSE,
    INDEX idx_administration (administration),
    INDEX idx_created_at (created_at)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_unicode_ci;