-- Create user_invitations table for tracking invitation status
-- ============================================================================
CREATE TABLE IF NOT EXISTS user_invitations (
    id INT AUTO_INCREMENT PRIMARY KEY,
    administration VARCHAR(100) NOT NULL,
    email VARCHAR(255) NOT NULL,
    username VARCHAR(255),
    temporary_password VARCHAR(255),
    invitation_status ENUM(
        'pending',
        'sent',
        'accepted',
        'expired',
        'failed'
    ) DEFAULT 'pending',
    template_type VARCHAR(50) DEFAULT 'user_invitation',
    sent_at TIMESTAMP NULL,
    expires_at TIMESTAMP NULL,
    accepted_at TIMESTAMP NULL,
    resend_count INT DEFAULT 0,
    last_resent_at TIMESTAMP NULL,
    created_by VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_administration (administration),
    INDEX idx_email (email),
    INDEX idx_status (invitation_status),
    INDEX idx_expires_at (expires_at),
    INDEX idx_admin_email (administration, email)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_unicode_ci;
-- Note: We allow multiple invitations per user to track history
-- The get_invitation() method returns the most recent one (ORDER BY created_at DESC LIMIT 1)