* Check Reference is a tab in myAdmin reportspuropose: To identify if all invoices are paid for or paid invoices are booked in the administration. It checks at ReferenceNumber within a ledger within an Administration
** Cascading Filters: Administratiion >> Ledger >> Reference Number 
** Button : Check references updates the data necessary to load

* Table1: Reference Summary Shows all ReferenceNumbers and the Summarized amount available within the filters WHERE the summarized amount is != 0
** Table with the same look and feel as tables in Actuals including a Total

* Table 2: Shows all the records belonging to the specified ReferenceNumber in table 1 and the selected filters order by TransactionDate
**  Fields TransactionDate, TransactiionNumber, Amount, TransactionDescription
**** Date format on display: yyyy-mm-dd 
** Table with the same look and feel as tables in Actuals including a Totalcd scripts