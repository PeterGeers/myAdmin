** Working on the report function

** Check saldo before update trx by account ???



Show expenses by referencenumber
** Add a tab View ReferenceNumber in de  Tab myAdmin Reports
** Select Administration or All
** Select (multiple) years to be included in the analysis
** Select ReferenceNumber (Dropdown menu and search based on Regex)
** Select 1 or more of the possible Accounts used for the bespoke ReferenceNumber
** Select all rows with bespoke reference number from vw_mutatieswithin the timeframe and selected administration
** Show a trendline of the expenses based on quarter/year summaries And the spend per quarter on top of each measure of the trendline
** Show a table with the transactions used in the analysis



Aangifte P&L and Balance (other column)

Bnb prijs per nacht, aantal nachten violin in reactjs  is beste oplossing. 
Bookings > 1 nacht (filter)
Export jaarrapportage naar xlsx 
Process import Business VisaCard Rabo (GoodwinSolutions)


** Can you give some findings and recommenfations when you lok at the data in select * from vw_mutaties where Administration like "Goodwin%%"
The data is a view on the table muaties (wich has a debet and a credit  code) Vy duplicating the records in a positive and a negative value where debet and credit are now duplicated records). You can have a same look at the table mutaties.

* Realised functions:
** [Check Accounts] Functions that shows the actual values of current banking accounts based on internal calculation and compares it with the records on the last date transactions exist of that specific banking account If there is an error with Rabo bank check sequene number of account since date it is ok.  

** Btw aangifte:
Maak een tab bij rapportages met 'BTW aangifte'
Gebruik de logica zoals in C:\Users\peter\aws\myAdmin\backend\OldRScripts\BTWAangifte.rmd
Maak een html report van de aangifte
Bereid een transactie voor om op te slaan in the tabel mutaties. Haal de vorige transactie op met TransactionNumber = "BTW" om de record indeling te zien. Bij een te betalen bedrag Debet = 2010 en Credit = 1300 Bij een te ontvangen bedrag Debet = 1300 en Credit = 2010. Na controle een Button om de transactie in de tabel mutaties op te slaan. Tevens dient de aangifte te worden opgeladen naar google drive in de folder BTW zoals gebeurt in fe functie pdf_processor.py. BTW Bedragen in de Samenvatting en in de Transaction Preview moetenafgerond zijn in hele getallen (Round, 0)