-- Create vw_ReadReferences view for pattern matching
CREATE OR REPLACE VIEW vw_ReadReferences AS
SELECT DISTINCT 
    Debet as debet,
    Credit as credit,
    Administration as administration,
    ReferenceNumber as referenceNumber
FROM mutaties
WHERE ReferenceNumber IS NOT NULL 
  AND ReferenceNumber != ''
  AND (Debet IS NOT NULL OR Credit IS NOT NULL)
ORDER BY Administration, ReferenceNumber;