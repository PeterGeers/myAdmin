-- ============================================================================
-- ZZP Module: Database Migration
-- Creates all ZZP tables in FK dependency order
-- Idempotent: uses CREATE TABLE IF NOT EXISTS / CREATE OR REPLACE VIEW
-- ============================================================================
-- ============================================================================
-- 1. contacts — Shared contact registry
-- ============================================================================
CREATE TABLE IF NOT EXISTS contacts (
    id INT AUTO_INCREMENT PRIMARY KEY,
    administration VARCHAR(50) NOT NULL,
    client_id VARCHAR(20) NOT NULL COMMENT 'Short unique ref per tenant, e.g. ACME, KPN',
    contact_type VARCHAR(20) NOT NULL DEFAULT 'client' COMMENT 'From zzp.contact_types parameter set',
    company_name VARCHAR(255) NOT NULL,
    contact_person VARCHAR(255) DEFAULT NULL,
    street_address VARCHAR(255) DEFAULT NULL,
    postal_code VARCHAR(20) DEFAULT NULL,
    city VARCHAR(100) DEFAULT NULL,
    country VARCHAR(100) DEFAULT 'NL',
    vat_number VARCHAR(50) DEFAULT NULL,
    kvk_number VARCHAR(20) DEFAULT NULL COMMENT 'Chamber of Commerce',
    phone VARCHAR(50) DEFAULT NULL,
    iban VARCHAR(50) DEFAULT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    created_by VARCHAR(255) DEFAULT NULL,
    UNIQUE KEY uq_tenant_client_id (administration, client_id),
    INDEX idx_administration (administration),
    INDEX idx_client_id (client_id),
    INDEX idx_contact_type (contact_type)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_unicode_ci;
-- ============================================================================
-- 2. contact_emails — Multiple emails per contact with type indicator
-- ============================================================================
CREATE TABLE IF NOT EXISTS contact_emails (
    id INT AUTO_INCREMENT PRIMARY KEY,
    contact_id INT NOT NULL,
    email VARCHAR(255) NOT NULL,
    email_type ENUM('general', 'invoice', 'other') DEFAULT 'general',
    is_primary BOOLEAN DEFAULT FALSE,
    FOREIGN KEY (contact_id) REFERENCES contacts(id) ON DELETE CASCADE,
    INDEX idx_contact_id (contact_id)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_unicode_ci;
-- ============================================================================
-- 3. products — Shared product/service registry
-- ============================================================================
CREATE TABLE IF NOT EXISTS products (
    id INT AUTO_INCREMENT PRIMARY KEY,
    administration VARCHAR(50) NOT NULL,
    product_code VARCHAR(30) NOT NULL COMMENT 'Short unique ref per tenant, e.g. DEV-HR, CONSULT',
    external_reference VARCHAR(100) DEFAULT NULL COMMENT 'Link to external system (e.g. supplier SKU, accounting code)',
    name VARCHAR(255) NOT NULL,
    description TEXT DEFAULT NULL,
    product_type VARCHAR(50) NOT NULL COMMENT 'From zzp.product_types parameter set',
    unit_price DECIMAL(12, 2) DEFAULT 0.00,
    vat_code VARCHAR(20) NOT NULL COMMENT 'Ref to tax_rates.tax_code (high/low/zero)',
    unit_of_measure VARCHAR(50) DEFAULT 'uur' COMMENT 'uur, stuk, maand, etc.',
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    created_by VARCHAR(255) DEFAULT NULL,
    UNIQUE KEY uq_tenant_product_code (administration, product_code),
    INDEX idx_administration (administration),
    INDEX idx_product_type (product_type),
    INDEX idx_external_reference (external_reference)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_unicode_ci;
-- ============================================================================
-- 4. invoices — Core invoice header
-- ============================================================================
CREATE TABLE IF NOT EXISTS invoices (
    id INT AUTO_INCREMENT PRIMARY KEY,
    administration VARCHAR(50) NOT NULL,
    invoice_number VARCHAR(30) NOT NULL COMMENT 'e.g. INV-2026-0001 or CN-2026-0001',
    invoice_type ENUM('invoice', 'credit_note') DEFAULT 'invoice',
    contact_id INT NOT NULL,
    invoice_date DATE NOT NULL,
    due_date DATE NOT NULL,
    payment_terms_days INT DEFAULT 30,
    currency VARCHAR(3) DEFAULT 'EUR',
    exchange_rate DECIMAL(12, 6) DEFAULT 1.000000,
    status ENUM(
        'draft',
        'sent',
        'paid',
        'overdue',
        'cancelled',
        'credited'
    ) DEFAULT 'draft',
    subtotal DECIMAL(12, 2) DEFAULT 0.00,
    vat_total DECIMAL(12, 2) DEFAULT 0.00,
    grand_total DECIMAL(12, 2) DEFAULT 0.00,
    notes TEXT DEFAULT NULL,
    original_invoice_id INT DEFAULT NULL COMMENT 'For credit notes: link to original',
    sent_at DATETIME DEFAULT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    created_by VARCHAR(255) DEFAULT NULL,
    UNIQUE KEY uq_tenant_invoice_number (administration, invoice_number),
    FOREIGN KEY (contact_id) REFERENCES contacts(id),
    FOREIGN KEY (original_invoice_id) REFERENCES invoices(id),
    INDEX idx_administration (administration),
    INDEX idx_status (status),
    INDEX idx_contact_id (contact_id),
    INDEX idx_due_date (due_date),
    INDEX idx_invoice_date (invoice_date)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_unicode_ci;
-- ============================================================================
-- 5. invoice_lines — Line items per invoice
-- ============================================================================
CREATE TABLE IF NOT EXISTS invoice_lines (
    id INT AUTO_INCREMENT PRIMARY KEY,
    invoice_id INT NOT NULL,
    product_id INT DEFAULT NULL,
    description VARCHAR(512) NOT NULL,
    quantity DECIMAL(10, 4) DEFAULT 1.0000,
    unit_price DECIMAL(12, 2) NOT NULL,
    vat_code VARCHAR(20) NOT NULL,
    vat_rate DECIMAL(5, 2) NOT NULL COMMENT 'Snapshot of rate at invoice date',
    vat_amount DECIMAL(12, 2) NOT NULL,
    line_total DECIMAL(12, 2) NOT NULL COMMENT 'quantity * unit_price (excl VAT)',
    sort_order INT DEFAULT 0,
    FOREIGN KEY (invoice_id) REFERENCES invoices(id) ON DELETE CASCADE,
    FOREIGN KEY (product_id) REFERENCES products(id),
    INDEX idx_invoice_id (invoice_id)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_unicode_ci;
-- ============================================================================
-- 6. vw_invoice_vat_summary — VAT breakdown per rate per invoice (view)
-- ============================================================================
CREATE OR REPLACE VIEW vw_invoice_vat_summary AS
SELECT invoice_id,
    vat_code,
    vat_rate,
    ROUND(SUM(line_total), 2) AS base_amount,
    ROUND(SUM(vat_amount), 2) AS vat_amount
FROM invoice_lines
GROUP BY invoice_id,
    vat_code,
    vat_rate;
-- ============================================================================
-- 7. invoice_number_sequences — Tenant+year sequence counter with row-level locking
-- ============================================================================
CREATE TABLE IF NOT EXISTS invoice_number_sequences (
    id INT AUTO_INCREMENT PRIMARY KEY,
    administration VARCHAR(50) NOT NULL,
    prefix VARCHAR(10) NOT NULL COMMENT 'INV or CN',
    year INT NOT NULL,
    last_sequence INT DEFAULT 0,
    UNIQUE KEY uq_tenant_prefix_year (administration, prefix, year)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_unicode_ci;
-- ============================================================================
-- 8. time_entries — Time tracking records
-- ============================================================================
CREATE TABLE IF NOT EXISTS time_entries (
    id INT AUTO_INCREMENT PRIMARY KEY,
    administration VARCHAR(50) NOT NULL,
    contact_id INT NOT NULL,
    product_id INT DEFAULT NULL,
    project_name VARCHAR(255) DEFAULT NULL,
    entry_date DATE NOT NULL,
    hours DECIMAL(6, 2) NOT NULL,
    hourly_rate DECIMAL(10, 2) NOT NULL,
    description TEXT DEFAULT NULL,
    is_billable BOOLEAN DEFAULT TRUE,
    is_billed BOOLEAN DEFAULT FALSE,
    invoice_id INT DEFAULT NULL COMMENT 'Set when billed',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    created_by VARCHAR(255) DEFAULT NULL,
    FOREIGN KEY (contact_id) REFERENCES contacts(id),
    FOREIGN KEY (product_id) REFERENCES products(id),
    FOREIGN KEY (invoice_id) REFERENCES invoices(id),
    INDEX idx_administration (administration),
    INDEX idx_contact_id (contact_id),
    INDEX idx_entry_date (entry_date),
    INDEX idx_is_billed (is_billed)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_unicode_ci;
-- ============================================================================
-- 9. Seed: Activate ZZP module for InterimManagement tenant
-- ============================================================================
INSERT INTO tenant_modules (
        administration,
        module_name,
        is_active,
        created_by
    )
VALUES ('InterimManagement', 'ZZP', TRUE, 'system') ON DUPLICATE KEY
UPDATE is_active = TRUE;
-- ============================================================================
-- VERIFICATION
-- ============================================================================
SELECT 'ZZP tables created successfully' AS status;
SELECT TABLE_NAME,
    TABLE_ROWS
FROM INFORMATION_SCHEMA.TABLES
WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME IN (
        'contacts',
        'contact_emails',
        'products',
        'invoices',
        'invoice_lines',
        'invoice_number_sequences',
        'time_entries'
    )
ORDER BY TABLE_NAME;
SELECT TABLE_NAME,
    INDEX_NAME,
    COLUMN_NAME
FROM INFORMATION_SCHEMA.STATISTICS
WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME IN (
        'contacts',
        'contact_emails',
        'products',
        'invoices',
        'invoice_lines',
        'invoice_number_sequences',
        'time_entries'
    )
ORDER BY TABLE_NAME,
    INDEX_NAME;
SELECT TABLE_NAME
FROM INFORMATION_SCHEMA.VIEWS
WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'vw_invoice_vat_summary';
SELECT administration,
    module_name,
    is_active
FROM tenant_modules
WHERE module_name = 'ZZP';