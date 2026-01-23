Correct the banking processor pattern analysis. Since a few weeks it is not working anymore:
Findings A:
-- In the Finance Database there are 2 near similar instances vw_ReadReferences(No Date) and vw_readreferences (+ Date)
--- No idea which one is used and if it is case sensitive
--- No idea who/what created the double views

Logic: Define the best possible value for missing ReferenceNumber and Debet or Credit number for each record:
-- Based on the known variables TransactionDescription, Administraion, Debet or Credit number of the banking account
-- Using patterns
--- found by filtering mutaties from the last 2 years the Administration, RefernceNumber, Debet and or Credit value and Last (Date)
-- For each record the bankaccount lookup and the debet or credit for the ReferenceNumber
-- If Debet is bank account the Credit number is retrieved from the pattern view
-- If Credit is bank accoun the Debet number is retrieved from the pattern view

Findings B:
- If updating/validating the transactions after the patterns are applied
-- Hitting ENTER pushes the records to the database and no confirmation asked
- Please remove method/overriding the ENTER key to the actual field the cursor is in and letbuttons procee to the next step 
-- Button: Apply Patterns
-- Button: Save to Database

Test data:
-- Input: CSV_O*.csv are 2 input files for the banking processor
-- Output: RABO 2025-12-19.csv are the corrected records loaded in the database based on manual corrected data