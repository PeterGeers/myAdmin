-- Populate lookupbankaccounts_R with bank account mappings
INSERT INTO lookupbankaccounts_R (rekeningNummer, Account, Administration) VALUES
('NL80RABO0107936917', '1002', 'GoodwinSolutions'),
('NL89RABO1342368843', '1011', 'GoodwinSolutions'),
('NL67RABO1342368851', '1012', 'GoodwinSolutions'),
('NL71RABO0148034454', '1003', 'PeterPrive'),
('NL64RABO3245234589', '1011', 'PeterPrive'),
('NL05REVO8814090866', '1021', 'PeterPrive'),
('NL08REVO7549383472', '1022', 'PeterPrive'),
('Revolut', '1023', 'PeterPrive')
ON DUPLICATE KEY UPDATE Account=VALUES(Account), Administration=VALUES(Administration);