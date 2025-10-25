** Working on the report function

** Check saldo before update trx by account ???

Show expenses by referencenumber
Aangifte P&L and Balance (other column)
Btw aangifte
Bnb prijs per nacht, aantal nachten violin in reactjs  is beste oplossing. 
Bookings > 1 nacht (filter)
Export jaarrapportage naar xlsx 
Process import Business VisaCard Rabo (GoodwinSolutions)


** Can you give some findings and recommenfations when you lok at the data in select * from vw_mutaties where Administration like "Goodwin%%"
The data is a view on the table muaties (wich has a debet and a credit  code) Vy duplicating the records in a positive and a negative value where debet and credit are now duplicated records). You can have a same look at the table mutaties.

* Realised functions:
** [Check Accounts] Functions that shows the actual values of current banking accounts based on internal calculation and compares it with the records on the last date transactions exist of that specific banking account If there is an error with Rabo bank check sequene number of account since date it is ok.  