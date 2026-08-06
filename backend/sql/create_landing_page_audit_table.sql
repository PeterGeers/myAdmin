-- Landing Page Audit Table
-- Records publish, unpublish, and rollback events for landing pages.
-- Task 4.4 — Phase 4 of the Landing Page spec.
CREATE TABLE IF NOT EXISTS landing_page_audit (
    id INT AUTO_INCREMENT PRIMARY KEY,
    administration VARCHAR(50) NOT NULL,
    action VARCHAR(50) NOT NULL,
    version INT,
    performed_by VARCHAR(255) NOT NULL,
    performed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    details TEXT,
    INDEX idx_administration (administration),
    INDEX idx_performed_at (performed_at)
);