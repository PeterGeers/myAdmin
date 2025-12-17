Done!
Total checked: 4785
Missing: 632
Output: missing_invoices.csv

1. From a sql backup restore removed urls for missing gdrive invoices (mainly jpg/png) using id only where there was an url and no longer now.
2. Create a file missing invoices with id, date, reference, url, filename for all urls starting with google where the url does no longer exist
3. Contact google support with the question how they can be deleted and if there is a way to get them recovered.
4. Define a regular check to validate if urls exist and if not create list of missing urls. Check in trash and if not contact google support.


We now have a file with still missing_invoices.csv
1. Most missing invoices are jpg or png and their names stored in Ref4
1.1 Most invoices have duplicates in the missingin voices file but that is they occur mostly in 2 records
2. Many of the missing invoices from initial date until 31-12-2023 can be found back in the backup on Microsoft One Drive
3. Is it possible to search on my one drive for each unique invoice (Ref4) and when found
3.2 store the image in the folder with name ReferenceNumber
3.2 Get its url 
3.3 Update the records in mutaties with the id's linked to the Ref4 with the new retrieved url from the invoice
============================================================
📊 SUMMARY
============================================================
Results:
✅ Found: 483 records (from 240 unique files)
❌ Not found: 93 records (from 43 unique files)
Total processed: 576 records from 283 unique filenames
Output files created:
found_invoices.csv - Contains all found invoices with their OneDrive paths
not_found_invoices.csv - Contains invoices still missing