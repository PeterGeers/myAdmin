-- Create lookupbankaccounts_R table
CREATE TABLE IF NOT EXISTS lookupbankaccounts_R (
    id INT AUTO_INCREMENT PRIMARY KEY,
    rekeningNummer VARCHAR(50),
    Account VARCHAR(10),
    Administration VARCHAR(100),
    INDEX idx_rekening (rekeningNummer),
    INDEX idx_admin (Administration)
);