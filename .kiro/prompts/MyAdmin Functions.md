Implemented functions

Samenvatting
✅ STR Invoice Generator is succesvol geïmplementeerd:
📁 Templates in Google Drive
Nederlandse template: https://drive.google.com/file/d/1uNMxc51kKXngTZHJkduu8LkjjIf0mXU_/view?usp=drivesdk
Engelse template: https://drive.google.com/file/d/1p1wzRXMZBeWglo-cG9tNoZbqJyRuWRQl/view?usp=drivesdk
Templates folder: https://drive.google.com/drive/folders/12FJAYbX5MI3wpGxwahcHykRQfUCRZob1
🔧 Geïmplementeerde functionaliteit:
Backend routes voor zoeken en factuur generatie
HTML templates met professionele styling
Frontend component met zoek- en preview functionaliteit
Google Drive integratie voor template opslag
Automatische berekeningen (prijs per nacht, totalen)
🚀 Gebruik:
Start de backend: python src/app.py
Ga naar "STR Invoice Generator" in het menu
Zoek op gastnaam of reserveringscode
Genereer en print facturen
De templates zijn nu correct opgeslagen in de voorgestelde Google Drive folder structuur en de volledige functionaliteit is geïntegreerd in je myAdmin systeem.
Samenvatting
Ik heb een complete STR Invoice Generator geïmplementeerd voor je myAdmin systeem:
✅ Wat is geïmplementeerd:
HTML Templates (opgeslagen lokaal en voor Google Drive):
Nederlandse factuur template (str_invoice_nl.html)
Engelse factuur template (str_invoice_en.html)
Professionele styling met logo integratie
Automatische berekeningen en conditionele secties
Backend API (str_invoice_routes.py):
/search-booking - Zoek boekingen op gastnaam/reserveringscode
/generate-invoice - Genereer HTML factuur
/upload-template - Upload templates naar Google Drive
Integratie met bestaande BNB database
Frontend Component (STRInvoice.tsx):
Zoekfunctionaliteit met real-time resultaten
Taal selectie (Nederlands/Engels)
Modal preview van facturen
Print functionaliteit
Toegevoegd aan hoofdnavigatie
Hulpscripts:
upload_templates.py - Upload templates naar Google Drive
test_str_invoice.py - Test alle functionaliteit
Uitgebreide README met documentatie
🔧 Hoe te gebruiken:
Templates uploaden naar Google Drive:
cd backend
python upload_templates.py
Copy
bash
Functionaliteit testen:
python test_str_invoice.py
Copy
bash
Frontend gebruiken:
Start de applicatie
Ga naar "STR Invoice Generator"
Zoek op gastnaam of reserveringscode
Genereer en print facturen

📊 Data Flow:
Zoek in bnb tabel op guestName of reservationCode
Haal booking details op (amountGross, checkinDate, etc.)
Bereken factuur details (prijs per nacht, totalen)
Genereer HTML met template (NL/EN)
Toon preview en print optie
De implementatie is volledig geïntegreerd met je bestaande myAdmin architectuur en gebruikt dezelfde database, Google Drive service en styling patterns.

* STR Channel revenue
** Add a tab to the BankingProcessor with the name: STR Channel Revenue.
** Monthly calculation of the STR revenue based on the amounts received in ledger account 1600 in line with the logic in LoadBnBChannelRevenue.R
** Before loading the data the proposed transactions will be shown in a table and after confirmation will be written to the table mutaties
** Make sure the logic of apis will ne used and the relevant testplans have to be updated
** Filters for years and months: Current year minus 1 to curerent year +1 and months 1:12 Administration

* Create a tab bnb-violins in myAdminReports with violin diagrams
** showing either the Price per Night or the Nr of nights per stay
** Drop down selection report Price per Night or Days per Stay
** Drop down selection the Years to be part of the report
** Drop down selection the Listings to be part
** Drop down selection the channels to be part
** Bnb prijs per nacht, aantal nachten violin in reactjs  is beste oplossing. 

* [Check Accounts] Functions that shows the actual values of current banking accounts based on internal calculation and compares it with the records on the last date transactions exist of that specific banking account If there is an error with Rabo bank check sequene number of account since date it is ok.  

* Btw aangifte:
** Maak een tab bij rapportages met 'BTW aangifte'
** Gebruik de logica zoals in C:\Users\peter\aws\myAdmin\backend\OldRScripts\BTWAangifte.rmd
** Maak een html report van de aangifte
** Bereid een transactie voor om op te slaan in the tabel mutaties. Haal de vorige transactie op met TransactionNumber = "BTW" om de record indeling te zien. Bij een te betalen bedrag Debet = 2010 en Credit = 1300 Bij een te ontvangen bedrag Debet = 1300 en Credit = 2010. Na controle een Button om de transactie in de tabel mutaties op te slaan. Tevens dient de aangifte te worden opgeladen naar google drive in de folder BTW zoals gebeurt in fe functie pdf_processor.py. BTW Bedragen in de Samenvatting en in de Transaction Preview moetenafgerond zijn in hele getallen (Round, 0)

* Show expenses by referencenumber:
** Add a tab View ReferenceNumber in de  Tab myAdmin Reports
** Select Administration or All
** Select (multiple) years to be included in the analysis
** Select ReferenceNumber (Dropdown menu and search based on Regex)
** Select 1 or more of the possible Accounts used for the bespoke ReferenceNumber
** Select all rows with bespoke reference number from vw_mutaties within the timeframe and selected administration
** Show a trendline of the expenses based on quarter/year summaries And the spend per quarter on top of each measure of the trendline
** Show a table with the transactions used in the analysis

* Can you give some findings and recommenfations when you lok at the data in select * from mutaties where Administration like "Goodwin%%"
** The data is a view on the table muaties (wich has a debet and a credit  code)

* Aangifte Inkomstenbelasting  
** Add a tab to MyAdmin reports nanmed (Aangifte IB)
** Use the table vw_mutaties (contains all relevant data)
** Select Year (limited to available dates and 1 only)
** Select Administration (limited to available administration in bespoke year(s))
** Use the column Aangifte as the base to summarize
*** if VW = N the calculation is always from beginning (all frecords of Administration until to end of Year selected (31-12-YEAR)
*** if VW = Y the calculation is SUM(Amount) from transactions where jaar == Year
** Fields to show: Parent, Aangifte, Amount with a subtotal by Parent
** On click in a row show the underlying accounts(reknum)
** Add a grand total 

* Show repetive boookings from a guestName in bnb 
** Ad tab to myAdmin reports with the name bnb Terugkerend
** Summarize bookings on guestName
** Select only guestNames where Aantal > 1 (filter)
** Show Aantal, guestName, Sort(Aantal,  GuestName)
** On click on the row show the bnb records involoved


* 📊 myReporting: React + MySQL + Recharts Reporting Dashboard
** 📚 Resources
*** Recharts Documentation**: https://recharts.org/en-US/
*** Recharts Examples**: https://recharts.org/en-US/examples/
*** React Grid Layout**: https://github.com/react-grid-layout/react-grid-layout
*** Chakra UI Components**: https://chakra-ui.com/
*** React TypeScript**: https://react-typescript-cheatsheet.netlify.app/
** 🛠 Aanbevelingen
*** Gebruik `ResponsiveContainer` voor alle charts
*** Implementeer loading states en error handling
*** Gebruik TypeScript voor type safety
*** Test charts op verschillende schermgroottes
*** Optimaliseer data queries voor performance
*** Gebruik `.env` voor database configuratie
*** Sla dashboard layout op in localStorage of database
*** Implementeer widget add/remove functionaliteit
*** Voeg export functie toe voor dashboard screenshots
** ✅ Doel
*** Een veilige, interactieve rapportagefunctie bouwen in ReactJS die financiële data uit een MySQL-database ophaalt en visualiseert met Recharts.

* Prompt for BnB actuals dashboard in myAdmin eports
** Add a dashboard BnB actuals in myAdmin Report
** The data in this dashboard should be limited to the data in the tables bnb, bnbplanned, bnbfuture for field definions see 'mysql table fields.md'

** The following filters are needed (see myFilters.md for specification)
*** Year To filter the data for a specific year
**** it must be possible to select 1 or more of the year (distinct year) by clicking on a selection field
*** Listing to select 1 or all of the possible listings
*** Channel to select 1 or more of the possible channels
*** The option to show the data per quarter [q] or month [m]
*** Filter to select the view of the table to be Listing or Channel in the column header
*** Filter to select which amounts must be shown with this list: amountGross, amountNett, amountChannelFee, amountTouristTax, amountVat (Muli selectable)

*** Display format
** The following table should be shown
*** Listing or Channel as column header (X-axis)
*** Year with quarter and month as subitems in the first Columns (Y-axis)  Must be easy to collapse or extend using a plus/minus sign before each row
**** This need the amountGross, amountNett, amountChannelFee, amountTouristTax and amountVat to be summarized by listing, and period (year, q,  m))
**** fields: Listing, year, q, m, amountGross, amountNett, amountChannelFee, amountTouristTax, amountVat
*** The option to expand thr view to q and m.


*** Table layout 
**** Y-Axis: width (120px),  1 column with year, indent 2 characters for q and another 2 for m
**** X-Axis: width (100 px for period and 60 px for each column presenting an amount) 
***** Labels must be right aligned with the amounts
**** Cells: Summarized Amount for all leveld year, q, m and total
 
**** No white line between the rows
**** Minimize space between table header and table
*** Sort order of selected rows from new to old f.e. 2025 [4,3,2,1] of [12,11,10,09,08,07,06,05,04,03,02,01], 2024, 2023

* DashBoard actuals Prompt for dashboard actuals in myAdmin eports
** The data in this dashboard should be limited to the data in vw_mutaties

** The following filters are needed (see myFilters.md for specification)
*** Year To filter the data for a specific jaar
**** it must be possible to select 1 or more of the jaar (distinct jaar) by clicking on a selection field
*** Administration to filter tha data on a specific Administration 
*** Display format

** The following tables should be shown
*** Balance (This need the data to be summarized by ledger from the beginning (all years including the last year) where VW is == N
**** fields: Parent, ledger, VW, jaar, kwartaal, maand, summarized(Amount)
*** Profit/Loss: This need the contain the data to be summarized by ledger for the selected Year where VW == Y)
**** fields: Parent, ledger, VW, jaar, kwartaal, maand, summarized(Amount)
*** The option to expand to kwartaal and to month

*** Table layout 
**** Y-Axis: width (120px),  1 column with Parent, indent 2 characters for ledger
**** X-Axis: width (60 px for each column presented ) A column for each year selected. 
***** Align Can the year column headers  in the  Profit/Loss table be right aligned woth the amounts
**** Cells: Summarized Amount with the option 
**** It is the intention that 1 Parent has 1-N ledgers and the Amount per Parent is summarized as well as the Total amount for all ledgers.  
**** No white line between the rows
**** Minimize space between table header and table
*** Sort order of selected rows from old to new f.e. 2023, 2024, 2025

** Piechart for Balance table: 
*** "CustomActiveShapePieChart" to the dashboard
*** Make all values positive
*** Add to the same row as the balance table but with phone support it should move below
*** Ledger text as legenda bij de vlakken

** Barchart for BProfit/Loss table: 
*** "BiaxialBarChart" to the dashboard
*** Multiply values of ledger itnms in the parent 8000 with -1
*** Add to the same row as the Profit/Loss table but with phone support it should move below
*** Ledger text as legenda bij de vlakken
*** Leave ledger 8099 Bijzondere baten en lasten out of the Graph
*** graph for each selected yearcompare year by year
*** Add message to bar chart 8099 Bijzondere baten en lasten not included



* Check Reference is a tab in myAdmin reports puropose: To identify if all invoices are paid for or paid invoices are booked in the administration. It checks at ReferenceNumber within a ledger within an Administration
** Cascading Filters: Administratiion >> Ledger >> Reference Number 
** Button : Check references updates the data necessary to load
* Table1: Reference Summary Shows all ReferenceNumbers and the Summarized amount available within the filters WHERE the summarized amount is != 0
** Table with the same look and feel as tables in Actuals including a Total
* Table 2: Shows all the records belonging to the specified ReferenceNumber in table 1 and the selected filters order by TransactionDate
**  Fields TransactionDate, TransactiionNumber, Amount, TransactionDescription
**** Date format on display: yyyy-mm-dd 
** Table with the same look and feel as tables in Actuals including a Totalcd scripts


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
