-- Convert 'NA' strings to NULL in mutaties table
UPDATE mutaties 
SET 
    Ref1 = CASE WHEN Ref1 = 'NA' THEN NULL ELSE Ref1 END,
    Ref2 = CASE WHEN Ref2 = 'NA' THEN NULL ELSE Ref2 END,
    Ref3 = CASE WHEN Ref3 = 'NA' THEN NULL ELSE Ref3 END,
    Ref4 = CASE WHEN Ref4 = 'NA' THEN NULL ELSE Ref4 END
WHERE Ref1 = 'NA' OR Ref2 = 'NA' OR Ref3 = 'NA' OR Ref4 = 'NA';