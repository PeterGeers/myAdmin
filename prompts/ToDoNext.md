** Check saldo before update trx by account ???

* Pdf DocUrl en docName validatie
** Add Pdf Validation to PDF Transaction Processor as additional function
Select Years (Drop Down) to process rows of specific year

x <- Select distinct ReferenceNumber, Ref3, Ref4, Administration from mutaties where Ref3 regexp 'google' and Year = jaar(transactionDate)
For rows in x
If url(Ref3) ref3 regexp "file" file exists Ok, next 
elseIf  url(Ref3) ref3 regexp "folder" get filenames in folder and check if documentname exists then get url of filename and update Ref3 record in mutaties 
elseIf find folder url based on referencenumber and check if documentname is in list of filenames in folder 
if documentname exists in filenames of folder get url of filename and Update Ref3 in mutaties
else show missing ID, TransactionNumber, TransactionDate, TransactionDescription, TransactionAmount, ReferencenNumber, Ref3 and Ref4 and Administration in a table on the screen. On Click on a row show update Screen with fieldd with ID, RerferenceNumber, Ref3 and Ref4 to update where Reference Number and/or Ref3 and/or Ref 4 can be updated





Process import Business VisaCard Rabo (GoodwinSolutions)